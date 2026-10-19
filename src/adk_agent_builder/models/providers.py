"""Extensible model and provider abstraction layer for Google ADK."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.errors import ExternalPrerequisiteError
from adk_agent_builder.models.base import CompatModel


class ProviderType(str, Enum):
    GEMINI = "gemini"
    VERTEX_AI = "vertex_ai"
    GEMMA = "gemma"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    LITELLM = "litellm"
    OLLAMA = "ollama"
    VLLM = "vllm"


class ProviderCapabilities(CompatModel):
    provider: ProviderType
    adk_adapter_class: str
    extra_package: Optional[str] = None
    required_env_vars: List[str] = Field(default_factory=list)
    supports_tool_calling: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True
    supports_live_audio_video: bool = False
    supports_context_caching: bool = False
    supports_thinking_or_effort: bool = False
    reasoning_config_field: Optional[str] = None
    supports_model_consult: bool = False
    notes: str = ""


PROVIDER_CATALOG: Dict[ProviderType, ProviderCapabilities] = {
    ProviderType.GEMINI: ProviderCapabilities(
        provider=ProviderType.GEMINI,
        adk_adapter_class="google.adk.models.Gemini",
        extra_package=None,
        required_env_vars=["GEMINI_API_KEY"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=True,
        supports_context_caching=True,
        supports_thinking_or_effort=True,
        reasoning_config_field="thinking_config",
        supports_model_consult=True,
        notes="Native Google AI Studio Gemini adapter; also accepts GOOGLE_API_KEY.",
    ),
    ProviderType.VERTEX_AI: ProviderCapabilities(
        provider=ProviderType.VERTEX_AI,
        adk_adapter_class="google.adk.models.Gemini",
        extra_package="google-cloud-aiplatform>=2.2.0",
        required_env_vars=["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=True,
        supports_context_caching=True,
        supports_thinking_or_effort=True,
        reasoning_config_field="thinking_config",
        supports_model_consult=True,
        notes="Enterprise Vertex AI Gemini adapter using Application Default Credentials.",
    ),
    ProviderType.GEMMA: ProviderCapabilities(
        provider=ProviderType.GEMMA,
        adk_adapter_class="google.adk.models.Gemma",
        extra_package=None,
        required_env_vars=["GEMINI_API_KEY"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=False,
        supports_thinking_or_effort=False,
        supports_model_consult=False,
        notes="Open-weights Gemma models via Google AI / Vertex or local endpoints.",
    ),
    ProviderType.ANTHROPIC: ProviderCapabilities(
        provider=ProviderType.ANTHROPIC,
        adk_adapter_class="google.adk.models.AnthropicLlm",
        extra_package="anthropic>=0.34.0",
        required_env_vars=["ANTHROPIC_API_KEY"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=True,
        supports_thinking_or_effort=True,
        reasoning_config_field="thinking",
        supports_model_consult=True,
        notes="Supports Claude adaptive thinking with visible thoughts (ADK v2.9.1+).",
    ),
    ProviderType.OPENAI: ProviderCapabilities(
        provider=ProviderType.OPENAI,
        adk_adapter_class="google.adk.integrations.openai.OpenAILlm",
        extra_package="google-adk[openai]",
        required_env_vars=["OPENAI_API_KEY"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=False,
        supports_thinking_or_effort=True,
        reasoning_config_field="OpenAIGenerateContentConfig.effort",
        supports_model_consult=True,
        notes="Moved to google.adk.integrations.openai in ADK v2.10.0; uses effort instead of thinking_config on OpenAIResponsesLlm.",
    ),
    ProviderType.LITELLM: ProviderCapabilities(
        provider=ProviderType.LITELLM,
        adk_adapter_class="google.adk.models.lite_llm.LiteLlm",
        extra_package="litellm>=1.45.0",
        required_env_vars=[],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=True,
        supports_thinking_or_effort=False,
        supports_model_consult=False,
        notes="Multi-provider routing adapter with JSON-tolerant tool argument parsing (ADK v2.12.0).",
    ),
    ProviderType.OLLAMA: ProviderCapabilities(
        provider=ProviderType.OLLAMA,
        adk_adapter_class="google.adk.models.lite_llm.LiteLlm",
        extra_package="litellm>=1.45.0",
        required_env_vars=["OLLAMA_API_BASE"],
        supports_tool_calling=True,
        supports_structured_output=False,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=False,
        supports_thinking_or_effort=False,
        supports_model_consult=False,
        notes="Local Ollama inference via LiteLlm(model='ollama_chat/<model>').",
    ),
    ProviderType.VLLM: ProviderCapabilities(
        provider=ProviderType.VLLM,
        adk_adapter_class="google.adk.models.lite_llm.LiteLlm",
        extra_package="litellm>=1.45.0",
        required_env_vars=["VLLM_API_BASE"],
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_live_audio_video=False,
        supports_context_caching=False,
        supports_thinking_or_effort=False,
        supports_model_consult=False,
        notes="Self-hosted OpenAI-compatible vLLM endpoint.",
    ),
}


class ModelProviderConfig(CompatModel):
    """Validated provider configuration with fallback and consultation settings."""

    provider: ProviderType = ProviderType.GEMINI
    model_name: str = "gemini-2.5-flash"
    fallback_model_name: Optional[str] = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    reasoning_effort: Optional[str] = None  # low | medium | high
    enable_model_consult: bool = False
    consult_advisor_model: Optional[str] = "gemini-2.5-pro"
    consult_turn_budget: int = 2
    consult_session_budget: int = 5

    def get_capabilities(self) -> ProviderCapabilities:
        return PROVIDER_CATALOG[self.provider]

    def validate_compatibility(
        self,
        *,
        requires_live: bool = False,
        requires_structured_output: bool = False,
        requires_caching: bool = False,
    ) -> List[str]:
        """Validate requested agent features against documented provider capabilities."""
        caps = self.get_capabilities()
        issues: List[str] = []
        if requires_live and not caps.supports_live_audio_video:
            issues.append(
                f"Provider '{self.provider.value}' does not natively support ADK Live bidirectional audio/video sessions."
            )
        if requires_structured_output and not caps.supports_structured_output:
            issues.append(
                f"Provider '{self.provider.value}' does not guarantee strict schema-validated structured outputs."
            )
        if requires_caching and not caps.supports_context_caching:
            issues.append(
                f"Provider '{self.provider.value}' does not support model context caching in ADK."
            )
        if self.enable_model_consult and not caps.supports_model_consult:
            issues.append(
                f"Provider '{self.provider.value}' does not support ModelConsultTool advisor handoffs."
            )
        return issues

    def check_credentials_present(self, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Check whether required credentials exist in environment without exposing secret values."""
        environment = env if env is not None else dict(os.environ)
        caps = self.get_capabilities()
        if self.provider == ProviderType.GEMINI:
            has_key = bool(environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY"))
            return {
                "provider": self.provider.value,
                "configured": has_key,
                "checked_vars": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            }
        missing = [var for var in caps.required_env_vars if not environment.get(var)]
        return {
            "provider": self.provider.value,
            "configured": len(missing) == 0,
            "checked_vars": caps.required_env_vars,
            "missing_vars": missing,
        }

    def render_adk_model_expr(self) -> str:
        """Render valid Python expression for instantiating the model in generated ADK code."""
        if self.provider in (ProviderType.GEMINI, ProviderType.VERTEX_AI):
            if self.fallback_model_name:
                return (
                    f'FallbackModel(models=["{self.model_name}", "{self.fallback_model_name}"])'
                )
            return f'"{self.model_name}"'
        if self.provider == ProviderType.OPENAI:
            return f'OpenAILlm(model="{self.model_name}")'
        if self.provider == ProviderType.ANTHROPIC:
            return f'AnthropicLlm(model="{self.model_name}")'
        if self.provider == ProviderType.OLLAMA:
            model_id = self.model_name if self.model_name.startswith("ollama") else f"ollama_chat/{self.model_name}"
            return f'LiteLlm(model="{model_id}")'
        return f'LiteLlm(model="{self.model_name}")'
