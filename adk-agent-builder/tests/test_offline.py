#!/usr/bin/env python3
"""Offline test suite for the adk-agent-builder skill.

Runs with any Python 3.10+ and a standard library only - no network, no API
key, no model calls. It validates the skill's own tooling end to end:

- quick_validate / package_skill: schema rules, exclusions, archive integrity
- testing.py helpers: classification, schema checks, event parsing, scoring
- create_agent.py: name validation and (when an ADK install is available) a
  real `adk create` scaffold in a temp directory with a fake key
- deploy_agent.py: command building, secret audit, dry-run behaviour
- dashboard.py: rendering, escaping, error codes
- documentation integrity: every scripts/ references/ assets/ path named in
  SKILL.md exists, and the skill folder validates with --strict

Optional environment variables (all tests skip cleanly when unset):
  ADK_TEST_PYTHON  python.exe of an environment with google-adk installed
  ADK_TEST_ADK     adk executable of that same environment

Run:
    python tests/test_offline.py
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
ASSETS = SKILL_ROOT / "assets"
sys.path.insert(0, str(SCRIPTS))

import create_agent  # noqa: E402
import dashboard  # noqa: E402
import deploy_agent  # noqa: E402
import package_skill  # noqa: E402
import quick_validate  # noqa: E402
import testing as testing_mod  # noqa: E402


def run_py(args: list[str], *, cwd: Path | None = None, timeout: float = 300, env_extra: dict | None = None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True,
                          errors="replace", timeout=timeout, env=env, stdin=subprocess.DEVNULL)


def make_skill(root: Path, name: str = "demo-skill", description: str = "Does demo things. Use when testing.",
               body: str = "# Demo\n\nBody.\n") -> Path:
    skill = root / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}", encoding="utf-8")
    return skill


_ADK_CACHE: dict[str, str | None] = {}


def adk_python() -> str | None:
    """Path to a python with google-adk, from ADK_TEST_PYTHON, else None (cached)."""
    if "py" not in _ADK_CACHE:
        candidate = os.environ.get("ADK_TEST_PYTHON", "").strip()
        ok = None
        if candidate and Path(candidate).exists():
            try:
                probe = subprocess.run([candidate, "-c", "import google.adk"], capture_output=True, timeout=120)
                ok = candidate if probe.returncode == 0 else None
            except Exception:
                ok = None
        _ADK_CACHE["py"] = ok
    return _ADK_CACHE["py"]


# --------------------------------------------------------------------------- quick_validate
class TestQuickValidate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qv-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_skill_passes(self):
        skill = make_skill(self.tmp)
        valid, report = quick_validate.validate_skill(skill)
        self.assertTrue(valid, report)
        self.assertNotIn("warning", report.lower(), report)

    def test_missing_skill_md(self):
        (self.tmp / "empty").mkdir()
        valid, report = quick_validate.validate_skill(self.tmp / "empty")
        self.assertFalse(valid)
        self.assertIn("SKILL.md not found", report)

    def test_missing_folder(self):
        valid, _ = quick_validate.validate_skill(self.tmp / "nope")
        self.assertFalse(valid)

    def test_bad_name_and_missing_description(self):
        skill = self.tmp / "Demo_Skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: Demo_Skill\n---\n\nBody\n", encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertFalse(valid)
        self.assertIn("Missing 'description'", report)
        self.assertIn("kebab-case", report)

    def test_angle_brackets_rejected(self):
        skill = make_skill(self.tmp, description="Uses <this> to do things")
        valid, report = quick_validate.validate_skill(skill)
        self.assertFalse(valid)
        self.assertIn("angle brackets", report)

    def test_description_too_long(self):
        skill = make_skill(self.tmp, description="x" * 1025)
        valid, report = quick_validate.validate_skill(skill)
        self.assertFalse(valid)
        self.assertIn("too long", report)

    def test_unexpected_key_rejected(self):
        skill = make_skill(self.tmp)
        text = (skill / "SKILL.md").read_text()
        (skill / "SKILL.md").write_text(text.replace("description:", "surprise: yes\ndescription:"), encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertFalse(valid)
        self.assertIn("Unexpected key", report)

    def test_name_folder_mismatch_warns_but_passes(self):
        skill = make_skill(self.tmp, name="folder-name")
        (skill / "SKILL.md").write_text(
            (skill / "SKILL.md").read_text().replace("name: folder-name", "name: other-name"), encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertTrue(valid, report)
        self.assertIn("warning", report.lower())
        valid_strict, _ = quick_validate.validate_skill(skill, strict=True)
        self.assertFalse(valid_strict)

    def test_nested_skill_md_rejected_but_excluded_dirs_ignored(self):
        skill = make_skill(self.tmp)
        (skill / "inner").mkdir()
        (skill / "inner" / "SKILL.md").write_text("---\nname: inner\n---\n", encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertFalse(valid)
        self.assertIn("exactly one SKILL.md", report)
        shutil.rmtree(skill / "inner")
        ignored = skill / "tests"
        ignored.mkdir()
        (ignored / "SKILL.md").write_text("---\nname: ignored\n---\n", encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertTrue(valid, report)

    def test_missing_referenced_path_warns_outside_code_fences_only(self):
        body = ("# Demo\n\nRun `scripts/real.py` and check `references/guide.md`.\n\n"
                "```\nexamples/made/up/path.py\n```\n")
        skill = make_skill(self.tmp, body=body)
        (skill / "scripts").mkdir()
        (skill / "scripts" / "real.py").write_text("# ok\n", encoding="utf-8")
        valid, report = quick_validate.validate_skill(skill)
        self.assertTrue(valid, report)
        self.assertIn("references/guide.md", report)
        self.assertNotIn("examples/made", report)  # inside a fence: not a real reference


# --------------------------------------------------------------------------- package_skill
class TestPackageSkill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pkg-"))
        self.skill = make_skill(self.tmp, name="pkg-demo")
        for rel, text in [
            ("scripts/tool.py", "print('hi')\n"),
            ("references/doc.md", "# doc\n"),
            ("assets/data.txt", "x\n"),
            ("README.md", "# readme\n"),
        ]:
            p = self.skill / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        for rel, text in [
            (".env", "GOOGLE_API_KEY=AIzaShouldNotShip\n"),
            ("adk_runs/sessions.db", "binary-ish\n"),
            ("__pycache__/junk.pyc", "junk\n"),
            ("tests/test_inner.py", "def test(): pass\n"),
            (".venv/lib/thing.py", "# venv\n"),
            ("notes.log", "log\n"),
        ]:
            p = self.skill / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_package_creates_clean_archive(self):
        out_dir = self.tmp / "dist"
        result = package_skill.package_skill(self.skill, out_dir)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "pkg-demo.skill")
        import zipfile
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            self.assertIn("pkg-demo/SKILL.md", names)
            self.assertIn("pkg-demo/scripts/tool.py", names)
            self.assertIn("pkg-demo/references/doc.md", names)
            self.assertIn("pkg-demo/assets/data.txt", names)
            self.assertIn("pkg-demo/README.md", names)
            for forbidden in (".env", "sessions.db", "__pycache__", "tests/", ".venv", ".log"):
                self.assertFalse(any(forbidden in n for n in names), f"{forbidden} leaked into {names}")

    def test_invalid_skill_is_not_packaged(self):
        bad = self.tmp / "bad-skill"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---\nname: bad-skill\n---\n", encoding="utf-8")  # no description
        result = package_skill.package_skill(bad, self.tmp / "dist")
        self.assertIsNone(result)
        self.assertFalse((self.tmp / "dist" / "bad-skill.skill").exists())

    def test_dry_run_writes_nothing(self):
        out_dir = self.tmp / "dist"
        result = package_skill.package_skill(self.skill, out_dir, dry_run=True)
        self.assertIsNotNone(result)
        self.assertFalse(result.exists())


# --------------------------------------------------------------------------- testing.py helpers
class TestTestingHelpers(unittest.TestCase):
    def test_classify(self):
        cases = [
            ("API key not valid. Please pass a valid API key.", "AUTH_INVALID_KEY"),
            ("ConnectError: [Errno 11001] getaddrinfo failed", "INFRA_NETWORK"),
            ("httpx.ConnectError while calling; API_KEY_INVALID", "INFRA_NETWORK"),  # network wins
            ("429 Too Many Requests", "QUOTA_OR_RATE_LIMIT"),
            ("RESOURCE_EXHAUSTED: quota exceeded for model", "QUOTA_OR_RATE_LIMIT"),
            ("models/gemini-9 does not exist: model not found", "MODEL_NOT_FOUND"),
            ("everything is fine", None),
        ]
        for blob, expected in cases:
            self.assertEqual(testing_mod.classify(blob), expected, blob)

    def test_subset(self):
        self.assertTrue(testing_mod.subset({"a": 1}, {"a": 1, "b": 2}))
        self.assertTrue(testing_mod.subset({"a": {"b": [1]}}, {"a": {"b": [1, 2], "c": 3}}))
        self.assertFalse(testing_mod.subset({"a": 2}, {"a": 1}))
        self.assertFalse(testing_mod.subset({"a": 1}, {"b": 1}))
        self.assertFalse(testing_mod.subset({"a": [1, 9]}, {"a": [1, 2]}))

    def test_validate_schema_subset_of_jsonschema(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "string", "enum": ["x", "y"]},
                "c": {"type": "array", "items": {"type": "string"}},
            },
        }
        self.assertEqual(testing_mod.validate_schema({"a": 1, "b": "x", "c": ["s"]}, schema), [])
        errors = testing_mod.validate_schema({"b": "z"}, schema)
        self.assertTrue(any("missing required 'a'" in e for e in errors))
        self.assertTrue(any("not in enum" in e for e in errors))
        bool_error = testing_mod.validate_schema({"a": True}, schema)
        self.assertTrue(any("expected integer, got bool" in e for e in bool_error))
        item_error = testing_mod.validate_schema({"a": 1, "c": ["s", 2]}, schema)
        self.assertTrue(any("c[1]" in e for e in item_error))
        self.assertTrue(testing_mod.validate_schema(5, {"type": "object"}))

    def _events(self):
        return [
            {"author": "user", "content": {"parts": [{"text": "hi"}]}},
            {"author": "root", "content": {"parts": [{"text": "thinking...", "thought": True}]}},
            {"author": "root", "content": {"parts": [{"functionCall": {"name": "lookup_order", "args": {"order_id": "A100"}}}]},
             "usageMetadata": {"totalTokenCount": 10}},
            {"author": "tools", "content": {"parts": [{"functionResponse": {"name": "lookup_order", "response": {"status": "success"}}}]},
             "usageMetadata": {"totalTokenCount": 5}},
            {"author": "root", "content": {"parts": [{"text": "It shipped."}]},
             "actions": {"stateDelta": {"k": 1}, "transferToAgent": "order_support", "route": ["BUG"]}},
        ]

    def test_parse_events(self):
        parsed = testing_mod.parse_events(self._events())
        self.assertEqual([c["tool"] for c in parsed["calls"]], ["lookup_order"])
        self.assertEqual(parsed["calls"][0]["args"], {"order_id": "A100"})
        self.assertEqual(parsed["authors"], ["root", "tools"])
        self.assertEqual(parsed["final_text"], "It shipped.")
        self.assertEqual(parsed["transfers"], ["order_support"])
        self.assertEqual(parsed["routes"], [["BUG"]])
        self.assertEqual(parsed["state_delta"], {"k": 1})
        self.assertEqual(parsed["tokens"], 15)
        self.assertEqual(parsed["n_events"], 5)
        self.assertEqual(len(parsed["texts"]), 1)  # thought suppressed, call event has no text

    def test_parse_events_errors_and_empty(self):
        parsed = testing_mod.parse_events([{"author": "root", "errorCode": "X", "errorMessage": "boom"}])
        self.assertEqual(parsed["errors"], ["X: boom"])
        self.assertEqual(parsed["n_events"], 1)
        empty = testing_mod.parse_events(None)
        self.assertEqual(empty["calls"], [])
        self.assertEqual(empty["final_text"], "")

    def test_evaluate_checks(self):
        parsed = testing_mod.parse_events(self._events())
        parsed["http_error"] = ""
        state = {"user:name": "Ada", "extra": {"n": 1}}
        expect = {
            "response_contains": ["shipped"],
            "response_not_contains": ["cancelled"],
            "response_regex": [r"shipped\."],
            "tool_calls_include": ["lookup_order"],
            "tool_calls_exclude": ["apply_refund"],
            "tool_args": [{"tool": "lookup_order", "args_subset": {"order_id": "A100"}}],
            "max_tool_calls": 1,
            "agents_involved": ["order_support"],
            "agents_excluded": ["billing"],
            "routes_include": ["BUG"],
            "state_contains": {"extra": {"n": 1}},
            "state_keys": ["user:name"],
            "max_latency_s": 5.0,
            "min_chars": 5,
        }
        checks = {c["check"]: c for c in testing_mod.evaluate(expect, parsed, state, 3.2)}
        self.assertTrue(checks["response_contains 'shipped'"]["ok"])
        self.assertTrue(checks["response_not_contains 'cancelled'"]["ok"])
        self.assertTrue(checks["response_regex /shipped\\./"]["ok"])
        self.assertTrue(checks["tool_called lookup_order"]["ok"])
        self.assertTrue(checks["tool_not_called apply_refund"]["ok"])
        self.assertTrue(checks["tool_args lookup_order"]["ok"])
        self.assertTrue(checks["max_tool_calls"]["ok"])
        self.assertTrue(checks["agent_involved order_support"]["ok"])
        self.assertTrue(checks["agent_excluded billing"]["ok"])
        self.assertTrue(checks["route_taken BUG"]["ok"])
        self.assertTrue(checks["state_contains extra"]["ok"])
        self.assertTrue(checks["state_key user:name"]["ok"])
        self.assertTrue(checks["max_latency_s"]["ok"])
        self.assertTrue(checks["no_error"]["ok"])

    def test_evaluate_failures_carry_detail(self):
        parsed = testing_mod.parse_events(self._events())
        parsed["http_error"] = ""
        expect = {"response_contains": ["cancelled"], "tool_calls_include": ["missing_tool"],
                  "max_tool_calls": 0, "response_not_contains": ["shipped"],
                  "max_latency_s": 1.0}
        checks = {c["check"]: c for c in testing_mod.evaluate(expect, parsed, {}, 9.9)}
        self.assertFalse(checks["response_contains 'cancelled'"]["ok"])
        self.assertIn("response was", checks["response_contains 'cancelled'"]["detail"])
        self.assertFalse(checks["tool_called missing_tool"]["ok"])
        self.assertFalse(checks["max_tool_calls"]["ok"])
        self.assertFalse(checks["response_not_contains 'shipped'"]["ok"])
        self.assertFalse(checks["max_latency_s"]["ok"])

    def test_evaluate_json_fence_and_schema(self):
        run = testing_mod.parse_events([{"author": "root", "content": {"parts": [{"text": '```json\n{"a": 1}\n```'}]}}])
        run["http_error"] = ""
        checks = {c["check"]: c for c in testing_mod.evaluate(
            {"json_valid": True, "json_schema": {"type": "object", "required": ["b"]}}, run, {}, 1.0)}
        self.assertTrue(checks["json_valid"]["ok"])
        self.assertFalse(checks["json_schema"]["ok"])
        self.assertIn("missing required 'b'", checks["json_schema"]["detail"])

    def test_make_skeleton_mentions_tools_and_subagents(self):
        info = {"tree": {"name": "root", "tools": ["lookup_order", "transfer_to_agent"],
                         "sub_agents": [{"name": "billing", "tools": ["apply_refund"], "sub_agents": []}]}}
        spec = testing_mod.make_skeleton(info)
        ids = {t["id"] for t in spec["tests"]}
        self.assertIn("T_smoke", ids)
        self.assertIn("T_tool_lookup_order", ids)
        self.assertIn("T_route_billing", ids)
        self.assertIn("T_tool_apply_refund", ids)
        self.assertNotIn("transfer_to_agent", json.dumps(spec))

    def test_log_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "server.log"
            log.write_text("abc", encoding="utf-8")
            offset = testing_mod.log_size(log)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("def")
            self.assertEqual(testing_mod.log_window(log, offset), "def")
            self.assertEqual(testing_mod.log_window(None, 0), "")
        self.assertEqual(testing_mod.log_size(Path("does-not-exist.log")), 0)

    def test_cli_help(self):
        proc = run_py([str(SCRIPTS / "testing.py"), "--help"], timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for flag in ("--min-interval", "--retry-infra", "--server-log", "--base-url"):
            self.assertIn(flag, proc.stdout)


# --------------------------------------------------------------------------- create_agent
class TestCreateAgent(unittest.TestCase):
    def test_validate_app_name(self):
        for good in ("a", "support_desk", "ABC-def-1"):
            self.assertIsNone(create_agent.validate_app_name(good), good)
        for bad in ("", "1abc", "a b", "a/b", "user"):
            self.assertIsNotNone(create_agent.validate_app_name(bad), bad)

    def test_resolve_api_key_sources(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            key, source = create_agent.resolve_api_key(None)
            self.assertEqual((key, source), (create_agent.PLACEHOLDER_KEY, "placeholder"))
            key, source = create_agent.resolve_api_key("flag-key")
            self.assertEqual((key, source), ("flag-key", "argument"))
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "env-key"}):
            self.assertEqual(create_agent.resolve_api_key(None), ("env-key", "env"))
            self.assertEqual(create_agent.resolve_api_key("flag-key"), ("flag-key", "argument"))

    def test_cli_help(self):
        proc = run_py([str(SCRIPTS / "create_agent.py"), "--help"], timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--no-venv", proc.stdout)
        self.assertIn("--workspace", proc.stdout)

    @unittest.skipUnless(os.environ.get("ADK_TEST_ADK") and adk_python(),
                         "set ADK_TEST_PYTHON/ADK_TEST_ADK to run the real adk create scaffold test")
    def test_real_adk_create_scaffold(self):
        """Runs the real `adk create` against a temp workspace using the
        supplied ADK install and a fake key - fully offline (no model calls)."""
        with tempfile.TemporaryDirectory(prefix="adk-e2e-") as tmp:
            tmp = Path(tmp)
            report_path = tmp / "create_report.json"
            proc = run_py([str(SCRIPTS / "create_agent.py"), "e2e_demo",
                           "--workspace", str(tmp), "--no-venv", "--skip-install",
                           "--python", adk_python(), "--adk", os.environ["ADK_TEST_ADK"],
                           "--api-key", "FAKE_KEY_OFFLINE_TEST",
                           "--json-out", str(report_path)], timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["success"], report)
            app_dir = tmp / "e2e_demo"
            for f in ("agent.py", "__init__.py", ".env"):
                self.assertTrue((app_dir / f).exists(), f)
            self.assertIn("FAKE_KEY_OFFLINE_TEST", (app_dir / ".env").read_text(encoding="utf-8"))
            self.assertIn("gemini-2.5-flash", (app_dir / "agent.py").read_text(encoding="utf-8"))
            self.assertTrue(any(s["name"] == "adk create" and s["ok"] for s in report["steps"]))

            again = run_py([str(SCRIPTS / "create_agent.py"), "e2e_demo",
                            "--workspace", str(tmp), "--no-venv", "--skip-install",
                            "--python", adk_python(), "--adk", os.environ["ADK_TEST_ADK"],
                            "--api-key", "FAKE_KEY_OFFLINE_TEST",
                            "--json-out", str(report_path)], timeout=300)
            self.assertEqual(again.returncode, 4, "existing non-empty app folder must be refused without --force")


# --------------------------------------------------------------------------- deploy_agent
class TestDeployAgent(unittest.TestCase):
    def _app(self, tmp: Path) -> Path:
        app = tmp / "demo_app"
        app.mkdir()
        (app / "agent.py").write_text("root_agent = None\n", encoding="utf-8")
        (app / ".env").write_text("GOOGLE_GENAI_USE_ENTERPRISE=0\nGOOGLE_API_KEY=AIzaFAKE123456789012\n",
                                  encoding="utf-8")
        return app

    def test_build_command(self):
        args = mock.Mock(mode="cloud_run", project="proj", region="us-central1", service_name="svc",
                         with_ui=True, app_name=None, env=["A=1", "B=2"], api_key=None, engine_id=None,
                         display_name=None, description=None, extra=["--min-instances=1"])
        cmd = deploy_agent.build_command("adk", Path("app"), args)
        self.assertEqual(cmd[:3], ["adk", "deploy", "cloud_run"])
        for token in ("--project", "proj", "--region", "us-central1", "--service_name", "svc", "--with_ui",
                      "--env", "A=1", "B=2", "--min-instances=1"):
            self.assertIn(token, cmd)

    def test_secret_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            warnings = deploy_agent.secret_warnings(deploy_agent.read_env_keys(app))
            self.assertTrue(any("GOOGLE_API_KEY" in w for w in warnings))
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "clean"
            app.mkdir()
            (app / ".env").write_text("GOOGLE_GENAI_USE_ENTERPRISE=0\nGOOGLE_API_KEY=YOUR_API_KEY\n", encoding="utf-8")
            warnings = deploy_agent.secret_warnings(deploy_agent.read_env_keys(app))
            self.assertEqual(warnings, [])

    def test_dry_run_and_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            app = self._app(tmp)
            proc = run_py([str(SCRIPTS / "deploy_agent.py"), str(app), "--mode", "cloud_run", "--dry-run"],
                          timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads((tmp / "adk_runs" / "deploy_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["dry_run"])
            self.assertEqual(report["exit_code"], None)
            self.assertIn("deploy cloud_run", report["command"])
            self.assertTrue(any("GOOGLE_API_KEY" in w for w in report["warnings"]))
            empty = tmp / "empty_app"
            empty.mkdir()
            proc = run_py([str(SCRIPTS / "deploy_agent.py"), str(empty), "--mode", "cloud_run", "--dry-run"],
                          timeout=120)
            self.assertEqual(proc.returncode, 3)


# --------------------------------------------------------------------------- dashboard
class TestDashboard(unittest.TestCase):
    def _results(self) -> dict:
        return {
            "summary": {
                "verdict": "NEEDS_FIX", "app": "demo", "tests_total": 2, "tests_passed": 1,
                "pass_rate": 0.5, "must_total": 2, "must_passed": 1, "flaky": [],
                "retried": [], "quota_reclassified": [],
                "by_category": {"functional": {"total": 2, "passed": 1}},
                "requirements": {"R1": {"tests": 2, "passed": 1, "text": "works", "severity": "must",
                                        "status": "NOT_MET"}},
                "latency": {"p50_s": 1.0, "p95_s": 2.0, "max_s": 2.0, "mean_s": 1.5},
                "tokens_total": 10, "avg_tool_calls": 1.0, "failure_classes": {"ASSERTION_FAILED": 1},
                "output_dir": "x",
            },
            "results": [
                {"test_id": "T01", "passed": True, "severity": "must", "category": "functional",
                 "latency_s": [1.0], "tokens": 5, "tool_calls": ["lookup_order"], "retries": 0,
                 "failed_checks": [], "final_response": "ok", "agents": ["root"],
                 "first_user_input": "hi"},
                {"test_id": "T02", "passed": False, "severity": "must", "category": "functional",
                 "failure_class": "ASSERTION_FAILED", "latency_s": [2.0], "tokens": 5,
                 "tool_calls": ["missing_tool"], "retries": 1,
                 "failed_checks": [{"check": "response_contains 'x'", "detail": "d", "hint": "helpful hint"}],
                 "final_response": "<script>alert(1)</script>", "agents": ["root"],
                 "first_user_input": "hi"},
            ],
        }

    def test_render_escapes_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            results = tmp / "results.json"
            results.write_text(json.dumps(self._results()), encoding="utf-8")
            proc = run_py([str(SCRIPTS / "dashboard.py"), "--results", str(results)], timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            html = (tmp / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("NEEDS_FIX", html)
            self.assertIn("T02", html)
            self.assertIn("helpful hint", html)
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)

    def test_bad_input_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_py([str(SCRIPTS / "dashboard.py"), "--results", str(Path(tmp) / "missing.json")], timeout=60)
            self.assertEqual(proc.returncode, 2)


# --------------------------------------------------------------------------- docs, assets, packaging of the real skill
class TestSkillIntegrity(unittest.TestCase):
    def test_skill_validates_strict(self):
        valid, report = quick_validate.validate_skill(SKILL_ROOT, strict=True)
        self.assertTrue(valid, report)

    def test_quick_validate_cli_strict(self):
        # cwd + "." is how a human runs it from inside the skill folder; the
        # folder name must resolve correctly for the name check.
        proc = run_py([str(SCRIPTS / "quick_validate.py"), ".", "--strict"], cwd=SKILL_ROOT, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_all_python_files_compile(self):
        files = sorted(list(SCRIPTS.glob("*.py")) + list(ASSETS.glob("*.py")))
        self.assertGreaterEqual(len(files), 7)
        for f in files:
            with self.subTest(file=f.name):
                compile(f.read_text(encoding="utf-8"), str(f), "exec")

    def test_spec_example_is_valid(self):
        spec = json.loads((ASSETS / "spec_example.json").read_text(encoding="utf-8"))
        self.assertNotIn("TODO", json.dumps(spec))
        self.assertGreaterEqual(len(spec["tests"]), 8)
        req_ids = {r["id"] for r in spec["requirements"]}
        for r in spec["requirements"]:
            self.assertIn(r["severity"], ("must", "should"))
        for t in spec["tests"]:
            self.assertTrue(t.get("id") and t.get("turns"), t)
            self.assertIn(t["severity"], ("must", "should"), t["id"])
            self.assertTrue(set(t["requirement_ids"]) <= req_ids, t["id"])

    @unittest.skipUnless(adk_python(), "set ADK_TEST_PYTHON to run ADK-backed asset tests")
    def test_asset_templates_build_against_adk(self):
        py = adk_python()
        with tempfile.TemporaryDirectory(prefix="assets-") as tmp:
            tmp = Path(tmp)

            multi_driver = tmp / "multi.py"
            multi_driver.write_text(
                "import importlib.util\n"
                f"spec = importlib.util.spec_from_file_location('multi', r'{ASSETS / 'multi_agent_agent.py'}')\n"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "print(m.root_agent.name)\n"
                "print([s.name for s in m.root_agent.sub_agents])\n"
                "print(m.lookup_order('A100')['status'], m.lookup_order('ZZZ')['status'])\n",
                encoding="utf-8")
            proc = subprocess.run([py, str(multi_driver)], capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("support_desk", proc.stdout)
            self.assertIn("order_support", proc.stdout)
            self.assertIn("success error", proc.stdout)

            graph_driver = tmp / "graph.py"
            graph_driver.write_text(
                "import importlib.util\n"
                f"spec = importlib.util.spec_from_file_location('graph', r'{ASSETS / 'graph_agent.py'}')\n"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "r = m.build_routing_workflow(); f = m.build_fanout_workflow()\n"
                "print(type(r).__name__, type(f).__name__)\n",
                encoding="utf-8")
            proc = subprocess.run([py, str(graph_driver)], capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Workflow Workflow", proc.stdout)

            sqlite_driver = tmp / "sqlite_run.py"
            sqlite_driver.write_text(
                "import importlib.util\n"
                f"spec = importlib.util.spec_from_file_location('sq', r'{ASSETS / 'sqlite_tools.py'}')\n"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "print(m.init_db()['status'])\n"
                "print(m.lookup_order('A100')['status'], m.lookup_order('nope')['status'])\n"
                "print(m.create_request('bad-email', 'short')['status'])\n"
                "print(m.create_request('ada@example.com', 'Printer jams every morning.')['status'])\n"
                "print(m.list_requests('ADA@example.com')['count'])\n",
                encoding="utf-8")
            env = os.environ.copy()
            env["APP_DB_PATH"] = str(tmp / "app.db")
            proc = subprocess.run([py, str(sqlite_driver)], capture_output=True, text=True, timeout=180, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.split(), ["success", "success", "error", "error", "success", "1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
