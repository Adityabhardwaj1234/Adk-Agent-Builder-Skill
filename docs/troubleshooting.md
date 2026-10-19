# Troubleshooting & Diagnostics Guide (`docs/troubleshooting.md`)

Use `adk-agent-builder report --project-dir <dir> --json` or `adk-agent-builder validate --project-dir <dir> --repair` to diagnose and remediate project issues.

## Diagnostic Reference

- **`VAL_SYNTAX_ERROR`**: Python syntax error in generated or modified `.py` file. Inspect the reported file and line number.
- **`VAL_MISSING_ROOT_AGENT`**: `app/agent.py` is missing a top-level `root_agent` assignment required by `adk web` and `adk eval`. Run `adk-agent-builder validate --repair` to restore `root_agent`.
- **`VAL_DEPRECATED_ADK_IMPORT`**: Project imports deprecated modules (`google.adk.labs.openai`, `vertexai.preview`, or `google.adk.flows.llm_flows.audio_*`). Run `adk-agent-builder validate --repair` to migrate imports automatically.
- **`SEC_HARDCODED_SECRET`**: A live credential pattern (`AIza*`, `AQ.*`, `sk-*`) was detected. Remove from source files, store in environment variables, and rotate the exposed credential.
- **`TST_SUITE_FAILURE` / `EVAL_THRESHOLD_FAILURE`**: Unit tests or evaluation thresholds failed. Run `adk-agent-builder validate --repair` (bounded to 3 attempts) to repair broken tool output contracts and re-verify regression tests.
