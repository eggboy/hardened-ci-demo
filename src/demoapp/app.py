"""Flask application factory for the multi-tenant workspace and invoice service."""

import logging

from flask import Flask, abort, jsonify, request
from flask.typing import ResponseReturnValue

from demoapp import auth, db
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

    return app
