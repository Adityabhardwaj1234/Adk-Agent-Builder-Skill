"""Unit tests for RequirementsEngine and ArchitecturePlanner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.errors import RequirementsValidationError
from adk_agent_builder.models.architecture import ArchitecturePattern
from adk_agent_builder.models.requirements import (
    LatencyCostExpectation,
    RequirementsSpecification,
    SecurityPrivacySpec,
)
from adk_agent_builder.planning.planner import ArchitecturePlanner
from adk_agent_builder.requirements.engine import RequirementsEngine


class TestRequirementsAndPlanner(unittest.TestCase):
    def test_natural_language_intake_and_defaults(self) -> None:
        spec = RequirementsEngine.from_natural_language(
            "Build an ADK agent that looks up weather and order tickets using custom tools"
        )
        self.assertTrue(spec.project_name.endswith("_agent"))
        self.assertIn("custom_function_tool", spec.expected_tools)
        self.assertGreaterEqual(len(spec.acceptance_criteria), 2)

    def test_empty_prompt_raises_requirements_error(self) -> None:
        with self.assertRaises(RequirementsValidationError):
            RequirementsEngine.from_natural_language("   ")

    def test_contradiction_detection_provider_and_latency(self) -> None:
        spec = RequirementsSpecification(
            project_name="conflict_agent",
            business_objective="Realtime live audio agent on ollama",
            preferred_provider="ollama",
            preferred_model="llama3",
            requires_streaming_or_live=True,
            modalities=["text", "audio"],
            latency_and_cost=LatencyCostExpectation(
                max_latency_seconds=0.3,
                quality_tier="high_reasoning",
            ),
            external_systems=["https://api.example.com"],
            expected_tools=["google_search"],
            security=SecurityPrivacySpec(allow_external_network=False),
        )
        normalized = RequirementsEngine.normalize_and_validate(spec)
        codes = {c.code for c in normalized.contradictions}
        self.assertIn("REQ_PROVIDER_CAPABILITY_MISMATCH", codes)
        self.assertIn("REQ_LATENCY_REASONING_CONFLICT", codes)
        self.assertIn("REQ_NETWORK_ISOLATION_CONFLICT", codes)

    def test_planner_selects_simplest_viable_architecture(self) -> None:
        # 1. Tool agent
        spec_tool = RequirementsEngine.from_natural_language("Lookup customer order status")
        plan_tool = ArchitecturePlanner.plan(spec_tool)
        self.assertEqual(plan_tool.selected_pattern, ArchitecturePattern.TOOL_AGENT)

        # 2. Sequential workflow
        spec_seq = RequirementsEngine.from_natural_language(
            "Run a sequential step-by-step pipeline for intake and synthesis"
        )
        plan_seq = ArchitecturePlanner.plan(spec_seq)
        self.assertEqual(plan_seq.selected_pattern, ArchitecturePattern.SEQUENTIAL_WORKFLOW)
        self.assertEqual(len(plan_seq.sub_agents), 2)

        # 3. Parallel workflow
        spec_par = RequirementsEngine.from_natural_language(
            "Execute independent research branches in parallel"
        )
        plan_par = ArchitecturePlanner.plan(spec_par)
        self.assertEqual(plan_par.selected_pattern, ArchitecturePattern.PARALLEL_WORKFLOW)

        # 4. Loop workflow
        spec_loop = RequirementsEngine.from_natural_language(
            "Iteratively refine draft in a loop with a critic"
        )
        plan_loop = ArchitecturePlanner.plan(spec_loop)
        self.assertEqual(plan_loop.selected_pattern, ArchitecturePattern.LOOP_WORKFLOW)

    def test_load_yaml_specification_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "spec.yaml"
            p.write_text(
                "project_name: demo\nbusiness_objective: Test YAML loader\n",
                encoding="utf-8",
            )
            loaded = RequirementsEngine.load_file(p)
            self.assertEqual(loaded.project_name, "demo")


if __name__ == "__main__":
    unittest.main()
