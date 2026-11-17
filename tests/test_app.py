"""HTTP integration tests for tenant isolation, RBAC, exports, reports, and webhooks."""

import json
from dataclasses import dataclass

import pytest
import requests
from faker import Faker
from flask.testing import FlaskClient

from conftest import SeededWorld
from demoapp import webhooks


@dataclass(frozen=True)
class _StubResponse:
    status_code: int


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@pytest.mark.parametrize(
    "header_value",
    [None, "", "Basic dXNlcjpwYXNz", "Bearer ", "Bearer unknown-token"],
)
def test_invoices_reject_missing_or_invalid_tokens(client: FlaskClient, header_value: str | None) -> None:
    headers = {"Authorization": header_value} if header_value is not None else {}
    response = client.get("/invoices", headers=headers)
    assert response.status_code == 401


def test_list_invoices_is_scoped_to_caller_tenant(client: FlaskClient, seeded_world: SeededWorld) -> None:
    response = client.get("/invoices", headers=_auth_headers(seeded_world.alpha_member_token))
    assert response.status_code == 200
    invoices = response.get_json()["invoices"]
    assert len(invoices) == 1
    assert invoices[0]["id"] == seeded_world.alpha_invoice_id
    assert invoices[0]["tenant_id"] == "tenant-alpha"


def test_get_invoice_enforces_cross_tenant_isolation(client: FlaskClient, seeded_world: SeededWorld) -> None:
    own = client.get(
        f"/invoices/{seeded_world.alpha_invoice_id}",
        headers=_auth_headers(seeded_world.alpha_member_token),
    )
    assert own.status_code == 200
    assert own.get_json()["id"] == seeded_world.alpha_invoice_id

    cross_tenant = client.get(
        f"/invoices/{seeded_world.alpha_invoice_id}",
        headers=_auth_headers(seeded_world.beta_admin_token),
    )
    assert cross_tenant.status_code == 404


def test_member_cannot_create_invoice(client: FlaskClient, seeded_world: SeededWorld, faker: Faker) -> None:
    response = client.post(
        "/invoices",
        headers=_auth_headers(seeded_world.alpha_member_token),
        json={"customer_email": faker.email(), "amount_cents": 9900, "notes": "Attempted by member"},
    )
    assert response.status_code == 403


def test_admin_can_create_invoice_in_own_tenant(
    client: FlaskClient,
    seeded_world: SeededWorld,
    faker: Faker,
) -> None:
    email = faker.email()
    response = client.post(
        "/invoices",
        headers=_auth_headers(seeded_world.alpha_admin_token),
        json={"customer_email": email, "amount_cents": 25000, "notes": "Seat expansion"},
    )
    assert response.status_code == 201
    created = response.get_json()
    assert created["tenant_id"] == "tenant-alpha"
    assert created["customer_email"] == email
    assert created["amount_cents"] == 25000
    assert created["status"] == "open"


def test_invoice_audit_report_summarizes_tenant_totals(
    client: FlaskClient,
    seeded_world: SeededWorld,
) -> None:
    response = client.get("/reports/invoices", headers=_auth_headers(seeded_world.alpha_admin_token))
    assert response.status_code == 200
    report = response.get_json()
    assert report["tenant_id"] == "tenant-alpha"
    assert report["count"] == 1
    assert report["total_cents"] == 125000


def test_export_invoice_delivers_payload(
    client: FlaskClient,
    seeded_world: SeededWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, object, object]] = []

    def fake_post(url: str, **kwargs: object) -> _StubResponse:
        captured.append((url, kwargs.get("json"), kwargs.get("headers")))
        return _StubResponse(status_code=202)

    monkeypatch.setattr(requests, "post", fake_post)
    response = client.post(
        f"/invoices/{seeded_world.alpha_invoice_id}/export",
        headers=_auth_headers(seeded_world.alpha_admin_token),
        json={},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["delivery_status"] == 202
    assert body["invoice"]["id"] == seeded_world.alpha_invoice_id
    assert len(captured) == 1
    assert captured[0][0] == "https://accounting.internal.example/v1/exports"


def test_delete_invoice_removes_record(client: FlaskClient, seeded_world: SeededWorld) -> None:
    response = client.delete(
        f"/invoices/{seeded_world.alpha_invoice_id}",
        headers=_auth_headers(seeded_world.alpha_admin_token),
    )
    assert response.status_code == 200
    assert response.get_json() == {"deleted": seeded_world.alpha_invoice_id}


def test_payment_webhook_accepts_valid_signature_and_rejects_bad_signature(
    client: FlaskClient,
    seeded_world: SeededWorld,
) -> None:
    event = {
        "tenant_id": "tenant-alpha",
        "invoice_id": seeded_world.alpha_invoice_id,
        "status": "paid",
        "upgrade_plan": "enterprise",
    }
    payload_bytes = json.dumps(event).encode("utf-8")

    bad_response = client.post(
        "/webhooks/payment",
        data=payload_bytes,
        content_type="application/json",
        headers={"X-Webhook-Signature": "sha256=bad"},
    )
    assert bad_response.status_code == 401

    valid_sig = webhooks.compute_signature(seeded_world.alpha_webhook_secret, payload_bytes)
    good_response = client.post(
        "/webhooks/payment",
        data=payload_bytes,
        content_type="application/json",
        headers={"X-Webhook-Signature": valid_sig},
    )
    assert good_response.status_code == 200
    result = good_response.get_json()
    assert result["invoice"]["status"] == "paid"
    assert result["plan"] == "enterprise"
