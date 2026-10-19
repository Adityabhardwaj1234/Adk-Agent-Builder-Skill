# ADR 0001: Dual-Layer Architecture (Skill + Python Engineering Toolkit)

- **Status**: Accepted
- **Date**: 2026-10-18

## Context
Instruction-only skills (`SKILL.md` without executable tooling) force coding agents to reinvent project scaffolding, evaluation schemas, AST validation, and deployment scripts on every turn, leading to inconsistent code quality and unverified claims.

## Decision
Split the system into:
1. **Layer A (`SKILL.md` + `references/`)**: Concise operational instructions (<150 lines) following progressive disclosure.
2. **Layer B (`src/adk_agent_builder/`)**: A tested Python package with a 16-command CLI (`adk-agent-builder`) that performs deterministic scaffolding, AST/security validation, test execution, ADK evaluation, and bounded self-repair.
