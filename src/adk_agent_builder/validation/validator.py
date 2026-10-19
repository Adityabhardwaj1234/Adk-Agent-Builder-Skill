"""Automated static, schema, and ADK API compatibility validator."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import List
from pydantic import Field

from adk_agent_builder.models.base import CompatModel
from adk_agent_builder.models.evaluation import EvalConfig, EvalSet


DEPRECATED_ADK_IMPORTS = {
    "google.adk.flows.llm_flows.audio_cache_manager": "Deprecated in ADK v2.10.0; migrate to google.adk.live.",
    "google.adk.flows.llm_flows.audio_transcriber": "Deprecated in ADK v2.10.0; migrate to google.adk.live.",
    "google.adk.flows.llm_flows.transcription_manager": "Deprecated in ADK v2.10.0; migrate to google.adk.live.",
    "google.adk.labs.openai": "Moved in ADK v2.10.0; import from google.adk.integrations.openai.",
    "vertexai.preview": "Migrated in ADK v2.12.0; use google-cloud-aiplatform v2.2+.",
}

REQUIRED_PROJECT_FILES = [
    "pyproject.toml",
    "app/__init__.py",
    "app/agent.py",
    "app/tools.py",
]


class ValidationIssue(CompatModel):
    code: str
    severity: str  # error | warning
    file_path: str
    line: int = 1
    message: str
    remediation: str


class ValidationReport(CompatModel):
    project_dir: str
    valid: bool = False
    checked_files: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)


class ProjectValidator:
    """Validates generated or user-authored ADK projects for syntax, entrypoints, schemas, and API usage."""

    @staticmethod
    def validate_project(project_dir: Path) -> ValidationReport:
        issues: List[ValidationIssue] = []
        checked = 0

        is_suite_repo = (project_dir / "SKILL.md").exists() and (project_dir / "src/adk_agent_builder").exists()
        if not is_suite_repo:
            for req_file in REQUIRED_PROJECT_FILES:
                if not (project_dir / req_file).exists():
                    issues.append(
                        ValidationIssue(
                            code="VAL_MISSING_REQUIRED_FILE",
                            severity="error",
                            file_path=req_file,
                            message=f"Required ADK project file '{req_file}' is missing.",
                            remediation=f"Create '{req_file}' or run `adk-agent-builder build`.",
                        )
                    )

        # Check Python files
        for py_file in sorted(project_dir.rglob("*.py")):
            rel = str(py_file.relative_to(project_dir))
            if "__pycache__" in rel or rel.startswith("."):
                continue
            checked += 1
            source = py_file.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=rel)
            except SyntaxError as exc:
                issues.append(
                    ValidationIssue(
                        code="VAL_SYNTAX_ERROR",
                        severity="error",
                        file_path=rel,
                        line=exc.lineno or 1,
                        message=f"Python syntax error: {exc.msg}",
                        remediation="Fix the syntax error at the reported line.",
                    )
                )
                continue

            # Check deprecated imports
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for dep_mod, msg in DEPRECATED_ADK_IMPORTS.items():
                        if node.module.startswith(dep_mod):
                            issues.append(
                                ValidationIssue(
                                    code="VAL_DEPRECATED_ADK_IMPORT",
                                    severity="error",
                                    file_path=rel,
                                    line=node.lineno,
                                    message=f"Deprecated import '{node.module}': {msg}",
                                    remediation=msg,
                                )
                            )

            # Check root_agent in app/agent.py
            if rel == "app/agent.py":
                assigned_names = {
                    target.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    for target in node.targets
                    if isinstance(target, ast.Name)
                }
                if "root_agent" not in assigned_names:
                    issues.append(
                        ValidationIssue(
                            code="VAL_MISSING_ROOT_AGENT",
                            severity="error",
                            file_path=rel,
                            line=1,
                            message="app/agent.py must define a top-level 'root_agent' variable for ADK CLI discovery.",
                            remediation="Define `root_agent = LlmAgent(...)` or a workflow agent in app/agent.py.",
                        )
                    )

            # Check tool function type annotations & docstrings in app/tools.py
            if rel == "app/tools.py":
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                        if ast.get_docstring(node) is None:
                            issues.append(
                                ValidationIssue(
                                    code="VAL_TOOL_MISSING_DOCSTRING",
                                    severity="warning",
                                    file_path=rel,
                                    line=node.lineno,
                                    message=f"Tool function '{node.name}' lacks a docstring; ADK uses docstrings for tool declarations.",
                                    remediation=f"Add a descriptive docstring to '{node.name}'.",
                                )
                            )

        # Check EvalSet and EvalConfig schemas
        for eval_file in sorted(project_dir.rglob("*.evalset.json")) + sorted(project_dir.rglob("*.test.json")):
            rel = str(eval_file.relative_to(project_dir))
            checked += 1
            try:
                raw = json.loads(eval_file.read_text(encoding="utf-8"))
                eval_set = EvalSet.from_dict(raw)
                if not eval_set.eval_cases:
                    issues.append(
                        ValidationIssue(
                            code="VAL_EMPTY_EVALSET",
                            severity="error",
                            file_path=rel,
                            message="EvalSet has zero eval_cases (ADK v2.10.0+ raises ValueError on empty eval_cases).",
                            remediation="Add at least one EvalCase to eval_cases.",
                        )
                    )
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        code="VAL_INVALID_EVALSET_SCHEMA",
                        severity="error",
                        file_path=rel,
                        message=f"Invalid EvalSet JSON schema: {exc}",
                        remediation="Align the file with the ADK EvalSet Pydantic schema.",
                    )
                )

        for cfg_file in sorted(project_dir.rglob("test_config.json")):
            rel = str(cfg_file.relative_to(project_dir))
            checked += 1
            try:
                raw = json.loads(cfg_file.read_text(encoding="utf-8"))
                _ = EvalConfig.from_dict(raw)
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        code="VAL_INVALID_EVAL_CONFIG",
                        severity="error",
                        file_path=rel,
                        message=f"Invalid test_config.json schema: {exc}",
                        remediation="Ensure criteria is a mapping of metric names to float thresholds.",
                    )
                )

        err_count = sum(1 for i in issues if i.severity == "error")
        warn_count = sum(1 for i in issues if i.severity == "warning")
        return ValidationReport(
            project_dir=str(project_dir),
            valid=(err_count == 0),
            checked_files=checked,
            error_count=err_count,
            warning_count=warn_count,
            issues=issues,
        )
