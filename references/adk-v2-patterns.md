# Google ADK v2.12.0 Architecture & API Patterns Reference

## 1. Core Agent Classes (`google.adk.agents`)

- **`LlmAgent` (aliased as `Agent`)**: Primary reasoning unit backed by a model (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.8-flash`, or provider adapter).
  - When used inside a sequential or graph workflow in ADK 2.0+, set `mode="single_turn"` and `include_contents="default"` so downstream nodes receive outputs without hanging in interactive chat mode.
  - Sub-agents configured with `mode="single_turn"` in `sub_agents=[...]` are automatically exposed as tools to a coordinator `LlmAgent`.
- **`SequentialAgent`**: Executes `sub_agents` strictly in order, sharing `session.state` across steps via `output_key`.
- **`ParallelAgent`**: Executes independent `sub_agents` concurrently. Always declare `ParallelAgent` statically in the agent hierarchy to preserve ADK resume and OpenTelemetry trace visibility.
- **`LoopAgent`**: Repeats `sub_agents` until a termination condition is set in `session.state` or `max_iterations` is reached.
- **`BaseAgent`**: Inherit and implement `_run_async_impl` for custom programmatic orchestration.

## 2. Models & Resilience (`google.adk.models`)

- **`FallbackModel`**: Added in ADK v2.9.0 for automatic failover between primary and backup models.
- **`ModelConsultTool`**: Added in ADK v2.11.0 to let an agent consult a higher-reasoning advisor model mid-task, bounded by turn and session budgets.
- **`OpenAILlm` / `OpenAIResponsesLlm`**: Located under `google.adk.integrations.openai` (`google-adk[openai]`); use `OpenAIGenerateContentConfig.effort` for reasoning models (ADK v2.10.0+).
- **`AnthropicLlm`**: Supports Claude adaptive thinking with visible thoughts (ADK v2.9.1+).

## 3. Callbacks & Plugins (`google.adk.agents.callback_context`)

- **`before_agent_callback` / `after_agent_callback`**: Return `None` to proceed normally; returning `Content` from `before_agent_callback` short-circuits execution. Returning `None` from `after_agent_callback` avoids emitting duplicate content events.
- **`before_model_callback` / `after_model_callback`**: Return `LlmResponse` from `before_model_callback` to block unsafe requests or serve cached responses.
- **`before_tool_callback` / `after_tool_callback`**: Return a `dict` from `before_tool_callback` to skip tool execution; use `after_tool_callback` (ADK v2.12.0) to screen and redact tool outputs before returning them to the model.
- **Built-in Plugins**: `ToolCallIntegrityPlugin` (v2.11.0), `BigQueryAgentAnalyticsPlugin` (v2.12.0), `MultimodalToolResultsPlugin` (v2.8.0), `RecordingsPlugin`.
