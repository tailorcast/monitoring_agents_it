"""LangGraph state definition for monitoring workflow."""

from typing import TypedDict, List, Annotated, Optional
import operator

from ..utils.metrics import CollectorResult


class MonitoringState(TypedDict, total=False):
    """
    Shared state across LangGraph workflow.

    This state is passed between nodes and accumulates data
    as the workflow progresses through collection, analysis,
    and reporting phases.
    """

    # Collection phase outputs (per collector)
    ec2_results: List[CollectorResult]
    vps_results: List[CollectorResult]
    docker_results: List[CollectorResult]
    api_results: List[CollectorResult]
    database_results: List[CollectorResult]
    llm_results: List[CollectorResult]
    s3_results: List[CollectorResult]

    # Aggregated results
    all_results: List[CollectorResult]  # All check results
    issues: List[CollectorResult]  # Only RED/YELLOW status items

    # AI analysis outputs
    root_cause_analysis: dict  # Structured analysis from Claude
    recommendations: List[dict]  # Actionable recommendations

    # Final report
    telegram_message: str  # Formatted Telegram message

    # Metadata
    execution_start: float  # Timestamp when workflow started
    token_usage: Annotated[int, operator.add]  # Cumulative LLM tokens (auto-sum across nodes)
    errors: Annotated[List[str], operator.add]  # Cumulative errors (auto-append across nodes)
