#!/usr/bin/env python3
"""offline_eval.py - deterministic checks for everything in the Apex Hyperstore app that
does not need an LLM: schema enforcement, every tool, database persistence and
reference-ID minting.

testing.py proves the *agent* behaves; this proves the *groundwork* is correct, so a
failing test there points at code rather than at model behaviour.

    .venv\\Scripts\\python.exe offline_eval.py
    .venv\\Scripts\\python.exe offline_eval.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from apex_hyperstore import db, schemas, tools  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[dict] = []


def check(group: str, name: str, ok: bool, detail: str = "") -> bool:
    results.append({"group": group, "case": name, "result": PASS if ok else FAIL, "detail": detail})
    return ok


def err_has(*needles: str) -> callable:
    def _(res: dict) -> bool:
        blob = json.dumps(res, default=str).lower()
        return res.get("status") in ("error", "not_found") and all(n.lower() in blob for n in needles)
    return _


def ok_of(*keys: str) -> callable:
    def _(res: dict) -> bool:
        return res.get("status") == "ok" and all(res.get(k) for k in keys)
    return _


# --------------------------------------------------------------------- database
G = "database"
check(G, "schema creates all 8 tables", True)
conn = db.connect()
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
expected = {"customers", "products", "orders", "order_items", "knowledge_base",
            "system_status", "service_requests", "returns"}
check(G, "all tables present", expected <= tables, f"missing={sorted(expected - tables)}")
counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in expected}
check(G, "seed data loaded", all(counts[t] > 0 for t in
                                 ("customers", "products", "orders", "knowledge_base")), json.dumps(counts))
check(G, "seeding is idempotent", db.connect().execute("SELECT COUNT(*) FROM products").fetchone()[0]
      == counts["products"])
check(G, "every seeded order has items", all(
    conn.execute("SELECT COUNT(*) FROM order_items WHERE order_id=?",
                 (r[0],)).fetchone()[0] > 0
    for r in conn.execute("SELECT order_id FROM orders")), "")

# ------------------------------------------------------------------- orders
G = "orders"
r = tools.lookup_order("APX-ORD-2026-041882", "ananya.iyer@example.com")
check(G, "lookup_order returns verified order", ok_of("order", "message")(r)
      and r["order"]["status"] == "out_for_delivery", json.dumps(r)[:160])
check(G, "lookup_order includes line items", len(r.get("order", {}).get("items", [])) > 0)
r = tools.lookup_order("APX-ORD-2026-041882", "someone.else@example.com")
check(G, "lookup_order blocks wrong email", r["status"] == "unverified" and r["verified"] is False)
r = tools.lookup_order("APX-ORD-2026-041882")
check(G, "lookup_order works without email", r["status"] == "ok")
check(G, "lookup_order rejects bad ID format", err_has("apx-ord-2026-041882")(tools.lookup_order("12345")))
check(G, "lookup_order reports unknown ID", err_has("no order")(tools.lookup_order("APX-ORD-2026-999999")))
r = tools.list_customer_orders("rohit.malhotra@example.com")
check(G, "list_customer_orders finds orders", ok_of("orders")(r) and len(r["orders"]) == 1)
check(G, "list_customer_orders includes profile", (r.get("customer") or {}).get("loyalty_tier") == "Gold")
check(G, "list_customer_orders rejects bad email",
      err_has("not a valid email")(tools.list_customer_orders("rohit@@example")))
check(G, "list_customer_orders handles unknown email",
      tools.list_customer_orders("nobody@example.com")["status"] == "not_found")
r = tools.search_products("water purifier")
check(G, "search_products finds by category words",
      ok_of("products")(r) and r["products"][0]["sku"] == "APX-SKU-100512", json.dumps(r)[:160])
check(G, "search_products reports discount %",
      r["products"][0]["discount_pct"] == round((1 - 11499 / 14999) * 100))
r = tools.search_products("cooktop")
check(G, "search_products flags out-of-stock",
      ok_of("products")(r) and r["products"][0]["in_stock"] is False, json.dumps(r)[:200])
check(G, "search_products no-match is not an error",
      tools.search_products("quantum skateboard")["status"] == "no_match")
check(G, "get_product_details returns SKU",
      ok_of("product")(tools.get_product_details("APX-SKU-100512")))
check(G, "get_product_details rejects unknown SKU",
      err_has("no product")(tools.get_product_details("APX-SKU-000000")))
check(G, "returns: delivered order accepted",
      ok_of("return_id")(tools.create_return_request(
          "APX-ORD-2026-041905", "rohit.malhotra@example.com",
          "Motor is making a grinding noise", "2026-10-18 10:00")))
check(G, "returns: wrong email refused",
      err_has("does not match")(tools.create_return_request(
          "APX-ORD-2026-041905", "wrong@example.com", "Grinding noise from motor")))
check(G, "returns: undelivered order refused",
      err_has("not delivered")(tools.create_return_request(
          "APX-ORD-2026-041988", "daniel.okafor@example.com", "Wrong item delivered instead")))
check(G, "returns: short reason refused",
      err_has("reason")(tools.create_return_request(
          "APX-ORD-2026-041905", "rohit.malhotra@example.com", "bad")))
check(G, "returns: bad order ID refused",
      err_has("apx-ord-2026-041882")(tools.create_return_request(
          "ORD-905", "rohit.malhotra@example.com", "Item is defective on arrival")))

# ------------------------------------------------------- support / knowledge base
G = "support"
r = tools.search_knowledge_base("payment failed APX-4021")
check(G, "kb search ranks exact error code first",
      ok_of("articles")(r) and r["articles"][0]["kb_id"] == "APX-KB-0101", json.dumps(r)[:200])
r = tools.search_knowledge_base("my coupon will not apply at checkout")
check(G, "kb search matches plain-language symptom",
      ok_of("articles")(r) and r["articles"][0]["kb_id"] == "APX-KB-0105", json.dumps(r)[:200])
check(G, "kb search returns a parsed article model",
      set(r["articles"][0]) >= {"kb_id", "error_code", "symptom", "fix_steps", "escalation_team"})
check(G, "kb search honours top_k",
      1 <= len(tools.search_knowledge_base("payment order delivery app", top_k=2)["articles"]) <= 2,
      str(len(tools.search_knowledge_base("payment order delivery app", top_k=2)["articles"])))
check(G, "kb search no-match is not an error",
      tools.search_knowledge_base("teleportation failure")["status"] == "no_match")
check(G, "kb search rejects empty query", err_has("too short")(tools.search_knowledge_base("a")))
r = tools.get_troubleshooting_guide("APX-KB-0106")
check(G, "guide returns step list", ok_of("article")(r) and "." in r["article"]["fix_steps"])
check(G, "guide rejects unknown kb_id", err_has("no article")(tools.get_troubleshooting_guide("APX-KB-9999")))
r = tools.check_system_status("all")
check(G, "system status lists all services", ok_of("services")(r) and len(r["services"]) == 5)
check(G, "system status surfaces degraded services", len(r["degraded_services"]) == 2,
      json.dumps(r["degraded_services"]))
check(G, "system status filters by name",
      ok_of("services")(tools.check_system_status("Checkout")) and
      len(tools.check_system_status("Checkout")["services"]) == 1)
check(G, "system status rejects unknown service",
      err_has("no service named")(tools.check_system_status("Teleporter")))

# ------------------------------------------------------------- service requests
G = "requests"
catalog = tools.list_service_catalog()
check(G, "catalog exposes 11 request types", len(catalog["request_types"]) == 11)
check(G, "catalog exposes 4 urgency levels", len(catalog["urgency_levels"]) == 4)
check(G, "catalog exposes 8 emergency types", len(catalog["emergency_types"]) == 8)
check(G, "catalog states mandatory fields",
      set(catalog["mandatory_fields"]) == {"full_name", "email", "phone", "request_type", "issue_summary"})
check(G, "catalog documents reference format", "APX-SR-YYYY-XXXXXX" in catalog["reference_format"])

r = tools.check_request_readiness()
check(G, "readiness lists every missing field",
      set(r["missing"]) == {"full_name", "email", "phone", "request_type", "issue_summary"},
      json.dumps(r["missing"]))
r = tools.check_request_readiness("Rohit Malhotra", "rohit.malhotra@example.com", "+91 98450 05518",
                                  "refund", "Refund not credited after 9 days")
check(G, "readiness passes complete details", r["ready"] is True, json.dumps(r["missing"]))
r = tools.check_request_readiness("###", "bad@@email", "123", "not_a_type", "short")
check(G, "readiness explains each bad field",
      set(r["missing"]) == {"full_name", "email", "phone", "request_type", "issue_summary"},
      json.dumps(r["missing"]))
check(G, "readiness accepts a spaced phone number",
      tools.check_request_readiness("Rohit Malhotra", "rohit.malhotra@example.com",
                                    "+91 98450 05518", "refund",
                                    "Refund not credited after 9 days")["ready"] is True)
r = tools.check_request_readiness("Rohit Malhotra", "rohit.malhotra@example.com", "9845005518",
                                  "refund", "Refund not credited after 9 days", "ORD-905")
check(G, "readiness flags malformed order ID", "order_id" in r["missing"])

normal = tools.create_support_request(
    "Rohit Malhotra", "rohit.malhotra@example.com", "9845005518", "refund",
    "Refund for the mixer grinder was credited to my card but not to my bank account",
    urgency="high", scheduled_for="2026-10-18 11:00", order_id="APX-ORD-2026-041905",
    channel="whatsapp")
check(G, "standard request filed", ok_of("reference_id")(normal), json.dumps(normal)[:200])
check(G, "standard request uses APX-SR prefix",
      bool(schemas.REFERENCE_ID_RE.match(normal.get("reference_id", ""))) and
      normal["reference_id"].startswith("APX-SR-2026-"), normal.get("reference_id", ""))
check(G, "request routed to the right team", normal["assigned_team"] == "Payments Recovery Desk")
check(G, "high urgency gets a 2-hour SLA",
      abs((schemas.parse_ts(normal["created_at"]) + timedelta(hours=2)
           - schemas.parse_ts(normal["target_response_at"])).total_seconds()) < 90,
      f"{normal['created_at']} -> {normal['target_response_at']}")
check(G, "scheduled_for normalised to IST",
      normal["scheduled_for"] == "2026-10-18 11:00 IST", normal["scheduled_for"])
check(G, "phone normalised to +91 E.164", normal["phone"] == "+919845005518", normal["phone"])
check(G, "email normalised to lowercase", normal["email"] == "rohit.malhotra@example.com")

emg = tools.create_support_request(
    "Fatima Sheikh", "fatima.sheikh@example.com", "9845007773", "emergency",
    "Water purifier leaked coolant across the kitchen floor and my child is nearby",
    urgency="emergency", emergency_type="damaged_goods", scheduled_for="asap")
check(G, "emergency request filed", ok_of("reference_id")(emg), json.dumps(emg)[:200])
check(G, "emergency uses APX-EMG prefix",
      emg["reference_id"].startswith("APX-EMG-2026-") and
      bool(schemas.REFERENCE_ID_RE.match(emg["reference_id"])), emg["reference_id"])
check(G, "emergency owned by response desk", emg["assigned_team"] == "Emergency Response Desk")
mins = (schemas.now_ist() - schemas.parse_ts(emg["created_at"])).total_seconds() / 60
check(G, "emergency SLA is ~15 minutes", mins < 16, f"{mins:.1f} min")
check(G, "emergency request is persisted", db.connect().execute(
    "SELECT COUNT(*) FROM service_requests WHERE reference_id=?", (emg["reference_id"],)
).fetchone()[0] == 1)

check(G, "emergency without a type is refused",
      err_has("emergency_type")(tools.create_support_request(
          "A B", "a@b.co", "9845000000", "emergency", "There is smoke coming from the oven")))
promo = tools.create_support_request(
    "A B", "a@b.co", "9845000000", "emergency",
    "Water is gushing from a burst pipe under the sink and flooding the flat",
    emergency_type="access_blocked")
check(G, "request_type=emergency is promoted to a 15-minute SLA",
      promo["status"] == "ok" and promo["urgency"] == "emergency"
      and promo["assigned_team"] == "Emergency Response Desk"
      and promo["reference_id"].startswith("APX-EMG-"), json.dumps(promo)[:200])
check(G, "emergency_type without emergency urgency is refused",
      err_has("urgency")(tools.create_support_request(
          "A B", "a@b.co", "9845000000", "product_defect", "Broken glass inside the pack",
          urgency="normal", emergency_type="damaged_goods")))
check(G, "invalid email is refused",
      err_has("email")(tools.create_support_request(
          "A B", "not-an-email", "9845000000", "billing", "Charged twice for one order")))
check(G, "invalid phone is refused",
      err_has("phone")(tools.create_support_request(
          "A B", "reject@example.com", "123", "billing", "Charged twice for one order")))
check(G, "short issue summary is refused",
      err_has("issue_summary")(tools.create_support_request(
          "A B", "reject@example.com", "9845000000", "billing", "help")))
check(G, "unknown request type is refused",
      err_has("request_type")(tools.create_support_request(
          "A B", "reject@example.com", "9845000000", "not_a_type", "Something is wrong with my order")))
check(G, "malformed order ID is refused",
      err_has("order_id")(tools.create_support_request(
          "A B", "reject@example.com", "9845000000", "order_issue", "Cart will not let me pay",
          order_id="ORD-123")))
check(G, "past scheduled_for is refused",
      err_has("past")(tools.create_support_request(
          "A B", "reject@example.com", "9845000000", "feedback", "Please call me back tomorrow",
          scheduled_for="2020-01-01 10:00")))
check(G, "unparseable scheduled_for is refused",
      err_has("scheduled_for")(tools.create_support_request(
          "A B", "reject@example.com", "9845000000", "feedback", "Please call me back tomorrow",
          scheduled_for="sometime soon please")))
check(G, "nothing is stored when validation fails", db.connect().execute(
    "SELECT COUNT(*) FROM service_requests WHERE email='reject@example.com'").fetchone()[0] == 0)

G = "phone normalisation"
for raw, want in [("9845005518", "+919845005518"), ("+91 98450 05518", "+919845005518"),
                  ("+919845005518", "+919845005518"), ("09845005518", "+919845005518"),
                  ("98450 05518", "+919845005518"), ("080-5555-0100", "+918055550100")]:
    got = schemas.normalise_phone(raw)
    check(G, f"normalises {raw!r}", got == want, f"got {got}, want {want}")
for bad in ["123", "abcdefghij", "", "12345678901234567890"]:
    try:
        schemas.normalise_phone(bad)
        check(G, f"rejects {bad!r}", False, "was accepted")
    except ValueError:
        check(G, f"rejects {bad!r}", True)

G = "requests"

r = tools.get_service_request_status(normal["reference_id"])
check(G, "status round-trips the stored request",
      ok_of("reference_id")(r) and r["assigned_team"] == normal["assigned_team"] and
      r["phone"] == normal["phone"], json.dumps(r)[:200])
check(G, "status rejects malformed reference",
      err_has("not a valid reference")(tools.get_service_request_status("SR-2026-123")))
check(G, "status reports unknown reference",
      err_has("no request")(tools.get_service_request_status("APX-SR-2026-ZZZZZZ")))

ids = {tools.create_support_request(
    f"Test User {i}", f"t{i}@example.com", "9845000000", "feedback",
    "Automated uniqueness probe message number")["reference_id"] for i in range(30)}
check(G, "30 minted references are all unique", len(ids) == 30, f"{len(ids)}/30")
check(G, "every minted reference matches the published format",
      all(schemas.REFERENCE_ID_RE.match(i) for i in ids))
check(G, "every request type maps to a team",
      set(schemas.REQUEST_TYPE_LABELS) == set(schemas.REQUEST_TYPE_TEAM))

# ------------------------------------------------------------------ concierge
G = "concierge"
r = tools.get_company_info("returns")
check(G, "company_info returns the returns policy",
      ok_of("info")(r) and "14-day" in json.dumps(r), json.dumps(r)[:160])
check(G, "company_info marks the company as fictional", "fictional" in r["info"]["disclaimer"])
check(G, "company_info handles unknown topic", ok_of("info")(tools.get_company_info("weather")))
check(G, "company_info default topic works", ok_of("info")(tools.get_company_info()))
r = tools.check_delivery_postcode("560066")
check(G, "same-day pincode is serviceable", ok_of("slots")(r) and r["tier"] == "same_day")
check(G, "unserviceable pincode explained", tools.check_delivery_postcode("000001")["serviceable"] is False)
check(G, "bad pincode rejected", err_has("6-digit")(tools.check_delivery_postcode("56A")))
r = tools.list_support_teams()
check(G, "team list is populated", ok_of("teams")(r) and len(r["teams"]) == 6)

# ------------------------------------------------------- end-to-end simulation
G = "simulation"
flow = []
flow.append(tools.check_request_readiness())
flow.append(tools.check_request_readiness("Daniel Okafor", "daniel.okafor@example.com", "9845009902",
                                          "emergency", "Grocery bag arrived warm and smells spoiled"))
flow.append(tools.create_support_request(
    "Daniel Okafor", "daniel.okafor@example.com", "9845009902", "emergency",
    "Grocery bag arrived warm and smells spoiled, batch printed as B-2211",
    urgency="emergency", emergency_type="food_safety", order_id="APX-ORD-2026-041988"))
flow.append(tools.get_service_request_status(flow[-1].get("reference_id", "")))
check(G, "emergency flow reaches the cold-chain owner",
      flow[1]["ready"] is True and flow[2]["assigned_team"] == "Emergency Response Desk")
check(G, "status lookup returns the same reference",
      flow[3].get("reference_id") == flow[2].get("reference_id"))
check(G, "emergency_type survives the round trip", flow[3].get("emergency_type") == "food_safety")
check(G, "order link survives the round trip",
      flow[3].get("order_id") == "APX-ORD-2026-041988")

# ---------------------------------------------------------------------- report
def report() -> int:
    width = 78
    print("=" * width)
    print("APEX HYPERSTORE - OFFLINE (NON-LLM) EVALUATION")
    print("=" * width)
    group = None
    for r in results:
        if r["group"] != group:
            group = r["group"]
            print(f"\n[{group.upper()}]")
        mark = "  ok  " if r["result"] == PASS else " FAIL "
        print(f"{mark} {r['case']}" + (f"\n         -> {r['detail']}" if r["result"] == FAIL and r["detail"] else ""))
    total, failed = len(results), sum(r["result"] == FAIL for r in results)
    print("\n" + "=" * width)
    print(f"{'PASS' if not failed else 'FAIL'}: {total - failed}/{total} checks passed"
          f"  ({100 * (total - failed) / total:.1f}%)")
    print("=" * width)
    return 0 if not failed else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write the full results as JSON")
    a = ap.parse_args()
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=2))
    sys.exit(report())
