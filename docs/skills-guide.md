# Skill Authoring & Validation Guide (`docs/skills-guide.md`)

## 1. Runtime ADK Skills vs Coding-Agent Development Skills

- **Coding-Agent Development Skill**: The root `SKILL.md` in this repository (`name: adk-agent-builder`), used by coding assistants (Gemini, Claude Code, Antigravity, Codex) to operate the `adk-agent-builder` engineering toolkit.
- **Runtime ADK Agent Skills**: Domain skills loaded dynamically at runtime by an ADK agent via `SkillToolset` (ADK v2.10.0+ supports `SkillDiscoveryMode`, `ADK_ENABLE_SKILL_LIFECYCLE=1`, `EPHEMERAL` single-turn lifecycles, and `unload_skill`).

## 2. Validating a Skill (`adk-agent-builder skills`)

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli skills --skill-dir . --json
```

`SkillValidator` verifies:
1. Valid YAML frontmatter containing `name` (`^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$`) and `description` (20–1024 chars).
2. Progressive disclosure budget (`SKILL.md` <= 500 lines recommended).
3. Zero symlink escapes or `..` relative path traversal in markdown links or bundled files.
