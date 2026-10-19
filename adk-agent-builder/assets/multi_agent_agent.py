"""Coordinator + specialists: route each intent to the agent that owns it.

Template for ADK 2.x apps (replace <app>/agent.py, keep the generated
`from . import agent` in <app>/__init__.py). Everything below runs offline on
the sample data, so the structure can be scaffolded, imported and tested
before any real system is connected.

Pattern (references/architecture.md, sections 3 and 10):
- one coordinator that greets, answers small talk and routes; specialists who
  each own exactly one domain with a specific, non-overlapping description,
- tools return {"status": ...} dicts, so the model acts on errors instead of
  crashing and never has to answer facts from memory,
- write-tools validate before acting: `apply_refund` refuses an amount larger
  than the invoice - a prompt cannot promise that, code can.

Replace the sample data structures with real lookups (a database accessed
through tools - see assets/sqlite_tools.py for that pattern).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List

try:
    from google.adk.agents import Agent
except ImportError:
    @dataclass
    class Agent:  # type: ignore[no-redef]
        name: str
        model: str = "gemini-2.5-flash"
        description: str = ""
        instruction: str = ""
        tools: List[Callable[..., Any]] = field(default_factory=list)
        sub_agents: List["Agent"] = field(default_factory=list)

MODEL = "gemini-2.5-flash"  # keep the id `adk create` wrote into agent.py

# --- sample data: replace with real systems, reached only through tools -------

_SAMPLE_ORDERS = {
    "A100": {"status": "shipped", "eta": "Tuesday", "carrier": "DHL"},
    "B200": {"status": "processing", "eta": "next Monday", "carrier": None},
}

_SAMPLE_INVOICES = {
    "INV-7": {"order_id": "A100", "amount_usd": 42.50, "paid": True},
}

# --- tools (the model reads the docstrings as descriptions) -------------------

def lookup_order(order_id: str) -> dict:
    """Look up the live status, ETA and carrier of a customer order by its id.

    Example ids: A100, B200. Always use this instead of guessing.
    """
    row = _SAMPLE_ORDERS.get((order_id or "").strip().upper())
    if not row:
        return {"status": "error",
                "error": f"No order {order_id!r} found. Do not invent one; ask the customer to re-check the id."}
    # `status` is reserved for the tool outcome; the order's own lifecycle lives
    # in `order_status` so the two can never collide.
    return {"status": "success", "order_id": order_id.strip().upper(),
            "order_status": row["status"], "eta": row["eta"], "carrier": row["carrier"]}


def lookup_invoice(invoice_id: str) -> dict:
    """Look up an invoice: which order it pays for, the amount and whether it is paid."""
    row = _SAMPLE_INVOICES.get((invoice_id or "").strip().upper())
    if not row:
        return {"status": "error", "error": f"No invoice {invoice_id!r} found."}
    return {"status": "success", "invoice_id": invoice_id.strip().upper(), **row}


def apply_refund(invoice_id: str, amount_usd: float) -> dict:
    """Refund an invoice. Only call after the customer has confirmed the invoice id and amount."""
    inv = _SAMPLE_INVOICES.get((invoice_id or "").strip().upper())
    if not inv:
        return {"status": "error", "error": f"No invoice {invoice_id!r} found."}
    if amount_usd <= 0:
        return {"status": "error", "error": "Refund amount must be positive."}
    if amount_usd > inv["amount_usd"]:
        return {"status": "error",
                "error": f"Refund of {amount_usd:.2f} exceeds the invoice total {inv['amount_usd']:.2f}."}
    return {"status": "success", "refund_id": "REF-1", "invoice_id": invoice_id.strip().upper(),
            "amount_usd": amount_usd}

# --- specialists ---------------------------------------------------------------

order_support = Agent(
    name="order_support",
    model=MODEL,
    description="Order status, delivery dates and carrier questions for existing order ids.",
    instruction=(
        "Answer order questions with the `lookup_order` tool.\n"
        "- Never state an order fact that did not come from the tool.\n"
        "- If the tool returns an error, say the order could not be found and ask "
        "the customer to check the id from their confirmation email.\n"
        "- If carrier is null, say no carrier is assigned yet."
    ),
    tools=[lookup_order],
)

billing = Agent(
    name="billing",
    model=MODEL,
    description="Invoice, payment status and refund questions.",
    instruction=(
        "Use `lookup_invoice` for invoice facts and `apply_refund` for refunds.\n"
        "- Confirm the invoice id and amount with the customer before calling apply_refund.\n"
        "- If apply_refund returns an error, relay it plainly; never promise a refund it refused."
    ),
    tools=[lookup_invoice, apply_refund],
)

# --- coordinator: the entry point `adk` loads ---------------------------------

root_agent = Agent(
    name="support_desk",
    model=MODEL,
    description="Front door of the support desk: greets, answers small talk, routes to the right specialist.",
    instruction=(
        "Greet briefly. Then route each request:\n"
        "- order status / delivery / carrier -> transfer to order_support\n"
        "- invoices / payments / refunds -> transfer to billing\n"
        "Handle greetings and 'what can you do' yourself. For anything outside "
        "these two domains, say plainly that you cannot help with it - do not improvise."
    ),
    sub_agents=[order_support, billing],
)
