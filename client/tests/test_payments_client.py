"""Client tests against a scripted HTTP fixture, not the payments server."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from client.payments_client import list_payments


PAYMENTS = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "payments.json").read_text()
)


@contextmanager
def scripted_api(replies):
    """Serve the supplied replies in sequence and record actual HTTP requests."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if len(requests) > len(replies):
                self.send_error(500, "Unexpected request")
                return
            status, payload = replies[len(requests) - 1]
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ListPaymentsTests(unittest.TestCase):
    def assert_requests(self, requests, pages, page_size):
        self.assertEqual(len(requests), len(pages))
        for request, page in zip(requests, pages):
            parsed = urlsplit(request)
            self.assertEqual(parsed.path, "/payments")
            self.assertEqual(
                parse_qs(parsed.query),
                {"page": [str(page)], "page_size": [str(page_size)]},
            )

    def test_collects_fixture_records_with_default_page_size(self):
        replies = [
            (200, {"data": PAYMENTS[:2], "next_page": 2}),
            (200, {"data": PAYMENTS[2:4], "next_page": 3}),
            (200, {"data": PAYMENTS[4:], "next_page": None}),
        ]
        with scripted_api(replies) as (base_url, requests):
            self.assertEqual(list_payments(base_url), PAYMENTS)
        self.assert_requests(requests, [1, 2, 3], 2)

    def test_follows_explicit_next_page_with_custom_size_and_trailing_slash(self):
        replies = [
            (200, {"data": PAYMENTS[:1], "next_page": 7}),
            (200, {"data": PAYMENTS[1:2], "next_page": None}),
        ]
        with scripted_api(replies) as (base_url, requests):
            self.assertEqual(list_payments(base_url + "/", page_size=1), PAYMENTS[:2])
        self.assert_requests(requests, [1, 7], 1)

    def test_empty_terminal_page(self):
        with scripted_api([(200, {"data": [], "next_page": None})]) as (url, requests):
            self.assertEqual(list_payments(url), [])
        self.assert_requests(requests, [1], 2)

    def test_empty_nonterminal_page_does_not_end_traversal(self):
        replies = [
            (200, {"data": [], "next_page": 2}),
            (200, {"data": PAYMENTS, "next_page": None}),
        ]
        with scripted_api(replies) as (url, requests):
            self.assertEqual(list_payments(url), PAYMENTS)
        self.assert_requests(requests, [1, 2], 2)

    def test_maximum_page_size(self):
        with scripted_api([(200, {"data": PAYMENTS, "next_page": None})]) as (url, requests):
            self.assertEqual(list_payments(url, 100), PAYMENTS)
        self.assert_requests(requests, [1], 100)

    def test_invalid_page_sizes_fail_before_transport(self):
        with patch("client.payments_client.urlopen") as transport:
            for size in [0, -1, 101, 1.5, "2", True, None]:
                with self.subTest(page_size=size), self.assertRaises(ValueError):
                    list_payments("http://unused.invalid", size)
            transport.assert_not_called()

    def test_http_error_propagates_instead_of_returning_partial_results(self):
        replies = [
            (200, {"data": PAYMENTS[:2], "next_page": 2}),
            (400, {"error": "Invalid page"}),
        ]
        with scripted_api(replies) as (url, requests):
            with self.assertRaises(HTTPError) as raised:
                list_payments(url)
            self.assertEqual(raised.exception.code, 400)
            raised.exception.close()
        self.assert_requests(requests, [1, 2], 2)

    def test_rejects_invalid_next_page_without_another_request(self):
        for next_page in [1, 0, -1, True, "2", 1.5, {}]:
            with self.subTest(next_page=next_page):
                with scripted_api([(200, {"data": [], "next_page": next_page})]) as (url, requests):
                    with self.assertRaisesRegex(ValueError, "next_page"):
                        list_payments(url)
                self.assertEqual(len(requests), 1)

    def test_rejects_missing_or_invalid_response_fields(self):
        for payload in [[], {"data": []}, {"data": {}, "next_page": None}]:
            with self.subTest(payload=payload):
                with scripted_api([(200, payload)]) as (url, requests):
                    with self.assertRaises(ValueError):
                        list_payments(url)
                self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
