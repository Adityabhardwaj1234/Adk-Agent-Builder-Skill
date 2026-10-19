"""Self-contained HTML Dashboard Renderer for both `testing.py` (`results.json`) and `EvalReport` JSON files."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DASHBOARD_CSS = """
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


def _esc(val: Any) -> str:
    return html.escape(str(val), quote=True)


class DashboardRenderer:
    """Renders standalone dark-mode HTML reports with zero external CDN dependencies."""

    @staticmethod
    def render_from_file(
        input_json_path: Path,
        output_html_path: Optional[Path] = None,
        *,
        evaluation_md_path: Optional[Path] = None,
    ) -> Path:
        data = json.loads(input_json_path.read_text(encoding="utf-8"))
        eval_md = (
            evaluation_md_path.read_text(encoding="utf-8")
            if evaluation_md_path and evaluation_md_path.exists()
            else None
        )
        out_path = output_html_path or input_json_path.with_name("dashboard.html")
        html_str = DashboardRenderer.render_html(data, evaluation_md=eval_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_str, encoding="utf-8")
        return out_path

    @staticmethod
    def render_html(data: Dict[str, Any], *, evaluation_md: Optional[str] = None) -> str:
        # Detect whether input is Variant 1 (`summary` + `results`) or Variant 2 (`EvalReport` / `case_results`)
        if "summary" in data and "results" in data:
            return DashboardRenderer._render_http_results(data, evaluation_md)
        if "case_results" in data and "eval_set_id" in data:
            return DashboardRenderer._render_eval_report(data, evaluation_md)
        raise ValueError("Unsupported results JSON structure: expected ('summary','results') or ('eval_set_id','case_results').")

    @staticmethod
    def _render_http_results(data: Dict[str, Any], evaluation_md: Optional[str] = None) -> str:
        s = data["summary"]
        results: List[Dict[str, Any]] = data.get("results", [])
        verdict = str(s.get("verdict", "NEEDS_FIX"))
        app = str(s.get("app", "adk_agent"))
        lat = s.get("latency", {})

        req_rows = []
        for rid, rv in (s.get("requirements") or {}).items():
            st = rv.get("status", "UNTESTED")
            cls = "ok" if st == "MET" else ("warn" if st == "UNTESTED" else "bad")
            req_rows.append(
                f"<tr><td><code>{_esc(rid)}</code></td>"
                f"<td><span class='pill'>{_esc(rv.get('severity', 'must'))}</span></td>"
                f"<td class='{cls}'>{_esc(st)}</td>"
                f"<td>{_esc(rv.get('passed', 0))}/{_esc(rv.get('tests', 0))}</td>"
                f"<td>{_esc(rv.get('text', ''))}</td></tr>"
            )
        req_html = (
            "<table><thead><tr><th>ID</th><th>Severity</th><th>Status</th><th>Tests</th><th>Requirement</th></tr></thead>"
            f"<tbody>{''.join(req_rows)}</tbody></table>"
            if req_rows
            else "<p class='muted'>No requirements recorded.</p>"
        )

        failures = [r for r in results if not r.get("passed")]
        fail_cards = []
        for r in failures:
            checks = "".join(
                f"<li><code>{_esc(fc.get('check'))}</code> — {_esc(fc.get('detail'))}</li>"
                for fc in r.get("failed_checks", [])
            )
            hint = f"<div class='hint'>Hint: {_esc(r.get('hint', ''))}</div>" if r.get("hint") else ""
            fail_cards.append(
                f"<div class='fail'><div><strong>{_esc(r.get('test_id'))}</strong> "
                f"<span class='pill'>{_esc(r.get('failure_class', 'FAIL'))}</span></div>"
                f"<ul>{checks}</ul>{hint}</div>"
            )
        fail_html = "".join(fail_cards) if fail_cards else "<p class='ok'>All tests passed.</p>"

        test_rows = []
        for r in results:
            cls = "ok" if r.get("passed") else "bad"
            status_lbl = "PASS" if r.get("passed") else (r.get("failure_class") or "FAIL")
            test_rows.append(
                f"<tr><td><code>{_esc(r.get('test_id'))}</code></td>"
                f"<td>{_esc(r.get('category', ''))}</td>"
                f"<td>{_esc(r.get('severity', ''))}</td>"
                f"<td class='{cls}'>{_esc(status_lbl)}</td>"
                f"<td>{_esc(', '.join(r.get('tool_calls', [])) or '—')}</td>"
                f"<td>{_esc(', '.join(r.get('agents', [])) or '—')}</td>"
                f"<td>{_esc(r.get('tokens', 0))}</td></tr>"
            )
        eval_section = f"<h2>Qualitative Evaluation</h2><pre>{_esc(evaluation_md)}</pre>" if evaluation_md else ""

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ADK Test Report — {_esc(app)}</title>
<style>{DASHBOARD_CSS}</style></head>
<body><div class="wrap">
<h1>ADK Agent Evaluation Dashboard — {_esc(app)}</h1>
<div class="sub">Self-contained engineering report</div>
<span class="verdict {_esc(verdict)}">{_esc(verdict)}</span>
<div class="cards">
  <div class="card"><div class="k">Tests Passed</div><div class="v">{_esc(s.get('tests_passed', 0))}/{_esc(s.get('tests_total', 0))}</div></div>
  <div class="card"><div class="k">MUST Passed</div><div class="v">{_esc(s.get('must_passed', 0))}/{_esc(s.get('must_total', 0))}</div></div>
  <div class="card"><div class="k">Latency p50 / p95</div><div class="v">{_esc(lat.get('p50_s', 0))}s / {_esc(lat.get('p95_s', 0))}s</div></div>
  <div class="card"><div class="k">Total Tokens</div><div class="v">{_esc(s.get('tokens_total', 0))}</div></div>
</div>
<h2>Requirements Coverage</h2>
{req_html}
<h2>Failures &amp; Diagnostics</h2>
{fail_html}
<h2>All Test Cases</h2>
<table><thead><tr><th>Test</th><th>Category</th><th>Severity</th><th>Outcome</th><th>Tools</th><th>Agents</th><th>Tokens</th></tr></thead>
<tbody>{''.join(test_rows)}</tbody></table>
{eval_section}
</div></body></html>"""

    @staticmethod
    def _render_eval_report(data: Dict[str, Any], evaluation_md: Optional[str] = None) -> str:
        verdict = "PASS" if data.get("overall_passed") else "NEEDS_FIX"
        eval_id = str(data.get("eval_set_id", "default_eval"))
        scores = data.get("aggregate_scores", {})
        eff = data.get("aggregate_efficiency", {})
        cases = data.get("case_results", [])

        score_cards = "".join(
            f"<div class='card'><div class='k'>{_esc(k)}</div><div class='v'>{_esc(v)}</div></div>"
            for k, v in scores.items()
        )
        rows = []
        for c in cases:
            st = c.get("status", "failed")
            cls = "ok" if st == "passed" else ("warn" if st == "skipped" else "bad")
            sc_str = ", ".join(f"{k}={v}" for k, v in (c.get("scores") or {}).items())
            reasons = "; ".join(c.get("failure_reasons") or []) or "—"
            rows.append(
                f"<tr><td><code>{_esc(c.get('eval_id'))}</code></td>"
                f"<td class='{cls}'>{_esc(st.upper())}</td>"
                f"<td>{_esc(sc_str)}</td>"
                f"<td>{_esc(reasons)}</td></tr>"
            )
        eval_section = f"<h2>Qualitative Notes</h2><pre>{_esc(evaluation_md)}</pre>" if evaluation_md else ""
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ADK EvalSet Report — {_esc(eval_id)}</title>
<style>{DASHBOARD_CSS}</style></head>
<body><div class="wrap">
<h1>ADK Evaluation Report — {_esc(eval_id)}</h1>
<div class="sub">Mode: {_esc(data.get('execution_mode', 'deterministic_mock'))} | Version: {_esc(data.get('agent_version', '0.1.0'))}</div>
<span class="verdict {verdict}">{verdict}</span>
<div class="cards">
  <div class="card"><div class="k">Cases Passed</div><div class="v">{_esc(data.get('passed_cases', 0))}/{_esc(data.get('total_cases', 0))}</div></div>
  <div class="card"><div class="k">Avg Tool Calls</div><div class="v">{_esc(eff.get('tool_call_count_v1', 0))}</div></div>
  <div class="card"><div class="k">Avg Tokens</div><div class="v">{_esc(eff.get('token_usage_v1', 0))}</div></div>
  {score_cards}
</div>
<h2>Evaluation Cases</h2>
<table><thead><tr><th>Case ID</th><th>Status</th><th>Criteria Scores</th><th>Notes / Failures</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
{eval_section}
</div></body></html>"""
