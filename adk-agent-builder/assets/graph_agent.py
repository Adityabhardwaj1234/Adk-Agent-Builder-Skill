"""Deterministic graph workflows (ADK 2.x): branching, fan-out/fan-in, code steps.

Template for processes that must be predictable - classification in, code
between the steps, reasoning only where it is actually needed. Two builders
are ready to run; assign the one you need:

    root_agent = build_routing_workflow()     # classify -> route -> handle
    # root_agent = build_fanout_workflow()    # gather in parallel -> join -> synthesize

Node semantics (references/architecture.md, section 6):
- function nodes receive `node_input` (the previous node's output) and return
  an `Event`: `Event(message=...)` is shown to the user, `Event(output=...)`
  carries data onward, `Event(route=...)` selects outgoing edges,
- dict edges `(router, {"BUG": handler, ...})` route on the emitted route
  string; `JoinNode` waits for parallel branches,
- cycles are not bounded automatically - keep exits certain, and use
  `LoopAgent`/dynamic workflows when you need iteration,
- because handlers are plain functions, most of a graph is testable with zero
  model calls; keep the LLM nodes to classification and synthesis.
"""
from __future__ import annotations

import json

from google.adk import Agent, Event, Workflow
from google.adk.workflow import JoinNode

MODEL = "gemini-2.5-flash"  # keep the id `adk create` wrote into agent.py


# ---------------------------------------------------------------------------
# Pattern 1: classifier -> router -> branch handlers
# ---------------------------------------------------------------------------

classifier = Agent(
    name="classifier",
    model=MODEL,
    instruction=(
        "Classify the message as exactly one word, nothing else:\n"
        "- BUG for anything about errors, outages or broken behaviour\n"
        "- BILLING for invoices, payments or refunds\n"
        "- SMALL_TALK for greetings and everything else"
    ),
)


def route_message(node_input: str) -> Event:
    """Turn the classifier's word into a route. Never raises: unknown -> SMALL_TALK."""
    word = (node_input or "").strip().upper()
    word = word if word in {"BUG", "BILLING", "SMALL_TALK"} else "SMALL_TALK"
    return Event(route=word)


def handle_bug(node_input: str) -> Event:
    # Replace with an Agent (e.g. a triage agent with tools) once the real
    # workflow is agreed; the deterministic form is what tests can pin down.
    return Event(message="That sounds like a bug. Please include what you did, what you "
                         "expected and what happened - I will file it as a ticket.")


def handle_billing(node_input: str) -> Event:
    return Event(message="Billing question received. Share the invoice id and I will look it up.")


def handle_small_talk(node_input: str) -> Event:
    return Event(message="Hi! I can help with bugs and billing questions.")


def build_routing_workflow() -> Workflow:
    return Workflow(
        name="routing_workflow",
        edges=[
            ("START", classifier, route_message),
            (route_message, {"BUG": handle_bug,
                             "BILLING": handle_billing,
                             "SMALL_TALK": handle_small_talk}),
        ],
    )


# ---------------------------------------------------------------------------
# Pattern 2: fan-out to independent steps, join, then one synthesis agent
# ---------------------------------------------------------------------------

def gather_tickets() -> Event:
    tickets = [{"id": "T-1", "priority": "high"}, {"id": "T-2", "priority": "low"}]
    return Event(output={"open_tickets": len(tickets), "top": tickets[0]})


def gather_oncall() -> Event:
    return Event(output={"oncall": "ada@example.com", "shift_ends": "18:00 UTC"})


def gather_health() -> Event:
    return Event(output={"error_rate": 0.4, "p95_ms": 820})


def assemble_briefing(node_input) -> Event:
    # `node_input` here is whatever the JoinNode passes along for your ADK
    # version - print the first run's node_input and normalise in this one
    # function rather than spreading assumptions across nodes.
    summary = node_input if isinstance(node_input, (dict, list, str)) else str(node_input)
    return Event(output={"briefing_source": "join", "raw": summary})


synth = Agent(
    name="synth",
    model=MODEL,
    instruction=(
        "Write a short operations briefing: what is on fire, who is on call, and "
        "the recommended next action. Use only the data you were given; if a "
        "field is missing, say so instead of guessing."
    ),
)


def build_fanout_workflow() -> Workflow:
    join = JoinNode(name="join")
    return Workflow(
        name="ops_briefing",
        edges=[
            ("START", gather_tickets, join),
            ("START", gather_oncall, join),
            ("START", gather_health, join),
            (join, assemble_briefing),
            (assemble_briefing, synth),
        ],
    )


root_agent = build_routing_workflow()
