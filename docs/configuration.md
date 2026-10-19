# Configuration, Security, Testing, Deployment & Troubleshooting Reference

## 1. Configuration (`docs/configuration.md`)

`BuilderConfig` (`src/adk_agent_builder/config.py`) loads settings in priority order: explicit CLI overrides > environment variables > YAML config file > defaults.

- `ADK_BUILDER_PROVIDER`: Default model provider (`gemini`, `vertex_ai`, `gemma`, `anthropic`, `openai`, `litellm`, `ollama`, `vllm`).
- `ADK_BUILDER_MODEL`: Default model identifier (e.g., `gemini-2.5-flash`).
- `ADK_MAX_LLM_CALLS`: Maximum LLM calls per invocation (default `20`, enforcing strict API quota protection).
- `ADK_EXPERIMENTAL_TELEMETRY`: Enable experimental per-workflow token/call OTel metrics (`true` / `false`).
- `ADK_ENABLE_SKILL_LIFECYCLE`: Enable experimental ADK v2.10.0 skill lifecycle caps (`1` / `0`).

## 2. Security Baseline (`docs/security.md`)

- **Credential Isolation**: Credentials are checked by variable presence (`check_credentials_present`) and never logged or written to generated files.
- **Automatic Log Redaction**: `RedactingJsonFormatter` and `redact_sensitive_text` (`src/adk_agent_builder/logging.py`) scrub `AIza*`, `AQ.*`, `sk-*`, `ghp_*`, `ya29.*`, and `Bearer` tokens.
- **Static Security Scanning**: `SecurityScanner.scan_project` detects hardcoded keys, `eval()`, `exec()`, `pickle.loads()`, `yaml.load()`, and `subprocess(..., shell=True)`.
- **Runtime Callbacks**: `GovernanceRuntime` (`src/adk_agent_builder/security/governance.py`) provides `before_model_callback` prompt-injection blocking, `before_tool_callback` allowlist and human-confirmation gates (`RequestInput`), and `after_tool_callback` secret sanitization (ADK v2.12.0).
