"""Structured logging with automatic secret and credential redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Pattern

# Patterns for sensitive credentials and tokens that must never appear in logs or reports
SECRET_PATTERNS: List[Pattern[str]] = [
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    re.compile(r"AQ\.[0-9A-Za-z\-_]{20,}"),
    re.compile(r"sk-[0-9A-Za-z\-_]{20,}"),
    re.compile(r"sk-ant-[0-9A-Za-z\-_]{20,}"),
    re.compile(r"ghp_[0-9A-Za-z]{25,}"),
    re.compile(r"github_pat_[0-9A-Za-z_]{25,}"),
    re.compile(r"ya29\.[0-9A-Za-z\-_]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password|credential|authorization)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{12,})['\"]?"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{12,}"),
]

SENSITIVE_KEY_NAMES = {
    "api_key",
    "gemini_api_key",
    "google_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "client_secret",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "private_key",
    "authorization",
    "auth_credential",
}


def redact_sensitive_text(text: str, extra_secrets: Optional[Iterable[str]] = None) -> str:
    """Redact API keys, tokens, and credential assignments from a string."""
    if not text:
        return text
    redacted = str(text)
    if extra_secrets:
        for secret in extra_secrets:
            if secret and len(secret) >= 6:
                redacted = redacted.replace(secret, "[REDACTED_SECRET]")
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1=[REDACTED_SECRET]", redacted)
        else:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def redact_dict(data: Any, extra_secrets: Optional[Iterable[str]] = None) -> Any:
    """Recursively redact sensitive keys and secret patterns in dictionaries and lists."""
    if isinstance(data, dict):
        result: Dict[str, Any] = {}
        for k, v in data.items():
            key_lower = str(k).lower()
            if any(s in key_lower for s in SENSITIVE_KEY_NAMES) and v not in (None, "", False):
                result[k] = "[REDACTED_SECRET]"
            else:
                result[k] = redact_dict(v, extra_secrets=extra_secrets)
        return result
    if isinstance(data, list):
        return [redact_dict(item, extra_secrets=extra_secrets) for item in data]
    if isinstance(data, str):
        return redact_sensitive_text(data, extra_secrets=extra_secrets)
    return data


class RedactingJsonFormatter(logging.Formatter):
    """Structured JSON formatter that redacts secrets automatically."""

    def __init__(self, correlation_id: Optional[str] = None) -> None:
        super().__init__()
        self.correlation_id = correlation_id or "default"

    def format(self, record: logging.LogRecord) -> str:
        msg = redact_sensitive_text(record.getMessage())
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", self.correlation_id),
            "message": msg,
        }
        if hasattr(record, "stage"):
            payload["stage"] = getattr(record, "stage")
        if hasattr(record, "extra_data"):
            payload["data"] = redact_dict(getattr(record, "extra_data"))
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, sort_keys=True)


def get_logger(
    name: str = "adk_agent_builder",
    level: str = "INFO",
    json_format: bool = False,
    correlation_id: Optional[str] = None,
) -> logging.Logger:
    """Configure and return a redaction-aware logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        if json_format:
            handler.setFormatter(RedactingJsonFormatter(correlation_id=correlation_id))
        else:
            handler.setFormatter(
                logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
            )
        logger.addHandler(handler)
        logger.propagate = False
    return logger
