#!/usr/bin/env python3
"""create_agent.py - scaffold a fresh Google ADK app in a workspace, unattended.

The ADK CLI is interactive: ``adk create`` pops a model menu, then a backend
menu, then an API-key prompt. Interactive menus are exactly wrong for an agent
that is scaffolding a project on the user's behalf - they cannot be answered,
and scraping their text breaks whenever a release reorders an option. ADK 2.x
accepts the same choices as flags, so this script never parses a menu: it
passes ``--model``, ``--api_key`` and ``--type CODE`` and lets the CLI run to
completion with a non-interactive stdin. (If stdin is not a TTY the CLI cannot
prompt for telemetry either, and telemetry is off by default; the script also
records an explicit opt-out via ``adk telemetry disable`` when the command is
available.)

What it does, in order
  1. validate the app name locally (same rule as ADK: start with a letter,
     letters/digits/underscore/hyphen after that, and not the reserved name
     ``user``) so a typo fails in milliseconds instead of after a `pip install`
  2. prepare the workspace and refuse to overwrite a non-empty app folder
     unless ``--force`` is given
  3. create ``<workspace>/.venv`` and install ``google-adk`` with extras
     (default ``db,mcp``; the ``eval`` extra is intentionally optional - see
     references/pitfalls.md for the Windows path-length caveat)
  4. run ``adk create <app> --model M --api_key K --type CODE`` from the
     workspace (the parent directory ADK expects)
  5. verify the generated files, and import the app once as a smoke test
  6. write ``<workspace>/adk_runs/create_report.json`` and print a JSON summary

Without an API key the ``.env`` receives the literal placeholder
``YOUR_API_KEY``. Structure and imports still work, but any real model call
fails with an auth error and the test harness will report ``INFRA_BLOCKED`` -
which is the honest outcome.

Usage
    python create_agent.py <app_name> --workspace ./adk_workspace
    python create_agent.py support_desk --workspace ws --api-key "$GOOGLE_API_KEY"
    python create_agent.py demo --workspace ws --model gemini-3.8-flash
    python create_agent.py demo --workspace ws --no-venv --skip-install --adk adk  # reuse an existing env

Exit codes: 0 success, 2 usage error, 3 environment failure,
            4 app folder exists (add --force to replace).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Same rule the ADK enforces (google/adk/apps/app.py: validate_app_name).
APP_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
RESERVED_APP_NAMES = {"user"}
PLACEHOLDER_KEY = "YOUR_API_KEY"
DEFAULT_MODEL = "gemini-2.5-flash"  # free-tier workable per request bucket; override with --model
DEFAULT_EXTRAS = "db,mcp"           # session/DB backend + MCP toolset support; eval extra is opt-in
TOTAL_STEPS = 7                     # 6 logged steps + the telemetry opt-out


class StepLog:
    """Collects one record per numbered step for the JSON report and the console."""

    def __init__(self) -> None:
        self.steps: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "", cmd: list[str] | None = None) -> None:
        self.steps.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
            "cmd": " ".join(str(c) for c in cmd) if cmd else None,
        })
        print(f"[create_agent] step {len(self.steps)}/{TOTAL_STEPS} {name}: "
              f"{'ok' if ok else 'FAILED'}" + (f" - {detail}" if detail else ""))


def validate_app_name(name: str) -> str | None:
    """Return an error message for an invalid app name, or None if it is valid."""
    if not APP_NAME_RE.match(name or ""):
        return (
            f"Invalid app name '{name}': must start with a letter and contain only "
            "letters, digits, underscores and hyphens (e.g. support_desk)"
        )
    if name.lower() in RESERVED_APP_NAMES:
        return f"App name '{name}' is reserved; choose another name"
    return None


def run(cmd: list[str], *, cwd: Path, timeout: float, stdin_devnull: bool = True) -> subprocess.CompletedProcess:
    """Run a command non-interactively and capture its output."""
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL if stdin_devnull else None,
    )


def tail(text: str, n: int = 500) -> str:
    text = (text or "").strip()
    return text[-n:] if text else ""


def resolve_api_key(flag_value: str | None) -> tuple[str, str]:
    """Return (key, source) where source is 'argument' | 'env' | 'placeholder'."""
    if flag_value:
        return flag_value.strip(), "argument"
    env_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if env_key:
        return env_key, "env"
    return PLACEHOLDER_KEY, "placeholder"


def venv_python(workspace: Path) -> Path:
    return workspace / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_adk(workspace: Path) -> Path:
    return workspace / ".venv" / ("Scripts/adk.exe" if os.name == "nt" else "bin/adk")


def verify_scaffold(app_dir: Path) -> tuple[bool, dict]:
    """Check the files `adk create` is expected to have written. Returns (ok, files)."""
    expected = ["__init__.py", "agent.py", ".env"]
    files = {name: (app_dir / name).exists() for name in expected}
    env_text = (app_dir / ".env").read_text(encoding="utf-8", errors="replace") if files[".env"] else ""
    files["env_has_key"] = "GOOGLE_API_KEY=" in env_text
    files["env_enterprise_flag"] = "GOOGLE_GENAI_USE_ENTERPRISE=0" in env_text
    ok = files["__init__.py"] and files["agent.py"] and files["env_has_key"]
    return ok, files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("Usage")[0].strip())
    ap.add_argument("app_name", help="App folder name (e.g. support_desk)")
    ap.add_argument("--workspace", default="./adk_workspace",
                    help="Workspace directory that will hold .venv and the app folder")
    ap.add_argument("--api-key", default=None,
                    help="Google AI Studio API key; defaults to $GOOGLE_API_KEY, else the placeholder")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Model id written into agent.py (default {DEFAULT_MODEL}; "
                         "gemini-3.5-flash / gemini-3.8-flash are the current menu options, "
                         "gemini-flash-latest tracks the newest)")
    ap.add_argument("--extras", default=DEFAULT_EXTRAS,
                    help=f"google-adk extras to install (default '{DEFAULT_EXTRAS}'; 'eval' and 'a2a' are opt-in)")
    ap.add_argument("--force", action="store_true",
                    help="Replace the app folder if it already exists and is not empty")
    ap.add_argument("--python", default=sys.executable,
                    help="Base interpreter used to create the workspace venv (default: this interpreter)")
    ap.add_argument("--adk", default=None,
                    help="adk executable to use (default: <workspace>/.venv adk, else 'adk' from PATH)")
    ap.add_argument("--no-venv", action="store_true",
                    help="Do not create a venv; use --python/--adk as installed (for existing environments)")
    ap.add_argument("--skip-install", action="store_true",
                    help="Skip pip install (assumes google-adk is already available to the chosen interpreter)")
    ap.add_argument("--timeout", type=float, default=600, help="Timeout in seconds per heavy step (default 600)")
    ap.add_argument("--json-out", default=None,
                    help="Report path (default <workspace>/adk_runs/create_report.json)")
    args = ap.parse_args(argv)

    report: dict = {
        "success": False, "app_name": args.app_name, "workspace": None, "model": args.model,
        "python": args.python if not args.no_venv else None, "adk": None,
        "api_key": None, "key_placeholder": False, "venv": None, "extras": args.extras,
        "steps": [], "files": {}, "next_actions": [], "report_path": None,
    }
    log = StepLog()
    report["steps"] = log.steps

    # ---- step 1: validate inputs -------------------------------------------------
    error = validate_app_name(args.app_name)
    if error:
        log.add("validate app name", False, error)
        print(f"[create_agent] {error}")
        return 2
    workspace = Path(args.workspace).expanduser().resolve()
    app_dir = workspace / args.app_name
    report["workspace"] = str(workspace)
    if app_dir.exists() and any(app_dir.iterdir()):
        if not args.force:
            log.add("validate inputs", False,
                    f"{app_dir} already exists and is not empty - pass --force to replace it")
            print(f"[create_agent] refuse to overwrite {app_dir} (use --force to replace)")
            return 4
        shutil.rmtree(app_dir)
        log.add("validate inputs", True, f"replaced existing folder {app_dir} (--force)")
    else:
        log.add("validate inputs", True, f"app name '{args.app_name}' is valid")

    # ---- step 2: prepare workspace ----------------------------------------------
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "adk_runs").mkdir(exist_ok=True)
    key, key_source = resolve_api_key(args.api_key)
    report["api_key"] = key_source
    report["key_placeholder"] = key_source == "placeholder"
    report["venv"] = None if args.no_venv else str(workspace / ".venv")
    log.add("prepare workspace", True,
            f"workspace={workspace}; api key from {key_source}"
            + (" (real tests will report INFRA_BLOCKED until it is replaced)" if key_source == "placeholder" else ""))

    # ---- step 3: venv -------------------------------------------------------------
    py = Path(args.python)
    if args.no_venv:
        log.add("create venv", True, "--no-venv: using the supplied interpreter directly")
    else:
        vpy = venv_python(workspace)
        if vpy.exists():
            log.add("create venv", True, f"reusing existing venv at {workspace / '.venv'}")
        else:
            try:
                proc = run([args.python, "-m", "venv", str(workspace / ".venv")], cwd=workspace, timeout=args.timeout)
            except Exception as e:
                log.add("create venv", False, f"{type(e).__name__}: {e}")
                return 3
            if proc.returncode != 0:
                log.add("create venv", False, f"python -m venv failed: {tail(proc.stderr)}")
                return 3
            log.add("create venv", True, f"created {workspace / '.venv'}")
        py = vpy

    # ---- step 4: install ------------------------------------------------------------------
    if args.no_venv or args.skip_install:
        log.add("install google-adk", True, "skipped (--no-venv/--skip-install)")
    else:
        spec = f"google-adk[{args.extras}]" if args.extras else "google-adk"
        try:
            proc = run([py, "-m", "pip", "install", "--disable-pip-version-check", spec],
                       cwd=workspace, timeout=args.timeout)
        except Exception as e:
            log.add("install google-adk", False, f"{type(e).__name__}: {e}")
            return 3
        if proc.returncode != 0:
            log.add("install google-adk", False, f"pip install {spec} failed: {tail(proc.stderr) or tail(proc.stdout)}")
            return 3
        log.add("install google-adk", True, f"installed {spec} into {workspace / '.venv'}")

    # ---- step 5: adk create ------------------------------------------------------------------
    adk = str(Path(args.adk)) if args.adk else (
        str(venv_adk(workspace)) if venv_adk(workspace).exists() else "adk")
    report["adk"] = adk
    try:  # explicit telemetry opt-out; older/edge installs may not have the subcommand (off by default)
        tel = run([adk, "telemetry", "disable"], cwd=workspace, timeout=60)
        tel_ok = tel.returncode == 0
    except Exception:
        tel_ok = False
    log.steps.append({"name": "telemetry opt-out", "ok": True, "cmd": f"{adk} telemetry disable",
                      "detail": "recorded" if tel_ok else "not available; telemetry is off by default"})
    print(f"[create_agent] step {len(log.steps)}/{TOTAL_STEPS} telemetry opt-out: ok")

    cmd = [adk, "create", args.app_name, "--model", args.model, "--api_key", key, "--type", "CODE"]
    try:
        proc = run(cmd, cwd=workspace, timeout=args.timeout)
    except Exception as e:
        log.add("adk create", False, f"{type(e).__name__}: {e}", cmd)
        return 3
    if proc.returncode != 0:
        log.add("adk create", False,
                f"exit {proc.returncode}: {tail(proc.stderr) or tail(proc.stdout)}", cmd)
        return 3
    log.add("adk create", True, f"scaffolded {app_dir}", cmd)
    report["model"] = args.model

    # ---- step 6: verify + smoke import ------------------------------------------------------
    files_ok, files = verify_scaffold(app_dir)
    report["files"] = files
    if not files_ok:
        log.add("verify scaffold", False, f"missing expected files in {app_dir}: {files}")
        return 3
    log.add("verify scaffold", True, "agent.py, __init__.py and .env present with GOOGLE_API_KEY")

    smoke_ok, smoke_detail = True, "skipped (no venv install to smoke-test with)"
    if not args.no_venv and not args.skip_install:
        try:
            proc = run([py, "-c", f"import {args.app_name}.agent"], cwd=workspace, timeout=min(args.timeout, 180))
            smoke_ok = proc.returncode == 0
            smoke_detail = "imported cleanly" if smoke_ok else f"import failed: {tail(proc.stderr)}"
        except Exception as e:
            smoke_ok, smoke_detail = False, f"{type(e).__name__}: {e}"
    report["smoke_import"] = {"ok": smoke_ok, "detail": smoke_detail}
    print(f"[create_agent] smoke import: {'ok' if smoke_ok else 'FAILED'} - {smoke_detail}")

    # ---- report -----------------------------------------------------------------------------
    report["success"] = bool(files_ok and smoke_ok)
    report["next_actions"] = []
    if report["key_placeholder"]:
        report["next_actions"].append(
            f"Put a real key into {app_dir / '.env'} (GOOGLE_API_KEY=...) or live runs report INFRA_BLOCKED")
    report["next_actions"] += [
        f"Write the agent code in {app_dir / 'agent.py'} (keep `from . import agent` in __init__.py)",
        f"Introspect with: python scripts/testing.py --workspace {workspace} --app {args.app_name} --init-spec",
        f"Test with:      python scripts/testing.py --workspace {workspace} --app {args.app_name} --spec <spec.json>",
    ]
    out = Path(args.json_out).resolve() if args.json_out else workspace / "adk_runs" / "create_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["report_path"] = str(out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({"success": report["success"], "app": args.app_name, "workspace": str(workspace),
                      "model": args.model, "key": key_source, "report": str(out)}, indent=2))
    print(f"[create_agent] report -> {out}")
    return 0 if report["success"] else 3


if __name__ == "__main__":
    sys.exit(main())
