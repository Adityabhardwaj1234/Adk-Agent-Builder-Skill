"""Offline checks for run_paced_suite - no model, no server."""
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, ".")
from run_paced_suite import INFRA, is_infra_failure, merge, reclassify

SPEC = {"requirements": [{"id": "R1", "text": "a", "severity": "must"},
                         {"id": "R2", "text": "b", "severity": "should"}],
        "tests": [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}]}


def rec(tid, passed, cls=None, reqs=("R1",), cat="functional", sev="must", lat=5.0):
    return {"test_id": tid, "passed": passed, "failure_class": cls, "requirement_ids": list(reqs),
            "category": cat, "severity": sev, "latency_s": [lat], "tokens": 100,
            "tool_calls": ["lookup_order"], "agents": ["orders_agent"], "final_response": "x",
            "first_user_input": "y", "failed_checks": [], "flaky": False}


def run(label, results, expect_verdict, expect_passed):
    with tempfile.TemporaryDirectory() as d:
        s = merge(results, SPEC, Path(d))
    ok = s["verdict"] == expect_verdict and s["tests_passed"] == expect_passed
    print(f"{'ok  ' if ok else 'FAIL'} {label:<52} verdict={s['verdict']:<14} "
          f"passed={s['tests_passed']}/{s['tests_total']}")
    return ok


def recheck(name, ok):
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    return ok


def recheck(name, ok):
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    return ok


fails = 0
fails += not run("all pass -> PASS", [rec("T1", True), rec("T2", True, reqs=("R2",), sev="should"),
                                      rec("T3", True, reqs=("R2",), sev="should")], "PASS", 3)
fails += not run("all infra failures -> INFRA_BLOCKED",
                 [rec("T1", True), rec("T2", False, "QUOTA_OR_RATE_LIMIT"),
                  rec("T3", False, "INFRA_NETWORK")], "INFRA_BLOCKED", 1)
fails += not run("assertion failure -> NEEDS_FIX",
                 [rec("T1", True), rec("T2", True, reqs=("R2",), sev="should"),
                  rec("T3", False, "ASSERTION_FAILED", reqs=("R2",), sev="should")],
                 "NEEDS_FIX", 2)
fails += not run("must fail -> not PASS even at 90%",
                 [rec("T1", False, "ASSERTION_FAILED"), rec("T2", True, reqs=("R2",), sev="should"),
                  rec("T3", True, reqs=("R2",), sev="should")], "NEEDS_FIX", 2)

with tempfile.TemporaryDirectory() as d:
    s = merge([rec("T1", True), rec("T2", True, reqs=("R2",), sev="should"),
               rec("T3", False, "ASSERTION_FAILED", reqs=("R2",), sev="should")], SPEC, Path(d))
    cov = s["requirements"]
    written_order = [r["test_id"] for r in
                     json.loads((Path(d) / "results.json").read_text())["results"]]
    json_exists = (Path(d) / "results.json").exists()
    md_exists = (Path(d) / "report.md").exists()
checks = [
    ("R1 MET", cov["R1"]["status"] == "MET"),
    ("R2 NOT_MET", cov["R2"]["status"] == "NOT_MET"),
    ("R1 coverage 1/1", (cov["R1"]["passed"], cov["R1"]["tests"]) == (1, 1)),
    ("by_category counted", s["by_category"]["functional"]["total"] == 3),
    ("latency p50 == 5.0", s["latency"]["p50_s"] == 5.0),
    ("failure_classes tallied", s["failure_classes"] == {"ASSERTION_FAILED": 1}),
    ("results.json written", json_exists),
    ("report.md written", md_exists),
    ("retried counted", s["retried_tests"] == 0),
    ("is_infra_failure(quota)", is_infra_failure({"failure_class": "QUOTA_OR_RATE_LIMIT"})),
    ("not is_infra_failure(assert)", not is_infra_failure({"failure_class": "ASSERTION_FAILED"})),
    ("is_infra_failure(None)", not is_infra_failure({"failure_class": None})),
    ("result order follows spec", written_order == ["T1", "T2", "T3"]),
]
for name, ok in checks:
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    fails += not ok

# ---------------------------------------------------------------- reclassify
QUOTA_LOG = ("2026-10-17 ERROR google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED. "
             "Quota exceeded for metric: generate_content_free_tier_requests\n")
OVERLOAD_LOG = ("google.genai.errors.ServerError: 503 UNAVAILABLE. This model is currently "
                "experiencing high demand.\n")
CLEAN_LOG = "2026-10-17 INFO server started\n"
with tempfile.TemporaryDirectory() as d:
    lp = Path(d) / "api_server.log"

    lp.write_text(CLEAN_LOG, encoding="utf-8")
    off = len(CLEAN_LOG)
    rs = reclassify([rec("T1", False, "AGENT_RUNTIME_ERROR")], lp, off)
    recheck("clean log -> failure left alone", rs[0]["failure_class"] == "AGENT_RUNTIME_ERROR")

    lp.write_text(CLEAN_LOG + QUOTA_LOG, encoding="utf-8")
    off2 = lp.stat().st_size - len(QUOTA_LOG)
    r = rec("T1", False, "AGENT_RUNTIME_ERROR")
    r["tokens"] = 0
    rs = reclassify([r], lp, off2)
    recheck("429 after offset + 0 tokens -> throttled",
            rs[0]["failure_class"] == "QUOTA_OR_RATE_LIMIT" and rs[0].get("_throttled"))

    lp.write_text(CLEAN_LOG + QUOTA_LOG, encoding="utf-8")
    r = rec("T1", False, "AGENT_RUNTIME_ERROR")
    r["tokens"] = 1500
    rs = reclassify([r], lp, off2)
    recheck("429 but tokens spent -> real error kept",
            rs[0]["failure_class"] == "AGENT_RUNTIME_ERROR")

    lp.write_text(QUOTA_LOG + CLEAN_LOG, encoding="utf-8")
    rs = reclassify([rec("T1", False, "AGENT_RUNTIME_ERROR")], lp, 0)
    recheck("quota before offset is ignored (slice-scoped)",
            rs[0]["failure_class"] == "AGENT_RUNTIME_ERROR")

    lp.write_text(CLEAN_LOG + OVERLOAD_LOG, encoding="utf-8")
    off3 = lp.stat().st_size - len(OVERLOAD_LOG)
    r = rec("T1", False, "AGENT_RUNTIME_ERROR")
    r["tokens"] = 0
    rs = reclassify([r], lp, off3)
    recheck("503 high demand -> throttled", rs[0]["failure_class"] == "QUOTA_OR_RATE_LIMIT")

    lp.write_text(CLEAN_LOG + QUOTA_LOG, encoding="utf-8")
    rs = reclassify([rec("T1", True)], lp, off2)
    recheck("passing test never reclassified", rs[0].get("failure_class") is None)

print(f"\n{'PASS' if not fails else 'FAIL'}: {len(checks) + 4 + 6 - fails} checks passed")
sys.exit(1 if fails else 0)
