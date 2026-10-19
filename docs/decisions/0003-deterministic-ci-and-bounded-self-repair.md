# ADR 0003: Deterministic CI & Bounded Self-Repair Loop

- **Status**: Accepted
- **Date**: 2026-10-18

## Context
Unbounded code regeneration loops waste API quota and can overwrite working files. Furthermore, ordinary CI pipelines must not require live paid LLM credentials or cloud infrastructure.

## Decision
1. Cap `DiagnosticsAndRepairEngine.run_bounded_repair` (`src/adk_agent_builder/diagnostics/repair.py`) at `max_attempts=3` with stage-specific root-cause diagnosis and regression re-verification.
2. Run all default unit, contract, security, evaluation, and 13-step acceptance tests deterministically offline, while gating live provider/cloud deployment operations behind explicit environment variables and `--approve-billable`.
