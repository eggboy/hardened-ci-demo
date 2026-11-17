"""Tenant-scoped SQLite persistence for workspaces, principals, and invoices."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'starter',
    webhook_secret TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member'))
);

CREATE TABLE IF NOT EXISTS api_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    customer_email TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(frozen=True)
class Tenant:
    """A workspace tenant record."""

    id: str
    name: str
    plan: str
    webhook_secret: str


@dataclass(frozen=True)
class Invoice:
    """A tenant-scoped customer invoice."""

    id: int
    tenant_id: str
    customer_email: str
    amount_cents: int
    status: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the invoice into a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "customer_email": self.customer_email,
            "amount_cents": self.amount_cents,
            "status": self.status,
            "notes": self.notes,
        }


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys enabled and close it on exit."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db(path: str) -> None:
    """Create database tables if they do not exist."""
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def create_tenant(path: str, tenant_id: str, name: str, webhook_secret: str, plan: str = "starter") -> Tenant:
    """Insert a tenant workspace and return the created record."""
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO tenants (id, name, plan, webhook_secret) VALUES (?, ?, ?, ?)",
            (tenant_id, name, plan, webhook_secret),
        )
        conn.commit()
    return Tenant(id=tenant_id, name=name, plan=plan, webhook_secret=webhook_secret)


def get_tenant(path: str, tenant_id: str) -> Tenant | None:
    """Fetch a tenant by identifier, or return None when absent."""
    with connect(path) as conn:
        row = conn.execute(
            "SELECT id, name, plan, webhook_secret FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()
    if row is None:
        return None
    return Tenant(
        id=str(row["id"]),
        name=str(row["name"]),
        plan=str(row["plan"]),
        webhook_secret=str(row["webhook_secret"]),
    )


def add_user(path: str, tenant_id: str, name: str, email: str, role: str) -> int:
    """Insert a tenant user with role 'admin' or 'member' and return its ID."""
    with connect(path) as conn:
        cursor = conn.execute(
            "INSERT INTO users (tenant_id, name, email, role) VALUES (?, ?, ?, ?)",
            (tenant_id, name, email, role),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def issue_token(path: str, user_id: int, raw_value: str) -> None:
    """Store the SHA-256 hex digest of an API bearer credential for a user."""
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    with connect(path) as conn:
        conn.execute("INSERT INTO api_tokens (token_hash, user_id) VALUES (?, ?)", (digest, user_id))
        conn.commit()


def get_principal_row_by_token_hash(path: str, token_hash: str) -> tuple[int, str, str] | None:
    """Return (user_id, tenant_id, role) matching a SHA-256 token hash, or None."""
    query = """
        SELECT u.id, u.tenant_id, u.role
        FROM api_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = ?
    """
    with connect(path) as conn:
        row = conn.execute(query, (token_hash,)).fetchone()
    if row is None:
        return None
    return (int(row["id"]), str(row["tenant_id"]), str(row["role"]))


def _row_to_invoice(row: sqlite3.Row) -> Invoice:
    return Invoice(
        id=int(row["id"]),
        tenant_id=str(row["tenant_id"]),
        customer_email=str(row["customer_email"]),
        amount_cents=int(row["amount_cents"]),
        status=str(row["status"]),
        notes=str(row["notes"]),
    )


def create_invoice(
    path: str,
    tenant_id: str,
    customer_email: str,
    amount_cents: int,
    notes: str = "",
) -> Invoice:
    """Insert a new open invoice scoped to a tenant and return it."""
    query = """
        INSERT INTO invoices (tenant_id, customer_email, amount_cents, status, notes)
        VALUES (?, ?, ?, 'open', ?)
    """
    with connect(path) as conn:
        cursor = conn.execute(query, (tenant_id, customer_email, amount_cents, notes))
        conn.commit()
        invoice_id = int(cursor.lastrowid or 0)
    return Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        customer_email=customer_email,
        amount_cents=amount_cents,
        status="open",
        notes=notes,
    )


def list_invoices(path: str, tenant_id: str) -> list[Invoice]:
    """List all invoices belonging to the given tenant ordered by ID."""
    query = """
        SELECT id, tenant_id, customer_email, amount_cents, status, notes
        FROM invoices
        WHERE tenant_id = ?
        ORDER BY id
    """
    with connect(path) as conn:
        rows = conn.execute(query, (tenant_id,)).fetchall()
    return [_row_to_invoice(row) for row in rows]


def get_invoice(path: str, tenant_id: str, invoice_id: int) -> Invoice | None:
    """Fetch a single invoice scoped to both invoice ID and tenant ID."""
    query = """
        SELECT id, tenant_id, customer_email, amount_cents, status, notes
        FROM invoices
        WHERE id = ? AND tenant_id = ?
    """
    with connect(path) as conn:
        row = conn.execute(query, (invoice_id, tenant_id)).fetchone()
    if row is None:
        return None
    return _row_to_invoice(row)


def delete_invoice_by_id(path: str, invoice_id: int) -> bool:
    """Delete an invoice row by ID and return True when a row was deleted."""
    with connect(path) as conn:
        cursor = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        conn.commit()
        return int(cursor.rowcount or 0) > 0


def mark_invoice_status_and_plan(
    path: str,
    tenant_id: str,
    invoice_id: int,
    status: str,
    upgrade_plan: str | None = None,
) -> Invoice | None:
    """Update an invoice status and optionally upgrade the tenant subscription plan."""
    with connect(path) as conn:
        cursor = conn.execute(
            "UPDATE invoices SET status = ? WHERE id = ? AND tenant_id = ?",
            (status, invoice_id, tenant_id),
        )
        if int(cursor.rowcount or 0) == 0:
            return None
        if upgrade_plan:
            conn.execute("UPDATE tenants SET plan = ? WHERE id = ?", (upgrade_plan, tenant_id))
        conn.commit()
    return get_invoice(path, tenant_id, invoice_id)
