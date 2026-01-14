"""Report generation agent for Telegram notifications."""

import time
import logging
from datetime import datetime
from typing import List, Dict

from .state import MonitoringState
from ..utils.metrics import CollectorResult
from ..utils.status import HealthStatus


class ReportAgent:
    """
    Generates formatted Telegram reports from monitoring state.

    Creates structured messages with emojis, status summaries,
    detailed issues, and AI analysis results.
    """

    def __init__(self, logger: logging.Logger = None):
        """
        Initialize report agent.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    async def generate_report(self, state: MonitoringState) -> str:
        """
        Generate formatted Telegram report from workflow state.

        Args:
            state: MonitoringState with collection and analysis results

        Returns:
            str: Formatted Telegram message (markdown)
        """
        all_results = state.get('all_results', [])
        issues = state.get('issues', [])
        analysis = state.get('root_cause_analysis', {})

        self.logger.info(f"Generating report: {len(all_results)} total checks, {len(issues)} issues")

        # Build report sections
        report = self._build_header(all_results, issues)
        report += "\n" + self._build_summary_section(all_results)

        if issues:
            report += "\n" + self._build_issues_section(issues)
            report += "\n" + self._build_analysis_section(analysis)

        report += "\n" + self._build_footer(state)

        return report

    def _build_header(self, all_results: List[CollectorResult], issues: List[CollectorResult]) -> str:
        """
        Build report header with overall status.

        Args:
            all_results: All check results
            issues: Only RED/YELLOW results

        Returns:
            str: Formatted header
        """
        total = len(all_results)
        passed = total - len(issues)

        # Count by severity
        red_count = len([i for i in issues if i.status == HealthStatus.RED])
        yellow_count = len([i for i in issues if i.status == HealthStatus.YELLOW])

        # Determine overall status
        if red_count > 0:
            overall_emoji = "🔴"
            overall_status = "Critical Issues"
        elif yellow_count > 0:
            overall_emoji = "🟡"
            overall_status = "Warnings"
        else:
            overall_emoji = "🟢"
            overall_status = "All Systems Healthy"

        # Format timestamp
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

        header = f"""{overall_emoji} **Infrastructure Health Report**
📅 {timestamp}

📊 **Overall Status**: {overall_status}
✅ {passed}/{total} checks passed
"""

        if red_count > 0:
            header += f"🔴 {red_count} critical issue(s)\n"
        if yellow_count > 0:
            header += f"🟡 {yellow_count} warning(s)\n"

        header += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

        return header

    def _build_summary_section(self, all_results: List[CollectorResult]) -> str:
        """
        Build summary section grouped by collector type.

        Args:
            all_results: All check results

        Returns:
            str: Formatted summary
        """
        # Group by collector type
        by_collector = {}
        for result in all_results:
            by_collector.setdefault(result.collector_name, []).append(result)

        summary = "## 📦 Summary by Type\n\n"

        for collector_name, results in sorted(by_collector.items()):
            issues = [r for r in results if r.status != HealthStatus.GREEN]
            passed = len(results) - len(issues)

            # Determine worst status for this collector
            if issues:
                worst_status = min(
                    issues,
                    key=lambda x: ['green', 'yellow', 'red', 'unknown'].index(x.status.value)
                ).status
                status_emoji = worst_status.to_emoji()
            else:
                status_emoji = "🟢"

            summary += f"{status_emoji} **{collector_name.upper()}**: {passed}/{len(results)} healthy\n"

        return summary

    def _build_issues_section(self, issues: List[CollectorResult]) -> str:
        """
        Build detailed issues section.

        Args:
            issues: List of RED/YELLOW results

        Returns:
            str: Formatted issues section
        """
        section = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        section += "## 🚨 Issues Detected\n\n"

        # Group by severity
        red_issues = [i for i in issues if i.status == HealthStatus.RED]
        yellow_issues = [i for i in issues if i.status == HealthStatus.YELLOW]
        unknown_issues = [i for i in issues if i.status == HealthStatus.UNKNOWN]

        # Critical issues
        if red_issues:
            section += "### 🔴 Critical Issues\n\n"
            for issue in red_issues:
                section += f"**{issue.target_name}** ({issue.collector_name})\n"
                section += f"└─ {issue.message}\n"

                if issue.metrics:
                    metrics_str = self._format_metrics(issue.metrics)
                    section += f"   📊 {metrics_str}\n"

                section += "\n"

        # Warnings
        if yellow_issues:
            section += "### 🟡 Warnings\n\n"
            for issue in yellow_issues:
                section += f"**{issue.target_name}** ({issue.collector_name})\n"
                section += f"└─ {issue.message}\n"

                if issue.metrics:
                    metrics_str = self._format_metrics(issue.metrics)
                    section += f"   📊 {metrics_str}\n"

                section += "\n"

        # Unknown status
        if unknown_issues:
            section += "### ⚪ Unknown Status\n\n"
            for issue in unknown_issues:
                section += f"**{issue.target_name}** ({issue.collector_name})\n"
                section += f"└─ {issue.message}\n\n"

        return section

    def _build_analysis_section(self, analysis: Dict) -> str:
        """
        Build AI analysis section.

        Args:
            analysis: Analysis result from AnalysisAgent

        Returns:
            str: Formatted analysis section
        """
        section = "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        section += "## 🤖 AI Analysis\n\n"

        if not analysis or isinstance(analysis, str):
            section += f"{analysis or 'No analysis available'}\n"
            return section

        # Root cause
        root_cause = analysis.get('root_cause', 'Unknown')
        severity = analysis.get('severity', 'unknown').upper()

        section += f"**Root Cause**: {root_cause}\n"
        section += f"**Severity**: {severity}\n\n"

        # Affected systems
        affected = analysis.get('affected_systems', [])
        if affected:
            section += f"**Affected Systems**: {', '.join(affected[:5])}\n"
            if len(affected) > 5:
                section += f"   ... and {len(affected) - 5} more\n"
            section += "\n"

        # Recommendations
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            section += "**Recommended Actions**:\n\n"

            for i, rec in enumerate(recommendations, 1):
                priority = rec.get('priority', 'medium').upper()
                action = rec.get('action', 'No action specified')
                rationale = rec.get('rationale', '')

                # Priority emoji
                priority_emoji = {
                    'IMMEDIATE': '🔥',
                    'HIGH': '⚠️',
                    'MEDIUM': 'ℹ️',
                    'LOW': '💡'
                }.get(priority, 'ℹ️')

                section += f"{i}. {priority_emoji} **[{priority}]** {action}\n"

                if rationale:
                    section += f"   └─ {rationale}\n"

                section += "\n"

        return section

    def _build_footer(self, state: MonitoringState) -> str:
        """
        Build footer with execution metadata.

        Args:
            state: MonitoringState with execution metadata

        Returns:
            str: Formatted footer
        """
        # Calculate execution time
        execution_start = state.get('execution_start', time.time())
        duration = time.time() - execution_start

        # Get token usage
        token_usage = state.get('token_usage', 0)

        # Get errors
        errors = state.get('errors', [])

        footer = "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        footer += f"⏱ **Execution time**: {duration:.1f}s\n"
        footer += f"🔤 **LLM tokens used**: {token_usage:,}\n"

        if errors:
            footer += f"⚠️ **Errors encountered**: {len(errors)}\n"

        footer += "\n_Generated by Monitoring AI Agent_"

        return footer

    def _format_metrics(self, metrics: Dict, max_items: int = 3) -> str:
        """
        Format metrics dict for display.

        Args:
            metrics: Metrics dictionary
            max_items: Maximum number of metrics to show

        Returns:
            str: Formatted metrics string
        """
        if not metrics:
            return "No metrics"

        # Format key-value pairs
        items = []
        for k, v in list(metrics.items())[:max_items]:
            # Format value based on type
            if isinstance(v, float):
                formatted_v = f"{v:.2f}"
            elif isinstance(v, int):
                formatted_v = f"{v:,}"
            else:
                formatted_v = str(v)

            items.append(f"{k}={formatted_v}")

        result = ", ".join(items)

        # Add ellipsis if truncated
        if len(metrics) > max_items:
            result += f", ... ({len(metrics) - max_items} more)"

        return result
