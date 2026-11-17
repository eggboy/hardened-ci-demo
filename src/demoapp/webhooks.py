"""HMAC-SHA256 signature verification for inbound billing webhooks."""

import hashlib
import hmac

SIGNATURE_PREFIX = "sha256="


def compute_signature(signing_key: str, payload: bytes) -> str:
    """Compute the sha256=<hex> HMAC signature for a raw webhook body."""
    digest = hmac.new(signing_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_webhook_signature(signing_key: str, payload: bytes, header_value: str) -> bool:
    """Compare a provided X-Webhook-Signature header against the expected HMAC."""
    expected = compute_signature(signing_key, payload)
    return hmac.compare_digest(expected, header_value.strip())
