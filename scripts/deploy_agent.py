#!/usr/bin/env python3
"""deploy_agent.py - deploy an ADK app with `adk deploy`, safely and with a report.

Wraps the ADK deploy commands (``cloud_run``, ``agent_engine``) so that an
agent doing the deployment on the user's behalf gets four things the raw CLI
does not provide:

  1. Preflight checks before anything is uploaded - the app folder really
     contains an agent, `gcloud` is actually installed (Cloud Run mode), and a
     project/region or express-mode key is present for Agent Engine. Finding
     these out *before* a five-minute build beats reading a stack trace after
     one.
  2. A secret audit of the app's ``.env``. Deploys stage the app folder as
     source; a live ``GOOGLE_API_KEY=AIza...`` sitting in ``.env`` is uploaded
     with it. The script warns loudly, and explains the alternative (pass the
     key as a deployment env var or use Secret Manager) instead of leaking
     silently.
  3. ``--dry-run`` - prints the exact command line and the preflight findings
     without running anything. Use it to show the user what will happen.
  4. A machine-readable report at ``<workspace>/adk_runs/deploy_report.json``
     (command, preflight warnings, exit code, output tail) so the outcome of a
     deployment survives the conversation that triggered it.

Usage
    python deploy_agent.py ./adk_workspace/my_app --mode cloud_run --project my-proj --region us-central1
    python deploy_agent.py ./adk_workspace/my_app --mode agent_engine --project my-proj --region us-central1
    python deploy_agent.py ./adk_workspace/my_app --mode cloud_run --dry-run
    python deploy_agent.py ./my_app --mode cloud_run -- --no-allow-unauthenticated --min-instances=1

Exit codes: 0 success (or dry-run), 1 deployment failed, 2 usage error, 3 preflight failed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SECRET_KEYS = {"GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
               "DATABASE_URL", "DB_PASSWORD", "PGPASSWORD", "AWS_SECRET_ACCESS_KEY"}


def venv_adk(app_path: Path) -> str:
    """Prefer the workspace venv's adk (app_path/.. corresponds to the workspace)."""
    adk_rel = ".venv/Scripts/adk.exe" if os.name == "nt" else ".venv/bin/adk"
    for ws in (app_path.parent, app_path.parent.parent):
        candidate = ws / adk_rel
        if candidate.exists():
            return str(candidate)
    return "adk"


def read_env_keys(app_path: Path) -> dict[str, str]:
    """Parse the app's .env into a key->value map (values never printed in full)."""
    env_file = app_path / ".env"
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def secret_warnings(env_values: dict[str, str]) -> list[str]:
    warnings = []
    for key, value in env_values.items():
        looks_secret = key in SECRET_KEYS or any(t in key.upper() for t in ("SECRET", "TOKEN", "PASSWORD", "API_KEY"))
        if not looks_secret:
            continue
        if value and "YOUR_" not in value and len(value) >= 8:
            warnings.append(
                f"{key} in .env looks like a live secret and will be staged with the app source. "
                f"Prefer `--env {key}=<value>` at deploy time (or Secret Manager) and keep .env for local runs only")
    return warnings


def build_command(adk: str, app_path: Path, args) -> list[str]:
    cmd = [adk, "deploy", args.mode, str(app_path)]
    if args.project:
        cmd += ["--project", args.project]
    if args.region:
        cmd += ["--region", args.region]
    if args.mode == "cloud_run":
        if args.service_name:
            cmd += ["--service_name", args.service_name]
        if args.with_ui:
            cmd += ["--with_ui"]
    if args.mode == "agent_engine":
        if args.api_key:
            cmd += ["--api_key", args.api_key]
        if args.engine_id:
            cmd += ["--agent_engine_id", args.engine_id]
        if args.display_name:
            cmd += ["--display_name", args.display_name]
        if args.description:
            cmd += ["--description", args.description]
    if args.app_name:
        cmd += ["--app_name", args.app_name]
    for kv in args.env:
        cmd += ["--env", kv]
    cmd += args.extra
    return cmd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("Usage")[0].strip())
    ap.add_argument("app_path", help="Path to the app folder (the one containing agent.py)")
    ap.add_argument("--mode", choices=["cloud_run", "agent_engine"], default="cloud_run",
                    help="Deployment target (default cloud_run)")
    ap.add_argument("--project", default=None, help="Google Cloud project id")
    ap.add_argument("--region", default=None, help="Google Cloud region (e.g. us-central1)")
    ap.add_argument("--service-name", default=None, help="Cloud Run service name (cloud_run only)")
    ap.add_argument("--app-name", default=None, help="ADK app name (defaults to the folder name)")
    ap.add_argument("--with-ui", action="store_true", help="Also serve the ADK Web UI (cloud_run only)")
    ap.add_argument("--env", action="append", default=[], help="Environment variable as key=value (repeatable)")
    ap.add_argument("--api-key", default=None, help="Express-mode API key (agent_engine only)")
    ap.add_argument("--engine-id", default=None, help="Existing Agent Engine id to update (agent_engine only)")
    ap.add_argument("--display-name", default=None, help="Display name in Agent Engine")
    ap.add_argument("--description", default=None, help="Description in Agent Engine")
    ap.add_argument("--adk", default=None, help="adk executable (default: workspace .venv, else adk on PATH)")
    ap.add_argument("--dry-run", action="store_true", help="Run preflight checks and print the command; deploy nothing")
    ap.add_argument("--timeout", type=float, default=3600, help="Deployment timeout in seconds (default 3600)")
    ap.add_argument("--json-out", default=None, help="Report path (default <app_dir>/../adk_runs/deploy_report.json)")
    ap.add_argument("extra", nargs="*", default=[],
                    help="Extra arguments passed through to the provider (after --), e.g. -- --min-instances=1")
    args = ap.parse_args(argv)

    app_path = Path(args.app_path).expanduser().resolve()
    report: dict = {"success": False, "dry_run": args.dry_run, "mode": args.mode, "app_path": str(app_path),
                    "command": None, "warnings": [], "errors": [], "exit_code": None, "output_tail": "", "report_path": None}

    def finish(code: int) -> int:
        out = Path(args.json_out).resolve() if args.json_out else app_path.parent / "adk_runs" / "deploy_report.json"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            report["report_path"] = str(out)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"[deploy] report -> {out}")
        except OSError as e:
            print(f"[deploy] could not write report: {e}")
        return code

    # ---- preflight -----------------------------------------------------------------
    if not app_path.exists() or not app_path.is_dir():
        report["errors"].append(f"app folder not found: {app_path}")
        print(f"[deploy] ERROR: app folder not found: {app_path}")
        return finish(3)
    if not (app_path / "agent.py").exists() and not (app_path / "root_agent.yaml").exists():
        report["errors"].append("no agent.py or root_agent.yaml in the app folder")
        print(f"[deploy] ERROR: {app_path} does not contain agent.py or root_agent.yaml")
        return finish(3)
    if args.mode == "cloud_run":
        if not shutil.which("gcloud") and not args.dry_run:
            report["errors"].append("gcloud is not on PATH; Cloud Run deploys use it under the hood")
            print("[deploy] ERROR: gcloud is not on PATH (install the Google Cloud SDK or use --dry-run)")
            return finish(3)
        if not shutil.which("gcloud"):
            report["warnings"].append("gcloud not found on PATH (ok for --dry-run, required for a real deploy)")
    else:
        if not (args.project and args.region) and not args.api_key:
            report["warnings"].append(
                "agent_engine deploy without --project/--region and without --api-key; "
                "the app's .env must carry GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION instead")

    env_values = read_env_keys(app_path)
    report["env_keys"] = sorted(env_values)
    report["warnings"] += secret_warnings(env_values)

    adk = args.adk or venv_adk(app_path)
    cmd = build_command(adk, app_path, args)
    report["command"] = " ".join(cmd)

    for w in report["warnings"]:
        print(f"[deploy] warning: {w}")
    print(f"[deploy] command: {report['command']}")

    if args.dry_run:
        report["success"] = True
        print("[deploy] dry run: nothing was deployed")
        return finish(0)

    # ---- deploy --------------------------------------------------------------------
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              stdin=subprocess.DEVNULL, timeout=args.timeout)
    except FileNotFoundError:
        report["errors"].append(f"could not run '{adk}' - is google-adk installed in the workspace venv?")
        print(f"[deploy] ERROR: could not run '{adk}'")
        return finish(3)
    except subprocess.TimeoutExpired:
        report["errors"].append(f"deployment timed out after {args.timeout:.0f}s")
        print("[deploy] ERROR: deployment timed out")
        return finish(1)

    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    report["exit_code"] = proc.returncode
    report["output_tail"] = output[-4000:]
    report["success"] = proc.returncode == 0
    print(output[-4000:] if output else "(no output)")
    if proc.returncode == 0:
        print(f"[deploy] deployed {app_path.name} via {args.mode}")
        return finish(0)
    report["errors"].append(f"adk deploy exited with code {proc.returncode}")
    print(f"[deploy] FAILED (exit {proc.returncode})")
    return finish(1)


if __name__ == "__main__":
    sys.exit(main())
