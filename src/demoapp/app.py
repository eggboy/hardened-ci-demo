"""Flask application factory for the multi-tenant workspace and invoice service."""

import logging

from flask import Flask, abort, jsonify, request
from flask.typing import ResponseReturnValue

from demoapp import auth, db, exporter, webhooks
from demoapp.cache import ResponseCache, tenant_key
from demoapp.notifier import AccountingClient

logger = logging.getLogger(__name__)


def create_app(
    db_path: str,
    accounting_url: str = "https://accounting.internal.example/v1/exports",
    accounting_api_key: str = "placeholder",
) -> Flask:
    """Create the Flask application backed by SQLite, tenant cache, and accounting client."""
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    db.init_db(db_path)

    cache = ResponseCache()
    notifier = AccountingClient(endpoint_url=accounting_url, api_key=accounting_api_key)
    app.extensions["response_cache"] = cache
    app.extensions["accounting_client"] = notifier

    @app.get("/health")
    def health() -> ResponseReturnValue:
        return jsonify(status="ok")

    @app.get("/invoices")
    def list_tenant_invoices() -> ResponseReturnValue:
        principal = auth.authenticate_request(db_path, request.headers.get("Authorization"))
        invoices = db.list_invoices(db_path, principal.tenant_id)
        return jsonify(invoices=[inv.to_dict() for inv in invoices])

    @app.get("/invoices/<int:invoice_id>")
    def get_tenant_invoice(invoice_id: int) -> ResponseReturnValue:
        principal = auth.authenticate_request(db_path, request.headers.get("Authorization"))
        key = tenant_key(principal.tenant_id, "invoice", invoice_id)
        cached = cache.get(key)
        if cached is not None:
            return jsonify(cached)
        invoice = db.get_invoice(db_path, principal.tenant_id, invoice_id)
        if invoice is None:
            logger.info("Invoice %s not found for tenant %s", invoice_id, principal.tenant_id)
            abort(404)
        payload = invoice.to_dict()
        cache.set(key, payload)
        return jsonify(payload)

    @app.post("/invoices")
    def create_tenant_invoice() -> ResponseReturnValue:
        principal = auth.authenticate_request(db_path, request.headers.get("Authorization"))
        auth.require_admin(principal)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        customer_email = body.get("customer_email")
        amount_cents = body.get("amount_cents")
        notes = body.get("notes", "")
        if not isinstance(customer_email, str) or "@" not in customer_email or len(customer_email) > 254:
            abort(400)
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents < 0:
            abort(400)
        if not isinstance(notes, str) or len(notes) > 2000:
            abort(400)
        invoice = db.create_invoice(
            db_path,
            tenant_id=principal.tenant_id,
            customer_email=customer_email,
            amount_cents=amount_cents,
            notes=notes,
        )
        logger.info("Created invoice %s in tenant %s", invoice.id, principal.tenant_id)
        return jsonify(invoice.to_dict()), 201

    @app.delete("/invoices/<int:invoice_id>")
    def delete_invoice(invoice_id: int) -> ResponseReturnValue:
        auth.authenticate_request(db_path, request.headers.get("Authorization"))
        if not db.delete_invoice_by_id(db_path, invoice_id):
            abort(404)
        return jsonify(deleted=invoice_id)

    @app.post("/invoices/<int:invoice_id>/export")
    def trigger_invoice_export(invoice_id: int) -> ResponseReturnValue:
        principal = auth.authenticate_request(db_path, request.headers.get("Authorization"))
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            abort(400)
        destination_url = body.get("destination_url")
        if destination_url is not None and not isinstance(destination_url, str):
            abort(400)
        result = exporter.export_invoice(
            db_path=db_path,
            cache=cache,
            notifier=notifier,
            principal=principal,
            invoice_id=invoice_id,
            destination_url=destination_url,
        )
        if result is None:
            abort(404)
        return jsonify(result)

    @app.get("/reports/invoices")
    def invoice_audit_report() -> ResponseReturnValue:
        principal = auth.authenticate_request(db_path, request.headers.get("Authorization"))
        target_tenant = request.args.get("tenant_id") or principal.tenant_id
        invoices = db.list_invoices(db_path, target_tenant)
        total_cents = sum(inv.amount_cents for inv in invoices)
        return jsonify(
            tenant_id=target_tenant,
            count=len(invoices),
            total_cents=total_cents,
            invoices=[inv.to_dict() for inv in invoices],
        )

    @app.post("/webhooks/payment")
    def payment_webhook() -> ResponseReturnValue:
        raw_body = request.get_data()
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        tenant_id = body.get("tenant_id")
        invoice_id = body.get("invoice_id")
        status = body.get("status", "paid")
        upgrade_plan = body.get("upgrade_plan")
        if not isinstance(tenant_id, str) or not isinstance(invoice_id, int) or isinstance(invoice_id, bool):
            abort(400)
        if not isinstance(status, str) or (upgrade_plan is not None and not isinstance(upgrade_plan, str)):
            abort(400)
        tenant = db.get_tenant(db_path, tenant_id)
        if tenant is None:
            abort(404)
        sig_header = request.headers.get("X-Webhook-Signature")
        if sig_header and not webhooks.verify_webhook_signature(tenant.webhook_secret, raw_body, sig_header):
            logger.warning("Rejected invalid payment webhook signature for tenant %s", tenant_id)
            abort(401)
        updated = db.mark_invoice_status_and_plan(
            db_path,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            status=status,
            upgrade_plan=upgrade_plan,
        )
        if updated is None:
            abort(404)
        refreshed = db.get_tenant(db_path, tenant_id)
        current_plan = refreshed.plan if refreshed is not None else tenant.plan
        return jsonify(invoice=updated.to_dict(), plan=current_plan)

    return app
