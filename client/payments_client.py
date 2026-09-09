"""Standard-library client for payments API contract B, version 2.0.0."""

import json
from urllib.parse import urlencode
from urllib.request import urlopen


def list_payments(base_url: str, page_size: int = 2) -> list[dict]:
    """Return every page in API order, following opaque ``next_cursor`` values.

    ``base_url`` is the API root, for example ``http://127.0.0.1:8000``.
    HTTP and transport errors propagate to the caller. Invalid pagination
    responses raise ValueError rather than risking an endless traversal.
    """
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("page_size must be an integer between 1 and 100")

    payments = []
    cursor = None
    visited = set()
    while True:
        parameters = {"page_size": page_size}
        if cursor is not None:
            parameters["cursor"] = cursor
        query = urlencode(parameters)
        with urlopen(f"{base_url.rstrip('/')}/payments?{query}", timeout=10) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("payments response must be an object containing a data array")
        if "next_cursor" not in payload:
            raise ValueError("payments response must contain next_cursor")
        payments.extend(payload["data"])
        cursor = payload["next_cursor"]
        if cursor is None:
            return payments
        if not isinstance(cursor, str) or not cursor or cursor in visited:
            raise ValueError("next_cursor must be a nonempty, unvisited string or null")
        visited.add(cursor)
