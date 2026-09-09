"""Shared-feature definitions and the collaboration extension to handoffs."""

import html
import re
from pathlib import PurePosixPath

from .model import TOKEN, nonempty, require, validate_repo


def fields(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected.split()), f"Invalid {label} fields.")


def name(value):
    require(isinstance(value, str) and TOKEN.fullmatch(value), "Invalid feature or component ID.")


def commit(value):
    require(isinstance(value, str) and re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", value),
            "Use a full lowercase commit SHA, not a branch name or abbreviated revision.")


def issue_ref(value):
    fields(value, "repo issue", "issue reference")
    validate_repo(value["repo"])
    require(type(value["issue"]) is int and value["issue"] > 0, "Issue must be a positive integer.")


def contract(value):
    fields(value, "repo path revision", "contract reference")
    validate_repo(value["repo"])
    path = value["path"]
    require(nonempty(path) and not path.startswith("/") and "\\" not in path
            and all(part not in {"", ".", ".."} for part in path.split("/"))
            and str(PurePosixPath(path)) == path, "Contract path must be relative to its repository.")
    commit(value["revision"])


def validate_feature(feature):
    fields(feature, "version id parent contract components", "feature")
    require(type(feature["version"]) is int and feature["version"] == 1, "Unsupported feature definition version.")
    name(feature["id"])
    issue_ref(feature["parent"])
    contract(feature["contract"])
    require(isinstance(feature["components"], dict) and len(feature["components"]) >= 2,
            "A shared feature needs at least two components.")
    targets = {(feature["parent"]["repo"], feature["parent"]["issue"])}
    for component, target in feature["components"].items():
        name(component)
        issue_ref(target)
        key = (target["repo"], target["issue"])
        require(key not in targets, "Parent and component issues must be distinct.")
        targets.add(key)
    return feature


def validate_collaboration(value, evidence_ids, revision):
    require(isinstance(value, dict), "collaboration must be an object.")
    kind = value.get("kind")
    common = "feature_id kind contract "
    if kind == "component":
        fields(value, common + "component state dependencies", "component contribution")
        name(value["component"])
        require(value["state"] in ("in_progress", "implemented"), "Invalid component state.")
        if value["state"] == "implemented" or revision != "unknown":
            commit(revision)
        require(isinstance(value["dependencies"], list), "dependencies must be an array.")
        for dependency in value["dependencies"]:
            fields(dependency, "component need status", "dependency")
            name(dependency["component"])
            require(dependency["component"] != value["component"], "Dependencies must name another component.")
            require(nonempty(dependency["need"]), "Describe the dependency.")
            require(dependency["status"] in ("open", "resolved"), "Invalid dependency status.")
    elif kind == "integration":
        fields(value, common + "implementations result tests", "integration record")
        require(isinstance(value["implementations"], dict) and len(value["implementations"]) >= 2,
                "Integration records need at least two implementation revisions.")
        for component, sha in value["implementations"].items():
            name(component)
            commit(sha)
        require(value["result"] in ("not_run", "passed", "failed"), "Invalid integration result.")
        require(isinstance(value["tests"], list), "tests must be an array.")
        results = []
        for test in value["tests"]:
            fields(test, "name result evidence", "integration test")
            require(nonempty(test["name"]), "Name the integration test and its scope.")
            require(test["result"] in ("not_run", "passed", "failed"), "Invalid test result.")
            require(isinstance(test["evidence"], list), "Test evidence must be an array.")
            require(all(isinstance(e, str) and e in evidence_ids for e in test["evidence"]),
                    "Integration test references missing evidence.")
            require(test["result"] == "not_run" or test["evidence"], "Executed tests need captured evidence.")
            results.append(test["result"])
        expected = ("failed" if "failed" in results else
                    "passed" if results and all(r == "passed" for r in results) else "not_run")
        require(value["result"] == expected, "Integration result disagrees with its test results.")
    else:
        require(False, "Contribution kind must be component or integration.")
    name(value["feature_id"])
    contract(value["contract"])


def bind_contribution(handoff, feature):
    """Validate a structurally valid v2 handoff against its feature registry."""
    c = handoff["collaboration"]
    require(c["feature_id"] == feature["id"], "Contribution belongs to another feature.")
    require(all(c["contract"][k] == feature["contract"][k] for k in ("repo", "path")),
            "Contribution refers to a different contract document.")
    if c["kind"] == "component":
        require(c["component"] in feature["components"], "Unknown component in contribution.")
        target = feature["components"][c["component"]]
        require(all(d["component"] in feature["components"] for d in c["dependencies"]),
                "Dependency names an unknown component.")
    else:
        target = feature["parent"]
        require(set(c["implementations"]) == set(feature["components"]),
                "Integration record must name every component in the feature.")
    require(handoff["repo"] == target["repo"] and handoff["issue"] == target["issue"],
            "Contribution is attached to the wrong feature issue.")


def scope(handoff):
    c = handoff.get("collaboration")
    return (c["feature_id"], c["kind"], c.get("component")) if c else ("issue",)


def render_collaboration(c):
    esc = lambda s: html.escape(s, quote=False)
    ref = c["contract"]
    lines = ["", "### Shared feature", "", f"Feature: {esc(c['feature_id'])}",
             f"Contract: {esc(ref['repo'])}/{esc(ref['path'])} at {ref['revision']}", ""]
    if c["kind"] == "component":
        lines.append(f"Component: {c['component']} · State: {c['state']}")
        lines.extend(f"- {d['status']}: needs {d['component']} for {esc(d['need'])}" for d in c["dependencies"])
    else:
        lines.append(f"Integration result reported: {c['result']}")
        lines.extend(f"- {component}: {revision}" for component, revision in sorted(c["implementations"].items()))
        lines.append("")
        lines.extend(f"- {t['result']}: {esc(t['name'])} [{', '.join(t['evidence'])}]" for t in c["tests"])
    return lines

