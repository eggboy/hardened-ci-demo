"""Outbound HTTPS client for delivering invoice exports to the accounting service."""

import ipaddress
import logging
from collections.abc import Mapping
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def is_safe_destination_url(destination_url: str, allowed_endpoint: str) -> bool:
    """Validate that destination_url uses HTTPS and matches the allowed endpoint host and port."""
    if not isinstance(destination_url, str) or not destination_url.strip():
        return False
    try:
        parsed = urlparse(destination_url)
        allowed = urlparse(allowed_endpoint)
    except Exception:
        return False

    if parsed.scheme.lower() != "https":
        return False

    if not parsed.netloc or not parsed.hostname:
        return False

    if parsed.username or parsed.password:
        return False

    if parsed.netloc not in (parsed.hostname, f"{parsed.hostname}:{parsed.port}"):
        return False

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        pass

    allowed_hostname = allowed.hostname.rstrip(".").lower() if allowed.hostname else None
    if not allowed_hostname or hostname != allowed_hostname:
        return False

    parsed_port = parsed.port or (443 if parsed.scheme == "https" else None)
    allowed_port = allowed.port or (443 if allowed.scheme == "https" else None)
    if parsed_port != allowed_port:
        return False

    return True


class AccountingClient:
    """HTTP client authenticated with the service accounting API key."""

    def __init__(self, endpoint_url: str, api_key: str) -> None:
        """Validate that endpoint_url uses HTTPS and store client credentials."""
        parsed = urlparse(endpoint_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Accounting endpoint_url must be a valid https:// URL.")
        self.endpoint_url = endpoint_url
        self.api_key = api_key

    def is_safe_destination(self, destination_url: str) -> bool:
        """Verify destination_url is HTTPS and matches the configured endpoint host."""
        return is_safe_destination_url(destination_url, self.endpoint_url)

    def send_export(self, payload: Mapping[str, object]) -> int:
        """Deliver an export payload to the configured HTTPS accounting endpoint."""
        return self.deliver_to_url(self.endpoint_url, payload)

    def deliver_to_url(self, destination_url: str, payload: Mapping[str, object]) -> int:
        """Post an export payload to destination_url with the service API key."""
        if not self.is_safe_destination(destination_url):
            raise ValueError("Destination URL fails SSRF safety validation.")
        response = requests.post(
            destination_url,
            json=dict(payload),
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=5,
        )
        logger.info("Delivered accounting export with HTTP status %s", response.status_code)
        return int(response.status_code)
