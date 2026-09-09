# Shared features

Use a shared feature when two or more components depend on the same contract. The component issues may be in different GitHub.com repositories. The parent issue collects integration records.

## Feature file

Create `feature.json` in your project with this structure. The repository names, issues, and repeated SHA below are fictional; replace them with your real coordinates.

```json
{
  "version": 1,
  "id": "list-payments",
  "parent": {"repo": "example/payments", "issue": 200},
  "contract": {
    "repo": "example/payments",
    "path": "api/openapi.yaml",
    "revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "components": {
    "server": {"repo": "example/payments", "issue": 201},
    "client": {"repo": "example/payments-sdk", "issue": 202}
  }
}
```

The definition requires at least two components, each on a distinct issue. `id` and component names use letters, numbers, dots, underscores, or hyphens and start with a letter or number. The contract path is relative to its repository. Contract revisions must be full lowercase Git commit SHAs, 40 or 64 hexadecimal characters. Branch names and abbreviated revisions are rejected because they cannot establish stable equality.

Configure Relay's project registry with the parent repository and the memories accessible to this project. For example:

```sh
relay init --repo example/payments \
  --memory maya=example/maya-feature-memory \
  --memory leo=example/leo-feature-memory
```

The local feature file chooses the target contract. Edit it deliberately when the shared target changes. Contributions may target an older contract revision, which continuation reports as a mismatch. Relay does not resolve or fetch the referenced contract; the receiving agent inspects it with the team's normal repository tools.

## Component contributions

Run `prepare-feature` with the component name, the implementation revision, and a focused retrieval query:

```sh
relay prepare-feature feature.json --component client \
  --revision FULL_CLIENT_COMMIT_SHA --contract-revision FULL_CONTRACT_A_SHA \
  --author Leo --query "client pagination implementation and assumptions" \
  --out .relay/client-contribution
```

`--contract-revision` is optional and defaults to the feature file's target. `--revision` defaults to `unknown`; an `implemented` contribution requires a full commit SHA. In-progress contributions may use `unknown` when no implementation revision exists yet.

Capture source turns with `cite`, then fill the generated handoff. Version 2 retains every [v1 field](handoff-v1.md) and adds a `collaboration` object:

```json
{
  "feature_id": "list-payments",
  "kind": "component",
  "component": "client",
  "contract": {
    "repo": "example/payments",
    "path": "api/openapi.yaml",
    "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "state": "implemented",
  "dependencies": [
    {
      "component": "server",
      "need": "a runnable endpoint with the same contract for integration tests",
      "status": "open"
    }
  ]
}
```

State is `in_progress` or `implemented`. Dependencies name another component in the feature and are `open` or `resolved`. Describe the particular work that depends on it. An integration-testing prerequisite should not imply that all client implementation work is blocked. Relay does not infer dependency resolution from another component's state.

The existing `render` and `publish` commands validate the contribution against the feature definition saved in its preparation bundle. They check the issue target, component identity, contract document, dependency names, and captured evidence. Change a published contribution by preparing a new one and placing the earlier handoff ID in `supersedes` when appropriate.

## Integration records

An integration record is a version 2 handoff on the parent issue. It names every tested component revision and the contract revision. Generate one with:

```sh
relay prepare-integration feature.json \
  --implementation server=FULL_SERVER_COMMIT_SHA \
  --implementation client=FULL_CLIENT_COMMIT_SHA \
  --author Maya --query "list-payments integration test results" \
  --out .relay/integration
```

Supply each component exactly once, with full commit SHAs. `--contract-revision` can record a run against an older contract. Relay creates an empty `not_run` plan; it does not execute tests or invent results.

After running the relevant tests in your development workflow, capture their Funes session turns with `cite`. Fill the summary, next steps, and integration object:

```json
{
  "feature_id": "list-payments",
  "kind": "integration",
  "contract": {
    "repo": "example/payments",
    "path": "api/openapi.yaml",
    "revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "implementations": {
    "server": "1111111111111111111111111111111111111111",
    "client": "3333333333333333333333333333333333333333"
  },
  "result": "passed",
  "tests": [
    {
      "name": "Cursor pagination and authentication against a running server",
      "result": "passed",
      "evidence": ["ID_RETURNED_BY_CITE"]
    }
  ]
}
```

Each test is `not_run`, `passed`, or `failed`. Executed tests require captured evidence. The overall result is `failed` if any test failed, `passed` if a nonempty set of tests all passed, and `not_run` otherwise. Thus `not_run` can also mean a partly executed plan. A fixture-only client test should be named as such and should not be presented as a server/client integration test.

Use `render` to inspect the complete comment and `publish` to post it to the parent issue when authorized. Raw retrieved passages stay local; all summary and collaboration metadata goes into the comment. `supersedes` can replace an earlier integration report from the same GitHub poster, keeping its history available.

## Continue the feature

```sh
relay continue-feature feature.json --out .relay/feature-context
```

Relay reads the parent and component issues, gathers their contributions, and retrieves cited evidence from the configured memories. Add `--query` for an additional cross-memory search. The output includes:

- `FEATURE.md`: component states, contract differences, open dependencies, proposed next steps, and integration status.
- `feature-context.json`: complete revisions, issue bodies, handoffs, test records, source passages, and retrieval warnings.

The assessment uses explicit records, not arrival order or a model's guess:

| Status | Meaning |
| --- | --- |
| `not_verified` | Missing or ambiguous component state, different contract targets, no run for the current revisions, an unfinished test plan, or incomplete issue history |
| `passed_recorded` | A passing report covers the exact selected revisions and target contract, with matching retrieved test evidence |
| `failed_recorded` | A failing report covers that exact combination, with matching retrieved test evidence |
| `conflicting_reports` | Active reports for the same current combination disagree |
| `unverified_evidence` | A matching report exists, but its cited test evidence is missing or different |

Multiple active contributions for one component remain visible and prevent choosing a single implementation revision. Replacing a contribution requires an explicit reference to an earlier handoff in the same feature/component scope, from the same GitHub poster. Cross-author or cross-feature replacement requests do not hide work.

Legacy version 1 handoffs remain readable as background. Relay does not infer contract metadata from their summaries. Inaccessible repositories or invalid feature contributions produce warnings; an incomplete history cannot produce a passing assessment. Other accessible work remains available.

`passed_recorded` describes the reported test scope. It does not establish independent verification, team acceptance, production readiness, or semantic compatibility beyond those tests. Open dependencies remain visible even if an integration test passes. An agent should inspect the present code, referenced contract diff, test scope, and outstanding questions before continuing.

## Versioning

Version 2 comments use `<!-- relay:handoff:v2` and otherwise retain the original readable-comment plus hidden-JSON format. The marker must agree with the JSON version, and the visible comment must match its metadata. Version 1 rendering and parsing remain supported. The feature definition itself uses version 1; its version is independent of the handoff format.

