# Security & Governance Guide (`docs/security.md`)

## Threat Model & Implemented Controls

| Threat Vector | Control Implemented | Module / File |
| :--- | :--- | :--- |
| **Hardcoded API Keys & Tokens** | Regex & key-name redaction (`AIza*`, `AQ.*`, `sk-*`, `Bearer`) + static file scanner | `logging.py`, `security/scanner.py` |
| **Prompt Injection & System Override** | `before_model_guardrail` blocks instruction-override patterns before model invocation | `security/governance.py`, `app/callbacks.py` |
| **Leaked Secrets in Tool Outputs** | `after_tool_sanitizer` (`after_tool_callback`, ADK v2.12.0) scrubs tool responses before returning to LLM | `security/governance.py`, `app/callbacks.py` |
| **Unconfirmed Mutating Tool Calls** | `before_tool_callback` pauses mutating tools with `status="requires_confirmation"` unless `human_confirmed=True` | `security/governance.py` |
| **Arbitrary Code / Shell Injection** | AST scanner flags `eval`, `exec`, `os.system`, `pickle.loads`, `yaml.load`, and `shell=True` | `security/scanner.py` |
| **Path Traversal in Skills & Artifacts** | `SkillValidator` and `IsolatedArtifactService` reject `..` segments and symlink escapes | `skills/validator.py`, `sessions/manager.py` |
| **Runaway Token / Quota Consumption** | Enforces `max_llm_calls` (default 20) and `max_iterations` on `LoopAgent` | `config.py`, `security/governance.py` |
| **Unapproved Billable Cloud Deployments** | `DeploymentManager` blocks non-dry-run cloud deployments unless `--approve-billable` is passed | `deployment/deployer.py` |
