# Google ADK Agent Builder & Engineering Suite (`v2.1.0`)

A complete, modular, production-oriented **Google Agent Development Kit (ADK 2.x)** creation, validation, testing, quota-paced evaluation, self-repair, and deployment engineering suite.

## Dual-Layer Architecture

1. **Layer A — Coding-Agent Skill (`SKILL.md` + `adk-agent-builder/` + `references/` + `assets/`)**:
   - Progressive-disclosure instructions and verified ADK v2.12 patterns teaching coding agents how to gather requirements, choose the simplest viable architecture, scaffold apps, run offline and paced live evaluations, diagnose failures, and enforce security boundaries.
   - Packaged into a clean, installable `.skill` archive (`adk-agent-builder/dist/adk-agent-builder.skill`).
2. **Layer B — Python Engineering Toolkit (`src/adk_agent_builder/` + `scripts/`)**:
   - **18-Command CLI (`adk-agent-builder`)**: `doctor`, `audit`, `init`, `requirements`, `plan`, `build`, `validate`, `test`, `eval`, `quota`, `dashboard`, `report`, `package`, `deploy`, `smoke-test`, `status`, `integrations`, and `skills`.
   - **6 Zero-Dependency Standalone Scripts (`scripts/`)**:
     - `scripts/create_agent.py`: Unattended `venv` + `pip install google-adk[db,mcp]` + `adk create` (flags only, no interactive menus) + smoke import + JSON report.
     - `scripts/testing.py`: Introspects app, starts `adk api_server`, runs multi-turn `spec.json` over HTTP (`POST /run`) with `--min-interval` and `--retry-infra`, reclassifies server-log `429`/`503` quota errors, and writes `results.json` + `report.md`.
     - `scripts/dashboard.py`: Renders `results.json` into a single self-contained dark-mode HTML dashboard (zero external CDN dependencies).
     - `scripts/deploy_agent.py`: Wraps `adk deploy` (`cloud_run`, `agent_engine`, `docker`, `gke`) with preflight checks, `.env` live-secret staging audit, `--dry-run`, and JSON deployment report.
     - `scripts/quick_validate.py` & `scripts/package_skill.py`: Strict `SKILL.md` frontmatter, kebab-case naming, and doc-path validator plus `.skill` packager.
   - **Reference Application (`Apex-HyperStore-Agent/`)**: Complete multi-agent ADK reference implementation (`apex_concierge` coordinator + `orders_agent`, `support_agent`, `service_request_agent`, parameterized SQLite database, 99-check offline evaluation suite `offline_eval.py`, and quota-paced runner `run_paced_suite.py`).

## Installation

```bash
# Install the core toolkit in editable mode
pip install -e .

# Or run directly from source without installation
PYTHONPATH=src python3 -m adk_agent_builder.cli --help
```

## Quickstart: Complete Lifecycle

```bash
# 1. Inspect runtime readiness, ADK/Agents CLI bridges, and 11 templates
PYTHONPATH=src python3 -m adk_agent_builder.cli doctor --json

# 2. Parse natural-language requirements into a validated specification
PYTHONPATH=src python3 -m adk_agent_builder.cli requirements \
  --from-text "Build a sequential order lookup and policy compliance ADK agent" \
  --name order_compliance_agent \
  --output requirements.yaml

# 3. Generate architecture trade-off scorecard and plan
PYTHONPATH=src python3 -m adk_agent_builder.cli plan \
  --spec requirements.yaml \
  --output plan.json

# 4. Scaffold project, run static AST + security checks, unit tests, evals, and bounded self-repair
PYTHONPATH=src python3 -m adk_agent_builder.cli build \
  --spec requirements.yaml \
  --output-dir ./generated_agents/order_compliance_agent \
  --repair \
  --json

# 5. Plan live evaluation slices within a 20-messages/day free-tier API budget
PYTHONPATH=src python3 -m adk_agent_builder.cli quota \
  --spec Apex-HyperStore-Agent/adk_runs/spec.json \
  --daily-limit 20 \
  --rpm-limit 5 \
  --json

# 6. Render a standalone HTML evaluation dashboard
PYTHONPATH=src python3 -m adk_agent_builder.cli dashboard \
  --input Apex-HyperStore-Agent/adk_runs/final/results.json \
  --output apex_dashboard.html
```

## Running the Test Suites (0 API Calls Required)

```bash
# 1. Core Python package test suite (unit, integration, contract, security, eval, e2e journey)
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 2. Standalone script & skill packaging test suite (38 tests)
python3 adk-agent-builder/tests/test_offline.py

# 3. Reference multi-agent app offline evaluation (99 checks) & runner logic (23 checks)
python3 Apex-HyperStore-Agent/offline_eval.py
python3 Apex-HyperStore-Agent/test_runner_logic.py
```

## Documentation Index

- [`docs/audit.md`](docs/audit.md) — Reconnaissance audit, discovered defects across both archives, and baseline vs post-remediation results.
- [`docs/architecture.md`](docs/architecture.md) — System architecture, module boundaries, and 17-stage lifecycle diagram.
- [`docs/feature-matrix.md`](docs/feature-matrix.md) — Evidence-backed ADK v2.12 feature and compatibility matrix with official source links.
- [`docs/cli-reference.md`](docs/cli-reference.md) — Complete reference for all 18 `adk-agent-builder` CLI commands and 6 standalone scripts.
- [`docs/user-guide.md`](docs/user-guide.md) — End-to-end guide from natural-language requirements to deployed agent.
- [`docs/workflows-and-integrations.md`](docs/workflows-and-integrations.md) — Multi-agent workflows, ADK 2.0 `Workflow` graphs, `MCPToolset`, and custom tools.
- [`docs/testing-and-evaluation.md`](docs/testing-and-evaluation.md) — Offline testing, ADK `.evalset.json`, HTTP `spec.json`, 20-messages/day quota pacing, and bounded self-repair.
- [`docs/security.md`](docs/security.md) — Secret scanning, `.env` staging audit, prompt-injection guardrails, and least-privilege IAM.
- [`docs/deployment.md`](docs/deployment.md) — Local, Docker, Cloud Run, Vertex AI Agent Runtime (`agent_engine`), and GKE deployment guide.
- [`docs/skills-guide.md`](docs/skills-guide.md) — Authoring, validating, and packaging Agent Skills (`SKILL.md` and `.skill` archives).
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — Diagnostic codes, common ADK 2.12 pitfalls, and remediation recipes.
