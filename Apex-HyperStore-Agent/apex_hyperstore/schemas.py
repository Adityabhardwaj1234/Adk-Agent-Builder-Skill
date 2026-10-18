"""Typed contracts for the Apex Hyperstore support platform.

These Pydantic models are the enforced contract for every conversation that
creates or reads a record. The LLM never writes to the database directly: it
hands values to a tool, the tool validates them here, and a reference ID is
only minted once validation passes. That is what stops half-filled requests,
typo'd phone numbers and invented order IDs from entering the system.
"""
from __future__ import annotations

import random
import re
import string
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

IST = timezone(timedelta(hours=5, minutes=30))

# ----------------------------------------------------------------- vocabularies
RequestType = Literal[
    "order_issue", "delivery_delay", "return_exchange", "refund", "product_defect",
    "billing", "account_access", "loyalty", "feedback", "emergency", "other",
]
Urgency = Literal["emergency", "high", "normal", "low"]
EmergencyType = Literal[
    "none", "safety_hazard", "food_safety", "payment_fraud", "medical_allergy",
    "damaged_goods", "access_blocked", "no_delivery_aged",
]
Channel = Literal["web_chat", "whatsapp", "phone", "email", "store_counter"]

REQUEST_TYPE_LABELS = {
    "order_issue": "A problem with an order",
    "delivery_delay": "Delivery running late or not arriving",
    "return_exchange": "Return or exchange of an item",
    "refund": "Refund not received or wrong amount",
    "product_defect": "Item defective, damaged or wrong",
    "billing": "Charges, invoice or coupon problem",
    "account_access": "Login, OTP or profile access",
    "loyalty": "Prime membership, points or coupons",
    "feedback": "Compliment, complaint or suggestion",
    "emergency": "Something urgent that needs the response desk now",
    "other": "Something not covered above",
}

EMERGENCY_TYPE_LABELS = {
    "none": "Not an emergency",
    "safety_hazard": "Safety hazard - electrical, fire or structural risk",
    "food_safety": "Food safety - spoiled, contaminated or wrong temperature",
    "payment_fraud": "Payment fraud - unauthorised debit or duplicate charge",
    "medical_allergy": "Medical or allergy reaction to a delivered product",
    "damaged_goods": "Damaged goods - leaking, broken or hazardous packaging",
    "access_blocked": "Access blocked - locked gate, no water or electricity supply",
    "no_delivery_aged": "No delivery and the customer is elderly, disabled or dependants alone",
}

URGENCY_SLA_MINUTES = {"emergency": 15, "high": 120, "normal": 1440, "low": 4320}

REQUEST_TYPE_TEAM = {
    "order_issue": "Last Mile Operations",
    "delivery_delay": "Last Mile Operations",
    "return_exchange": "Quality Desk",
    "refund": "Payments Recovery Desk",
    "product_defect": "Quality Desk",
    "billing": "Payments Recovery Desk",
    "account_access": "Identity & Accounts Desk",
    "loyalty": "Loyalty & Coupons Desk",
    "feedback": "Customer Experience Desk",
    "emergency": "Emergency Response Desk",
    "other": "Standard Support Queue",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-zA-Z]{2,}$")
# A customer may write a number in any of the shapes humans actually use, so the
# check works on digits and normalises rather than rejecting the formatting.
PHONE_HINT = re.compile(r"^[+\d][\d\s\-()]{5,20}$")
ORDER_ID_RE = re.compile(r"^APX-ORD-\d{4}-\d{6}$", re.I)
REFERENCE_ID_RE = re.compile(r"^APX-(?:SR|EMG)-\d{4}-[A-Z0-9]{6}$", re.I)
RETURN_ID_RE = re.compile(r"^APX-RET-\d{4}-\d{4}$", re.I)
ASAP_WORDS = {"asap", "as soon as possible", "immediately", "now", "right away", "urgent", ""}


def normalise_phone(raw: str) -> str:
    """Turn any of the shapes people write into +91XXXXXXXXXX.

    Accepts 9845005518, +91 98450 05518, +919845005518, 09845005518 and
    landlines with an area code, so nobody is blocked by punctuation.
    """
    if not PHONE_HINT.match((raw or "").strip()):
        raise ValueError("phone must be a 10-digit Indian mobile (6-9 start) or a landline")
    d = re.sub(r"\D", "", raw)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]  # trunk prefix on a mobile, or area code on a landline
    if len(d) == 10 and d[0] in "6789":
        return "+91" + d
    if 10 <= len(d) <= 11:
        return "+91" + d
    raise ValueError("phone must be a 10-digit Indian mobile (6-9 start) or a landline "
                     "with its area code")


# --------------------------------------------------------------------- inputs
class ContactDetails(BaseModel):
    """Who we may contact. All three fields are mandatory before a request is filed."""
    full_name: str = Field(min_length=2, max_length=80, description="Customer's full name")
    email: str = Field(description="Contact email address")
    phone: str = Field(description="Contact phone number")

    @field_validator("full_name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("full_name must contain letters")
        if not re.search(r"[A-Za-z].*[A-Za-z]", v) and len(v) < 3:
            raise ValueError("full_name looks incomplete")
        return v

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("email is not a valid address, expected name@domain.tld")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_ok(cls, v: str) -> str:
        return normalise_phone(v)


class ServiceRequestInput(BaseModel):
    """Everything required to file a support request of any kind."""
    contact: ContactDetails
    request_type: RequestType = Field(description="Category of the request")
    issue_summary: str = Field(min_length=12, max_length=600,
                               description="One or two sentences describing the problem in the "
                                           "customer's own words")
    urgency: Urgency = Field(default="normal", description="How fast the customer needs help")
    emergency_type: EmergencyType = Field(default="none",
                                         description="Set only when urgency is emergency")
    scheduled_for: str = Field(default="asap",
                               description="'asap' or a preferred callback/visit time, "
                                           "e.g. '2026-10-18 14:00'")
    order_id: str = Field(default="", description="Related Apex order ID, if any")
    channel: Channel = Field(default="web_chat", description="Channel the request arrived on")

    @field_validator("issue_summary")
    @classmethod
    def _summary_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 12:
            raise ValueError("issue_summary must be at least 12 characters describing the problem")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("issue_summary must be a written description, not symbols")
        return v

    @field_validator("order_id")
    @classmethod
    def _order_ok(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            return ""
        v = re.sub(r"\s+", "", v)
        if not ORDER_ID_RE.match(v):
            raise ValueError("order_id must look like APX-ORD-2026-041882")
        return v

    @field_validator("emergency_type")
    @classmethod
    def _emergency_ok(cls, v: str) -> str:
        if v == "none":
            return v
        return v

    def resolved_scheduled_for(self, now: datetime) -> tuple[str, datetime | None]:
        """Normalise scheduled_for into (label, parsed_datetime_or_None)."""
        raw = (self.scheduled_for or "").strip()
        if raw.lower() in ASAP_WORDS:
            return "asap", None
        cleaned = raw.replace(" at ", " ").replace(" IST", "").replace("ist", "")
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M",
                    "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d %B %Y %H:%M", "%d %b %Y %H:%M"):
            try:
                dt = datetime.strptime(cleaned, fmt).replace(tzinfo=IST)
            except ValueError:
                continue
            if dt < now - timedelta(hours=1):
                raise ValueError("scheduled_for is in the past, ask the customer for a future slot")
            return dt.strftime("%Y-%m-%d %H:%M IST"), dt
        raise ValueError(
            "scheduled_for must be 'asap' or a date-time such as 2026-10-18 14:00")


class OrderLookupInput(BaseModel):
    order_id: str = Field(description="Apex order ID, e.g. APX-ORD-2026-041882")
    email: str = Field(default="", description="Email on the order, used to verify ownership")

    @field_validator("order_id")
    @classmethod
    def _oid(cls, v: str) -> str:
        v = re.sub(r"\s+", "", v.strip().upper())
        if not ORDER_ID_RE.match(v):
            raise ValueError("order_id must look like APX-ORD-2026-041882")
        return v

    @field_validator("email")
    @classmethod
    def _em(cls, v: str) -> str:
        v = v.strip().lower()
        if v and not EMAIL_RE.match(v):
            raise ValueError("email is not a valid address")
        return v


class ReturnRequestInput(BaseModel):
    order_id: str
    email: str
    reason: str = Field(min_length=8, max_length=300)
    pickup_slot: str = Field(default="asap")

    @field_validator("order_id")
    @classmethod
    def _oid(cls, v: str) -> str:
        v = re.sub(r"\s+", "", v.strip().upper())
        if not ORDER_ID_RE.match(v):
            raise ValueError("order_id must look like APX-ORD-2026-041882")
        return v

    @field_validator("email")
    @classmethod
    def _em(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("email is not a valid address")
        return v


# -------------------------------------------------------------------- outputs
class ServiceRequestOutput(BaseModel):
    """The single shape every filed request returns, whatever its type."""
    reference_id: str = Field(description="APX-SR-* or APX-EMG-* reference, quote it back verbatim")
    request_status: str = Field(description="Lifecycle status of the ticket, e.g. 'open'")
    request_type: RequestType
    urgency: Urgency
    emergency_type: EmergencyType
    full_name: str
    email: str
    phone: str
    scheduled_for: str
    order_id: str = ""
    assigned_team: str
    target_response_at: str
    created_at: str
    channel: Channel
    next_step: str = Field(default="", description="What happens next; derived, not stored")


class OrderSummary(BaseModel):
    order_id: str
    status: str
    placed_at: str
    delivery_slot: str
    total_inr: float
    item_count: int
    payment_mode: str
    warehouse: str
    items: list[dict] = Field(default_factory=list)


class OrderLookupOutput(BaseModel):
    found: bool
    verified: bool
    order: Optional[OrderSummary] = None
    message: str


class KnowledgeArticle(BaseModel):
    kb_id: str
    topic: str
    error_code: str
    surface: str
    symptom: str
    cause: str
    fix_steps: str
    escalation_team: str
    severity: str


class SystemStatusEntry(BaseModel):
    service: str
    status: str
    incident: str
    updated_at: str


class ValidationCheck(BaseModel):
    field: str
    ok: bool
    detail: str


class ReadinessReport(BaseModel):
    ready: bool
    checks: list[ValidationCheck]
    missing: list[str]
    message: str


# ------------------------------------------------------------- reference IDs
def now_ist() -> datetime:
    return datetime.now(tz=IST)


def parse_ts(value: str) -> datetime:
    """Parse a stored or displayed timestamp into an IST-aware datetime.

    Handles both the ISO form written to the database and the human-readable
    "2026-10-18 09:30 IST" form that tools hand back to the agent and the customer.
    """
    text = str(value).strip().replace(" IST", "").replace("IST", "")
    dt = datetime.fromisoformat(text)
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def new_reference_id(urgency: str, when: datetime | None = None) -> str:
    """Mint an immutable request reference. Emergency requests get APX-EMG-*."""
    when = when or now_ist()
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(random.choice(alphabet) for _ in range(6))
    prefix = "EMG" if urgency == "emergency" else "SR"
    return f"APX-{prefix}-{when.year}-{suffix}"


def new_return_id(when: datetime | None = None) -> str:
    when = when or now_ist()
    seq = random.randint(1000, 9999)
    return f"APX-RET-{when.year}-{seq}"


def target_response_at(urgency: str, when: datetime | None = None) -> datetime:
    when = when or now_ist()
    return when + timedelta(minutes=URGENCY_SLA_MINUTES.get(urgency, 1440))
