"""Outbound HTTPS client for delivering invoice exports to the accounting service."""

import logging
from collections.abc import Mapping
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class AccountingClient:
    """HTTP client authenticated with the service accounting API key."""

    def __init__(self, endpoint_url: str, api_key: str) -> None:
        """Validate that endpoint_url uses HTTPS and store client credentials."""
        parsed = urlparse(endpoint_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Accounting endpoint_url must be a valid https:// URL.")
        self.endpoint_url = endpoint_url
        self.api_key = api_key

    def send_export(self, payload: Mapping[str, object]) -> int:
        """Deliver an export payload to the configured HTTPS accounting endpoint."""
        response = requests.post(
            self.endpoint_url,
            json=dict(payload),
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=5,
        )
        logger.info("Delivered accounting export with HTTP status %s", response.status_code)
        return int(response.status_code)
