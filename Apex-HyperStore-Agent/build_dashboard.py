#!/usr/bin/env python3
"""build_dashboard.py - generate Apex-HyperStore-Agent/apex_hyperstore_dashboard.html

A single self-contained HTML file that lists the whole solution in tables: the
company identity, the agent tree, every tool, the enforced schemas, the reference
ID formats, the test suite and the evaluation.

    .venv\\Scripts\\python.exe build_dashboard.py
    .venv\\Scripts\\python.exe build_dashboard.py --results adk_runs/run1/results.json

Company facts are read from apex_hyperstore/company_profile.py and schemas.py so
the dashboard can never drift from the agent's own source of truth.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from apex_hyperstore import schemas  # noqa: E402
from apex_hyperstore.company_profile import (CHANNELS, DISCLAIMER, HOURS, IDENTITY,  # noqa: E402
                                            POLICIES, RUNNING_CAMPAIGNS, SLA, SUPPORT_TEAMS)

HERE = Path(__file__).resolve().parent

# Tool reference: (tool, owning agent, what it does, arguments, what it returns)
TOOL_REFERENCE = [
    ("get_company_info", "apex_concierge",
     "Official company facts: identity, channels, hours, policies, membership, offers, teams",
     "topic: general | identity | contact | hours | policies | delivery | returns | membership | teams | campaigns | sla",
     "info{} with the requested sections + disclaimer"),
    ("check_delivery_postcode", "apex_concierge",
     "Serviceability and delivery tier for a 6-digit Indian pincode",
     "postcode: str", "serviceable, tier (same_day | next_day | none), slots[]"),
    ("list_support_teams", "apex_concierge",
     "Which team owns which kind of problem, with its response SLA",
     "-", "teams[] with team, owns, sla, hours"),
    ("search_knowledge_base", "support_agent",
     "Finds troubleshooting articles by error code or plain-language symptom",
     "query: str, top_k: int = 3", "articles[] of KnowledgeArticle, ranked"),
    ("get_troubleshooting_guide", "support_agent",
     "Full ordered fix steps for one article",
     "kb_id: str (APX-KB-nnnn)", "article: KnowledgeArticle"),
    ("check_system_status", "support_agent",
     "Live health of checkout, payments, app, website, delivery, cold chain",
     "service: str = 'all'", "services[], degraded_services[]"),
    ("lookup_order", "orders_agent",
     "Order by ID with status, slot, items, tracking note; optional email verification",
     "order_id: str, email: str = ''", "order: OrderSummary, verified: bool"),
    ("list_customer_orders", "orders_agent",
     "Recent orders for a customer when no order ID is known",
     "email: str, limit: int = 5", "orders[], customer profile"),
    ("search_products", "orders_agent",
     "Catalogue search for price, discount, stock and availability",
     "query: str, limit: int = 5", "products[] with price_inr, stock_units, in_stock"),
    ("get_product_details", "orders_agent",
     "Exact catalogue record for one SKU",
     "sku: str (APX-SKU-nnnnnn)", "product{} incl. warehouse, aisle, rating"),
    ("create_return_request", "orders_agent",
     "Validates a delivered order and the 14-day window, stores the return",
     "order_id, email, reason (min 8), pickup_slot = 'asap'",
     "return_id (APX-RET-yyyy-nnnn), refund_method, amount_inr"),
    ("list_service_catalog", "service_request_agent",
     "Request types, urgency levels, emergency types, channels, mandatory fields, reference format",
     "-", "catalog used to choose a valid request_type and SLA"),
    ("check_request_readiness", "service_request_agent",
     "Per-field validation of what has been collected so far; reports what is missing",
     "full_name, email, phone, request_type, issue_summary, order_id, scheduled_for",
     "ready: bool, checks[] per field, missing[]"),
    ("create_support_request", "service_request_agent",
     "Files any request of any type, stores it, returns the reference and the owning team",
     "full_name, email, phone, request_type, issue_summary, urgency, emergency_type, "
     "scheduled_for, order_id, channel",
     "ServiceRequestOutput: reference_id, assigned_team, target_response_at, next_step"),
    ("get_service_request_status", "service_request_agent",
     "Looks up a previously filed request by reference ID",
     "reference_id: str (APX-SR-2026-XXXXXX or APX-EMG-2026-XXXXXX)",
     "request_status, assigned_team, target_response_at, next_step"),
]

SCHEMA_REFERENCE = [
    ("ContactDetails", "input", "full_name, email, phone",
     "name >= 2 chars and contains letters; email must match name@domain.tld; "
     "phone normalised from 9845005518 / +91 98450 05518 / 09845005518 / landline to +91XXXXXXXXXX",
     "Required on every service request. Nothing is stored without it."),
    ("ServiceRequestInput", "input", "contact, request_type, issue_summary, urgency, "
                                      "emergency_type, scheduled_for, order_id, channel",
     "request_type and emergency_type are closed enums; issue_summary >= 12 chars; "
     "order_id must match APX-ORD-yyyy-nnnnnn; scheduled_for is 'asap' or a future "
     "date-time; urgency=emergency requires an emergency_type and the reverse",
     "This is what stops a half-filled or invented request reaching the database."),
    ("OrderLookupInput", "input", "order_id, email",
     "order_id must match the Apex format; email must be valid when supplied",
     "Used for the ownership check on every order lookup."),
    ("ReturnRequestInput", "input", "order_id, email, reason, pickup_slot",
     "valid order format, valid email, reason >= 8 chars",
     "Plus the delivered-status and 14-day window checks in the tool."),
    ("ServiceRequestOutput", "output", "reference_id, request_status, request_type, urgency, "
                                        "emergency_type, contact, scheduled_for, order_id, "
                                        "assigned_team, target_response_at, created_at, "
                                        "channel, next_step",
     "closed enums, reference format APX-SR / APX-EMG",
     "Every filed request returns this shape whatever its type, so the customer always "
     "gets a reference, an owner and a time."),
    ("OrderLookupOutput / OrderSummary", "output", "found, verified, order, message",
     "verified is false when the email does not match; no details are revealed when unverified",
     "Stops an order being discussed with someone who cannot prove it is theirs."),
    ("KnowledgeArticle", "output", "kb_id, topic, error_code, surface, symptom, cause, "
                                   "fix_steps, escalation_team, severity",
     "-", "The article is a typed object, so the fix steps cannot be truncated or paraphrased "
          "into something unsafe."),
    ("SystemStatusEntry", "output", "service, status, incident, updated_at",
     "-", "Incident text is quoted from the status store, never invented."),
    ("ReadinessReport / ValidationCheck", "output", "ready, checks[], missing[], message",
     "one ValidationCheck per mandatory field with a correctable reason",
     "Drives the 'ask for one missing thing at a time' behaviour."),
]

REFERENCE_IDS = [
    ("APX-ORD-yyyy-nnnnnn", "Order", "APX-ORD-2026-041882", r"^APX-ORD-\d{4}-\d{6}$",
     "minted by the order system; the agent can only read it"),
    ("APX-RET-yyyy-nnnn", "Return / exchange", "APX-RET-2026-0031", r"^APX-RET-\d{4}-\d{4}$",
     "minted by create_return_request after the order and window are validated"),
    ("APX-SR-yyyy-XXXXXX", "Service request (normal, high, low)", "APX-SR-2026-7K2P9Q",
     r"^APX-SR-\d{4}-[A-Z0-9]{6}$", "minted by create_support_request once every mandatory field validates"),
    ("APX-EMG-yyyy-XXXXXX", "Emergency service request (15-minute SLA)", "APX-EMG-2026-R4208U",
     r"^APX-EMG-\d{4}-[A-Z0-9]{6}$",
     "same tool, different prefix, so an emergency is separable in a report"),
    ("APX-KB-nnnn", "Knowledge-base article", "APX-KB-0101", r"^APX-KB-\d{4}$",
     "static; quoted so the agent follows the published fix steps"),
    ("APX-SKU-nnnnnn", "Product", "APX-SKU-100512", r"^APX-SKU-\d{6}$", "static catalogue identifier"),
    ("APX-CUS-nnnnnn", "Customer profile", "APX-CUS-100241", r"^APX-CUS-\d{6}$",
     "static; returned with the customer record"),
]

DB_TABLES = [
    ("customers", "Profile, city and loyalty tier",
     "customer_id (PK), full_name, email, phone, city, loyalty_tier, loyalty_points, joined_on"),
    ("products", "Catalogue for price, stock and availability questions",
     "sku (PK), name, category, brand, price_inr, mrp_inr, stock_units, warehouse, aisle, rating"),
    ("orders", "Order status, slot, payment and delivery facts",
     "order_id (PK), customer_id, email, placed_at, status, delivery_slot, warehouse, "
     "total_inr, item_count, payment_mode, address, tracking_note"),
    ("order_items", "Line items per order",
     "order_id + sku (PK), name, qty, unit_price_inr"),
    ("knowledge_base", "Published troubleshooting articles with error codes",
     "kb_id (PK), topic, error_code, surface, symptom, cause, fix_steps, escalation_team, severity"),
    ("system_status", "Live service health used before promising a fix time",
     "service (PK), status, incident, updated_at"),
    ("service_requests", "Every request the bot files, emergency or routine",
     "reference_id (PK), created_at, full_name, email, phone, request_type, urgency, "
     "emergency_type, scheduled_for, order_id, issue_summary, channel, assigned_team, "
     "target_response_at, request_status"),
    ("returns", "Returns and exchanges with pickup and refund method",
     "return_id (PK), order_id, email, created_at, reason, pickup_slot, refund_method, "
     "amount_inr, status"),
]

EVAL_PARAMS = [
    ("Task success", "25%", "Does the final answer actually resolve the request, using real "
     "tool data rather than plausible prose?", "R1-R10"),
    ("Instruction following", "20%", "Format, tone, scope and refusals as specified; collects "
     "fields before filing; never invents facts", "R8, R9, R13"),
    ("Tool use", "20%", "Right tool, right arguments, no redundant or looping calls, tool "
     "errors handled by asking the customer for the missing detail", "R6, R7, R10, R16"),
    ("Orchestration", "15%", "Correct routing to the owning specialist, no ping-pong, state "
     "and facts carried across the handoff", "R3, R4, R5, R14"),
    ("Robustness & safety", "15%", "Out-of-scope requests, prompt injection, secrets, bad "
     "input, missing data, no leakage of instructions", "R11, R12, R13"),
    ("Efficiency", "5%", "Latency p50/p95, tokens, tool calls per task", "R16"),
]


def e(v) -> str:
    return html.escape(str(v))


def table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def score_cell(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return f'<td class="muted">{e(v)}</td>'
    badge = {5: "good", 4: "good", 3: "warn", 2: "bad", 1: "bad"}.get(int(n), "")
    return f'<td class="score"><span class="pill {badge}">{int(n)}/5</span></td>'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="adk_runs/run1/results.json")
    ap.add_argument("--offline", default="adk_runs/offline_results.json")
    ap.add_argument("--evaluation", default="adk_runs/evaluation_scores.json")
    ap.add_argument("--out", default="apex_hyperstore_dashboard.html")
    args = ap.parse_args()

    results = {}
    rp = Path(args.results)
    if rp.exists():
        loaded = json.loads(rp.read_text(encoding="utf-8")).get("summary")
        if loaded:
            results = loaded
    offline = []
    op = Path(args.offline)
    if op.exists():
        offline = json.loads(op.read_text(encoding="utf-8"))
    scores = {}
    ep = Path(args.evaluation)
    if ep.exists():
        scores = json.loads(ep.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- tables
    identity_rows = [[k, e(v)] for k, v in IDENTITY.items()]
    hours_rows = [[k, e(v)] for k, v in HOURS.items()]
    channel_rows = [[k, e(v)] for k, v in CHANNELS.items()]
    policy_rows = [[k, e(v)] for k, v in POLICIES.items()]
    team_rows = [[e(t["team"]), e(t["owns"]), e(t["sla"]), e(t["hours"])] for t in SUPPORT_TEAMS]
    campaign_rows = [[e(c)] for c in RUNNING_CAMPAIGNS]

    sla_rows = [[u, e(f"{v['target_minutes']} minutes" if u == "emergency"
                      else f"{v['target_hours']} hours"), e(v["team"])] for u, v in SLA.items()]
    rtype_rows = [[k, e(v), e(schemas.REQUEST_TYPE_TEAM.get(k, ""))] for k, v in schemas.REQUEST_TYPE_LABELS.items()]
    emerg_rows = [[k, e(v)] for k, v in schemas.EMERGENCY_TYPE_LABELS.items()]
    chan_rows = [[c] for c in schemas.Channel.__args__]

    verdict = results.get("verdict", "not run yet")
    vclass = {"PASS": "good", "NEEDS_FIX": "warn", "INFRA_BLOCKED": "warn"}.get(verdict, "muted")
    if results:
        headline = (f"{results['tests_passed']}/{results['tests_total']} tests passed &middot; "
                    f"MUST {results['must_passed']}/{results['must_total']} &middot; "
                    f"p50 {results['latency']['p50_s']}s / p95 {results['latency']['p95_s']}s &middot; "
                    f"{results['tokens_total']:,} tokens &middot; "
                    f"{results['avg_tool_calls']} tool calls per task")
    else:
        headline = "Run <code>testing.py</code> to populate this section."

    req_rows = []
    if results:
        for rid, v in results.get("requirements", {}).items():
            st = v.get("status", "-")
            cls = {"MET": "good", "NOT_MET": "bad", "UNTESTED": "warn"}.get(st, "muted")
            req_rows.append([f'<b>{e(rid)}</b>', f'<span class="pill {cls}">{e(st)}</span>',
                             f'{v["passed"]}/{v["tests"]}', e(v.get("severity", "")),
                             e(v.get("text", ""))])

    cat_rows = []
    if results:
        for c, v in sorted(results.get("by_category", {}).items()):
            cls = "good" if v["passed"] == v["total"] else "bad"
            cat_rows.append([e(c), f'<span class="pill {cls}">{v["passed"]}/{v["total"]}</span>'])

    test_rows = []
    if results:
        rj = json.loads(rp.read_text(encoding="utf-8"))
        for t in rj.get("results", []):
            ok = t["passed"]
            cls = "good" if ok else "bad"
            resp = e(t.get("final_response", "")[:220])
            test_rows.append([
                f'<b>{e(t["test_id"])}</b>',
                f'<span class="pill {cls}">{"PASS" if ok else "FAIL"}</span>',
                e(t.get("category", "")),
                e(", ".join(t.get("requirement_ids", []))),
                e(f'{t["latency_s"][0]:.1f}s' if t.get("latency_s") else "-"),
                e(", ".join(t.get("tool_calls", [])) or "-"),
                e(", ".join(t.get("agents", []))),
                resp])

    off_rows = []
    off_fail = 0
    for r in offline:
        ok = r["result"] == "PASS"
        off_fail += 0 if ok else 1
        off_rows.append([f'<b>{e(r["group"])}</b>', e(r["case"]),
                         f'<span class="pill {"good" if ok else "bad"}">{e(r["result"])}</span>',
                         e(r.get("detail", ""))[:180]])

    eval_rows = []
    for dim, weight, criteria, reqs in EVAL_PARAMS:
        s = scores.get("scores", {}).get(dim, {})
        eval_rows.append([f"<b>{e(dim)}</b>", f'<span class="muted">{e(weight)}</span>',
                          e(criteria), score_cell(s.get("score", "-")), e(s.get("evidence", "")),
                          f'<span class="muted">{e(reqs)}</span>'])

    overall = scores.get("overall", {})
    overall_html = ""
    if overall:
        overall_html = (f'<div class="verdictbox"><div><span class="big">{e(overall.get("weighted", "-"))}'
                        f'<span class="small">/5</span></span></div><div>'
                        f'<div class="vlabel">Qualitative verdict</div>'
                        f'<div class="vtext">{e(overall.get("verdict", ""))}</div>'
                        f'<div class="vnote">{e(overall.get("note", ""))}</div></div></div>')

    gates = scores.get("gates", [])
    gate_rows = [[e(g[0]), f'<span class="pill {"good" if "PASS" in str(g[1]).upper() else "warn"}">'
                             f'{e(g[1])}</span>', e(g[2])] for g in gates]

    css = """
    :root{--bg:#0e1116;--panel:#161b22;--line:#2a323d;--text:#e6edf3;--muted:#8b949e;
          --good:#3fb950;--bad:#f85149;--warn:#d29922;--accent:#58a6ff;}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);
         font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
    .wrap{max-width:1400px;margin:0 auto;padding:32px 24px 80px}
    header.top{border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:28px}
    h1{margin:0 0 6px;font-size:30px;letter-spacing:-.02em}
    h2{margin:38px 0 12px;font-size:20px;border-bottom:1px solid var(--line);padding-bottom:8px}
    h3{margin:22px 0 8px;font-size:16px;color:var(--muted);font-weight:600;text-transform:uppercase;
       letter-spacing:.06em}
    .tag{color:var(--muted);font-size:14px}
    .banner{display:flex;gap:16px;align-items:center;flex-wrap:wrap;background:var(--panel);
            border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:20px 0}
    .verdictbox{display:flex;gap:24px;align-items:center;background:var(--panel);
                border:1px solid var(--line);border-radius:10px;padding:18px 22px;margin:18px 0}
    .big{font-size:40px;font-weight:700;color:var(--accent);line-height:1}
    .small{font-size:18px;color:var(--muted)}
    .vlabel{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
    .vtext{font-weight:600;margin:2px 0 4px}
    .vnote{color:var(--muted);font-size:13px;max-width:760px}
    table{width:100%;border-collapse:collapse;margin:10px 0 4px;font-size:14px}
    th{text-align:left;background:#1c222b;color:var(--muted);font-weight:600;
       text-transform:uppercase;font-size:11.5px;letter-spacing:.06em;padding:9px 10px;
       border:1px solid var(--line);white-space:nowrap}
    td{padding:9px 10px;border:1px solid var(--line);vertical-align:top}
    tbody tr:nth-child(even){background:#12171e}
    code{background:#0b0f14;border:1px solid var(--line);border-radius:4px;padding:1px 5px;
         font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#a5d6ff}
    .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:700;
          border:1px solid var(--line)}
    .pill.good{background:rgba(63,185,80,.15);color:var(--good);border-color:rgba(63,185,80,.4)}
    .pill.bad{background:rgba(248,81,73,.15);color:var(--bad);border-color:rgba(248,81,73,.4)}
    .pill.warn{background:rgba(210,153,34,.15);color:var(--warn);border-color:rgba(210,153,34,.4)}
    .pill.muted{background:#1c222b;color:var(--muted)}
    .muted{color:var(--muted)}
    .note{background:var(--panel);border-left:3px solid var(--accent);padding:12px 16px;
          margin:14px 0;border-radius:0 8px 8px 0;font-size:14px}
    pre{background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:14px;
        overflow-x:auto;font:12.5px ui-monospace,Menlo,Consolas,monospace;line-height:1.5}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:14px 0}
    .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
    .card .k{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
    .card .v{font-size:20px;font-weight:700;margin-top:4px}
    .tree{background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:14px 16px;
          font:12.5px ui-monospace,Menlo,Consolas,monospace;line-height:1.7;overflow-x:auto}
    .tree .c{color:var(--accent);font-weight:700}
    .tree .s{color:#7ee787}
    a{color:var(--accent)}
    """

    def money(v):
        try:
            return f"{float(v):,.0f}"
        except (TypeError, ValueError):
            return e(v)

    tag_line = IDENTITY["tagline"]
    html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apex Hyperstore &mdash; agentic support solution</title>
<style>{css}</style></head>
<body><div class="wrap">

<header class="top">
  <h1>Apex Hyperstore &mdash; agentic customer-support solution</h1>
  <div class="tag">{e(IDENTITY['legal_name'])} &middot; {e(tag_line)} &middot; {e(DISCLAIMER)}</div>
</header>

<div class="banner">
  <span class="pill {vclass}" style="font-size:14px;padding:6px 16px">{e(verdict)}</span>
  <span>{headline}</span>
</div>

<div class="grid">
  <div class="card"><div class="k">Agents</div><div class="v">1 + 3</div>
    <div class="muted">coordinator + 3 specialists</div></div>
  <div class="card"><div class="k">Tools</div><div class="v">{len(TOOL_REFERENCE)}</div>
    <div class="muted">every one gated by a schema</div></div>
  <div class="card"><div class="k">Database tables</div><div class="v">{len(DB_TABLES)}</div>
    <div class="muted">SQLite, seeded, parameterised</div></div>
  <div class="card"><div class="k">Reference prefixes</div><div class="v">{len(REFERENCE_IDS)}</div>
    <div class="muted">orders, returns, requests, emergencies</div></div>
  <div class="card"><div class="k">Offline checks</div>
    <div class="v">{len(offline) - off_fail}/{len(offline)}</div>
    <div class="muted">no model needed</div></div>
</div>

<h2>1. Agent architecture</h2>
<div class="tree">
<span class="c">apex_concierge</span>  <span class="muted">(root_agent &mdash; coordinator, general assistant)</span>
  <span class="muted">tools:</span> get_company_info, check_delivery_postcode, list_support_teams
  <br>&nbsp;&nbsp;&#9492;&#9472; <span class="s">orders_agent</span>          <span class="muted">orders, delivery, returns, refunds, catalogue</span>
  <br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="muted">tools:</span> lookup_order, list_customer_orders, search_products, get_product_details, create_return_request
  <br>&nbsp;&nbsp;&#9492;&#9472; <span class="s">support_agent</span>         <span class="muted">error codes, app/website faults, outages</span>
  <br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="muted">tools:</span> search_knowledge_base, get_troubleshooting_guide, check_system_status
  <br>&nbsp;&nbsp;&#9492;&#9472; <span class="s">service_request_agent</span>  <span class="muted">requests, callbacks, emergencies, reference IDs</span>
  <br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="muted">tools:</span> list_service_catalog, check_request_readiness, create_support_request, get_service_request_status
</div>
{table(["Agent", "Owns (routing trigger)", "Tools", "Model", "Guarded"],
        [['<b>apex_concierge</b>',
          "Greetings, small talk, company facts, delivery area, out-of-scope handling",
          '<code>get_company_info</code> <code>check_delivery_postcode</code> <code>list_support_teams</code>',
          "<code>gemini-flash-latest</code>", "yes"],
         ["<b>orders_agent</b>",
          "Order ID, tracking, late delivery, cancel, return, exchange, refund chase, price, stock",
          '<code>lookup_order</code> <code>list_customer_orders</code> <code>search_products</code> '
          '<code>get_product_details</code> <code>create_return_request</code>',
          "<code>gemini-flash-latest</code>", "yes"],
         ["<b>support_agent</b>",
          "Error codes (APX-nnnn), crashes, login/OTP, failed payments, coupons, outages",
          '<code>search_knowledge_base</code> <code>get_troubleshooting_guide</code> <code>check_system_status</code>',
          "<code>gemini-flash-latest</code>", "yes"],
         ["<b>service_request_agent</b>",
          "Complaints, callbacks, scheduled visits, emergencies, reference tracking",
          '<code>list_service_catalog</code> <code>check_request_readiness</code> '
          '<code>create_support_request</code> <code>get_service_request_status</code>',
          "<code>gemini-flash-latest</code>", "yes"]])}

<h2>2. Company identity (fictional)</h2>
{table(["Field", "Value"], identity_rows)}
<h3>Support channels</h3>
{table(["Channel", "Detail"], channel_rows)}
<h3>Operating hours</h3>
{table(["Function", "Hours"], hours_rows)}
<h3>Policies the agent quotes</h3>
{table(["Policy", "Detail"], policy_rows)}
<h3>Support teams and SLAs</h3>
{table(["Team", "Owns", "Response SLA", "Hours"], team_rows)}
<h3>Live campaigns</h3>
{table(["Offer"], campaign_rows)}

<h2>3. Tools</h2>
<div class="note">Every tool returns a dict with a <code>status</code> key
(<code>ok</code> / <code>error</code> / <code>not_found</code>) and a message written for the customer,
so a bad input becomes a question the agent asks rather than an exception. A
<code>before_tool_callback</code> on each agent blocks any tool that is not on the list above and logs every call.</div>
{table(["Tool", "Agent", "Purpose", "Arguments", "Returns"], TOOL_REFERENCE)}

<h2>4. Enforced schemas</h2>
<div class="note">The model never writes to the database. It passes values to a tool, the tool validates
them against these Pydantic models, and a reference ID is minted only after validation passes. This is what
makes "ask for name, email or phone" and "emergency type and time" enforceable rather than aspirational.</div>
{table(["Model", "Direction", "Fields", "Validation rules", "Why it exists"],
        [[f"<b>{e(m)}</b>", e(d), e(f), e(r), e(w)] for m, d, f, r, w in SCHEMA_REFERENCE])}

<h2>5. Reference ID formats</h2>
{table(["Format", "Meaning", "Example", "Regex", "Issued by"], REFERENCE_IDS)}

<h2>6. Request vocabulary</h2>
<h3>Request types and owning team</h3>
{table(["Value", "Label", "Owning team"], rtype_rows)}
<h3>Urgency and response SLA</h3>
{table(["Urgency", "Respond within", "Team"], sla_rows)}
<h3>Emergency types (require urgency = emergency)</h3>
{table(["Value", "Meaning"], emerg_rows)}
<h3>Channels</h3>
{table(["Channel"], chan_rows)}

<h2>7. Database</h2>
{table(["Table", "Purpose", "Key columns"], DB_TABLES)}

<h2>8. Requirements</h2>
{table(["id", "Status", "passed", "severity", "requirement"], req_rows or [["", "run the suite", "", "", ""]])}

<h2>9. Test results</h2>
<h3>By category</h3>
{table(["Category", "Passed"], cat_rows)}
<h3>Per test</h3>
{table(["Test", "Result", "Category", "Requirements", "Latency", "Tools called", "Agents", "Final response"],
        test_rows or [["", "run the suite", "", "", "", "", "", ""]])}

<h3>Deterministic (offline) checks</h3>
<div class="note">These {len(offline)} checks need no model: they exercise the schemas, every tool, the
database and reference minting directly (<code>offline_eval.py</code>). They separate "the groundwork is
broken" from "the model answered badly".</div>
{table(["Group", "Check", "Result", "Detail"], off_rows or [["", "run offline_eval.py --json", "", ""]])}

<h2>10. Evaluation parameters</h2>
{overall_html}
{table(["Dimension", "Weight", "What is scored", "Score", "Evidence", "Requirements"], eval_rows)}
<h3>Delivery gates</h3>
{table(["Gate", "Status", "Basis"], gate_rows or [["", "populate adk_runs/evaluation_scores.json", ""]])}

<h2>11. How to run</h2>
<pre>cd Apex-HyperStore-Agent

# 1. dependencies (already installed in .venv)
.venv\\Scripts\\python.exe -m pip install -r apex_hyperstore\\requirements.txt

# 2. the key lives in .env at this level - never commit it
#    .env  -&gt;  GOOGLE_API_KEY=...

# 3. deterministic checks, no model needed
.venv\\Scripts\\python.exe offline_eval.py --json adk_runs\\offline_results.json

# 4. introspect the agent tree, then run the full suite
.venv\\Scripts\\python.exe ..\\adk-agent-builder\\testing.py --workspace . --app apex_hyperstore --init-spec
.venv\\Scripts\\python.exe ..\\adk-agent-builder\\testing.py --workspace . --app apex_hyperstore ^
        --spec adk_runs\\spec.json --out adk_runs\\run1

# 4b. or the paced runner: same tests, same testing.py, sliced so the free tier's
#     5 requests/minute does not turn every later test into a 429
.venv\\Scripts\\python.exe run_paced_suite.py --chunk 3 --pause 75

# 5. rebuild this dashboard
.venv\\Scripts\\python.exe build_dashboard.py --results adk_runs\\run3\\results.json

# 6. talk to it (development only)
.venv\\Scripts\\adk.exe web .</pre>

<div class="note"><b>Safety rules baked into every agent</b>
<ul>
<li>Never reveals or paraphrases its instructions, tools or prompt.</li>
<li>Never asks for or accepts a password, UPI PIN, OTP or CVV, and never echoes one back.</li>
<li>Never states an order status, price, stock level or SLA that a tool did not return in this conversation.</li>
<li>Only quotes a reference ID that came from <code>create_support_request</code> or <code>get_service_request_status</code>.</li>
<li>Order details stay hidden until the registered email matches.</li>
</ul></div>

<p class="muted" style="margin-top:30px">{e(DISCLAIMER)}<br>
Generated by <code>build_dashboard.py</code> from the same modules the agent imports, so it cannot
drift from the running system.</p>

</div></body></html>"""

    Path(args.out).write_text(html_doc, encoding="utf-8")
    print(f"dashboard -> {Path(args.out).resolve()}  ({len(html_doc):,} bytes)")
    if results:
        print(f"  verdict {verdict}: {results['tests_passed']}/{results['tests_total']} passed")
    if offline:
        print(f"  offline checks: {len(offline) - off_fail}/{len(offline)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
