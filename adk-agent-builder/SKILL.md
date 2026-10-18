---
name: adk-agent-builder
description: Build, test, evaluate, deploy and package Google Agent Development Kit (ADK) agents end to end. Use this skill whenever the user mentions Google ADK, google-adk, "adk create", "adk web", "adk api_server", agent.py with Gemini, agents built with Google's framework - and whenever an existing ADK agent misbehaves, fails its tests, answers wrongly, fabricates facts, loops, routes to the wrong sub-agent, or errors with quota/auth problems. It scaffolds apps in a fresh venv with adk create, writes the agent code (tools, state, sessions, SQLite/Postgres, memory, ADK Skills, MCP, callbacks/plugins, guardrails), designs multi-agent orchestration (coordinator/sub-agents, Sequential/Parallel/Loop agents, graph workflows, A2A), derives requirements and test specs, runs them through the ADK API server with failure classification and pacing for free-tier keys, scores and iterates until the tests pass, renders a results dashboard, deploys to Cloud Run or Agent Engine, and packages the skill's own tooling.
---

# ADK Agent Builder

Turn "build me an agent that ..." into a **working, tested, evaluated** Google ADK (Python, `google-adk`) app - and keep it honest: the scripts do the deterministic work (scaffold, run, score, classify, report), you do the design and judgment. Never claim behaviour passed unless `results.json` says `PASS`.

| Ships | Purpose |
|---|---|
| `scripts/create_agent.py` | venv + `pip install google-adk[db,mcp]` + `adk create` (all flags, no menus) + file verification + JSON report |
| `scripts/testing.py` | introspects the app, starts `adk api_server`, runs the JSON spec over HTTP, evaluates, classifies failures, scores, writes reports |
| `scripts/dashboard.py` | renders `results.json` into one standalone HTML dashboard (inline CSS, no CDN) |
| `scripts/deploy_agent.py` | wraps `adk deploy` (Cloud Run / Agent Engine) with preflight checks, secret audit, `--dry-run`, JSON report |
| `scripts/quick_validate.py` | validates a skill folder (frontmatter, naming, doc-integrity of referenced paths) |
| `scripts/package_skill.py` | packages a skill folder into a clean, verified `.skill` archive |

References (read only when needed): `references/architecture.md` (agent types, orchestration, graph workflows, A2A), `references/data-memory-skills.md` (state, sessions, databases, memory, ADK Skills, MCP, plugins, guardrails), `references/evaluation.md` (spec format, rubric, failure -> fix table; read before writing tests), `references/pitfalls.md` (verified gotchas; read when something fails unexpectedly), `references/deployment.md` (deploy targets, secrets, verification).

Templates in `assets/` (tested, copy and adapt): `multi_agent_agent.py` (coordinator + specialists), `graph_agent.py` (routing + fan-out/fan-in graph), `sqlite_tools.py` (safe database tools), `spec_example.json` (a full 8-test spec matching the coordinator template).

## Facts verified against ADK 2.12 (do not "correct" them from memory)

- `adk create` takes everything as flags: `--model`, `--api_key`, `--type CODE`. Interactive menus appear only when flags are missing; `create_agent.py` passes them and closes stdin, so no prompt can hang a run. Telemetry only prompts on a real TTY and is off by default; the script also records `adk telemetry disable`.
- Model ids (2.12 menu): `gemini-3.5-flash`, `gemini-3.8-flash`; the script defaults to `gemini-2.5-flash` (a per-minute workable free-tier bucket) and accepts `--model`. The code alias `gemini-flash-latest` tracks the newest release, which may have a tiny daily bucket - pin an id for repeatable runs.
- App names: `^[a-zA-Z][a-zA-Z0-9_-]*$`, and `user` is reserved. Both are enforced when scaffolding, before any install work.
- Run CLI commands from the **parent** directory of the app folder. `adk api_server`/`adk web` take the agents directory (the workspace), not the app folder.
- API server: `POST /apps/{app}/users/{u}/sessions/{s}` (body = initial state) · `POST /run` returns all events as JSON · `GET /apps/{app}/app-info` · `GET /list-apps` · `GET /health` · camelCase bodies (`appName`, `newMessage`).
- ADK 2 imports: `from google.adk import Agent, Workflow, Event`; `from google.adk.workflow import JoinNode`; workflow agents still exist: `from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent`.
- Extras: `db` required for `DatabaseSessionService` (async driver URLs only: `sqlite+aiosqlite:///...`, `postgresql+asyncpg://...`), `mcp` for `McpToolset`, `a2a` for `RemoteA2aAgent`/`to_a2a` imports, `eval` for ADK's graders (pulls litellm - on Windows this extra can hit the 260-char path limit; skip it there). The scripts install `db,mcp` by default.
- Deploy subcommands: `cloud_run`, `docker`, `agent_engine`, `gke`; common flags `--project`, `--region`, `--service_name`, `--app_name`, `--with_ui`, `--env K=V`, and provider passthrough after `--`.
- The app's `.env` is loaded with override behavior by the CLI (it walks up from the app folder), so a placeholder key in `.env` beats a correct key in the shell. Check `.env` first when auth fails.

## Step 0 - Understand the request (keep it short)

Extract, asking at most 2-3 questions and only if the answer changes the design:
1. Goal and users - what the agent does, who talks to it.
2. Capabilities - tools/APIs/data; database, cross-session memory, files, web search, MCP servers?
3. Structure - single agent or several specialists? Free-form delegation or a fixed process? (decision table in `references/architecture.md`)
4. Inputs/outputs - free text, or structured (`input_schema` / JSON output)?
5. Constraints - tone, safety rules, languages, latency budget.

State your assumptions in one short paragraph and proceed. Prefer the **simplest architecture that satisfies the requirements**: one `LlmAgent` with good tools beats a multi-agent system unless specialization, fixed ordering, parallelism or iterative refinement is genuinely needed.

## Step 1 - Scaffold with `create_agent.py`

```bash
python <skill_dir>/scripts/create_agent.py <app_name> --workspace ./adk_workspace \
       --api-key "$GOOGLE_API_KEY"        # omit -> literal placeholder YOUR_API_KEY in .env
# reuse an existing google-adk install instead of building a venv:
python <skill_dir>/scripts/create_agent.py <app_name> --workspace ./ws --no-venv --skip-install --adk adk
# different model:
python <skill_dir>/scripts/create_agent.py <app_name> --workspace ./ws --model gemini-3.8-flash
```

- It prints a JSON summary and writes `<workspace>/adk_runs/create_report.json`. **Check `success: true`** and read the step list.
- No key supplied -> placeholder `YOUR_API_KEY` in `.env`: structure and imports are testable, but live runs will report `INFRA_BLOCKED`. Tell the user plainly that a real key from https://aistudio.google.com/apikey must go into `<app>/.env` (`GOOGLE_API_KEY=...`) before behaviour can be evaluated. Never print or commit a real key.
- Failure handling: `pip install` error -> check Python >= 3.10 and network, or retry with `--extras db` (Windows path-length with `eval`; see `references/pitfalls.md`); "folder exists" -> use `--force` only if you created it; import smoke test failed -> read the step detail, it carries the stderr tail.

## Step 2 - Write the agent code (inside `<workspace>/<app_name>/`)

Edit the generated files; keep `__init__.py` as `from . import agent`; `agent.py` must expose `root_agent` (or `app = App(...)` whose name equals the folder name). Start from `assets/multi_agent_agent.py`, `assets/graph_agent.py` or `assets/sqlite_tools.py` when they fit.

Rules that make agents work (details in the references):
- **Instructions**: role, step-by-step behaviour, when to call each tool, output format, what to refuse. Reference state with `{key}`, and `{key?}` where the value may legitimately be absent.
- **Tools** are plain Python functions: type hints, a precise docstring (it *is* the description the model reads), few simple parameters, return a `dict` with a `"status"` key and human-readable errors. Never wrap tool bodies in broad `except Exception:` - ADK 2 uses exceptions to retry and pause.
- **Sub-agents**: each needs a distinct, specific `description` (routing runs on it); one agent instance may have only one parent. Negative routing tests catch overlapping descriptions.
- **Structured output**: `output_schema` (Pydantic) on the agent; combined with tools on the same agent it is model-dependent - if it fails, split into a tool-using agent plus a formatter agent.
- **Databases/memory/skills/MCP**: follow `references/data-memory-skills.md`. Secrets come from `.env`; DB tools use parameterised SQL and validate inputs before writing.
- **Guardrails**: `before_tool_callback`/`before_model_callback` for risky tools; McpToolset supports a confirmation callback for destructive MCP tools; use ADK's tool-confirmation flow for anything irreversible.
- Add a `requirements.txt` with extra packages and a short `README.md` (how to run `adk web`).

Sanity check the import before writing tests - it also writes the introspected agent tree:

```bash
python <skill_dir>/scripts/testing.py --workspace ./adk_workspace --app <app_name> --init-spec
```

## Step 3 - Write requirements and tests

1. Turn the request into numbered requirements (R1..Rn), each testable, tagged `must` or `should`. Include the implicit ones: out-of-scope handling, prompt injection, schema validity, "facts come from tools", no secret leaks, routing both ways.
2. Write the spec JSON (format in `references/evaluation.md`; full example in `assets/spec_example.json`). Rules:
   - at least one test per requirement and **>= 8 tests overall**; cover `functional`, `edge`, `safety`, `schema` (if structured I/O), `multi_agent` (routing incl. one negative), `memory` (multi-turn/state), `performance` (latency/tool budget);
   - if the agent has an `input_schema`, inputs are JSON objects matching it (`testing.py` validates them first and reports `SPEC_INPUT_INVALID` - a spec bug, not an agent bug);
   - assert **mechanisms** (tool called, args, agent involved, route, state, JSON validity, regex/invariants), not model phrasing.
3. Save as `<workspace>/adk_runs/spec.json` (copy from the printed `spec_skeleton.json`). The runner refuses specs that still contain `TODO`.

## Step 4 - Run the tests

```bash
python <skill_dir>/scripts/testing.py --workspace ./adk_workspace --app <app_name> \
       --spec ./adk_workspace/adk_runs/spec.json \
       [--repeat 2] [--min-interval 13] [--retry-infra 2] [--export-evalset]
```

- Starts `adk api_server` on a free port with SQLite sessions, one fresh session per test, then stops it. Outputs in `adk_runs/<timestamp>/`: `report.md` (read first), `results.json`, `transcripts.md` (full conversations incl. tool calls), `raw/<test>__runN.json` (every event + state), `server.log`, `agent_schema.json`, `app_info.json`.
- Free-tier keys: `--min-interval 13` paces a 5-requests/minute bucket; `--min-interval 1` between runs against a deployed service. `--retry-infra N` retries transient failures with exponential backoff. Quota throttling arrives as a bare `/run HTTP 500`; when a failed test spent zero tokens and its server-log window contains quota markers, it is reclassified to `QUOTA_OR_RATE_LIMIT` instead of `AGENT_RUNTIME_ERROR`.
- Exit codes: 0 PASS · 1 failures · 2 infra blocked (key/network/quota/model) · 3 import error or server did not start · 4 bad spec.

## Step 5 - Evaluate (judgment on top of the numbers)

Read `report.md`, then **skim `transcripts.md`** - passing assertions do not prove good answers. Score 1-5 on each dimension and write the table into `<workspace>/adk_runs/evaluation.md`:

| Dimension | Look for |
|---|---|
| Task success | Does the final answer solve the request using real tool data? |
| Instruction following | Format, tone, scope, refusals as specified |
| Tool use | Right tool, right args, no redundant/looping calls, errors handled |
| Orchestration (multi-agent) | Correct routing, no ping-pong, sub-agent output used, state passed |
| Robustness & safety | Out-of-scope, injection, bad input, missing data |
| Efficiency | Latency p50/p95, tokens, tool calls per task |

Call the agent "done" only when the script says `PASS` **and** task success, instruction following and tool use score >= 4. If `INFRA_BLOCKED`, do not "fix" the agent - fix the environment or report honestly that behaviour is unverified.

Optionally render the numbers (and that evaluation) for the user:

```bash
python <skill_dir>/scripts/dashboard.py --results ./adk_workspace/adk_runs/<timestamp>/results.json \
       --evaluation ./adk_workspace/adk_runs/evaluation.md --out ./adk_workspace/adk_runs/dashboard.html
```

Deeper (real key, ADK graders): `--export-evalset` writes `<app>/evals/generated.evalset.json`, then `adk eval <app> <that file>`; criteria like `rubric_based_final_response_quality_v1`, `hallucinations_v1`, `safety_v1` are described in `references/evaluation.md`.

## Step 6 - Fix and iterate (max 5 rounds)

Use the `failure_class` and per-check hints in `report.md`; the full table is in `references/evaluation.md`. Summary:

| Failure | Typical fix |
|---|---|
| `AUTH_INVALID_KEY`, `INFRA_NETWORK`, `QUOTA_OR_RATE_LIMIT`, `MODEL_NOT_FOUND` | Environment, not code: real key in `.env`, connectivity, pace the run, correct model id |
| `AGENT_RUNTIME_ERROR` | Read `server.log` and the raw event error; fix the exception, schema mismatch or missing state key |
| `ASSERTION_FAILED` - tool not called | Sharpen the tool docstring; say in the instruction when to call it |
| `ASSERTION_FAILED` - wrong/missing sub-agent | Make descriptions mutually exclusive; state the routing; or switch to a fixed workflow |
| `ASSERTION_FAILED` - content | Check the tool result reached the answer (`output_key`, `{key}` templating) |
| `SPEC_INPUT_INVALID` | Fix the spec input, not the agent |
| Flaky | Lower temperature, make the instruction explicit, or make the process deterministic (graph workflow) |

Change one thing at a time, re-run the **whole** suite (a fix that breaks two green tests is a regression), and log each round (what failed, what changed, new score) in `evaluation.md`. After 5 rounds with a MUST still failing, stop, report the failures, your diagnosis and options - never weaken a test to force a pass; only change a test if the test itself was wrong, and say so.

## Step 7 - Deliver

Give the user: what was built (architecture in 3-5 lines), the file list, how to run it (`cd <workspace>` and `.venv\Scripts\activate` on Windows / `source .venv/bin/activate` on POSIX, then `adk web` - development only), the verdict with pass counts, latency numbers, known gaps, and the key reminder if a placeholder is still in `.env`. Never claim live-model behaviour was verified when the verdict was `INFRA_BLOCKED`.

## Step 8 - Deploy (only when asked)

Read `references/deployment.md` first. Always dry-run, then deploy, then verify - a deploy that printed "done" is not a deploy that works:

```bash
python <skill_dir>/scripts/deploy_agent.py ./adk_workspace/<app_name> --mode cloud_run \
       --project <gcp-project> --region us-central1 --service-name <service> \
       --env GOOGLE_GENAI_USE_ENTERPRISE=0 --dry-run          # inspect command + warnings first
# real deploy: drop --dry-run. Agent Engine: --mode agent_engine --project P --region R
# verify the deployed service with the same spec:
python <skill_dir>/scripts/testing.py --app <app_name> --workspace ./adk_workspace \
       --base-url https://<service-url> --spec ./adk_workspace/adk_runs/spec.json --min-interval 2
```

The script preflights (`gcloud` present, agent folder valid), audits `.env` for live-looking secrets before they ride along with staged source, and writes `adk_runs/deploy_report.json`. Report the service URL/engine id and the verification result back to the user.

## Maintaining this skill

Development-only suite (not shipped): `python tests/test_offline.py` - offline, no API key; includes a real `adk create` scaffold against an existing ADK install when `ADK_TEST_PYTHON`/`ADK_TEST_ADK` are set. After any edit to this skill:

```bash
python <skill_dir>/scripts/quick_validate.py <skill_dir> --strict     # frontmatter + doc-integrity (every referenced path must exist)
python <skill_dir>/scripts/package_skill.py <skill_dir> ./dist       # writes <name>.skill, excludes tests/.env/adk_runs/*.db, verifies the archive
```

The validator fails on instructions that point at missing files - the exact bug this skill once shipped - so every path you name in this file must exist in the folder.
