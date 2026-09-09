"""Feature preparation and cross-issue continuation through the existing adapters."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import adapters, workflows
from .feature_model import bind_contribution, commit, validate_feature
from .feature_status import assess, write_feature_continuation
from .model import RelayError, now, require
from .storage import new_directory, read_json, write_json


def prepare_feature(project, feature, component, query, author, revision, destination,
                    contract_revision=None, implementations=None):
    validate_feature(feature)
    require(project["repo"] == feature["parent"]["repo"], "Project registry must refer to the feature's parent repository.")
    require(not Path(destination).exists(), "Output directory already exists; choose a new directory.")
    ref = dict(feature["contract"])
    if contract_revision is not None:
        commit(contract_revision)
        ref["revision"] = contract_revision
    if component is not None:
        require(component in feature["components"], "Component is not in feature.json.")
        require(implementations is None, "Component drafts cannot include integration implementations.")
        if revision != "unknown":
            commit(revision)
        target = feature["components"][component]
        collaboration = {"feature_id": feature["id"], "kind": "component", "component": component,
                         "contract": ref, "state": "in_progress", "dependencies": []}
    else:
        require(isinstance(implementations, dict) and set(implementations) == set(feature["components"]),
                "Supply --implementation COMPONENT=SHA for every feature component.")
        for sha in implementations.values():
            commit(sha)
        target = feature["parent"]
        collaboration = {"feature_id": feature["id"], "kind": "integration", "contract": ref,
                         "implementations": implementations, "result": "not_run", "tests": []}
    folder, warnings = workflows.prepare({**project, "repo": target["repo"]}, target["issue"], query,
                                         author, revision, destination)
    bundle = read_json(folder / "context.json")
    bundle["feature"] = feature
    write_json(folder / "context.json", bundle)
    h = read_json(folder / "handoff.json")
    h.update(version=2, collaboration=collaboration)
    write_json(folder / "handoff.json", h)
    with (folder / "PREPARE.md").open("a") as stream:
        stream.write("\nThis is a version 2 feature contribution. Fill collaboration as well as the summary.\n"
                     "Keep contract and implementation revisions pinned. Integration tests need captured evidence.\n")
    return folder, warnings


def read_feature_issue(feature, target):
    snapshot = {"target": target, "issue": None, "handoffs": [], "warnings": [], "complete": False}
    try:
        snapshot["issue"] = adapters.issue(target["repo"], target["issue"])

        def validate_context(h):
            if h["version"] == 2:
                bind_contribution(h, feature)

        records, warnings = workflows.collect_handoffs(adapters.comments(target["repo"], target["issue"]),
                                                       target["repo"], target["issue"], validate_context)
        snapshot.update(handoffs=records, warnings=warnings, complete=not warnings)
        if any(r["handoff"]["version"] == 1 for r in records):
            snapshot["warnings"].append(f"{target['repo']}#{target['issue']}: legacy handoffs have no contract metadata; retained as background.")
    except RelayError as exc:
        snapshot["warnings"].append(f"Could not fully read {target['repo']}#{target['issue']}: {exc}")
    return snapshot


def continue_feature(project, feature, destination, query=None):
    validate_feature(feature)
    require(project["repo"] == feature["parent"]["repo"], "Project registry must refer to the feature's parent repository.")
    require(not Path(destination).exists(), "Output directory already exists; choose a new directory.")
    targets = [feature["parent"], *feature["components"].values()]
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        snapshots = list(pool.map(lambda target: read_feature_issue(feature, target), targets))
    records = [r for snapshot in snapshots for r in snapshot["handoffs"]]
    warnings = [w for snapshot in snapshots for w in snapshot["warnings"]]
    active = [r for r in records if not r["superseded_by"]]
    sources, source_warnings = workflows.retrieve_evidence(active, project["memories"])
    warnings.extend(source_warnings)
    recall = adapters.recall(project["memories"], query) if query else []
    warnings.extend(r["error"] for r in recall if r["error"])
    context = {"version": 1, "mode": "live", "captured_at": now(), "feature": feature,
               "issues": snapshots, "handoffs": records, "evidence": sources, "recall": recall,
               "warnings": warnings, "assessment": assess(feature, records, sources,
                                                           incomplete=any(not s["complete"] for s in snapshots))}
    folder = new_directory(destination)
    write_json(folder / "feature-context.json", context)
    write_feature_continuation(folder, context)
    return folder, warnings

