"""Contract tests verifying adapter schemas, template catalog integrity, .env secret staging checks, and deployment contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.deployment.deployer import DeploymentManager
from adk_agent_builder.errors import DeploymentBlockedError
from adk_agent_builder.models.architecture import ArchitecturePattern
from adk_agent_builder.models.evaluation import EvalConfig
from adk_agent_builder.models.providers import PROVIDER_CATALOG, ProviderType
from adk_agent_builder.templates.catalog import TEMPLATE_CATALOG, list_templates


class TestAdaptersAndSchemasContract(unittest.TestCase):
    def test_all_providers_have_valid_capability_contracts(self) -> None:
        for p_type in ProviderType:
            self.assertIn(p_type, PROVIDER_CATALOG)
            cap = PROVIDER_CATALOG[p_type]
            self.assertEqual(cap.provider, p_type)
            self.assertTrue(len(cap.adk_adapter_class) > 0)

    def test_all_templates_have_valid_metadata(self) -> None:
        templates = list_templates()
        self.assertEqual(len(templates), 11)
        covered_patterns = {t.pattern for t in templates}
        self.assertEqual(covered_patterns, set(ArchitecturePattern))
        for tmpl in templates:
            self.assertIn(tmpl.id, TEMPLATE_CATALOG)
            self.assertGreaterEqual(len(tmpl.adk_classes), 1)
            self.assertGreaterEqual(len(tmpl.included_files), 1)

    def test_deployment_contract_blocks_unapproved_billable_execution_and_audits_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p_dir = Path(tmp) / "contract_agent"
            p_dir.mkdir()
            (p_dir / ".env").write_text("GEMINI_API_KEY=LiveSecretValue12345\n", encoding="utf-8")

            # Dry-run succeeds without credentials or approval and surfaces .env staging warning
            plan = DeploymentManager.create_deployment_plan(
                p_dir,
                target="agent_runtime",
                dry_run=True,
                service_account="custom-sa@proj.iam.gserviceaccount.com",
                env={},
            )
            self.assertTrue(plan.dry_run)
            self.assertIn("--service_account=custom-sa@proj.iam.gserviceaccount.com", plan.planned_command)
            self.assertEqual(len(plan.secret_warnings), 1)
            self.assertIn("GEMINI_API_KEY", plan.secret_warnings[0])

            # Live execution without --approve-billable is strictly blocked
            with self.assertRaises(DeploymentBlockedError):
                DeploymentManager.create_deployment_plan(
                    p_dir,
                    target="cloud_run",
                    dry_run=False,
                    approve_billable=False,
                )

    def test_evalset_and_evalconfig_roundtrip_contract(self) -> None:
        raw_cfg = {"criteria": {"tool_trajectory_avg_score": 1.0, "response_match_score": 0.85}, "ignore_args": True}
        cfg = EvalConfig.from_dict(raw_cfg)
        self.assertTrue(cfg.ignore_args)
        self.assertEqual(cfg.criteria["response_match_score"], 0.85)


if __name__ == "__main__":
    unittest.main()
