"""Structured schemas for customer requirements intake, normalization, and clarification."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class RequirementPriority(str, Enum):
    HARD = "hard"
    PREFERENCE = "preference"
    ASSUMPTION = "assumption"
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out_of_scope"


class RequirementItem(CompatModel):
    id: str
    category: str
    description: str
    priority: RequirementPriority = RequirementPriority.HARD
    rationale: Optional[str] = None


class ClarificationQuestion(CompatModel):
    id: str
    topic: str
    question: str
    impact: str
    proposed_default: str
    blocking: bool = False


class RequirementContradiction(CompatModel):
    code: str
    severity: str = "error"
    description: str
    conflicting_fields: List[str] = Field(default_factory=list)
    remediation: str


class LatencyCostExpectation(CompatModel):
    max_latency_seconds: float = 10.0
    max_cost_usd_per_1k_turns: float = 5.0
    quality_tier: str = "balanced"  # fast | balanced | high_reasoning
    daily_request_limit: Optional[int] = None


class SecurityPrivacySpec(CompatModel):
    pii_redaction_required: bool = True
    allow_external_network: bool = False
    allow_code_execution: bool = False
    require_human_confirmation_for_mutations: bool = True
    custom_service_account: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)


class PersistenceMemorySpec(CompatModel):
    session_backend: str = "in_memory"  # in_memory | sqlite | database | vertex_agent_engine
    memory_backend: str = "none"  # none | in_memory | sqlite | vertex_memory_bank
    artifact_backend: str = "in_memory"  # in_memory | gcs
    enable_context_compaction: bool = True
    enable_context_caching: bool = False
    multi_turn_session: bool = True


class AcceptanceCriterion(CompatModel):
    id: str
    description: str
    metric_name: str = "tool_trajectory_avg_score"
    threshold: float = 1.0


class RequirementsSpecification(CompatModel):
    """Complete customer requirements specification with explicit assumptions and diagnostics."""

    project_name: str = "adk_custom_agent"
    business_objective: str
    user_types: List[str] = Field(default_factory=lambda: ["end_user"])
    user_stories: List[str] = Field(default_factory=list)
    functional_requirements: List[RequirementItem] = Field(default_factory=list)
    non_functional_requirements: List[RequirementItem] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    external_systems: List[str] = Field(default_factory=list)
    preferred_provider: str = "gemini"
    preferred_model: str = "gemini-2.5-flash"
    fallback_model: Optional[str] = None
    requires_structured_output: bool = False
    output_schema_name: Optional[str] = None
    requires_streaming_or_live: bool = False
    modalities: List[str] = Field(default_factory=lambda: ["text"])
    persistence: PersistenceMemorySpec = Field(default_factory=PersistenceMemorySpec)
    latency_and_cost: LatencyCostExpectation = Field(default_factory=LatencyCostExpectation)
    security: SecurityPrivacySpec = Field(default_factory=SecurityPrivacySpec)
    deployment_target: str = "local"  # local | docker | cloud_run | agent_runtime | gke
    observability_backends: List[str] = Field(default_factory=lambda: ["opentelemetry"])
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)
    contradictions: List[RequirementContradiction] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
