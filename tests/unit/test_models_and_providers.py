"""Unit tests for domain models, lifecycle checkpoints, providers, logging redaction, and telemetry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.config import BuilderConfig
from adk_agent_builder.logging import redact_dict, redact_sensitive_text
from adk_agent_builder.models.lifecycle import EngineeringRunState, LifecycleStage, StageStatus
from adk_agent_builder.models.providers import ModelProviderConfig, ProviderType
from adk_agent_builder.telemetry import TelemetryRecorder


class TestModelsAndProviders(unittest.TestCase):
    def test_secret_redaction_covers_tokens_and_dicts(self) -> None:
        # Construct synthetic test tokens dynamically so source files contain zero literal token strings
        fake_aq = "AQ." + ("x" * 28)
        fake_aiza = "AIza" + ("0" * 32)
        sample = f"Key is {fake_aq} and {fake_aiza}"
        redacted = redact_sensitive_text(sample)
        self.assertNotIn(fake_aq, redacted)
        self.assertNotIn(fake_aiza, redacted)
        self.assertIn("[REDACTED_SECRET]", redacted)

        nested = {"gemini_api_key": "secret-val", "nested": {"text": sample}}
        clean = redact_dict(nested)
        self.assertEqual(clean["gemini_api_key"], "[REDACTED_SECRET]")
        self.assertIn("[REDACTED_SECRET]", clean["nested"]["text"])

    def test_provider_capabilities_and_credential_checks(self) -> None:
        cfg = ModelProviderConfig(
            provider=ProviderType.GEMINI,
            model_name="gemini-2.5-flash",
            fallback_model_name="gemini-2.5-pro",
        )
        self.assertEqual(
            cfg.render_adk_model_expr(),
            'FallbackModel(models=["gemini-2.5-flash", "gemini-2.5-pro"])',
        )
        cred_missing = cfg.check_credentials_present(env={})
        self.assertFalse(cred_missing["configured"])
        cred_present = cfg.check_credentials_present(env={"GEMINI_API_KEY": "dummy"})
        self.assertTrue(cred_present["configured"])

        ollama_cfg = ModelProviderConfig(
            provider=ProviderType.OLLAMA,
            model_name="llama3.2",
            enable_model_consult=True,
        )
        issues = ollama_cfg.validate_compatibility(requires_live=True, requires_structured_output=True)
        self.assertEqual(len(issues), 3)

    def test_lifecycle_state_persistence_and_17_stages(self) -> None:
        state = EngineeringRunState(
            run_id="run-01",
            project_name="demo_agent",
            project_dir="/tmp/demo_agent",
        )
        state.initialize_all_stages()
        self.assertEqual(len(state.stages), 17)
        state.mark_stage(
            LifecycleStage.STAGE_01_REQUIREMENT_INTAKE,
            StageStatus.PASSED,
            duration_ms=12.5,
            artifacts=["requirements.yaml"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            state.save(p)
            reloaded = EngineeringRunState.load(p)
            self.assertEqual(
                reloaded.stages[LifecycleStage.STAGE_01_REQUIREMENT_INTAKE.value].status,
                StageStatus.PASSED,
            )

    def test_telemetry_recorder_and_config(self) -> None:
        rec = TelemetryRecorder(redact_prompts=True)
        with rec.span("build_step", stage="07_project_scaffolding", attributes={"prompt": "secret user text"}):
            pass
        summary = rec.summary()
        self.assertEqual(summary["metrics"]["stages_executed"], 1)
        self.assertEqual(
            summary["spans"][0]["attributes"]["prompt"],
            "[REDACTED_BY_TELEMETRY_POLICY]",
        )
        cfg = BuilderConfig.from_env_and_file(overrides={"default_model": "gemini-2.5-pro"})
        self.assertEqual(cfg.default_model, "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
