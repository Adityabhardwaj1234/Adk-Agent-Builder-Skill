#!/usr/bin/env python3
"""build_ops_dashboard.py - the support team's queue view, as one self-contained HTML file.

Reads the live SQLite database and renders every service request the chatbot has filed, with
SLA state computed against the wall clock, filters, search, and a separate emergency panel.

No decryption happens here: the database stores contact details as plain text (see the
security note rendered into the page). Regenerate after the agent has run more conversations:

    .venv\\Scripts\\python.exe build_ops_dashboard.py
    .venv\\Scripts\\python.exe build_ops_dashboard.py --hide-synthetic
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from apex_hyperstore import schemas  # noqa: E402
from apex_hyperstore.company_profile import SLA, SUPPORT_TEAMS  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
SLA_MINUTES = dict(schemas.URGENCY_SLA_MINUTES)
TEAMS = {v["team"] for v in SUPPORT_TEAMS}
TEAMS |= {"Standard Support Queue", "Customer Experience Desk"}

# Rows created by offline_eval.py and by repeated test runs, not by a real conversation.
SYNTHETIC_EMAILS = {"a@b.co", "probe@example.com", "reject@example.com"}
SYNTHETIC_NAMES = {"A B", "Test User"}


def is_synthetic(r: dict) -> bool:
    email = (r.get("email") or "").lower()
    name = (r.get("full_name") or "").strip()
    if email in SYNTHETIC_EMAILS:
        return True
    if name in SYNTHETIC_NAMES or name.startswith("Test User"):
        return True
    return bool(email) and email.startswith("t") and email[1:2].isdigit() and email.endswith("@example.com")


def load_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM service_requests ORDER BY created_at DESC")]
    returns = [dict(r) for r in conn.execute(
        "SELECT * FROM returns ORDER BY created_at DESC")]
    orders = [dict(r) for r in conn.execute(
        "SELECT order_id, customer_name, status, placed_at, total_inr FROM orders "
        "ORDER BY placed_at DESC")]
    conn.close()
    now = datetime.now(IST)

    for r in rows:
        created = schemas.parse_ts(r["created_at"])
        target = schemas.parse_ts(r["target_response_at"])
        due_in = (target - now).total_seconds() / 60
        r["age_min"] = round((now - created).total_seconds() / 60)
        r["due_in_min"] = round(due_in)
        r["sla_min"] = SLA_MINUTES.get(r["urgency"], 1440)
        if r["request_status"] != "open":
            r["sla_state"] = "closed"
        elif due_in < 0:
            r["sla_state"] = "breached"
        elif due_in <= 30:
            r["sla_state"] = "due"
        else:
            r["sla_state"] = "ok"
        r["synthetic"] = is_synthetic(r)
        r["created_h"] = created.strftime("%Y-%m-%d %H:%M")
        r["target_h"] = target.strftime("%Y-%m-%d %H:%M")
        r["summary"] = (r["issue_summary"] or "")[:200]
        r.pop("issue_summary", None)
        r.pop("created_at", None)
        r.pop("target_response_at", None)
    for r in returns:
        r["created_h"] = schemas.parse_ts(r["created_at"]).strftime("%Y-%m-%d %H:%M")
    return rows, returns, orders


def human(mins: int) -> str:
    sign = "-" if mins < 0 else ""
    mins = abs(mins)
    if mins < 60:
        return f"{sign}{mins}m"
    if mins < 1440:
        return f"{sign}{mins // 60}h {mins % 60:02d}m"
    return f"{sign}{mins // 1440}d {(mins % 1440) // 60}h"


def pill(state: str, text: str) -> str:
    """Server-side twin of the pill() helper in the page's JavaScript."""
    cls = {"breached": "bad", "due": "warn", "ok": "good", "closed": "info"}.get(state, "muted")
    return f'<span class="pill {cls}">{text}</span>'


CSS = """
:root{--bg:#0e1116;--panel:#161b22;--line:#2a323d;--text:#e6edf3;--muted:#8b949e;
--good:#3fb950;--bad:#f85149;--warn:#d29922;--accent:#58a6ff;--purple:#bc8cff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
 font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1680px;margin:0 auto;padding:24px 20px 60px}
h1{margin:0 0 4px;font-size:24px;letter-spacing:-.02em}
h2{margin:28px 0 10px;font-size:17px;border-bottom:1px solid var(--line);padding-bottom:7px}
.sub{color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px;cursor:pointer}
.card:hover{border-color:var(--accent)}
.card.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.card .v{font-size:26px;font-weight:700;margin-top:2px}
.card .n{font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:#1c222b;color:var(--muted);font-weight:600;
 text-transform:uppercase;font-size:10.5px;letter-spacing:.06em;padding:8px;text-align:left;
 border:1px solid var(--line);white-space:nowrap;z-index:2}
td{padding:7px 8px;border:1px solid var(--line);vertical-align:top}
tbody tr:nth-child(even){background:#11161d}
tbody tr:hover{background:#1a212a}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:10.5px;font-weight:700;
 border:1px solid var(--line);white-space:nowrap}
.good{background:rgba(63,185,80,.15);color:var(--good);border-color:rgba(63,185,80,.4)}
.bad{background:rgba(248,81,73,.15);color:var(--bad);border-color:rgba(248,81,73,.4)}
.warn{background:rgba(210,153,34,.15);color:var(--warn);border-color:rgba(210,153,34,.4)}
.info{background:rgba(88,166,255,.15);color:var(--accent);border-color:rgba(88,166,255,.4)}
.purple{background:rgba(188,140,255,.15);color:var(--purple);border-color:rgba(188,140,255,.4)}
.muted{color:var(--muted)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.bar{position:sticky;top:0;background:#11161d;border:1px solid var(--line);border-radius:9px;
 padding:11px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:5;margin-bottom:12px}
input[type=search],select{background:#0b0f14;border:1px solid var(--line);color:var(--text);
 padding:7px 10px;border-radius:6px;font-size:13px}
input[type=search]{min-width:270px;flex:1}
button{background:#1c222b;border:1px solid var(--line);color:var(--text);padding:7px 12px;
 border-radius:6px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--accent)}
.note{background:var(--panel);border-left:3px solid var(--warn);padding:11px 15px;margin:14px 0;
 border-radius:0 8px 8px 0;font-size:13px}
.emg{border:1px solid rgba(248,81,73,.45);border-radius:9px;overflow:hidden;margin-bottom:16px}
.emg .hd{background:rgba(248,81,73,.1);padding:9px 14px;font-weight:700;font-size:13px}
.scroll{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:9px}
.tag{font-size:11px;padding:1px 7px;border-radius:4px;background:#1c222b;border:1px solid var(--line);
 color:var(--muted)}
a{color:var(--accent)}
@media print{.bar,.cards{display:none}body{background:#fff;color:#000}}
"""

JS = """
const ROWS = __ROWS__;
const TYPES = [...new Set(ROWS.map(r=>r.request_type))].sort();
const TEAMS = [...new Set(ROWS.map(r=>r.assigned_team))].sort();
let filter = {state:null, synthetic:false, team:'', type:'', q:''};

const sel = ['sla_state','urgency','request_type','assigned_team']
  .map(k=>`<select id=f_${k}><option value="">all ${k.replace('_',' ')}</option>` +
    [...new Set(ROWS.map(r=>r[k]))].sort().map(v=>
      `<option value="${v}">${v}</option>`).join('') + `</select>`).join('');

function pill(s, t){ const c = {'breached':'bad','due':'warn','ok':'good','closed':'info'}[s]||'muted';
  return `<span class="pill ${c}">${t}</span>`; }

function row(r){
  const urg = r.urgency==='emergency'
    ? `<span class="pill bad">EMERGENCY</span>` : `<span class="pill ${r.urgency==='high'?'warn':'info'}">${r.urgency}</span>`;
  const sla = pill(r.sla_state, r.sla_state==='ok'?`due in ${human(r.due_in_min)}`
    : r.sla_state==='due'?`due ${human(r.due_in_min)}`
    : r.sla_state==='breached'?`BREACHED ${human(r.due_in_min)}`:r.request_status);
  return `<tr>
    <td class="mono">${r.reference_id}${r.synthetic?' <span class="tag">test</span>':''}</td>
    <td>${urg}<br><span class="muted" style="font-size:11px">${r.emergency_type}</span></td>
    <td>${r.request_type}<br><span class="muted" style="font-size:11px">${r.scheduled_for}</span></td>
    <td><b>${r.full_name}</b><br><span class="mono muted">${r.email}</span><br>
        <span class="mono muted">${r.phone}</span></td>
    <td class="mono">${r.order_id||'-'}</td>
    <td style="max-width:290px">${r.summary}</td>
    <td>${r.assigned_team}<br><span class="muted" style="font-size:11px">${r.channel}</span></td>
    <td>${sla}<br><span class="muted" style="font-size:11px">opened ${r.created_h}</span></td>
  </tr>`;
}

function human(m){
  const sign = m<0?'-':''; m=Math.abs(m);
  if(m<60) return sign+m+'m';
  if(m<1440) return sign+Math.floor(m/60)+'h '+String(m%60).padStart(2,'0')+'m';
  return sign+Math.floor(m/1440)+'d '+Math.floor((m%1440)/60)+'h';
}

function apply(){
  const q = filter.q.toLowerCase();
  const rows = ROWS.filter(r=>
    (!filter.state || r.sla_state===filter.state) &&
    (!filter.team || r.assigned_team===filter.team) &&
    (!filter.type || r.request_type===filter.type) &&
    (document.getElementById('hide_syn').checked ? !r.synthetic : true) &&
    (!q || (r.reference_id+' '+r.full_name+' '+r.email+' '+r.phone+' '+r.request_type+' '+
            r.assigned_team+' '+r.order_id+' '+r.summary).toLowerCase().includes(q)));
  document.getElementById('cnt').textContent = rows.length;
  document.getElementById('body').innerHTML = rows.map(row).join('') ||
    `<tr><td colspan="8" class="muted">No requests match this filter.</td></tr>`;
  document.querySelectorAll('.card').forEach(c=>
    c.classList.toggle('sel', c.dataset.f === (filter.state||'')));
}

document.getElementById('filters').innerHTML = sel;
for (const k of ['sla_state','urgency','request_type','assigned_team'])
  document.getElementById('f_'+k).addEventListener('change', e=>{filter[k]=e.target.value; apply();});
document.getElementById('q').addEventListener('input', e=>{filter.q=e.target.value; apply();});
document.getElementById('hide_syn').addEventListener('change', apply);
document.querySelectorAll('.card').forEach(c=>c.addEventListener('click',()=>{
  filter.state = (filter.state===c.dataset.f) ? null : c.dataset.f; apply();}));
apply();
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/apex_hyperstore.db")
    ap.add_argument("--out", default="apex_ops_dashboard.html")
    ap.add_argument("--hide-synthetic", action="store_true",
                    help="tick the box in the page by default")
    a = ap.parse_args()

    rows, returns, orders = load_rows(Path(a.db))
    real = [r for r in rows if not r["synthetic"]]
    emg = [r for r in real if r["urgency"] == "emergency"]
    breached = [r for r in real if r["sla_state"] == "breached"]
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    def card(k, v, note, f=None):
        d = f' data-f="{f}"' if f else ""
        return (f'<div class="card"{d}><div class="k">{k}</div><div class="v">{v}</div>'
                f'<div class="n">{note}</div></div>')

    cards = "".join([
        card("Open requests", len(real), f"{len(rows) - len(real)} synthetic excluded", "open"),
        card("Emergency", len(emg), "15-minute SLA", "emergency"),
        card("Breached SLA", len(breached), "past target response", "breached"),
        card("Due now", len([r for r in real if r["sla_state"] == "due"]), "within 30 min", "due"),
        card("High priority", len([r for r in real if r["urgency"] == "high"]), "2-hour SLA"),
        card("On track", len([r for r in real if r["sla_state"] == "ok"]), "within target"),
    ])

    by_team: dict[str, int] = {}
    for r in real:
        by_team[r["assigned_team"]] = by_team.get(r["assigned_team"], 0) + 1
    team_rows = "".join(
        f"<tr><td>{t}</td><td>{n}</td><td>{SLA['emergency']['team'] if 'Emergency' in t else ''}</td></tr>"
        for t, n in sorted(by_team.items(), key=lambda x: -x[1]))

    by_type: dict[str, int] = {}
    for r in real:
        by_type[r["request_type"]] = by_type.get(r["request_type"], 0) + 1
    type_rows = "".join(f"<tr><td>{k}</td><td>{v}</td><td>{schemas.REQUEST_TYPE_LABELS.get(k,'')}</td></tr>"
                        for k, v in sorted(by_type.items(), key=lambda x: -x[1]))

    ret_rows = "".join(
        f"<tr><td class='mono'>{x['return_id']}</td><td class='mono'>{x['order_id']}</td>"
        f"<td class='mono'>{html.escape(x['email'])}</td><td>{html.escape(x['reason'])}</td>"
        f"<td>{x['pickup_slot']}</td><td>Rs {float(x['amount_inr']):,.0f}</td>"
        f"<td><span class='pill info'>{x['status']}</span></td><td class='muted'>{x['created_h']}</td></tr>"
        for x in returns)

    ord_rows = "".join(
        f"<tr><td class='mono'>{x['order_id']}</td><td>{html.escape(x['customer_name'])}</td>"
        f"<td>{x['status'].replace('_',' ')}</td><td>Rs {float(x['total_inr']):,.0f}</td>"
        f"<td class='muted'>{x['placed_at'][:16].replace('T',' ')}</td></tr>" for x in orders)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apex Hyperstore &mdash; support queue</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Apex Hyperstore &mdash; support queue</h1>
<div class="sub">Every request the chatbot has filed, with SLA state at {now} IST &middot;
<strong>plain-text PII, no decryption &mdash; see the security note below</strong></div>

<div class="cards">{cards}</div>

<div class="bar">
  <input type="search" id="q" placeholder="Search reference, name, email, phone, order, team, text...">
  <span id="filters" style="display:flex;gap:8px;flex-wrap:wrap"></span>
  <label class="muted" style="display:flex;align-items:center;gap:5px">
    <input type="checkbox" id="hide_syn" {'checked' if a.hide_synthetic else ''}> hide synthetic test rows</label>
  <span class="muted"><b id="cnt">0</b> shown</span>
  <button onclick="location.reload()">Refresh</button>
</div>

<div class="emg">
  <div class="hd">EMERGENCY DESK &mdash; {len(emg)} request(s) at the 15-minute SLA</div>
  <div class="scroll"><table><thead><tr><th>Reference</th><th>Type</th><th>Customer</th>
  <th>Order</th><th>What happened</th><th>Team</th><th>SLA</th></tr></thead><tbody>
  {''.join(f"<tr><td class='mono'>{r['reference_id']}</td><td>{r['emergency_type']}</td>"
           f"<td><b>{html.escape(r['full_name'])}</b><br><span class='mono muted'>{html.escape(r['phone'])}</span></td>"
           f"<td class='mono'>{r['order_id'] or '-'}</td><td>{html.escape(r['summary'])}</td>"
           f"<td>{r['assigned_team']}</td>"
           f"<td>{pill(r['sla_state'], ('BREACHED ' if r['sla_state']=='breached' else 'due in ')+human(r['due_in_min']))}</td></tr>"
           for r in emg) or "<tr><td colspan='7' class='muted'>No emergencies.</td></tr>"}
  </tbody></table></div>
</div>

<h2>Request queue</h2>
<table><thead><tr><th>Reference</th><th>Urgency</th><th>Type / when</th><th>Customer</th>
<th>Order</th><th>Summary</th><th>Owner / channel</th><th>SLA</th></tr></thead>
<tbody id="body"></tbody></table>

<h2>Workload by team</h2>
<table><thead><tr><th>Team</th><th>Open requests</th><th>Note</th></tr></thead>
<tbody>{team_rows or '<tr><td colspan="3" class="muted">No real requests.</td></tr>'}</tbody></table>

<h2>Request types</h2>
<table><thead><tr><th>Value</th><th>Count</th><th>Meaning</th></tr></thead>
<tbody>{type_rows or '<tr><td colspan="3" class="muted">No real requests.</td></tr>'}</tbody></table>

<h2>Returns ({len(returns)})</h2>
<table><thead><tr><th>Return</th><th>Order</th><th>Email</th><th>Reason</th><th>Pickup</th>
<th>Amount</th><th>Status</th><th>Raised</th></tr></thead><tbody>{ret_rows}</tbody></table>

<h2>Orders ({len(orders)})</h2>
<table><thead><tr><th>Order</th><th>Customer</th><th>Status</th><th>Total</th><th>Placed</th></tr></thead>
<tbody>{ord_rows}</tbody></table>

<div class="note"><b>Security note &mdash; the data is not encrypted.</b>
This page renders contact names, emails and phone numbers straight out of
<code>data/apex_hyperstore.db</code>, where they are stored as plain text. Nothing was decrypted
to build it. Anyone with the HTML file has every customer's contact details, so treat it as
confidential. Before this goes anywhere real it needs encryption at rest (a library such as
<code>cryptography</code>'s Fernet over the PII columns, key from the environment, never from the
repo) plus role-based access on the dashboard. All records here are synthetic demo data for a
fictional company.</div>

<p class="sub" style="margin-top:24px">Regenerate: <code>.venv\\Scripts\\python.exe build_ops_dashboard.py</code>
&middot; source of truth is the same SQLite file the agent tools read and write.</p>
</div>
<script>{JS.replace("__ROWS__", json.dumps(rows))}</script>
</body></html>"""

    Path(a.out).write_text(page, encoding="utf-8")
    print(f"ops dashboard -> {Path(a.out).resolve()} ({len(page):,} bytes)")
    print(f"  {len(rows)} requests ({len(real)} real, {len(rows) - len(real)} synthetic), "
          f"{len(emg)} emergency, {len(breached)} breached, {len(returns)} returns, {len(orders)} orders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
