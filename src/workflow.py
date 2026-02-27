"""LangGraph workflow for monitoring orchestration."""

import asyncio
import dataclasses
import time
import logging
import os
from typing import Dict

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    StateGraph = None
    END = None

from .agents.state import MonitoringState
from .agents.analysis_agent import AnalysisAgent
from .agents.report_agent import ReportAgent
from .services.bedrock_client import BedrockClient
from .services.budget_tracker import BudgetTracker
from .services.metric_history import MetricHistoryStore
from .config.models import MonitoringSystemConfig
from .utils.status import HealthStatus
from .utils.logger import setup_logger

# Import collectors
from .collectors.ec2_collector import EC2Collector
from .collectors.vps_collector import VPSCollector
from .collectors.docker_collector import DockerCollector
from .collectors.api_collector import APICollector
from .collectors.database_collector import DatabaseCollector
from .collectors.llm_collector import LLMCollector
from .collectors.s3_collector import S3Collector


class MonitoringWorkflow:
    """
    LangGraph workflow orchestrator for infrastructure monitoring.

    Coordinates parallel data collection, AI analysis, and report generation.
    """

    def __init__(self, config: MonitoringSystemConfig, logger: logging.Logger = None):
        """
        Initialize monitoring workflow.

        Args:
            config: System configuration
            logger: Optional logger instance

        Raises:
            ImportError: If langgraph not installed
        """
        if StateGraph is None:
            raise ImportError("langgraph library not installed. Install with: pip install langgraph>=0.2.0")

        self.config = config
        self.logger = logger or setup_logger("workflow")

        # Setup LangSmith tracing if enabled
        self._setup_langsmith()

        # Initialize AI components
        self.logger.info("Initializing AI components...")
        self.bedrock_client = BedrockClient(config.llm, self.logger)
        self.budget_tracker = BudgetTracker(
            daily_budget_usd=config.llm.daily_budget_usd,
            logger=self.logger
        )
        self.history_store = MetricHistoryStore(
            history_file=config.monitoring.history_file_path,
            logger=self.logger
        )

        # Initialize agents
        self.analysis_agent = AnalysisAgent(
            self.bedrock_client,
            self.budget_tracker,
            self.logger
        )
        self.report_agent = ReportAgent(self.logger)

        # Initialize collectors
        self.logger.info("Initializing collectors...")
        thresholds_dict = config.thresholds.__dict__

        self.collectors = {}

        if config.targets.ec2_instances:
            self.collectors["ec2"] = EC2Collector(
                config.targets.ec2_instances,
                thresholds_dict,
                self.logger
            )

        if config.targets.vps_servers:
            self.collectors["vps"] = VPSCollector(
                config.targets.vps_servers,
                thresholds_dict,
                self.logger
            )
            # VPS servers are also used for Docker
            self.collectors["docker"] = DockerCollector(
                config.targets.vps_servers,
                thresholds_dict,
                self.logger
            )

        if config.targets.api_endpoints:
            self.collectors["api"] = APICollector(
                config.targets.api_endpoints,
                thresholds_dict,
                self.logger
            )

        if config.targets.databases:
            self.collectors["database"] = DatabaseCollector(
                config.targets.databases,
                thresholds_dict,
                self.logger
            )

        if config.targets.llm_models:
            self.collectors["llm"] = LLMCollector(
                config.targets.llm_models,
                thresholds_dict,
                self.logger
            )

        if config.targets.s3_buckets:
            self.collectors["s3"] = S3Collector(
                config.targets.s3_buckets,
                thresholds_dict,
                self.logger
            )

        self.logger.info(f"Initialized {len(self.collectors)} collector(s)")

        # Build LangGraph workflow
        self.graph = self._build_graph()
        self.logger.info("Workflow initialized successfully")

    def _setup_langsmith(self):
        """
        Setup LangSmith tracing if environment variables are configured.

        Set these environment variables to enable:
        - LANGCHAIN_TRACING_V2=true
        - LANGCHAIN_API_KEY=your_api_key
        - LANGCHAIN_PROJECT=monitoring-agents (optional)
        """
        if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
            api_key = os.getenv("LANGCHAIN_API_KEY")
            project = os.getenv("LANGCHAIN_PROJECT", "monitoring-agents")

            if api_key:
                self.logger.info(f"LangSmith tracing enabled for project: {project}")
                self.logger.info("View traces at: https://smith.langchain.com")
            else:
                self.logger.warning(
                    "LANGCHAIN_TRACING_V2 is enabled but LANGCHAIN_API_KEY is not set. "
                    "Tracing will not work."
                )
        else:
            self.logger.debug("LangSmith tracing disabled")

    def _build_graph(self) -> StateGraph:
        """
        Construct LangGraph workflow.

        Graph structure:
        - Entry: aggregate (runs all collectors in parallel)
        - Sequential: aggregate → analyze → generate_report → send_telegram → END

        Returns:
            Compiled StateGraph
        """
        workflow = StateGraph(MonitoringState)

        # Add processing nodes
        workflow.add_node("aggregate", self._aggregate_results)
        workflow.add_node("history_filter", self._history_filter)
        workflow.add_node("analyze", self._ai_analysis)
        workflow.add_node("generate_report", self._generate_report)
        workflow.add_node("send_telegram", self._send_telegram)

        # Set entry point
        workflow.set_entry_point("aggregate")

        # Define sequential flow
        workflow.add_edge("aggregate", "history_filter")
        workflow.add_edge("history_filter", "analyze")
        workflow.add_edge("analyze", "generate_report")
        workflow.add_edge("generate_report", "send_telegram")
        workflow.add_edge("send_telegram", END)

        return workflow.compile()

    async def _aggregate_results(self, state: MonitoringState) -> Dict:
        """
        Collect data from all collectors in parallel and aggregate results.

        This node runs all collectors concurrently using asyncio.gather
        instead of using LangGraph parallel edges (simpler implementation).

        Args:
            state: Current workflow state

        Returns:
            dict: Updates to state (all_results, issues)
        """
        self.logger.info(f"Starting parallel collection from {len(self.collectors)} collector(s)")

        # Run all collectors in parallel
        collector_tasks = [
            collector.collect()
            for collector in self.collectors.values()
        ]

        # Wait for all collectors to complete
        results = await asyncio.gather(*collector_tasks, return_exceptions=True)

        # Flatten and process results
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                collector_name = list(self.collectors.keys())[i] if i < len(self.collectors) else "unknown"
                self.logger.error(f"Collector '{collector_name}' failed: {result}")

                # Add error to state
                errors = state.get('errors', [])
                errors.append(f"{collector_name}: {str(result)}")

                continue

            # Extend results (each collector returns list)
            if isinstance(result, list):
                all_results.extend(result)
            else:
                self.logger.warning(f"Unexpected collector result type: {type(result)}")

        # Filter issues (RED, YELLOW, or UNKNOWN status)
        issues = [
            r for r in all_results
            if r.status in [HealthStatus.RED, HealthStatus.YELLOW, HealthStatus.UNKNOWN]
        ]

        self.logger.info(
            f"Collection complete: {len(all_results)} total checks, "
            f"{len(issues)} issue(s) detected"
        )

        return {
            "all_results": all_results,
            "issues": issues
        }

    async def _history_filter(self, state: MonitoringState) -> Dict:
        """
        Dampen first-occurrence threshold breaches from RED to YELLOW.

        Binary failures (connection errors, container down) are never touched.
        Only numeric threshold metrics (CPU, RAM, disk, API response time) may be
        downgraded on their first occurrence today; subsequent occurrences stay RED.

        Args:
            state: Current workflow state with raw all_results

        Returns:
            dict: Updated all_results and issues
        """
        thresholds = self.config.thresholds.__dict__
        adjusted = []

        for result in state.get("all_results", []):
            if result.status != HealthStatus.RED:
                adjusted.append(result)
                continue

            red_keys = self.history_store.get_red_metric_keys(result, thresholds)

            if not red_keys:
                # Binary failure or collector not in THRESHOLD_METRICS — pass through
                adjusted.append(result)
                continue

            all_first_occurrence = all(
                self.history_store.get_daily_count(k) == 0 for k in red_keys
            )

            # Always increment counts for all red metric keys
            for k in red_keys:
                self.history_store.increment(k)

            if all_first_occurrence:
                dampened = dataclasses.replace(
                    result,
                    status=HealthStatus.YELLOW,
                    message=result.message + " [first occurrence today]",
                )
                self.logger.info(
                    f"Dampened first-occurrence RED → YELLOW: "
                    f"{result.collector_name}:{result.target_name} ({red_keys})"
                )
                adjusted.append(dampened)
            else:
                adjusted.append(result)

        issues = [
            r for r in adjusted
            if r.status in [HealthStatus.RED, HealthStatus.YELLOW, HealthStatus.UNKNOWN]
        ]

        self.logger.info(
            f"History filter complete: {len(adjusted)} results, {len(issues)} issue(s)"
        )

        return {"all_results": adjusted, "issues": issues}

    async def _ai_analysis(self, state: MonitoringState) -> Dict:
        """
        Perform AI-powered root cause analysis.

        Args:
            state: Current workflow state with issues

        Returns:
            dict: Updates to state (root_cause_analysis, recommendations, token_usage)
        """
        issues = state.get('issues', [])

        if not issues:
            self.logger.info("No issues to analyze, skipping AI analysis")
            return {
                "root_cause_analysis": {"root_cause": "All systems healthy"},
                "recommendations": [],
                "token_usage": 0
            }

        self.logger.info(f"Starting AI analysis of {len(issues)} issue(s)")

        # Run analysis
        analysis_result = await self.analysis_agent.analyze(issues)

        token_usage = analysis_result.get('token_usage', {}).get('total_tokens', 0)

        self.logger.info(f"AI analysis complete: {token_usage} tokens used")

        return {
            "root_cause_analysis": analysis_result,
            "recommendations": analysis_result.get('recommendations', []),
            "token_usage": token_usage
        }

    async def _generate_report(self, state: MonitoringState) -> Dict:
        """
        Generate formatted Telegram report.

        Args:
            state: Current workflow state with analysis results

        Returns:
            dict: Updates to state (telegram_message)
        """
        self.logger.info("Generating Telegram report")

        report = await self.report_agent.generate_report(state)

        self.logger.debug(f"Report generated: {len(report)} characters")

        return {
            "telegram_message": report
        }

    async def _send_telegram(self, state: MonitoringState) -> Dict:
        """
        Send report via Telegram.

        Args:
            state: Current workflow state with telegram_message

        Returns:
            dict: Dict with delivery status
        """
        message = state.get('telegram_message', '')

        if not message:
            self.logger.warning("No Telegram message to send")
            return {"telegram_sent": False}

        self.logger.info("Sending report via Telegram")

        try:
            # Import here to handle optional dependency
            from .services.telegram_client import TelegramClient

            telegram = TelegramClient(self.config.telegram, self.logger)
            success = await telegram.send_message(message)

            if success:
                self.logger.info("Telegram report delivered successfully")
            else:
                self.logger.error("Failed to deliver Telegram report")

            return {"telegram_sent": success}

        except ImportError as e:
            self.logger.error(
                f"Telegram library not available: {e}. "
                "Install with: pip install python-telegram-bot>=20.8"
            )
            return {"telegram_sent": False}

        except Exception as e:
            self.logger.error(f"Telegram delivery failed: {e}", exc_info=True)
            return {"telegram_sent": False}

    def visualize_graph(self, output_path: str = "workflow_graph.png") -> bool:
        """
        Generate visual representation of the workflow graph.

        Args:
            output_path: Path to save the graph image

        Returns:
            bool: True if visualization was generated successfully
        """
        try:
            # Generate mermaid PNG
            mermaid_png = self.graph.get_graph().draw_mermaid_png()

            with open(output_path, 'wb') as f:
                f.write(mermaid_png)

            self.logger.info(f"Graph visualization saved to {output_path}")
            return True

        except ImportError as e:
            self.logger.error(
                f"Graph visualization requires additional dependencies: {e}\n"
                "Install with: pip install pygraphviz or pip install grandalf"
            )
            return False

        except Exception as e:
            self.logger.error(f"Failed to generate graph visualization: {e}")
            return False

    async def run(self) -> MonitoringState:
        """
        Execute the complete monitoring workflow.

        Returns:
            MonitoringState: Final state after workflow completion
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting monitoring workflow execution")
        self.logger.info("=" * 60)

        # Initialize state
        initial_state: MonitoringState = {
            "execution_start": time.time(),
            "token_usage": 0,
            "errors": []
        }

        try:
            # Execute workflow
            final_state = await self.graph.ainvoke(initial_state)

            # Log summary
            duration = time.time() - initial_state['execution_start']
            total_checks = len(final_state.get('all_results', []))
            issues_count = len(final_state.get('issues', []))
            tokens = final_state.get('token_usage', 0)

            self.logger.info("=" * 60)
            self.logger.info("Workflow execution completed")
            self.logger.info(f"Duration: {duration:.1f}s")
            self.logger.info(f"Checks: {total_checks} total, {issues_count} issues")
            self.logger.info(f"Tokens: {tokens:,}")
            self.logger.info("=" * 60)

            return final_state

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            raise
