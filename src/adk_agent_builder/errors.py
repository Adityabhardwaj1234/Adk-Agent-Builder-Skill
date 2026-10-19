"""Domain-specific exception hierarchy with actionable error messages and exit codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional


class ExitCode(IntEnum):
    """Standardized CLI exit codes for deterministic automation."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGUMENTS = 2
    REQUIREMENTS_ERROR = 3
    VALIDATION_FAILED = 4
    TEST_FAILED = 5
    EVALUATION_FAILED = 6
    SECURITY_VIOLATION = 7
    DEPLOYMENT_BLOCKED = 8
    EXTERNAL_DEPENDENCY_MISSING = 9
    SELF_REPAIR_EXHAUSTED = 10


@dataclass
class BuilderErrorContext:
    """Structured diagnostic context attached to suite exceptions."""

    stage: str = "unknown"
    file_path: Optional[str] = None
    command: Optional[str] = None
    remediation: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class AdkBuilderError(Exception):
    """Base exception for all ADK Agent Builder Suite errors."""

    exit_code: ExitCode = ExitCode.GENERAL_ERROR
    error_code: str = "ADK_ERR_000"

    def __init__(
        self,
        message: str,
        *,
        stage: str = "general",
        file_path: Optional[str] = None,
        command: Optional[str] = None,
        remediation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = BuilderErrorContext(
            stage=stage,
            file_path=file_path,
            command=command,
            remediation=remediation,
            details=details or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize exception into a structured diagnostic dictionary."""
        return {
            "error_code": self.error_code,
            "exit_code": int(self.exit_code),
            "message": self.message,
            "stage": self.context.stage,
            "file_path": self.context.file_path,
            "command": self.context.command,
            "remediation": self.context.remediation,
            "details": self.context.details,
        }


class RequirementsValidationError(AdkBuilderError):
    """Raised when customer requirements contain contradictions or invalid schemas."""

    exit_code = ExitCode.REQUIREMENTS_ERROR
    error_code = "ADK_ERR_REQ"


class ProjectValidationError(AdkBuilderError):
    """Raised when static project validation fails."""

    exit_code = ExitCode.VALIDATION_FAILED
    error_code = "ADK_ERR_VAL"


class TestExecutionError(AdkBuilderError):
    """Raised when unit, integration, or contract tests fail."""

    exit_code = ExitCode.TEST_FAILED
    error_code = "ADK_ERR_TST"


class EvaluationFailureError(AdkBuilderError):
    """Raised when agent evaluation fails acceptance criteria thresholds."""

    exit_code = ExitCode.EVALUATION_FAILED
    error_code = "ADK_ERR_EVAL"


class SecurityPolicyError(AdkBuilderError):
    """Raised when a security baseline check or secret policy check fails."""

    exit_code = ExitCode.SECURITY_VIOLATION
    error_code = "ADK_ERR_SEC"


class DeploymentBlockedError(AdkBuilderError):
    """Raised when deployment prerequisites or explicit authorization are missing."""

    exit_code = ExitCode.DEPLOYMENT_BLOCKED
    error_code = "ADK_ERR_DEP"


class ExternalPrerequisiteError(AdkBuilderError):
    """Raised when an optional SDK, CLI, or cloud credential is required but missing."""

    exit_code = ExitCode.EXTERNAL_DEPENDENCY_MISSING
    error_code = "ADK_ERR_PRE"


class SelfRepairExhaustedError(AdkBuilderError):
    """Raised when the bounded self-repair pipeline exceeds maximum retry budget."""

    exit_code = ExitCode.SELF_REPAIR_EXHAUSTED
    error_code = "ADK_ERR_RPR"
