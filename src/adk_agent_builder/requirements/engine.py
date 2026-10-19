"""Requirements intake, normalization, contradiction detection, and clarification engine."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from adk_agent_builder.errors import RequirementsValidationError
from adk_agent_builder.models.providers import ModelProviderConfig, ProviderType
from adk_agent_builder.models.requirements import (
    AcceptanceCriterion,
    ClarificationQuestion,
    RequirementContradiction,
    RequirementItem,
    RequirementPriority,
    RequirementsSpecification,
)


class RequirementsEngine:
    """Ingests customer requirements, normalizes structure, detects conflicts, and proposes defaults."""

    @staticmethod
    def from_natural_language(
        prompt: str,
        *,
        project_name: Optional[str] = None,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> RequirementsSpecification:
        """Parse a natural-language requirement description into a structured specification."""
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            raise RequirementsValidationError(
                "Requirement description cannot be empty.",
                stage="01_requirement_intake",
                remediation="Provide a non-empty natural-language description or a YAML/JSON spec file.",
            )

        lower = clean_prompt.lower()
        derived_name = project_name or RequirementsEngine._derive_project_name(clean_prompt)

        tools: List[str] = []
        if any(w in lower for w in ("search", "grounding", "web", "research")):
            tools.append("google_search")
        if any(w in lower for w in ("bigquery", "warehouse", "sql", "analytics")):
            tools.append("bigquery_toolset")
        if any(w in lower for w in ("mongodb", "vector", "hybrid search")):
            tools.append("mongodb_toolset")
        if any(w in lower for w in ("mcp", "model context protocol")):
            tools.append("mcp_toolset")
        if any(w in lower for w in ("openapi", "rest api", "swagger")):
            tools.append("openapi_toolset")
        if any(w in lower for w in ("rag", "retrieval", "knowledge base", "document")):
            tools.append("vertex_rag_retrieval")
        if any(w in lower for w in ("code execution", "sandbox", "calculate", "python")):
            tools.append("code_execution")
        if any(w in lower for w in ("ticket", "order", "refund", "lookup", "custom", "weather", "calculator")):
            tools.append("custom_function_tool")
        if not tools:
            tools.append("custom_function_tool")

        modalities = ["text"]
        requires_live = False
        if any(w in lower for w in ("voice", "audio", "speech", "live", "realtime")):
            modalities.append("audio")
            requires_live = True
        if any(w in lower for w in ("video", "camera", "vision")):
            modalities.append("video")

        provider = provider_override or "gemini"
        for cand in ("anthropic", "openai", "ollama", "vllm", "litellm", "gemma", "vertex_ai"):
            if cand in lower and not provider_override:
                provider = cand
                break

        model = model_override or ("gemini-2.5-flash" if provider in ("gemini", "vertex_ai") else "gpt-4o-mini")

        deployment = "local"
        if "cloud run" in lower:
            deployment = "cloud_run"
        elif any(w in lower for w in ("agent engine", "agent runtime", "vertex")):
            deployment = "agent_runtime"
        elif "gke" in lower or "kubernetes" in lower:
            deployment = "gke"
        elif "docker" in lower or "container" in lower:
            deployment = "docker"

        func_reqs = [
            RequirementItem(
                id="FR-001",
                category="core_behavior",
                description=clean_prompt,
                priority=RequirementPriority.HARD,
            )
        ]
        if "parallel" in lower:
            func_reqs.append(
                RequirementItem(
                    id="FR-002",
                    category="orchestration",
                    description="Execute independent sub-tasks concurrently via ParallelAgent.",
                    priority=RequirementPriority.HARD,
                )
            )
        if "sequential" in lower or "pipeline" in lower or "step-by-step" in lower:
            func_reqs.append(
                RequirementItem(
                    id="FR-003",
                    category="orchestration",
                    description="Execute multi-stage pipeline deterministically via SequentialAgent.",
                    priority=RequirementPriority.HARD,
                )
            )
        if "loop" in lower or "iterative" in lower or "refine" in lower:
            func_reqs.append(
                RequirementItem(
                    id="FR-004",
                    category="orchestration",
                    description="Iteratively refine output with explicit max_iterations via LoopAgent.",
                    priority=RequirementPriority.HARD,
                )
            )

        spec = RequirementsSpecification(
            project_name=derived_name,
            business_objective=clean_prompt,
            functional_requirements=func_reqs,
            expected_tools=tools,
            preferred_provider=provider,
            preferred_model=model,
            requires_streaming_or_live=requires_live,
            modalities=modalities,
            deployment_target=deployment,
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC-001",
                    description="Tool trajectory matches expected ground-truth calls.",
                    metric_name="tool_trajectory_avg_score",
                    threshold=1.0,
                ),
                AcceptanceCriterion(
                    id="AC-002",
                    description="Final response achieves semantic/lexical similarity threshold.",
                    metric_name="response_match_score",
                    threshold=0.8,
                ),
            ],
        )
        return RequirementsEngine.normalize_and_validate(spec)

    @staticmethod
    def load_file(path: Union[str, Path]) -> RequirementsSpecification:
        """Load a requirements specification from a YAML or JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise RequirementsValidationError(
                f"Requirements specification file not found: {file_path}",
                stage="01_requirement_intake",
                file_path=str(file_path),
                remediation="Verify the file path or run `adk-agent-builder requirements --from-text` to generate one.",
            )
        content = file_path.read_text(encoding="utf-8")
        try:
            if file_path.suffix.lower() == ".json":
                data = json.loads(content)
            else:
                data = yaml.safe_load(content)
        except Exception as exc:
            raise RequirementsValidationError(
                f"Failed to parse requirements file {file_path}: {exc}",
                stage="01_requirement_intake",
                file_path=str(file_path),
                remediation="Ensure valid YAML or JSON syntax.",
            ) from exc

        if not isinstance(data, dict):
            raise RequirementsValidationError(
                f"Requirements specification must be a mapping/object in {file_path}",
                stage="01_requirement_intake",
                file_path=str(file_path),
            )
        spec = RequirementsSpecification.from_dict(data)
        return RequirementsEngine.normalize_and_validate(spec)

    @staticmethod
    def normalize_and_validate(spec: RequirementsSpecification) -> RequirementsSpecification:
        """Normalize fields, populate explicit assumptions, and detect contradictions."""
        spec.project_name = re.sub(r"[^a-zA-Z0-9_]", "_", spec.project_name.strip()).lower()
        if not spec.project_name or spec.project_name[0].isdigit():
            spec.project_name = f"agent_{spec.project_name or 'app'}"

        contradictions: List[RequirementContradiction] = []
        clarifications: List[ClarificationQuestion] = []
        assumptions: List[str] = list(spec.assumptions)

        # 1. Provider compatibility checks
        try:
            provider_enum = ProviderType(spec.preferred_provider.lower())
        except ValueError:
            contradictions.append(
                RequirementContradiction(
                    code="REQ_UNSUPPORTED_PROVIDER",
                    severity="error",
                    description=f"Provider '{spec.preferred_provider}' is not a verified ADK provider.",
                    conflicting_fields=["preferred_provider"],
                    remediation="Select one of: gemini, vertex_ai, gemma, anthropic, openai, litellm, ollama, vllm.",
                )
            )
            provider_enum = ProviderType.GEMINI

        provider_cfg = ModelProviderConfig(
            provider=provider_enum,
            model_name=spec.preferred_model,
            fallback_model_name=spec.fallback_model,
        )
        compat_issues = provider_cfg.validate_compatibility(
            requires_live=spec.requires_streaming_or_live or ("audio" in spec.modalities),
            requires_structured_output=spec.requires_structured_output,
            requires_caching=spec.persistence.enable_context_caching,
        )
        for issue in compat_issues:
            contradictions.append(
                RequirementContradiction(
                    code="REQ_PROVIDER_CAPABILITY_MISMATCH",
                    severity="error",
                    description=issue,
                    conflicting_fields=["preferred_provider", "modalities", "requires_structured_output"],
                    remediation="Switch to 'gemini' or 'vertex_ai' provider or disable the unsupported capability.",
                )
            )

        # 2. Network vs External Systems contradiction check
        external_tools = {"google_search", "bigquery_toolset", "mongodb_toolset", "openapi_toolset", "vertex_rag_retrieval"}
        requested_external = external_tools.intersection(set(spec.expected_tools))
        if requested_external and spec.security.allow_external_network is False and len(spec.external_systems) > 0:
            contradictions.append(
                RequirementContradiction(
                    code="REQ_NETWORK_ISOLATION_CONFLICT",
                    severity="warning",
                    description=(
                        f"External tools {sorted(requested_external)} and external systems {spec.external_systems} "
                        "are requested while security.allow_external_network is False."
                    ),
                    conflicting_fields=["expected_tools", "external_systems", "security.allow_external_network"],
                    remediation="Enable security.allow_external_network for live mode or use deterministic mocks in CI.",
                )
            )

        # 3. Latency vs Complex Reasoning / Multi-Agent check
        if spec.latency_and_cost.max_latency_seconds < 1.0 and spec.latency_and_cost.quality_tier == "high_reasoning":
            contradictions.append(
                RequirementContradiction(
                    code="REQ_LATENCY_REASONING_CONFLICT",
                    severity="error",
                    description=(
                        f"Sub-second latency target ({spec.latency_and_cost.max_latency_seconds}s) conflicts with "
                        "quality_tier='high_reasoning'."
                    ),
                    conflicting_fields=[
                        "latency_and_cost.max_latency_seconds",
                        "latency_and_cost.quality_tier",
                    ],
                    remediation="Increase max_latency_seconds to >=5.0s or select quality_tier='fast' with gemini-2.5-flash.",
                )
            )

        # 4. Populate sensible assumptions & focused clarifications
        if not spec.acceptance_criteria:
            spec.acceptance_criteria = [
                AcceptanceCriterion(
                    id="AC-DEFAULT-01",
                    description="Default ADK tool trajectory match threshold.",
                    metric_name="tool_trajectory_avg_score",
                    threshold=1.0,
                ),
                AcceptanceCriterion(
                    id="AC-DEFAULT-02",
                    description="Default ADK ROUGE-1 response similarity threshold.",
                    metric_name="response_match_score",
                    threshold=0.8,
                ),
            ]
            assumptions.append(
                "Applied default ADK evaluation thresholds (tool_trajectory_avg_score=1.0, response_match_score=0.8)."
            )

        if spec.deployment_target in ("cloud_run", "agent_runtime", "gke") and not spec.security.custom_service_account:
            assumptions.append(
                "Cloud deployment target selected without a custom service account; will generate dry-run plan and recommend a dedicated least-privilege service account."
            )
            clarifications.append(
                ClarificationQuestion(
                    id="CQ-001",
                    topic="deployment_identity",
                    question="Which dedicated IAM service account should be bound to the deployed agent?",
                    impact="Affects IAM permissions for Vertex AI, BigQuery, and Secret Manager in production.",
                    proposed_default="adk-agent-sa@<project-id>.iam.gserviceaccount.com (dry-run only until specified)",
                    blocking=False,
                )
            )

        if "mcp_toolset" in spec.expected_tools and not spec.external_systems:
            clarifications.append(
                ClarificationQuestion(
                    id="CQ-002",
                    topic="mcp_server_transport",
                    question="What MCP server transport (stdio command or SSE/StreamableHTTP URL) should MCPToolset connect to?",
                    impact="Determines MCP connection parameters and security allowlist.",
                    proposed_default="Local stdio mock server in CI; configurable via MCP_SERVER_URL in .env",
                    blocking=False,
                )
            )

        spec.assumptions = list(dict.fromkeys(assumptions))
        spec.contradictions = contradictions
        spec.clarification_questions = clarifications
        return spec

    @staticmethod
    def _derive_project_name(prompt: str) -> str:
        words = re.findall(r"[a-zA-Z0-9]+", prompt.lower())
        stop = {"build", "create", "an", "a", "the", "adk", "agent", "for", "that", "with", "to", "and"}
        meaningful = [w for w in words if w not in stop][:3]
        if not meaningful:
            return "adk_custom_agent"
        return "_".join(meaningful) + "_agent"
