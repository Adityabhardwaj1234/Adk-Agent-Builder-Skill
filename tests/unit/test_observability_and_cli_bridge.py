"""Unit tests for ObservabilityManager and AdkCliAdapter."""

from __future__ import annotations

import unittest
from pathlib import Path

from adk_agent_builder.integrations.adk_cli import AdkCliAdapter
from adk_agent_builder.observability.manager import ObservabilityConfig, ObservabilityManager


class TestObservabilityAndCliBridge(unittest.TestCase):
    def test_exporter_validation_and_manifest(self) -> None:
        res = ObservabilityManager.validate_exporters(
            ["opentelemetry", "cloud_trace", "bigquery_agent_analytics"]
        )
        self.assertTrue(res["valid"])
        bad = ObservabilityManager.validate_exporters(["unknown_exporter"])
        self.assertFalse(bad["valid"])

        manifest = ObservabilityManager.generate_observability_manifest(
            ObservabilityConfig(
                enabled_exporters=["opentelemetry", "bigquery_agent_analytics"],
                redact_prompts_and_responses=True,
                capture_full_payloads=True,
                bq_dataset_id="agent_telemetry",
            )
        )
        self.assertTrue(manifest["bigquery_analytics"]["enabled"])
        self.assertFalse(manifest["capture_full_payloads"])  # overridden by redact_prompts_and_responses

    def test_token_cost_estimation(self) -> None:
        est = ObservabilityManager.estimate_token_cost("gemini-2.5-flash", 10_000, 2_000)
        self.assertTrue(est["pricing_documented"])
        self.assertIsNotNone(est["estimated_cost_usd"])

        unknown = ObservabilityManager.estimate_token_cost("custom-local-llm", 1000, 1000)
        self.assertFalse(unknown["pricing_documented"])
        self.assertIsNone(unknown["estimated_cost_usd"])

    def test_adk_cli_command_builder_and_detection(self) -> None:
        env_info = AdkCliAdapter.detect_environment()
        self.assertIn("adk_cli", env_info)
        self.assertIn("agents_cli", env_info)

        proj = Path("/tmp/sample_agent")
        eval_cmd = AdkCliAdapter.build_adk_command("eval", proj)
        self.assertEqual(eval_cmd[:2], ["adk", "eval"])
        run_cmd = AdkCliAdapter.build_adk_command("run", proj, state_file=Path("/tmp/state.json"))
        self.assertIn("--state_file=/tmp/state.json", run_cmd)


if __name__ == "__main__":
    unittest.main()
