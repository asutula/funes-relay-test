import base64
import http.client
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode, urlsplit

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

    def continuation(self, cursor, page_size=2):
        return self.get("/payments?" + urlencode({"cursor": cursor, "page_size": page_size}))

    def test_defaults_sort_without_reordering_supplied_list(self):
        original = list(self.payments)
        status, payload = self.get("/payments")
        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"data", "next_cursor"})
        self.assertEqual(payload["data"], sorted(original, key=lambda p: p["id"])[:2])
        self.assertIsInstance(payload["next_cursor"], str)
        self.assertTrue(payload["next_cursor"])
        self.assertEqual(self.payments, original)
        self.assertIs(self.server.payments, self.payments)

    def test_complete_traversal_and_partial_final_page(self):
        status, payload = self.get("/payments")
        actual = []
        for index, count in enumerate([2, 2, 1]):
            self.assertEqual(status, 200)
            self.assertEqual(len(payload["data"]), count)
            actual.extend(payload["data"])
            if index < 2:
                self.assertIsInstance(payload["next_cursor"], str)
                status, payload = self.continuation(payload["next_cursor"])
            else:
                self.assertIsNone(payload["next_cursor"])
        self.assertEqual(actual, sorted(self.payments, key=lambda p: p["id"]))

    def test_exact_page_boundary_has_no_next_cursor(self):
        self.payments.pop()
        first = self.get("/payments")[1]
        final = self.continuation(first["next_cursor"])[1]
        self.assertEqual(len(final["data"]), 2)
        self.assertIsNone(final["next_cursor"])

    def test_no_remaining_records_returns_empty(self):
        first = self.get("/payments")[1]
        self.payments.clear()
        self.assertEqual(self.continuation(first["next_cursor"]), (200, {"data": [], "next_cursor": None}))

    def test_empty_supplied_list_stays_empty_and_retained(self):
        self.payments.clear()
        self.assertEqual(self.get("/payments"), (200, {"data": [], "next_cursor": None}))
        self.assertIs(self.server.payments, self.payments)

    def test_new_empty_list_is_not_replaced_by_default_fixture(self):
        empty = []
        with create_server(payments=empty) as server:
            self.assertIs(server.payments, empty)

    def test_earlier_insertion_does_not_repeat_original_records(self):
        expected = sorted(self.payments, key=lambda p: p["id"])
        status, payload = self.get("/payments")
        self.assertEqual(status, 200)
        actual = list(payload["data"])
        inserted = {"id": "pay_000", "amount_cents": 0, "currency": "USD"}
        self.payments.append(inserted)
        for _ in range(5):
            if payload["next_cursor"] is None:
                break
            status, payload = self.continuation(payload["next_cursor"])
            self.assertEqual(status, 200)
            actual.extend(payload["data"])
        self.assertIsNone(payload["next_cursor"])
        self.assertEqual(actual, expected)
        fresh = self.get("/payments?page_size=1")[1]
        self.assertEqual(fresh["data"], [inserted])

    def test_later_insertions_can_appear_without_snapshot_isolation(self):
        first = self.get("/payments")[1]
        inserted = {"id": "pay_002a", "amount_cents": 7, "currency": "USD"}
        self.payments.append(inserted)
        status, payload = self.continuation(first["next_cursor"])
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"][0], inserted)

    def test_deleted_boundary_record_does_not_invalidate_cursor(self):
        first = self.get("/payments")[1]
        self.payments[:] = [p for p in self.payments if p["id"] != "pay_002"]
        status, payload = self.continuation(first["next_cursor"])
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in payload["data"]], ["pay_003", "pay_004"])

    def test_page_size_can_change_during_traversal(self):
        first = self.get("/payments?page_size=1")[1]
        status, payload = self.continuation(first["next_cursor"], page_size=100)
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in payload["data"]], ["pay_002", "pay_003", "pay_004", "pay_005"])
        self.assertIsNone(payload["next_cursor"])

    def test_page_size_boundaries(self):
        for size, count in [(1, 1), (100, 5)]:
            with self.subTest(size=size):
                status, payload = self.get(f"/payments?page_size={size}")
                self.assertEqual(status, 200)
                self.assertEqual(len(payload["data"]), count)
                self.assertEqual(payload["next_cursor"] is None, size == 100)

    def test_invalid_page_size_returns_json_error(self):
        for value in ["", "0", "-1", "1.5", "abc", "%20", "1e2", "101", "1&page_size=2"]:
            with self.subTest(value=value):
                status, payload = self.get(f"/payments?page_size={value}")
                self.assertEqual(status, 400)
                self.assertIsInstance(payload["error"], str)
                self.assertTrue(payload["error"])

    def test_obsolete_page_parameter_is_rejected(self):
        cursor = self.get("/payments")[1]["next_cursor"]
        for suffix in ["page", "page=", "page=1", "page=2", "page=1&" + urlencode({"cursor": cursor})]:
            with self.subTest(suffix=suffix):
                status, payload = self.get("/payments?" + suffix)
                self.assertEqual(status, 400)
                self.assertIn("page", payload["error"])

    def test_invalid_cursors_return_json_error(self):
        invalid = ["", "!", "a", "abcd", "not-a-cursor"]
        for payload in [None, [], {}, {"v": 2, "after": "pay_002"}, {"v": True, "after": "pay_002"}, {"v": 1, "after": 2}]:
            invalid.append(base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("="))
        for cursor in invalid:
            with self.subTest(cursor=cursor):
                status, payload = self.continuation(cursor)
                self.assertEqual(status, 400)
                self.assertEqual(payload, {"error": "Invalid cursor"})
        valid = self.get("/payments")[1]["next_cursor"]
        status, payload = self.get("/payments?" + urlencode([("cursor", valid), ("cursor", valid)]))
        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "Invalid cursor"})

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
                    self.assertEqual(json.loads(response.read()), {"data": records, "next_cursor": None})
                finally:
                    connection.close()
            finally:
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
