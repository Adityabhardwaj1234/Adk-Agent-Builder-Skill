"""Pydantic schemas aligned with official Google ADK Evaluation (EvalSet, EvalCase, EvalConfig)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class ContentPart(CompatModel):
    text: str


class MessageContent(CompatModel):
    role: Optional[str] = "user"
    parts: List[ContentPart] = Field(default_factory=list)


class ToolUseRecord(CompatModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None


class IntermediateData(CompatModel):
    tool_uses: List[ToolUseRecord] = Field(default_factory=list)
    intermediate_responses: List[Any] = Field(default_factory=list)


class InvocationTurn(CompatModel):
    invocation_id: str
    user_content: MessageContent
    final_response: MessageContent
    intermediate_data: IntermediateData = Field(default_factory=IntermediateData)


class SessionInputSpec(CompatModel):
    app_name: str
    user_id: str = "test_user"
    state: Dict[str, Any] = Field(default_factory=dict)


class EvalCase(CompatModel):
    eval_id: str
    conversation: List[InvocationTurn] = Field(default_factory=list)
    session_input: SessionInputSpec


class EvalSet(CompatModel):
    """Official ADK EvalSet schema used in *.test.json and *.evalset.json files."""

    eval_set_id: str
    name: str = ""
    description: str = ""
    eval_cases: List[EvalCase] = Field(default_factory=list)


class EvalConfig(CompatModel):
    """Official ADK test_config.json schema with supported criteria."""

    criteria: Dict[str, float] = Field(
        default_factory=lambda: {
            "tool_trajectory_avg_score": 1.0,
            "response_match_score": 0.8,
        }
    )
    ignore_args: bool = False
    custom_metrics: List[str] = Field(default_factory=list)


class CaseEvalResult(CompatModel):
    eval_id: str
    status: str  # passed | failed | skipped
    scores: Dict[str, float] = Field(default_factory=dict)
    efficiency: Dict[str, float] = Field(
        default_factory=lambda: {
            "tool_call_count_v1": 0.0,
            "inference_call_count_v1": 0.0,
            "token_usage_v1": 0.0,
            "invocation_duration_v1": 0.0,
        }
    )
    failure_reasons: List[str] = Field(default_factory=list)


class EvalReport(CompatModel):
    eval_set_id: str
    agent_version: str = "1.0.0"
    execution_mode: str = "deterministic_mock"  # deterministic_mock | live_provider
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    skipped_cases: int = 0
    overall_passed: bool = False
    aggregate_scores: Dict[str, float] = Field(default_factory=dict)
    aggregate_efficiency: Dict[str, float] = Field(default_factory=dict)
    case_results: List[CaseEvalResult] = Field(default_factory=list)
