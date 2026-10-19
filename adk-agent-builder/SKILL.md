---
name: adk-agent-builder
description: Design, scaffold, validate, test, evaluate, pace free-tier API quotas, self-repair, render HTML dashboards, package, and deploy production-ready Google Agent Development Kit (ADK 2.x) agent systems end to end. Use this skill whenever the user mentions Google ADK, google-adk, adk create, adk web, adk api_server, Agents CLI, agent.py with Gemini, SequentialAgent, ParallelAgent, LoopAgent, Graph Workflow, JoinNode, RemoteA2aAgent, MCPToolset, or wants to build, debug, evaluate, or deploy an ADK agent on Cloud Run, Vertex AI Agent Runtime (Agent Engine), GKE, or Docker.
---

# Google ADK Agent Builder

Turn "build me an agent that ..." into a **working, tested, evaluated, and deployable** Google ADK (Python, `google-adk` v2.12+) application. The deterministic scripts scaffold, validate, pace free-tier API quotas, score, classify failures, and render dashboards.

| Shipped Script | Purpose |
|---|---|
| `scripts/create_agent.py` | Unattended `venv` + `pip install google-adk[db,mcp]` + `adk create` (flags only, no interactive menus) + smoke import + JSON report |
| `scripts/testing.py` | Introspects app, starts `adk api_server`, runs JSON spec over `POST /run` with `--min-interval` & `--retry-infra`, classifies failures, writes `results.json` & `report.md` |
| `scripts/dashboard.py` | Renders `results.json` (and optional `evaluation.md`) into a standalone dark-mode HTML dashboard (inline CSS, no CDN) |
| `scripts/deploy_agent.py` | Wraps `adk deploy` (`cloud_run`, `agent_engine`, `docker`, `gke`) with preflight checks, `.env` live-secret audit, `--dry-run`, and JSON report |
| `scripts/quick_validate.py` | Validates a skill folder (`SKILL.md` frontmatter, kebab-case naming, and referenced doc-path integrity) |
| `scripts/package_skill.py` | Packages a skill folder into a clean, verified `.skill` archive (never ships `.env`, `*.db`, `.venv`, `adk_runs`, or `tests`) |

References in `references/` (read on demand):
- `references/architecture.md` — Agent types, coordinator/specialist routing, `SequentialAgent`/`ParallelAgent`/`LoopAgent`, ADK 2.0 `Workflow` graphs, `JoinNode`, and A2A.
- `references/data-memory-skills.md` — Session state (`{key}` / `{key?}`), `DatabaseSessionService` (`sqlite+aiosqlite:///...`), memory, `SkillToolset`, `MCPToolset`, and guardrails.
- `references/evaluation.md` — Test spec schema, deterministic assertions, rubric scoring, and failure-to-fix mapping.
- `references/pitfalls.md` — Verified ADK 2.12 gotchas (quota 429 surfacing as HTTP 500, `.env` override behavior, Windows 260-char path limit).
- `references/deployment.md` — Cloud Run, Vertex AI Agent Engine, Docker, GKE, and secret handling.

Templates in `assets/` (tested, copy and adapt):
- `assets/multi_agent_agent.py` — Coordinator + specialists (`order_support`, `billing`) with status-dict tools and pre-write validation.
- `assets/graph_agent.py` — ADK 2.0 `Workflow` with `Event(route=...)` dict routing and `JoinNode` fan-out/fan-in.
- `assets/sqlite_tools.py` — Parameterized SQLite tools with Pydantic input validation and resilient connection handling.
- `assets/spec_example.json` — Full 8-test specification matching `assets/multi_agent_agent.py`.

## Verified ADK 2.12 Facts

- `adk create` accepts `--model`, `--api_key`, and `--type CODE` flags so `scripts/create_agent.py` runs unattended with closed stdin and records `adk telemetry disable`.
- Default model is `gemini-2.5-flash` (workable per-minute free-tier bucket); override with `--model`. Note that `gemini-flash-latest` resolves to the newest model, which often has a strict **20 requests/day** free-tier cap.
- App names must match `^[a-zA-Z][a-zA-Z0-9_-]*$` and cannot be `user`.
- Run `adk api_server` and `adk web` from the **parent** workspace directory of the app folder.
- ADK 2.0 imports: `from google.adk import Agent, Workflow, Event`; `from google.adk.workflow import JoinNode`; `from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent`.

## Workflow Steps

1. **Understand Requirements & Select Simplest Architecture**: Prefer one `LlmAgent` with focused tools unless specialization, fixed ordering (`SequentialAgent`), concurrency (`ParallelAgent`), iterative refinement (`LoopAgent`), or deterministic branching (`Workflow` graph) is genuinely required.
2. **Scaffold with `scripts/create_agent.py`**:
   ```bash
   python3 scripts/create_agent.py my_app --workspace ./adk_workspace --api-key "$GOOGLE_API_KEY"
   ```
3. **Implement Agent & Tools**: Adapt `assets/multi_agent_agent.py`, `assets/graph_agent.py`, or `assets/sqlite_tools.py`. Always return `{"status": ...}` dicts from tools and validate inputs before mutating state.
4. **Offline Validation First (0 API Calls)**: Validate syntax, imports, tool contracts, and database persistence offline before spending live API quota.
5. **Paced Live Evaluation (20 Messages/Day & 5 RPM Safe)**:
   ```bash
   python3 scripts/testing.py --workspace ./adk_workspace --app my_app --spec assets/spec_example.json --min-interval 13 --retry-infra 2
   ```
6. **Render Standalone HTML Dashboard**:
   ```bash
   python3 scripts/dashboard.py --results ./adk_workspace/adk_runs/<run>/results.json
   ```
7. **Deploy Safely with Secret Audit**:
   ```bash
   python3 scripts/deploy_agent.py ./adk_workspace/my_app --mode cloud_run --project my-proj --region us-central1 --dry-run
   ```
