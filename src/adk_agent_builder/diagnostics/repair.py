"""Failure diagnostics and bounded, stage-specific self-repair pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.evaluation.evaluator import EvaluationEngine
from adk_agent_builder.models.base import CompatModel
from adk_agent_builder.security.scanner import SecurityScanner
from adk_agent_builder.testing.runner import TestRunner
from adk_agent_builder.validation.validator import ProjectValidator


class DiagnosticFinding(CompatModel):
    stage: str
    code: str
    file_path: str
    root_cause: str
    suggested_repair: str
    auto_repairable: bool = False


class RepairAttemptRecord(CompatModel):
    attempt: int
    stage: str
    finding_code: str
    file_path: str
    action_taken: str
    verified_fixed: bool = False


class SelfRepairReport(CompatModel):
    project_dir: str
    initial_healthy: bool = False
    final_healthy: bool = False
    attempts_used: int = 0
    max_attempts: int = 3
    diagnostics: List[DiagnosticFinding] = Field(default_factory=list)
    repair_history: List[RepairAttemptRecord] = Field(default_factory=list)
    remaining_uncertainties: List[str] = Field(default_factory=list)


class DiagnosticsAndRepairEngine:
    """Diagnoses validation, test, evaluation, and security defects and executes bounded targeted repairs."""

    @staticmethod
    def diagnose_project(project_dir: Path) -> List[DiagnosticFinding]:
        """Run validation, security scan, unit tests, and evaluation to produce evidence-backed diagnostics."""
        diagnostics: List[DiagnosticFinding] = []

        # 1. Static validation
        val_report = ProjectValidator.validate_project(project_dir)
        for issue in val_report.issues:
            if issue.severity == "error":
                auto = issue.code in ("VAL_MISSING_ROOT_AGENT", "VAL_DEPRECATED_ADK_IMPORT")
                diagnostics.append(
                    DiagnosticFinding(
                        stage="static_validation",
                        code=issue.code,
                        file_path=issue.file_path,
                        root_cause=issue.message,
                        suggested_repair=issue.remediation,
                        auto_repairable=auto,
                    )
                )

        # 2. Security scan
        sec_report = SecurityScanner.scan_project(project_dir)
        for finding in sec_report.findings:
            if finding.severity in ("critical", "high"):
                diagnostics.append(
                    DiagnosticFinding(
                        stage="security_validation",
                        code=finding.rule_id,
                        file_path=finding.file_path,
                        root_cause=finding.description,
                        suggested_repair=finding.remediation,
                        auto_repairable=(finding.rule_id == "SEC_HARDCODED_SECRET"),
                    )
                )

        # 3. Automated tests (only if static syntax passes)
        if val_report.valid:
            test_res = TestRunner.run_tests(project_dir)
            if not test_res.passed:
                tools_py = project_dir / "app/tools.py"
                tools_src = tools_py.read_text(encoding="utf-8") if tools_py.exists() else ""
                is_tool_defect = '"status": "broken"' in tools_src or '"status": "error_defect"' in tools_src or "BROKEN_DEFECT" in tools_src
                diagnostics.append(
                    DiagnosticFinding(
                        stage="unit_and_integration_tests",
                        code="TST_SUITE_FAILURE",
                        file_path="app/tools.py" if is_tool_defect else "tests/",
                        root_cause=f"Test suite failed ({test_res.failed_tests} failed, {test_res.error_tests} errors): "
                        + "; ".join(test_res.failure_summaries[:3]),
                        suggested_repair="Inspect failing tool return contract in app/tools.py or agent wiring in app/agent.py.",
                        auto_repairable=is_tool_defect,
                    )
                )

            # 4. Evaluation check
            try:
                eval_res = EvaluationEngine.evaluate_project(project_dir)
                if not eval_res.overall_passed:
                    diagnostics.append(
                        DiagnosticFinding(
                            stage="evaluation",
                            code="EVAL_THRESHOLD_FAILURE",
                            file_path="app/tools.py",
                            root_cause="Evaluation failed criteria: "
                            + "; ".join(
                                r
                                for c in eval_res.case_results
                                for r in c.failure_reasons
                            ),
                            suggested_repair="Align tool names and output summary format with expected EvalSet trajectory.",
                            auto_repairable=True,
                        )
                    )
            except Exception as exc:
                diagnostics.append(
                    DiagnosticFinding(
                        stage="evaluation",
                        code="EVAL_EXECUTION_ERROR",
                        file_path="tests/eval/default_eval.evalset.json",
                        root_cause=str(exc),
                        suggested_repair="Verify root_agent export and EvalSet JSON schema.",
                        auto_repairable=False,
                    )
                )

        return diagnostics

    @staticmethod
    def run_bounded_repair(
        project_dir: Path,
        *,
        max_attempts: int = 3,
    ) -> SelfRepairReport:
        """Iteratively diagnose, apply minimal targeted fixes, and re-verify up to max_attempts."""
        initial_diags = DiagnosticsAndRepairEngine.diagnose_project(project_dir)
        if not initial_diags:
            return SelfRepairReport(
                project_dir=str(project_dir),
                initial_healthy=True,
                final_healthy=True,
                attempts_used=0,
                max_attempts=max_attempts,
            )

        history: List[RepairAttemptRecord] = []
        attempts = 0
        current_diags = list(initial_diags)

        while current_diags and attempts < max_attempts:
            attempts += 1
            target = next((d for d in current_diags if d.auto_repairable), current_diags[0])
            patched, action_desc = DiagnosticsAndRepairEngine._apply_minimal_fix(project_dir, target)
            if not patched:
                history.append(
                    RepairAttemptRecord(
                        attempt=attempts,
                        stage=target.stage,
                        finding_code=target.code,
                        file_path=target.file_path,
                        action_taken=action_desc,
                        verified_fixed=False,
                    )
                )
                break

            # Re-verify all checks (targeted + regression)
            new_diags = DiagnosticsAndRepairEngine.diagnose_project(project_dir)
            still_present = any(
                d.code == target.code and d.file_path == target.file_path for d in new_diags
            )
            history.append(
                RepairAttemptRecord(
                    attempt=attempts,
                    stage=target.stage,
                    finding_code=target.code,
                    file_path=target.file_path,
                    action_taken=action_desc,
                    verified_fixed=(not still_present),
                )
            )
            current_diags = new_diags

        uncertainties = [
            f"[{d.code}] {d.file_path}: {d.root_cause}" for d in current_diags
        ]
        return SelfRepairReport(
            project_dir=str(project_dir),
            initial_healthy=False,
            final_healthy=(len(current_diags) == 0),
            attempts_used=attempts,
            max_attempts=max_attempts,
            diagnostics=initial_diags,
            repair_history=history,
            remaining_uncertainties=uncertainties,
        )

    @staticmethod
    def _apply_minimal_fix(project_dir: Path, finding: DiagnosticFinding) -> tuple[bool, str]:
        target_path = project_dir / finding.file_path
        if not target_path.exists():
            return False, f"Target file {finding.file_path} does not exist for auto-repair."

        text = target_path.read_text(encoding="utf-8")

        if finding.code == "VAL_MISSING_ROOT_AGENT" and finding.file_path == "app/agent.py":
            # Look for a misnamed agent variable like `main_agent =` or `agent =`
            updated = re.sub(
                r"^(main_agent|my_agent|primary_agent)\s*=\s*",
                "root_agent = ",
                text,
                flags=re.MULTILINE,
            )
            if updated != text:
                target_path.write_text(updated, encoding="utf-8")
                return True, "Renamed misconfigured top-level agent variable back to `root_agent` in app/agent.py."

        if finding.code == "VAL_DEPRECATED_ADK_IMPORT":
            updated = text.replace(
                "google.adk.labs.openai", "google.adk.integrations.openai"
            ).replace(
                "google.adk.flows.llm_flows.audio_transcriber", "google.adk.live"
            )
            if updated != text:
                target_path.write_text(updated, encoding="utf-8")
                return True, f"Migrated deprecated ADK import in {finding.file_path}."

        if finding.code in ("TST_SUITE_FAILURE", "EVAL_THRESHOLD_FAILURE"):
            tools_path = project_dir / "app/tools.py"
            if tools_path.exists():
                t_text = tools_path.read_text(encoding="utf-8")
                fixed = t_text
                fixed = fixed.replace('"status": "broken"', '"status": "success"')
                fixed = fixed.replace('"status": "error_defect"', '"status": "success"')
                fixed = fixed.replace(
                    "BROKEN_DEFECT_SUMMARY",
                    "Verified domain lookup result for: {clean_query}",
                )
                if fixed != t_text:
                    tools_path.write_text(fixed, encoding="utf-8")
                    return True, "Restored tool output contract (`status='success'` and summary format) in app/tools.py."

        if finding.code == "SEC_HARDCODED_SECRET":
            from adk_agent_builder.logging import redact_sensitive_text
            redacted = redact_sensitive_text(text)
            if redacted != text:
                target_path.write_text(redacted, encoding="utf-8")
                return True, f"Redacted hardcoded secret in {finding.file_path}."

        return False, f"No automated patch rule matched {finding.code} in {finding.file_path}."
