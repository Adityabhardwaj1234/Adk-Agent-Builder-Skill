"""Catalog of verified Google ADK project templates."""

from __future__ import annotations

from typing import Dict, List
from pydantic import Field

from adk_agent_builder.models.architecture import ArchitecturePattern
from adk_agent_builder.models.base import CompatModel


class TemplateMetadata(CompatModel):
    id: str
    name: str
    pattern: ArchitecturePattern
    description: str
    adk_classes: List[str] = Field(default_factory=list)
    included_files: List[str] = Field(default_factory=list)
    requires_optional_extras: List[str] = Field(default_factory=list)


TEMPLATE_CATALOG: Dict[str, TemplateMetadata] = {
    "simple_agent": TemplateMetadata(
        id="simple_agent",
        name="Simple Conversational LlmAgent",
        pattern=ArchitecturePattern.SINGLE_AGENT,
        description="Minimal single-agent ADK project with instructions, session service, and callback guardrails.",
        adk_classes=["LlmAgent", "Runner", "InMemorySessionService"],
        included_files=["app/agent.py", "app/callbacks.py", "tests/unit/test_agent_unit.py"],
    ),
    "tool_agent": TemplateMetadata(
        id="tool_agent",
        name="Tool-Using ReAct LlmAgent",
        pattern=ArchitecturePattern.TOOL_AGENT,
        description="Single LlmAgent wired with typed FunctionTools, before/after tool callbacks, and trajectory evals.",
        adk_classes=["LlmAgent", "FunctionTool", "Runner", "InMemorySessionService"],
        included_files=["app/agent.py", "app/tools.py", "app/callbacks.py", "tests/eval/default_eval.evalset.json"],
    ),
    "sequential_workflow": TemplateMetadata(
        id="sequential_workflow",
        name="Deterministic SequentialAgent Pipeline",
        pattern=ArchitecturePattern.SEQUENTIAL_WORKFLOW,
        description="Multi-stage SequentialAgent pipeline where single-turn sub-agents pass structured outputs via session state.",
        adk_classes=["SequentialAgent", "LlmAgent", "Runner", "InMemorySessionService"],
        included_files=["app/agent.py", "app/tools.py", "tests/integration/test_agent_e2e.py"],
    ),
    "parallel_workflow": TemplateMetadata(
        id="parallel_workflow",
        name="Concurrent ParallelAgent Fan-Out / Fan-In",
        pattern=ArchitecturePattern.PARALLEL_WORKFLOW,
        description="ParallelAgent executing independent research and verification branches concurrently.",
        adk_classes=["ParallelAgent", "SequentialAgent", "LlmAgent", "Runner"],
        included_files=["app/agent.py", "app/tools.py", "tests/integration/test_agent_e2e.py"],
    ),
    "loop_workflow": TemplateMetadata(
        id="loop_workflow",
        name="Bounded Iterative LoopAgent Workflow",
        pattern=ArchitecturePattern.LOOP_WORKFLOW,
        description="Generator-critic iterative refinement workflow with explicit max_iterations termination guard.",
        adk_classes=["LoopAgent", "LlmAgent", "Runner"],
        included_files=["app/agent.py", "app/tools.py", "tests/integration/test_agent_e2e.py"],
    ),
    "graph_workflow": TemplateMetadata(
        id="graph_workflow",
        name="ADK 2.0 Deterministic Graph Workflow (Workflow + JoinNode)",
        pattern=ArchitecturePattern.GRAPH_WORKFLOW,
        description="Declarative ADK 2.0 Workflow combining single-turn LlmAgent nodes, Event(route=...) dict branching, and JoinNode fan-in.",
        adk_classes=["Workflow", "Event", "JoinNode", "LlmAgent", "Runner"],
        included_files=["app/agent.py", "app/tools.py", "assets/graph_agent.py", "tests/integration/test_agent_e2e.py"],
    ),
    "specialist_multi_agent": TemplateMetadata(
        id="specialist_multi_agent",
        name="Coordinator + Specialist Multi-Agent Team",
        pattern=ArchitecturePattern.SPECIALIST_MULTI_AGENT,
        description="Hierarchical coordinator LlmAgent delegating to domain-specific single-turn sub-agents.",
        adk_classes=["LlmAgent", "Runner", "InMemorySessionService"],
        included_files=["app/agent.py", "app/tools.py", "app/callbacks.py", "tests/integration/test_agent_e2e.py"],
    ),
    "mcp_agent": TemplateMetadata(
        id="mcp_agent",
        name="MCP-Enabled LlmAgent (MCPToolset)",
        pattern=ArchitecturePattern.MCP_ENABLED_AGENT,
        description="Agent connecting to Model Context Protocol servers (MCP SDK 1.x/2.x) with local mock fallback for CI.",
        adk_classes=["LlmAgent", "MCPToolset", "Runner"],
        included_files=["app/agent.py", "app/tools.py", "tests/unit/test_agent_unit.py"],
        requires_optional_extras=["mcp"],
    ),
    "rag_agent": TemplateMetadata(
        id="rag_agent",
        name="Grounded RAG Retrieval Agent",
        pattern=ArchitecturePattern.RAG_AGENT,
        description="Retrieval-augmented agent with document search tool, source citation enforcement, and hallucination checks.",
        adk_classes=["LlmAgent", "VertexAiRagRetrieval", "Runner"],
        included_files=["app/agent.py", "app/tools.py", "tests/eval/default_eval.evalset.json"],
    ),
    "a2a_remote_agent": TemplateMetadata(
        id="a2a_remote_agent",
        name="Agent2Agent (A2A) Remote Interoperability Agent",
        pattern=ArchitecturePattern.REMOTE_A2A_AGENT,
        description="Exposes root_agent via to_a2a() and consumes remote specialist agents via RemoteA2aAgent(use_legacy=False).",
        adk_classes=["LlmAgent", "RemoteA2aAgent", "to_a2a"],
        included_files=["app/agent.py", "app/fast_api_app.py", "tests/unit/test_agent_unit.py"],
        requires_optional_extras=["a2a"],
    ),
    "live_voice_agent": TemplateMetadata(
        id="live_voice_agent",
        name="Multimodal Live / Voice Streaming Agent",
        pattern=ArchitecturePattern.LIVE_VOICE_AGENT,
        description="Optional bidirectional audio/video streaming template using google.adk.live and session resumption.",
        adk_classes=["LlmAgent", "Runner", "RunConfig"],
        included_files=["app/agent.py", "app/tools.py", "tests/unit/test_agent_unit.py"],
    ),
}


def list_templates() -> List[TemplateMetadata]:
    return [TEMPLATE_CATALOG[k] for k in sorted(TEMPLATE_CATALOG.keys())]
