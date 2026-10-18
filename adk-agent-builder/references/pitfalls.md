# Pitfalls and gotchas (verified against google-adk 2.12.0)

Every entry here cost real debugging time on real ADK projects. Read it before
building, and again when something behaves oddly. Environment problems and
code problems look identical from the outside; this list is how you tell them
apart quickly.

## Contents
1. Windows-specific
2. Environment and quota
3. Code and orchestration
4. Tests and specs
5. Docs and skill hygiene

---

## 1. Windows-specific

- **The 260-character path limit is real.** `pip install "google-adk[eval]"`
  pulls `litellm` and friends; the resulting nested paths in a deep project
  folder (e.g. under OneDrive) can exceed 260 characters and `pip` fails with
  confusing "No such file or directory" errors deep inside its own temp
  extraction. Consequences: skip the `eval` extra on Windows unless you need
  `adk eval` with rubric criteria, and put workspaces in short paths
  (`C:\ws\my_app`) when installing many extras. `create_agent.py` therefore
  installs `db,mcp` by default, never `all`.
- **`adk api_server --reload` is force-disabled on Windows** (uvicorn's
  reloader needs an asyncio subprocess; the SelectorEventLoop cannot provide
  it). The server runs fine - it just does not auto-restart on file changes.
  Restart it manually after editing agent code. `scripts/testing.py` passes
  `--no-reload` everywhere for a clean process tree.
- **venv layout is `.venv\Scripts\...`, not `.venv/bin/...`.** The scripts in
  this skill resolve this automatically; hand-written commands must too
  (`.\\.venv\\Scripts\\adk.exe`, `.\\.venv\\Scripts\\python.exe`).
- **PowerShell quoting eats arguments.** Prefer `--flag=value` forms
  (`--session_service_uri=sqlite+aiosqlite:///...`) or quote the value for the
  *inner* parser: `--server-arg "'--foo=bar'"`. Single `--flag value` pairs
  with spaces or `=` inside the value are the usual casualties.
- **OneDrive-synced folders** occasionally lock files mid-write (syncing venv
  contents) and make installs slow. It usually works; if a venv misbehaves in
  a synced folder, move the workspace somewhere plain before debugging code.

## 2. Environment and quota

- **Free-tier limits arrive disguised as HTTP 500.** The ADK API server wraps
  model errors into a generic `/run` failure, so an exhausted quota or a 429
  reaches the client as `HTTP 500` with no quota text - easy to misread as an
  agent crash. `testing.py` handles this in two ways: `--min-interval` keeps
  the request rate under the cap, `--retry-infra` retries transient failures,
  and a zero-token failure whose server-log window contains 429 /
  `RESOURCE_EXHAUSTED` markers is reclassified to `QUOTA_OR_RATE_LIMIT`
  instead of `AGENT_RUNTIME_ERROR`. If you see quota-class failures, fix the
  pace - do not edit the agent.
- **Quota is counted per model.** Switching to a "newer" model does not add
  requests per minute; on a free key the per-model daily cap can be as low as
  a couple of dozen requests, so a 28-test suite that ran dry in the morning
  can still fail in the afternoon with a different model. Budget tests per
  day; the free path that worked best used `gemini-2.5-flash` (a workable
  requests-per-minute bucket) with paced runs.
- **`.env` overrides the shell environment (`override=True`).** The CLI walks
  up from the agent folder to the first `.env` and loads it over whatever the
  process already has. A stale placeholder key in `.env` therefore beats a
  correct `$GOOGLE_API_KEY` in your terminal - if auth fails while the shell
  looks right, check `.env` first. (Also: a `.env` in a *parent* folder is
  found by the walk-up, which is how one workspace can accidentally share a
  key across apps.)
- **Telemetry never prompts in automation** - the interactive question only
  appears on a real TTY, and telemetry is off unless consent was recorded
  (`~/.adk/config.json`). For determinism, `create_agent.py` records an
  explicit opt-out with `adk telemetry disable` (non-interactive).
- **App names**: ADK requires `^[a-zA-Z][a-zA-Z0-9_-]*$` and reserves `user`.
  Validate locally (both `create_agent.py` and ADK do) - a bad name otherwise
  wastes a full install cycle.
- **Model ids matter.** `gemini-flash-latest` tracks the newest release and
  may be a model with a tiny daily quota; a pinned id (`gemini-2.5-flash`,
  `gemini-3.5-flash`, `gemini-3.8-flash`) is what you want for repeatable
  test runs. Keep the id that `adk create --model` wrote; the menu ids and the
  flag ids are the same strings.

## 3. Code and orchestration

- **Never wrap tool code in `except Exception:`** (and never touch
  `BaseException`). ADK 2 uses exceptions to retry and to pause/resume
  workflows; a broad catch swallows the signal and turns a recoverable pause
  into a wrong answer. Catch *specific* exceptions, and when you do, return a
  `{"status": "error", ...}` dict the model can act on instead of `None`.
- **`output_schema` does not combine with tools on every model.** When an
  agent that calls tools also declares `output_schema`, some models reject the
  request. The fix is architectural, not a retry: split into a tool-calling
  agent and a formatter agent (or a graph step) that only formats.
- **`temp:` state dies at the end of the invocation.** Values written with a
  `temp:` prefix are gone by the next turn - if a later turn needs them, use
  unprefixed keys. Conversely, realize that unprefixed keys persist for the
  whole session and `user:`/`app:` keys persist beyond it.
- **Two writers, one state key, one race.** Parallel branches (or parallel
  sub-agents) writing the same `output_key` interleave nondeterministically.
  Give each branch its own key and merge explicitly afterwards.
- **`{key}` with a missing key can break the turn**; `{key?}` tolerates
  absence. Use `{key?}` everywhere a producer is not guaranteed to have run.
- **`exit_loop` goes in the loop's *sub-agent* tools**, not on the `LoopAgent`
  itself. And always set `max_iterations` - a loop without a bound is how test
  suites hang.
- **Two agents, one instance**: the same agent object under two parents causes
  duplicate/aliased behaviour; create separate instances (or `.clone()` for
  remote agents).
- **`api_server`'s positional argument is the workspace** (the folder that
  *contains* app folders), not the app folder. Pointing it at the app itself
  produces an empty `list-apps`.
- **SQLite sessions are single-writer.** Two servers (or a server plus a
  stray process) on the same `.db` file produce `database is locked`. The test
  harness starts one server per run on a fresh port and stops it in `finally`.

## 4. Tests and specs

- **Infrastructure failures are not agent failures.** `AUTH_INVALID_KEY`,
  `INFRA_NETWORK`, `QUOTA_OR_RATE_LIMIT` and `MODEL_NOT_FOUND` say nothing
  about the agent's quality; the correct response is to fix the environment
  and re-run, never to edit instructions in response. The runner already
  retries the transient ones and reports `INFRA_BLOCKED` when *all* failures
  are environmental.
- **A placeholder key makes structure testable and behaviour untestable.**
  `YOUR_API_KEY` in `.env` still lets import checks, schema checks and file
  verification pass; live runs will report `INFRA_BLOCKED`. Both outcomes are
  useful - just never call the second one a pass.
- **Spec drift**: after changing an agent's `input_schema`, old test inputs
  become invalid and every test reports `SPEC_INPUT_INVALID`. That is the
  runner protecting you from testing the wrong contract; update the spec with
  the schema change.
- **Tests that still contain `TODO` are refused** - they are skeletons, not
  tests.
- **Flaky is a verdict, not a nuisance.** `--repeat N` exposes
  nondeterminism; fix it (lower temperature, explicit instruction, graph
  workflow) instead of deleting the test. Never lower a test's severity to
  turn a red run green.
- **Assert on mechanisms, not prose.** Exact-phrase checks on model wording
  fail the moment a release changes phrasing; check tool calls, state, regex
  patterns and invariants instead (references/evaluation.md).
- **Changing the agent invalidates the last run.** Any edit to
  `agent.py`/tools/instructions requires re-running the whole suite; fixing
  one red test by breaking two green ones is the standard regression path.

## 5. Docs and skill hygiene

- **The bug this skill's own repository had**: SKILL.md pointing at
  `testing.py` at the skill root after it moved into `scripts/`, and at
  support files that never existed. Every path in a skill's instructions must
  exist in the shipped folder. `scripts/quick_validate.py` now checks every
  `scripts/...`, `references/...`, `assets/...` path mentioned in SKILL.md
  and warns about missing ones; the skill's own test suite fails on that
  warning.
- **Package what runs, not what built it.** Development state (`tests/`,
  `adk_runs/`, `__pycache__`, session databases, `.env`) must never enter a
  `.skill` archive - `scripts/package_skill.py` excludes them by pattern, and
  a packaged archive is inspected by the test suite to prove it.
- **Versions drift.** These references were verified against
  `google-adk 2.12.0`; menu ids, flag names and import paths have changed
  between 1.x and 2.x before. When something in the skill disagrees with the
  installed package, the installed package wins - re-check with the CLI's
  own `--help` and the source under
  `.venv/Lib/site-packages/google/adk/`.
