#!/usr/bin/env python3
"""dashboard.py - turn a testing.py results.json into a single self-contained HTML report.

``testing.py`` writes machine-readable results; this script renders them into
one HTML file a human can actually read: verdict, pass rates, latency, token
use, per-requirement coverage, every failure with its hint, and the per-test
table. No external assets, no CDN, no browser APIs - "open the file" is the
whole requirement, and it works offline and in sandboxed viewers.

It also accepts an optional evaluation markdown file (the qualitative scores an
agent writes in Step 5 of SKILL.md) and embeds it as a section, so the numbers
and the judgment live in one place.

Usage
    python dashboard.py --results ws/adk_runs/20260101-120000/results.json
    python dashboard.py --results results.json --evaluation ws/adk_runs/evaluation.md --out report.html
Exit codes: 0 report written, 2 usage/input error.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

CSS = """
:root{--bg:#0f1419;--card:#1a2029;--ink:#e8eef5;--muted:#93a1b0;--ok:#37c77f;--bad:#f0546d;--warn:#e9b949;--line:#2a3441}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 10px;color:#cdd9e5}
.sub{color:var(--muted);margin-bottom:18px}
.verdict{display:inline-block;padding:6px 16px;border-radius:8px;font-weight:700;letter-spacing:.4px}
.verdict.PASS{background:rgba(55,199,127,.15);color:var(--ok);border:1px solid var(--ok)}
.verdict.NEEDS_FIX{background:rgba(240,84,109,.12);color:var(--bad);border:1px solid var(--bad)}
.verdict.INFRA_BLOCKED{background:rgba(233,185,73,.12);color:var(--warn);border:1px solid var(--warn)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.card .v{font-size:22px;font-weight:700;margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
tr:last-child td{border-bottom:none}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}.warn{color:var(--warn);font-weight:600}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;border:1px solid var(--line)}
.fail{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--bad);border-radius:8px;padding:14px;margin:10px 0}
.fail code{background:#0b0f14;padding:1px 6px;border-radius:5px;font-size:13px}
.hint{color:var(--muted);font-size:13px;margin:6px 0 0}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;overflow:auto;white-space:pre-wrap}
.muted{color:var(--muted)}
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def fmt_seconds(v) -> str:
    try:
        return f"{float(v):.1f}s"
    except (TypeError, ValueError):
        return "-"


def card(key: str, value) -> str:
    return f'<div class="card"><div class="k">{esc(key)}</div><div class="v">{esc(value)}</div></div>'


def status_pill(ok: bool, text_ok="PASS", text_bad="FAIL") -> str:
    cls = "ok" if ok else "bad"
    return f'<span class="{cls}">{text_ok if ok else text_bad}</span>'


def render(results: dict, evaluation_md: str | None, title: str) -> str:
    summary = results.get("summary") or {}
    tests = results.get("results") or []
    verdict = summary.get("verdict", "UNKNOWN")
    latency = summary.get("latency") or {}

    parts: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>",
        f"<style>{CSS}</style></head><body><div class='wrap'>",
        f"<h1>{esc(title)}</h1>",
        f"<div class='sub'>ADK test results - app <b>{esc(summary.get('app', '?'))}</b></div>",
        f"<div class='verdict {esc(verdict)}'>{esc(verdict)}</div>",
        "<div class='cards'>",
        card("Pass rate", f"{summary.get('tests_passed', 0)}/{summary.get('tests_total', 0)} "
                          f"({(summary.get('pass_rate') or 0) * 100:.0f}%)"),
        card("MUST tests", f"{summary.get('must_passed', 0)}/{summary.get('must_total', 0)}"),
        card("Latency p50", fmt_seconds(latency.get("p50_s"))),
        card("Latency p95", fmt_seconds(latency.get("p95_s"))),
        card("Tokens", summary.get("tokens_total", 0)),
        card("Avg tool calls", summary.get("avg_tool_calls", 0)),
        "</div>",
    ]

    flags = []
    if summary.get("flaky"):
        flags.append(f"<span class='pill warn'>flaky: {esc(', '.join(summary['flaky']))}</span>")
    if summary.get("retried"):
        flags.append(f"<span class='pill'>retried (infra): {esc(', '.join(summary['retried']))}</span>")
    if summary.get("quota_reclassified"):
        flags.append(f"<span class='pill warn'>quota-reclassified: {esc(', '.join(summary['quota_reclassified']))}</span>")
    if flags:
        parts.append("<p>" + " ".join(flags) + "</p>")

    requirements = summary.get("requirements") or {}
    if requirements:
        parts.append("<h2>Requirements</h2><table><tr><th>id</th><th>status</th><th>passed/tests</th><th>text</th></tr>")
        for rid, v in requirements.items():
            status = v.get("status", "-")
            cls = {"MET": "ok", "NOT_MET": "bad", "UNTESTED": "warn"}.get(status, "muted")
            parts.append(f"<tr><td>{esc(rid)}</td><td class='{cls}'>{esc(status)}</td>"
                         f"<td>{v.get('passed', 0)}/{v.get('tests', 0)}</td><td>{esc(v.get('text', ''))}</td></tr>")
        parts.append("</table>")

    categories = summary.get("by_category") or {}
    if categories:
        parts.append("<h2>Categories</h2><table><tr><th>category</th><th>passed</th></tr>")
        for name, v in categories.items():
            ok = v.get("passed", 0) == v.get("total", 0)
            parts.append(f"<tr><td>{esc(name)}</td><td>{status_pill(ok)} {v.get('passed', 0)}/{v.get('total', 0)}</td></tr>")
        parts.append("</table>")

    failures = [t for t in tests if not t.get("passed")]
    if failures:
        parts.append("<h2>Failures</h2>")
        for t in failures:
            parts.append(f"<div class='fail'><b>{esc(t.get('test_id'))}</b> "
                         f"<span class='pill'>{esc(t.get('failure_class') or 'FAILED')}</span> "
                         f"<span class='muted'>{esc(t.get('severity', ''))} / {esc(t.get('category', ''))}</span>")
            parts.append(f"<div class='muted'>input: <code>{esc(str(t.get('first_user_input', ''))[:300])}</code></div>")
            parts.append(f"<div class='muted'>tools: {esc(t.get('tool_calls', []))} - agents: {esc(t.get('agents', []))}</div>")
            parts.append(f"<div>response: <code>{esc(str(t.get('final_response', ''))[:400])}</code></div>")
            for fc in t.get("failed_checks", []):
                parts.append(f"<div class='hint'>- FAILED <code>{esc(fc.get('check'))}</code> {esc(fc.get('detail', ''))[:300]}</div>")
                if fc.get("hint"):
                    parts.append(f"<div class='hint'>hint: {esc(fc['hint'])}</div>")
            parts.append("</div>")

    if tests:
        parts.append("<h2>All tests</h2><table><tr><th>test</th><th>result</th><th>category</th><th>latency</th>"
                     "<th>tokens</th><th>tools</th><th>retries</th></tr>")
        for t in tests:
            lat = ", ".join(fmt_seconds(x) for x in t.get("latency_s", []))
            parts.append(f"<tr><td>{esc(t.get('test_id'))}</td><td>{status_pill(bool(t.get('passed')))}</td>"
                         f"<td>{esc(t.get('category', ''))}</td><td>{esc(lat)}</td><td>{t.get('tokens', 0)}</td>"
                         f"<td>{t.get('tool_calls', [])}</td><td>{t.get('retries', 0)}</td></tr>")
        parts.append("</table>")

    if evaluation_md is not None:
        parts.append("<h2>Qualitative evaluation (evaluation.md)</h2><pre>" + esc(evaluation_md) + "</pre>")

    parts.append("<p class='muted' style='margin-top:40px'>Generated by dashboard.py from testing.py results.json</p>")
    parts.append("</div></body></html>")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("Usage")[0].strip())
    ap.add_argument("--results", required=True, help="Path to results.json written by testing.py")
    ap.add_argument("--evaluation", default=None, help="Optional evaluation.md to embed as a section")
    ap.add_argument("--out", default=None, help="Output HTML path (default: dashboard.html next to results.json)")
    ap.add_argument("--title", default=None, help="Report title (default: 'ADK test dashboard - <app>')")
    args = ap.parse_args(argv)

    results_path = Path(args.results).resolve()
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read results.json: {e}")
        return 2
    if not isinstance(results, dict) or "summary" not in results:
        print("results.json does not look like testing.py output (no 'summary' key)")
        return 2

    evaluation_md = None
    eval_path = Path(args.evaluation).resolve() if args.evaluation else results_path.parent.parent / "evaluation.md"
    if eval_path.exists():
        evaluation_md = eval_path.read_text(encoding="utf-8", errors="replace")

    title = args.title or f"ADK test dashboard - {results['summary'].get('app', results_path.stem)}"
    out_path = Path(args.out).resolve() if args.out else results_path.parent / "dashboard.html"
    out_path.write_text(render(results, evaluation_md, title), encoding="utf-8")
    print(f"[dashboard] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
