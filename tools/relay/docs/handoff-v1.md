# Handoff format v1

Version 1 remains supported for issue handoffs. [Shared-feature contributions](shared-features.md) use version 2, which adds structured collaboration metadata to the fields below.

The authoritative validator is `relay_cli/model.py:validate`. The CLI uses JSON files and embeds the same object in a GitHub issue comment. All fields below are required; unknown fields are rejected.

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Exactly `1` |
| `id` | UUID string | Identity of this contribution; keep unchanged on a publication retry |
| `repo` | string | GitHub `owner/repository` |
| `issue` | positive integer | Target issue number |
| `created_at` | ISO datetime | Creation timestamp with timezone; self-reported |
| `author` | nonempty string | Display attribution; self-reported |
| `revision` | nonempty string | Code revision investigated, or explicit `unknown` |
| `summary` | nonempty string | Current state and scope of the investigation |
| `findings` | array | Claims and supporting evidence, possibly empty |
| `questions` | array of nonempty strings | Remaining uncertainty |
| `next_steps` | nonempty array of nonempty strings | Work the next teammate can perform |
| `evidence` | array | Source references captured through `cite` |
| `supersedes` | array of UUID strings | Earlier handoffs this contribution explicitly replaces |

Each finding contains exactly these fields:

```json
{
  "claim": "The focused retry experiment passed without token renewal.",
  "kind": "observation",
  "evidence": ["e-example"]
}
```

`kind` is `observation` or `hypothesis`. Each finding needs at least one evidence ID that exists in the handoff. Neither kind means the team accepted the claim.

Each evidence reference contains exactly these fields:

```json
{
  "id": "e-example",
  "memory": "acme/maya-payments-memory",
  "session": "c7aa244f-73b7-4548-a6cf-8e104358232d",
  "from": 40,
  "to": 43,
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

This example hash is illustrative. Relay calculates real hashes from the UTF-8 encoded `funes get` output. Turn ranges are inclusive, nonnegative, and limited to 200 turns per citation. Funes must return the requested range without its truncation notice. Memory locations are Hub `owner/dataset` names. Evidence IDs are unique within a handoff.

## GitHub representation

Relay renders a human-readable summary, findings, questions, next steps, and commands for retrieving the evidence. It appends:

```text
<!-- relay:handoff:v1
{the complete handoff JSON object}
-->
```

The encoder escapes `<` inside JSON strings so text cannot end or inject a metadata block. Readers require one block, validate the object, check its repository and issue, and require its rendered body to match the visible comment. Change a handoff by publishing a new contribution, rather than manually editing the generated comment.

GitHub's comment URL and poster login are recorded separately from the self-reported handoff author. The poster can be inspected by the receiving agent. This is attribution through GitHub, not a cryptographic signature.

## Continuation rules

All valid comments remain in the continuation record. A handoff becomes inactive only when a later comment from the same GitHub poster explicitly supersedes it. Cross-author and forward references produce warnings and do not hide earlier work. Handoff IDs with conflicting content or posters produce warnings; Relay retains the first valid occurrence in the API's chronological order.

For each active handoff, Relay retrieves cited sources only when their memory names appear in the local project registry. A source is `matched`, `changed`, or `unavailable`. Hash mismatches are informational and require source inspection; they do not establish that the claim changed. A reference validates provenance coordinates, not the semantics of the attached claim.

This prototype has no `accepted` decision state. An acceptance workflow would need reviewer identity, the approved scope and revision, and separate rules for replacing decisions.
