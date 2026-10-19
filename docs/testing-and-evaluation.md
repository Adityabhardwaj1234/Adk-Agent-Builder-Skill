# Testing, Evaluation, Deployment & Troubleshooting Guides

## 1. Testing & Evaluation (`docs/testing-and-evaluation.md`)

- **Unit, Contract, Security & Integration Tests**: Run via `adk-agent-builder test` (uses `pytest` when installed and automatically falls back to `python3 -m unittest discover`).
- **ADK Evaluation (`adk-agent-builder eval`)**:
  - Validates `.evalset.json` and `.test.json` files against `EvalSet` and `EvalCase` Pydantic models.
  - Rejects empty `eval_cases` with a `ValueError` (matching ADK v2.10.0 `9dbc2ae`).
  - Never marks skipped test cases as passed.
  - Calculates `tool_trajectory_avg_score` (with optional `ignore_args=True`), `response_match_score` (ROUGE-1 F1), `hallucinations_v1`, `safety_v1`, `multi_turn_task_success_v1`, and automatic efficiency metrics (`tool_call_count_v1`, `inference_call_count_v1`, `token_usage_v1`, `invocation_duration_v1`).

## 2. Deployment & Rollback (`docs/deployment.md`)

- **Supported Targets**: `local`, `docker`, `cloud_run`, `agent_runtime` (Vertex AI Agent Engine with `--service_account` support in ADK v2.12.0), and `gke`.
- **Dry-Run Default**: `adk-agent-builder deploy` defaults to `--dry-run` and outputs the exact `adk deploy ...` command, missing environment prerequisites, and rollback command.
- **Explicit Authorization**: Passing `--execute` for `cloud_run`, `agent_runtime`, or `gke` without `--approve-billable` raises `DeploymentBlockedError` (`ExitCode.DEPLOYMENT_BLOCKED = 8`).

## 3. Troubleshooting Playbook (`docs/troubleshooting.md`)

| Diagnostic Code | Stage | Root Cause | Automated / Manual Remediation |
| :--- | :--- | :--- | :--- |
| `VAL_MISSING_ROOT_AGENT` | `static_validation` | `app/agent.py` does not define top-level `root_agent` | Auto-repaired by `adk-agent-builder validate --repair` |
| `VAL_DEPRECATED_ADK_IMPORT` | `static_validation` | Uses `google.adk.labs.openai` or legacy `llm_flows` audio imports | Auto-repaired to `google.adk.integrations.openai` / `google.adk.live` |
| `SEC_HARDCODED_SECRET` | `security_validation` | Plaintext API key (`AIza*`, `AQ.*`, `sk-*`) found in source or `.env` | Auto-redacted by `--repair`; rotate compromised key immediately |
| `TST_SUITE_FAILURE` | `unit_and_integration_tests` | Tool return dictionary violates expected status/summary contract | Auto-repaired for standard tool contract defects or inspect traceback |
| `EVAL_THRESHOLD_FAILURE` | `evaluation` | `tool_trajectory_avg_score` or `response_match_score` below threshold | Align tool call sequence and summary phrasing in `app/tools.py` |
