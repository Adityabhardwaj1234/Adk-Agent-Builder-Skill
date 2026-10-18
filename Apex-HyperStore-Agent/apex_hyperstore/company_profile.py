"""Canonical, single-source-of-truth profile for the fictional company Apex Hyperstore.

Every contact address uses the reserved `.example` domain and the 555-01xx
fictional phone block, so nothing here can reach a real person. The support
agent is instructed to state that it is a demo identity when it quotes
contact details.
"""

BRAND = "Apex Hyperstore"
TAGLINE = "Everything for every home, same-day."

IDENTITY = {
    "legal_name": "Apex Hyperstore Private Limited",
    "brand": BRAND,
    "tagline": TAGLINE,
    "founded": "2009",
    "hq": "Apex Tower, 14th Floor, Outer Ring Road, Bellandur, Bengaluru 560103, India",
    "company_reg_no": "APX-HYP-2009-KA-041177 (fictional)",
    "cin": "U52100KA2009PTC041177 (fictional)",
    "ceo": "Mrs. Nandita Raghavan",
    "cto": "Mr. Karthik Venugopal",
    "chief_customer_officer": "Ms. Priya Deshmukh",
    "employees": "21,400",
    "footprint": "148 hypermarkets, 9 FreshHub cold-chain hubs, 11 regional warehouses "
                 "across Bengaluru, Hyderabad, Pune, Chennai, Delhi NCR and Kolkata",
}

CHANNELS = {
    "chat": "This assistant - web chat, available 24x7",
    "phone": "1800-555-0100 (India toll-free, 24x7) - fictional",
    "whatsapp": "+91 80 5555 0200 (9:00-23:00 IST) - fictional",
    "email": "care@apexhyperstore.example - first reply within 24 working hours - fictional",
    "emergency_line": "1800-555-0300 (Emergency Response Desk, 24x7) - fictional",
}

HOURS = {
    "chat_assistant": "24x7, every day including public holidays",
    "hypermarkets": "09:00 to 21:30 IST, all 7 days",
    "customer_care_desk": "08:00 to 22:00 IST, 7 days (phone is 24x7)",
    "emergency_response_desk": "24x7 including nights and holidays",
    "freshhub_grocery_window": "06:00 to 11:00 IST same-day slot; next day after 11:00",
}

POLICIES = {
    "delivery": "Free standard delivery above Rs 499. Same-day slots in 42 pincodes, "
                "next-day in 1,900 pincodes. Grocery and cold-chain items follow the "
                "FreshHub 06:00-11:00 IST window.",
    "returns": "14-day return window from delivery for non-perishable items. Refund to the "
               "original payment method within 5 working days of pickup. Grocery/perishables, "
               "personal care and innerwear are non-returnable for hygiene reasons.",
    "cancellation": "Free cancellation any time before the order moves to 'out for delivery'. "
                    "After that, refuse at doorstep or return under the 14-day policy.",
    "refunds": "Refunds are issued to the source account only - no cash refunds at the store. "
               "Bank settlement takes 3-5 working days after pickup scan.",
    "warranty": "12 months manufacturer warranty on appliances, 24 months on the Apex PureLife "
                "RO series. Warranty is claimable at any Apex Hyperstore service counter.",
    "pricing": "MRP is inclusive of all taxes. No surcharge at checkout. Price-match policy "
               "applies to identical SKUs within 7 days of purchase.",
    "membership": "Apex Prime membership is Rs 499/year or free above Rs 25,000 annual spend. "
                  "Members get free next-day delivery, early access to festive sales and 2x points.",
    "privacy": "We never ask for passwords, UPI PINs, OTPs or full card numbers on any channel. "
               "Such a request is always a scam - report it on the emergency line.",
}

SLA = {
    "emergency": {"target_minutes": 15, "team": "Emergency Response Desk"},
    "high": {"target_hours": 2, "team": "Priority Support Queue"},
    "normal": {"target_hours": 24, "team": "Standard Support Queue"},
    "low": {"target_hours": 72, "team": "Standard Support Queue"},
}

SUPPORT_TEAMS = [
    {"team": "Emergency Response Desk", "owns": "safety hazards, food safety, payment fraud, "
                                                  "burst pipe/wrong-address-with-damaged-goods, access blockage",
     "sla": "15 minutes", "hours": "24x7"},
    {"team": "Payments Recovery Desk", "owns": "failed or duplicated UPI/card payments, refund delays",
     "sla": "2 hours", "hours": "08:00-22:00 IST"},
    {"team": "Last Mile Operations", "owns": "delayed, lost or damaged delivery",
     "sla": "2 hours", "hours": "24x7"},
    {"team": "Identity & Accounts Desk", "owns": "login locks, OTP issues, address change",
     "sla": "24 hours", "hours": "08:00-22:00 IST"},
    {"team": "Quality Desk", "owns": "defective or wrong items, food safety follow-up",
     "sla": "24 hours", "hours": "08:00-22:00 IST"},
    {"team": "Loyalty & Coupons Desk", "owns": "Prime membership, missing points, coupon disputes",
     "sla": "72 hours", "hours": "09:00-19:00 IST"},
]

RUNNING_CAMPAIGNS = [
    "APXGET10 - 10% off on orders above Rs 1,999, valid to 2026-10-20",
    "FRESH20 - 20% off the first NutriBox subscription, valid to 2026-11-15",
]

DISCLAIMER = ("Apex Hyperstore is a fictional company created for this demo. All contact "
              "details, order IDs, prices and policies are synthetic.")

TOPICS = {
    "general": ["identity", "channels", "hours", "policies", "sla", "teams", "campaigns"],
    "identity": ["identity"],
    "contact": ["channels"],
    "hours": ["hours"],
    "policies": ["policies"],
    "delivery": ["policies.delivery", "hours.freshhub_grocery_window"],
    "returns": ["policies.returns", "policies.refunds", "policies.cancellation"],
    "membership": ["policies.membership"],
    "teams": ["teams"],
    "campaigns": ["campaigns"],
    "sla": ["sla"],
}


def _dig(key: str):
    if "." in key:
        head, tail = key.split(".", 1)
        return _dig(tail) if head == "policies" else None
    src = {"identity": IDENTITY, "channels": CHANNELS, "hours": HOURS, "policies": POLICIES,
           "sla": SLA, "teams": SUPPORT_TEAMS, "campaigns": RUNNING_CAMPAIGNS}.get(key)
    return src


def company_info(topic: str = "general") -> dict:
    """Return the profile sections for a topic. Unknown topics fall back to 'general'."""
    keys = TOPICS.get((topic or "general").strip().lower(), TOPICS["general"])
    out: dict = {"brand": BRAND, "topic": topic, "disclaimer": DISCLAIMER}
    for k in keys:
        if k.startswith("policies."):
            out.setdefault("policies", {})[k.split(".", 1)[1]] = POLICIES[k.split(".", 1)[1]]
        elif k.startswith("hours."):
            out.setdefault("operating_hours", {})[k.split(".", 1)[1]] = HOURS[k.split(".", 1)[1]]
        elif k == "sla":
            out["sla"] = {u: {"target": (f"{v['target_minutes']} minutes" if u == "emergency"
                                         else f"{v['target_hours']} hours"),
                              "team": v["team"]} for u, v in SLA.items()}
        else:
            out[k] = _dig(k)
    return out
