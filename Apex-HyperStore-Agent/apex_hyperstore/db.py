"""Apex Hyperstore support platform - SQLite data layer.

Everything in this file is synthetic demo data for the fictional company
"Apex Hyperstore". No real customer, order or payment data is present.

The database is created and seeded on first use so the agent works out of the
box. Point APEX_DB_PATH somewhere else to use a different file.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR.parent / "data" / "apex_hyperstore.db"

_INIT_LOCK = threading.Lock()
_INITIALISED: set[str] = set()
_RESOLVED_FALLBACK_PATH: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id    TEXT PRIMARY KEY,
    full_name      TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT NOT NULL,
    city           TEXT NOT NULL,
    loyalty_tier   TEXT NOT NULL,
    loyalty_points INTEGER NOT NULL DEFAULT 0,
    joined_on      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    sku          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    brand        TEXT NOT NULL,
    price_inr    REAL NOT NULL,
    mrp_inr      REAL NOT NULL,
    stock_units  INTEGER NOT NULL,
    warehouse    TEXT NOT NULL,
    aisle        TEXT NOT NULL,
    rating       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL,
    customer_name  TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT NOT NULL,
    placed_at      TEXT NOT NULL,
    status         TEXT NOT NULL,
    delivery_slot  TEXT NOT NULL,
    warehouse      TEXT NOT NULL,
    total_inr      REAL NOT NULL,
    item_count     INTEGER NOT NULL,
    payment_mode   TEXT NOT NULL,
    address        TEXT NOT NULL,
    tracking_note  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id     TEXT NOT NULL,
    sku          TEXT NOT NULL,
    name         TEXT NOT NULL,
    qty          INTEGER NOT NULL,
    unit_price_inr REAL NOT NULL,
    PRIMARY KEY (order_id, sku)
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    kb_id           TEXT PRIMARY KEY,
    topic           TEXT NOT NULL,
    error_code      TEXT NOT NULL,
    surface         TEXT NOT NULL,
    symptom         TEXT NOT NULL,
    cause           TEXT NOT NULL,
    fix_steps       TEXT NOT NULL,
    escalation_team TEXT NOT NULL,
    severity        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_status (
    service    TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    incident   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_requests (
    reference_id     TEXT PRIMARY KEY,
    created_at       TEXT NOT NULL,
    full_name        TEXT NOT NULL,
    email            TEXT NOT NULL,
    phone            TEXT NOT NULL,
    request_type     TEXT NOT NULL,
    urgency          TEXT NOT NULL,
    emergency_type   TEXT NOT NULL,
    scheduled_for    TEXT NOT NULL,
    order_id         TEXT NOT NULL DEFAULT '',
    issue_summary    TEXT NOT NULL,
    channel          TEXT NOT NULL,
    assigned_team    TEXT NOT NULL,
    target_response_at TEXT NOT NULL,
    request_status    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    return_id     TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    email         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    reason        TEXT NOT NULL,
    pickup_slot   TEXT NOT NULL,
    refund_method TEXT NOT NULL,
    amount_inr    REAL NOT NULL,
    status        TEXT NOT NULL
);
"""


def db_path() -> Path:
    global _RESOLVED_FALLBACK_PATH
    if "APEX_DB_PATH" in os.environ:
        return Path(os.environ["APEX_DB_PATH"])
    if _RESOLVED_FALLBACK_PATH is not None:
        return _RESOLVED_FALLBACK_PATH
    return DEFAULT_DB_PATH


def _open_with_schema(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=MEMORY")
    conn.executescript(SCHEMA)
    return conn


def connect() -> sqlite3.Connection:
    """Open a connection with the schema guaranteed to exist (falling back to tempdir if mount rejects locks)."""
    global _RESOLVED_FALLBACK_PATH
    path = db_path()
    try:
        conn = _open_with_schema(path)
    except sqlite3.OperationalError:
        _RESOLVED_FALLBACK_PATH = Path(tempfile.gettempdir()) / "apex_hyperstore" / "apex_hyperstore.db"
        path = _RESOLVED_FALLBACK_PATH
        conn = _open_with_schema(path)
    if str(path) not in _INITIALISED:
        with _INIT_LOCK:
            if str(path) not in _INITIALISED:
                _seed(conn)
                _INITIALISED.add(str(path))
    return conn


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------- seed
def _seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]:
        return  # already seeded

    customers = [
        ("APX-CUS-100241", "Ananya Iyer", "ananya.iyer@example.com", "+919845002241",
         "Bengaluru", "Platinum", 18450, "2019-04-12"),
        ("APX-CUS-100518", "Rohit Malhotra", "rohit.malhotra@example.com", "+919845005518",
         "Pune", "Gold", 6210, "2021-08-03"),
        ("APX-CUS-100773", "Fatima Sheikh", "fatima.sheikh@example.com", "+919845007773",
         "Hyderabad", "Silver", 1480, "2023-01-27"),
        ("APX-CUS-100902", "Daniel Okafor", "daniel.okafor@example.com", "+919845009902",
         "Chennai", "Gold", 7735, "2020-11-19"),
    ]
    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", customers)

    products = [
        ("APX-SKU-100341", "Apex FreshBlend 1200W Mixer Grinder", "Home Appliances", "Apex Home",
         4299.0, 6299.0, 42, "WH-BLR-02", "Aisle 7 / Rack 3", 4.4),
        ("APX-SKU-100512", "Apex PureLife RO Water Purifier", "Home Appliances", "Apex Home",
         11499.0, 14999.0, 8, "WH-BLR-01", "Aisle 7 / Rack 1", 4.6),
        ("APX-SKU-100688", "Apex GlowLED 55\" Smart TV", "Electronics", "Apex Vision",
         27999.0, 38999.0, 5, "WH-BLR-01", "Aisle 2 / Wall 4", 4.2),
        ("APX-SKU-100744", "Apex CloudSoft Memory Foam Mattress (Queen)", "Home & Living", "Apex Sleep",
         8999.0, 12999.0, 17, "WH-PNQ-01", "Aisle 4 / Floor", 4.5),
        ("APX-SKU-100821", "Apex NutriBox Organic Grocery Subscription (Monthly)", "Grocery", "Apex Fresh",
         1249.0, 1499.0, 999, "WH-BLR-03", "Cold Chain", 4.7),
        ("APX-SKU-100937", "Apex SecureCam Wi-Fi Security Camera", "Electronics", "Apex Vision",
         3499.0, 4499.0, 61, "WH-BLR-02", "Aisle 2 / Shelf 9", 4.0),
        ("APX-SKU-101055", "Apex ChefPro 6-Burner Gas Stove", "Kitchen", "Apex Kitchen",
         18999.0, 24499.0, 3, "WH-BLR-02", "Aisle 6 / Rack 2", 4.3),
        ("APX-SKU-101140", "Apex RunFlex Trail Running Shoes", "Sportswear", "Apex Motion",
         3299.0, 4499.0, 74, "WH-PNQ-01", "Aisle 1 / Wall 2", 4.1),
        ("APX-SKU-101268", "Apex ChefPro Induction Cooktop", "Kitchen", "Apex Kitchen",
         9499.0, 12499.0, 0, "WH-BLR-02", "Aisle 6 / Rack 5", 4.5),
    ]
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)", products)

    orders = [
        ("APX-ORD-2026-041882", "APX-CUS-100241", "Ananya Iyer", "ananya.iyer@example.com",
         "+919845002241", "2026-10-12T19:41:00", "out_for_delivery", "2026-10-17T18:00:00 to 21:00",
         "WH-BLR-03", 5548.0, 3, "UPI", "Flat 402, Brigade Sunshine, Whitefield, Bengaluru 560066",
         "Out for delivery with the Apex FreshHub rider; ETA today 18:00-21:00."),
        ("APX-ORD-2026-041905", "APX-CUS-100518", "Rohit Malhotra", "rohit.malhotra@example.com",
         "+919845005518", "2026-10-14T11:07:00", "delivered", "2026-10-16T09:00:00 to 12:00",
         "WH-BLR-02", 4299.0, 1, "Credit Card", "A-903, Silver Oak Residency, Baner, Pune 411045",
         "Delivered. Invoice available in My Orders. Return window closes 2026-10-23."),
        ("APX-ORD-2026-041940", "APX-CUS-100773", "Fatima Sheikh", "fatima.sheikh@example.com",
         "+919845007773", "2026-10-15T21:52:00", "delayed", "2026-10-17T12:00:00 to 15:00",
         "WH-BLR-01", 11499.0, 1, "Net Banking", "H.No 12-3-9, Gachibowli, Hyderabad 500032",
         "Delayed: the pincode serviceability check failed at the Gachibowli hub. Rewarehousing in progress."),
        ("APX-ORD-2026-041988", "APX-CUS-100902", "Daniel Okafor", "daniel.okafor@example.com",
         "+919845009902", "2026-10-16T08:15:00", "payment_captured", "2026-10-19T10:00:00 to 13:00",
         "WH-BLR-01", 27999.0, 1, "Wallet", "12/3, Palm Grove Apartments, Adyar, Chennai 600020",
         "Payment captured, order awaiting stock allocation at WH-BLR-01 (low stock item)."),
    ]
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)

    items = [
        ("APX-ORD-2026-041882", "APX-SKU-100821", "Apex NutriBox Organic Grocery Subscription (Monthly)", 2, 1249.0),
        ("APX-ORD-2026-041882", "APX-SKU-100937", "Apex SecureCam Wi-Fi Security Camera", 1, 3050.0),
        ("APX-ORD-2026-041882", "APX-SKU-100744", "Apex CloudSoft Memory Foam Mattress (Queen)", 0, 0.0),
        ("APX-ORD-2026-041905", "APX-SKU-100341", "Apex FreshBlend 1200W Mixer Grinder", 1, 4299.0),
        ("APX-ORD-2026-041940", "APX-SKU-100512", "Apex PureLife RO Water Purifier", 1, 11499.0),
        ("APX-ORD-2026-041988", "APX-SKU-100688", "Apex GlowLED 55\" Smart TV", 1, 27999.0),
    ]
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", [i for i in items if i[3] > 0])

    kb = [
        ("APX-KB-0101", "Checkout", "APX-4021", "Apex app / website",
         "\"Payment failed (APX-4021)\" at checkout although UPI request was debited.",
         "UPI mandate succeeded at the bank but the payment-gateway callback to Apex timed out, so the order was not created.",
         "1. Ask the customer to check their bank app for a pending mandate and reverse it if present. "
         "2. Retry checkout with the same UPI handle on a new payment attempt. "
         "3. If the debit repeats twice, raise a payment-fraud-safe request with urgency=high and emergency_type=payment_fraud. "
         "4. Never ask the customer to share a UPI PIN, OTP or CVV.",
         "Payments Recovery Desk", "high"),
        ("APX-KB-0102", "Delivery tracking", "APX-4099", "Apex app",
         "Tracking page shows \"Out for delivery\" for more than 24 hours and never updates.",
         "The rider's handheld device lost connectivity in a low-network pincode; the last scan is stale.",
         "1. Pull the order with lookup_order and read its tracking_note. "
         "2. If the slot has passed by more than 24 hours, create a service request of type delivery_delay with urgency=high. "
         "3. Tell the customer a freshridership scan is pushed automatically every 2 hours. "
         "4. Do not promise a refund - refunds are owned by the orders agent.",
         "Last Mile Operations", "high"),
        ("APX-KB-0103", "Account access", "APX-4150", "Apex app",
         "\"Invalid credentials (APX-4150)\" although the customer is sure the password is right.",
         "The account got soft-locked after 5 failed attempts, or OTP is going to a stale phone number.",
         "1. Confirm the email on file with list_customer_orders. "
         "2. Trigger \"Forgot password\" and ask the customer to read the 6-digit OTP to the agent. "
         "3. If the lock persists after a correct OTP, create an account_access request with urgency=normal. "
         "4. Never ask for the password itself and never read back an OTP the customer did not volunteer.",
         "Identity & Accounts Desk", "medium"),
        ("APX-KB-0104", "Returns", "APX-4210", "Apex app / website",
         "\"Return not eligible (APX-4210)\" for an item delivered 15 days ago.",
         "The item is outside the 14-day return window, or the category is non-returnable (perishables, innerwear, already-opened personal care).",
         "1. Read the delivered_at date from lookup_order and explain the 14-day window. "
         "2. Check the product category - grocery/perishables and personal care are non-returnable. "
         "3. If the item is defective, treat it as a product_defect request instead of a return. "
         "4. Escalate to the Quality Desk only when the customer supplies a defect description.",
         "Quality Desk", "medium"),
        ("APX-KB-0105", "Payments", "APX-4305", "Website",
         "Coupon code is rejected with \"APX-4305: coupon not applicable\".",
         "The cart contains a category that is excluded from the coupon, or the coupon expired at 23:59 IST.",
         "1. Check the coupon terms against the cart categories in search_products. "
         "2. Grocery subscriptions and EMI-only items are usually excluded. "
         "3. An expired coupon cannot be reactivated; offer the current running coupon from company_info.",
         "Loyalty & Coupons Desk", "low"),
        ("APX-KB-0106", "Cold chain", "APX-4402", "Apex app",
         "\"Cold chain breach (APX-4402)\" notification on a grocery order.",
         "A FreshHub chiller exceeded 8 C during transit; the batch is auto-quarantined and the order is re-picked.",
         "1. Explain the batch quarantine - it is a safety control, not a billing error. "
         "2. Offer a free re-pick on the next cold-chain slot, or a 100% refund on NutriBox. "
         "3. Create a product_defect request with urgency=high and emergency_type=food_safety if the customer reports illness. "
         "4. Log the batch number the customer quotes.",
         "Cold Chain Assurance", "critical"),
    ]
    conn.executemany("INSERT INTO knowledge_base VALUES (?,?,?,?,?,?,?,?,?)", kb)

    status = [
        ("Checkout & Payments", "degraded", "Elevated UPI callback latency (APX-4021 retries). Started 2026-10-17T06:10:00.",
         "2026-10-17T09:30:00"),
        ("Apex App (Android/iOS)", "operational", "None", "2026-10-17T09:30:00"),
        ("Website", "operational", "None", "2026-10-17T09:30:00"),
        ("Last Mile Delivery", "degraded", "Rider scan gaps on Gachibowli pincode cluster. Started 2026-10-16T22:45:00.",
         "2026-10-17T09:30:00"),
        ("FreshHub Cold Chain", "operational", "None", "2026-10-17T09:30:00"),
    ]
    conn.executemany("INSERT INTO system_status VALUES (?,?,?,?)", status)

    returns = [
        ("APX-RET-2026-0031", "APX-ORD-2026-041905", "rohit.malhotra@example.com", "2026-10-16T16:20:00",
         "Item not as described in the listing", "2026-10-18T10:00:00 to 13:00", "Original payment method",
         4299.0, "pickup_scheduled"),
    ]
    conn.executemany("INSERT INTO returns VALUES (?,?,?,?,?,?,?,?,?)", returns)
    conn.commit()


if __name__ == "__main__":  # `python db.py` prints a quick inventory
    c = connect()
    for t in ("customers", "products", "orders", "knowledge_base", "system_status", "service_requests", "returns"):
        print(f"{t:<16}", c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    print("db file:", db_path())
