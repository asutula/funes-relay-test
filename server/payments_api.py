"""Local payments API using contract B's opaque continuation cursors."""

import argparse
import base64
import binascii
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "payments.json"


def _load_payments(path):
    with Path(path).open(encoding="utf-8") as fixture:
        return json.load(fixture)


def _positive_integer(query, name, default, maximum=None):
    values = query.get(name)
    if values is None:
        return default
    if len(values) != 1 or re.fullmatch(r"[0-9]+", values[0]) is None:
        raise ValueError(f"{name} must be a positive integer")
    value = int(values[0])
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside the allowed range")
    return value


def _encode_cursor(after):
    payload = json.dumps({"v": 1, "after": after}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(query):
    values = query.get("cursor")
    if values is None:
        return None
    if len(values) != 1 or re.fullmatch(r"[A-Za-z0-9_-]+", values[0]) is None:
        raise ValueError("Invalid cursor")
    token = values[0]
    try:
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"v", "after"}
            or type(payload["v"]) is not int
            or payload["v"] != 1
            or not isinstance(payload["after"], str)
            or _encode_cursor(payload["after"]) != token
        ):
            raise ValueError("Invalid cursor")
    except (binascii.Error, UnicodeError, ValueError) as error:
        raise ValueError("Invalid cursor") from error
    return payload["after"]


class PaymentsHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path != "/payments":
            self._send_json(404, {"error": "Not found"})
            return
        query = parse_qs(request.query, keep_blank_values=True)
        try:
            if "page" in query:
                raise ValueError("page is obsolete; use cursor")
            after = _decode_cursor(query)
            page_size = _positive_integer(query, "page_size", 2, maximum=100)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return

        payments = sorted(self.server.payments, key=lambda payment: payment["id"])
        if after is not None:
            payments = [payment for payment in payments if payment["id"] > after]
        data = payments[:page_size]
        self._send_json(200, {
            "data": data,
            "next_cursor": _encode_cursor(data[-1]["id"]) if len(payments) > page_size else None,
        })


def create_server(host="127.0.0.1", port=0, payments=None):
    """Return an unstarted server, retaining a caller-supplied payments list."""
    if payments is None:
        payments = _load_payments(DEFAULT_FIXTURE)
    server = ThreadingHTTPServer((host, port), PaymentsHandler)
    server.payments = payments
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    with create_server(port=args.port, payments=_load_payments(args.fixture)) as server:
        host, port = server.server_address
        print(f"Listening on http://{host}:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
