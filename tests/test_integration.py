"""Exercise the client against the real server over loopback HTTP."""

import json
from pathlib import Path
import threading
import unittest

from client.payments_client import list_payments
from server.payments_api import create_server


class PaymentsIntegrationTests(unittest.TestCase):
    def start_server(self, payments):
        server = create_server(host="127.0.0.1", port=0, payments=payments)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.addCleanup(cleanup)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def fixture(self):
        return json.loads((Path(__file__).parents[1] / "fixtures/payments.json").read_text())

    def test_all_pages(self):
        payments = self.fixture()
        result = list_payments(self.start_server(payments), page_size=2)
        self.assertEqual(result, payments)

    def test_one_item_per_page(self):
        payments = self.fixture()
        self.assertEqual(list_payments(self.start_server(payments), page_size=1), payments)

    def test_single_page(self):
        payments = self.fixture()
        self.assertEqual(list_payments(self.start_server(payments), page_size=100), payments)

    def test_empty_dataset(self):
        self.assertEqual(list_payments(self.start_server([]), page_size=2), [])


if __name__ == "__main__":
    unittest.main()
