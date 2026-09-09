"""Standard-library client for payments API contract A, version 1.0.0."""

import json
from urllib.parse import urlencode
from urllib.request import urlopen


def list_payments(base_url: str, page_size: int = 2) -> list[dict]:
    """Return every page in API order, following numeric ``next_page`` values.

    ``base_url`` is the API root, for example ``http://127.0.0.1:8000``.
    HTTP and transport errors propagate to the caller. Invalid pagination
    responses raise ValueError rather than risking an endless traversal.
    """
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("page_size must be an integer between 1 and 100")

    payments = []
    page = 1
    visited = set()
    while page is not None:
        if type(page) is not int or page < 1 or page in visited:
            raise ValueError("next_page must be a positive, unvisited integer or null")
        visited.add(page)
        query = urlencode({"page": page, "page_size": page_size})
        with urlopen(f"{base_url.rstrip('/')}/payments?{query}", timeout=10) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("payments response must be an object containing a data array")
        if "next_page" not in payload:
            raise ValueError("payments response must contain next_page")
        payments.extend(payload["data"])
        page = payload["next_page"]
    return payments
