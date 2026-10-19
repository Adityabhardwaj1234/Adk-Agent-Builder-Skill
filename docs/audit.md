# Repository Audit & Reconnaissance Report (`docs/audit.md`)

## 1. Reconnaissance Summary Across Uploaded Archives

Two repository variants were inspected and synthesized into a unified Agent Engineering Suite:

1. **Archive 1 (`Adk-Agent-Builder-Skill-1.zip`)**: Git repository (`main` branch, commit `e889a85`) containing:
   - `adk-agent-builder/`: Standalone script-based skill (`SKILL.md`, `scripts/create_agent.py`, `scripts/testing.py`, `scripts/dashboard.py`, `scripts/deploy_agent.py`, `scripts/quick_validate.py`, `scripts/package_skill.py`, `references/*.md`, `assets/*.py`, `tests/test_offline.py`).
   - `Apex-HyperStore-Agent/`: Full multi-agent customer-support reference application (`apex_hyperstore/agent.py`, `tools.py`, `schemas.py`, `db.py`, `offline_eval.py`, `run_paced_suite.py`, `consolidate.py`, `test_runner_logic.py`, and recorded `adk_runs/`).
   - `skill-creator/`: Skill evaluation viewer, benchmark aggregator, and description optimizer.
2. **Archive 2 (`Adk-Agent-Builder-Skill.zip`)**: Installable Python engineering package (`pyproject.toml`, `src/adk_agent_builder/`) providing a 17-stage lifecycle engine, Pydantic domain models, AST/security validation, bounded self-repair, ADK `.evalset.json` evaluation, observability, deployment adapters, and a 13-step end-to-end acceptance test suite.

## 2. Specific Problems & Defects Found (with File Paths)

| # | File Path | Defect Identified | Remediation Applied |
|---|---|---|---|
| 1 | `Apex-HyperStore-Agent/apex_hyperstore/agent.py` & `__init__.py` | Unconditional `from google.adk.agents import Agent` and `from dotenv import load_dotenv` caused `offline_eval.py` to crash with `ModuleNotFoundError: No module named 'google.adk'` when run in offline CI environments | Added graceful dataclass fallback shim in `apex_hyperstore/agent.py` when `google-adk` or `python-dotenv` is not installed |
| 2 | `Apex-HyperStore-Agent/apex_hyperstore/schemas.py` & `adk-agent-builder/assets/sqlite_tools.py` | Used Pydantic v2-only `field_validator`, `.model_dump()`, and `Field(pattern=...)`, failing on Pydantic v1 (`1.10.4`) environments | Implemented transparent Pydantic v1/v2 compatibility layer (`field_validator` / `validator`, `model_dump` / `dict`) |
| 3 | `Apex-HyperStore-Agent/apex_hyperstore/db.py` & `assets/sqlite_tools.py` | Unconditional `PRAGMA journal_mode=WAL` failed with `sqlite3.OperationalError: disk I/O error` on virtualized/containerized filesystems (such as gVisor mounts) | Wrapped `PRAGMA journal_mode=WAL` with fallback to `MEMORY` journal mode and `tempfile.gettempdir()` database path |
| 4 | `Apex-HyperStore-Agent/offline_eval.py` | Line 161 hardcoded `scheduled_for="2026-10-18 11:00"`, causing `create_support_request` to reject the slot as `"in the past"` on dates after October 18, 2026 | Replaced hardcoded date string with dynamic `(schemas.now_ist() + timedelta(days=1)).strftime("%Y-%m-%d") + " 11:00"` |
| 5 | `Apex-HyperStore-Agent/run_paced_suite.py` | (a) Line 42 pointed `TESTING` to non-existent `adk-agent-builder/testing.py` instead of `adk-agent-builder/scripts/testing.py`; (b) Lines 43–44 hardcoded Windows `.venv/Scripts/*.exe` paths; (c) `is_infra_failure` was defined twice (lines 53 and 93), with the second definition dropping `rec.get("_throttled", False)` | Fixed `TESTING` path resolution, added cross-platform POSIX/Windows binary lookup, removed duplicate `is_infra_failure`, and added `--daily-quota-limit 20` enforcement |
| 6 | `adk-agent-builder/assets/__pycache__/*.pyc` & `Apex-HyperStore-Agent/apex_hyperstore/.adk/session.db` | Compiled Python 3.12 bytecode and binary SQLite session DB were tracked in the archive | Removed binary caches/DBs and updated packaging exclusions |
| 7 | `README.md` (in Archive 1) | Contained raw conversational chat text (`"Done. The skill is now a complete..."`) rather than engineering documentation | Replaced with full architecture, installation, CLI, script, and quickstart documentation |

## 3. Baseline vs Post-Remediation Verification

| Check Suite | Command | Baseline (Before Fixes) | Post-Remediation |
|---|---|---|---|
| **Toolkit Test Suite (`tests/`)** | `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 30 passed (Archive 2 only) | **32 passed, 0 failed, 0 skipped** |
| **Standalone Script Tests (`adk-agent-builder/tests/`)** | `python3 adk-agent-builder/tests/test_offline.py` | 36 passed, 2 skipped | **37 passed, 2 skipped (live-ADK opt-in)** |
| **Apex Offline Evaluation (`Apex-HyperStore-Agent/`)** | `python3 Apex-HyperStore-Agent/offline_eval.py` | **CRASHED** (`ModuleNotFoundError` / `OperationalError` / past date) | **99/99 checks passed (100.0%)** |
| **Apex Paced Runner Logic (`Apex-HyperStore-Agent/`)** | `python3 Apex-HyperStore-Agent/test_runner_logic.py` | 23/23 passed | **23/23 checks passed (100.0%)** |
| **Strict Skill Validation (Root & Sub-Skill)** | `PYTHONPATH=src python3 -m adk_agent_builder.cli skills --strict` | Separate unmerged skills | **Both `valid: true`, 0 errors, 0 warnings** |
