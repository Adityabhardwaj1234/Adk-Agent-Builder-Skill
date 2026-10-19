---
name: adk-agent-builder
description: Design, scaffold, validate, test, evaluate, pace free-tier API quotas, self-repair, render HTML dashboards, package, and deploy production-ready Google Agent Development Kit (ADK 2.x) agent systems end to end. Use this skill whenever the user mentions Google ADK, google-adk, adk create, adk web, adk api_server, Agents CLI, agent.py with Gemini, SequentialAgent, ParallelAgent, LoopAgent, Graph Workflow, JoinNode, RemoteA2aAgent, MCPToolset, or wants to build, debug, evaluate, or deploy an ADK agent on Cloud Run, Vertex AI Agent Runtime (Agent Engine), GKE, or Docker.
---

# Google ADK Agent Builder & Engineering Suite

Turn natural-language or structured requirements into **validated, tested, evaluated, and deployable** Google ADK (`google-adk` v2.12.0+) applications. This suite provides two complementary layers:

1. **Installable Python Engineering Package (`adk_agent_builder` CLI)**: 18 commands driving a 17-stage lifecycle (`doctor`, `audit`, `init`, `requirements`, `plan`, `build`, `validate`, `test`, `eval`, `quota`, `dashboard`, `report`, `package`, `deploy`, `smoke-test`, `status`, `integrations`, `skills`).
2. **Standalone Zero-Dependency Scripts (`scripts/`)**: Unattended `adk create` scaffolding (`scripts/create_agent.py`), live HTTP `adk api_server` evaluation with free-tier rate pacing (`scripts/testing.py`), self-contained HTML dashboard rendering (`scripts/dashboard.py`), `.env`-safe deployment wrapper (`scripts/deploy_agent.py`), and `.skill` validation/packaging (`scripts/quick_validate.py`, `scripts/package_skill.py`).

## Shipped Tooling, References, and Templates

| Component | Path | Purpose |
|---|---|---|
| **Core CLI** | `src/adk_agent_builder/cli.py` | 18-command lifecycle orchestrator (`adk-agent-builder`) |
| **Scaffold Script** | `scripts/create_agent.py` | Unattended `venv` + `pip install google-adk[db,mcp]` + `adk create` (flags only, no interactive menus) |
| **Live HTTP Harness** | `scripts/testing.py` | Introspects app, boots `adk api_server`, runs `spec.json` over `POST /run` with `--min-interval` & `--retry-infra` |
| **HTML Dashboard** | `scripts/dashboard.py` | Renders `results.json` or `EvalReport` into a standalone dark-mode HTML dashboard (zero CDN) |
| **Safe Deployer** | `scripts/deploy_agent.py` | Wraps `adk deploy` (`cloud_run`, `agent_engine`, `docker`, `gke`) with preflight & `.env` live-secret audit |
| **Skill Validator** | `scripts/quick_validate.py` | Validates `SKILL.md` frontmatter, kebab-case naming, and referenced doc paths |
| **Skill Packager** | `scripts/package_skill.py` | Builds clean `.skill` archive excluding `.env`, `*.db`, `.venv`, `adk_runs`, and `tests` |
| **Coordinator Template** | `assets/multi_agent_agent.py` | Coordinator + specialist `LlmAgent` tree with status-dict tools and pre-write validation |
| **Graph Template** | `assets/graph_agent.py` | ADK 2.0 `Workflow` with `Event(route=...)` dict branching and `JoinNode` fan-out/fan-in |
| **SQLite Template** | `assets/sqlite_tools.py` | Parameterized SQLite tools with Pydantic input validation |
| **Example Spec** | `assets/spec_example.json` | 8-test multi-category specification matching `assets/multi_agent_agent.py` |

Consult progressive-disclosure references in `references/` when needed:
- `references/architecture.md` & `references/adk-v2-patterns.md` — Agent types, `SequentialAgent`/`ParallelAgent`/`LoopAgent`, ADK 2.0 Graph `Workflow`, `JoinNode`, `mode="single_turn"`, and A2A.
- `references/data-memory-skills.md` — Session state (`{key}` / `{key?}`), `DatabaseSessionService` (`sqlite+aiosqlite:///...`), memory, `SkillToolset`, `MCPToolset`, and callbacks.
- `references/evaluation.md` & `references/evaluation-schemas.md` — HTTP `spec.json` assertions, ADK `.evalset.json` criteria, failure classification, and rubric scoring.
- `references/pitfalls.md` — Verified ADK 2.12 gotchas (quota 429 surfacing as HTTP 500, `.env` override precedence, Windows 260-char path limit on `eval` extra).
- `references/deployment.md` & `references/security-checklist.md` — Cloud Run, Vertex AI Agent Runtime (`agent_engine`), GKE, `.env` secret staging prevention, and callback guardrails.

## Verified ADK 2.12 Facts

- **Non-Interactive Scaffolding**: `adk create <app> --model gemini-2.5-flash --api_key <KEY> --type CODE` bypasses interactive menus. App names must match `^[a-zA-Z][a-zA-Z0-9_-]*$` and cannot be `user`.
- **Parent-Directory Execution**: Run `adk web` and `adk api_server` from the **parent** workspace directory containing the app folder.
- **ADK 2.0 Graph & Workflow Imports**: `from google.adk import Agent, Workflow, Event`; `from google.adk.workflow import JoinNode`; `from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent, LoopAgent`.
- **Single-Turn Sub-Agents**: Set `mode="single_turn"` and `include_contents="default"` on workflow/specialist sub-agents so control returns cleanly after each step.
- **Free-Tier Quota Reality (20 Messages/Day & 5 RPM)**: Free Gemini keys allow ~5 requests/minute and often cap at **20 requests/day per model**. Always run offline validation, unit tests, and deterministic mock evaluations FIRST at **0 API calls**, then use `adk-agent-builder quota` and `--min-interval 13` for live runs.

## 8-Step Engineering Workflow

### Step 1: Environment & Readiness Check

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli doctor --json
```

### Step 2: Requirements Intake & Contradiction Check

Parse natural-language or YAML requirements into a validated specification separating hard requirements, preferences, assumptions, and contradictions:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli requirements \
  --from-text "Build a sequential order lookup and policy compliance ADK agent" \
  --name order_compliance_agent \
  --output requirements.yaml
```

### Step 3: Architecture Selection & Trade-Off Planning

Select the simplest ADK pattern that satisfies the requirements (`single_agent`, `tool_agent`, `sequential_workflow`, `parallel_workflow`, `loop_workflow`, `graph_workflow`, `specialist_multi_agent`, `mcp_enabled_agent`, `rag_agent`, `remote_a2a_agent`, `live_voice_agent`):

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli plan \
  --spec requirements.yaml \
  --output architecture_plan.json
```

### Step 4: Project Generation & Bounded Self-Repair

Generate the project (or scaffold a live `google-adk` venv via `scripts/create_agent.py`) and run static AST validation, secret scanning, unit tests, and deterministic evaluations:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli build \
  --spec requirements.yaml \
  --output-dir ./generated_agents/order_compliance_agent \
  --repair \
  --json
```

### Step 5: Offline Testing & Deterministic Evaluation (0 API Calls)

Verify all tools, schemas, callbacks, and trajectories offline before spending any live API quota:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli test \
  --project-dir ./generated_agents/order_compliance_agent

PYTHONPATH=src python3 -m adk_agent_builder.cli eval \
  --project-dir ./generated_agents/order_compliance_agent \
  --output eval_report.json
```

### Step 6: Quota-Aware Live API Server Testing (20 Messages/Day Safe)

Estimate live message cost and build a 20-messages/day safe slice schedule before running `scripts/testing.py`:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli quota \
  --spec assets/spec_example.json \
  --daily-limit 20 \
  --rpm-limit 5 \
  --json

python3 scripts/testing.py \
  --workspace ./adk_workspace \
  --app my_app \
  --spec assets/spec_example.json \
  --min-interval 13 \
  --retry-infra 2
```

### Step 7: HTML Dashboard & Lifecycle Reporting

Render a self-contained HTML dashboard from either `results.json` (`scripts/testing.py`) or `eval_report.json` (`adk-agent-builder eval`):

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli dashboard \
  --input eval_report.json \
  --output dashboard.html
```

### Step 8: Secret-Audited Packaging & Deployment Planning

Audit `.env` for live secrets that would be staged into container images, package the project, and generate a dry-run deployment plan:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli deploy \
  --project-dir ./generated_agents/order_compliance_agent \
  --target cloud_run \
  --dry-run \
  --json
```
