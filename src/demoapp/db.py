"""SQLite access for the demo service."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
"""


@dataclass(frozen=True)
class User:
    """A row from the users table."""

    id: int
    name: str
    email: str


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection to the SQLite database at ``path`` and close it afterwards."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(path: str) -> None:
    """Create the schema if it doesn't exist."""
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def add_user(path: str, name: str, email: str) -> int:
    """Insert a user and return its id."""
    with connect(path) as conn:
        cursor = conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
        conn.commit()
        return int(cursor.lastrowid or 0)


def get_user(path: str, user_id: int) -> User | None:
    """Return the user with ``user_id``, or ``None`` if it doesn't exist."""
    with connect(path) as conn:
        row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return User(id=row["id"], name=row["name"], email=row["email"])
