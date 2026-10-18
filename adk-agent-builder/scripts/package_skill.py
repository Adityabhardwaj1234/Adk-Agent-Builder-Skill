#!/usr/bin/env python3
"""package_skill.py - create a distributable ``.skill`` file from a skill folder.

A ``.skill`` file is a zip archive of the skill folder (whose top-level entry
keeps the folder name, e.g. ``adk-agent-builder/SKILL.md``) that skill
marketplaces and agent runtimes can install directly.

What is packaged
    Everything in the skill folder *except* build artifacts, local development
    state and secrets. Exclusions are deliberate:

    - ``__pycache__``, ``node_modules``, ``.venv``/``venv``, ``.git`` and the
      other cache/tooling directories are noise or huge and would break on
      other machines.
    - ``evals/`` and ``tests/`` keep the development suites out of the
      distribution - the shipped skill is instructions plus runtime scripts.
    - ``.env``, ``*.db``/``*.sqlite*`` and ``*.log`` are *never* shipped. An
      ADK workspace can contain an API key and a session database one folder
      away; this guard makes leaking them impossible rather than unlikely.

Validation runs first (via quick_validate.py in the same directory): a skill
that fails validation is not packaged. Warnings (for example, an unusual name)
are printed but do not block.

Usage
    python package_skill.py <path/to/skill-folder> [output-directory] [--dry-run]

Examples
    python package_skill.py ./adk-agent-builder
    python package_skill.py ./adk-agent-builder ./dist           # writes dist/adk-agent-builder.skill
    python package_skill.py ./adk-agent-builder --dry-run        # list contents, write nothing

Exit codes: 0 packaged (or dry-run succeeded), 1 validation/packaging error.
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quick_validate import validate_skill  # noqa: E402  (same-directory import by design)

# Excluded at any depth.
EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".git", ".hg", ".svn",
    ".venv", "venv", "env", ".env.d", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "adk_runs", ".adk", "dist", "build", "*.egg-info",
}
# Excluded only at the skill root (development suites, not part of the product).
ROOT_EXCLUDE_DIRS = {"evals", "tests"}
# File name patterns excluded at any depth. Secrets and local databases first.
EXCLUDE_GLOBS = {
    ".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "*.db-journal", "*.db-wal",
    "*.pyc", "*.pyo", "*.log", "*.skill",
}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def should_exclude(rel_path: Path) -> tuple[bool, str]:
    """Return (exclude, reason). rel_path is relative to the skill folder root."""
    parts = rel_path.parts
    for part in parts[:-1]:
        if part in EXCLUDE_DIRS or any(fnmatch.fnmatch(part, pat) for pat in EXCLUDE_DIRS if "*" in pat):
            return True, f"directory '{part}' is excluded"
    if parts and parts[0] in ROOT_EXCLUDE_DIRS:
        return True, f"root directory '{parts[0]}' is not shipped"
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True, "OS metadata file"
    for pat in EXCLUDE_GLOBS:
        if fnmatch.fnmatch(name, pat):
            return True, f"matches '{pat}' (never shipped)"
    return False, ""


def collect_files(skill_path: Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Split the folder into (files to package, [(excluded file, reason)])."""
    included, excluded = [], []
    for file_path in sorted(skill_path.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(skill_path)
        drop, reason = should_exclude(rel)
        if drop:
            excluded.append((rel, reason))
        else:
            included.append(rel)
    return included, excluded


def package_skill(skill_path, output_dir=None, *, dry_run: bool = False):
    """Package a skill folder into a .skill file.

    Returns the path to the created file (or the path it *would* create in a
    dry run), or None on error.
    """
    skill_path = Path(skill_path).resolve()
    if not skill_path.exists() or not skill_path.is_dir():
        print(f"Error: skill folder not found: {skill_path}")
        return None

    print(f"Validating {skill_path.name} ...")
    valid, report = validate_skill(skill_path)
    print(report)
    if not valid:
        print("Please fix the errors above before packaging.")
        return None

    included, excluded = collect_files(skill_path)
    if not included:
        print("Error: nothing to package (every file was excluded?).")
        return None
    if not any(rel == Path("SKILL.md") for rel in included):
        print("Error: SKILL.md was excluded from the package; refusing to write a broken archive.")
        return None

    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
    else:
        output_path = Path.cwd()
    skill_filename = output_path / f"{skill_name}.skill"

    print(f"\nContents ({len(included)} files):")
    total_bytes = 0
    for rel in included:
        size = (skill_path / rel).stat().st_size
        total_bytes += size
        print(f"  + {skill_name}/{rel.as_posix()}  ({size:,} bytes)")
    if excluded:
        by_reason: dict[str, int] = {}
        for _rel, reason in excluded:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        print(f"\nSkipped {len(excluded)} file(s):")
        for reason, count in sorted(by_reason.items()):
            print(f"  - {count} x {reason}")

    if dry_run:
        print(f"\nDry run: {skill_filename} would receive {len(included)} files "
              f"({total_bytes:,} bytes before compression)")
        return skill_filename

    output_path.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for rel in included:
                zipf.write(skill_path / rel, Path(skill_name) / rel)
        # Re-open and verify before declaring success - a truncated zip that the
        # caller only discovers at install time is the worst failure mode.
        with zipfile.ZipFile(skill_filename) as zipf:
            bad = zipf.testzip()
            names = zipf.namelist()
            if bad is not None:
                raise RuntimeError(f"archive is corrupt at {bad}")
            if f"{skill_name}/SKILL.md" not in names:
                raise RuntimeError("SKILL.md missing from archive root")
        print(f"\nPackaged {len(names)} entries, {skill_filename.stat().st_size:,} bytes -> {skill_filename}")
        return skill_filename
    except Exception as e:
        print(f"Error creating .skill file: {e}")
        try:
            skill_filename.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("Usage")[0].strip())
    ap.add_argument("skill_folder", help="Path to the skill folder (contains SKILL.md)")
    ap.add_argument("output_directory", nargs="?", default=None,
                    help="Where to write <name>.skill (default: current directory)")
    ap.add_argument("--dry-run", action="store_true", help="List archive contents without writing the file")
    args = ap.parse_args(argv)

    print(f"Packaging skill: {args.skill_folder}"
          + (f"  ->  output: {args.output_directory}" if args.output_directory else ""))
    result = package_skill(args.skill_folder, args.output_directory, dry_run=args.dry_run)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
