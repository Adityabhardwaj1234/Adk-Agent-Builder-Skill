"""Architecture Planner: Selects optimal ADK pattern and explains trade-offs."""

from __future__ import annotations

from typing import List, Tuple

from adk_agent_builder.models.architecture import (
    AgentNodeSpec,
    ArchitecturePattern,
    ArchitecturePlan,
    TradeoffScorecard,
)
from adk_agent_builder.models.requirements import RequirementsSpecification


SCORECARD_TEMPLATES = {
    ArchitecturePattern.SINGLE_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.SINGLE_AGENT,
        complexity_score=1,
        reliability_score=5,
        latency_profile="lowest (1 LLM turn)",
        token_cost_profile="lowest",
        testability_score=5,
        maintainability_score=5,
        fit_rationale="Best for focused conversational or structured-output tasks with zero or minimal tools.",
    ),
    ArchitecturePattern.TOOL_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.TOOL_AGENT,
        complexity_score=2,
        reliability_score=5,
        latency_profile="low (1-2 LLM turns + tool execution)",
        token_cost_profile="low",
        testability_score=5,
        maintainability_score=5,
        fit_rationale="Simplest reliable pattern when a single LlmAgent can invoke cohesive FunctionTools.",
    ),
    ArchitecturePattern.SEQUENTIAL_WORKFLOW: TradeoffScorecard(
        pattern=ArchitecturePattern.SEQUENTIAL_WORKFLOW,
        complexity_score=2,
        reliability_score=5,
        latency_profile="medium (sum of sequential steps)",
        token_cost_profile="medium",
        testability_score=5,
        maintainability_score=4,
        fit_rationale="Ideal for deterministic multi-step pipelines (e.g., intake -> analysis -> synthesis) where order is strict.",
    ),
    ArchitecturePattern.PARALLEL_WORKFLOW: TradeoffScorecard(
        pattern=ArchitecturePattern.PARALLEL_WORKFLOW,
        complexity_score=3,
        reliability_score=4,
        latency_profile="low-medium (max of concurrent branches)",
        token_cost_profile="medium-high",
        testability_score=4,
        maintainability_score=4,
        fit_rationale="Best when multiple independent research or data-gathering sub-agents can execute concurrently.",
    ),
    ArchitecturePattern.LOOP_WORKFLOW: TradeoffScorecard(
        pattern=ArchitecturePattern.LOOP_WORKFLOW,
        complexity_score=3,
        reliability_score=4,
        latency_profile="medium-high (bounded by max_iterations)",
        token_cost_profile="medium-high",
        testability_score=4,
        maintainability_score=4,
        fit_rationale="Suited for generator-critic or iterative refinement loops with explicit termination bounds.",
    ),
    ArchitecturePattern.SPECIALIST_MULTI_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.SPECIALIST_MULTI_AGENT,
        complexity_score=4,
        reliability_score=4,
        latency_profile="medium-high (coordinator + specialist delegation)",
        token_cost_profile="high",
        testability_score=3,
        maintainability_score=4,
        fit_rationale="Warranted when distinct domains require isolated instructions, separate toolsets, and dynamic routing.",
    ),
    ArchitecturePattern.GRAPH_WORKFLOW: TradeoffScorecard(
        pattern=ArchitecturePattern.GRAPH_WORKFLOW,
        complexity_score=4,
        reliability_score=5,
        latency_profile="medium",
        token_cost_profile="medium",
        testability_score=4,
        maintainability_score=4,
        fit_rationale="ADK 2.0+ Workflow combining deterministic FunctionNodes, Event(route=...) branching, JoinNode fan-in, and single-turn LlmAgent nodes.",
    ),
    ArchitecturePattern.MCP_ENABLED_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.MCP_ENABLED_AGENT,
        complexity_score=3,
        reliability_score=4,
        latency_profile="low-medium",
        token_cost_profile="low-medium",
        testability_score=4,
        maintainability_score=4,
        fit_rationale="Connects an LlmAgent to external MCP tool servers via MCPToolset (supports MCP SDK 1.x and 2.x).",
    ),
    ArchitecturePattern.RAG_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.RAG_AGENT,
        complexity_score=3,
        reliability_score=4,
        latency_profile="low-medium",
        token_cost_profile="medium",
        testability_score=4,
        maintainability_score=4,
        fit_rationale="Grounded retrieval agent combining knowledge-base search tools with citation and hallucination guardrails.",
    ),
    ArchitecturePattern.REMOTE_A2A_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.REMOTE_A2A_AGENT,
        complexity_score=4,
        reliability_score=4,
        latency_profile="medium-high (network RPC overhead)",
        token_cost_profile="medium",
        testability_score=3,
        maintainability_score=4,
        fit_rationale="Cross-boundary interoperability using Agent2Agent (A2A) protocol (`to_a2a` server and `RemoteA2aAgent` client).",
    ),
    ArchitecturePattern.LIVE_VOICE_AGENT: TradeoffScorecard(
        pattern=ArchitecturePattern.LIVE_VOICE_AGENT,
        complexity_score=4,
        reliability_score=4,
        latency_profile="realtime bidirectional streaming",
        token_cost_profile="high",
        testability_score=3,
        maintainability_score=3,
        fit_rationale="Bidirectional audio/video streaming agent using ADK `google.adk.live` with session resumption and interruption handling.",
    ),
}


class ArchitecturePlanner:
    """Recommends the simplest ADK architecture that satisfies functional and non-functional requirements."""

    @staticmethod
    def plan(spec: RequirementsSpecification) -> ArchitecturePlan:
        """Analyze requirements and produce an evidence-backed ArchitecturePlan."""
        selected_pattern, template_name, rationale = ArchitecturePlanner._select_pattern(spec)
        selected_scorecard = SCORECARD_TEMPLATES[selected_pattern]

        rejected: List[TradeoffScorecard] = []
        for pat, card in SCORECARD_TEMPLATES.items():
            if pat != selected_pattern:
                rejected.append(card)

        root_node, sub_nodes = ArchitecturePlanner._build_agent_topology(spec, selected_pattern)

        security_controls = [
            "secret_redaction_logging",
            "before_model_prompt_injection_guardrail",
            "before_tool_argument_validation",
            "after_tool_output_sanitization",
            "max_llm_calls_budget",
        ]
        if spec.security.require_human_confirmation_for_mutations:
            security_controls.append("require_confirmation_on_mutating_tools")

        return ArchitecturePlan(
            project_name=spec.project_name,
            selected_pattern=selected_pattern,
            selected_template=template_name,
            selection_rationale=rationale,
            rejected_alternatives=rejected[:4],
            selected_scorecard=selected_scorecard,
            root_agent=root_node,
            sub_agents=sub_nodes,
            required_integrations=list(spec.expected_tools),
            termination_conditions={
                "max_iterations": 5 if selected_pattern == ArchitecturePattern.LOOP_WORKFLOW else 3,
                "max_llm_calls": spec.latency_and_cost.daily_request_limit or 20,
                "timeout_seconds": int(spec.latency_and_cost.max_latency_seconds * 3),
                "abort_signal_enabled": True,
            },
            session_strategy={
                "session_backend": spec.persistence.session_backend,
                "memory_backend": spec.persistence.memory_backend,
                "artifact_backend": spec.persistence.artifact_backend,
                "context_compaction": spec.persistence.enable_context_compaction,
                "context_caching": spec.persistence.enable_context_caching,
            },
            security_controls=security_controls,
            observability_plan={
                "backends": spec.observability_backends,
                "redact_prompts": spec.security.pii_redaction_required,
                "efficiency_metrics_enabled": True,
            },
            deployment_target=spec.deployment_target,
        )

    @staticmethod
    def _select_pattern(spec: RequirementsSpecification) -> Tuple[ArchitecturePattern, str, str]:
        text = (
            spec.business_objective
            + " "
            + " ".join(r.description for r in spec.functional_requirements)
        ).lower()
        tools = set(spec.expected_tools)

        if spec.requires_streaming_or_live or "audio" in spec.modalities or "video" in spec.modalities:
            return (
                ArchitecturePattern.LIVE_VOICE_AGENT,
                "live_voice_agent",
                "Requirement specifies real-time audio/video streaming modalities, requiring ADK's google.adk.live runner.",
            )
        if "a2a" in text or "remote agent" in text:
            return (
                ArchitecturePattern.REMOTE_A2A_AGENT,
                "a2a_remote_agent",
                "Requirement specifies remote cross-agent interoperability over the A2A protocol.",
            )
        if "mcp_toolset" in tools or "mcp" in text:
            return (
                ArchitecturePattern.MCP_ENABLED_AGENT,
                "mcp_agent",
                "Requirement depends on Model Context Protocol (MCP) tool servers via MCPToolset.",
            )
        if "vertex_rag_retrieval" in tools or "rag" in text or "knowledge base" in text:
            return (
                ArchitecturePattern.RAG_AGENT,
                "rag_agent",
                "Requirement centers on grounded document/knowledge-base retrieval with citation validation.",
            )
        if "graph" in text or ("branch" in text and "deterministic" in text) or "joinnode" in text:
            return (
                ArchitecturePattern.GRAPH_WORKFLOW,
                "graph_workflow",
                "Requirement combines deterministic node routing (`Event(route=...)`), `JoinNode` fan-in, and single-turn LLM nodes in an ADK 2.0 graph workflow.",
            )
        if "parallel" in text or "concurrent" in text:
            return (
                ArchitecturePattern.PARALLEL_WORKFLOW,
                "parallel_workflow",
                "Requirement involves independent sub-tasks that benefit from concurrent execution via ParallelAgent.",
            )
        if "loop" in text or "iterative" in text or "critic" in text:
            return (
                ArchitecturePattern.LOOP_WORKFLOW,
                "loop_workflow",
                "Requirement needs iterative generation and critique bounded by LoopAgent(max_iterations).",
            )
        if "sequential" in text or "pipeline" in text or "step-by-step" in text:
            return (
                ArchitecturePattern.SEQUENTIAL_WORKFLOW,
                "sequential_workflow",
                "Requirement describes a fixed multi-stage pipeline best served by a deterministic SequentialAgent.",
            )
        if "multi-agent" in text or "specialist" in text or "coordinator" in text or len(tools) >= 4:
            return (
                ArchitecturePattern.SPECIALIST_MULTI_AGENT,
                "specialist_multi_agent",
                "Multiple distinct domains/tools justify a coordinator LlmAgent delegating to specialist sub-agents.",
            )
        if tools:
            return (
                ArchitecturePattern.TOOL_AGENT,
                "tool_agent",
                "A single LlmAgent equipped with focused FunctionTools is the simplest, lowest-latency architecture that meets all requirements.",
            )
        return (
            ArchitecturePattern.SINGLE_AGENT,
            "simple_agent",
            "No external tools or multi-agent handoffs are needed; a single LlmAgent minimizes latency, cost, and complexity.",
        )

    @staticmethod
    def _build_agent_topology(
        spec: RequirementsSpecification,
        pattern: ArchitecturePattern,
    ) -> Tuple[AgentNodeSpec, List[AgentNodeSpec]]:
        model = spec.preferred_model
        tools = list(spec.expected_tools) or ["custom_function_tool"]

        if pattern in (
            ArchitecturePattern.SINGLE_AGENT,
            ArchitecturePattern.TOOL_AGENT,
            ArchitecturePattern.MCP_ENABLED_AGENT,
            ArchitecturePattern.RAG_AGENT,
            ArchitecturePattern.LIVE_VOICE_AGENT,
            ArchitecturePattern.REMOTE_A2A_AGENT,
        ):
            root = AgentNodeSpec(
                name=f"{spec.project_name}_root",
                agent_type="LlmAgent",
                model=model,
                mode="chat",
                include_contents="default",
                instruction=f"You are the primary agent for: {spec.business_objective}",
                description=spec.business_objective[:120],
                tools=tools if pattern != ArchitecturePattern.SINGLE_AGENT else [],
                callbacks=["before_model_guardrail", "before_tool_validator", "after_tool_sanitizer"],
            )
            return root, []

        if pattern in (ArchitecturePattern.SEQUENTIAL_WORKFLOW, ArchitecturePattern.GRAPH_WORKFLOW):
            sub1 = AgentNodeSpec(
                name="intake_analyzer_agent",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Analyze the user request and extract structured parameters using available tools.",
                tools=tools,
                output_key="analysis_result",
            )
            sub2 = AgentNodeSpec(
                name="response_synthesizer_agent",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Synthesize a validated final response based on state['analysis_result'].",
                tools=[],
                output_key="final_output",
            )
            root = AgentNodeSpec(
                name=f"{spec.project_name}_{'graph' if pattern == ArchitecturePattern.GRAPH_WORKFLOW else 'sequential'}",
                agent_type="Workflow" if pattern == ArchitecturePattern.GRAPH_WORKFLOW else "SequentialAgent",
                model=model,
                description="Deterministic pipeline orchestrating intake analysis and synthesis.",
                sub_agents=[sub1.name, sub2.name],
            )
            return root, [sub1, sub2]

        if pattern == ArchitecturePattern.PARALLEL_WORKFLOW:
            sub1 = AgentNodeSpec(
                name="primary_research_branch",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Gather primary domain facts using tools.",
                tools=tools,
                output_key="primary_data",
            )
            sub2 = AgentNodeSpec(
                name="risk_verification_branch",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Concurrently verify policy compliance and edge cases.",
                tools=[],
                output_key="verification_data",
            )
            root = AgentNodeSpec(
                name=f"{spec.project_name}_parallel",
                agent_type="ParallelAgent",
                model=model,
                description="Concurrent fan-out execution across independent specialist branches.",
                sub_agents=[sub1.name, sub2.name],
            )
            return root, [sub1, sub2]

        if pattern == ArchitecturePattern.LOOP_WORKFLOW:
            sub1 = AgentNodeSpec(
                name="draft_generator_agent",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Generate or refine the solution draft based on critic feedback.",
                tools=tools,
                output_key="current_draft",
            )
            sub2 = AgentNodeSpec(
                name="quality_critic_agent",
                agent_type="LlmAgent",
                model=model,
                mode="single_turn",
                include_contents="default",
                instruction="Evaluate state['current_draft'] against acceptance criteria and signal completion.",
                tools=[],
                output_key="critic_verdict",
            )
            root = AgentNodeSpec(
                name=f"{spec.project_name}_loop",
                agent_type="LoopAgent",
                model=model,
                description="Bounded iterative refinement workflow.",
                sub_agents=[sub1.name, sub2.name],
                max_iterations=3,
            )
            return root, [sub1, sub2]

        # Specialist multi-agent default
        sub1 = AgentNodeSpec(
            name="domain_execution_specialist",
            agent_type="LlmAgent",
            model=model,
            mode="single_turn",
            include_contents="default",
            instruction="Execute domain-specific tool operations accurately.",
            tools=tools,
        )
        sub2 = AgentNodeSpec(
            name="policy_audit_specialist",
            agent_type="LlmAgent",
            model=model,
            mode="single_turn",
            include_contents="default",
            instruction="Verify policy compliance, formatting, and safety constraints.",
            tools=[],
        )
        root = AgentNodeSpec(
            name=f"{spec.project_name}_coordinator",
            agent_type="LlmAgent",
            model=model,
            mode="chat",
            include_contents="default",
            instruction="Coordinate user requests and delegate to specialist sub-agents.",
            sub_agents=[sub1.name, sub2.name],
            callbacks=["before_model_guardrail", "before_tool_validator", "after_tool_sanitizer"],
        )
        return root, [sub1, sub2]
