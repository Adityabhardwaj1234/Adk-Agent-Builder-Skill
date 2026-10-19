"""Packaging, deployment planning, explicit authorization gates, .env secret staging checks, and smoke testing."""

from __future__ import annotations

import importlib.util
import os
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.errors import DeploymentBlockedError
from adk_agent_builder.models.base import CompatModel
from adk_agent_builder.validation.validator import ProjectValidator


SECRET_ENV_KEYS = {
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DATABASE_URL",
    "DB_PASSWORD",
    "PGPASSWORD",
    "AWS_SECRET_ACCESS_KEY",
}


DEPLOYMENT_TARGETS: Dict[str, Dict[str, Any]] = {
    "local": {
        "billable": False,
        "required_env": [],
        "command_template": "adk web {project_dir}",
        "rollback_procedure": "Stop local process (Ctrl+C) and checkout previous Git commit.",
    },
    "docker": {
        "billable": False,
        "required_env": [],
        "command_template": "docker build -t {project_name}:latest {project_dir} && docker run --rm -p 8080:8080 --env-file .env {project_name}:latest",
        "rollback_procedure": "Stop running container and deploy previous image digest.",
    },
    "cloud_run": {
        "billable": True,
        "required_env": ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"],
        "command_template": "adk deploy cloud_run --project={project_id} --region={region} --service_name={project_name} {project_dir}",
        "rollback_procedure": "gcloud run services update-traffic {project_name} --to-revisions=PREVIOUS_REVISION=100 --region={region}",
    },
    "agent_runtime": {
        "billable": True,
        "required_env": ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"],
        "command_template": "adk deploy agent_engine --project={project_id} --region={region} --display_name={project_name} {sa_flag} {project_dir}",
        "rollback_procedure": "Revert ReasoningEngine / Agent Runtime traffic to prior resource ID and delete faulty deployment via Vertex AI console or SDK.",
    },
    "gke": {
        "billable": True,
        "required_env": ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GKE_CLUSTER_NAME"],
        "command_template": "adk deploy gke --project={project_id} --region={region} --cluster_name={cluster} {project_dir}",
        "rollback_procedure": "kubectl rollout undo deployment/{project_name}",
    },
}


class DeploymentPlan(CompatModel):
    project_name: str
    target: str
    dry_run: bool = True
    authorized: bool = False
    billable_Warning: bool = False
    prerequisites_satisfied: bool = False
    missing_env_vars: List[str] = Field(default_factory=list)
    secret_warnings: List[str] = Field(default_factory=list)
    planned_command: str = ""
    rollback_guidance: str = ""
    status: str = "planned"


class SmokeTestReport(CompatModel):
    project_dir: str
    target: str
    passed: bool = False
    health_status: str = "unknown"
    sample_query: str = "smoke test ping"
    sample_response: str = ""
    errors: List[str] = Field(default_factory=list)


class DeploymentManager:
    """Handles packaging, deployment prerequisite validation, .env secret staging audits, dry-run planning, and smoke tests."""

    @staticmethod
    def audit_env_secrets(project_dir: Path) -> List[str]:
        """Inspect project .env for live credentials that `adk deploy` would stage with the container source."""
        env_file = project_dir / ".env"
        if not env_file.exists():
            return []
        warnings: List[str] = []
        for raw_line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            k = key.strip()
            v = val.strip().strip('"').strip("'")
            looks_secret = k in SECRET_ENV_KEYS or any(
                t in k.upper() for t in ("SECRET", "TOKEN", "PASSWORD", "API_KEY")
            )
            if looks_secret and v and "YOUR_" not in v.upper() and "<" not in v and len(v) >= 8:
                warnings.append(
                    f"{k} in .env looks like a live credential and would be staged with the app source during cloud deploy. "
                    f"Prefer `--env {k}=<value>` at deploy time or Secret Manager, and keep .env for local runs only."
                )
        return warnings

    @staticmethod
    def package_project(
        project_dir: Path,
        output_zip_path: Optional[Path] = None,
    ) -> Path:
        """Validate and package an ADK project into a clean .zip archive excluding secrets, DBs, and caches."""
        val = ProjectValidator.validate_project(project_dir)
        if not val.valid:
            raise DeploymentBlockedError(
                f"Cannot package invalid project '{project_dir}': {val.error_count} validation errors found.",
                stage="14_packaging_deployment_planning",
                file_path=str(project_dir),
                remediation="Run `adk-agent-builder validate` and fix reported errors first.",
            )

        target_zip = output_zip_path or (project_dir / "dist" / f"{project_dir.name}.zip")
        target_zip.parent.mkdir(parents=True, exist_ok=True)

        excluded_dirs = {
            "__pycache__",
            ".git",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
            "venv",
            ".venv",
            "adk_runs",
            ".adk",
        }
        excluded_suffixes = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log"}
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(project_dir.rglob("*")):
                if not item.is_file():
                    continue
                rel = item.relative_to(project_dir)
                if any(part in excluded_dirs for part in rel.parts):
                    continue
                if item.name == ".env" or item.name.startswith(".env.") and item.name != ".env.example":
                    continue
                if item.suffix in excluded_suffixes:
                    continue
                zf.write(item, arcname=str(Path(project_dir.name) / rel))

        return target_zip

    @staticmethod
    def create_deployment_plan(
        project_dir: Path,
        target: str = "local",
        *,
        dry_run: bool = True,
        approve_billable: bool = False,
        service_account: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> DeploymentPlan:
        """Create and validate a deployment plan; blocks unapproved billable cloud deployments."""
        target_key = target.lower().strip()
        if target_key == "agent_engine":
            target_key = "agent_runtime"
        if target_key not in DEPLOYMENT_TARGETS:
            raise DeploymentBlockedError(
                f"Unsupported deployment target '{target}'. Supported targets: {sorted(DEPLOYMENT_TARGETS.keys())}",
                stage="14_packaging_deployment_planning",
            )

        meta = DEPLOYMENT_TARGETS[target_key]
        environment = env if env is not None else dict(os.environ)
        missing_env = [v for v in meta["required_env"] if not environment.get(v)]
        env_warnings = DeploymentManager.audit_env_secrets(project_dir)

        project_id = environment.get("GOOGLE_CLOUD_PROJECT", "<PROJECT_ID>")
        region = environment.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        cluster = environment.get("GKE_CLUSTER_NAME", "<GKE_CLUSTER>")
        sa_flag = f"--service_account={service_account}" if service_account else ""

        cmd = meta["command_template"].format(
            project_dir=str(project_dir),
            project_name=project_dir.name,
            project_id=project_id,
            region=region,
            cluster=cluster,
            sa_flag=sa_flag,
        ).strip()

        is_billable = bool(meta["billable"])
        if not dry_run and is_billable and not approve_billable:
            raise DeploymentBlockedError(
                f"Cloud deployment to '{target_key}' creates billable resources and requires explicit --approve-billable authorization.",
                stage="15_deployment_smoke_testing",
                command=cmd,
                remediation="Run with --dry-run to inspect the plan, or pass --approve-billable with valid cloud credentials.",
            )

        if not dry_run and missing_env:
            raise DeploymentBlockedError(
                f"Cannot execute live deployment to '{target_key}': missing required environment variables {missing_env}.",
                stage="15_deployment_smoke_testing",
                command=cmd,
                remediation=f"Set {', '.join(missing_env)} or run with --dry-run.",
            )

        return DeploymentPlan(
            project_name=project_dir.name,
            target=target_key,
            dry_run=dry_run,
            authorized=(approve_billable or not is_billable),
            billable_Warning=is_billable,
            prerequisites_satisfied=(len(missing_env) == 0),
            missing_env_vars=missing_env,
            secret_warnings=env_warnings,
            planned_command=cmd,
            rollback_guidance=meta["rollback_procedure"].format(
                project_name=project_dir.name, region=region
            ),
            status="dry_run_ready" if dry_run else "ready_for_execution",
        )

    @staticmethod
    def run_smoke_test(project_dir: Path, target: str = "local") -> SmokeTestReport:
        """Execute a deterministic local or endpoint smoke test against the generated project."""
        fast_api_file = project_dir / "app/fast_api_app.py"
        if not fast_api_file.exists():
            return SmokeTestReport(
                project_dir=str(project_dir),
                target=target,
                passed=False,
                errors=[f"Missing {fast_api_file} for smoke test."],
            )

        proj_str = str(project_dir.resolve())
        added = False
        if proj_str not in sys.path:
            sys.path.insert(0, proj_str)
            added = True
        try:
            for mod_name in list(sys.modules.keys()):
                if mod_name == "app" or mod_name.startswith("app."):
                    del sys.modules[mod_name]

            spec = importlib.util.spec_from_file_location("app.fast_api_app", str(fast_api_file))
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            health = mod.health_check()
            turn = mod.invoke_sync("smoke test ping")
            passed = (
                health.get("status") == "healthy"
                and turn.get("status") == "ok"
                and bool(turn.get("response"))
            )
            return SmokeTestReport(
                project_dir=str(project_dir),
                target=target,
                passed=passed,
                health_status=str(health.get("status", "unknown")),
                sample_query="smoke test ping",
                sample_response=str(turn.get("response", "")),
                errors=[] if passed else ["Health check or invoke_sync did not return status='ok'."],
            )
        except Exception as exc:
            return SmokeTestReport(
                project_dir=str(project_dir),
                target=target,
                passed=False,
                errors=[str(exc)],
            )
        finally:
            if added and proj_str in sys.path:
                sys.path.remove(proj_str)
