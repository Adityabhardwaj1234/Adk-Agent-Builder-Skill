"""Consolidate the paced runs into one final results.json.

Later runs win for any test they re-ran, so the chain run3 -> run4 -> run5 reads as a single
suite that was progressively unblocked. Also records, per test, which model produced the
result and how many attempts it took.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from run_paced_suite import merge  # noqa: E402

RUNS = ["adk_runs/run3", "adk_runs/run4", "adk_runs/run5"]
spec = json.loads(Path("adk_runs/spec.json").read_text(encoding="utf-8"))

latest: dict[str, dict] = {}
history: dict[str, list[str]] = {}
models: dict[str, str] = {}

for run in RUNS:
    f = Path(run) / "results.json"
    if not f.exists():
        print(f"skip {run} (no results.json)")
        continue
    data = json.loads(f.read_text(encoding="utf-8"))
    for r in data["results"]:
        tid = r["test_id"]
        history.setdefault(tid, []).append(
            f"{Path(run).name}:{'PASS' if r['passed'] else 'FAIL'}")
        models[tid] = r.get("_model", r.get("_model", "?"))
        latest[tid] = r
    print(f"{run}: {len(data['results'])} results, "
          f"{sum(x['passed'] for x in data['results'])} passed")

for tid, r in latest.items():
    r["_runs"] = history[tid]
    r["_model"] = models.get(tid, "?")

final = [latest[t["id"]] for t in spec["tests"] if t["id"] in latest]
missing = [t["id"] for t in spec["tests"] if t["id"] not in latest]
if missing:
    print("WARNING: no result for", missing)

summary = merge(final, spec, Path("adk_runs/final"))
print()
print(f"FINAL VERDICT {summary['verdict']}: {summary['tests_passed']}/{summary['tests_total']} "
      f"passed, MUST {summary['must_passed']}/{summary['must_total']}")
print(f"latency p50 {summary['latency']['p50_s']}s p95 {summary['latency']['p95_s']}s "
      f"max {summary['latency']['max_s']}s | tokens {summary['tokens_total']:,} | "
      f"avg tool calls {summary['avg_tool_calls']}")
print("by category:", summary["by_category"])
print("failure classes:", summary["failure_classes"])
multi = sum(1 for r in final if len(r["_runs"]) > 1)
print(f"tests re-run at least once: {multi}")
used: dict = {}
for r in final:
    used[r["_model"]] = used.get(r["_model"], 0) + 1
print("models used:", used)
Path("adk_runs/final/consolidation.json").write_text(json.dumps(
    {"runs": RUNS, "history": history, "models": models}, indent=2), encoding="utf-8")
