"""Evaluation, quota budget planning (20 messages/day), dashboard rendering, and self-repair tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.diagnostics.repair import DiagnosticsAndRepairEngine
from adk_agent_builder.evaluation.evaluator import EvaluationEngine
from adk_agent_builder.evaluation.quota import QuotaBudgetManager, QuotaBudgetPolicy
from adk_agent_builder.generation.generator import ProjectGenerator
from adk_agent_builder.observability.dashboard import DashboardRenderer
from adk_agent_builder.planning.planner import ArchitecturePlanner
from adk_agent_builder.requirements.engine import RequirementsEngine


class TestEvaluationAndRepair(unittest.TestCase):
    def test_empty_evalset_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p_dir = Path(tmp)
            eval_file = p_dir / "empty.evalset.json"
            eval_file.write_text(
                '{"eval_set_id": "empty", "eval_cases": []}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                EvaluationEngine.evaluate_project(p_dir, evalset_path=eval_file)

    def test_trajectory_ignore_args_and_report_comparison(self) -> None:
        expected = [{"name": "lookup", "args": {"query": "exact"}}]
        actual = [{"name": "lookup", "args": {"query": "different"}}]
        self.assertEqual(
            EvaluationEngine.compute_trajectory_score(expected, actual, ignore_args=False),
            0.0,
        )
        self.assertEqual(
            EvaluationEngine.compute_trajectory_score(expected, actual, ignore_args=True),
            1.0,
        )

    def test_quota_budget_manager_enforces_20_messages_per_day_and_slices_spec(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        apex_spec = repo_root / "Apex-HyperStore-Agent" / "adk_runs" / "spec.json"
        self.assertTrue(apex_spec.exists())

        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / ".adk_quota_ledger.json"
            policy = QuotaBudgetPolicy(
                daily_message_limit=20,
                requests_per_minute_limit=5,
                rotate_models=["gemini-2.5-flash"],
            )
            report = QuotaBudgetManager.estimate_and_plan(
                apex_spec, policy=policy, ledger_path=ledger_file, slice_size=3
            )
            self.assertEqual(report.spec_format, "http_spec")
            self.assertEqual(report.total_cases, 28)
            self.assertGreater(report.total_estimated_messages, 20)
            self.assertFalse(report.fits_in_single_model_daily_quota)
            # Total messages scheduled across recommended slices must never exceed the 20/day budget
            scheduled_msgs = sum(s.estimated_messages for s in report.recommended_slices)
            self.assertLessEqual(scheduled_msgs, 20)
            self.assertGreater(len(report.deferred_case_ids), 0)

            # Rotating across 2 models doubles effective daily capacity to 40
            policy_rot = QuotaBudgetPolicy(
                daily_message_limit=20,
                requests_per_minute_limit=5,
                rotate_models=["gemini-2.5-flash", "gemini-3.5-flash"],
            )
            rep_rot = QuotaBudgetManager.estimate_and_plan(
                apex_spec, policy=policy_rot, ledger_path=ledger_file, slice_size=4
            )
            self.assertEqual(rep_rot.effective_daily_capacity, 40)
            self.assertTrue(rep_rot.fits_in_remaining_budget)
            self.assertEqual(len(rep_rot.deferred_case_ids), 0)

            # Record usage and verify remaining budget decreases
            QuotaBudgetManager.record_usage(ledger_file, "gemini-2.5-flash", 6, run_label="slice_01_02")
            rep_after = QuotaBudgetManager.estimate_and_plan(
                apex_spec, policy=policy, ledger_path=ledger_file, slice_size=3
            )
            self.assertEqual(rep_after.consumed_today, 6)
            self.assertEqual(rep_after.remaining_today, 14)

    def test_dashboard_renderer_supports_http_results_and_eval_report(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        apex_results = repo_root / "Apex-HyperStore-Agent" / "adk_runs" / "final" / "results.json"
        self.assertTrue(apex_results.exists())

        with tempfile.TemporaryDirectory() as tmp:
            out_html = Path(tmp) / "apex_dashboard.html"
            written = DashboardRenderer.render_from_file(apex_results, out_html)
            self.assertTrue(written.exists())
            content = written.read_text(encoding="utf-8")
            self.assertIn("ADK Agent Evaluation Dashboard", content)
            self.assertIn("PASS", content)

            # Also test rendering from an ADK EvalReport JSON
            eval_json = Path(tmp) / "eval_report.json"
            eval_json.write_text(
                json.dumps(
                    {
                        "eval_set_id": "demo_eval_set",
                        "agent_version": "0.1.0",
                        "execution_mode": "deterministic_mock",
                        "total_cases": 1,
                        "passed_cases": 1,
                        "failed_cases": 0,
                        "skipped_cases": 0,
                        "overall_passed": True,
                        "aggregate_scores": {"tool_trajectory_avg_score": 1.0, "response_match_score": 1.0},
                        "aggregate_efficiency": {"tool_call_count_v1": 1.0, "token_usage_v1": 24.0},
                        "case_results": [
                            {
                                "eval_id": "case_01",
                                "status": "passed",
                                "scores": {"tool_trajectory_avg_score": 1.0},
                                "failure_reasons": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            eval_html = DashboardRenderer.render_from_file(eval_json, Path(tmp) / "eval_dashboard.html")
            self.assertTrue(eval_html.exists())
            self.assertIn("demo_eval_set", eval_html.read_text(encoding="utf-8"))

    def test_bounded_self_repair_fixes_injected_defects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = Path(tmp) / "repair_demo_agent"
            spec = RequirementsEngine.from_natural_language(
                "Build a tool agent for order lookup", project_name="repair_demo_agent"
            )
            plan = ArchitecturePlanner.plan(spec)
            ProjectGenerator.generate_project(spec, plan, proj_dir)

            # Inject defect 1: break root_agent export name in app/agent.py
            agent_py = proj_dir / "app/agent.py"
            agent_py.write_text(
                agent_py.read_text(encoding="utf-8").replace("root_agent = ", "main_agent = "),
                encoding="utf-8",
            )

            # Inject defect 2: break tool status contract in app/tools.py
            tools_py = proj_dir / "app/tools.py"
            tools_py.write_text(
                tools_py.read_text(encoding="utf-8").replace('"status": "success"', '"status": "broken"'),
                encoding="utf-8",
            )

            diags = DiagnosticsAndRepairEngine.diagnose_project(proj_dir)
            self.assertGreaterEqual(len(diags), 1)

            repair_report = DiagnosticsAndRepairEngine.run_bounded_repair(proj_dir, max_attempts=3)
            self.assertFalse(repair_report.initial_healthy)
            self.assertTrue(repair_report.final_healthy)
            self.assertLessEqual(repair_report.attempts_used, 3)


if __name__ == "__main__":
    unittest.main()
