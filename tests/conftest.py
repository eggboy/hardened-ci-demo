"""Shared pytest fixtures seeding two isolated B2B workspace tenants."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from faker import Faker
from flask import Flask
from flask.testing import FlaskClient

from demoapp import db
from demoapp.app import create_app


@dataclass(frozen=True)
class SeededWorld:
    """Seeded multi-tenant database state and test credentials."""

    db_path: str
    alpha_admin_token: str
    alpha_member_token: str
    alpha_invoice_id: int
    alpha_webhook_secret: str
    beta_admin_token: str
    beta_member_token: str
    beta_invoice_id: int
    beta_webhook_secret: str


@pytest.fixture
def faker() -> Faker:
    """Deterministic fake data generator."""
    return Faker(seed=1234)


@pytest.fixture
def seeded_world(tmp_path: Path, faker: Faker) -> SeededWorld:
    """Create two isolated tenants with admin/member tokens and one invoice each."""
    db_path = str(tmp_path / "test.sqlite3")
    db.init_db(db_path)

    alpha_secret = "whsec-alpha-secret-key"
    beta_secret = "whsec-beta-secret-key"
    db.create_tenant(db_path, "tenant-alpha", "Alpha Corp", alpha_secret)
    db.create_tenant(db_path, "tenant-beta", "Beta Industries", beta_secret)

    alpha_admin_id = db.add_user(db_path, "tenant-alpha", faker.name(), faker.unique.email(), "admin")
    alpha_member_id = db.add_user(db_path, "tenant-alpha", faker.name(), faker.unique.email(), "member")
    beta_admin_id = db.add_user(db_path, "tenant-beta", faker.name(), faker.unique.email(), "admin")
    beta_member_id = db.add_user(db_path, "tenant-beta", faker.name(), faker.unique.email(), "member")

    alpha_admin_token = "tok-alpha-admin"
    alpha_member_token = "tok-alpha-member"
    beta_admin_token = "tok-beta-admin"
    beta_member_token = "tok-beta-member"

    db.issue_token(db_path, alpha_admin_id, alpha_admin_token)
    db.issue_token(db_path, alpha_member_id, alpha_member_token)
    db.issue_token(db_path, beta_admin_id, beta_admin_token)
    db.issue_token(db_path, beta_member_id, beta_member_token)

    alpha_invoice = db.create_invoice(
        db_path,
        tenant_id="tenant-alpha",
        customer_email=faker.unique.email(),
        amount_cents=125000,
        notes="Annual enterprise contract",
    )
    beta_invoice = db.create_invoice(
        db_path,
        tenant_id="tenant-beta",
        customer_email=faker.unique.email(),
        amount_cents=45000,
        notes="Quarterly platform renewal",
    )

    return SeededWorld(
        db_path=db_path,
        alpha_admin_token=alpha_admin_token,
        alpha_member_token=alpha_member_token,
        alpha_invoice_id=alpha_invoice.id,
        alpha_webhook_secret=alpha_secret,
        beta_admin_token=beta_admin_token,
        beta_member_token=beta_member_token,
        beta_invoice_id=beta_invoice.id,
        beta_webhook_secret=beta_secret,
    )


@pytest.fixture
def app(seeded_world: SeededWorld) -> Iterator[Flask]:
    """Create a Flask application wired to the seeded multi-tenant SQLite database."""
    application = create_app(
        db_path=seeded_world.db_path,
        accounting_url="https://accounting.internal.example/v1/exports",
        accounting_api_key="acct-live-secret-key",
    )
    yield application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client for the application."""
    return app.test_client()
