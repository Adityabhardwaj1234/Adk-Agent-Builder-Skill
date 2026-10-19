"""Safe test discovery and execution engine supporting pytest and unittest fallback."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from pydantic import Field

from adk_agent_builder.logging import redact_sensitive_text
from adk_agent_builder.models.base import CompatModel


class TestSuiteResult(CompatModel):
    project_dir: str
    runner_used: str
    command: str
    passed: bool = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    failure_summaries: List[str] = Field(default_factory=list)


class TestRunner:
    """Executes project unit, integration, and contract tests safely with timeouts and output parsing."""

    @staticmethod
    def run_tests(
        project_dir: Path,
        *,
        test_subdir: Optional[str] = None,
        pattern: str = "test_*.py",
        timeout_seconds: int = 60,
    ) -> TestSuiteResult:
        target_dir = project_dir / (test_subdir or "tests")
        if not target_dir.exists():
            return TestSuiteResult(
                project_dir=str(project_dir),
                runner_used="none",
                command="",
                passed=False,
                failure_summaries=[f"Test directory not found: {target_dir}"],
            )

        env = dict(os.environ)
        existing_py = env.get("PYTHONPATH", "")
        src_paths = [str(project_dir)]
        if (project_dir / "src").exists():
            src_paths.insert(0, str(project_dir / "src"))
        env["PYTHONPATH"] = os.pathsep.join(src_paths + ([existing_py] if existing_py else []))

        has_pytest = shutil.which("pytest") is not None
        if has_pytest:
            runner_name = "pytest"
            cmd = [sys.executable, "-m", "pytest", str(target_dir), "-v"]
        else:
            runner_name = "unittest"
            cmd = [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(target_dir),
                "-t",
                str(project_dir),
                "-p",
                pattern,
                "-v",
            ]

        start = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(project_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

        total, passed_cnt, failed_cnt, skipped_cnt, error_cnt = TestRunner._parse_counts(
            combined, proc.returncode
        )
        failures = TestRunner._extract_failure_lines(combined)

        # Never treat a run with 0 executed tests or skipped-only tests as a silent pass
        overall_passed = (
            proc.returncode == 0
            and total > 0
            and failed_cnt == 0
            and error_cnt == 0
            and passed_cnt > 0
        )

        return TestSuiteResult(
            project_dir=str(project_dir),
            runner_used=runner_name,
            command=" ".join(cmd),
            passed=overall_passed,
            total_tests=total,
            passed_tests=passed_cnt,
            failed_tests=failed_cnt,
            skipped_tests=skipped_cnt,
            error_tests=error_cnt,
            duration_ms=round(duration_ms, 2),
            stdout=redact_sensitive_text(proc.stdout[-4000:]),
            stderr=redact_sensitive_text(proc.stderr[-4000:]),
            failure_summaries=failures,
        )

    @staticmethod
    def _parse_counts(output: str, returncode: int) -> tuple[int, int, int, int, int]:
        # Unittest format: "Ran X tests in Ys" + "OK (skipped=Z)" or "FAILED (failures=F, errors=E, skipped=S)"
        ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
        if ran_match:
            total = int(ran_match.group(1))
            f_match = re.search(r"failures=(\d+)", output)
            e_match = re.search(r"errors=(\d+)", output)
            s_match = re.search(r"skipped=(\d+)", output)
            failed = int(f_match.group(1)) if f_match else 0
            errors = int(e_match.group(1)) if e_match else 0
            skipped = int(s_match.group(1)) if s_match else 0
            passed = max(0, total - failed - errors - skipped)
            return total, passed, failed, skipped, errors

        # Pytest format
        p_match = re.search(r"(\d+)\s+passed", output)
        f_match = re.search(r"(\d+)\s+failed", output)
        s_match = re.search(r"(\d+)\s+skipped", output)
        e_match = re.search(r"(\d+)\s+errors?", output)
        passed = int(p_match.group(1)) if p_match else 0
        failed = int(f_match.group(1)) if f_match else 0
        skipped = int(s_match.group(1)) if s_match else 0
        errors = int(e_match.group(1)) if e_match else (1 if returncode != 0 and failed == 0 else 0)
        total = passed + failed + skipped + errors
        return total, passed, failed, skipped, errors

    @staticmethod
    def _extract_failure_lines(output: str) -> List[str]:
        summaries: List[str] = []
        for line in output.splitlines():
            if any(
                marker in line
                for marker in ("FAIL:", "ERROR:", "AssertionError:", "SyntaxError:", "ImportError:", "ModuleNotFoundError:")
            ):
                summaries.append(redact_sensitive_text(line.strip()))
        return summaries[:15]
