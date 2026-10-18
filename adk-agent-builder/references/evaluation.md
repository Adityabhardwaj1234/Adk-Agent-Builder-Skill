# Evaluation: requirements, specs, scoring, and the failure -> fix table

Read this before writing tests, and again when interpreting a failing run.
`scripts/testing.py` implements everything described here; this document is the
contract it follows.

## Contents
1. From the user's request to testable requirements
2. The spec format (`spec.json`) - every field
3. Writing assertions that do not flake
4. Run parameters: repeat, pacing, retries
5. Verdicts, exit codes and what each failure class means
6. The failure -> fix table
7. Optional deeper evaluation with `adk eval`

---

## 1. From the user's request to testable requirements

Turn the request into numbered requirements (`R1..Rn`), each tagged `must` or
`should`, each testable by observable behaviour. Always include the implicit
ones; they are the most common real-world failure:

- the agent handles out-of-scope requests by declining, not improvising
- it resists prompt injection (does not reveal instructions or data)
- it does not leak secrets, other users' data, or unverified "facts"
- structured output actually validates against its schema
- it uses tools for facts instead of answering from model memory
- for multi-agent systems: routing goes to the right specialist, and there is a
  negative test proving a request does *not* reach the wrong one
- for stateful agents: values collected earlier are reused, not asked again

A requirement that cannot fail is not a requirement. "Be helpful" cannot be
tested; "answers store hours from `get_company_info`" can.

## 2. The spec format (`spec.json`)

```jsonc
{
  "requirements": [
    {"id": "R1", "text": "Answers order questions from real order data", "severity": "must"}
  ],
  "tests": [
    {
      "id": "T01_order_status",
      "category": "functional",            // functional|edge|safety|multi_agent|memory|schema|performance
      "severity": "must",                  // must|should
      "requirement_ids": ["R1"],
      "description": "Optional human note",
      "initial_state": {"user:name": "Ada"},          // optional session state before the first turn
      "turns": [
        {"user": "Where is my order A123?"},           // plain text, or a JSON object matching input_schema
        {"user": "...", "state_delta": {"k": "v"}}     // optional per-turn state injection
      ],
      "expect": { /* see below */ }
    }
  ]
}
```

`expect` fields `testing.py` evaluates (all optional; `no_error: true` applies
to every test unless switched off):

| Field | Meaning |
|---|---|
| `no_error` | no runtime errors and no HTTP error in any turn |
| `response_contains` / `response_not_contains` | case-insensitive substrings of the final response |
| `response_regex` | list of regexes (case-insensitive, DOTALL) |
| `min_chars` / `max_chars` | length bounds for the final response |
| `tool_calls_include` / `tool_calls_exclude` | tool names that must / must not be called |
| `tool_calls_in_order` | subsequence of tool calls in this order |
| `tool_args` | `[{"tool": "x", "args_subset": {...}}]` - a call to `x` whose args include the subset |
| `max_tool_calls` | upper bound on tool calls (loop detector) |
| `agents_involved` / `agents_excluded` | (sub-)agents that must appear in authors or transfers |
| `routes_include` | graph workflow route values that must be emitted |
| `state_contains` / `state_keys` | session state values / key presence after the run |
| `json_valid` / `json_schema` | final response parses as JSON / matches a JSON-schema subset |
| `max_latency_s` | total wall-clock latency for the test's turns |

If the root agent has an `input_schema`, every test input should be a JSON
object matching it - `testing.py` validates inputs against the introspected
schema *before* sending and reports `SPEC_INPUT_INVALID` (a spec bug, not an
agent bug) when they do not match.

Building the first draft: `python scripts/testing.py --workspace W --app A
--init-spec` introspects the agent tree and writes a skeleton with one test per
tool and per sub-agent. Replace every `TODO` - the runner refuses specs that
still contain the string `TODO`.

## 3. Writing assertions that do not flake

LLM wording varies; facts do not. Assert on:

- **the mechanism**: which tool was called (`tool_calls_include`), with which
  arguments (`tool_args`), by which agent (`agents_involved`)
- **stored facts**: `state_keys`, `state_contains`, `json_valid`
- **invariants**: `response_not_contains` for forbidden content, regexes for
  format-level facts (an ID pattern, a date shape)

Avoid: exact-phrase assertions on prose, assertions that pass when the model
hallucinates (e.g. checking a figure appears without checking the tool
returned it), and giant omnibus tests - one behaviour per test, so a failure
points at one fix. Cover the categories the skill asks for: `functional`,
`edge`, `safety`, `schema` (if structured I/O), `multi_agent` (routing),
`memory` (multi-turn/state), `performance` (latency/tool budget). At least one
test per requirement and eight tests overall is the working floor.

Flakiness is signal, not noise: run `--repeat 3` for non-deterministic
behaviour; a test that passes some runs is reported as `flaky`. Fix flakiness
by lowering temperature (`generate_content_config`), making instructions
explicit, or replacing probabilistic behaviour with a graph workflow - not by
deleting the test.

## 4. Run parameters: repeat, pacing, retries

```bash
python scripts/testing.py --workspace ws --app my_app --spec ws/adk_runs/spec.json \
    --repeat 2 --min-interval 13 --retry-infra 2 --retry-wait 30
```

- `--min-interval S` - sleep between tests. Free-tier keys allow only a few
  requests per minute; `--min-interval 13` keeps a 5 rpm key under its cap.
- `--retry-infra N` - retry tests that failed for transient reasons
  (`INFRA_NETWORK`, `QUOTA_OR_RATE_LIMIT`) with exponential backoff
  (`--retry-wait * 2^attempt`). Auth and model-name failures are never
  retried: waiting does not fix a wrong key.
- When a failed test spent zero tokens and the server log for its time window
  contains quota markers (429 / RESOURCE_EXHAUSTED / "high demand"), the
  failure is reclassified from `AGENT_RUNTIME_ERROR` to
  `QUOTA_OR_RATE_LIMIT`. This exists because the ADK API server turns
  throttling into a bare `HTTP 500`; without the log check, a rate limit reads
  as an agent bug. With `--base-url`, pass `--server-log PATH` to enable it.

## 5. Verdicts, exit codes and failure classes

Verdicts (in `results.json` -> `summary.verdict`):

| Verdict | Meaning |
|---|---|
| `PASS` | all MUST tests pass and overall pass rate >= `--pass-threshold` (default 0.9) |
| `NEEDS_FIX` | at least one real failure |
| `INFRA_BLOCKED` | **every** failure is infrastructure (key/network/quota/model) - behaviour was not evaluated |

Exit codes: `0` PASS, `1` failures, `2` infra blocked, `3` import/server
failure, `4` bad spec.

Failure classes and what they mean:

| Class | Cause | Whose problem |
|---|---|---|
| `ASSERTION_FAILED` | behaviour ran, expectation did not hold | the agent |
| `AGENT_RUNTIME_ERROR` | exception/error event during the run | the agent |
| `SPEC_INPUT_INVALID` | test input does not match `input_schema` | the spec |
| `AUTH_INVALID_KEY` | key missing, invalid or expired | the environment |
| `INFRA_NETWORK` | DNS/connect/timeout | the environment |
| `QUOTA_OR_RATE_LIMIT` | 429 / daily cap (often surfaced as HTTP 500) | the environment |
| `MODEL_NOT_FOUND` | model id not available to this key/region | the environment |

## 6. The failure -> fix table

| Failure class + check | Typical fix |
|---|---|
| `AUTH_INVALID_KEY`, `INFRA_NETWORK`, `QUOTA_OR_RATE_LIMIT`, `MODEL_NOT_FOUND` | Environment, not code: real key in `.env`, connectivity, pace the run (`--min-interval`, `--retry-infra`), check the model id. Do **not** edit the agent. |
| `AGENT_RUNTIME_ERROR` | Read `server.log` and the raw event error; fix the exception, schema mismatch or missing state key |
| `ASSERTION_FAILED` - `tool_called` | Sharpen the tool docstring and name; state in the instruction when to use it ("use `x` whenever ...") |
| `ASSERTION_FAILED` - `tool_args` | Simplify the signature; add type hints and parameter docs; business rules go in the tool, not the prompt |
| `ASSERTION_FAILED` - `agent_involved` / `agent_excluded` | Make sub-agent `description`s specific and mutually exclusive; say when to route to each; switch to a fixed workflow if routing keeps missing |
| `ASSERTION_FAILED` - `route_taken` | Router output does not match the edge dict keys - check the classifier's output normalization |
| `ASSERTION_FAILED` - `response_contains` | Verify the tool result reached the answer: check `output_key`, `{key}` templating, and the "no facts without tools" rule |
| `ASSERTION_FAILED` - `json_valid` / `json_schema` | Use `output_schema`; if tools exist on the same agent and it still fails, split into a tool agent plus a formatter agent |
| `ASSERTION_FAILED` - `state_` | Write via `output_key` or `tool_context.state`; `temp:` keys do not survive the invocation |
| Flaky | Lower temperature; make the instruction explicit; make the process deterministic (graph workflow / workflow agents) |
| `max_latency_s` / `max_tool_calls` | Faster model, trim instructions/tools, parallelize independent agents, enable context caching, stop loops |

Change one thing at a time and re-run the **whole** suite - a prompt fix that
passes your failing test and breaks two others is how agents regress. Log each
round (what failed, what changed, new score) in `evaluation.md`. After five
rounds with a MUST still failing, stop and report the failure honestly instead
of weakening the test; only change a test when the test itself was wrong, and
say so in the evaluation.

## 7. Optional deeper evaluation with `adk eval`

`testing.py` is self-contained, but ADK ships its own evaluation tooling:

- `--export-evalset` writes `<app>/evals/generated.evalset.json` from passing
  runs; then `adk eval <app> <evalset.json>` replays them through ADK's runner.
- ADK eval criteria include `rubric_based_final_response_quality_v1`,
  `hallucinations_v1` and `safety_v1` - they need a real key and (on Windows)
  the `eval` extra, which pulls `litellm` and can exceed the 260-character path
  limit; see references/pitfalls.md before installing it there.

Treat `adk eval` as a second opinion after `testing.py` says PASS, not as a
replacement: the spec you wrote is the contract, and it is the artifact this
skill optimizes for.
