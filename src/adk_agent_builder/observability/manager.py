"""Observability configuration, exporters, and token/cost telemetry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.logging import redact_dict
from adk_agent_builder.models.base import CompatModel


SUPPORTED_EXPORTERS: Dict[str, Dict[str, Any]] = {
    "opentelemetry": {
        "name": "OpenTelemetry OTLP Exporter",
        "required_env": ["OTEL_EXPORTER_OTLP_ENDPOINT"],
        "adk_support": "Native OTel span emission across Runner, Agent, Model, Tool, and SkillToolset (ADK v2.9.2+ preserves OTel event names outside Agent Engine).",
    },
    "cloud_trace": {
        "name": "Google Cloud Trace (telemetry.googleapis.com)",
        "required_env": ["GOOGLE_CLOUD_PROJECT"],
        "adk_support": "Native OTLP export to telemetry.googleapis.com (ADK v2.9.0+).",
    },
    "bigquery_agent_analytics": {
        "name": "BigQueryAgentAnalyticsPlugin",
        "required_env": ["GOOGLE_CLOUD_PROJECT", "BQ_ANALYTICS_DATASET"],
        "adk_support": "ADK v2.12.0+ plugin with enriched AGENT_STARTING metadata and on_schema_ready / on_schema_error hooks.",
    },
    "langfuse": {
        "name": "Langfuse OTel Integration",
        "required_env": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
        "adk_support": "Compatible via OpenTelemetry OTLP HTTP exporter.",
    },
    "phoenix": {
        "name": "Arize Phoenix OTel Collector",
        "required_env": ["PHOENIX_COLLECTOR_ENDPOINT"],
        "adk_support": "Compatible via OpenTelemetry OTLP span exporter.",
    },
    "agentops": {
        "name": "AgentOps Telemetry Adapter",
        "required_env": ["AGENTOPS_API_KEY"],
        "adk_support": "Optional third-party callback/OTel integration.",
    },
    "mlflow": {
        "name": "MLflow Tracing Exporter",
        "required_env": ["MLFLOW_TRACKING_URI"],
        "adk_support": "Compatible via MLflow OpenTelemetry trace ingestion.",
    },
}

# Documented reference token pricing per 1M tokens (USD) for cost estimation
DOCUMENTED_PRICING_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-flash-latest": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


class ObservabilityConfig(CompatModel):
    enabled_exporters: List[str] = Field(default_factory=lambda: ["opentelemetry"])
    redact_prompts_and_responses: bool = True
    capture_full_payloads: bool = False
    enable_experimental_telemetry: bool = False
    bq_dataset_id: Optional[str] = None
    bq_table_id: Optional[str] = "agent_events"


class ObservabilityManager:
    """Manages observability exporter validation, configuration generation, and token cost estimation."""

    @staticmethod
    def validate_exporters(exporters: List[str]) -> Dict[str, Any]:
        valid: List[str] = []
        unknown: List[str] = []
        for exp in exporters:
            key = exp.lower().strip()
            if key in SUPPORTED_EXPORTERS:
                valid.append(key)
            else:
                unknown.append(exp)
        return {
            "valid": len(unknown) == 0,
            "configured_exporters": valid,
            "unknown_exporters": unknown,
            "details": [SUPPORTED_EXPORTERS[k] for k in valid],
        }

    @staticmethod
    def estimate_token_cost(
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Dict[str, Any]:
        pricing = DOCUMENTED_PRICING_PER_1M_TOKENS.get(model_name)
        if not pricing:
            return {
                "model": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": None,
                "pricing_documented": False,
            }
        cost = (input_tokens / 1_000_000.0) * pricing["input"] + (
            output_tokens / 1_000_000.0
        ) * pricing["output"]
        return {
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(cost, 6),
            "pricing_documented": True,
        }

    @staticmethod
    def generate_observability_manifest(cfg: ObservabilityConfig) -> Dict[str, Any]:
        return redact_dict(
            {
                "exporters": cfg.enabled_exporters,
                "redact_prompts_and_responses": cfg.redact_prompts_and_responses,
                "capture_full_payloads": cfg.capture_full_payloads and not cfg.redact_prompts_and_responses,
                "adk_experimental_telemetry_opt_in": cfg.enable_experimental_telemetry,
                "bigquery_analytics": {
                    "enabled": "bigquery_agent_analytics" in cfg.enabled_exporters,
                    "dataset_id": cfg.bq_dataset_id,
                    "table_id": cfg.bq_table_id,
                    "callbacks": ["on_schema_ready", "on_schema_error"],
                },
            }
        )
