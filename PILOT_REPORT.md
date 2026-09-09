# Funes Relay pilot

The pilot completed with five passing integration cases and Relay reporting `passed_recorded` for the exact tested revisions.

This pilot uses separate server and client agents to implement a payments feature, then changes the shared API contract and asks the client agent to continue through Relay. The repository is [asutula/funes-relay-test](https://github.com/asutula/funes-relay-test).

## What ran

| Stage | Observed result |
| --- | --- |
| Independent contract A implementations | 12 server tests and 9 client HTTP fixture tests passed. |
| Baseline integration | 4 tests passed against the actual server and client. |
| Insert a record between response pages | The regression failed because numeric pagination returned `pay_002` twice. |
| Server contract B | The server agent changed to cursor pagination and passed 17 tests, including the insertion case. |
| New server with unchanged client | All 5 integration cases failed with HTTP 400. |
| Relay continuation | `not_verified`, with the client's old contract flagged. All 7 retrieved evidence ranges matched; no retrieval warnings. |
| Client assessment before editing | Identified the contract change, recovered its rationale, separated historical test results from current validation, and proposed the required client changes. |
| Adapted client | 11 independent HTTP fixture tests passed. |
| Final integration | All 5 cases passed, including insertion between responses. |
| Final Relay read-back | `passed_recorded`, 6 matched source ranges, no retrieval warnings, contract mismatches, or open dependencies. |

The coordinator introduced the insertion experiment and the new requirement. The server agent then implemented the new contract independently of the client. The client agent received the continuation bundle, inspected the pinned contract diff, and recorded its assessment before changing code. It did not inspect the server implementation or communicate with the server agent.

## Inspect the result

- [Client assessment before editing](client/ADAPTATION_ASSESSMENT.md)
- [Final integration handoff](https://github.com/asutula/funes-relay-test/issues/1#issuecomment-5596656898)
- [Original server contract-change handoff](https://github.com/asutula/funes-relay-test/issues/2#issuecomment-5594571782)
- [Final client handoff](https://github.com/asutula/funes-relay-test/issues/3#issuecomment-5596655919)
- [Compact verification receipts](pilot/results.json)

The server and contract are pinned to `aec4a4e6333bed7938b63b0787e8869f87af025f`; the client is pinned to `d207471e6d1f5dc1fa4b7373feec494f7b9f0836`. Integration ran at merged checkout `6c19308335e8f8943b972666e3c219a4270759cb`. Later documentation commits do not change the tested implementation.

## What Relay contributed

The handoffs connected implementation and contract revisions to decisions and test evidence. The earlier passing integration result remained tied to its original pair of revisions. When the server contract changed, Relay identified that the client targeted an older contract and that integration was unverified.

GitHub held the readable handoffs and their structured metadata. Funes held selected work logs and full test outputs in a private Hugging Face dataset. Relay retrieved source ranges and checked them against the hashes in the handoffs. The client recovered the reason for the change from that context, including the failed insertion experiment and the old client's HTTP 400 responses.

## Limits

This is one controlled feature, with both agents using the same account and machine. It does not establish effectiveness across a larger team, separate permissions, conflicting contributors, or long-running work.

The coordinator exported selected work logs, prepared the summaries, published the handoffs, and ran integration. Automatic capture of complete agent sessions and autonomous handoff publication were not tested. The implementation and tests used Python 3.14.7; Python 3.11 runtime behavior was not tested.

Cursor traversal requires unique immutable IDs. Inserts before the current boundary stay outside that traversal, while later inserts can appear. These tests do not establish snapshot isolation or concurrent mutation safety.

The next product improvement is to reduce the coordinator's manual work: capture a selected contribution, attach the code and contract revisions, cite its test run, and offer a reviewable handoff in one command. The collaboration records already provide the structure for that workflow.
