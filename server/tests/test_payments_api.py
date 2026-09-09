import http.client
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

from server.payments_api import create_server


ROOT = Path(__file__).resolve().parents[2]


class PaymentsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.payments = [
            {"id": f"pay_{number:03d}", "amount_cents": number * 100, "currency": "USD"}
            for number in [3, 1, 5, 2, 4]
        ]
        self.server = create_server(payments=self.payments)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def get(self, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            self.assertEqual(int(response.getheader("Content-Length")), len(body))
            return response.status, json.loads(body)
        finally:
            connection.close()

    def test_defaults_sort_without_reordering_supplied_list(self):
        original = list(self.payments)
        status, payload = self.get("/payments")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"data": sorted(original, key=lambda p: p["id"])[:2], "next_page": 2})
        self.assertEqual(self.payments, original)
        self.assertIs(self.server.payments, self.payments)

    def test_complete_traversal_and_partial_final_page(self):
        actual = []
        for page, expected_next, count in [(1, 2, 2), (2, 3, 2), (3, None, 1)]:
            status, payload = self.get(f"/payments?page={page}&page_size=2")
            self.assertEqual(status, 200)
            self.assertEqual(payload["next_page"], expected_next)
            self.assertEqual(len(payload["data"]), count)
            actual.extend(payload["data"])
        self.assertEqual(actual, sorted(self.payments, key=lambda p: p["id"]))

    def test_exact_page_boundary_has_no_next_page(self):
        self.payments.pop()
        self.assertEqual(self.get("/payments?page=2")[1]["next_page"], None)

    def test_page_beyond_end_is_empty(self):
        self.assertEqual(self.get("/payments?page=999999"), (200, {"data": [], "next_page": None}))

    def test_empty_supplied_list_stays_empty_and_retained(self):
        self.payments.clear()
        self.assertEqual(self.get("/payments"), (200, {"data": [], "next_page": None}))
        self.assertIs(self.server.payments, self.payments)

    def test_new_empty_list_is_not_replaced_by_default_fixture(self):
        empty = []
        with create_server(payments=empty) as server:
            self.assertIs(server.payments, empty)

    def test_mutation_between_requests_is_visible(self):
        self.get("/payments")
        inserted = {"id": "pay_000", "amount_cents": 0, "currency": "USD"}
        self.payments.append(inserted)
        self.assertEqual(self.get("/payments?page_size=1")[1], {"data": [inserted], "next_page": 2})

    def test_page_size_boundaries(self):
        for size, count, next_page in [(1, 1, 2), (100, 5, None)]:
            with self.subTest(size=size):
                status, payload = self.get(f"/payments?page_size={size}")
                self.assertEqual(status, 200)
                self.assertEqual(len(payload["data"]), count)
                self.assertEqual(payload["next_page"], next_page)

    def test_invalid_parameters_return_json_error(self):
        invalid = ["", "0", "-1", "1.5", "abc", "%20", "1e2", "1&{name}=2"]
        for name in ["page", "page_size"]:
            for value in invalid:
                with self.subTest(name=name, value=value):
                    status, payload = self.get(f"/payments?{name}={value.format(name=name)}")
                    self.assertEqual(status, 400)
                    self.assertIsInstance(payload["error"], str)
                    self.assertTrue(payload["error"])
        self.assertEqual(self.get("/payments?page_size=101")[0], 400)

    def test_unknown_path(self):
        self.assertEqual(self.get("/missing")[0], 404)

    def test_default_fixture(self):
        with create_server() as server:
            self.assertEqual(server.payments, json.loads((ROOT / "fixtures/payments.json").read_text()))


class CommandLineTests(unittest.TestCase):
    def test_cli_serves_custom_fixture_on_assigned_port(self):
        records = [{"id": "custom", "amount_cents": 42, "currency": "EUR"}]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "payments.json"
            fixture.write_text(json.dumps(records), encoding="utf-8")
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "server/payments_api.py"), "--port", "0", "--fixture", str(fixture)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=5), "Server did not announce readiness")
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Listening on http://127.0.0.1:"), line)
                address = urlsplit(line.removeprefix("Listening on "))
                connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
                try:
                    connection.request("GET", "/payments")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read()), {"data": records, "next_page": None})
                finally:
                    connection.close()
            finally:
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
