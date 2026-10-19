"""Safe SQLite tools: storage is reachable only through validated functions.

Why tools and not direct database access (references/data-memory-skills.md,
section 3): the model hands values to code, code validates them, and only then
does anything touch storage. That makes "ask for the id before querying" a
guarantee instead of a prompt wish, blocks injection by construction
(parameterised SQL only), and gives the model actionable dict errors instead
of stack traces it never sees.

Wire the functions into an agent:

    from . import sqlite_tools
    ...
    tools=[sqlite_tools.lookup_order, sqlite_tools.create_request]

Set APP_DB_PATH in .env to point at a real file; the default is
<app>/data/app.db, created on first use. Run this module directly to create
and seed a demo database:

    python -m <app>.sqlite_tools         (or)  python sqlite_tools.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

try:
    from pydantic import field_validator as _field_validator
    _PYDANTIC_V2 = True
except ImportError:
    from pydantic import validator as _validator
    _PYDANTIC_V2 = False


def _email_validator(field_name: str):
    if _PYDANTIC_V2:
        return _field_validator(field_name)
    return _validator(field_name, allow_reuse=True)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id   TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    eta        TEXT,
    carrier    TEXT
);
CREATE TABLE IF NOT EXISTS requests (
    request_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_email TEXT NOT NULL,
    summary        TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_FALLBACK_DB_PATH: Path | None = None
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db_path() -> Path:
    """Resolve the database path: APP_DB_PATH from the environment, else <app>/data/app.db."""
    global _FALLBACK_DB_PATH
    configured = os.environ.get("APP_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if _FALLBACK_DB_PATH is not None:
        return _FALLBACK_DB_PATH
    return Path(__file__).resolve().parent / "data" / "app.db"


def connect() -> sqlite3.Connection:
    """Open a short-lived connection with row access by name and FK checks on."""
    global _FALLBACK_DB_PATH
    path = db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.OperationalError:
        _FALLBACK_DB_PATH = Path(tempfile.gettempdir()) / "adk_sqlite_tools" / "app.db"
        _FALLBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_FALLBACK_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def init_db() -> dict:
    """Create the tables and seed demo rows (idempotent)."""
    global _FALLBACK_DB_PATH
    try:
        with connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_id, status, eta, carrier) VALUES (?, ?, ?, ?)",
                ("A100", "shipped", "Tuesday", "DHL"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_id, status, eta, carrier) VALUES (?, ?, ?, ?)",
                ("B200", "processing", "next Monday", None),
            )
            row = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()
    except sqlite3.OperationalError:
        _FALLBACK_DB_PATH = Path(tempfile.gettempdir()) / "adk_sqlite_tools" / "app.db"
        os.environ["APP_DB_PATH"] = str(_FALLBACK_DB_PATH)
        with connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_id, status, eta, carrier) VALUES (?, ?, ?, ?)",
                ("A100", "shipped", "Tuesday", "DHL"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_id, status, eta, carrier) VALUES (?, ?, ?, ?)",
                ("B200", "processing", "next Monday", None),
            )
            row = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()
    return {"status": "success", "db": str(db_path()), "orders": row["n"]}


# --- read tool -----------------------------------------------------------------

def lookup_order(order_id: str) -> dict:
    """Look up the status, ETA and carrier of an order by its id (example: A100)."""
    order_id = (order_id or "").strip().upper()
    if not order_id:
        return {"status": "error", "error": "order_id is required."}
    if len(order_id) > 40:
        return {"status": "error", "error": "order_id is too long to be a real id."}
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT order_id, status, eta, carrier FROM orders WHERE order_id = ?",
                (order_id,),  # parameterised: values never become SQL text
            ).fetchone()
    except sqlite3.Error as e:
        return {"status": "error", "error": f"database unavailable: {e}"}
    if row is None:
        return {"status": "error",
                "error": f"No order {order_id!r} found. Ask the customer to re-check the id; never invent one."}
    record = dict(row)
    order_status = record.pop("status", None)
    return {"status": "success", "order_status": order_status, **record}


# --- write tool ------------------------------------------------------------------

class RequestInput(BaseModel):
    """Validated shape of a support request before it is stored."""

    customer_email: str = Field(min_length=3, max_length=254)
    summary: str = Field(min_length=5, max_length=1000)

    @_email_validator("customer_email")
    @classmethod
    def _validate_email_pattern(cls, v: str) -> str:
        if not _EMAIL_RE.match((v or "").strip()):
            raise ValueError("customer_email must be a valid email address")
        return v


def create_request(customer_email: str, summary: str) -> dict:
    """Store a support request. Both fields are required; the email must be valid."""
    try:
        data = RequestInput(customer_email=customer_email, summary=summary)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        return {"status": "error",
                "error": f"Invalid input ({problems}). Ask the customer for the missing or corrected value."}
    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO requests (customer_email, summary) VALUES (?, ?)",
                (data.customer_email.strip(), data.summary.strip()),
            )
            request_id = cur.lastrowid
    except sqlite3.Error as e:
        return {"status": "error", "error": f"could not save the request: {e}"}
    return {"status": "success", "request_id": request_id, "customer_email": data.customer_email.strip()}


def list_requests(customer_email: str) -> dict:
    """List the five most recent requests for a customer email."""
    email = (customer_email or "").strip().lower()
    if "@" not in email:
        return {"status": "error", "error": "A customer email is required to list requests."}
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT request_id, summary, created_at FROM requests "
                "WHERE lower(customer_email) = ? ORDER BY request_id DESC LIMIT 5",
                (email,),
            ).fetchall()
    except sqlite3.Error as e:
        return {"status": "error", "error": f"database unavailable: {e}"}
    return {"status": "success", "count": len(rows), "requests": [dict(r) for r in rows]}


if __name__ == "__main__":  # manual smoke: create the file and read one row
    print(init_db())
    print(lookup_order("A100"))
    print(create_request("ada@example.com", "Printer on floor 3 jams every morning."))
    print(list_requests("ada@example.com"))
