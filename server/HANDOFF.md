# Server contract B handoff

Based on server contract A commit `875d313e46b667d5846536b69dc3a3ff3a914ab4`. Contract B changes are uncommitted on `pilot/server` for parent review and signing.

## Why the contract changed

Contract B follows the parent-reported insertion experiment against contract A at server revision 875d313e46b667d5846536b69dc3a3ff3a914ab4. The parent reported four passing baseline integration tests, then inserted pay_000 between the first and second requests. Numeric pagination returned pay_001, pay_002, pay_002, pay_003, pay_004, pay_005. This worker did not execute that parent integration experiment. The parent authorized a new stable-traversal requirement beyond contract A's guarantees.

## API changes

Replaced numeric page/next_page with optional opaque cursor/next_cursor. The first request omits cursor. A non-null next_cursor is passed unchanged as cursor; null ends traversal. Each token records the last returned ID and continuation selects IDs strictly greater than it. page_size retains default 2 and range 1..100 and may change between requests. Payment fields, ascending order, CLI, create_server signature, and supplied-list identity stay unchanged. Any page parameter is rejected with JSON 400. Empty, repeated, malformed, unsupported-version, wrong-shape, or noncanonical cursors also return JSON 400. api/openapi.json is now version 2.0.0.

## Guarantees and limits

This is keyset traversal with unique immutable IDs, not full snapshot isolation. Inserts at or before the current ID boundary stay outside this traversal and appear on a fresh traversal. Later inserts can appear. Deletes and payment edits can affect later responses. The trusted payment fixture/list is not schema-validated. Internally tokens are canonical unpadded base64url JSON with version and after fields. They are stateless and unsigned; opacity is a client contract, not encryption or tamper protection. They have no expiry or server-instance binding. Arbitrary well-formed boundaries are accepted. No concurrent mutation stress test or Python 3.11 runtime test ran. No client worktree was read or changed, and no external data was published.

## Validation

The server-only suite passed 17 tests in 8.161s under Python 3.14.7, outside the sandbox so real 127.0.0.1 HTTP sockets could bind on ephemeral ports. The CLI also ran in a separate subprocess and served a temporary custom fixture. Regression coverage reproduces the pay_000 insertion between requests and asserts that all five original records appear exactly once. It also checks fresh traversal visibility, later inserts, deleted boundary IDs, changed page_size, empty results, cursor validation, obsolete page rejection, default fixtures, sorting, list identity, and CLI. Two tests inspect bound server state instead of making an HTTP request. All tests passed with no skips.

Command from the server worktree, with tool escalation for loopback sockets:

```sh
python3 -m unittest discover -s server/tests -v
```

```text
Ran 17 tests in 8.161s

OK
```

The exact shell invocation and complete output are in the final contract-B test entry of `server/evidence.json`.

## Next steps

Parent should review and sign these uncommitted changes, record the resulting implementation and contract revisions in Relay, and let the independent client contributor adapt using shared evidence. Then run both baseline and insertion integration cases against the exact server/client revision pair. The contract-A summary remains in commit 875d313. The parent retained its original execution logs in a separate local evidence export. server/evidence.json exports this contract-B phase only.
