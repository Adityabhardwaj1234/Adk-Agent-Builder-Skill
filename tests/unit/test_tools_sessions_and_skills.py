"""Unit tests for IntegrationRegistry, LocalSessionService, SQLiteMemoryService, IsolatedArtifactService, and SkillValidator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adk_agent_builder.sessions.manager import (
    IsolatedArtifactService,
    LocalSessionService,
    SQLiteMemoryService,
    SessionEvent,
    SessionNotFoundError,
)
from adk_agent_builder.skills.validator import SkillValidator
from adk_agent_builder.tools.registry import IntegrationRegistry, ToolIntegrationSpec, IntegrationStatus


class TestToolsSessionsAndSkills(unittest.TestCase):
    def test_integration_registry_and_custom_registration(self) -> None:
        reg = IntegrationRegistry()
        all_specs = reg.list_all()
        self.assertGreaterEqual(len(all_specs), 12)
        custom = ToolIntegrationSpec(
            id="crm_connector",
            name="Custom CRM Connector",
            category="enterprise",
            status=IntegrationStatus.IMPLEMENTED,
            adk_import_path="app.tools",
            adk_class_or_symbol="crm_lookup",
            requires_credentials=True,
            required_env_vars=["CRM_API_TOKEN"],
        )
        reg.register(custom)
        self.assertIsNotNone(reg.get("crm_connector"))
        health_missing = reg.check_health("crm_connector", env={})
        self.assertFalse(health_missing["healthy"])
        health_ok = reg.check_health("crm_connector", env={"CRM_API_TOKEN": "present"})
        self.assertTrue(health_ok["healthy"])

    def test_session_service_sqlite_rewind_and_compaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "sessions.db"
            svc = LocalSessionService(sqlite_path=db_file)

            # Appending to non-existent session raises SessionNotFoundError (ADK v2.9.0+)
            with self.assertRaises(SessionNotFoundError):
                svc.append_event(
                    app_name="app1",
                    user_id="u1",
                    session_id="missing",
                    event=SessionEvent(invocation_id="inv0", author="user", role="user", text="hi"),
                )

            sess = svc.create_session(
                app_name="app1",
                user_id="u1",
                session_id="s1",
                initial_state={"counter": 0},
            )
            self.assertEqual(sess.state["counter"], 0)

            svc.append_event(
                app_name="app1",
                user_id="u1",
                session_id="s1",
                event=SessionEvent(
                    invocation_id="inv1",
                    author="agent",
                    role="model",
                    text="step 1 done",
                    state_delta={"counter": 1},
                ),
            )
            svc.append_event(
                app_name="app1",
                user_id="u1",
                session_id="s1",
                event=SessionEvent(
                    invocation_id="inv2",
                    author="agent",
                    role="model",
                    text="step 2 done",
                    state_delta={"counter": 2},
                ),
            )

            # Rewind before inv2
            rewound = svc.rewind_session(
                app_name="app1",
                user_id="u1",
                session_id="s1",
                target_invocation_id="inv2",
            )
            self.assertEqual(len(rewound.events), 1)
            self.assertEqual(rewound.state["counter"], 1)

            # Compaction
            for idx in range(5):
                svc.append_event(
                    app_name="app1",
                    user_id="u1",
                    session_id="s1",
                    event=SessionEvent(
                        invocation_id=f"extra-{idx}",
                        author="user",
                        role="user",
                        text=f"turn {idx}",
                    ),
                )
            compacted = svc.compact_context(
                app_name="app1", user_id="u1", session_id="s1", keep_recent_turns=2
            )
            self.assertTrue(compacted["compacted"])

            # Memory service is distinct from session storage
            mem_svc = SQLiteMemoryService(Path(tmp) / "memory.db")
            latest_sess = svc.get_session(app_name="app1", user_id="u1", session_id="s1")
            ingested = mem_svc.ingest_session(latest_sess, topic="order_history")
            self.assertGreaterEqual(ingested, 5)
            found = mem_svc.search_memories(app_name="app1", user_id="u1", query="step 1")
            self.assertEqual(len(found), 1)
            # Isolation across user_id
            found_other_user = mem_svc.search_memories(app_name="app1", user_id="u2", query="step 1")
            self.assertEqual(len(found_other_user), 0)

    def test_artifact_service_isolation_and_negative_version(self) -> None:
        art = IsolatedArtifactService()
        buf = bytearray(b"initial-payload")
        v0 = art.save_artifact(
            app_name="app1",
            user_id="u1",
            session_id="s1",
            filename="report.txt",
            data=bytes(buf),
        )
        self.assertEqual(v0, 0)
        # Mutating caller buffer or loaded artifact must not mutate stored artifact (ADK v2.12.0)
        loaded = art.load_artifact(app_name="app1", user_id="u1", session_id="s1", filename="report.txt")
        assert loaded is not None
        loaded["data"] = b"corrupted"
        reloaded = art.load_artifact(app_name="app1", user_id="u1", session_id="s1", filename="report.txt")
        assert reloaded is not None
        self.assertEqual(reloaded["data"], b"initial-payload")

        # Negative version returns None (ADK v2.11.0 fix)
        self.assertIsNone(
            art.load_artifact(
                app_name="app1", user_id="u1", session_id="s1", filename="report.txt", version=-1
            )
        )
        # Path traversal rejected
        with self.assertRaises(ValueError):
            art.save_artifact(
                app_name="app1", user_id="u1", session_id="s1", filename="../etc/passwd", data=b"x"
            )

    def test_skill_validator_validates_repo_skill_and_rejects_traversal(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        report = SkillValidator.validate_skill_directory(repo_root)
        self.assertTrue(report.valid, f"Repo SKILL.md failed validation: {report.errors}")
        self.assertEqual(report.skill_name, "adk-agent-builder")

        with tempfile.TemporaryDirectory() as tmp:
            bad_dir = Path(tmp)
            (bad_dir / "SKILL.md").write_text(
                "---\nname: INVALID_NAME!\ndescription: short\n---\nSee [escape](../secret.txt)\n",
                encoding="utf-8",
            )
            bad_rep = SkillValidator.validate_skill_directory(bad_dir)
            self.assertFalse(bad_rep.valid)
            self.assertGreaterEqual(len(bad_rep.errors), 3)


if __name__ == "__main__":
    unittest.main()
