#!/usr/bin/env python3
"""run_paced_suite.py - run the Apex test spec through testing.py without being rate limited.

The free Gemini tier is the constraint here, and it is two constraints at once:

  * a per-minute limit (5 generate_content requests/minute), and
  * a per-model DAILY limit. gemini-flash-latest (gemini-3.8-flash) and free-tier keys
    typically allow 20 requests/day; once that is spent, every later test fails with a
    429 that surfaces as `/run HTTP 500`.

Neither is an agent problem, but an unpaced suite therefore reports a wall of failures that
have nothing to do with the code. This runner works around that without modifying testing.py.
It starts one `adk api_server`, hands testing.py a small slice of the spec through
--base-url, and then:

  * tracks per-model daily request consumption against `--daily-quota-limit` (default 20),
  * rotates the model between slices when asked, because each model has its own daily bucket,
  * pauses between slices so the per-minute budget refills,
  * notices when a test failed for an INFRA reason (rate limit, network, quota) rather than
    an assertion failure, and re-runs just that test after an exponential backoff,
  * grows the pause when throttling actually happened, shrinks it when a slice came clean,
  * merges everything into one results.json + report.md using testing.py's own scoring rules,
    recording which model produced each result.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _resolve_testing_script() -> Path:
    candidates = [
        HERE.parent / "adk-agent-builder" / "scripts" / "testing.py",
        HERE.parent / "scripts" / "testing.py",
        HERE.parent / "adk-agent-builder" / "testing.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _resolve_venv_bin(binary_name: str, fallback: str) -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    ext = ".exe" if os.name == "nt" and not binary_name.endswith(".exe") else ""
    for root in (HERE, HERE.parent):
        candidate = root / ".venv" / scripts_dir / f"{binary_name}{ext}"
        if candidate.exists():
            return candidate
    which_res = shutil.which(binary_name)
    return Path(which_res) if which_res else Path(fallback)


TESTING = _resolve_testing_script()
PYTHON = _resolve_venv_bin("python", sys.executable)
ADK = _resolve_venv_bin("adk", "adk")
INFRA = {"INFRA_NETWORK", "AUTH_INVALID_KEY", "QUOTA_OR_RATE_LIMIT", "MODEL_NOT_FOUND"}

QUOTA_LOG_MARKERS = re.compile(
    r"RESOURCE_EXHAUSTED|429\s|quota exceeded|_ResourceExhaustedError|"
    r"503 UNAVAILABLE|UNAVAILABLE:|high demand", re.I)


def is_infra_failure(rec: dict) -> bool:
    """True when a test failed for an environment reason rather than an assertion."""
    return rec.get("failure_class") in INFRA or rec.get("_throttled", False)


def reclassify(results: list[dict], log_path: Path, offset: int = 0) -> list[dict]:
    """Turn server-side 429/503 into QUOTA_OR_RATE_LIMIT so they get retried, not blamed."""
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            text = fh.read()
    except OSError:
        return results
    if not QUOTA_LOG_MARKERS.search(text):
        return results
    for rec in results:
        if rec["passed"] or rec.get("failure_class") != "AGENT_RUNTIME_ERROR":
            continue
        if rec.get("tokens", 0) == 0:
            rec["failure_class"] = "QUOTA_OR_RATE_LIMIT"
            rec["_throttled"] = True
    return results


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, timeout: float = 5) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except Exception:
        return 0


# --------------------------------------------------------------------- scoring
def merge(results: list[dict], spec: dict, out_dir: Path) -> dict:
    """Combine results and re-score exactly as testing.py does."""
    results = sorted(results, key=lambda r: [t["id"] for t in spec["tests"]].index(r["test_id"])
                  if r["test_id"] in [t["id"] for t in spec["tests"]] else 999)
    total = len(results)
    passed = sum(r["passed"] for r in results)
    must = [r for r in results if r["severity"] == "must"]
    must_pass = sum(r["passed"] for r in must)
    infra = [r for r in results if not r["passed"] and is_infra_failure(r)]

    by_cat: dict[str, dict] = {}
    for r in results:
        c = by_cat.setdefault(r["category"], {"total": 0, "passed": 0})
        c["total"] += 1
        c["passed"] += int(r["passed"])

    req_cov: dict = {}
    for r in results:
        for rid in r["requirement_ids"]:
            c = req_cov.setdefault(rid, {"tests": 0, "passed": 0})
            c["tests"] += 1
            c["passed"] += int(r["passed"])
    for rq in spec.get("requirements", []):
        entry = req_cov.setdefault(rq["id"], {"tests": 0, "passed": 0})
        entry["text"] = rq.get("text", "")
        entry["severity"] = rq.get("severity", "must")
        entry["status"] = ("UNTESTED" if entry["tests"] == 0
                           else "MET" if entry["passed"] == entry["tests"] else "NOT_MET")

    lat = sorted(x for r in results for x in r["latency_s"] if x > 0)

    def pctl(p):
        return round(lat[min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1))))], 2) if lat else 0.0

    rate = passed / total if total else 0
    if total - passed > 0 and len(infra) == total - passed:
        verdict = "INFRA_BLOCKED"
    elif must_pass == len(must) and rate >= 0.9:
        verdict = "PASS"
    else:
        verdict = "NEEDS_FIX"

    fc: dict = {}
    for r in results:
        if r["failure_class"]:
            fc[r["failure_class"]] = fc.get(r["failure_class"], 0) + 1

    summary = {
        "verdict": verdict, "app": "apex_hyperstore", "tests_total": total, "tests_passed": passed,
        "pass_rate": round(rate, 3), "must_total": len(must), "must_passed": must_pass,
        "flaky": [r["test_id"] for r in results if r.get("flaky")], "by_category": by_cat,
        "requirements": req_cov,
        "latency": {"p50_s": pctl(50), "p95_s": pctl(95), "max_s": round(max(lat), 2) if lat else 0,
                    "mean_s": round(statistics.mean(lat), 2) if lat else 0},
        "tokens_total": sum(r["tokens"] for r in results),
        "avg_tool_calls": round(statistics.mean([len(r["tool_calls"]) for r in results]), 2)
        if results else 0,
        "failure_classes": fc, "output_dir": str(out_dir), "paced": True,
        "retried_tests": sum(1 for r in results if r.get("_retried")),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, default=str))

    L = ["# ADK test report - apex_hyperstore (paced run)", "",
         f"**Verdict: {verdict}**  | pass {passed}/{total} ({rate:.0%}) | MUST {must_pass}/{len(must)}",
         f"Latency p50 {summary['latency']['p50_s']}s, p95 {summary['latency']['p95_s']}s | "
         f"tokens {summary['tokens_total']} | avg tool calls {summary['avg_tool_calls']}",
         f"Tests re-run after an infrastructure failure: {summary['retried_tests']}", "",
         "_Run in paced slices with retry/backoff to stay inside the 5 requests/minute and "
         "20 requests/day free-tier limits; testing.py itself was not modified._", "",
         "## Requirements", "", "| id | status | passed/tests | text |", "|---|---|---|---|"]
    for rid, v in req_cov.items():
        L.append(f"| {rid} | {v.get('status','-')} | {v['passed']}/{v['tests']} | {v.get('text','')} |")
    L += ["", "## Categories", ""] + [f"- {k}: {v['passed']}/{v['total']}" for k, v in by_cat.items()]
    L += ["", "## Failures", ""]
    bad = [r for r in results if not r["passed"]]
    if not bad:
        L.append("None.")
    for r in bad:
        L += [f"### {r['test_id']} [{r['failure_class']}] ({r['severity']}, {r['category']})",
              f"- input: `{str(r['first_user_input'])[:200]}`",
              f"- tools called: {r['tool_calls']}  agents: {r['agents']}",
              f"- response: {r['final_response'][:300]!r}"]
        for f in r["failed_checks"]:
            L.append(f"- FAILED `{f['check']}` {f['detail'][:200]}")
        L.append("")
    (out_dir / "report.md").write_text("\n".join(L))
    return summary


class ServerHandle:
    """Owns the `adk api_server` lifecycle so the model can be swapped between slices."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.proc = None
        self.base = ""
        self.model = None

    @staticmethod
    def set_model(model: str) -> None:
        env_file = HERE / ".env"
        existing = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
        lines = [l for l in existing if not l.startswith("APEX_MODEL=")]
        lines.append(f"APEX_MODEL={model}")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def start(self, model: str, log) -> bool:
        self.stop()
        self.set_model(model)
        port = free_port()
        self.base = f"http://127.0.0.1:{port}"
        srv_log = open(self.out_dir / "api_server.log", "a", encoding="utf-8")
        srv_log.write(f"\n=== starting api_server model={model} port={port} ===\n")
        srv_log.flush()
        self.proc = subprocess.Popen(
            [str(ADK), "api_server", "--port", str(port),
             "--session_service_uri",
             f"sqlite+aiosqlite:///{(self.out_dir / 'sessions.db').as_posix()}", str(HERE)],
            cwd=str(HERE), stdout=srv_log, stderr=subprocess.STDOUT)
        deadline = time.time() + 120
        while time.time() < deadline and get(self.base + "/health") != 200:
            if self.proc.poll() is not None:
                srv_log.close()
                log.write(f"server exited early for {model}\n")
                return False
            time.sleep(1)
        srv_log.close()
        healthy = get(self.base + "/health") == 200
        if healthy:
            self.model = model
        return healthy

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


# ---------------------------------------------------------------------- runner
def run_slice(group: list[dict], spec: dict, base: str, out_dir: Path, label: str,
              log) -> list[dict]:
    """Hand one slice to testing.py and return its per-test results."""
    sub = {"_comment": f"{label} of the paced run", "requirements": spec["requirements"],
           "tests": group}
    sub_path = out_dir / f"slice_{label}.json"
    sub_path.write_text(json.dumps(sub, indent=2), encoding="utf-8")
    sub_out = out_dir / f"slice_{label}"
    proc = subprocess.run(
        [str(PYTHON), str(TESTING), "--workspace", str(HERE), "--app", "apex_hyperstore",
         "--base-url", base, "--spec", str(sub_path), "--out", str(sub_out)],
        cwd=str(HERE), capture_output=True, text=True)
    log.write(proc.stdout or "")
    log.write(proc.stderr or "")
    log.flush()
    rj = sub_out / "results.json"
    if not rj.exists():
        print(f"[pace]   {label}: no results.json (testing.py exited {proc.returncode})", flush=True)
        return []
    return json.loads(rj.read_text(encoding="utf-8"))["results"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="adk_runs/spec.json")
    ap.add_argument("--out", default="adk_runs/run3")
    ap.add_argument("--chunk", type=int, default=3, help="tests per slice")
    ap.add_argument("--pause", type=int, default=75, help="seconds between clean slices")
    ap.add_argument("--max-pause", type=int, default=300, help="ceiling for the backoff")
    ap.add_argument("--max-retries", type=int, default=2, help="retries per throttled test")
    ap.add_argument("--base-pause", type=int, default=60, help="floor the backoff shrinks to")
    ap.add_argument("--daily-quota-limit", type=int, default=20,
                    help="max live messages per model per day (default: 20 for free tier)")
    ap.add_argument("--model", default=None, help="write APEX_MODEL to .env before running")
    ap.add_argument("--rotate", default=None,
                    help="comma-separated models to rotate between slices; each has its own "
                         "daily free-tier bucket, so rotation multiplies the budget")
    a = ap.parse_args()

    spec = json.loads((HERE / a.spec).read_text(encoding="utf-8"))
    tests = spec["tests"]
    by_id = {t["id"]: t for t in tests}
    out_dir = (HERE / a.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    models = [m.strip() for m in a.rotate.split(",") if m.strip()] if a.rotate else []
    if a.model:
        models = [a.model] + [m for m in models if m != a.model]
    if not models:
        env_path = HERE / ".env"
        env_line = next((l for l in (env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else [])
                         if l.startswith("APEX_MODEL=")), "")
        models = [env_line.split("=", 1)[1]] if "=" in env_line else ["gemini-2.5-flash"]

    log = open(out_dir / "server.log", "w")
    log.write("=== paced runner driver log ===\n")
    groups = [tests[i:i + a.chunk] for i in range(0, len(tests), a.chunk)]
    print(f"[pace] {len(tests)} tests in {len(groups)} slices | chunk {a.chunk} | "
          f"base pause {a.pause}s (max {a.max_pause}) | retries {a.max_retries} | "
          f"daily-quota-limit {a.daily_quota_limit}", flush=True)
    print(f"[pace] rotating models: {', '.join(models)}", flush=True)

    server = ServerHandle(out_dir)
    results: dict[str, dict] = {}
    attempts: dict[str, int] = {}
    model_calls: dict[str, int] = {m: 0 for m in models}
    pause = a.pause

    try:
        for i, group in enumerate(groups, 1):
            label = f"{i:02d}"
            available_models = [m for m in models if model_calls.get(m, 0) + len(group) <= a.daily_quota_limit]
            if not available_models:
                print(f"[pace] daily quota limit ({a.daily_quota_limit} messages/model) reached across {models}; stopping safely", flush=True)
                break
            model = available_models[(i - 1) % len(available_models)]
            ids = [t["id"] for t in group]
            if server.model != model:
                print(f"\n[pace] starting server on {model}", flush=True)
                if not server.start(model, log):
                    print(f"[pace] server would not start on {model}; stopping", flush=True)
                    break
            print(f"\n[pace] slice {label} [{model}]: {', '.join(ids)}", flush=True)
            srv_log = out_dir / "api_server.log"
            before = srv_log.stat().st_size if srv_log.exists() else 0
            slice_results = reclassify(
                run_slice(group, spec, server.base, out_dir, label, log),
                srv_log, before)
            model_calls[model] = model_calls.get(model, 0) + sum(len(t.get("turns", [1])) for t in group)
            for rec in slice_results:
                attempts.setdefault(rec["test_id"], 1)
                rec["_model"] = model
                results[rec["test_id"]] = rec
                print(f"[pace]   {rec['test_id']:<28} "
                      f"{'PASS' if rec['passed'] else 'FAIL'} "
                      f"{'' if rec['passed'] else '[' + str(rec['failure_class']) + ']'}",
                      flush=True)

            throttled = [tid for tid in ids
                         if tid in results and not results[tid]["passed"]
                         and is_infra_failure(results[tid])]
            if throttled:
                pause = min(int(pause * 1.6), a.max_pause)
                for tid in throttled:
                    if attempts.get(tid, 1) > a.max_retries:
                        continue
                    alt = models[(models.index(model) + 1) % len(models)] if len(models) > 1 else model
                    if model_calls.get(alt, 0) >= a.daily_quota_limit:
                        continue
                    print(f"[pace] throttled: {tid} -> retry on {alt} in {pause}s "
                          f"(attempt {attempts.get(tid, 1) + 1}/{a.max_retries + 1})", flush=True)
                    time.sleep(pause)
                    if alt != model:
                        if not server.start(alt, log):
                            print(f"[pace] retry server would not start on {alt}", flush=True)
                            break
                    for rec in run_slice([by_id[tid]], spec, server.base, out_dir,
                                         f"r{i:02d}_{tid[:14]}", log):
                        reclassify([rec], out_dir / "api_server.log")
                        rec["_retried"] = True
                        rec["_model"] = alt
                        attempts[rec["test_id"]] = attempts.get(rec["test_id"], 1) + 1
                        model_calls[alt] = model_calls.get(alt, 0) + 1
                        prev = results.get(rec["test_id"], {})
                        results[rec["test_id"]] = rec if rec["passed"] else (
                            rec if not prev.get("passed") else prev)
                        print(f"[pace]   {rec['test_id']:<28} "
                              f"{'PASS' if rec['passed'] else 'FAIL'} (retry on {alt})", flush=True)
            else:
                pause = max(a.base_pause, int(pause * 0.8))

            (out_dir / "partial_results.json").write_text(json.dumps(
                {"completed": len(results), "expected": len(tests),
                 "results": [results[t["id"]] for t in tests if t["id"] in results]},
                indent=2, default=str), encoding="utf-8")

            if i < len(groups):
                print(f"[pace] pausing {pause}s", flush=True)
                time.sleep(pause)
    finally:
        server.stop()
        log.close()

    final = [results[t["id"]] for t in tests if t["id"] in results]
    summary = merge(final, spec, out_dir)
    used: dict = {}
    for r in final:
        used[r.get("_model", "?")] = used.get(r.get("_model", "?"), 0) + 1
    print("\n" + "=" * 72)
    print(f"MERGED VERDICT {summary['verdict']}: {summary['tests_passed']}/{summary['tests_total']}"
          f" passed, MUST {summary['must_passed']}/{summary['must_total']}")
    print(f"latency p50 {summary['latency']['p50_s']}s p95 {summary['latency']['p95_s']}s | "
          f"tokens {summary['tokens_total']} | retried {summary['retried_tests']}")
    print(f"models used: {used}")
    print(f"failure classes: {summary['failure_classes']}")
    print(f"report -> {out_dir / 'report.md'}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
