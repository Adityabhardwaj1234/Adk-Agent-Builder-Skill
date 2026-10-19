# ADR 0002: ADK v2.12.0 Compatibility & Pydantic v1/v2 Bridge

- **Status**: Accepted
- **Date**: 2026-10-18

## Context
Developer environments vary between base containers with `pydantic 1.10.x` and cloud environments with `pydantic 2.x` and `google-adk>=2.10.0`.

## Decision
1. Implement `CompatModel` (`src/adk_agent_builder/models/base.py`) providing `.to_dict()`, `.to_json()`, and `.from_dict()` across both Pydantic v1 and v2 while normalizing `Enum` and `Path` values into YAML/JSON-safe primitives.
2. Include `app/adk_compat.py` in generated ADK projects so projects import official `google.adk` classes when installed and fall back to a deterministic local runner in offline CI.
