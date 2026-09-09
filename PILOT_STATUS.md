# Pilot checkpoint

The independent server and client agents implemented contract A in separate worktrees. Their suites passed 12 server tests and 9 client fixture tests. The coordinator then ran 4 passing integration tests against a real local server. That baseline is on `main` at `ce4f928865e02b828198531204f4bb3743cc08f0`.

The next experiment inserted `pay_000` after the first response page. Contract A returned `pay_002` twice. The server agent implemented contract B with cursor pagination and passed 17 server tests, including the insertion case. Its implementation and contract are pinned to `aec4a4e6333bed7938b63b0787e8869f87af025f`.

`pilot/pagination-experiment` currently combines contract B's server with contract A's client. All 5 integration cases fail with HTTP 400 because the client still sends `page`. This is the recorded starting point for the client adaptation phase.

Real local Funes indexing, recall, and source retrieval have succeeded. Shared-memory upload and live Relay handoffs are pending. The next step is to let the client agent recover the changed contract and rationale through Relay, record its assessment before editing, adapt its implementation, and rerun the integration suite.

The memory inputs are selected pilot work logs and test records. This pilot does not test automatic capture of complete agent sessions. A passing final run will establish the behavior covered by these tests; it will not establish general collaboration effectiveness from a single example.

The feature and its component issues are [#1](https://github.com/asutula/funes-relay-test/issues/1), [#2](https://github.com/asutula/funes-relay-test/issues/2), and [#3](https://github.com/asutula/funes-relay-test/issues/3).
