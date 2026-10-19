"""Telemetry, correlation IDs, and execution span recording."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

from adk_agent_builder.logging import redact_dict


def generate_correlation_id(prefix: str = "adk-run") -> str:
    """Generate a unique correlation ID for tracing engineering lifecycle operations."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class TelemetrySpan:
    """Represents a timed execution span with redacted attributes."""

    name: str
    correlation_id: str
    stage: str
    start_time_utc: str
    end_time_utc: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "in_progress"
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "correlation_id": self.correlation_id,
            "stage": self.stage,
            "start_time_utc": self.start_time_utc,
            "end_time_utc": self.end_time_utc,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "attributes": redact_dict(self.attributes),
        }


class TelemetryRecorder:
    """In-memory and exportable telemetry recorder compatible with OpenTelemetry semantics."""

    def __init__(self, correlation_id: Optional[str] = None, redact_prompts: bool = True) -> None:
        self.correlation_id = correlation_id or generate_correlation_id()
        self.redact_prompts = redact_prompts
        self.spans: List[TelemetrySpan] = []
        self.metrics: Dict[str, float] = {
            "total_duration_ms": 0.0,
            "stages_executed": 0,
            "stages_failed": 0,
            "tool_calls_recorded": 0,
            "tokens_estimated": 0,
        }

    @contextmanager
    def span(
        self,
        name: str,
        stage: str = "general",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Generator[TelemetrySpan, None, None]:
        """Record a timed telemetry span around a lifecycle operation."""
        start_ts = time.perf_counter()
        start_utc = datetime.now(timezone.utc).isoformat()
        safe_attrs = redact_dict(attributes or {})
        if self.redact_prompts:
            for key in ("prompt", "raw_response", "user_input"):
                if key in safe_attrs:
                    safe_attrs[key] = "[REDACTED_BY_TELEMETRY_POLICY]"
        current_span = TelemetrySpan(
            name=name,
            correlation_id=self.correlation_id,
            stage=stage,
            start_time_utc=start_utc,
            attributes=safe_attrs,
        )
        self.spans.append(current_span)
        self.metrics["stages_executed"] += 1
        try:
            yield current_span
            current_span.status = "ok"
        except Exception as exc:
            current_span.status = "error"
            current_span.attributes["error_type"] = type(exc).__name__
            current_span.attributes["error_message"] = str(exc)
            self.metrics["stages_failed"] += 1
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
            current_span.duration_ms = elapsed_ms
            current_span.end_time_utc = datetime.now(timezone.utc).isoformat()
            self.metrics["total_duration_ms"] += elapsed_ms

    def summary(self) -> Dict[str, Any]:
        """Export all recorded spans and metrics."""
        return {
            "correlation_id": self.correlation_id,
            "redact_prompts": self.redact_prompts,
            "metrics": {k: round(v, 3) for k, v in self.metrics.items()},
            "spans": [s.to_dict() for s in self.spans],
        }
