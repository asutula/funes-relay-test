# Before-edit assessment for contract B

Written after reading the live Relay continuation bundle and pinned contract, before changing client implementation or tests.

## Current state

The clean client worktree is at c55d7fa5b278a07504fad4bd52c883d45c5c209d on pilot/client. Its implementation sends page=1, follows numeric next_page, and targets contract A at b5bd91f96ada6f41bb7e6e342a736b83cfdaa7ac. Client handoff 1b35eebb-e0dd-4c18-93d6-c9c96a475bde and evidence e-891e888a796c describe that behavior; the present source agrees.

Relay now targets contract B at aec4a4e6333bed7938b63b0787e8869f87af025f. Server handoff a7aa639f-9b59-40c2-9392-76f4d437b607 reports an implemented server at that revision and supersedes historical server handoff 671b8880-0656-479c-b8dc-96df9065fe69. The client still targets A. Relay reports integration=not_verified, and its seven cited source ranges are matched with no retrieval warnings. These are recorded contributor results, not a new integration run by this worker.

## Changed assumptions and reasons

I obtained the pinned contract with:

```sh
git show aec4a4e6333bed7938b63b0787e8869f87af025f:api/openapi.json
git diff b5bd91f96ada6f41bb7e6e342a736b83cfdaa7ac aec4a4e6333bed7938b63b0787e8869f87af025f -- api/openapi.json
```

Both commands exited 0. Version 2.0.0 removes numeric page and next_page. The first request must omit cursor. Later requests must pass each returned nonempty next_cursor string unchanged as cursor, until null. Sending the obsolete page parameter now returns 400. page_size still defaults to 2 with range 1 through 100. Payment fields and ascending order remain, with unique immutable IDs now explicit. Evidence e-86a5757bc17b in server handoff a7aa639f-9b59-40c2-9392-76f4d437b607 agrees with the pinned diff.

The reason is observable in e-8af431500232. The coordinator's contract A regression inserted pay_000 between requests and returned pay_001, pay_002, pay_002, pay_003, pay_004, pay_005. That test failed once, with duplicate pay_002. This motivated a new traversal guarantee; contract A had not promised stable traversal during insertion. Contract B continues strictly after the last returned ID. Earlier inserts stay outside the current traversal, while later inserts can appear. It does not provide a snapshot.

Evidence e-2dded48b4c68 reports five integration errors when the unchanged client was paired with the B server. Each first request still sent page=1 and received HTTP 400. Therefore retaining numeric pagination, merely renaming the response field, or deduplicating returned payments would not fix compatibility. The client must switch request and response continuation together. It must treat the token as opaque even though the server handoff describes its current encoding.

## Which old results apply

Client evidence e-9c642fcb6702 records nine passing independent HTTP fixture tests on Python 3.14.7 for the A client. The page_size constraints, record aggregation, HTTP error propagation, trailing slash handling, and envelope validation intentions still apply. Numeric request assertions and next_page fixture values do not test B and must change. The old pass is historical evidence, not validation of the edited client.

Integration handoff 1e20273a-daaf-4d49-b6f3-823429f33cf1 with evidence e-20bac44bdfcd records four passing baseline cases for client c55d7fa5b278a07504fad4bd52c883d45c5c209d and server 875d313e46b667d5846536b69dc3a3ff3a914ab4 against contract A. That exact pair passed all-pages, empty-data, page-size-one, and single-page cases. It says nothing about the B pair or insertion stability. Server evidence e-414a40b77fb7 records 17 passing B component tests, including insertion behavior, but those do not establish client compatibility.

## Work needed

1. Preserve list_payments(base_url, page_size=2), the module-level urlopen binding, and response context management. Replace numeric page state with an omitted initial cursor and opaque string continuation. Keep page_size on every request and URL-encode tokens so reserved characters round-trip unchanged.
2. Require data and next_cursor in responses. Stop only on null. Reject empty, non-string, or previously used continuation tokens before another request. Preserve response order and record contents without deduplicating or fabricating cursors.
3. Adapt the independent scripted HTTP fixture tests. Verify exact query fields, initial cursor omission, opaque tokens with reserved characters, complete and empty traversal, page_size limits, HTTP errors, and malformed or cyclic continuation. Keep an explicit old next_page response rejection case.
4. Run real loopback fixture tests with escalation if necessary, record exact commands and full output, then update the handoff and explicit evidence export. Parent will review, sign, merge, and run baseline plus insertion integration against exact B revisions.

## Limits and unresolved questions

This worker has not inspected server implementation or its worktree and will not run server/client integration. The scripted fixture can prove client request and response handling only. Actual prevention of repeated records during insertion depends on the server's strict ID boundary behavior and needs parent integration. Unique immutable IDs are required; inserts before the boundary, deletions, and later mutations do not imply snapshot semantics. The unchanged public function has one fixed page_size per traversal, although B allows varying it between requests. No requirement calls for adding that option. Python 3.11 runtime validation remains outstanding; available python3 was 3.14.7 in phase A. Timeout behavior and full Payment field validation remain outside this adaptation.
