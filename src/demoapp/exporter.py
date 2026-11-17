"""Invoice export orchestration across cache, persistence, and accounting delivery."""

import logging

from demoapp import db
from demoapp.auth import Principal
from demoapp.cache import ResponseCache
from demoapp.notifier import AccountingClient

logger = logging.getLogger(__name__)


def export_invoice(
    db_path: str,
    cache: ResponseCache,
    notifier: AccountingClient,
    principal: Principal,
    invoice_id: int,
    destination_url: str | None = None,
) -> dict[str, object] | None:
    """Serialize an invoice and deliver it to the accounting endpoint or override URL."""
    cache_key = f"export:{invoice_id}"
    cached = cache.get(cache_key)
    if cached is None:
        invoice = db.get_invoice(db_path, principal.tenant_id, invoice_id)
        if invoice is None:
            return None
        cached = invoice.to_dict()
        cache.set(cache_key, cached)
    target_url = destination_url or notifier.endpoint_url
    delivery_status = notifier.deliver_to_url(target_url, cached)
    logger.info("Exported invoice %s for user %s", invoice_id, principal.user_id)
    return {"invoice": cached, "delivery_status": delivery_status}
