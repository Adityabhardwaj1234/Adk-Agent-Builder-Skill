"""Complete 13-Step Automated End-to-End Acceptance Journey (Section 9 Requirement)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.cli import main
from adk_agent_builder.deployment.deployer import DeploymentManager
from adk_agent_builder.diagnostics.repair import DiagnosticsAndRepairEngine
from adk_agent_builder.errors import ExitCode
from adk_agent_builder.evaluation.evaluator import EvaluationEngine
from adk_agent_builder.generation.generator import ProjectGenerator
from adk_agent_builder.models.architecture import ArchitecturePattern
from adk_agent_builder.planning.planner import ArchitecturePlanner
from adk_agent_builder.requirements.engine import RequirementsEngine
from adk_agent_builder.testing.runner import TestRunner
from adk_agent_builder.validation.validator import ProjectValidator


class TestCompleteAcceptanceJourney(unittest.TestCase):
    """Verifies the complete 13-step engineering journey without requiring live external credentials."""

    def test_thirteen_step_acceptance_journey(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            # Step 1: Start with a clean example specification
            spec = RequirementsEngine.from_natural_language(
                "Build a customer order lookup agent with a custom lookup tool and policy verification",
                project_name="journey_order_agent",
            )
            spec_path = workspace / "journey_spec.yaml"
            main(
                [
                    "requirements",
                    "--from-text",
                    spec.business_objective,
                    "--name",
                    "journey_order_agent",
                    "--output",
                    str(spec_path),
                    "--json",
                ]
            )
            self.assertTrue(spec_path.exists())

            # Step 2 & Step 3: Generate a valid minimal ADK agent project using at least one real custom tool
            plan = ArchitecturePlanner.plan(spec)
            self.assertEqual(plan.selected_pattern, ArchitecturePattern.TOOL_AGENT)
            project_dir = workspace / "journey_order_agent"
            build_code = main(
                [
                    "build",
                    "--spec",
                    str(spec_path),
                    "--output-dir",
                    str(project_dir),
                    "--json",
                ]
            )
            self.assertEqual(build_code, int(ExitCode.SUCCESS))
            self.assertTrue((project_dir / "app/tools.py").exists())

            # Step 4: Add a suitable multi-agent or workflow example (SequentialAgent pipeline)
            seq_spec = RequirementsEngine.from_natural_language(
                "Run a sequential pipeline for intake analysis and compliance synthesis",
                project_name="journey_sequential_agent",
            )
            seq_plan = ArchitecturePlanner.plan(seq_spec)
            self.assertEqual(seq_plan.selected_pattern, ArchitecturePattern.SEQUENTIAL_WORKFLOW)
            seq_dir = workspace / "journey_sequential_agent"
            ProjectGenerator.generate_project(seq_spec, seq_plan, seq_dir)
            self.assertTrue(ProjectValidator.validate_project(seq_dir).valid)

            # Step 5: Run automated validation and unit tests
            val_report = ProjectValidator.validate_project(project_dir)
            self.assertTrue(val_report.valid)
            unit_result = TestRunner.run_tests(project_dir)
            self.assertTrue(unit_result.passed)
            self.assertGreaterEqual(unit_result.passed_tests, 5)

            # Step 6: Run a mocked end-to-end execution
            smoke_result = DeploymentManager.run_smoke_test(project_dir, target="local")
            self.assertTrue(smoke_result.passed)
            self.assertEqual(smoke_result.health_status, "healthy")

            # Step 7: Run an evaluation dataset and produce a report
            eval_report_path = workspace / "eval_report.json"
            eval_report = EvaluationEngine.evaluate_project(project_dir)
            eval_report_path.write_text(eval_report.to_json(indent=2), encoding="utf-8")
            self.assertTrue(eval_report.overall_passed)
            self.assertEqual(eval_report.aggregate_scores["tool_trajectory_avg_score"], 1.0)
            self.assertGreaterEqual(eval_report.aggregate_scores["response_match_score"], 0.8)

            # Step 8: Detect an intentionally introduced defect
            tools_py = project_dir / "app/tools.py"
            original_tools = tools_py.read_text(encoding="utf-8")
            defective_tools = original_tools.replace(
                '"status": "success"', '"status": "broken"'
            ).replace(
                "Verified domain lookup result for: {clean_query}",
                "BROKEN_DEFECT_SUMMARY",
            )
            tools_py.write_text(defective_tools, encoding="utf-8")

            diags = DiagnosticsAndRepairEngine.diagnose_project(project_dir)
            self.assertGreaterEqual(len(diags), 1)
            diag_codes = {d.code for d in diags}
            self.assertTrue(
                "TST_SUITE_FAILURE" in diag_codes or "EVAL_THRESHOLD_FAILURE" in diag_codes
            )

            # Step 9: Demonstrate diagnostic and bounded repair behavior
            repair_report = DiagnosticsAndRepairEngine.run_bounded_repair(project_dir, max_attempts=3)
            self.assertFalse(repair_report.initial_healthy)
            self.assertTrue(repair_report.final_healthy)
            self.assertGreaterEqual(len(repair_report.repair_history), 1)
            self.assertTrue(TestRunner.run_tests(project_dir).passed)
            self.assertTrue(EvaluationEngine.evaluate_project(project_dir).overall_passed)

            # Step 10: Package the generated project
            zip_path = DeploymentManager.package_project(project_dir)
            self.assertTrue(zip_path.exists())
            self.assertGreater(zip_path.stat().st_size, 1000)

            # Step 11 & Step 12: Validate configuration for a supported deployment target & verify dry-run workflow
            dep_plan = DeploymentManager.create_deployment_plan(
                project_dir,
                target="cloud_run",
                dry_run=True,
                env={"GOOGLE_CLOUD_PROJECT": "demo-gcp-project", "GOOGLE_CLOUD_LOCATION": "us-central1"},
            )
            self.assertTrue(dep_plan.dry_run)
            self.assertTrue(dep_plan.prerequisites_satisfied)
            self.assertIn("adk deploy cloud_run", dep_plan.planned_command)

            # Step 13: Verify the lifecycle report and troubleshooting documentation
            lifecycle_report_path = workspace / "lifecycle_report.json"
            rep_code = main(
                [
                    "report",
                    "--project-dir",
                    str(project_dir),
                    "--output",
                    str(lifecycle_report_path),
                    "--json",
                ]
            )
            self.assertEqual(rep_code, int(ExitCode.SUCCESS))
            rep_data = json.loads(lifecycle_report_path.read_text(encoding="utf-8"))
            self.assertEqual(rep_data["lifecycle"]["overall_status"], "completed")
            self.assertTrue(rep_data["validation"]["valid"])
            self.assertTrue(rep_data["security"]["passed"])


if __name__ == "__main__":
    unittest.main()
