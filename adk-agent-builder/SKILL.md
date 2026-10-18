---
name: adk-agent-builder
description: Build, test, evaluate and fix Google Agent Development Kit (ADK) agents end to end - scaffolds an ADK app in a fresh venv with `adk create` (latest Gemini flash model, Google AI Studio key), writes the agent code, generates requirements and tests, runs them through the ADK API server, scores the result and iterates until it passes. Supports single agents, tools, SQLite/Postgres databases, session state, long-term memory, ADK Skills, MCP, callbacks/plugins, and multi-agent orchestration (coordinator/sub-agents, Sequential/Parallel/Loop agents, ADK 2.0 graph workflows, A2A). Use this skill whenever the user mentions Google ADK, "adk create", "adk web", "adk api_server", an ADK agent, Gemini agents built with google-adk, multi-agent orchestration with Google's framework, or asks to create/test/evaluate/fix an agent app with Gemini - even if they do not say "skill" or "ADK" explicitly but describe building an agent with Google's agent framework.
---

# ADK Agent Builder

Turn a user's request ("build me an agent that ...") into a **working, tested, evaluated** Google ADK app.
You run a closed loop: **scaffold -> write code -> write requirements + tests -> run tests via the ADK API server -> evaluate -> fix -> re-run**.
The two bundled scripts do the deterministic work so you can spend your effort on design and judgment:

| Script | Purpose |
|---|---|
| `scripts/create_agent.py` | venv + `pip install google-adk` + `adk create` (answers menu: newest flash model, Google AI, API key) + verification |
| `scripts/testing.py` | introspects the app, starts `adk api_server`, runs your JSON test spec over HTTP, stores events/logs, scores, classifies failures |

Reference files (read only when needed):
- `references/architecture.md` - choosing agent types, multi-agent orchestration patterns, ADK 2.0 graph workflows, A2A (read for any request with more than one agent or any fixed process)
- `references/data-memory-skills.md` - state, sessions, databases, long-term memory, ADK Skills, MCP, compaction, caching, plugins (read when the agent must remember, store or fetch data)
- `references/evaluation.md` - spec format, how to derive requirements and tests, scoring rubric, failure -> fix table (read before writing tests)
- `references/pitfalls.md` - verified gotchas for ADK 2.x (read when something fails unexpectedly)
- `assets/` - tested templates: `multi_agent_agent.py`, `graph_agent.py`, `sqlite_tools.py`, `spec_example.json`

## Facts verified against ADK 2.12 (do not "correct" them from memory)

- `adk create` first asks to enable telemetry (the script disables it), then **model menu** (option 1 `gemini-3.5-flash`, option 2 `gemini-3.8-flash`, option 3 other), then **backend menu** (1 Google AI, 2 Vertex AI, 3 Login with Google), then **API key**. It writes `<app>/agent.py`, `__init__.py`, `.env` (`GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_ENTERPRISE=0`), `.gitignore`. Menus change between releases, so the script parses them and picks the newest non-lite "flash" entry rather than hard-coding "2".
- In code you may also use the alias `model="gemini-flash-latest"`, which the official docs use everywhere.
- Run commands from the **parent** directory of the app folder. `adk api_server`/`adk web` take the agents directory, not the app folder.
- API server: `POST /apps/{app}/users/{u}/sessions/{s}` creates a session (body = initial state); `POST /run` returns all events as a JSON list; `GET /apps/{app}/app-info` returns the agent tree; `GET /health`. JSON uses camelCase (`appName`, `newMessage`).
- ADK 2.x: `from google.adk import Agent, Workflow, Event`; `from google.adk.workflow import JoinNode`. Prebuilt workflow agents still exist: `from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent`.
- `DatabaseSessionService` needs `pip install "google-adk[db]"` and an **async** driver URL (`sqlite+aiosqlite:///...`, `postgresql+asyncpg://...`). `McpToolset` needs the `mcp` extra. The scripts install `db,mcp,eval` by default.

## Step 0 - Understand the request (keep it short)

Extract, asking at most 2-3 questions only if the answer would change the design:
1. **Goal and users** - what the agent does, who talks to it.
2. **Capabilities** - tools/APIs/data it needs; does it need a database, memory across sessions, files, web search, MCP servers?
3. **Structure** - single agent, or several specialists? Fixed process or free-form delegation? (decision table in `references/architecture.md`)
4. **Inputs/outputs** - free text, or structured (an input schema / JSON output)?
5. **Constraints** - tone, safety rules, languages, latency.

State your assumptions in one short paragraph and proceed. Prefer the **simplest architecture that satisfies the requirements**: one `LlmAgent` with good tools beats a multi-agent system unless specialization, fixed ordering, parallelism or iterative refinement is genuinely needed.

## Step 1 - Scaffold with `create_agent.py`

```bash
python <skill_dir>/scripts/create_agent.py <app_name> --workspace ./adk_workspace \
       --api-key "$GOOGLE_API_KEY"        # omit -> uses the literal placeholder YOUR_API_KEY
```
- `app_name`: letters/digits/underscore, must not start with a digit (e.g. `support_desk`).
- It prints a JSON summary and writes `<workspace>/adk_runs/create_report.json`. **Check `success: true`** and read the step list.
- If the user supplied no key, the placeholder `YOUR_API_KEY` is written into `.env`. Structure tests still run, but every Gemini call fails with a network/auth error, and `testing.py` will report `INFRA_BLOCKED`. Tell the user plainly that a real key from https://aistudio.google.com/apikey must go into `<app>/.env` (`GOOGLE_API_KEY=...`) before behaviour can be evaluated. Never print or commit a real key.
- Failure handling: `pip install` error -> check Python >= 3.10 and network; "folder exists" -> use `--force` only if you created it; menu not parsed -> pass `--model-choice N` after reading the menu in the report.

## Step 2 - Write the agent code (inside `<workspace>/<app_name>/`)

Edit the generated files; keep `__init__.py` as `from . import agent`; `agent.py` must expose `root_agent` (or `app = App(...)`, whose `name` equals the folder name).

Rules that make agents work (details and code in the references):
- **Instructions**: role, step-by-step behaviour, when to call each tool, output format, what to refuse. Reference state with `{key}` (use `{key?}` if it may be absent).
- **Tools** are plain Python functions: type hints, a precise docstring (it *is* the tool description the model reads), few simple parameters, return a `dict` with a `"status"` key and human-readable error messages. Do not swallow exceptions you want retried.
- **Sub-agents**: every sub-agent needs a distinct, specific `description` (the coordinator routes on it). One agent instance can have only one parent - create separate instances (or `.clone()`).
- **Structured output**: `output_schema` (Pydantic) on an agent; with tools on the same agent this only works reliably on newer Gemini models - otherwise split into a tool-using agent plus a formatter agent.
- **Code-execution and Google Search built-ins** can't be mixed with other tools on one agent in older versions; put them in their own sub-agent and wrap with `AgentTool`.
- **Databases/memory/skills/MCP**: follow `references/data-memory-skills.md`. Secrets and connection strings come from `.env`, never hard-coded; DB tools use parameterised SQL and least privilege.
- **Safety**: add `before_model_callback`/`before_tool_callback` guardrails for risky tools; use `require_confirmation` for destructive actions.
- Add `requirements.txt` listing extra packages, and a short `README.md` (how to run `adk web`).

After editing, sanity check that it imports: `python testing.py --workspace W --app A --init-spec` (also writes the introspected agent tree to `agent_schema.json`).

## Step 3 - Write requirements and tests

1. Turn the user's request into **numbered requirements** (R1..Rn), each testable, tagged `must` or `should`. Include implicit ones: handles out-of-scope requests, resists prompt injection, structured output is valid, tools are used for facts, no secrets leak.
2. Write the **test spec** JSON (format in `references/evaluation.md`; example in `assets/spec_example.json`). Rules:
   - At least **one test per requirement** and **>= 8 tests** overall; cover categories `functional`, `edge`, `safety`, `schema` (if structured I/O), `multi_agent` (routing/handoff), `memory` (multi-turn/state), `performance` (latency/tool-call budget).
   - If the agent has an `input_schema`, test inputs must be JSON objects matching it (`testing.py` validates them first).
   - Prefer **deterministic assertions** (tool called, args, agent involved, state key, JSON validity, substring/regex). LLM wording varies, so assert on facts, not phrasing.
   - For non-deterministic behaviour run `--repeat 3`; a test that passes only sometimes is reported as flaky.
3. Save it as `<workspace>/adk_runs/spec.json`. `testing.py` refuses specs that still contain `TODO`.

## Step 4 - Run the tests

```bash
python <skill_dir>/scripts/testing.py --workspace ./adk_workspace --app <app_name> \
       --spec ./adk_workspace/adk_runs/spec.json [--repeat 2] [--export-evalset]
```
It starts `adk api_server` on a free port with a SQLite session store, creates a fresh session per test, calls `/run`, then stops the server. Outputs in `adk_runs/<timestamp>/`:
`report.md` (read first) · `results.json` (machine-readable summary) · `transcripts.md` (full conversations incl. tool calls) · `raw/<test>__runN.json` (all events + state) · `server.log` · `agent_schema.json` · `app_info.json`.

Exit codes: 0 pass · 1 failures · 2 infra blocked (key/network/quota/model) · 3 import error or server did not start · 4 bad spec.

## Step 5 - Evaluate (your judgment on top of the numbers)

Read `report.md` and then **skim `transcripts.md`** - passing assertions do not prove good answers. Score the agent 1-5 on each dimension and write the table into `<workspace>/adk_runs/evaluation.md`:

| Dimension | Look for |
|---|---|
| Task success | Does the final answer actually solve the request, using real tool data? |
| Instruction following | Format, tone, scope, refusals as specified |
| Tool use | Right tool, right args, no redundant/looping calls, errors handled |
| Orchestration (multi-agent) | Correct routing, no ping-pong, sub-agent outputs used, state passed |
| Robustness & safety | Out-of-scope, injection, bad input, missing data |
| Efficiency | Latency p50/p95, tokens, tool calls per task |

Verdicts from the script: `PASS` (all MUST tests pass and pass rate >= 0.9), `NEEDS_FIX`, `INFRA_BLOCKED`. You may only call the agent "done" when the script says PASS **and** your qualitative scores are >= 4 on task success, instruction following and tool use. If `INFRA_BLOCKED`, do not "fix" the agent; fix the environment (see Step 1 note) or report honestly that behaviour is unverified.

Optional deeper evaluation with ADK's own tooling (needs a real key): `--export-evalset` writes `<app>/evals/generated.evalset.json`; run `adk eval <app> <that file>`; criteria such as `rubric_based_final_response_quality_v1`, `hallucinations_v1`, `safety_v1` and `adk optimize` are described in `references/evaluation.md`.

## Step 6 - Fix and iterate (max 5 rounds)

For each failure use the `failure_class` and the hint in `report.md`; the full table is in `references/evaluation.md`. Summary:

| Failure class | Typical fix |
|---|---|
| `AUTH_INVALID_KEY`, `INFRA_NETWORK`, `QUOTA_OR_RATE_LIMIT`, `MODEL_NOT_FOUND` | Environment, not code: real key in `.env`, connectivity, retry later, correct model id |
| `AGENT_RUNTIME_ERROR` | Read `server.log` and the raw event error; fix the exception, schema or missing state key |
| `ASSERTION_FAILED` - tool not called | Sharpen tool docstring + instruction ("use `x` whenever ...") |
| `ASSERTION_FAILED` - wrong/missing sub-agent | Make `description`s mutually exclusive; tell coordinator when to route; or switch to a fixed workflow |
| `ASSERTION_FAILED` - content | Check whether the tool result reached the answer; adjust instruction/output_key/templating |
| `SPEC_INPUT_INVALID` | Your test input does not match `input_schema` - fix the spec, not the agent |
| Flaky | Lower temperature (`generate_content_config`), make the instruction more explicit, or make the process deterministic with a graph workflow |

Change one thing at a time, re-run the **whole** suite (regressions!), and log each round (what failed, what you changed, new score) in `evaluation.md`. If after 5 rounds MUST tests still fail, stop and report the remaining failures, your diagnosis and options - do not weaken tests to force a pass (only change a test if it was wrong, and say so).

## Step 7 - Deliver

Give the user: what was built (architecture in 3-5 lines), file list, how to run (`cd <workspace> && source .venv/bin/activate && adk web .` - note `adk web` is for development only), the final verdict with pass counts, latency numbers, remaining known gaps, and the key reminder if a placeholder key is still in `.env`. Do not claim live-model behaviour was verified when the verdict was `INFRA_BLOCKED`.
