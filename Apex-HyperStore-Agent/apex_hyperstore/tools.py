"""Tools exposed to the Apex Hyperstore agents.

Each tool is the only path from the model to the database. Rules that apply to
every tool here:

* return a dict with a "status" key ("ok" or "error") and a human message,
* never raise for a bad customer input - return a precise, correctable error so
  the agent can ask the customer for the missing detail,
* never accept a value that has not passed the schema in schemas.py.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from pydantic import ValidationError

from . import db, schemas
from .company_profile import SLA as EMERGENCY_SLA
from .company_profile import TOPICS as COMPANY_TOPICS
from .company_profile import company_info


def _err(msg: str, **extra: Any) -> dict:
    return {"status": "error", "message": msg, **extra}


def _validation_error(prefix: str, exc: ValidationError) -> dict:
    """Turn pydantic errors into things a customer can actually fix."""
    missing, invalid = [], []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "value"
        msg = e["msg"].replace("Value error, ", "")
        if e["type"] == "missing":
            missing.append(loc)
        else:
            invalid.append(f"{loc}: {msg}")
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if invalid:
        parts.append("; ".join(invalid))
    return _err(f"{prefix}: " + " | ".join(parts), missing_fields=missing, invalid_fields=invalid)


def _safe(fn, *args, **kwargs):
    """Run a DB helper, turning unexpected exceptions into a tool-level error."""
    try:
        return fn(*args, **kwargs)
    except sqlite3.Error as exc:
        return _err(f"Database unavailable: {type(exc).__name__}. Do not retry immediately.")


# ======================================================================
# concierge / general assistant
# ======================================================================
def get_company_info(topic: str = "general") -> dict:
    """Official facts about Apex Hyperstore: who we are, contact channels, opening hours,
    delivery and return policies, membership, support teams and current offers.

    Use this whenever the customer asks about the company itself rather than about
    their own order or an error - for example "who do I talk to", "what are your
    timings", "what is your return policy", "do you deliver to my area".

    Args:
        topic: One of general, identity, contact, hours, policies, delivery, returns,
               membership, teams, campaigns, sla.
    """
    try:
        info = company_info(topic)
    except Exception as exc:  # never crash on a bad topic
        return _err(f"Unknown topic '{topic}'. Valid topics: {', '.join(COMPANY_TOPICS)}")
    return {"status": "ok", "topic": info["topic"], "info": info}


def check_delivery_postcode(postcode: str) -> dict:
    """Check whether Apex Hyperstore delivers to a 6-digit Indian pincode and which
    slots are available. Use this when a customer asks "do you deliver to 560066"
    or "when will my order arrive" and no order ID is known yet.

    Args:
        postcode: 6-digit Indian pincode.
    """
    pc = "".join(ch for ch in str(postcode) if ch.isdigit())
    if len(pc) != 6:
        return _err(f"'{postcode}' is not a 6-digit Indian pincode. Ask the customer for their pincode.")
    same_day = {"560066", "560103", "500032", "411045", "600020", "560001"}
    next_day = {"560048", "500081", "411014", "600026", "201301", "700001", "380015", "462001"}
    if pc in same_day:
        return {"status": "ok", "postcode": pc, "serviceable": True, "tier": "same_day",
                "slots": ["today 18:00-21:00", "tomorrow 09:00-12:00"],
                "message": f"Pincode {pc} is same-day serviceable. Grocery window is 06:00-11:00 IST."}
    if pc in next_day:
        return {"status": "ok", "postcode": pc, "serviceable": True, "tier": "next_day",
                "slots": ["tomorrow 09:00-12:00", "tomorrow 18:00-21:00"],
                "message": f"Pincode {pc} is next-day serviceable."}
    return {"status": "ok", "postcode": pc, "serviceable": False, "tier": "none", "slots": [],
            "message": f"Pincode {pc} is outside our own-delivery network. We can still serve it "
                       f"via a courier partner in 4-7 working days - offer a service request instead."}


def list_support_teams() -> dict:
    """List every Apex Hyperstore support team, what it owns and its response SLA.
    Use this when the customer asks who handles their kind of problem.
    """
    from .company_profile import SUPPORT_TEAMS, DISCLAIMER
    return {"status": "ok", "teams": SUPPORT_TEAMS, "disclaimer": DISCLAIMER}


# ======================================================================
# support agent - errors, how-to, system status
# ======================================================================
def search_knowledge_base(query: str, top_k: int = 3) -> dict:
    """Search the Apex Hyperstore troubleshooting knowledge base for an error message,
    error code or symptom. Always call this before guessing a fix when the customer
    reports an error or something is not working.

    Args:
        query: The customer's words or the error code, e.g. "payment failed APX-4021"
               or "app crashes at checkout".
        top_k: How many articles to return (1-5, default 3).
    """
    q = (query or "").strip()
    if len(q) < 3:
        return _err("Query is too short. Ask the customer to describe the error or share the error code.")
    try:
        k = max(1, min(int(top_k), 5))
    except (TypeError, ValueError):
        k = 3
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    rows = conn.execute("SELECT * FROM knowledge_base").fetchall()
    ql = q.lower()
    scored = []
    for r in rows:
        hay = " ".join(str(r[k]) for k in r.keys()).lower()
        score = 0
        if r["error_code"].lower() in ql:
            score += 10
        for tok in set(_words(ql)):
            if tok in hay:
                score += 2 if tok in r["topic"].lower() or tok in r["symptom"].lower() else 1
        if score:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: -x[0])
    hits = [schemas.KnowledgeArticle(**a) for _, a in scored[:k]]
    if not hits:
        return {"status": "no_match", "query": q,
                "message": "No article matches. Ask for the exact error code shown on screen, "
                           "or file a request with the support agent."}
    return {"status": "ok", "query": q, "count": len(hits),
            "articles": [h.model_dump() for h in hits]}


def _words(text: str) -> list[str]:
    """Split text into meaningful lowercase words (keeps error codes and pin-like tokens)."""
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split()
            if len(t) > 2 or t.isdigit()]


def get_troubleshooting_guide(kb_id: str) -> dict:
    """Fetch the full step-by-step fix for one knowledge-base article by its ID.
    Use after search_knowledge_base returns an article you want to follow in detail.

    Args:
        kb_id: Article ID such as APX-KB-0101.
    """
    kid = (kb_id or "").strip().upper()
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    row = conn.execute("SELECT * FROM knowledge_base WHERE kb_id=?", (kid,)).fetchone()
    if not row:
        return _err(f"No article with ID '{kid}'. Run search_knowledge_base to get a valid kb_id.")
    return {"status": "ok", "article": schemas.KnowledgeArticle(**dict(row)).model_dump()}


def check_system_status(service: str = "all") -> dict:
    """Check whether Apex Hyperstore services are healthy right now (checkout, payments,
    app, website, delivery, cold chain). Use before promising a fix time during an
    incident, or when a customer reports something failing for everyone.

    Args:
        service: 'all' or a specific service such as 'Checkout & Payments'.
    """
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    if (service or "all").strip().lower() == "all":
        rows = conn.execute("SELECT * FROM system_status ORDER BY service").fetchall()
    else:
        rows = conn.execute("SELECT * FROM system_status WHERE service LIKE ?",
                            (f"%{service.strip()}%",)).fetchall()
        if not rows:
            return _err(f"No service named '{service}'. Known services: "
                        + ", ".join(r[0] for r in conn.execute("SELECT service FROM system_status")))
    entries = [schemas.SystemStatusEntry(**dict(r)) for r in rows]
    degraded = [e.service for e in entries if e.status != "operational"]
    return {"status": "ok", "services": [e.model_dump() for e in entries],
            "degraded_services": degraded,
            "message": "All services operational." if not degraded
            else "Currently degraded: " + "; ".join(degraded)}


# ======================================================================
# orders agent
# ======================================================================
def lookup_order(order_id: str, email: str = "") -> dict:
    """Look up an Apex Hyperstore order by its ID, including status, delivery slot,
    items and tracking note. Always call this before telling a customer where their
    order is - never guess an order status.

    Args:
        order_id: The order ID, e.g. APX-ORD-2026-041882.
        email: Email on the order. If provided it must match, otherwise the result is
               returned unverified so the agent can ask for proof of identity.
    """
    try:
        inp = schemas.OrderLookupInput(order_id=order_id, email=email or "")
    except ValidationError as exc:
        return _validation_error("Invalid lookup", exc)
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (inp.order_id,)).fetchone()
    if not row:
        return {"status": "not_found", "found": False,
                "message": f"No order {inp.order_id} exists. Ask the customer to check the ID in "
                           f"their confirmation SMS or email - it must look like APX-ORD-2026-041882."}
    order = dict(row)
    items = [dict(i) for i in conn.execute("SELECT * FROM order_items WHERE order_id=?",
                                           (inp.order_id,)).fetchall()]
    verified = True
    if inp.email:
        verified = order["email"].lower() == inp.email
        if not verified:
            return {"status": "unverified", "found": True, "verified": False,
                    "order": schemas.OrderSummary(**{**order, "items": items}).model_dump(),
                    "message": "The order exists but the email does not match. Do not reveal "
                               "order details until the customer confirms the registered email."}
    return {"status": "ok", "found": True, "verified": verified,
            "order": schemas.OrderSummary(**{**order, "items": items}).model_dump(),
            "message": f"Order {order['order_id']} is {order['status'].replace('_', ' ')}."}


def list_customer_orders(email: str, limit: int = 5) -> dict:
    """List a customer's recent Apex orders so the agent can find the right order ID.
    Use when the customer says "my order" without giving an ID.

    Args:
        email: The customer's registered email.
        limit: Maximum orders to return (1-10, default 5).
    """
    em = (email or "").strip().lower()
    if not schemas.EMAIL_RE.match(em):
        return _err(f"'{email}' is not a valid email address. Ask the customer for their email.")
    try:
        n = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        n = 5
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    rows = conn.execute("SELECT * FROM orders WHERE email=? ORDER BY placed_at DESC LIMIT ?",
                        (em, n)).fetchall()
    if not rows:
        return {"status": "not_found", "message": f"No orders found for {em}."}
    cust = conn.execute("SELECT * FROM customers WHERE email=?", (em,)).fetchone()
    return {"status": "ok", "email": em,
            "customer": dict(cust) if cust else None,
            "orders": [dict(r) for r in rows],
            "message": f"Found {len(rows)} order(s) for {em}."}


def search_products(query: str, limit: int = 5) -> dict:
    """Search the Apex Hyperstore catalogue by name, brand or category. Use for price,
    stock or availability questions such as "do you have the RO purifier in stock".

    Args:
        query: Product name, brand or category words, e.g. "water purifier".
        limit: Maximum products to return (1-10, default 5).
    """
    q = (query or "").strip()
    if len(q) < 2:
        return _err("Query is too short to search the catalogue.")
    try:
        n = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        n = 5
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    words = [t for t in _words(q) if len(t) > 1]
    scored = []
    for r in conn.execute("SELECT * FROM products").fetchall():
        p = dict(r)
        hay = f"{p['name']} {p['category']} {p['brand']}".lower()
        score = sum(3 if w in p["name"].lower() else 1 for w in words if w in hay)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    hits = [p for _, p in scored[:n]]
    if not hits:
        return {"status": "no_match", "query": q,
                "message": "No product matched. Offer to check availability with a service request."}
    return {"status": "ok", "query": q, "count": len(hits),
            "products": [{"sku": p["sku"], "name": p["name"], "category": p["category"],
                          "brand": p["brand"], "price_inr": p["price_inr"], "mrp_inr": p["mrp_inr"],
                          "discount_pct": round((1 - p["price_inr"] / p["mrp_inr"]) * 100),
                          "stock_units": p["stock_units"], "warehouse": p["warehouse"],
                          "in_stock": p["stock_units"] > 0, "rating": p["rating"]} for p in hits],
            "message": f"{len(hits)} product(s) matched '{q}'."}


def get_product_details(sku: str) -> dict:
    """Get full catalogue detail for one product by SKU. Use after search_products when
    the customer needs exact price, stock count or warehouse for a specific item.

    Args:
        sku: Product SKU such as APX-SKU-100512.
    """
    s = (sku or "").strip().upper()
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    row = conn.execute("SELECT * FROM products WHERE sku=?", (s,)).fetchone()
    if not row:
        return _err(f"No product with SKU '{s}'. Run search_products to find the right SKU.")
    p = dict(row)
    p["in_stock"] = p["stock_units"] > 0
    p["discount_pct"] = round((1 - p["price_inr"] / p["mrp_inr"]) * 100)
    return {"status": "ok", "product": p}


def create_return_request(order_id: str, email: str, reason: str, pickup_slot: str = "asap") -> dict:
    """Create a return or exchange for a delivered order. Validates the order and the
    14-day window, stores the return and returns a return reference ID. Use when the
    customer wants to return or exchange an item - not for refunds of undelivered orders.

    Args:
        order_id: The order ID being returned from.
        email: Registered email on the order, for verification.
        reason: Why the item is being returned (min 8 characters).
        pickup_slot: 'asap' or a preferred pickup window, e.g. '2026-10-18 10:00'.
    """
    try:
        inp = schemas.ReturnRequestInput(order_id=order_id, email=email, reason=reason,
                                        pickup_slot=pickup_slot or "asap")
    except ValidationError as exc:
        return _validation_error("Cannot create return", exc)
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    order = conn.execute("SELECT * FROM orders WHERE order_id=?", (inp.order_id,)).fetchone()
    if not order:
        return _err(f"No order {inp.order_id} exists, so a return cannot be created.")
    if order["email"].lower() != inp.email:
        return _err("The email does not match this order. Ask the customer to confirm their "
                    "registered email before creating a return.")
    if order["status"] != "delivered":
        return _err(f"Order {inp.order_id} is '{order['status']}', not delivered. Only delivered "
                    f"orders can be returned - for an undelivered order offer a refund instead.")
    placed = schemas.parse_ts(order["placed_at"])
    if (schemas.now_ist() - placed).days > 14:
        return _err("This order is outside the 14-day return window. Offer a Quality Desk review "
                    "for a defective item or explain the policy.")
    rid = schemas.new_return_id()
    conn.execute("INSERT INTO returns VALUES (?,?,?,?,?,?,?,?,?)",
                 (rid, inp.order_id, inp.email, schemas.now_ist().isoformat(), inp.reason,
                  inp.pickup_slot, "Original payment method", float(order["total_inr"]),
                  "pickup_scheduled"))
    conn.commit()
    return {"status": "ok", "return_id": rid, "order_id": inp.order_id, "reason": inp.reason,
            "pickup_slot": inp.pickup_slot, "refund_method": "Original payment method",
            "amount_inr": float(order["total_inr"]), "state": "pickup_scheduled",
            "message": f"Return {rid} created for {inp.order_id}. Pickup {inp.pickup_slot}; "
                       f"refund of Rs {order['total_inr']:.0f} to original payment method "
                       f"within 5 working days of pickup scan."}


# ======================================================================
# service request agent
# ======================================================================
def list_service_catalog() -> dict:
    """List everything needed to file a service request: the request types, the urgency
    levels with their response SLA, the emergency types, the channels, and the fields
    that are mandatory. Use this at the start of a request conversation so you collect
    the right details and set the correct SLA.
    """
    return {
        "status": "ok",
        "request_types": [{"value": k, "label": v} for k, v in schemas.REQUEST_TYPE_LABELS.items()],
        "urgency_levels": [{"value": u, "respond_within": f"{m} minutes" if m <= 120 else f"{m // 60} hours"}
                           for u, m in schemas.URGENCY_SLA_MINUTES.items()],
        "emergency_types": [{"value": k, "label": v} for k, v in schemas.EMERGENCY_TYPE_LABELS.items()],
        "channels": list(schemas.Channel.__args__),
        "mandatory_fields": ["full_name", "email", "phone", "request_type", "issue_summary"],
        "optional_fields": ["urgency (default normal)", "emergency_type (default none)",
                            "scheduled_for (default asap)", "order_id"],
        "reference_format": "APX-SR-YYYY-XXXXXX, or APX-EMG-YYYY-XXXXXX for emergencies",
        "message": "Collect all mandatory fields before calling create_support_request.",
    }


def check_request_readiness(full_name: str = "", email: str = "", phone: str = "",
                            request_type: str = "", issue_summary: str = "",
                            order_id: str = "", scheduled_for: str = "asap") -> dict:
    """Validate the details collected so far and report exactly what is still missing.
    Use this before filing a request so you ask for one missing item at a time instead
    of collecting everything again.

    Args:
        full_name: Customer's full name if already given.
        email: Customer's email if already given.
        phone: Customer's phone if already given.
        request_type: One of the request types from list_service_catalog.
        issue_summary: What the customer reported.
        order_id: Related order ID if any.
        scheduled_for: 'asap' or a preferred time.
    """
    checks, missing = [], []

    def add(field, ok, detail):
        checks.append(schemas.ValidationCheck(field=field, ok=ok, detail=detail).model_dump())
        if not ok:
            missing.append(field)

    def probe(field, value):
        if not (value or "").strip():
            add(field, False, "not provided yet - ask the customer for it")
            return
        try:
            if field == "full_name":
                schemas.ContactDetails(full_name=value, email="probe@example.com",
                                       phone="9845000000")
                add(field, True, f"'{value.strip()}' accepted")
            elif field == "email":
                if schemas.EMAIL_RE.match(value.strip().lower()):
                    add(field, True, f"'{value.strip().lower()}' accepted")
                else:
                    add(field, False, "not a valid address, expected name@domain.tld")
            else:
                try:
                    schemas.normalise_phone(phone)
                    add(field, True, f"'{phone.strip()}' accepted")
                except ValueError as exc:
                    add(field, False, str(exc))
        except ValidationError as exc:
            add(field, False, exc.errors()[0]["msg"].replace("Value error, ", ""))

    probe("full_name", full_name)
    probe("email", email)
    probe("phone", phone)

    rt = (request_type or "").strip().lower()
    add("request_type", rt in schemas.REQUEST_TYPE_LABELS,
        f"'{rt}' is valid" if rt in schemas.REQUEST_TYPE_LABELS
        else f"pick one of: {', '.join(schemas.REQUEST_TYPE_LABELS)}")
    summary = " ".join((issue_summary or "").split())
    add("issue_summary", len(summary) >= 12,
        "detailed enough" if len(summary) >= 12
        else "needs at least 12 characters describing the problem in the customer's words")
    oid = (order_id or "").strip().upper()
    if oid:
        add("order_id", bool(schemas.ORDER_ID_RE.match(oid.replace(" ", ""))),
            "looks like a valid order ID" if schemas.ORDER_ID_RE.match(oid.replace(" ", ""))
            else "must look like APX-ORD-2026-041882")
    report = schemas.ReadinessReport(ready=not missing, checks=checks, missing=missing,
                                     message=("All mandatory details are present - call "
                                              "create_support_request now."
                                              if not missing else
                                              "Still needed: " + ", ".join(missing)))
    return {"status": "ok", **report.model_dump()}


def create_support_request(full_name: str, email: str, phone: str, request_type: str,
                           issue_summary: str, urgency: str = "normal",
                           emergency_type: str = "none", scheduled_for: str = "asap",
                           order_id: str = "", channel: str = "web_chat") -> dict:
    """File an Apex Hyperstore service request of any type and return its reference ID.
    Use this whenever the customer needs a human team - a complaint, a delay, a refund
    chase, an emergency, or any other follow-up. It validates everything, stores the
    request and tells the customer which team will respond and by when.

    Before calling this, collect full_name, email, phone, request_type and a clear
    issue_summary (at least 12 characters). For anything urgent set urgency='emergency'
    and pick the matching emergency_type so the Emergency Response Desk gets it in 15 minutes.

    Args:
        full_name: Customer's full name.
        email: Customer's email address.
        phone: Customer's phone number (10-digit mobile or landline).
        request_type: One of order_issue, delivery_delay, return_exchange, refund,
                      product_defect, billing, account_access, loyalty, feedback,
                      emergency, other.
        issue_summary: Clear description of the problem in the customer's own words.
        urgency: emergency, high, normal or low.
        emergency_type: none, safety_hazard, food_safety, payment_fraud, medical_allergy,
                        damaged_goods, access_blocked or no_delivery_aged.
        scheduled_for: 'asap' or a preferred callback/visit time such as '2026-10-18 14:00'.
        order_id: Related order ID if the request is about one.
        channel: web_chat, whatsapp, phone, email or store_counter.
    """
    try:
        inp = schemas.ServiceRequestInput(
            contact=schemas.ContactDetails(full_name=full_name, email=email, phone=phone),
            request_type=(request_type or "").strip().lower(),
            issue_summary=issue_summary,
            urgency=(urgency or "normal").strip().lower(),
            emergency_type=(emergency_type or "none").strip().lower(),
            scheduled_for=scheduled_for or "asap",
            order_id=order_id or "",
            channel=(channel or "web_chat").strip().lower(),
        )
    except ValidationError as exc:
        return _validation_error("Cannot file the request yet", exc)

    try:
        label, _ = inp.resolved_scheduled_for(schemas.now_ist())
    except ValueError as exc:
        return _err(f"scheduled_for: {exc}")

    # An emergency has to be treated as one. request_type=emergency is promoted
    # so a caller who forgot the urgency argument still gets the 15-minute SLA,
    # and an emergency can never travel without saying what kind it is.
    if inp.request_type == "emergency" and inp.urgency != "emergency":
        inp.urgency = "emergency"
    if inp.urgency == "emergency" and inp.emergency_type == "none":
        return _err("emergency_type: an emergency request needs an emergency_type "
                    "(safety_hazard, food_safety, payment_fraud, medical_allergy, "
                    "damaged_goods, access_blocked or no_delivery_aged).")
    if inp.emergency_type != "none" and inp.urgency != "emergency":
        return _err("urgency: an emergency_type was given but urgency is not 'emergency'. "
                    "Set urgency='emergency' as well.")

    reference = schemas.new_reference_id(inp.urgency)
    created = schemas.now_ist()
    team = schemas.REQUEST_TYPE_TEAM.get(inp.request_type, "Standard Support Queue")
    if inp.urgency == "emergency":
        team = EMERGENCY_SLA["emergency"]["team"]
    sla = schemas.target_response_at(inp.urgency, created)
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    try:
        conn.execute("INSERT INTO service_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (reference, created.isoformat(), inp.contact.full_name, inp.contact.email,
                      inp.contact.phone, inp.request_type, inp.urgency, inp.emergency_type,
                      label, inp.order_id, inp.issue_summary, inp.channel, team,
                      sla.isoformat(), "open"))
        conn.commit()
    except sqlite3.Error as exc:
        return _err(f"Could not store the request ({type(exc).__name__}). Nothing was saved - "
                    f"do not give the customer a reference ID.")
    out = schemas.ServiceRequestOutput(
        reference_id=reference, request_status="open", request_type=inp.request_type,
        urgency=inp.urgency, emergency_type=inp.emergency_type,
        full_name=inp.contact.full_name, email=inp.contact.email, phone=inp.contact.phone,
        scheduled_for=label, order_id=inp.order_id, assigned_team=team,
        target_response_at=sla.strftime("%Y-%m-%d %H:%M IST"), created_at=created.isoformat(),
        channel=inp.channel,
        next_step=(f"{team} will contact {inp.contact.full_name} at {inp.contact.phone} "
                   f"by {sla.strftime('%Y-%m-%d %H:%M IST')}."))
    return {"status": "ok", **out.model_dump(), "message": out.next_step}


def get_service_request_status(reference_id: str) -> dict:
    """Look up a previously filed Apex support request by its reference ID and return
    its current status, owning team and response target. Use when the customer quotes a
    reference like APX-SR-2026-XXXXXX or asks 'what happened to my complaint'.

    Args:
        reference_id: The reference ID, e.g. APX-SR-2026-7K2P9Q.
    """
    ref = re.sub(r"\s+", "", (reference_id or "").strip().upper())
    if not schemas.REFERENCE_ID_RE.match(ref):
        return _err(f"'{reference_id}' is not a valid reference ID. Expected APX-SR-YYYY-XXXXXX "
                    f"or APX-EMG-YYYY-XXXXXX.")
    conn = _safe(lambda: db.connect())
    if isinstance(conn, dict) and conn.get("status") == "error":
        return conn
    row = conn.execute("SELECT * FROM service_requests WHERE reference_id=?", (ref,)).fetchall()
    if not row:
        return {"status": "not_found", "reference_id": ref,
                "message": f"No request {ref} exists. Ask the customer to re-check the reference."}
    r = schemas.ServiceRequestOutput(**dict(row[0])).model_dump()
    r["next_step"] = (f"{r['assigned_team']} will contact {r['full_name']} at {r['phone']} "
                      f"by {r['target_response_at']}.")
    r["message"] = (f"Request {ref} is {r['request_status']}, owned by {r['assigned_team']}, "
                    f"response due {r['target_response_at']}.")
    return {"status": "ok", **r}


def mark_customer_context(tool_context, **kwargs) -> dict:
    """Internal helper (not exposed to the model): persist collected customer details in
    session state so a multi-turn conversation does not have to ask twice."""
    for k, v in kwargs.items():
        tool_context.state[k] = v
    return {"status": "ok"}


# Exposed groups for agent.py
CONCIERGE_TOOLS = [get_company_info, check_delivery_postcode, list_support_teams]
SUPPORT_TOOLS = [search_knowledge_base, get_troubleshooting_guide, check_system_status]
ORDERS_TOOLS = [lookup_order, list_customer_orders, search_products, get_product_details,
                create_return_request]
REQUEST_TOOLS = [list_service_catalog, check_request_readiness, create_support_request,
                 get_service_request_status]
