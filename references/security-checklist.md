# ADK Security & Governance Checklist

1. **Zero Hardcoded Secrets**: Never commit API keys (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `AQ.*`, `AIza*`, `sk-*`) into `.py`, `.yaml`, `.json`, or `.env` files. Use `.env.example` with placeholders only.
2. **Prompt Injection Screening**: Attach `before_model_callback` (`before_model_guardrail`) to inspect incoming user turns for instruction-override attempts.
3. **Tool Output Sanitization**: Attach `after_tool_callback` (`after_tool_sanitizer`, ADK v2.12.0) to redact sensitive tokens or PII from tool responses before they enter model context.
4. **Human Confirmation Gates**: Set `require_confirmation=True` on mutating workflow `@node` / `FunctionNode` definitions (ADK v2.12.0) or enforce confirmation via `before_tool_callback` (`RequestInput` pause in ADK v2.11.0).
5. **Path Confinement**: Confine local file access in GCS/artifact tools to an explicit `local_file_root` and reject `..` path traversal segments.
6. **Least-Privilege Cloud Deployment**: Bind deployed Agent Engine / Cloud Run services to a dedicated custom service account (`--service_account`, ADK v2.12.0).
