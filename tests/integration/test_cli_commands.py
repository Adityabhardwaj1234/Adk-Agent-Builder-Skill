"""Integration tests exercising CLI commands and exit codes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.cli import main
from adk_agent_builder.errors import ExitCode


class TestCliCommands(unittest.TestCase):
    def test_doctor_and_integrations_commands(self) -> None:
        self.assertEqual(main(["doctor", "--json"]), int(ExitCode.SUCCESS))
        self.assertEqual(main(["integrations", "--json"]), int(ExitCode.SUCCESS))

    def test_skills_validate_and_package_commands(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        code = main(["skills", "--skill-dir", str(repo_root), "--json"])
        self.assertEqual(code, int(ExitCode.SUCCESS))

        sub_skill = repo_root / "adk-agent-builder"
        if sub_skill.exists():
            with tempfile.TemporaryDirectory() as tmp:
                pkg_code = main(
                    [
                        "skills",
                        "--skill-dir",
                        str(sub_skill),
                        "--package",
                        "--output-dir",
                        str(tmp),
                        "--json",
                    ]
                )
                self.assertEqual(pkg_code, int(ExitCode.SUCCESS))
                self.assertTrue((Path(tmp) / "adk-agent-builder.skill").exists())

    def test_init_plan_build_validate_test_eval_quota_dashboard_package_deploy_cli_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec_file = tmp_path / "spec.yaml"
            plan_file = tmp_path / "plan.json"
            proj_dir = tmp_path / "cli_built_agent"
            eval_report_file = tmp_path / "eval_report.json"
            dashboard_file = tmp_path / "dashboard.html"

            self.assertEqual(
                main(
                    [
                        "init",
                        "--name",
                        "cli_built_agent",
                        "--objective",
                        "Sequential pipeline for order lookup and policy compliance",
                        "--output",
                        str(spec_file),
                        "--json",
                    ]
                ),
                int(ExitCode.SUCCESS),
            )
            self.assertTrue(spec_file.exists())

            self.assertEqual(
                main(["plan", "--spec", str(spec_file), "--output", str(plan_file), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertTrue(plan_file.exists())

            self.assertEqual(
                main(
                    [
                        "build",
                        "--spec",
                        str(spec_file),
                        "--output-dir",
                        str(proj_dir),
                        "--json",
                    ]
                ),
                int(ExitCode.SUCCESS),
            )

            self.assertEqual(
                main(["validate", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["test", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["eval", "--project-dir", str(proj_dir), "--output", str(eval_report_file), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertTrue(eval_report_file.exists())

            # Test quota command on generated evalset with 20 messages/day cap
            evalset_path = proj_dir / "tests/eval/default_eval.evalset.json"
            self.assertEqual(
                main(["quota", "--spec", str(evalset_path), "--daily-limit", "20", "--json"]),
                int(ExitCode.SUCCESS),
            )

            # Test dashboard command on generated eval report
            self.assertEqual(
                main(["dashboard", "--input", str(eval_report_file), "--output", str(dashboard_file), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertTrue(dashboard_file.exists())

            self.assertEqual(
                main(["status", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["report", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["smoke-test", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["deploy", "--project-dir", str(proj_dir), "--target", "cloud_run", "--dry-run", "--json"]),
                int(ExitCode.SUCCESS),
            )
            self.assertEqual(
                main(["package", "--project-dir", str(proj_dir), "--json"]),
                int(ExitCode.SUCCESS),
            )


if __name__ == "__main__":
    unittest.main()
