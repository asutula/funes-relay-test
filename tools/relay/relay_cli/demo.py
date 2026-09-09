"""Authored fixtures illustrating the workflow. No network or model calls."""

from .model import digest, draft, render
from .storage import new_directory, write_json
from .workflows import collect_handoffs, write_continuation


REPO = "example/payments"
ISSUE = {"number": 142, "title": "Intermittent duplicate payment attempts",
         "body": "Some payment retries produce a second attempt after authentication renews.",
         "url": "https://github.com/example/payments/issues/142", "updatedAt": "2026-09-08T10:00:00Z"}


def sample(author="Maya"):
    h = draft(REPO, 142, author, "a1b2c3d")
    h["summary"] = "Ordinary duplicate delivery did not reproduce the failure. The token-renewal path remains untested."
    passage = ("[user text seq40] Test ordinary duplicate delivery against commit a1b2c3d.\n"
               "[assistant text seq41] 100 duplicate deliveries reused the original idempotency key. "
               "No second attempt was created. This test did not renew authentication between attempts.\n"
               "---\nturns 40-41 of 60\n")
    e = {"id": "e-maya", "memory": "example/maya-payments", "session": "demo-maya-session",
         "from": 40, "to": 41, "sha256": digest(passage)}
    h["evidence"] = [e]
    h["findings"] = [{"kind": "observation", "claim": "100 ordinary duplicate deliveries reused one idempotency key; token renewal was not tested.", "evidence": [e["id"]]}]
    h["questions"] = ["Does token renewal preserve the idempotency key?"]
    h["next_steps"] = ["Force token expiration between the initial request and its retry, then compare idempotency keys."]
    return h, passage


def comment(h, poster, number):
    return {"body": render(h), "user": {"login": poster},
            "html_url": f"https://github.com/{REPO}/issues/142#issuecomment-{number}",
            "created_at": f"2026-09-08T{9 + number:02d}:00:00Z", "updated_at": f"2026-09-08T{9 + number:02d}:00:00Z"}


def save_handoff(folder, h, passages):
    folder.mkdir()
    write_json(folder / "handoff.json", h)
    write_json(folder / "context.json", {"version": 1, "mode": "demo", "repo": REPO, "issue": ISSUE,
               "evidence": {e["id"]: {"reference": e, "output": passages[e["id"]]} for e in h["evidence"]}})
    (folder / "handoff.md").write_text(render(h))


def run_demo(destination):
    folder = new_directory(destination)
    maya, maya_passage = sample()
    save_handoff(folder / "01-maya", maya, {"e-maya": maya_passage})
    comments = [comment(maya, "maya", 1)]
    records, warnings = collect_handoffs(comments, REPO, 142)
    continuation = {"version": 1, "mode": "demo", "repo": REPO, "issue": ISSUE,
                    "handoffs": records, "evidence": {"e-maya": {"reference": maya["evidence"][0],
                    "output": maya_passage, "status": "matched", "error": None}}, "recall": [], "warnings": warnings}
    leo_folder = folder / "02-leo-continues"
    leo_folder.mkdir()
    write_json(leo_folder / "continuation.json", continuation)
    write_continuation(leo_folder, continuation)
    leo = draft(REPO, 142, "Leo", "d4e5f6a")
    leo_passage = ("[user text seq12] Expire the token between request and retry.\n"
                   "[assistant text seq13] Reproduced on d4e5f6a: renewal creates key K2 after initial key K1. "
                   "Keeping K1 across renewal prevents the second attempt in this test.\n---\nturns 12-13 of 30\n")
    e = {"id": "e-leo", "memory": "example/leo-payments", "session": "demo-leo-session",
         "from": 12, "to": 13, "sha256": digest(leo_passage)}
    leo.update(summary="The retry after token renewal creates a new idempotency key. A focused reproduction now fails before the patch and passes with it.",
               findings=[{"kind": "observation", "claim": "Renewal creates K2 after initial key K1; retaining K1 prevents the second attempt in the focused reproduction.", "evidence": ["e-leo"]}],
               questions=["Does the same fix cover concurrent renewal across workers?"],
               next_steps=["Review the reproduction and patch on d4e5f6a.", "Test concurrent token renewal before merging."],
               evidence=[e])
    save_handoff(folder / "03-leo", leo, {"e-leo": leo_passage})
    comments.append(comment(leo, "leo", 2))
    records, warnings = collect_handoffs(comments, REPO, 142)
    continuation["handoffs"] = records
    continuation["warnings"] = warnings
    continuation["evidence"]["e-leo"] = {"reference": e, "output": leo_passage, "status": "matched", "error": None}
    team = folder / "04-team-continues"
    team.mkdir()
    write_json(team / "continuation.json", continuation)
    write_continuation(team, continuation)
    write_json(folder / "github-comments.json", comments)
    (folder / "WALKTHROUGH.md").write_text("""# Relay prototype

A teammate's investigation becomes your starting point.

This is a fictional, fully local walkthrough. The people, repository, sessions, findings, and revisions are sample data. No GitHub comments were posted, no Funes datasets were queried, and no model generated these sample summaries.

## 1. Maya leaves a handoff

Maya investigated issue #142, an intermittent duplicate-payment bug. Her tests did not reproduce it with ordinary duplicate delivery. She records the exact limitation: token renewal was never exercised.

Her handoff names the next experiment and cites the session turns that support the finding.

[Read Maya's handoff](01-maya/handoff.md) · [Inspect the editable metadata](01-maya/handoff.json)

## 2. Leo continues the issue

Leo's agent reads the handoff and retrieves its cited turns. It can distinguish "duplicate delivery is impossible" from the narrower result "ordinary duplicate delivery did not reproduce it."

The continuation packet points Leo to the untested token-renewal path.

[Read Leo's starting context](02-leo-continues/CONTINUE.md) · [Inspect the source passages](02-leo-continues/continuation.json)

## 3. Leo contributes new evidence

The focused experiment reproduces the problem. A retry after renewal gets a new idempotency key. Leo's handoff records the reproduction and the remaining concurrency question.

[Read Leo's handoff](03-leo/handoff.md)

## 4. The next teammate sees both contributions

Relay preserves Maya's original test conditions alongside Leo's reproduction. Leo's newer comment does not automatically erase Maya's work or count as an accepted team decision.

[Read the combined continuation](04-team-continues/CONTINUE.md)

## Try the product

The real workflow uses `prepare`, `cite`, `render`, `publish`, and `continue`. Your coding agent writes the summary from evidence; the CLI retrieves, validates, and transports it.

See the project README for the commands and the bundled agent skill. Demo artifacts are marked as demo data and the publish command rejects them.
""")
    return folder

