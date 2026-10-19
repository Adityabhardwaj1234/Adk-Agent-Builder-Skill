"""Static and runtime security scanner for ADK agent projects."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List
from pydantic import Field

from adk_agent_builder.logging import SECRET_PATTERNS
from adk_agent_builder.models.base import CompatModel


DANGEROUS_CALLS = {
    "eval": "Arbitrary code evaluation via eval() is unsafe.",
    "exec": "Arbitrary code execution via exec() is unsafe unless isolated in a sandbox.",
    "os.system": "Unchecked shell execution via os.system() risks command injection.",
    "pickle.loads": "Untrusted pickle deserialization allows arbitrary code execution.",
    "yaml.load": "Use yaml.safe_load() instead of yaml.load() to prevent arbitrary object instantiation.",
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions"),
    re.compile(r"(?i)reveal\s+(your\s+)?(system\s+prompt|api\s+key|secret)"),
    re.compile(r"(?i)bypass\s+(safety|security|guardrail|confirmation)"),
]


class SecurityFinding(CompatModel):
    rule_id: str
    severity: str  # critical | high | medium | low
    file_path: str
    line: int = 1
    description: str
    remediation: str


class SecurityScanReport(CompatModel):
    project_dir: str
    passed: bool = True
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    findings: List[SecurityFinding] = Field(default_factory=list)


class SecurityScanner:
    """Scans ADK project files for hardcoded secrets, dangerous calls, and policy violations."""

    @staticmethod
    def scan_project(project_dir: Path) -> SecurityScanReport:
        findings: List[SecurityFinding] = []
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(project_dir))
            if any(part.startswith(".") and part != ".env.example" for part in path.parts):
                if path.name == ".env":
                    findings.extend(SecurityScanner._scan_text_for_secrets(path, rel))
                continue
            if "__pycache__" in rel or rel.endswith((".pyc", ".db", ".whl", ".tar.gz", ".zip")):
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            findings.extend(SecurityScanner._scan_text_for_secrets(path, rel, content))
            if path.suffix == ".py":
                findings.extend(SecurityScanner._scan_python_ast(content, rel))

        crit = sum(1 for f in findings if f.severity == "critical")
        high = sum(1 for f in findings if f.severity == "high")
        med = sum(1 for f in findings if f.severity == "medium")

        return SecurityScanReport(
            project_dir=str(project_dir),
            passed=(crit == 0 and high == 0),
            critical_count=crit,
            high_count=high,
            medium_count=med,
            findings=findings,
        )

    @staticmethod
    def _scan_text_for_secrets(
        path: Path,
        rel_path: str,
        content: str | None = None,
    ) -> List[SecurityFinding]:
        text = content if content is not None else path.read_text(encoding="utf-8", errors="ignore")
        results: List[SecurityFinding] = []
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or "YOUR_API_KEY" in stripped or "REDACTED" in stripped or "<" in stripped:
                continue
            if "re.compile" in stripped or "SECRET_PATTERNS" in stripped:
                continue
            for pat in SECRET_PATTERNS[:7]:
                if pat.search(stripped):
                    results.append(
                        SecurityFinding(
                            rule_id="SEC_HARDCODED_SECRET",
                            severity="critical",
                            file_path=rel_path,
                            line=idx,
                            description="Hardcoded API key or credential token detected in file.",
                            remediation="Remove the secret immediately, rotate the credential, and load from environment variables.",
                        )
                    )
                    break
        return results

    @staticmethod
    def _scan_python_ast(source: str, rel_path: str) -> List[SecurityFinding]:
        results: List[SecurityFinding] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return results

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = SecurityScanner._resolve_call_name(node.func)
                if call_name in DANGEROUS_CALLS:
                    results.append(
                        SecurityFinding(
                            rule_id="SEC_DANGEROUS_CALL",
                            severity="high",
                            file_path=rel_path,
                            line=getattr(node, "lineno", 1),
                            description=DANGEROUS_CALLS[call_name],
                            remediation=f"Replace '{call_name}' with a safe, validated alternative.",
                        )
                    )
                if call_name in ("subprocess.run", "subprocess.Popen", "subprocess.call"):
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            results.append(
                                SecurityFinding(
                                    rule_id="SEC_SUBPROCESS_SHELL_TRUE",
                                    severity="high",
                                    file_path=rel_path,
                                    line=getattr(node, "lineno", 1),
                                    description="subprocess call with shell=True enables shell injection.",
                                    remediation="Pass argument lists with shell=False and explicit timeout.",
                                )
                            )
        return results

    @staticmethod
    def _resolve_call_name(func_node: ast.AST) -> str:
        if isinstance(func_node, ast.Name):
            return func_node.id
        if isinstance(func_node, ast.Attribute) and isinstance(func_node.value, ast.Name):
            return f"{func_node.value.id}.{func_node.attr}"
        return ""

    @staticmethod
    def check_prompt_injection(user_text: str) -> Dict[str, object]:
        """Runtime helper used by before_model_callback guardrails to detect prompt injection attempts."""
        matched = [p.pattern for p in PROMPT_INJECTION_PATTERNS if p.search(user_text or "")]
        return {
            "blocked": len(matched) > 0,
            "matched_patterns": matched,
        }
