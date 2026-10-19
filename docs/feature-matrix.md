# Google ADK v2.12.0 Evidence-Backed Feature & Compatibility Matrix (`docs/feature-matrix.md`)

Every capability below is verified against official Google ADK documentation ([adk.dev](https://adk.dev/)) and the official Python SDK release history ([google/adk-python releases](https://github.com/google/adk-python/releases) through `v2.12.0`, released 2026-10-13).

## Status Legend

- **Implemented & Tested**: Fully implemented in `adk_agent_builder` and verified by automated local unit/integration/acceptance tests.
- **Supported via Adapter**: Implemented in `adk_agent_builder` with configuration, code generation, and contract tests; live execution requires installing the optional SDK extra and supplying provider/cloud credentials.
- **Experimental**: Official ADK feature marked experimental upstream (`@experimental` or feature-flag gated).
- **Blocked by External Prerequisites**: Supported in generated plans/configs, but live execution requires cloud infrastructure or credentials unavailable in an offline CI sandbox.

## 1. Agent Construction, Reasoning & Models

| Feature / Capability | Official SDK / Package | ADK Version / API Notes | Suite Module | Status | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `LlmAgent` / `Agent` | `google-adk` | Core LLM reasoning agent; supports `mode="chat"` and `mode="single_turn"` (`include_contents="default"`) | `generation/generator.py` | **Implemented & Tested** | [Simple Agents](https://adk.dev/agents/llm-agents/) |
| Custom `BaseAgent` | `google-adk` | Custom orchestration via `_run_async_impl` | `templates/catalog.py` | **Implemented & Tested** | [Custom Agents](https://adk.dev/agents/custom-agents/) |
| `FallbackModel` | `google-adk>=2.9.0` | Automatic failover between primary and backup models (`c300b8d`) | `models/providers.py` | **Implemented & Tested** | [ADK Releases v2.9.0](https://github.com/google/adk-python/releases) |
| `ModelConsultTool` | `google-adk>=2.11.0` | Mid-task advisor model consultation capped by turn/session budgets (`84cc99a`) | `models/providers.py`, `tools/registry.py` | **Supported via Adapter** | [ADK Releases v2.11.0](https://github.com/google/adk-python/releases) |
| OpenAI Models (`OpenAILlm`, `OpenAIResponsesLlm`) | `google-adk[openai]>=2.10.0` | Moved to `google.adk.integrations.openai`; uses `OpenAIGenerateContentConfig.effort` (`b3d1392`) | `models/providers.py`, `validation/validator.py` | **Supported via Adapter** | [ADK Releases v2.10.0](https://github.com/google/adk-python/releases) |
| Anthropic (`AnthropicLlm`) | `google-adk`, `anthropic` | Supports Claude adaptive thinking with visible thoughts (`v2.9.1`, `ba0d542`) | `models/providers.py` | **Supported via Adapter** | [ADK Releases v2.9.1](https://github.com/google/adk-python/releases) |
| LiteLLM, Ollama, vLLM | `google-adk`, `litellm` | JSON-tolerant tool argument parsing (`v2.12.0`, `a01b226`) | `models/providers.py` | **Supported via Adapter** | [ADK Releases v2.12.0](https://github.com/google/adk-python/releases) |

## 2. Workflow Orchestration

| Feature / Capability | Official SDK / Package | ADK Version / API Notes | Suite Module | Status | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SequentialAgent` | `google-adk` | Deterministic sequential execution sharing `session.state` | `planning/planner.py`, `generation/generator.py` | **Implemented & Tested** | [Template Workflows](https://adk.dev/agents/workflow-agents/) |
| `ParallelAgent` | `google-adk` | Concurrent branch execution; must be declared statically for resume/OTel | `planning/planner.py`, `generation/generator.py` | **Implemented & Tested** | [Parallel Workflow](https://adk.dev/agents/workflow-agents/parallel-agents/) |
| `LoopAgent` | `google-adk` | Bounded iterative execution via `max_iterations` | `planning/planner.py`, `generation/generator.py` | **Implemented & Tested** | [Template Workflows](https://adk.dev/agents/workflow-agents/) |
| ADK 2.0 Graph `Workflow` | `google-adk>=2.0.0` | Declarative YAML graphs (`v2.9.0`), `@node`/`FunctionNode` `require_confirmation` (`v2.12.0`), `abort_signal` (`v2.11.0`) | `planning/planner.py`, `templates/catalog.py` | **Implemented & Tested** | [ADK Workflows](https://adk.dev/workflows/) |

## 3. Tools, Protocols (MCP & A2A) & Skills

| Feature / Capability | Official SDK / Package | ADK Version / API Notes | Suite Module | Status | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Custom `FunctionTool` & Generators | `google-adk` | Sync/generator `FunctionTool`s run via `FunctionNode` thread pool (`v2.12.0`) | `tools/registry.py`, `generation/generator.py` | **Implemented & Tested** | [ADK Custom Tools](https://adk.dev/agents/llm-agents/) |
| `google_search` Grounding | `google-adk` | Allowed with sub-agents on Gemini 3+ (`v2.12.0`, `6d52a23`) | `tools/registry.py` | **Supported via Adapter** | [Google ADK](https://adk.dev/) |
| `MCPToolset` | `google-adk`, `mcp` | Supports MCP SDK 1.x and opt-in modern protocol 2.x (`v2.9.0`, `v2.11.0`) | `tools/registry.py`, `templates/catalog.py` | **Supported via Adapter** | [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18) |
| A2A (`to_a2a`, `RemoteA2aAgent`) | `google-adk`, `a2a-sdk` | `use_legacy=False` activates A2A extension; `AgentCardBuilder` skill security (`v2.12.0`) | `tools/registry.py`, `templates/catalog.py` | **Supported via Adapter** | [ADK A2A Quickstart](https://adk.dev/a2a/quickstart-exposing/) |
| `BigQueryToolset` & `MongoDBToolset` | `google-adk` | BigQuery protected write mode (`v2.10.0`); MongoDB vector/hybrid search (`v2.10.0`) | `tools/registry.py` | **Supported via Adapter** | [ADK Releases v2.10.0](https://github.com/google/adk-python/releases) |
| `SkillToolset` & Agent Skills | `google-adk` | `SkillDiscoveryMode` and experimental `ADK_ENABLE_SKILL_LIFECYCLE=1` (`v2.10.0`) | `skills/validator.py` | **Implemented & Tested** | [Agent Skills Spec](https://agentskills.io/specification) |

## 4. Sessions, State, Memory, Artifacts, Callbacks & Evaluation

| Feature / Capability | Official SDK / Package | ADK Version / API Notes | Suite Module | Status | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SessionService` & Rewind | `google-adk` | `InMemorySessionService` raises `SessionNotFoundError` on missing session (`v2.9.0`) | `sessions/manager.py` | **Implemented & Tested** | [ADK Sessions](https://adk.dev/sessions/) |
| `SQLite` Memory Service | `google-adk>=2.11.0` | Built-in local SQLite memory service (`sqlite://` URI, `9625b06`) | `sessions/manager.py` | **Implemented & Tested** | [ADK Memory](https://adk.dev/sessions/memory/) |
| `ArtifactService` Isolation | `google-adk>=2.12.0` | Caller-mutation isolation (`cb8ced5`) and `None` on negative version (`6193957`) | `sessions/manager.py` | **Implemented & Tested** | [ADK Artifacts](https://adk.dev/artifacts/) |
| Lifecycle Callbacks (`before_*`, `after_*`) | `google-adk>=2.12.0` | `after_tool_callback` screens tool outputs (`fdda17c`); `after_agent_callback` returns `None` | `security/governance.py` | **Implemented & Tested** | [ADK Callbacks](https://adk.dev/callbacks/) |
| Evaluation (`EvalSet`, Criteria, Efficiency) | `google-adk>=2.10.0` | Empty `EvalSet` raises `ValueError` (`9dbc2ae`); reports duration, tokens, and call counts (`2d428ea`) | `evaluation/evaluator.py` | **Implemented & Tested** | [ADK Evaluation](https://adk.dev/evaluate/) |
| Cloud Deployment (`cloud_run`, `agent_engine`, `gke`) | `google-adk`, `google-agents-cli` | Custom service accounts (`--service_account`, `v2.12.0`); live deploy requires GCP credentials | `deployment/deployer.py` | **Blocked by External Prerequisites (Dry-Run Tested)** | [Agents CLI](https://adk.dev/get-started/agents-cli/) |
