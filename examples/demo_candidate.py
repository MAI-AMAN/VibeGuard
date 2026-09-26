"""Intentionally fragile demo target; VibeGuard should find, reproduce, and propose its repair."""

import json


def parse_retry_after(payload: str) -> int:
    """Parse a retry delay from a service response without validating missing fields."""
    return int(json.loads(payload)["retry_after"])
