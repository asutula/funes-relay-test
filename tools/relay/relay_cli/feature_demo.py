"""Fictional API and client contributions using the production comparison logic."""

import json

from .feature_model import bind_contribution
from .feature_status import assess, write_feature_continuation
from .model import digest, draft, now, render
from .storage import new_directory, write_json
from .workflows import collect_handoffs


def scenario():
    feature = {"version": 1, "id": "list-payments", "parent": {"repo": "example/payments", "issue": 200},
               "contract": {"repo": "example/payments", "path": "api/openapi.yaml", "revision": "b" * 40},
               "components": {"server": {"repo": "example/payments", "issue": 201},
                              "client": {"repo": "example/payments-sdk", "issue": 202}}}
    sources = {}

    def contribution(label, component, revision, contract_revision, summary):
        target = feature["components"][component] if component else feature["parent"]
        h = draft(target["repo"], target["issue"], "Leo" if component == "client" else "Maya", revision)
        h.update(version=2, summary=summary, next_steps=["Review the contribution and remaining integration work."])
        passage = f"[assistant text seq10] {summary}\n---\nturns 10-10 of 12\n"
        e = {"id": f"e-{label}", "memory": "example/feature-memory", "session": f"demo-{label}",
             "from": 10, "to": 10, "sha256": digest(passage)}
        h["evidence"] = [e]
        h["findings"] = [{"claim": summary, "kind": "observation", "evidence": [e["id"]]}]
        c = {"feature_id": feature["id"], "kind": "component" if component else "integration",
             "contract": {**feature["contract"], "revision": contract_revision}}
        if component:
            c.update(component=component, state="implemented", dependencies=[])
        h["collaboration"] = c
        sources[digest(json.dumps(e, sort_keys=True))] = {"reference": e, "output": passage, "status": "matched", "error": None}
        return h

    server = contribution("server", "server", "1" * 40, "b" * 40,
                          "The list-payments endpoint implements contract B with an opaque next_cursor. Numeric offsets cannot remain stable when new payments arrive.")
    server["next_steps"] = ["Provide the endpoint at server revision 1111111111 for client integration tests."]
    client_a = contribution("client-a", "client", "2" * 40, "a" * 40,
                            "The client implements contract A using numeric page offsets. Its fixture tests pass, but it has not exercised the current server.")
    client_a["collaboration"]["dependencies"] = [{"component": "server", "need": "a runnable endpoint with the same pagination contract for integration tests", "status": "open"}]
    client_a["next_steps"] = ["Inspect the A-to-B contract change and implement opaque cursor handling."]
    client_b = contribution("client-b", "client", "3" * 40, "b" * 40,
                            "The client now targets contract B and follows opaque next_cursor values. Its fixture tests pass. Server/client integration is still pending.")
    client_b["supersedes"] = [client_a["id"]]
    client_b["collaboration"]["dependencies"] = [{"component": "server", "need": "a runnable endpoint with the same pagination contract for integration tests", "status": "resolved"}]
    client_b["next_steps"] = ["Run list-payments pagination and authentication tests against server 1111111111 with client 3333333333."]
    old_run = contribution("old-integration", None, "unknown", "a" * 40,
                           "The earlier server 0000000000 and client 2222222222 passed the contract A pagination test. This result predates the cursor change.")
    new_run = contribution("new-integration", None, "unknown", "b" * 40,
                           "Server 1111111111 and client 3333333333 passed cursor pagination and authentication tests against contract B. Load and rollout testing are outside this run.")
    for h, server_sha, client_sha, title in (
        (old_run, "0" * 40, "2" * 40, "Numeric pagination against a running server"),
        (new_run, "1" * 40, "3" * 40, "Cursor pagination and authentication against a running server")):
        h["collaboration"].update(implementations={"server": server_sha, "client": client_sha}, result="passed",
                                  tests=[{"name": title, "result": "passed", "evidence": [h["evidence"][0]["id"]]}])
    new_run["supersedes"] = [old_run["id"]]
    new_run["next_steps"] = ["Review integration coverage, then plan load testing and rollout."]
    return feature, {"server": server, "client-a": client_a, "client-b": client_b,
                     "old-integration": old_run, "new-integration": new_run}, sources


def comments_for(handoffs):
    result = []
    for index, h in enumerate(handoffs, 1):
        result.append({"body": render(h), "user": {"login": h["author"].lower()},
                       "html_url": f"https://github.com/{h['repo']}/issues/{h['issue']}#issuecomment-{index}",
                       "created_at": f"2026-09-08T10:{index:02d}:00Z", "updated_at": f"2026-09-08T10:{index:02d}:00Z"})
    return result


def demo_context(feature, handoffs, sources):
    records, warnings, snapshots = [], [], []
    for target in [feature["parent"], *feature["components"].values()]:
        relevant = [h for h in handoffs if h["repo"] == target["repo"] and h["issue"] == target["issue"]]
        collected, issues = collect_handoffs(comments_for(relevant), target["repo"], target["issue"],
                                             lambda h: bind_contribution(h, feature))
        records.extend(collected)
        warnings.extend(issues)
        snapshots.append({"target": target, "handoffs": collected, "warnings": issues, "complete": not issues})
    used = {digest(json.dumps(e, sort_keys=True)) for r in records if not r["superseded_by"] for e in r["handoff"]["evidence"]}
    selected_sources = {key: value for key, value in sources.items() if key in used}
    return {"version": 1, "mode": "demo", "captured_at": now(), "feature": feature, "issues": snapshots,
            "handoffs": records, "evidence": selected_sources, "recall": [], "warnings": warnings,
            "assessment": assess(feature, records, selected_sources)}


def run_demo(destination):
    folder = new_directory(destination)
    feature, handoffs, sources = scenario()
    write_json(folder / "feature.json", feature)
    write_json(folder / "project.json", {"version": 1, "repo": feature["parent"]["repo"],
                                        "memories": {"team": "example/feature-memory"}})
    for name, h in handoffs.items():
        directory = folder / "contributions" / name
        directory.mkdir(parents=True)
        write_json(directory / "handoff.json", h)
        evidence = {e["id"]: {"reference": e, "output": sources[digest(json.dumps(e, sort_keys=True))]["output"]} for e in h["evidence"]}
        write_json(directory / "context.json", {"mode": "demo", "repo": h["repo"], "issue": {"number": h["issue"]},
                                                 "feature": feature, "evidence": evidence})
        (directory / "handoff.md").write_text(render(h))
    stages = [("01-contract-mismatch", ["server", "client-a", "old-integration"]),
              ("02-aligned-but-untested", ["server", "client-a", "client-b", "old-integration"]),
              ("03-integration-recorded", list(handoffs))]
    for stage, names in stages:
        directory = folder / stage
        directory.mkdir()
        context = demo_context(feature, [handoffs[n] for n in names], sources)
        write_json(directory / "feature-context.json", context)
        write_feature_continuation(directory, context)
    (folder / "WALKTHROUGH.md").write_text("""# Building an API and its client together

This offline demo uses fictional people, repositories, revisions, and test results. It runs Relay's real contract-comparison and integration-assessment code over authored fixtures. It does not run an API server, execute integration tests, query Funes, or post to GitHub.

The shared feature is list-payments. Maya owns the server in issue #201. Leo owns the client in a separate repository, issue #202. Parent issue #200 tracks the whole feature. The feature file pins the desired API contract to revision B, represented by a full SHA of repeated `b` characters.

[Inspect feature.json](feature.json)

## 1. Both implementations exist, but their contracts differ

The server implements contract B, which uses opaque cursors. The client still targets contract A, which uses numeric offsets. Relay reports the difference and Leo's unresolved integration dependency. An older passing integration result targets an older server and contract A, so it does not verify the current pair.

[Read the mismatch report](01-contract-mismatch/FEATURE.md)

The report points the next agent to the recorded contract references and the server's rationale. The agent would inspect the API diff to determine what the client needs to change. Relay itself detects reference differences; it does not infer API compatibility.

## 2. The client catches up; integration is still unverified

Leo publishes a new contribution for contract B, explicitly replacing his earlier one. Maya's contribution remains active. Both components are now implemented against B and the endpoint dependency is resolved.

Relay still reports `not_verified`. Agreement on a contract does not establish that the client works with the server.

[Read the aligned report](02-aligned-but-untested/FEATURE.md)

## 3. Record a test against the actual pair

Maya records a passing cursor-pagination and authentication test for server `1111111111...`, client `3333333333...`, and contract B. The record cites the test's session turns and replaces the earlier integration result. With matching source output, Relay reports `passed_recorded` for that exact combination.

The report keeps test scope visible. Load testing, team acceptance, and rollout readiness remain separate judgments.

[Read the integration report](03-integration-recorded/FEATURE.md) · [Inspect the integration record](contributions/new-integration/handoff.json)

## Use the workflow on your project

`prepare-feature` creates a component handoff. `prepare-integration` creates a test record on the parent issue. Both use the existing `cite`, `render`, and `publish` commands. `continue-feature` reads the linked issues and prepares the shared context.

See the project README and docs/shared-features.md for live setup. Demo contributions cannot be published.
""")
    return folder
