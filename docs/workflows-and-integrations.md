# Multi-Agent Workflow Design & Custom Integrations (`docs/workflows-and-integrations.md`)

## 1. Selecting the Right ADK Workflow Topology

`ArchitecturePlanner` (`src/adk_agent_builder/planning/planner.py`) scores 11 patterns and chooses the simplest pattern that satisfies your requirements:

| Pattern | ADK Class | When to Choose | Key ADK v2.12.0 Rule |
| :--- | :--- | :--- | :--- |
| **Single / Tool Agent** | `LlmAgent` | Focused task with 0–3 cohesive tools | Default `mode="chat"` for root interactive agent |
| **Sequential Pipeline** | `SequentialAgent` | Strict multi-step pipeline (`intake -> analysis -> synthesis`) | Sub-agents must use `mode="single_turn"` and `include_contents="default"` |
| **Concurrent Fan-Out** | `ParallelAgent` | Independent branches running concurrently | Declare `ParallelAgent` statically in hierarchy to preserve resume & OTel |
| **Iterative Refinement** | `LoopAgent` | Generator + critic loop | Always set explicit `max_iterations` termination bound |
| **Coordinator + Specialists** | `LlmAgent(sub_agents=[...])` | Dynamic routing across specialized domains | Sub-agents with `mode="single_turn"` are exposed automatically as tools |
| **Remote Interoperability** | `RemoteA2aAgent` / `to_a2a()` | Cross-service or cross-framework agent calls | Set `use_legacy=False` and require HTTPS for non-loopback AgentCard URLs |

## 2. Registering Custom Tools & Integrations

Use `IntegrationRegistry.register()` (`src/adk_agent_builder/tools/registry.py`) to register new enterprise connectors with typed schemas, timeouts, and credential checks:

```python
from adk_agent_builder.tools.registry import IntegrationRegistry, IntegrationStatus, ToolIntegrationSpec

registry = IntegrationRegistry()
registry.register(
    ToolIntegrationSpec(
        id="service_now_incidents",
        name="ServiceNow Incident Connector",
        category="enterprise_itsm",
        status=IntegrationStatus.IMPLEMENTED,
        adk_import_path="app.tools",
        adk_class_or_symbol="lookup_incident",
        requires_credentials=True,
        required_env_vars=["SERVICENOW_INSTANCE_URL", "SERVICENOW_TOKEN"],
        default_timeout_seconds=10.0,
    )
)
```
