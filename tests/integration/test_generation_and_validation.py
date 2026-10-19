"""Integration tests verifying project generation, validation, and evaluation across all ADK workflow patterns."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.deployment.deployer import DeploymentManager
from adk_agent_builder.evaluation.evaluator import EvaluationEngine
from adk_agent_builder.generation.generator import ProjectGenerator
from adk_agent_builder.planning.planner import ArchitecturePlanner
from adk_agent_builder.requirements.engine import RequirementsEngine
from adk_agent_builder.security.scanner import SecurityScanner
from adk_agent_builder.testing.runner import TestRunner
from adk_agent_builder.validation.validator import ProjectValidator


class TestGenerationAndValidationAllPatterns(unittest.TestCase):
    def test_generate_and_verify_multiple_workflow_topologies(self) -> None:
        prompts = [
            ("simple_lookup", "Look up customer order status using a custom tool"),
            ("seq_pipeline", "Execute a sequential step-by-step pipeline for intake and compliance"),
            ("par_branches", "Run independent research and compliance branches in parallel"),
            ("loop_refiner", "Iteratively refine draft in a loop with a critic"),
            ("mcp_connector", "Connect to an MCP server using MCPToolset"),
            ("rag_grounding", "Retrieve grounded knowledge base chunks using RAG"),
            ("a2a_service", "Expose and consume a remote agent over the A2A protocol"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, prompt in prompts:
                with self.subTest(pattern_project=name):
                    spec = RequirementsEngine.from_natural_language(prompt, project_name=name)
                    plan = ArchitecturePlanner.plan(spec)
                    proj_dir = root / name
                    files = ProjectGenerator.generate_project(spec, plan, proj_dir)
                    self.assertGreaterEqual(len(files), 15)

                    val = ProjectValidator.validate_project(proj_dir)
                    self.assertTrue(val.valid, f"Validation failed for {name}: {val.issues}")

                    sec = SecurityScanner.scan_project(proj_dir)
                    self.assertTrue(sec.passed, f"Security scan failed for {name}: {sec.findings}")

                    eval_rep = EvaluationEngine.evaluate_project(proj_dir)
                    self.assertTrue(eval_rep.overall_passed, f"Eval failed for {name}: {eval_rep.case_results}")

                    smoke = DeploymentManager.run_smoke_test(proj_dir)
                    self.assertTrue(smoke.passed, f"Smoke test failed for {name}: {smoke.errors}")

            # Also run full subprocess test suite on one multi-agent workflow project
            tst = TestRunner.run_tests(root / "par_branches")
            self.assertTrue(tst.passed)
            self.assertEqual(tst.passed_tests, 7)


if __name__ == "__main__":
    unittest.main()
