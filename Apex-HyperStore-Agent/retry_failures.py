"""Build a spec containing only the tests that failed in a previous run, then merge the
new results back over the old ones. Used so a quota-limited environment can re-verify the
failures without spending budget re-running the passes.

    .venv\\Scripts\\python.exe retry_failures.py --prev adk_runs/run3 --out adk_runs/run4
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, ".")
from run_paced_suite import merge  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--prev", default="adk_runs/run3")
ap.add_argument("--out", default="adk_runs/run4")
ap.add_argument("--keep-infrastructure", action="store_true",
                help="also re-run tests that failed with an INFRA class (default: only real failures)")
a = ap.parse_args()

prev = Path(a.prev)
out = Path(a.out)
prev_data = json.loads((prev / "results.json").read_text(encoding="utf-8"))
prev_results = prev_data["results"]
spec = json.loads(Path("adk_runs/spec.json").read_text(encoding="utf-8"))

INFRA = {"INFRA_NETWORK", "AUTH_INVALID_KEY", "QUOTA_OR_RATE_LIMIT", "MODEL_NOT_FOUND",
         "AGENT_RUNTIME_ERROR"}


def needs_rerun(r: dict) -> bool:
    if r["passed"]:
        return False
    if a.keep_infrastructure and r.get("failure_class") in INFRA:
        return True
    # Re-run anything that was not clearly an infrastructure problem.
    return r.get("failure_class") not in INFRA


retry_ids = [r["test_id"] for r in prev_results if needs_rerun(r)]
by_id = {t["id"]: t for t in spec["tests"]}
print(f"previous: {prev_results and len(prev_results)} tests, "
      f"{sum(r['passed'] for r in prev_results)} passed")
print(f"to re-run ({len(retry_ids)}): {', '.join(retry_ids)}")

out.mkdir(parents=True, exist_ok=True)
sub = {"_comment": f"re-run of the failures from {prev}",
       "requirements": spec["requirements"],
       "tests": [by_id[i] for i in retry_ids]}
(out / "spec.json").write_text(json.dumps(sub, indent=2, ensure_ascii=False), encoding="utf-8")

if not a.keep_infrastructure:
    # Keep everything from the previous run; the runner's merge will overlay the re-runs.
    shutil.copyfile(prev / "results.json", out / "results_prev.json")
    print(f"wrote {out / 'spec.json'} (merge source: {out / 'results_prev.json'})")
