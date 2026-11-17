"""In-memory response cache with explicit tenant key namespacing."""

from collections.abc import Mapping


def tenant_key(tenant_id: str, resource: str, resource_id: int | str) -> str:
    """Build a cache key namespaced to a specific tenant and resource."""
    return f"{tenant_id}:{resource}:{resource_id}"


class ResponseCache:
    """Shared process-local dictionary cache for serialized payloads."""

    def __init__(self) -> None:
        """Initialize an empty cache store."""
        self._entries: dict[str, dict[str, object]] = {}

    def get(self, key: str) -> dict[str, object] | None:
        """Return a shallow copy of the cached payload for key, or None."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        return dict(entry)

    def set(self, key: str, value: Mapping[str, object]) -> None:
        """Store a shallow copy of value under key."""
        self._entries[key] = dict(value)

    def invalidate(self, key: str) -> None:
        """Remove key from the cache if present."""
        self._entries.pop(key, None)
