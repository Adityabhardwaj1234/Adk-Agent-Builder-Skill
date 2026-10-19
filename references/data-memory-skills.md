# Data, sessions, memory, skills, MCP, guardrails (ADK 2.x, Python)

Read this when the agent must remember anything between messages, store or fetch
data, use long-term memory, expose documents to the model, call MCP servers, or
enforce rules the prompt alone cannot guarantee.

Verified against `google-adk 2.12.0` (imports checked against the installed
package). Where a feature is version-sensitive the note says so.

## Contents
1. Session state in one page
2. Session services (memory, SQLite, Postgres, Vertex)
3. Databases behind tools (the pattern that works)
4. Long-term memory
5. ADK Skills (SKILL.md folders the agent can load)
6. MCP servers as toolsets
7. Compaction, caching and context budget
8. Plugins and callbacks (guardrails that do not depend on the prompt)
9. Secrets: where they live and where they must not

---

## 1. Session state in one page

Every conversation is a *session* with a `state` dict. That dict is the only
place sub-agents, tools and callbacks can reliably exchange data.

| Prefix | Lifetime | Use for |
|---|---|---|
| (none) `key` | the session | task data the whole conversation shares |
| `temp:key` | one invocation | scratch values; never persisted |
| `user:key` | across sessions of one user | preferences, contact details |
| `app:key` | across all users of the app | shared config |

Writing state:
- `Agent(output_key="draft")` - the agent's final text lands in `state["draft"]`.
- Inside a tool: `tool_context.state["k"] = v`.
- Client-side per turn: the `/run` body accepts `stateDelta` (the test harness
  uses this via `turns[].state_delta`).

Reading state:
- In an instruction: `{key}` (raises the model's attention) and `{key?}` when
  the key may legitimately be absent - use the `?` form everywhere a value is
  not guaranteed, otherwise a missing key can break the turn.
- In code: `tool_context.state.get("key")`, `callback_context.state[...]`.

Rules that prevent most state bugs:
- Keys written by one agent and read by another must be produced *earlier* in
  the same conversation, or marked optional.
- Parallel branches must write **different** keys; two writers on one key is a
  race you will debug for an hour.
- Keep keys flat and prefixed by purpose (`order:last_id`) rather than nesting
  large objects the model has to re-read every turn.

## 2. Session services

```python
from google.adk.sessions import InMemorySessionService          # dev/tests only
from google.adk.sessions import DatabaseSessionService          # SQLite / Postgres
```

| Service | When | Notes |
|---|---|---|
| `InMemorySessionService` | tests, demos | state dies with the process; the API server default unless told otherwise |
| `DatabaseSessionService` | anything that must survive a restart | needs `pip install "google-adk[db]"` and an **async** driver URL |
| `VertexAiSessionService` | production on Google Cloud | managed sessions; pairs with Vertex agent deployments |

Async driver URLs (the synchronous ones fail at runtime - this is the single
most common setup mistake):

```
sqlite+aiosqlite:///./data/sessions.db
postgresql+asyncpg://user:pass@host:5432/dbname
```

The CLI wires this with `adk api_server --session_service_uri "sqlite+aiosqlite:///..."`.
The test harness starts the server with a SQLite URI automatically, so every
test runs against a real database instead of process memory.

## 3. Databases behind tools (the pattern that works)

Let the **model never write to the database directly**. The model hands values
to a tool; the tool validates them and only then touches storage. This turns
"please remember to ask for an email" from a prompt aspiration into a guarantee,
and it is why deterministic offline checks can prove the groundwork without a
model (see `assets/sqlite_tools.py` for the full pattern):

- one small function per operation (`lookup_order`, `create_request`) with
  type hints and a docstring the model reads as the tool description
- validate every input with a Pydantic model *before* writing anything
- parameterised SQL only - string-built SQL is both an injection hole and a
  source of quoting bugs the model cannot see
- return a `dict` with a `"status"` key (`"success"` / `"error"`) plus a
  human-readable error message; the model can act on a returned error but
  cannot act on an exception it never sees
- open the connection per call (cheap for SQLite; use a pool for Postgres) and
  never hold transactions across tool calls
- keep the DSN in `.env`; read it with `os.environ.get("DATABASE_URL")`

## 4. Long-term memory

Sessions remember a conversation; *memory* remembers a user across
conversations.

```python
from google.adk.memory import InMemoryMemoryService          # dev
from google.adk.memory import VertexAiMemoryBankService      # production
# google-adk also ships SqliteMemoryService and VertexAiRagMemoryService

from google.adk.tools import load_memory                     # agent-callable tool
from google.adk.tools import preload_memory                  # auto-inject relevant memories
```

Wiring that works:
- give the agent `tools=[load_memory]` for explicit recall, or
  `preload_memory` to inject relevant memories into the prompt each turn;
- ingest finished sessions (`add_session_to_memory` on the runner/context, or
  the memory service API) or nothing is ever retrievable;
- `InMemoryMemoryService` for tests; a persistent service only after the app
  works, because memory changes model behaviour in ways tests must re-verify.

Testable expectations: `tool_calls_include: ["load_memory"]` or `state_keys`
after a second session - memory is hard to assert on text, so assert on the
mechanism.

## 5. ADK Skills (SKILL.md folders the agent can load)

ADK 2.x natively supports *skills*: folders with a `SKILL.md` (name,
description, instructions) plus optional resources and scripts - the same
progressive-disclosure format used by agent skill ecosystems.

```python
from google.adk.skills import load_skills_from_dir      # returns [Skill, ...]
from google.adk.tools.skill_toolset import SkillToolset

skills = load_skills_from_dir("skills")                  # one folder per skill
root_agent = Agent(
    name="root_agent", model="gemini-flash-latest", instruction="...",
    tools=[SkillToolset(skills=skills)],
)
```

`SkillToolset` exposes discovery/loading to the model (list, search, load,
unload, load-resource, run-script) with lazy discovery by default, so skill
bodies only enter the context once they are actually needed. Scripts run
through a code executor; generated files can be saved as artifacts
(`save_output_artifacts=True`).

When to reach for ADK Skills: the agent needs domain instructions or documents
that are too large to paste into its own prompt, or a library of procedures it
picks between at runtime. For two short procedures, plain tools and a longer
instruction are simpler and cheaper.

## 6. MCP servers as toolsets

MCP (Model Context Protocol) servers give the agent tools and resources from
outside the process.

```python
from google.adk.tools import McpToolset          # needs  pip install "google-adk[mcp]"
```

Practical rules:
- one `McpToolset` per server; pass an explicit `tool_filter` when a server
  offers dozens of tools;
- stdio servers start a subprocess - keep command paths absolute and test them
  outside the agent first;
- prefer a read-only server for read-only jobs;
- MCP tools are ordinary tools from the model's point of view: assert on them
  in tests exactly like local functions (`tool_calls_include`);
- `McpToolset` supports a confirmation callback for destructive MCP tools -
  enable it rather than trusting the prompt.

## 7. Compaction, caching and context budget

Long conversations eventually exceed the model's window; ADK has first-class
tools for that:

```python
from google.adk.apps.app import App                     # app-level config
from google.adk.agents.context_cache_config import ContextCacheConfig
# EventsCompactionConfig lives with the app/invocation config (google.adk.apps / run_config)
```

- *Compaction* summarises older events so long sessions stay coherent
  (`EventsCompactionConfig` on the app/runner settings).
- *Context caching* (`ContextCacheConfig` on the agent) makes a large, stable
  prefix (instructions + tools) cheaper across turns; it only pays off when the
  prefix is stable, so put volatile data behind state keys instead.
- *Sub-agents with `include_contents='none'`* see only their instruction and
  state - the cheapest way to keep pipeline stages small.
- Before adding caching or compaction, check the actual cost: `testing.py`
  records `tokens_total` per run in `results.json`.

## 8. Plugins and callbacks (guardrails that do not depend on the prompt)

The prompt is a request; callbacks are enforcement.

```python
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
```

- `GlobalInstructionPlugin` puts cross-cutting rules (tone, safety, brand) on
  the `App` once, instead of pasting them into every agent's instruction.
- `before_tool_callback` / `after_tool_callback` on an agent: block tools
  outside an allow-list, log every call, rewrite arguments, or return a canned
  error. This is where "never touch the DB directly" becomes enforceable.
- `before_model_callback`: input screening, rate-limiting, redaction.
- Human confirmation for destructive actions: ADK supports tool-confirmation
  flows (`adk_request_confirmation` events; MCP toolsets have their own
  `require_confirmation` parameter). Use them for anything a user would want
  to approve - deletion, payment, sending external messages.
- Convert callback failures into logged, typed outcomes; never swallow
  exceptions the framework should see (see references/pitfalls.md on broad
  `except Exception:`).

## 9. Secrets: where they live and where they must not

- One `.env` in the app folder for local runs (`GOOGLE_API_KEY`, DB URLs).
  `adk create` writes it and immediately `.gitignore`s it - keep it that way.
- The agent code reads secrets with `os.environ`; it never prints them, never
  echoes them into state, never puts them in instructions.
- Tests must not depend on secret *values*: point them at fixture data, so the
  same suite passes with a placeholder key structure-wise.
- Deployments: pass secrets as deployment env vars or Secret Manager. The
  deploy script in this skill audits `.env` and warns before a secret rides
  along inside staged source (references/deployment.md).
