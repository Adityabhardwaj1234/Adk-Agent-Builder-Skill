"""Agent Skills (`agentskills.io`) validator, doc-integrity checker, and `.skill` archive packager."""

from __future__ import annotations

import fnmatch
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from adk_agent_builder.models.base import CompatModel


SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")
IGNORED_SKILL_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "venv",
    ".venv",
    "adk_runs",
    ".adk",
    "node_modules",
}
DOC_PATH_TOKEN_RE = re.compile(r"(?<![\w./-])((?:scripts|references|assets)/[\w][\w./-]*[\w])")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


class SkillValidationReport(CompatModel):
    skill_dir: str
    skill_name: Optional[str] = None
    skill_kind: str = "runtime_or_dev"
    valid: bool = False
    line_count: int = 0
    errors: List[str] = []
    warnings: List[str] = []
    discovered_resources: List[str] = []


class SkillPackageReport(CompatModel):
    skill_dir: str
    skill_name: str
    archive_path: str
    packaged_files: List[str] = []
    skipped_count: int = 0
    valid: bool = True


class SkillValidator:
    """Validates SKILL.md files, frontmatter, path boundaries, doc references, and packages `.skill` archives."""

    @staticmethod
    def validate_skill_directory(skill_dir: Path, *, strict: bool = False) -> SkillValidationReport:
        """Validate a skill directory against the Agent Skills specification and security rules."""
        errors: List[str] = []
        warnings: List[str] = []
        resources: List[str] = []

        resolved_root = skill_dir.resolve()
        skill_md = resolved_root / "SKILL.md"
        if not skill_md.exists():
            return SkillValidationReport(
                skill_dir=str(skill_dir),
                valid=False,
                errors=[f"Missing required SKILL.md in {skill_dir}"],
            )

        raw = skill_md.read_text(encoding="utf-8")
        lines = raw.splitlines()
        line_count = len(lines)
        if line_count > 500:
            warnings.append(
                f"SKILL.md is {line_count} lines (>500 recommended progressive disclosure limit). Move reference tables into references/."
            )

        frontmatter, body = SkillValidator._parse_frontmatter(raw)
        if frontmatter is None:
            errors.append("SKILL.md must begin with valid YAML frontmatter delimited by '---'.")
            name = None
            desc = ""
        else:
            name = frontmatter.get("name")
            desc = frontmatter.get("description", "")
            if not name or not isinstance(name, str):
                errors.append("YAML frontmatter is missing required string field 'name'.")
            elif not SKILL_NAME_PATTERN.match(name):
                errors.append(
                    f"Skill name '{name}' must use lowercase letters, digits, and hyphens only (3-64 chars)."
                )
            if not desc or not isinstance(desc, str) or len(desc.strip()) < 20:
                errors.append(
                    "YAML frontmatter 'description' must clearly describe what the skill does and when to trigger it (>=20 chars)."
                )
            elif len(desc) > 1024:
                errors.append("YAML frontmatter 'description' exceeds 1024 characters.")
            elif "<" in desc or ">" in desc:
                errors.append("YAML frontmatter 'description' must not contain angle brackets ('<' or '>').")

        # Check all files inside skill directory for symlink escape / path traversal
        for item in sorted(resolved_root.rglob("*")):
            try:
                rel = item.resolve().relative_to(resolved_root)
            except ValueError:
                errors.append(f"Path escape detected outside skill root: {item}")
                continue
            if any(part in IGNORED_SKILL_DIRS for part in rel.parts) or item.suffix == ".pyc":
                continue
            if item.is_file() and item.name != "SKILL.md":
                rel_str = str(rel)
                if not any(
                    rel_str.startswith(prefix)
                    for prefix in (
                        "scripts/",
                        "references/",
                        "assets/",
                        "src/",
                        "docs/",
                        "tests/",
                        "examples/",
                        "adk-agent-builder/",
                        "skill-creator/",
                        "Apex-HyperStore-Agent/",
                        "pyproject.toml",
                        "README.md",
                        "CHANGELOG.md",
                        "LICENSE",
                        ".gitignore",
                        ".github/",
                    )
                ):
                    warnings.append(f"Non-standard resource path '{rel_str}'; prefer scripts/, references/, or assets/.")
                resources.append(rel_str)

        # Check markdown relative links in body for path traversal
        for match in re.finditer(r"\]\(([^)]+)\)", body):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if ".." in target or target.startswith("/"):
                errors.append(f"Prohibited relative path traversal or absolute path in SKILL.md link: '{target}'")

        # Check doc-reference integrity outside code fences
        un_fenced = FENCE_RE.sub("", body)
        for token_match in DOC_PATH_TOKEN_RE.finditer(un_fenced):
            token_path = token_match.group(1)
            if not (resolved_root / token_path).exists():
                warnings.append(f"SKILL.md references '{token_path}', which does not exist in {resolved_root.name}/.")

        if strict and warnings:
            errors.extend(f"[strict] {w}" for w in warnings)

        skill_kind = (
            "coding_agent_dev_skill"
            if body and ("adk-agent-builder" in body or "coding agent" in body.lower() or "create_agent.py" in body)
            else "runtime_adk_skill"
        )

        return SkillValidationReport(
            skill_dir=str(skill_dir),
            skill_name=name,
            skill_kind=skill_kind,
            valid=len(errors) == 0,
            line_count=line_count,
            errors=errors,
            warnings=warnings,
            discovered_resources=resources,
        )

    @staticmethod
    def package_skill_archive(
        skill_dir: Path,
        output_dir: Optional[Path] = None,
    ) -> SkillPackageReport:
        """Package a validated skill directory into a clean `.skill` zip archive (excluding .env, *.db, tests, caches)."""
        val = SkillValidator.validate_skill_directory(skill_dir)
        if not val.valid:
            raise ValueError(f"Refusing to package invalid skill '{skill_dir}': {val.errors}")

        resolved = skill_dir.resolve()
        skill_name = val.skill_name or resolved.name
        dest_dir = output_dir.resolve() if output_dir else (resolved / "dist")
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive_path = dest_dir / f"{skill_name}.skill"

        exclude_globs = {".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "*.pyc", "*.pyo", "*.log", "*.skill"}
        root_exclude = {"tests", "evals"}

        packaged: List[str] = []
        skipped = 0

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(resolved.rglob("*")):
                if not item.is_file():
                    continue
                rel = item.relative_to(resolved)
                if any(part in IGNORED_SKILL_DIRS for part in rel.parts[:-1]):
                    skipped += 1
                    continue
                if rel.parts and rel.parts[0] in root_exclude:
                    skipped += 1
                    continue
                if any(fnmatch.fnmatch(item.name, pat) for pat in exclude_globs):
                    skipped += 1
                    continue
                arcname = f"{resolved.name}/{rel.as_posix()}"
                zf.write(item, arcname=arcname)
                packaged.append(arcname)

        return SkillPackageReport(
            skill_dir=str(skill_dir),
            skill_name=skill_name,
            archive_path=str(archive_path),
            packaged_files=packaged,
            skipped_count=skipped,
            valid=True,
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[Optional[Dict[str, Any]], str]:
        if not text.startswith("---"):
            return None, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None, text
        try:
            parsed = yaml.safe_load(parts[1])
            if not isinstance(parsed, dict):
                return None, parts[2]
            return parsed, parts[2]
        except Exception:
            return None, text
