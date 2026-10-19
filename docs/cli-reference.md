# CLI & Standalone Scripts Reference (`docs/cli-reference.md`)

The suite provides both the unified `adk-agent-builder` CLI (`python3 -m adk_agent_builder.cli`) and 6 zero-dependency standalone scripts in `scripts/`.

## 1. Unified CLI Commands (`adk-agent-builder`)

All commands support `--json` for machine-readable output and return deterministic exit codes (`0` success, `2` invalid arguments, `3` requirements error, `4` validation failed, `5` test failed, `6` evaluation failed, `7` security violation, `8` deployment blocked, `9` self-repair exhausted).

| Command | Purpose | Example |
|---|---|---|
| `doctor` | Inspect Python runtime, `adk`/`agents-cli` availability, providers, integrations, and templates | `adk-agent-builder doctor --json` |
| `audit` | Run AST validation, secret scanning, and skill validation on a directory | `adk-agent-builder audit --project-dir . --json` |
| `init` | Create a starter `requirements.yaml` specification | `adk-agent-builder init --name my_agent --output requirements.yaml` |
| `requirements` | Normalize YAML/JSON or natural-language requirements and detect contradictions | `adk-agent-builder requirements --from-text "Build a RAG agent" --name rag_bot` |
| `plan` | Score 11 ADK architectures and select the simplest viable pattern | `adk-agent-builder plan --spec requirements.yaml --output plan.json` |
| `build` | Generate runnable ADK project and execute all quality gates (with optional `--repair`) | `adk-agent-builder build --spec requirements.yaml --output-dir ./out --repair` |
| `validate` | Run static AST, entrypoint, schema, callback, and security checks (with optional `--repair`) | `adk-agent-builder validate --project-dir ./out --repair` |
| `test` | Discover and execute unit, integration, and contract tests | `adk-agent-builder test --project-dir ./out` |
| `eval` | Execute ADK `.evalset.json` datasets and compute trajectory, ROUGE-1, hallucination, and safety scores | `adk-agent-builder eval --project-dir ./out --output eval_report.json` |
| `quota` | Estimate live LLM message cost and generate a 20-messages/day & 5-RPM safe slice plan | `adk-agent-builder quota --spec spec.json --daily-limit 20 --rpm-limit 5 --json` |
| `dashboard` | Render a standalone dark-mode HTML dashboard from `results.json` or `eval_report.json` | `adk-agent-builder dashboard --input eval_report.json --output dashboard.html` |
| `report` | Generate a complete 17-stage lifecycle, validation, security, and diagnostic report | `adk-agent-builder report --project-dir ./out --output lifecycle_report.json` |
| `package` | Validate and package an ADK project into a clean `.zip` archive (excluding `.env`, DBs, caches) | `adk-agent-builder package --project-dir ./out` |
| `deploy` | Audit `.env` secrets, check cloud prerequisites, and generate/execute deployment plans | `adk-agent-builder deploy --project-dir ./out --target cloud_run --dry-run` |
| `smoke-test` | Run health check and synchronous invocation smoke test against a project | `adk-agent-builder smoke-test --project-dir ./out` |
| `status` | Inspect saved 17-stage lifecycle state (`.adk_builder_state/lifecycle_state.json`) | `adk-agent-builder status --project-dir ./out --json` |
| `integrations` | List and health-check all 12 ADK integrations, 8 model providers, and 11 templates | `adk-agent-builder integrations --json` |
| `skills` | Validate `SKILL.md` frontmatter and doc references (`--strict`) or package a `.skill` archive (`--package`) | `adk-agent-builder skills --skill-dir ./adk-agent-builder --strict --package` |

## 2. Standalone Scripts (`scripts/`)

| Script | Usage | Exit Codes |
|---|---|---|
| `scripts/create_agent.py` | `python3 scripts/create_agent.py <app_name> --workspace ./ws [--api-key KEY] [--model gemini-2.5-flash]` | `0` ok, `2` usage, `3` env failure, `4` folder exists |
| `scripts/testing.py` | `python3 scripts/testing.py --workspace ./ws --app <app> --spec spec.json --min-interval 13 --retry-infra 2` | `0` MUST pass, `1` test fail, `2` infra/quota blocked, `3` import/server fail, `4` bad spec |
| `scripts/dashboard.py` | `python3 scripts/dashboard.py --results results.json [--evaluation eval.md] [--out dashboard.html]` | `0` written, `2` input error |
| `scripts/deploy_agent.py` | `python3 scripts/deploy_agent.py ./ws/<app> --mode cloud_run --project P --region R --dry-run` | `0` ok/dry-run, `1` deploy fail, `2` usage, `3` preflight fail |
| `scripts/quick_validate.py` | `python3 scripts/quick_validate.py ./adk-agent-builder [--strict]` | `0` valid, `1` invalid |
| `scripts/package_skill.py` | `python3 scripts/package_skill.py ./adk-agent-builder ./dist [--dry-run]` | `0` packaged, `1` validation/package error |
