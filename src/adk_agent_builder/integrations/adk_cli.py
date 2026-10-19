"""Adapter for official Google `adk` CLI and `agents-cli` (`google-agents-cli`)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class AdkCliAdapter:
    """Safe subprocess wrapper around official `adk` and `agents-cli` binaries with local fallback."""

    @staticmethod
    def detect_environment() -> Dict[str, Any]:
        """Check whether `adk` and `agents-cli` binaries are installed and inspect their versions."""
        adk_bin = shutil.which("adk")
        agents_cli_bin = shutil.which("agents-cli")
        uv_bin = shutil.which("uv")
        gcloud_bin = shutil.which("gcloud")

        return {
            "adk_cli": {
                "installed": adk_bin is not None,
                "path": adk_bin,
                "version": AdkCliAdapter._get_version(adk_bin) if adk_bin else None,
            },
            "agents_cli": {
                "installed": agents_cli_bin is not None,
                "path": agents_cli_bin,
                "version": AdkCliAdapter._get_version(agents_cli_bin) if agents_cli_bin else None,
                "install_hint": "uvx google-agents-cli setup  OR  pip install google-agents-cli && agents-cli setup",
            },
            "uv": {"installed": uv_bin is not None, "path": uv_bin},
            "gcloud": {"installed": gcloud_bin is not None, "path": gcloud_bin},
            "fallback_mode_active": adk_bin is None or agents_cli_bin is None,
        }

    @staticmethod
    def build_adk_command(
        subcommand: str,
        project_dir: Path,
        *,
        evalset_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        state_file: Optional[Path] = None,
        port: int = 8080,
    ) -> List[str]:
        """Construct verified official `adk` CLI commands (compatible with ADK v2.12.0)."""
        if subcommand == "web":
            return ["adk", "web", f"--port={port}", str(project_dir)]
        if subcommand == "run":
            cmd = ["adk", "run"]
            if state_file:
                cmd.append(f"--state_file={state_file}")
            cmd.append(str(project_dir / "app"))
            return cmd
        if subcommand == "eval":
            target_eval = evalset_path or (project_dir / "tests/eval/default_eval.evalset.json")
            cmd = ["adk", "eval", str(project_dir / "app"), str(target_eval), "--print_detailed_results"]
            if config_path:
                cmd.append(f"--config_file_path={config_path}")
            return cmd
        if subcommand == "conformance_record":
            return ["adk", "conformance", "record", str(project_dir / "tests"), "none"]
        if subcommand == "conformance_test":
            return ["adk", "conformance", "test", "--generate_report", f"--report_dir={project_dir / 'reports'}"]
        raise ValueError(f"Unsupported adk CLI subcommand: {subcommand}")

    @staticmethod
    def _get_version(binary_path: Optional[str], timeout: int = 5) -> Optional[str]:
        if not binary_path:
            return None
        try:
            proc = subprocess.run(
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            return (proc.stdout or proc.stderr or "").strip().splitlines()[0]
        except Exception:
            return None
