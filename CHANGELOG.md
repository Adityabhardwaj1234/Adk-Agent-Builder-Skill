# Changelog

All notable changes to the **Google ADK Agent Builder & Engineering Suite** are documented in this file.

## [2.1.0] - 2026-10-19

### Added
- **Unified Dual-Layer Suite**: Combined the installable `adk_agent_builder` Python package (`src/adk_agent_builder/`) with the standalone ADK 2.12 execution scripts (`scripts/create_agent.py`, `scripts/testing.py`, `scripts/dashboard.py`, `scripts/deploy_agent.py`, `scripts/quick_validate.py`, `scripts/package_skill.py`), progressive-disclosure references (`references/`), runnable asset templates (`assets/`), `skill-creator/`, and the `Apex-HyperStore-Agent/` multi-agent reference project.
- **20-Messages/Day Free-Tier Quota Budget Manager (`src/adk_agent_builder/evaluation/quota.py` & `adk-agent-builder quota`)**: Estimates live LLM message costs across both HTTP `spec.json` and ADK `.evalset.json` files, enforces a configurable daily cap (default 20 messages/day per model, 5 RPM, `--min-interval 13`), prioritizes `must`-severity cases into paced slices, supports multi-model rotation (`--rotate-models`), and tracks daily usage in `.adk_quota_ledger.json`.
- **Standalone Dark-Mode HTML Dashboard Renderer (`src/adk_agent_builder/observability/dashboard.py` & `adk-agent-builder dashboard`)**: Renders self-contained HTML reports (inline CSS, zero external CDNs) from both `scripts/testing.py` `results.json` and `adk-agent-builder eval` `EvalReport` JSON files.
- **11th Verified Project Template (`graph_workflow`)**: Added full ADK 2.0 `Workflow` + `Event(route=...)` + `JoinNode` template to `TEMPLATE_CATALOG` and `ArchitecturePlanner`.
- **`.env` Live-Secret Staging Audit in `DeploymentManager`**: Integrated `audit_env_secrets()` into `adk-agent-builder deploy` to warn when live API keys in `.env` would be uploaded into Cloud Run or Agent Runtime containers.
- **`.skill` Archive Packaging in `SkillValidator`**: Added `adk-agent-builder skills --package` and strict doc-reference verification outside markdown code fences.

### Fixed
- Fixed `Apex-HyperStore-Agent/apex_hyperstore/agent.py` hard import crash when `google-adk` or `python-dotenv` is not installed so `offline_eval.py` runs in any environment.
- Fixed Pydantic v1/v2 compatibility across `Apex-HyperStore-Agent/apex_hyperstore/schemas.py` and `assets/sqlite_tools.py`.
- Fixed SQLite `PRAGMA journal_mode=WAL` `disk I/O error` on virtualized filesystems in `Apex-HyperStore-Agent/apex_hyperstore/db.py` and `assets/sqlite_tools.py`.
- Replaced hardcoded `2026-10-18` date in `Apex-HyperStore-Agent/offline_eval.py` with a dynamic future date (`now_ist() + 1 day`).
- Fixed broken `TESTING` script path, Windows-only `.venv/Scripts/*.exe` paths, and duplicate `is_infra_failure` definition in `Apex-HyperStore-Agent/run_paced_suite.py`.

## [2.0.0] - 2026-10-18

### Added
- Initial 17-stage lifecycle toolkit (`src/adk_agent_builder/`), Requirements Engine, Architecture Planner, Static AST/Security Validator, Bounded Self-Repair Engine, and 13-step End-to-End Acceptance Journey test suite.
