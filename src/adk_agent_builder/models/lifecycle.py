"""17-Stage Agent Engineering Lifecycle models and checkpoint persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class LifecycleStage(str, Enum):
    STAGE_01_REQUIREMENT_INTAKE = "01_requirement_intake"
    STAGE_02_CLARIFICATION_NORMALIZATION = "02_clarification_normalization"
    STAGE_03_FEASIBILITY_ANALYSIS = "03_feasibility_analysis"
    STAGE_04_ARCHITECTURE_SELECTION = "04_architecture_selection"
    STAGE_05_AGENT_WORKFLOW_PLANNING = "05_agent_workflow_planning"
    STAGE_06_TOOL_INTEGRATION_SELECTION = "06_tool_integration_selection"
    STAGE_07_PROJECT_SCAFFOLDING = "07_project_scaffolding"
    STAGE_08_AGENT_IMPLEMENTATION = "08_agent_implementation"
    STAGE_09_CONFIGURATION_GENERATION = "09_configuration_generation"
    STAGE_10_UNIT_INTEGRATION_TESTING = "10_unit_integration_testing"
    STAGE_11_SECURITY_POLICY_VALIDATION = "11_security_policy_validation"
    STAGE_12_EVALUATION_ACCEPTANCE = "12_evaluation_acceptance"
    STAGE_13_FAILURE_DIAGNOSIS_REMEDIATION = "13_failure_diagnosis_remediation"
    STAGE_14_PACKAGING_DEPLOYMENT_PLANNING = "14_packaging_deployment_planning"
    STAGE_15_DEPLOYMENT_SMOKE_TESTING = "15_deployment_smoke_testing"
    STAGE_16_OBSERVABILITY_CONFIGURATION = "16_observability_configuration"
    STAGE_17_MAINTENANCE_REGRESSION = "17_maintenance_regression"


class StageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class StageRecord(CompatModel):
    stage: LifecycleStage
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    artifacts: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class EngineeringRunState(CompatModel):
    """Persistent checkpoint state for an end-to-end engineering run."""

    run_id: str
    project_name: str
    project_dir: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_stage: Optional[LifecycleStage] = None
    overall_status: str = "initialized"
    stages: Dict[str, StageRecord] = Field(default_factory=dict)
    repair_history: List[Dict[str, Any]] = Field(default_factory=list)
    outstanding_risks: List[str] = Field(default_factory=list)
    deployment_state: Dict[str, Any] = Field(default_factory=lambda: {"status": "not_deployed"})

    def initialize_all_stages(self) -> None:
        for st in LifecycleStage:
            if st.value not in self.stages:
                self.stages[st.value] = StageRecord(stage=st)

    def mark_stage(
        self,
        stage: LifecycleStage,
        status: StageStatus,
        *,
        duration_ms: float = 0.0,
        artifacts: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rec = self.stages.get(stage.value) or StageRecord(stage=stage, started_at=now)
        if not rec.started_at:
            rec.started_at = now
        rec.status = status
        rec.completed_at = now
        rec.duration_ms = round(duration_ms, 3)
        if artifacts:
            rec.artifacts = list(dict.fromkeys(rec.artifacts + artifacts))
        if errors:
            rec.errors.extend(errors)
        if metrics:
            rec.metrics.update(metrics)
        self.stages[stage.value] = rec
        self.current_stage = stage
        self.updated_at = now
        if status == StageStatus.FAILED:
            self.overall_status = "failed"
        elif all(
            r.status in (StageStatus.PASSED, StageStatus.SKIPPED)
            for r in self.stages.values()
        ) and len(self.stages) == len(LifecycleStage):
            self.overall_status = "completed"
        else:
            self.overall_status = "in_progress"

    def save(self, state_file: Path) -> None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, state_file: Path) -> "EngineeringRunState":
        import json
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        return cls.from_dict(raw)
