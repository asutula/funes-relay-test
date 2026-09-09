# Relay

Continue a teammate's investigation with the evidence and next steps intact.

Relay is a working CLI prototype with an agent skill. It uses Funes to retrieve session history and GitHub issue comments to share handoffs. Your coding agent writes the synthesis. Relay captures sources, validates references, transports the handoff, and retrieves it for the next teammate. Version 0.2 also coordinates related features across repositories through pinned contracts, component dependencies, and integration records.

## Try it without an account

Requires Python 3.11 or newer. The demo and tests have no third-party dependencies.

```sh
python3 relay.py demo --out demo-output
```

Open `demo-output/WALKTHROUGH.md`. The fictional payment investigation follows Maya's initial tests, Leo's continuation, and a combined handoff for the next teammate. Generated `handoff.md` files show the exact GitHub comment format. `handoff.json` files are editable metadata.

The demo uses authored sample findings and session passages. It makes no network or model calls. Its files are marked as demo artifacts, and the publish command rejects them.

## Build a server API and client together

Run the second offline demo:

```sh
python3 relay.py demo-feature --out feature-demo
```

Open `feature-demo/WALKTHROUGH.md`. It shows a server targeting contract B while its client targets A, both implementations catching up to B, and an integration result for the exact server/client pair. An older passing result never verifies a newer pair automatically.

The live workflow adds three commands:

```sh
relay prepare-feature feature.json --component server \
  --revision "$(git rev-parse HEAD)" --author Maya \
  --query "list-payments contract and implementation" --out .relay/server

relay prepare-integration feature.json \
  --implementation server=FULL_SERVER_COMMIT_SHA \
  --implementation client=FULL_CLIENT_COMMIT_SHA \
  --author Maya --query "server client integration results" --out .relay/integration

relay continue-feature feature.json --out .relay/feature-context
```

Replace the SHA placeholders with full lowercase commit hashes. `feature.json` links the parent issue, component issues, and a contract document pinned to a commit. The project registry's repository must match the parent repository; components may live in other GitHub repositories.

`prepare-feature` and `prepare-integration` create version 2 handoffs. Use `cite`, fill their metadata, then `render` and `publish` as with ordinary handoffs. Component contributions go to their component issues. Integration records go to the parent issue.

`continue-feature` prepares `FEATURE.md` and `feature-context.json`, including differing contract targets, unresolved dependencies, proposed next steps, and integration results. It compares references, not the semantic compatibility of API changes. An agent should inspect the referenced contract diff before changing code.

See [shared-feature setup and metadata](docs/shared-features.md) for a complete feature file, dependency fields, test records, and result interpretation.

## The product loop

```text
"Prepare a handoff for #142"
  → read issue + search the project's Funes memories
  → capture relevant session turns
  → agent writes a handoff with evidence and next steps
  → render for review, then publish to the issue

"Pick up #142"
  → read the issue's handoffs
  → retrieve their cited session turns
  → agent checks current code and chooses where to continue
```

There is no hosted service or GitHub App in this version. It uses the locally authenticated `gh` and `funes` executables. The CLI does not call a generative model; the bundled skill supplies the workflow to your existing agent.

## Use it on a real project

Install Funes using its [upstream instructions](https://github.com/huggingface/funes). Install and authenticate the [GitHub CLI](https://cli.github.com/). Teammates need access to the configured, already-published Funes datasets. Relay never uploads agent sessions or calls `funes push`.

You can run the CLI directly with `python3 /absolute/path/to/relay/relay.py`. For a short `relay` command, install this source directory into your own virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps -e .
```

Use the resulting absolute `.venv/bin/relay` path from your project checkout, or activate that environment first. Installation may download setuptools for the build environment; direct execution requires no downloads.

### 1. Register the project memories

Run from the project checkout. Substitute actual repository and dataset names:

```sh
relay init --repo acme/payments \
  --memory maya=acme/maya-payments-memory \
  --memory leo=acme/leo-payments-memory
```

This creates `.relay/project.json`. The aliases route project searches across accessible memories. Each dataset should contain work you intend to expose to this project. Recall searches the configured memories as a whole; Relay does not enforce a repository filter inside them.

To share configuration in source control, keep a registry at a suitable path and use `relay --config team-memory.json COMMAND ...`. Tokens stay in the existing tools' authentication mechanisms, not this registry. Add local `.relay/` bundles to your project's `.gitignore`.

### 2. Prepare context

```sh
relay prepare 142 \
  --query "duplicate payment after token renewal: experiments and results" \
  --author "Maya" \
  --revision "$(git rev-parse HEAD)" \
  --out .relay/handoffs/142-maya
```

Relay fetches the issue and searches every configured memory, with up to four searches at once. It saves the raw results in `context.json` and creates an incomplete `handoff.json`. Failures from individual memories remain visible. An empty search is not evidence that no one investigated the problem.

An output directory must be new. Use a new directory for each contribution.

### 3. Capture sources and write the handoff

Read `PREPARE.md` and `context.json`. Funes recall results include `get` coordinates. Use those real coordinates to capture a source:

```sh
relay cite .relay/handoffs/142-maya \
  --memory maya --session SESSION_ID --from 40 --to 43
```

The command prints an evidence ID such as `e-8e54cc320d8f`. It adds the reference to `handoff.json` and saves the retrieved passage in `context.json`.

Your agent fills the handoff's `summary`, `findings`, `questions`, and `next_steps`. A finding looks like this, using the actual ID returned by `cite`:

```json
{
  "kind": "observation",
  "claim": "100 ordinary duplicate deliveries reused one key; token renewal was not tested.",
  "evidence": ["e-8e54cc320d8f"]
}
```

Use `hypothesis` for an interpretation that still needs testing. Findings require captured evidence. A handoff may have no findings yet, but must have a summary and at least one next step. The supplied revision is a recorded claim; Relay does not verify the checkout or run the experiments.

### 4. Review and publish

```sh
relay render .relay/handoffs/142-maya/handoff.json
relay publish .relay/handoffs/142-maya/handoff.json
```

`render` prints the exact comment after validating the draft and its local evidence snapshots. `publish` posts it to the recorded GitHub issue. This is the only Relay command that writes to GitHub. It sends the summary and all handoff metadata, including memory locations. It does not send the raw source passages. Review the rendered content for the issue's audience.

Publishing checks existing comments for the handoff ID. A sequential retry returns the existing comment; reusing an ID with different content fails. A new revision should be a new handoff. Simultaneous publishers can still race because GitHub issue comments do not offer a unique-key transaction. Relay does not automatically retry a failed or timed-out write.

### 5. Continue from another checkout

Configure the same project memories, then run:

```sh
relay continue 142 --out .relay/continuations/142-leo
```

Read `CONTINUE.md` and `continuation.json`. They contain the current issue, published handoffs, GitHub poster identities, and freshly retrieved source passages. Add `--query "token renewal"` to also search for related work.

The receiving agent should check the current code and tests against the handoff revisions before acting. Relay prepares context; it does not restore a branch or resume another agent's hidden state.

## Agent skill

The skill is at [skills/relay-handoff/SKILL.md](skills/relay-handoff/SKILL.md). Load that file explicitly in your agent, or copy its `relay-handoff` folder into the skill directory your agent uses. Keep the CLI installed and the project registry available in the working directory.

Example request:

> Use the Relay handoff skill in this source folder to prepare a handoff for issue #142. Show me the draft.

The skill covers preparation, citation, publication within the user's authorization, and continuation. No global agent configuration is changed by this prototype.

## Metadata and history

See [the v1 format](docs/handoff-v1.md). A readable comment and a hidden JSON block represent the same handoff. Relay rejects comments whose visible content has diverged from their metadata, so an edited headline or finding cannot silently leave a stale machine-readable account.

Every handoff remains a contributor's account. A newer comment does not count as agreement. Explicit `supersedes` references only replace earlier handoffs in the same scope from the same GitHub poster; other contributions stay active. Feature scopes distinguish each component and the parent integration records. Superseded records remain in the continuation JSON for inspection. Version 1 issue handoffs remain supported.

## Prototype boundaries

- Supports GitHub.com issues and Hub dataset names in `owner/dataset` form. GitHub Enterprise routing, PR event hooks, and local-memory sharing are not implemented.
- No accepted-decision registry, automated conflict resolution, or notifications yet.
- Feature contract references are pinned metadata. Relay does not fetch or diff the contract document, run a server/client pair, or execute the reported tests. A `passed_recorded` result describes the supplied test scope and matching retrieved evidence, not independent certification or rollout approval.
- Source hashes detect output differences, not authenticity or factual correctness. A Funes output-format change or a growing session's footer can also cause a mismatch. Remote memories and GitHub comments can be changed outside Relay.
- Retrieval is limited to configured memory names. A handoff cannot instruct Relay to read a different dataset or a local filesystem path. Missing permissions and changed sources produce warnings while preserving the available context.
- Local bundles contain private retrieved passages. They are created in owner-only directories. They are for the originating agent; share the rendered handoff through the intended issue.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

The 33-test suite covers real CLI subprocess calls against simulated `gh` and `funes` executables, both collaboration workflows, metadata round-trips, partial retrieval failure, missing and altered evidence, comment pagination, retry deduplication, parallel contributions, stale integration results, and conflicting reports. Live GitHub issue and comment reads passed against public `huggingface/funes` issue #144 during the original prototype. Live Funes retrieval and GitHub writes have not been exercised in this workspace.

Integration contracts are based on the [Funes recall documentation](https://github.com/huggingface/funes/blob/main/docs/recall.md), [GitHub issue comment command](https://cli.github.com/manual/gh_issue_comment), and [GitHub API pagination](https://cli.github.com/manual/gh_api).
