"""Centralized configuration management for ADK Agent Builder Suite."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from adk_agent_builder.logging import redact_dict


@dataclass
class BuilderConfig:
    """Centralized, validated configuration for the ADK Agent Builder Suite."""

    workspace_dir: Path = field(default_factory=lambda: Path.cwd())
    default_provider: str = "gemini"
    default_model: str = "gemini-2.5-flash"
    fallback_model: Optional[str] = "gemini-2.5-pro"
    adk_target_version: str = "2.12.0"
    session_service_uri: str = "memory://"
    memory_service_uri: str = "sqlite:///adk_memory.db"
    artifact_service_type: str = "in_memory"
    max_repair_attempts: int = 3
    subprocess_timeout_seconds: int = 60
    max_llm_calls_per_run: int = 20
    daily_api_call_budget: int = 20
    enable_experimental_telemetry: bool = False
    enable_skill_lifecycle: bool = False
    redact_prompts_by_default: bool = True
    require_deployment_approval: bool = True
    log_level: str = "INFO"
    json_logs: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env_and_file(
        cls,
        config_path: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "BuilderConfig":
        """Load configuration from optional YAML file, environment variables, and explicit overrides."""
        file_data: Dict[str, Any] = {}
        if config_path and config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                file_data = raw

        env_map: Dict[str, Any] = {}
        if os.environ.get("ADK_BUILDER_PROVIDER"):
            env_map["default_provider"] = os.environ["ADK_BUILDER_PROVIDER"]
        if os.environ.get("ADK_BUILDER_MODEL"):
            env_map["default_model"] = os.environ["ADK_BUILDER_MODEL"]
        if os.environ.get("ADK_MAX_LLM_CALLS"):
            try:
                env_map["max_llm_calls_per_run"] = int(os.environ["ADK_MAX_LLM_CALLS"])
            except ValueError:
                pass
        if os.environ.get("ADK_EXPERIMENTAL_TELEMETRY", "").lower() in ("1", "true", "yes"):
            env_map["enable_experimental_telemetry"] = True
        if os.environ.get("ADK_ENABLE_SKILL_LIFECYCLE", "").lower() in ("1", "true", "yes"):
            env_map["enable_skill_lifecycle"] = True

        merged: Dict[str, Any] = {**file_data, **env_map, **(overrides or {})}
        if "workspace_dir" in merged and not isinstance(merged["workspace_dir"], Path):
            merged["workspace_dir"] = Path(str(merged["workspace_dir"]))

        known_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        init_kwargs = {k: v for k, v in merged.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in merged.items() if k not in known_fields}
        if extra_kwargs:
            init_kwargs["extra"] = {**init_kwargs.get("extra", {}), **extra_kwargs}
        return cls(**init_kwargs)

    def to_safe_dict(self) -> Dict[str, Any]:
        """Export configuration as a dictionary with sensitive values redacted."""
        raw = {
            "workspace_dir": str(self.workspace_dir),
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "fallback_model": self.fallback_model,
            "adk_target_version": self.adk_target_version,
            "session_service_uri": self.session_service_uri,
            "memory_service_uri": self.memory_service_uri,
            "artifact_service_type": self.artifact_service_type,
            "max_repair_attempts": self.max_repair_attempts,
            "subprocess_timeout_seconds": self.subprocess_timeout_seconds,
            "max_llm_calls_per_run": self.max_llm_calls_per_run,
            "daily_api_call_budget": self.daily_api_call_budget,
            "enable_experimental_telemetry": self.enable_experimental_telemetry,
            "enable_skill_lifecycle": self.enable_skill_lifecycle,
            "redact_prompts_by_default": self.redact_prompts_by_default,
            "require_deployment_approval": self.require_deployment_approval,
            "log_level": self.log_level,
            "json_logs": self.json_logs,
            "extra": redact_dict(self.extra),
        }
        return redact_dict(raw)
