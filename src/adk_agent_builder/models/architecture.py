"""Architecture patterns, workflow topologies, and trade-off scorecards."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class ArchitecturePattern(str, Enum):
    SINGLE_AGENT = "single_agent"
    TOOL_AGENT = "tool_agent"
    SEQUENTIAL_WORKFLOW = "sequential_workflow"
    PARALLEL_WORKFLOW = "parallel_workflow"
    LOOP_WORKFLOW = "loop_workflow"
    SPECIALIST_MULTI_AGENT = "specialist_multi_agent"
    GRAPH_WORKFLOW = "graph_workflow"
    REMOTE_A2A_AGENT = "remote_a2a_agent"
    MCP_ENABLED_AGENT = "mcp_enabled_agent"
    RAG_AGENT = "rag_agent"
    LIVE_VOICE_AGENT = "live_voice_agent"


class TradeoffScorecard(CompatModel):
    pattern: ArchitecturePattern
    complexity_score: int = 1  # 1 (lowest) to 5 (highest)
    reliability_score: int = 5  # 1 to 5
    latency_profile: str = "low"
    token_cost_profile: str = "low"
    testability_score: int = 5  # 1 to 5
    maintainability_score: int = 5  # 1 to 5
    fit_rationale: str = ""


class AgentNodeSpec(CompatModel):
    name: str
    agent_type: str = "LlmAgent"  # LlmAgent | SequentialAgent | ParallelAgent | LoopAgent | BaseAgent | RemoteA2aAgent
    model: str = "gemini-2.5-flash"
    mode: str = "single_turn"  # chat | single_turn
    include_contents: str = "default"
    instruction: str = "You are a helpful specialist agent."
    description: str = "ADK Agent node"
    tools: List[str] = Field(default_factory=list)
    sub_agents: List[str] = Field(default_factory=list)
    output_key: Optional[str] = None
    max_iterations: Optional[int] = None
    require_confirmation: bool = False
    callbacks: List[str] = Field(default_factory=list)


class ArchitecturePlan(CompatModel):
    """Complete architectural recommendation and execution graph plan."""

    project_name: str
    selected_pattern: ArchitecturePattern
    selected_template: str
    selection_rationale: str
    rejected_alternatives: List[TradeoffScorecard] = Field(default_factory=list)
    selected_scorecard: TradeoffScorecard
    root_agent: AgentNodeSpec
    sub_agents: List[AgentNodeSpec] = Field(default_factory=list)
    required_integrations: List[str] = Field(default_factory=list)
    termination_conditions: Dict[str, Any] = Field(
        default_factory=lambda: {
            "max_iterations": 5,
            "max_llm_calls": 20,
            "timeout_seconds": 60,
            "abort_signal_enabled": True,
        }
    )
    session_strategy: Dict[str, Any] = Field(default_factory=dict)
    security_controls: List[str] = Field(default_factory=list)
    observability_plan: Dict[str, Any] = Field(default_factory=dict)
    deployment_target: str = "local"
