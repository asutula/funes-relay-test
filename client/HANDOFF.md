# Client contract A

Implemented api/openapi.json at b5bd91f96ada6f41bb7e6e342a736b83cfdaa7ac. list_payments follows numeric next_page values, combines responses, propagates HTTP errors, and rejects repeated or invalid continuation values.

Validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s client/tests -v` passed nine tests on Python 3.14.7 against an independent HTTP fixture. Tests cover full traversal, explicit continuation values, empty responses, page sizes, errors, and malformed envelopes. The initial sandbox run could not bind sockets; the authorized rerun passed. Exact execution logs are retained in the pilot's local evidence export for Funes indexing.

The client agent did not read the server implementation or run real server/client integration. Fixture tests establish client behavior against scripted responses. The client preserves returned records without deduplicating them; no snapshot semantics are promised by contract A.

Next: run baseline integration and the insertion-between-requests experiment. Use shared-feature context before adapting to any later contract.
