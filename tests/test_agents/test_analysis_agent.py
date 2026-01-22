"""Tests for AnalysisAgent."""

import pytest
import json
from unittest.mock import AsyncMock, Mock
from src.agents.analysis_agent import AnalysisAgent
from src.utils.metrics import CollectorResult
from src.utils.status import HealthStatus


@pytest.fixture
def mock_bedrock_client():
    """Create mocked BedrockClient."""
    client = Mock()
    client.ainvoke = AsyncMock()
    return client


@pytest.fixture
def mock_budget_tracker():
    """Create mocked BudgetTracker."""
    tracker = Mock()
    tracker.can_make_request = Mock(return_value=True)
    tracker.record_usage = Mock()
    return tracker


@pytest.fixture
def sample_issues():
    """Create sample issues for testing."""
    return [
        CollectorResult(
            collector_name="ec2",
            target_name="prod-server-1",
            status=HealthStatus.RED,
            metrics={"cpu": 95, "ram": 88},
            message="High CPU usage detected"
        ),
        CollectorResult(
            collector_name="api",
            target_name="main-api",
            status=HealthStatus.YELLOW,
            metrics={"response_time_ms": 2500},
            message="Slow response time"
        )
    ]


class TestAnalysisAgent:
    """Test suite for AnalysisAgent."""

    @pytest.mark.asyncio
    async def test_analyze_with_no_issues(self, mock_bedrock_client, mock_budget_tracker):
        """Test analysis when no issues are present."""
        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)

        result = await agent.analyze([])

        assert result['root_cause'] == "No issues detected"
        assert result['severity'] == "none"
        assert result['affected_systems'] == []
        assert result['recommendations'] == []
        assert result['token_usage']['total_tokens'] == 0

        # Should not call LLM
        mock_bedrock_client.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_with_budget_exceeded(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis when budget is exceeded."""
        mock_budget_tracker.can_make_request.return_value = False

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        assert "Budget exceeded" in result['root_cause']
        assert result['severity'] == "unknown"
        assert len(result['affected_systems']) == 2
        assert len(result['recommendations']) > 0
        assert "budget" in result['recommendations'][0]['action'].lower()

        # Should not call LLM
        mock_bedrock_client.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_with_valid_json_response(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis with valid JSON response from Claude."""
        # Mock LLM response
        llm_response = json.dumps({
            "root_cause": "High server load due to increased traffic",
            "severity": "high",
            "affected_systems": ["prod-server-1", "main-api"],
            "recommendations": [
                {
                    "priority": "immediate",
                    "action": "Scale up EC2 instances",
                    "rationale": "Reduce CPU load and improve response times"
                }
            ]
        })

        mock_bedrock_client.ainvoke.return_value = (
            llm_response,
            {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}
        )

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        assert result['root_cause'] == "High server load due to increased traffic"
        assert result['severity'] == "high"
        assert len(result['affected_systems']) == 2
        assert len(result['recommendations']) == 1
        assert result['recommendations'][0]['priority'] == "immediate"
        assert result['token_usage']['total_tokens'] == 1500

        # Should call LLM and record usage
        mock_bedrock_client.ainvoke.assert_called_once()
        mock_budget_tracker.record_usage.assert_called_once_with(1000, 500)

    @pytest.mark.asyncio
    async def test_analyze_with_markdown_json_response(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis with JSON wrapped in markdown code block."""
        # Mock LLM response with markdown
        llm_response = """Here's my analysis:

```json
{
  "root_cause": "Database connection pool exhausted",
  "severity": "critical",
  "affected_systems": ["prod-server-1"],
  "recommendations": [
    {
      "priority": "immediate",
      "action": "Increase database connection pool size",
      "rationale": "Prevent connection timeouts"
    }
  ]
}
```

This should resolve the issue."""

        mock_bedrock_client.ainvoke.return_value = (
            llm_response,
            {"input_tokens": 800, "output_tokens": 400, "total_tokens": 1200}
        )

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        assert result['root_cause'] == "Database connection pool exhausted"
        assert result['severity'] == "critical"
        assert len(result['recommendations']) == 1

    @pytest.mark.asyncio
    async def test_analyze_with_malformed_json(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis with malformed JSON response."""
        # Mock LLM response with invalid JSON
        llm_response = "This is not valid JSON at all"

        mock_bedrock_client.ainvoke.return_value = (
            llm_response,
            {"input_tokens": 500, "output_tokens": 200, "total_tokens": 700}
        )

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        # Should return fallback analysis
        assert "Unable to parse" in result['root_cause']
        assert result['severity'] == "unknown"
        assert len(result['recommendations']) > 0
        assert "parse_error" in result

    @pytest.mark.asyncio
    async def test_analyze_with_incomplete_json(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis with incomplete JSON (missing fields)."""
        # Mock LLM response with missing fields
        llm_response = json.dumps({
            "root_cause": "Network congestion"
            # Missing other required fields
        })

        mock_bedrock_client.ainvoke.return_value = (
            llm_response,
            {"input_tokens": 600, "output_tokens": 300, "total_tokens": 900}
        )

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        # Should fill in missing fields with defaults
        assert result['root_cause'] == "Network congestion"
        assert 'severity' in result
        assert 'affected_systems' in result
        assert 'recommendations' in result

    @pytest.mark.asyncio
    async def test_analyze_with_llm_exception(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test analysis when LLM call raises exception."""
        # Mock LLM exception
        mock_bedrock_client.ainvoke.side_effect = Exception("Bedrock service error")

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(sample_issues)

        # Should return error analysis
        assert "Analysis error" in result['root_cause']
        assert result['severity'] == "unknown"
        assert "error" in result
        assert len(result['recommendations']) > 0
        assert "Manual investigation" in result['recommendations'][0]['action']

    @pytest.mark.asyncio
    async def test_build_analysis_prompt(self, mock_bedrock_client, mock_budget_tracker, sample_issues):
        """Test prompt building from issues."""
        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)

        prompt = agent._build_analysis_prompt(sample_issues)

        # Verify prompt contains issue details
        assert "prod-server-1" in prompt
        assert "main-api" in prompt
        assert "cpu=95" in prompt or "cpu" in prompt.lower()
        assert "High CPU usage" in prompt
        assert "Slow response time" in prompt

        # Verify prompt has structured format
        assert "## EC2" in prompt.upper() or "ec2" in prompt.lower()
        assert "## API" in prompt.upper() or "api" in prompt.lower()
        assert "JSON" in prompt or "json" in prompt

    @pytest.mark.asyncio
    async def test_build_analysis_prompt_with_errors(self, mock_bedrock_client, mock_budget_tracker):
        """Test prompt building with issues that have errors."""
        issues = [
            CollectorResult(
                collector_name="database",
                target_name="prod-db",
                status=HealthStatus.RED,
                metrics={},
                message="Connection failed",
                error="Connection timeout after 10s"
            )
        ]

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        prompt = agent._build_analysis_prompt(issues)

        # Verify error is included
        assert "Connection timeout" in prompt
        assert "prod-db" in prompt

    @pytest.mark.asyncio
    async def test_get_system_prompt(self, mock_bedrock_client, mock_budget_tracker):
        """Test system prompt content."""
        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)

        system_prompt = agent._get_system_prompt()

        # Verify key elements
        assert "SRE" in system_prompt or "Site Reliability Engineer" in system_prompt
        assert "root cause" in system_prompt.lower()
        assert "practical" in system_prompt.lower() or "actionable" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_parse_analysis_response_with_extra_fields(self, mock_bedrock_client, mock_budget_tracker):
        """Test parsing response with extra fields."""
        response = json.dumps({
            "root_cause": "Memory leak",
            "severity": "high",
            "affected_systems": ["app-server"],
            "recommendations": [],
            "extra_field": "should be preserved",
            "another_field": 123
        })

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = agent._parse_analysis_response(response)

        # Should preserve extra fields
        assert result['root_cause'] == "Memory leak"
        assert result['extra_field'] == "should be preserved"

    @pytest.mark.asyncio
    async def test_parse_analysis_response_with_incomplete_recommendations(self, mock_bedrock_client, mock_budget_tracker):
        """Test parsing response with incomplete recommendation objects."""
        response = json.dumps({
            "root_cause": "Service overload",
            "severity": "medium",
            "affected_systems": ["web-server"],
            "recommendations": [
                {"action": "Restart service"},  # Missing priority and rationale
                {}  # Empty recommendation
            ]
        })

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = agent._parse_analysis_response(response)

        # Should fill in missing fields
        assert len(result['recommendations']) == 2
        assert 'priority' in result['recommendations'][0]
        assert 'rationale' in result['recommendations'][0]
        assert result['recommendations'][0]['action'] == "Restart service"
        assert result['recommendations'][1]['action'] == "No action specified"

    @pytest.mark.asyncio
    async def test_analyze_multiple_issues_same_collector(self, mock_bedrock_client, mock_budget_tracker):
        """Test analysis with multiple issues from same collector."""
        issues = [
            CollectorResult(
                collector_name="ec2",
                target_name="server-1",
                status=HealthStatus.RED,
                metrics={"cpu": 95},
                message="High CPU"
            ),
            CollectorResult(
                collector_name="ec2",
                target_name="server-2",
                status=HealthStatus.RED,
                metrics={"cpu": 92},
                message="High CPU"
            ),
            CollectorResult(
                collector_name="ec2",
                target_name="server-3",
                status=HealthStatus.YELLOW,
                metrics={"cpu": 75},
                message="Elevated CPU"
            )
        ]

        llm_response = json.dumps({
            "root_cause": "Traffic spike affecting all EC2 instances",
            "severity": "critical",
            "affected_systems": ["server-1", "server-2", "server-3"],
            "recommendations": [
                {
                    "priority": "immediate",
                    "action": "Enable auto-scaling",
                    "rationale": "Handle traffic spikes automatically"
                }
            ]
        })

        mock_bedrock_client.ainvoke.return_value = (
            llm_response,
            {"input_tokens": 1200, "output_tokens": 600, "total_tokens": 1800}
        )

        agent = AnalysisAgent(mock_bedrock_client, mock_budget_tracker)
        result = await agent.analyze(issues)

        assert "Traffic spike" in result['root_cause']
        assert len(result['affected_systems']) == 3
        assert result['severity'] == "critical"
