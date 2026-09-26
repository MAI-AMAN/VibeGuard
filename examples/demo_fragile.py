"""Intentionally fragile demo fixture used to demonstrate real reproduction and repair."""

import json


def parse_retry_after(payload: str) -> int:
    """Parse a retry delay from a service response."""
    data = json.loads(payload)
    retry_after = data.get("retry_after", 0)
    if not isinstance(retry_after, (int, str)):
        raise TypeError("retry_after must be an integer")
    return int(retry_after)
