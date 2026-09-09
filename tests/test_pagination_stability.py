"""Controlled insertion between actual HTTP requests; no response payloads are mocked."""

from contextlib import contextmanager
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from client import payments_client
from server.payments_api import create_server


class PaginationStabilityTests(unittest.TestCase):
    def test_insert_before_current_position_does_not_repeat_original_records(self):
        payments = json.loads((Path(__file__).parents[1] / "fixtures/payments.json").read_text())
        expected_ids = [payment["id"] for payment in payments]
        server = create_server(host="127.0.0.1", port=0, payments=payments)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        transport = payments_client.urlopen
        requests = []

        @contextmanager
        def insert_between_requests(url, **kwargs):
            with transport(url, **kwargs) as response:
                yield response
            requests.append(url)
            if len(requests) == 1:
                payments.insert(0, {"id": "pay_000", "amount_cents":700, "currency":"USD"})

        try:
            with patch.object(payments_client, "urlopen", side_effect=insert_between_requests):
                result = payments_client.list_payments(f"http://127.0.0.1:{server.server_address[1]}", page_size=2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertGreater(len(requests), 1)
        self.assertEqual([payment["id"] for payment in result], expected_ids)


if __name__ == "__main__":
    unittest.main()
