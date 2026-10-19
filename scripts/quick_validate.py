#!/usr/bin/env python3
"""quick_validate.py - validate a skill folder before packaging or installing.

A *skill* is a folder with a ``SKILL.md`` at its root. ``SKILL.md`` must start
with YAML frontmatter that carries at least a ``name`` and a ``description``.
Those two fields are the entire always-loaded footprint of a skill: the name is
how it is installed and referred to, the description is how the model decides
to consult it. Both are therefore worth validating mechanically before the
skill is zipped, uploaded or copied anywhere.

Checks performed
  1. ``SKILL.md`` exists at the skill root (exactly one is *packaged* - nested
     copies inside excluded directories such as ``__pycache__`` do not count).
  2. The frontmatter is present, parseable, and contains only allowed keys.
  3. ``name`` is a kebab-case string of at most 64 characters.
  4. ``description`` is a string of at most 1024 characters with no angle
     brackets (``<`` / ``>`` would corrupt the metadata block some runtimes
     render).
  5. ``compatibility``, if present, is a string of at most 500 characters.
  6. Documentation integrity (warning, not error): every ``scripts/...``,
     ``references/...`` or ``assets/...`` path mentioned in the SKILL.md body
     actually exists. A skill whose own instructions point at missing files
     fails the moment it is used; this check catches exactly that bug.

Design notes
  - Standard library only. If PyYAML happens to be installed it is used; if not,
    a small frontmatter parser handles the simple ``key: value`` scalars that
    frontmatter is expected to contain. Complex YAML therefore degrades to a
    clear message instead of a crash.
  - ``validate_skill()`` returns ``(valid, report)`` and never raises for
    invalid skills - callers (package_skill.py, tests) rely on that contract.
  - Warnings keep ``valid`` true; pass ``strict=True`` (or ``--strict`` on the
    CLI) to turn them into failures.

Usage
    python quick_validate.py <skill_directory> [--strict] [--quiet]
Exit codes: 0 valid, 1 invalid (or warnings under --strict).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}

# Directories whose contents are not packaged as part of the skill, so nested
# SKILL.md files inside them are ignored by the single-SKILL.md check below.
# Keep in sync with package_skill.py.
EXCLUDED_DIR_PARTS = {"__pycache__", "node_modules", ".venv", "venv", ".git"}
ROOT_EXCLUDED_DIR_PARTS = {"evals", "tests", "adk_runs"}

FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PATH_TOKEN_RE = re.compile(r"(?<![\w./-])((?:scripts|references|assets|tests|evals)/[\w][\w./-]*[\w/])")


def _counts_as_skill_md(rel_path: Path) -> bool:
    """True if a SKILL.md at rel_path (relative to the skill root) would be packaged."""
    dir_parts = rel_path.parts[:-1]
    if any(part in EXCLUDED_DIR_PARTS for part in dir_parts):
        return False
    if dir_parts and dir_parts[0] in ROOT_EXCLUDED_DIR_PARTS:
        return False
    return True


def _parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """Parse the SKILL.md frontmatter. Returns (mapping, error)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, "No YAML frontmatter found (file must start with a '---' block)"
    raw = match.group(1)
    try:  # prefer real YAML when available
        import yaml  # type: ignore

        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None, "Frontmatter must be a YAML dictionary"
        return data, None
    except ImportError:
        pass
    except Exception as e:  # yaml present but the document is malformed
        return None, f"Invalid YAML in frontmatter: {e}"

    # Minimal fallback parser: simple `key: value` scalars, # comments stripped.
    data: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            return None, (
                "Frontmatter is too complex for the built-in parser (a line without ':'). "
                "Install PyYAML or simplify the frontmatter"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]
        if value.endswith("#") or " #" in value:  # strip trailing comments on scalars
            value = value.split(" #", 1)[0].rstrip()
        if key in data:
            return None, (
                f"Frontmatter key '{key}' appears more than once - too complex for the "
                "built-in parser. Install PyYAML or fix the frontmatter"
            )
        data[key] = value
    return data, None


def _strip_code_fences(text: str) -> str:
    """Return the SKILL.md body with fenced code blocks removed, so that example
    paths inside code samples are not mistaken for real file references."""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _check_referenced_paths(skill_path: Path, skill_md: Path) -> list[str]:
    """Warn about scripts/references/assets paths mentioned in the body that do not exist."""
    body = _strip_code_fences(skill_md.read_text(encoding="utf-8"))
    body = body.split("---", 2)[-1] if body.startswith("---") else body
    missing = []
    for token in dict.fromkeys(PATH_TOKEN_RE.findall(body)):
        if any(ch in token for ch in "*<>{}"):  # globs / placeholders are not literal paths
            continue
        if not (skill_path / token).exists():
            missing.append(token)
    return missing


def validate_skill(skill_path, *, strict: bool = False):
    """Validate a skill folder.

    Returns:
        (valid: bool, report: str). ``report`` is human readable and contains
        every finding (errors and warnings). Never raises for bad skills.
    """
    skill_path = Path(skill_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not skill_path.exists() or not skill_path.is_dir():
        return False, f"Skill folder not found: {skill_path}"

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found at the skill root"

    nested = sorted(
        str(p.relative_to(skill_path)) for p in skill_path.rglob("SKILL.md")
        if p.resolve() != skill_md.resolve() and _counts_as_skill_md(p.relative_to(skill_path))
    )
    if nested:
        errors.append(
            "A skill must contain exactly one SKILL.md at <folder>/SKILL.md. "
            f"Extra: {', '.join(nested)}. Package separate skills separately, or rename "
            "supporting documents (e.g. references/<topic>.md)"
        )

    text = skill_md.read_text(encoding="utf-8")
    frontmatter, err = _parse_frontmatter(text)
    if err:
        errors.append(err)
        frontmatter = {}

    unexpected = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected:
        errors.append(
            f"Unexpected key(s) in frontmatter: {', '.join(sorted(unexpected))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    if "name" not in frontmatter:
        errors.append("Missing 'name' in frontmatter")
    else:
        name = frontmatter.get("name")
        if not isinstance(name, str):
            errors.append(f"'name' must be a string, got {type(name).__name__}")
        else:
            name = name.strip()
            if not NAME_RE.match(name):
                errors.append(
                    f"'name' is '{name}' - use kebab-case (lowercase letters, digits, single "
                    "hyphens; no leading/trailing hyphen)"
                )
            elif len(name) > 64:
                errors.append(f"'name' is too long ({len(name)} characters, max 64)")
            elif name != skill_path.resolve().name:
                warnings.append(
                    f"'name' is '{name}' but the folder is '{skill_path.resolve().name}' - installing "
                    "from this folder may register the skill under a different name than intended"
                )

    if "description" not in frontmatter:
        errors.append("Missing 'description' in frontmatter")
    else:
        description = frontmatter.get("description")
        if not isinstance(description, str):
            errors.append(f"'description' must be a string, got {type(description).__name__}")
        else:
            description = description.strip()
            if "<" in description or ">" in description:
                errors.append("'description' cannot contain angle brackets (< or >)")
            if len(description) > 1024:
                errors.append(f"'description' is too long ({len(description)} characters, max 1024)")

    compatibility = frontmatter.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str):
            errors.append(f"'compatibility' must be a string, got {type(compatibility).__name__}")
        elif len(compatibility) > 500:
            errors.append(f"'compatibility' is too long ({len(compatibility)} characters, max 500)")

    missing_paths = _check_referenced_paths(skill_path, skill_md)
    if missing_paths:
        warnings.append(
            "SKILL.md mentions paths that do not exist inside the skill: "
            + ", ".join(missing_paths)
            + " (fine if the skill creates them in the user's project; a bug if they should be bundled)"
        )

    lines = []
    if errors:
        lines.append(f"INVALID: {len(errors)} error(s)")
        lines += [f"  error: {e}" for e in errors]
    lines += [f"  warning: {w}" for w in warnings]
    if not errors and not warnings:
        lines.append(f"Valid skill: '{frontmatter.get('name', skill_path.name)}' looks good")
    elif not errors:
        lines.append("Valid skill (with warnings)")
    report = "\n".join(lines)
    valid = not errors and not (strict and warnings)
    return valid, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("Usage")[0].strip())
    ap.add_argument("skill_directory", help="Folder containing SKILL.md")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    ap.add_argument("--quiet", action="store_true", help="Print only the first/report summary line")
    args = ap.parse_args(argv)

    valid, report = validate_skill(args.skill_directory, strict=args.strict)
    print(report.splitlines()[0] if args.quiet else report)
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
