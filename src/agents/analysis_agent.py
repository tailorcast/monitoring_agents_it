"""AI-powered root cause analysis agent."""

import json
import re
import logging
from typing import List, Dict

from ..services.bedrock_client import BedrockClient
from ..services.budget_tracker import BudgetTracker
from ..utils.metrics import CollectorResult
from ..utils.status import HealthStatus


class AnalysisAgent:
    """
    Root cause analysis agent using Claude Haiku.

    Analyzes infrastructure issues, correlates related problems,
    and generates actionable recommendations.
    """

    def __init__(self, bedrock_client: BedrockClient, budget_tracker: BudgetTracker, logger: logging.Logger = None):
        """
        Initialize analysis agent.

        Args:
            bedrock_client: Bedrock client for LLM calls
            budget_tracker: Budget tracker to enforce spending limits
            logger: Optional logger instance
        """
        self.bedrock = bedrock_client
        self.budget = budget_tracker
        self.logger = logger or logging.getLogger(__name__)

    async def analyze(self, issues: List[CollectorResult]) -> Dict:
        """
        Perform root cause analysis on detected issues.

        Args:
            issues: List of CollectorResult with RED or YELLOW status

        Returns:
            dict: Analysis result with keys:
                - root_cause: Brief explanation of underlying cause
                - severity: critical|high|medium|low
                - affected_systems: List of affected system names
                - recommendations: List of actionable recommendations
                - token_usage: Token consumption details
        """
        # Handle no issues case
        if not issues:
            self.logger.info("No issues to analyze")
            return {
                "root_cause": "No issues detected",
                "severity": "none",
                "affected_systems": [],
                "recommendations": [],
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            }

        # Check budget before LLM call
        if not self.budget.can_make_request(estimated_tokens=8000):
            self.logger.warning("Budget exceeded, skipping AI analysis")
            return {
                "root_cause": "Budget exceeded - analysis skipped",
                "severity": "unknown",
                "affected_systems": [issue.target_name for issue in issues],
                "recommendations": [
                    {
                        "priority": "high",
                        "action": "Increase daily LLM budget or optimize prompt usage",
                        "rationale": "Unable to perform analysis due to budget constraints"
                    }
                ],
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            }

        # Build analysis prompt
        prompt = self._build_analysis_prompt(issues)
        system_prompt = self._get_system_prompt()

        try:
            # Call Claude
            self.logger.info(f"Analyzing {len(issues)} issue(s) with AI")
            response, usage = await self.bedrock.ainvoke(prompt, system_prompt)

            # Record token usage
            self.budget.record_usage(usage['input_tokens'], usage['output_tokens'])

            # Parse response
            analysis = self._parse_analysis_response(response)
            analysis['token_usage'] = usage

            self.logger.info(
                f"Analysis completed: {analysis.get('severity', 'unknown')} severity, "
                f"{len(analysis.get('recommendations', []))} recommendations"
            )

            return analysis

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                "root_cause": f"Analysis error: {str(e)}",
                "severity": "unknown",
                "affected_systems": [issue.target_name for issue in issues],
                "recommendations": [
                    {
                        "priority": "high",
                        "action": "Manual investigation required",
                        "rationale": "Automated analysis failed"
                    }
                ],
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "error": str(e)
            }

    def _build_analysis_prompt(self, issues: List[CollectorResult]) -> str:
        """
        Build structured analysis prompt from issues.

        Groups issues by collector type and formats them for Claude.

        Args:
            issues: List of issues to analyze

        Returns:
            str: Formatted prompt
        """
        prompt = "# Infrastructure Issues Detected\n\n"

        # Group issues by collector type for better correlation
        by_collector = {}
        for issue in issues:
            by_collector.setdefault(issue.collector_name, []).append(issue)

        # Format each collector group
        for collector_name, collector_issues in sorted(by_collector.items()):
            prompt += f"## {collector_name.upper()} Issues\n\n"

            for issue in collector_issues:
                status_emoji = issue.status.to_emoji()
                prompt += f"{status_emoji} **{issue.target_name}**\n"
                prompt += f"- Status: {issue.status.value.upper()}\n"
                prompt += f"- Message: {issue.message}\n"

                if issue.metrics:
                    # Format key metrics (limit to most important)
                    metrics_str = ", ".join([f"{k}={v}" for k, v in list(issue.metrics.items())[:5]])
                    prompt += f"- Metrics: {metrics_str}\n"

                if issue.error:
                    prompt += f"- Error: {issue.error}\n"

                prompt += "\n"

        # Add analysis instructions
        prompt += """
---

Analyze these infrastructure issues and provide:

1. **Root Cause**: Identify underlying cause by correlating related issues
2. **Severity**: Assess overall impact (critical/high/medium/low)
3. **Affected Systems**: List impacted system names
4. **Recommendations**: Provide specific, actionable remediation steps with priorities

**Respond in JSON format:**

```json
{
  "root_cause": "Brief explanation of the underlying cause",
  "severity": "critical|high|medium|low",
  "affected_systems": ["system1", "system2"],
  "recommendations": [
    {
      "priority": "immediate|high|medium|low",
      "action": "Specific remediation step",
      "rationale": "Why this will help resolve the issue"
    }
  ]
}
```

Be concise and practical. Focus on actionable insights.
"""
        return prompt

    def _get_system_prompt(self) -> str:
        """
        Get system prompt for Claude.

        Returns:
            str: System prompt defining Claude's role
        """
        return """You are an expert Site Reliability Engineer (SRE) and infrastructure analyst.

Your expertise includes:
- Root cause analysis and issue correlation
- Cloud infrastructure (AWS, Azure, VPS servers)
- Container orchestration (Docker)
- Database performance and reliability
- API monitoring and debugging
- System resource optimization

Your analysis should be:
- **Practical**: Focus on actionable recommendations
- **Concise**: Get to the point quickly
- **Structured**: Use the requested JSON format
- **Evidence-based**: Reference specific metrics and symptoms

Always correlate related issues to identify systemic problems rather than treating each issue in isolation."""

    def _parse_analysis_response(self, response: str) -> Dict:
        """
        Parse Claude's JSON response.

        Handles various response formats including markdown code blocks.

        Args:
            response: Raw response from Claude

        Returns:
            dict: Parsed analysis result
        """
        try:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to extract JSON without code block
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # No JSON found, use response as-is
                    raise ValueError("No JSON found in response")

            # Parse JSON
            analysis = json.loads(json_str)

            # Validate required fields
            if 'root_cause' not in analysis:
                analysis['root_cause'] = "Unable to determine root cause"

            if 'severity' not in analysis:
                analysis['severity'] = "unknown"

            if 'affected_systems' not in analysis:
                analysis['affected_systems'] = []

            if 'recommendations' not in analysis:
                analysis['recommendations'] = []

            # Validate recommendation structure
            for rec in analysis['recommendations']:
                if 'priority' not in rec:
                    rec['priority'] = 'medium'
                if 'action' not in rec:
                    rec['action'] = 'No action specified'
                if 'rationale' not in rec:
                    rec['rationale'] = ''

            return analysis

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse analysis response: {e}")
            self.logger.debug(f"Response text: {response[:500]}")

            # Return fallback analysis
            return {
                "root_cause": "Unable to parse AI analysis response",
                "severity": "unknown",
                "affected_systems": [],
                "recommendations": [
                    {
                        "priority": "high",
                        "action": "Manual investigation required",
                        "rationale": "Automated analysis parsing failed"
                    }
                ],
                "parse_error": str(e),
                "raw_response": response[:500]  # Include truncated response for debugging
            }
