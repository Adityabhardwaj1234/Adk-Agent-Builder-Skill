"""Free-tier Gemini API Quota Budget Manager & Paced Slice Planner (20 messages/day & 5 RPM safe)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class QuotaBudgetPolicy(CompatModel):
    """Configures daily and per-minute API request limits for free-tier or rate-limited keys."""

    daily_message_limit: int = 20
    requests_per_minute_limit: int = 5
    min_interval_seconds: float = 13.0
    reserve_messages_for_smoke: int = 2
    require_offline_pass_before_live: bool = True
    rotate_models: List[str] = Field(default_factory=lambda: ["gemini-2.5-flash"])


class QuotaSlice(CompatModel):
    """Represents a single paced slice of test/evaluation cases that fits within RPM/RPD limits."""

    slice_id: str
    model: str
    case_ids: List[str] = Field(default_factory=list)
    estimated_messages: int = 0
    must_count: int = 0
    recommended_pause_after_seconds: int = 75


class QuotaEstimateReport(CompatModel):
    """Pre-flight quota cost estimate and slice execution plan."""

    spec_path: str
    spec_format: str  # "adk_evalset" or "http_spec"
    total_cases: int = 0
    total_estimated_messages: int = 0
    must_cases_estimated_messages: int = 0
    daily_limit_per_model: int = 20
    models_configured: List[str] = Field(default_factory=list)
    effective_daily_capacity: int = 20
    consumed_today: int = 0
    remaining_today: int = 20
    fits_in_single_model_daily_quota: bool = True
    fits_in_remaining_budget: bool = True
    recommended_min_interval_seconds: float = 13.0
    recommended_slices: List[QuotaSlice] = Field(default_factory=list)
    deferred_case_ids: List[str] = Field(default_factory=list)
    guidance: List[str] = Field(default_factory=list)


class QuotaBudgetManager:
    """Plans, tracks, and enforces daily API message budgets (e.g. 20 messages/day free tier)."""

    DEFAULT_LEDGER_FILENAME = ".adk_quota_ledger.json"

    @staticmethod
    def _today_key() -> str:
        return datetime.date.today().isoformat()

    @staticmethod
    def load_ledger(ledger_path: Path) -> Dict[str, Any]:
        if not ledger_path.exists():
            return {"date": QuotaBudgetManager._today_key(), "models": {}, "history": []}
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
            if data.get("date") != QuotaBudgetManager._today_key():
                return {"date": QuotaBudgetManager._today_key(), "models": {}, "history": data.get("history", [])[-30:]}
            return data
        except Exception:
            return {"date": QuotaBudgetManager._today_key(), "models": {}, "history": []}

    @staticmethod
    def record_usage(
        ledger_path: Path,
        model: str,
        messages_used: int,
        *,
        run_label: str = "live_eval",
    ) -> Dict[str, Any]:
        """Record consumed live messages in the daily ledger."""
        ledger = QuotaBudgetManager.load_ledger(ledger_path)
        models = ledger.setdefault("models", {})
        models[model] = int(models.get(model, 0)) + max(0, int(messages_used))
        ledger.setdefault("history", []).append(
            {
                "date": ledger["date"],
                "model": model,
                "messages_used": int(messages_used),
                "run_label": run_label,
            }
        )
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        return ledger

    @staticmethod
    def estimate_and_plan(
        spec_path: Path,
        policy: Optional[QuotaBudgetPolicy] = None,
        *,
        ledger_path: Optional[Path] = None,
        slice_size: int = 3,
    ) -> QuotaEstimateReport:
        """Analyze a test spec (`spec.json`) or ADK EvalSet (`.evalset.json`) and build a 20-msg/day safe plan."""
        pol = policy or QuotaBudgetPolicy()
        raw = json.loads(spec_path.read_text(encoding="utf-8"))

        cases: List[Dict[str, Any]] = []
        if "tests" in raw and isinstance(raw["tests"], list):
            spec_format = "http_spec"
            for t in raw["tests"]:
                turns = t.get("turns", [{"user": ""}])
                cases.append(
                    {
                        "id": str(t.get("id", "unknown")),
                        "severity": str(t.get("severity", "must")).lower(),
                        "messages": max(1, len(turns)),
                    }
                )
        elif "eval_cases" in raw and isinstance(raw["eval_cases"], list):
            spec_format = "adk_evalset"
            for c in raw["eval_cases"]:
                conv = c.get("conversation", [])
                cases.append(
                    {
                        "id": str(c.get("eval_id", "unknown")),
                        "severity": "must",
                        "messages": max(1, len(conv)),
                    }
                )
        else:
            raise ValueError(f"Unrecognized specification format in {spec_path}: expected 'tests' or 'eval_cases'.")

        # Prioritize 'must' cases before 'should' cases so a 20-message/day cap tests critical behavior first
        ordered_cases = sorted(cases, key=lambda x: (0 if x["severity"] == "must" else 1, x["id"]))

        total_msgs = sum(c["messages"] for c in ordered_cases)
        must_msgs = sum(c["messages"] for c in ordered_cases if c["severity"] == "must")

        models = pol.rotate_models or ["gemini-2.5-flash"]
        effective_capacity = pol.daily_message_limit * len(models)

        consumed = 0
        if ledger_path is not None:
            ledger = QuotaBudgetManager.load_ledger(ledger_path)
            consumed = sum(int(v) for v in ledger.get("models", {}).values())

        remaining = max(0, effective_capacity - consumed)

        # Build slices that fit inside remaining budget
        slices: List[QuotaSlice] = []
        deferred: List[str] = []
        budget_cursor = 0
        current_batch: List[Dict[str, Any]] = []

        for c in ordered_cases:
            if budget_cursor + c["messages"] <= remaining:
                current_batch.append(c)
                budget_cursor += c["messages"]
                if len(current_batch) >= max(1, slice_size):
                    idx = len(slices) + 1
                    model_name = models[(idx - 1) % len(models)]
                    slices.append(
                        QuotaSlice(
                            slice_id=f"slice_{idx:02d}",
                            model=model_name,
                            case_ids=[item["id"] for item in current_batch],
                            estimated_messages=sum(item["messages"] for item in current_batch),
                            must_count=sum(1 for item in current_batch if item["severity"] == "must"),
                            recommended_pause_after_seconds=75,
                        )
                    )
                    current_batch = []
            else:
                deferred.append(c["id"])

        if current_batch:
            idx = len(slices) + 1
            model_name = models[(idx - 1) % len(models)]
            slices.append(
                QuotaSlice(
                    slice_id=f"slice_{idx:02d}",
                    model=model_name,
                    case_ids=[item["id"] for item in current_batch],
                    estimated_messages=sum(item["messages"] for item in current_batch),
                    must_count=sum(1 for item in current_batch if item["severity"] == "must"),
                    recommended_pause_after_seconds=75,
                )
            )

        min_interval = max(pol.min_interval_seconds, round(60.0 / max(1, pol.requests_per_minute_limit) + 1.0, 1))
        guidance: List[str] = [
            "Run offline validation (`adk-agent-builder validate`, `adk-agent-builder test`, and `adk-agent-builder eval`) FIRST at 0 API calls.",
            f"Use `--min-interval {min_interval:.0f}` with `scripts/testing.py` to stay under {pol.requests_per_minute_limit} RPM.",
        ]
        if total_msgs > pol.daily_message_limit:
            guidance.append(
                f"Suite requires ~{total_msgs} messages, which exceeds a single model's {pol.daily_message_limit} messages/day cap. "
                f"Execute the prioritized MUST slices ({len(slices)} slices, {budget_cursor} messages) or pass `--rotate gemini-2.5-flash,gemini-3.5-flash`."
            )
        else:
            guidance.append(
                f"Suite requires ~{total_msgs} messages, which fits within the {pol.daily_message_limit} messages/day budget ({remaining} remaining today)."
            )

        return QuotaEstimateReport(
            spec_path=str(spec_path),
            spec_format=spec_format,
            total_cases=len(ordered_cases),
            total_estimated_messages=total_msgs,
            must_cases_estimated_messages=must_msgs,
            daily_limit_per_model=pol.daily_message_limit,
            models_configured=models,
            effective_daily_capacity=effective_capacity,
            consumed_today=consumed,
            remaining_today=remaining,
            fits_in_single_model_daily_quota=(total_msgs <= pol.daily_message_limit),
            fits_in_remaining_budget=(total_msgs <= remaining),
            recommended_min_interval_seconds=min_interval,
            recommended_slices=slices,
            deferred_case_ids=deferred,
            guidance=guidance,
        )
