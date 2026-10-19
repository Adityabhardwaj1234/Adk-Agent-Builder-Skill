# Architecture & Engineering Design (`docs/architecture.md`)

## 1. Dual-Layer Architecture

`Adk-Agent-Builder-Skill` is architected as two complementary layers:

1. **Layer A — Coding-Agent Skill (`SKILL.md` + `references/`)**: Follows the [Agent Skills Specification](https://agentskills.io/specification) with progressive disclosure (<150 lines in `SKILL.md` and on-demand reference guides in `references/`).
2. **Layer B — Python Engineering Suite (`src/adk_agent_builder/`)**: A modular, typed, zero-secret-leakage Python package and CLI (`adk-agent-builder`) that executes requirements intake, architecture trade-off planning, project scaffolding, static AST validation, security scanning, unit/integration testing, ADK evaluation, bounded self-repair, packaging, and deployment planning.

## 2. System Data Flow & Self-Repair Pipeline

```text
Customer Requirements (NL Prompt / YAML / JSON)
        │
        ▼
[01-03] RequirementsEngine (requirements/engine.py)
        ├── Normalizes functional & non-functional specs
        ├── Detects provider/latency/network contradictions
        └── Populates explicit assumptions & clarification questions
        │
        ▼
[04-06] ArchitecturePlanner & IntegrationRegistry (planning/planner.py, tools/registry.py)
        ├── Evaluates 11 ADK patterns across Complexity, Latency, Cost, Testability
        └── Selects simplest viable topology (LlmAgent, Sequential, Parallel, Loop, etc.)
        │
        ▼
[07-09] ProjectGenerator (generation/generator.py)
        └── Scaffolds app/agent.py, app/tools.py, app/callbacks.py, tests/, EvalSet, Dockerfile
        │
        ▼
[10-12] Quality Gates: ProjectValidator + SecurityScanner + TestRunner + EvaluationEngine
        │
        ├── Pass ──────────────────────────────────────────┐
        │                                                  │
        └── Fail ──► [13] DiagnosticsAndRepairEngine       │
                          ├── Captures stage & root cause  │
                          ├── Applies minimal targeted fix │
                          └── Reruns targeted & regression ┘
                                (Bounded: max 3 attempts)
        │
        ▼
[14-17] DeploymentManager & ObservabilityManager (deployment/deployer.py, observability/manager.py)
        ├── Generates OpenTelemetry / Cloud Trace / BigQuery Analytics manifest
        ├── Packages validated .zip archive (excluding .env & caches)
        ├── Produces dry-run deployment plan (requires --approve-billable for cloud execution)
        └── Executes smoke tests & writes .adk_builder_state/lifecycle_state.json
```

## 3. Module Boundaries

- `adk_agent_builder.models`: Pydantic v1/v2 compatible schemas (`CompatModel`) for requirements, architecture plans, 17-stage lifecycle checkpoints, ADK `EvalSet`/`EvalConfig`, and model providers.
- `adk_agent_builder.requirements`: Natural-language and YAML/JSON intake, normalization, and contradiction detection.
- `adk_agent_builder.planning`: Architecture trade-off scorecards and ADK agent/sub-agent node graph builder.
- `adk_agent_builder.tools`: Extensible `IntegrationRegistry` with capability declarations and credential health checks.
- `adk_agent_builder.sessions`: Local session management (`LocalSessionService`), persistent `SQLiteMemoryService` (`sqlite://`), and `IsolatedArtifactService`.
- `adk_agent_builder.skills`: `SkillValidator` enforcing `agentskills.io` frontmatter and path-traversal boundaries.
- `adk_agent_builder.security`: Static AST and secret scanner (`SecurityScanner`) plus runtime ADK callback guardrails (`GovernanceRuntime`).
- `adk_agent_builder.templates` & `generation`: 10 ADK templates and deterministic project code generator.
- `adk_agent_builder.validation`, `testing`, `evaluation`, `diagnostics`: Quality assurance and bounded self-repair loop.
- `adk_agent_builder.deployment`, `observability`, `integrations`: Packaging, cloud deployment planning, OpenTelemetry config, and `adk` / `agents-cli` bridge.
