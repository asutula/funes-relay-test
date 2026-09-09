"""Versioned handoffs and their GitHub comment representation."""

import hashlib
import html
import json
import re
import shlex
from datetime import datetime, timezone
from uuid import UUID, uuid4


class RelayError(Exception):
    pass


REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
MARKER = re.compile(r"<!-- relay:handoff:v([12])\n(.*?)\n-->", re.DOTALL)


def require(condition, message):
    if not condition:
        raise RelayError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_repo(repo):
    require(isinstance(repo, str) and REPO.fullmatch(repo), "Repository must be owner/name.")
    require(all(part not in {".", ".."} for part in repo.split("/")), "Invalid repository.")


def validate_memory(memory):
    # Team configuration accepts Hub dataset names, never local filesystem paths.
    validate_repo(memory)
    require(not memory.startswith((".", "-")), "Memory must be a Hub owner/dataset name.")


def validate(h):
    require(isinstance(h, dict), "Handoff must be an object.")
    require(type(h.get("version")) is int and h["version"] in (1, 2), "Unsupported handoff version.")
    fields = {"version", "id", "repo", "issue", "created_at", "author", "revision",
              "summary", "findings", "questions", "next_steps", "evidence", "supersedes"}
    if h["version"] == 2:
        fields.add("collaboration")
    require(set(h) == fields, f"Handoff fields must be: {', '.join(sorted(fields))}.")
    try:
        UUID(h["id"])
        timestamp = datetime.fromisoformat(h["created_at"])
        require(timestamp.tzinfo is not None, "created_at needs a timezone.")
    except (ValueError, TypeError, AttributeError):
        raise RelayError("Invalid handoff ID or timestamp.") from None
    validate_repo(h["repo"])
    require(type(h["issue"]) is int and h["issue"] > 0, "Issue must be a positive integer.")
    for key in ("author", "revision", "summary"):
        require(nonempty(h[key]), f"Fill in {key} before rendering or publishing.")
    for key in ("findings", "questions", "next_steps", "evidence", "supersedes"):
        require(isinstance(h[key], list), f"{key} must be an array.")
    require(h["next_steps"], "Include at least one next step.")
    for key in ("questions", "next_steps", "supersedes"):
        require(all(nonempty(x) for x in h[key]), f"{key} must contain nonempty strings.")
    for predecessor in h["supersedes"]:
        try:
            UUID(predecessor)
        except (ValueError, TypeError, AttributeError):
            raise RelayError("supersedes must contain handoff UUIDs.") from None
        require(predecessor != h["id"], "A handoff cannot supersede itself.")
    ids = set()
    for e in h["evidence"]:
        require(isinstance(e, dict) and set(e) == {"id", "memory", "session", "from", "to", "sha256"},
                "Invalid evidence fields.")
        require(isinstance(e["id"], str) and TOKEN.fullmatch(e["id"]), "Invalid evidence ID.")
        require(e["id"] not in ids, "Duplicate evidence ID.")
        ids.add(e["id"])
        validate_memory(e["memory"])
        require(isinstance(e["session"], str) and TOKEN.fullmatch(e["session"]), "Invalid session ID.")
        require(type(e["from"]) is int and type(e["to"]) is int
                and 0 <= e["from"] <= e["to"] and e["to"] - e["from"] < 200,
                "Evidence ranges must cover 1 to 200 turns.")
        require(isinstance(e["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", e["sha256"]),
                "Invalid evidence hash.")
    for f in h["findings"]:
        require(isinstance(f, dict) and set(f) == {"claim", "kind", "evidence"}, "Invalid finding fields.")
        require(nonempty(f["claim"]), "Finding claims cannot be empty.")
        require(f["kind"] in ("observation", "hypothesis"), "Finding kind must be observation or hypothesis.")
        require(isinstance(f["evidence"], list) and f["evidence"], "Every finding needs evidence.")
        require(all(isinstance(ref, str) and ref in ids for ref in f["evidence"]),
                "Finding references missing evidence.")
    if h["version"] == 2:
        from .feature_model import validate_collaboration
        validate_collaboration(h["collaboration"], ids, h["revision"])
    return h


def draft(repo, issue, author, revision):
    return {"version": 1, "id": str(uuid4()), "repo": repo, "issue": issue,
            "created_at": now(), "author": author, "revision": revision, "summary": "",
            "findings": [], "questions": [], "next_steps": [], "evidence": [], "supersedes": []}


def get_command(e):
    return ["funes", "get", e["session"], "--from", str(e["from"]),
            "--to", str(e["to"]), "--memory", e["memory"]]


def render(h):
    validate(h)
    escape = lambda s: html.escape(s, quote=False)
    lines = [f"## Handoff for #{h['issue']}", "",
             f"Prepared by {escape(h['author'])} · Code revision: {escape(h['revision'])}",
             "", escape(h["summary"]), "", "### Findings", ""]
    for f in h["findings"]:
        lines.append(f"- **{f['kind'].capitalize()}**: {escape(f['claim'])} [{', '.join(f['evidence'])}]")
    if not h["findings"]:
        lines.append("No evidence-backed findings recorded yet.")
    for title, key in (("Open questions", "questions"), ("Next steps", "next_steps")):
        lines.extend(["", f"### {title}", ""])
        lines.extend(f"- {escape(x)}" for x in h[key])
        if not h[key]:
            lines.append("None recorded.")
    if h["supersedes"]:
        lines.extend(["", "Replaces handoffs: " + ", ".join(h["supersedes"])])
    if h["version"] == 2:
        from .feature_model import render_collaboration
        lines.extend(render_collaboration(h["collaboration"]))
    lines.extend(["", "### Evidence", "", "Sources require access to the named Funes memories.", ""])
    for e in h["evidence"]:
        lines.extend([f"**{e['id']}**", "", "```sh", shlex.join(get_command(e)), "```", ""])
    payload = json.dumps(h, ensure_ascii=True, sort_keys=True, indent=2).replace("<", "\\u003c")
    lines.extend([f"<!-- relay:handoff:v{h['version']}", payload, "-->", ""])
    result = "\n".join(lines)
    require(len(result.encode("utf-8")) <= 60000, "Handoff exceeds Relay's 60 KB comment limit.")
    return result


def parse_comment(body):
    matches = MARKER.findall(body)
    require(len(matches) == 1, "Expected exactly one Relay handoff block.")
    try:
        handoff = validate(json.loads(matches[0][1]))
    except json.JSONDecodeError:
        raise RelayError("Invalid handoff JSON in comment.") from None
    require(int(matches[0][0]) == handoff["version"], "Comment marker and handoff version disagree.")
    require(body.strip() == render(handoff).strip(), "Visible comment differs from its handoff metadata.")
    return handoff
