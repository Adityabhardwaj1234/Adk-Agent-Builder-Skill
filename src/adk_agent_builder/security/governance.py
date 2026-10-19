"""ADK Callback and Plugin governance hooks (ADK v2.12.0 compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from adk_agent_builder.logging import redact_dict, redact_sensitive_text
from adk_agent_builder.security.scanner import SecurityScanner


@dataclass
class GovernancePolicy:
    """Runtime governance policy for ADK callbacks and plugins."""

    max_llm_calls: int = 20
    max_tool_calls: int = 30
    block_prompt_injection: bool = True
    redact_tool_outputs: bool = True
    require_confirmation_tools: List[str] = field(default_factory=list)
    allowed_tool_names: Optional[List[str]] = None


class GovernanceRuntime:
    """Provides verified ADK callback implementations (before/after agent, model, tool)."""

    def __init__(self, policy: Optional[GovernancePolicy] = None) -> None:
        self.policy = policy or GovernancePolicy()
        self.llm_calls_count = 0
        self.tool_calls_count = 0
        self.audit_trail: List[Dict[str, Any]] = []

    def before_agent_callback(self, callback_context: Any) -> Optional[Dict[str, Any]]:
        """ADK before_agent_callback: returns None to continue or Content dict to short-circuit."""
        agent_name = getattr(callback_context, "agent_name", "unknown_agent")
        self.audit_trail.append({"hook": "before_agent_callback", "agent": agent_name})
        return None

    def after_agent_callback(self, callback_context: Any) -> Optional[Dict[str, Any]]:
        """ADK after_agent_callback: returns None so ADK does not emit a duplicate Content event."""
        agent_name = getattr(callback_context, "agent_name", "unknown_agent")
        self.audit_trail.append({"hook": "after_agent_callback", "agent": agent_name})
        return None

    def before_model_callback(
        self,
        callback_context: Any,
        llm_request: Any,
    ) -> Optional[Dict[str, Any]]:
        """ADK before_model_callback: enforces call budget and screens for prompt injection."""
        self.llm_calls_count += 1
        if self.llm_calls_count > self.policy.max_llm_calls:
            self.audit_trail.append({"hook": "before_model_callback", "action": "blocked_budget"})
            return {
                "content": {
                    "role": "model",
                    "parts": [{"text": "Execution halted: maximum LLM call budget exceeded."}],
                }
            }

        user_text = ""
        if isinstance(llm_request, dict):
            user_text = str(llm_request.get("last_user_message", ""))
        elif hasattr(llm_request, "contents") and llm_request.contents:
            last = llm_request.contents[-1]
            if hasattr(last, "parts") and last.parts:
                user_text = getattr(last.parts[0], "text", "") or ""

        if self.policy.block_prompt_injection and user_text:
            check = SecurityScanner.check_prompt_injection(user_text)
            if check["blocked"]:
                self.audit_trail.append(
                    {"hook": "before_model_callback", "action": "blocked_prompt_injection"}
                )
                return {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Request blocked by security policy: prompt injection or policy bypass detected."
                            }
                        ],
                    }
                }
        self.audit_trail.append({"hook": "before_model_callback", "action": "allowed"})
        return None

    def after_model_callback(
        self,
        callback_context: Any,
        llm_response: Any,
    ) -> Optional[Any]:
        """ADK after_model_callback: redacts accidental secret leakage in model responses."""
        if isinstance(llm_response, dict) and "text" in llm_response:
            redacted = redact_sensitive_text(str(llm_response["text"]))
            if redacted != llm_response["text"]:
                self.audit_trail.append({"hook": "after_model_callback", "action": "redacted_output"})
                return {**llm_response, "text": redacted}
        return None

    def before_tool_callback(
        self,
        tool: Any,
        args: Dict[str, Any],
        tool_context: Any,
    ) -> Optional[Dict[str, Any]]:
        """ADK before_tool_callback: enforces tool allowlist, call budget, and human confirmation."""
        self.tool_calls_count += 1
        tool_name = getattr(tool, "name", str(tool))
        if self.tool_calls_count > self.policy.max_tool_calls:
            return {"status": "blocked", "error": "Maximum tool call budget exceeded."}

        if self.policy.allowed_tool_names is not None and tool_name not in self.policy.allowed_tool_names:
            self.audit_trail.append(
                {"hook": "before_tool_callback", "tool": tool_name, "action": "blocked_unauthorized"}
            )
            return {"status": "blocked", "error": f"Tool '{tool_name}' is not in the authorized allowlist."}

        if tool_name in self.policy.require_confirmation_tools:
            confirmed = False
            if isinstance(tool_context, dict):
                confirmed = bool(tool_context.get("human_confirmed", False))
            elif hasattr(tool_context, "state") and isinstance(tool_context.state, dict):
                confirmed = bool(tool_context.state.get("human_confirmed", False))
            if not confirmed:
                self.audit_trail.append(
                    {"hook": "before_tool_callback", "tool": tool_name, "action": "paused_for_confirmation"}
                )
                return {
                    "status": "requires_confirmation",
                    "tool": tool_name,
                    "message": f"Action '{tool_name}' requires explicit human confirmation via RequestInput.",
                }

        self.audit_trail.append({"hook": "before_tool_callback", "tool": tool_name, "action": "allowed"})
        return None

    def after_tool_callback(
        self,
        tool: Any,
        args: Dict[str, Any],
        tool_context: Any,
        tool_response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """ADK v2.12.0 after_tool_callback: screens and redacts sensitive fields from tool outputs before returning to LLM."""
        tool_name = getattr(tool, "name", str(tool))
        if self.policy.redact_tool_outputs and isinstance(tool_response, dict):
            sanitized = redact_dict(tool_response)
            self.audit_trail.append(
                {"hook": "after_tool_callback", "tool": tool_name, "action": "sanitized"}
            )
            return sanitized
        return None
