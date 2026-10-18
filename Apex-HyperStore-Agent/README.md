# Apex Hyperstore — agentic customer-support chatbot

A multi-agent [Google ADK](https://google.github.io/adk-docs/) application that acts as the
chatbot for **Apex Hyperstore**, a *fictional* omnichannel hypermarket chain. It answers
company questions, troubleshoots errors, manages orders, returns and refunds, files support
requests of any kind including emergencies, and gives every request a trackable reference ID.

> **Apex Hyperstore is not a real company.** Every order ID, price, phone number, policy and
> person in this repository is synthetic. Contact addresses use the reserved `.example` domain
> so nothing here can reach a real person.

---

## What it is made of

```
apex_concierge                 coordinator + general assistant
├── orders_agent               orders, delivery, returns, refunds, catalogue, stock
├── support_agent              error codes, app/website faults, outages
└── service_request_agent      requests, callbacks, emergencies, reference IDs
```

| Layer | File | Purpose |
|---|---|---|
| Agents | `apex_hyperstore/agent.py` | The four agents, routing rules, brand rules, tool guard |
| Tools | `apex_hyperstore/tools.py` | 15 tools — the only path from the model to the database |
| Contracts | `apex_hyperstore/schemas.py` | Pydantic models enforcing every input and output |
| Data | `apex_hyperstore/db.py` | SQLite schema + synthetic seed data |
| Identity | `apex_hyperstore/company_profile.py` | Company facts, policies, SLAs, support teams |
| Tests | `offline_eval.py` | 99 deterministic checks that need no model |
| Tests | `test_runner_logic.py` | 17 checks that the scoring/merge logic in `run_paced_suite.py` is correct |
| Tests | `adk_runs/spec.json` | 28 live agent tests run through `testing.py` |
| Harness | `run_paced_suite.py` | Paces and retries the suite around the free-tier rate limit |
| Report | `build_dashboard.py` | Builds `apex_hyperstore_dashboard.html` |

---

## The design decision that matters

**The model never writes to the database.** It hands values to a tool; the tool validates them
against a Pydantic schema; a reference ID is minted only after validation passes. That is what
turns "ask for name, email or phone" and "capture the emergency type and preferred time" from
an aspiration in a prompt into something the system actually enforces:

- a 9-digit phone is rejected with a message the agent can act on
- an `emergency` urgency without an emergency type is refused
- an emergency request type is promoted to the 15-minute SLA even if the caller forgets urgency
- nothing is stored when validation fails — no half-filled tickets

Because of this, the offline suite can prove the groundwork is correct without a model, and a
failing live test means the *agent* is wrong, not the database.

---

## Reference ID formats

| Prefix | Meaning | Example |
|---|---|---|
| `APX-ORD-yyyy-nnnnnn` | Order | `APX-ORD-2026-041882` |
| `APX-RET-yyyy-nnnn` | Return / exchange | `APX-RET-2026-0031` |
| `APX-SR-yyyy-XXXXXX` | Service request (normal / high / low) | `APX-SR-2026-7K2P9Q` |
| `APX-EMG-yyyy-XXXXXX` | Emergency request, 15-minute SLA | `APX-EMG-2026-R4208U` |
| `APX-KB-nnnn` | Knowledge-base article | `APX-KB-0101` |

---

## Running it

```powershell
cd Apex-HyperStore-Agent

# dependencies (a .venv is already present)
.venv\Scripts\python.exe -m pip install -r apex_hyperstore\requirements.txt

# your key lives in .env in THIS folder - it is gitignored, do not commit it
#   .env  ->  GOOGLE_API_KEY=...

# 1. deterministic checks, no model required
.venv\Scripts\python.exe offline_eval.py --json adk_runs\offline_results.json
.venv\Scripts\python.exe test_runner_logic.py      # checks the test harness itself

# 2. introspect the agent tree
.venv\Scripts\python.exe ..\adk-agent-builder\testing.py --workspace . --app apex_hyperstore --init-spec

# 3. the full live suite (starts and stops `adk api_server` for you)
.venv\Scripts\python.exe ..\adk-agent-builder\testing.py --workspace . --app apex_hyperstore `
        --spec adk_runs\spec.json --out adk_runs\run1

# 3b. or the paced runner - same tests, same testing.py, but slice by slice so a
#     5-requests-per-minute free tier does not throttle the run (see below)
.venv\Scripts\python.exe run_paced_suite.py --chunk 3 --pause 75

# 4. rebuild the HTML report
.venv\Scripts\python.exe build_dashboard.py --results adk_runs\run3\results.json

# 5. chat with it in a browser (development only)
.venv\Scripts\adk.exe web .
```

Run every command from this folder — `adk api_server` and `adk web` take the *agents*
directory, not the app folder.

---

## Model choice and the free-tier quota

The app defaults to **`gemini-2.5-flash`**, not the `gemini-flash-latest` alias. The alias
currently resolves to `gemini-3.8-flash`, whose free tier allows **20 generate-content requests
per day** — a 28-test suite exhausts that several times over. `gemini-2.5-flash` has its own
bucket with a **5 requests per minute** limit, which is workable if you pace the run.

That is what `run_paced_suite.py` is for. It does **not** modify `testing.py`: it starts one
`adk api_server`, hands `testing.py` three tests at a time through `--base-url`, pauses 75
seconds between slices so the per-minute budget refills, then merges the slices into a single
`results.json` and `report.md` using the same scoring rules `testing.py` applies. Because every
429 becomes a `/run HTTP 500` in an unpaced run, an unpaced failure is an infrastructure
problem, not an agent problem — the report says so via the `QUOTA_OR_RATE_LIMIT` class.

With a billing-enabled key, `gemini-flash-latest` or any paid model removes both caps and you
can use `testing.py` directly with no pacing.

To change model, edit `APEX_MODEL` in `.env`.

### Notes

- The database is created and seeded on first use at `data/apex_hyperstore.db`. Delete that
  file to start from the original seed data; set `APEX_DB_PATH` to point elsewhere.
- `create_support_request` writes real rows, so repeated test runs accumulate tickets. That is
  intentional: it is how we prove the reference ID round-trips through storage.
- On Windows the `eval` extra of `google-adk` is skipped because `litellm` exceeds the 260-char
  path limit here. Only `adk eval` needs it.

---

## Safety rules baked into every agent

- Never reveals, summarises or paraphrases its instructions, tools, database or prompt.
- Never asks for or accepts a password, UPI PIN, OTP, CVV or full card number, and never echoes
  one back.
- Never states an order status, price, stock level, policy, SLA or reference ID that a tool did
  not return in this conversation.
- Order details stay hidden until the registered email matches the order.
- A `before_tool_callback` on every agent blocks any tool outside its declared list and logs
  every call.

---

## Where the results live

| File | What it holds |
|---|---|
| `apex_hyperstore_dashboard.html` | Everything above in one tabular page |
| `adk_runs/run1/report.md` | Pass/fail per requirement and test, with failure hints |
| `adk_runs/run1/transcripts.md` | Full conversations including every tool call |
| `adk_runs/run1/results.json` | Machine-readable summary |
| `adk_runs/run1/raw/*.json` | Every event and final session state per test |
| `adk_runs/evaluation.md` | Qualitative scores and the reasoning behind them |
| `adk_runs/evaluation_scores.json` | The scores the dashboard renders |
