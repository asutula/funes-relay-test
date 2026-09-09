import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from relay_cli import adapters, workflows
from relay_cli.demo import ISSUE, REPO, comment, run_demo, sample, save_handoff
from relay_cli.model import RelayError, digest, parse_comment, render, validate
from relay_cli.storage import read_json, write_json


class ContractTests(unittest.TestCase):
    def test_comment_roundtrip_with_marker_in_summary(self):
        h, _ = sample()
        h["summary"] = 'A finding with --> and <!-- relay:handoff:v1\n{}\n--> and `code`.'
        self.assertEqual(parse_comment(render(h)), h)

    def test_visible_edits_are_not_silently_ignored(self):
        h, _ = sample()
        with self.assertRaisesRegex(RelayError, "Visible comment"):
            parse_comment(render(h).replace("### Findings", "### No findings", 1))

    def test_bad_evidence_and_incomplete_drafts_are_rejected(self):
        h, _ = sample()
        mutations = [lambda x: x.update(summary=""),
                     lambda x: x.update(next_steps=[]),
                     lambda x: x["findings"][0].update(evidence=["invented"]),
                     lambda x: x["evidence"][0].update(memory="/tmp/private"),
                     lambda x: x["evidence"][0].update(session="--help"),
                     lambda x: x["evidence"][0].update(to=1000),
                     lambda x: x.update(issue=True),
                     lambda x: x.update(version=True),
                     lambda x: x.update(id=None),
                     lambda x: x.update(extra="field")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(h)
                mutation(candidate)
                with self.assertRaises(RelayError):
                    validate(candidate)

    def test_parallel_handoffs_survive_and_same_poster_can_replace(self):
        maya, _ = sample()
        leo, _ = sample("Leo")
        leo["supersedes"] = [maya["id"]]
        records, warnings = workflows.collect_handoffs([comment(maya, "maya", 1), comment(leo, "leo", 2)], REPO, 142)
        self.assertEqual([r["superseded_by"] for r in records], [[], []])
        self.assertTrue(warnings)
        records, warnings = workflows.collect_handoffs([comment(maya, "maya", 1), comment(leo, "maya", 2)], REPO, 142)
        self.assertEqual(records[0]["superseded_by"], [leo["id"]])
        self.assertFalse(warnings)

    def test_invalid_and_wrong_issue_comments_are_reported(self):
        h, _ = sample()
        h["issue"] = 143
        records, warnings = workflows.collect_handoffs([comment(h, "maya", 1),
            {"body": "<!-- relay:handoff:v1\n{}\n-->", "html_url": "invalid"}], REPO, 142)
        self.assertFalse(records)
        self.assertEqual(len(warnings), 2)

    def test_duplicate_ids_cannot_replace_poster(self):
        h, _ = sample()
        records, warnings = workflows.collect_handoffs([comment(h, "maya", 1), comment(h, "leo", 2)], REPO, 142)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["posted_by"], "maya")
        self.assertTrue(warnings)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.h, self.passage = sample()
        self.project = {"version": 1, "repo": REPO, "memories": {"maya": "example/maya-payments"}}

    def save_live(self):
        folder = self.root / "handoff"
        save_handoff(folder, self.h, {"e-maya": self.passage})
        context = read_json(folder / "context.json")
        context["mode"] = "live"
        write_json(folder / "context.json", context)
        return folder / "handoff.json"

    def test_publish_roundtrip_and_retry_deduplication(self):
        path = self.save_live()
        with patch.object(adapters, "comments", return_value=[]), patch.object(adapters, "post", return_value="comment-url") as post:
            receipt = workflows.publish(path)
            self.assertTrue(receipt["published"])
            self.assertEqual(parse_comment(post.call_args.args[2]), self.h)
            # Raw Funes transcripts do not leave the machine.
            self.assertNotIn(self.passage, post.call_args.args[2])
        with patch.object(adapters, "comments", return_value=[comment(self.h, "maya", 1)]), patch.object(adapters, "post") as post:
            self.assertFalse(workflows.publish(path)["published"])
            post.assert_not_called()

    def test_changed_published_id_is_rejected(self):
        path = self.save_live()
        prior = copy.deepcopy(self.h)
        prior["summary"] = "Earlier summary"
        with patch.object(adapters, "comments", return_value=[comment(prior, "maya", 1)]), patch.object(adapters, "post") as post:
            with self.assertRaisesRegex(RelayError, "different content"):
                workflows.publish(path)
            post.assert_not_called()

    def test_tampered_local_evidence_cannot_publish(self):
        path = self.save_live()
        context = read_json(path.parent / "context.json")
        context["evidence"]["e-maya"]["output"] = "fabricated replacement"
        write_json(path.parent / "context.json", context)
        with patch.object(adapters, "post") as post:
            with self.assertRaisesRegex(RelayError, "snapshot changed"):
                workflows.publish(path)
            post.assert_not_called()

    def test_demo_cannot_publish(self):
        folder = run_demo(self.root / "demo")
        with patch.object(adapters, "post") as post:
            with self.assertRaisesRegex(RelayError, "Demo"):
                workflows.publish(folder / "01-maya/handoff.json")
            post.assert_not_called()
        self.assertEqual(len(read_json(folder / "04-team-continues/continuation.json")["handoffs"]), 2)

    def test_continuation_reports_changed_unavailable_and_disallowed_evidence(self):
        for index, (memories, result, expected) in enumerate([
            (self.project["memories"], "different output", "changed"),
            (self.project["memories"], RelayError("token cannot read dataset"), "unavailable"),
            ({"other": "example/other"}, self.passage, "unavailable")]):
            project = {**self.project, "memories": memories}
            with self.subTest(expected=expected, memories=memories), \
                 patch.object(adapters, "issue", return_value=ISSUE), \
                 patch.object(adapters, "comments", return_value=[comment(self.h, "maya", 1)]), \
                 patch.object(adapters, "evidence", side_effect=result if isinstance(result, Exception) else None,
                              return_value=result) as fetch:
                folder, warnings = workflows.resume(project, 142, self.root / str(index))
                context = read_json(folder / "continuation.json")
                self.assertEqual(next(iter(context["evidence"].values()))["status"], expected)
                self.assertTrue(warnings)
                if memories != self.project["memories"]:
                    fetch.assert_not_called()

    def test_recall_reports_partial_failure(self):
        def response(args):
            if "example/private" in args:
                raise RelayError("access denied")
            return "no results"
        with patch.object(adapters, "run", side_effect=response):
            result = adapters.recall({"ok": "example/ok", "private": "example/private"}, "question")
        self.assertEqual(result[0]["output"], "no results")
        self.assertEqual(result[1]["error"], "access denied")

    def test_all_github_comment_pages_are_read(self):
        with patch.object(adapters, "gh_json", return_value=[[{"id": 1}], [{"id": 2}]]) as api:
            self.assertEqual(adapters.comments(REPO, 142), [{"id": 1}, {"id": 2}])
            self.assertIn("--paginate", api.call_args.args[0])

    def test_missing_and_truncated_funes_ranges_are_rejected(self):
        for output in ("", "no turns in that range of session x", "passage\n9 more turn(s) in range not shown"):
            with patch.object(adapters, "run", return_value=output), self.assertRaises(RelayError):
                adapters.evidence(self.h["evidence"][0])


class ProcessIntegrationTests(unittest.TestCase):
    """Exercise the real CLI and subprocess adapters using fake gh/funes executables."""

    def test_complete_two_person_cli_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            stub = '''#!{python}
import json, os, sys
from pathlib import Path
root = Path(os.environ["RELAY_TEST_STATE"])
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with (root / "calls.jsonl").open("a") as f:
    f.write(json.dumps([tool, *args]) + "\\n")
comments = root / "comments.json"
if tool == "funes":
    if args[0] == "recall":
        print("[2026-09-08] codex payments/session text score=1.0\\n  → get demo-session --from 4 --to 5 --memory example/team\\nRetry test passed.")
    else:
        print("[assistant text seq4] Retry test passed without renewal.\\n---\\nturns 4-5 of 20")
elif args[:2] == ["issue", "view"]:
    print(json.dumps({{"number": 142, "title": "Retry failure", "body": "Investigate retry", "url": "https://github.com/example/payments/issues/142", "updatedAt": "2026-09-08T10:00:00Z"}}))
elif args[0] == "api":
    data = json.loads(comments.read_text()) if comments.exists() else []
    print(json.dumps([data[:1], data[1:]]))
elif args[:2] == ["issue", "comment"]:
    assert args[-2:] == ["--body-file", "-"]
    data = json.loads(comments.read_text()) if comments.exists() else []
    url = "https://github.com/example/payments/issues/142#issuecomment-" + str(len(data)+1)
    data.append({{"body": sys.stdin.read(), "user": {{"login": "maya"}}, "html_url": url, "created_at": "2026-09-08T10:00:00Z", "updated_at": "2026-09-08T10:00:00Z"}})
    comments.write_text(json.dumps(data))
    print(url)
else:
    sys.exit(9)
'''.format(python=sys.executable)
            for name in ("gh", "funes"):
                path = binary / name
                path.write_text(stub)
                path.chmod(0o755)
            env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"], "RELAY_TEST_STATE": str(root)}
            cli = Path(__file__).resolve().parents[1] / "relay.py"

            def call(*args, success=True):
                result = subprocess.run([sys.executable, str(cli), *args], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
                return result.stdout

            call("init", "--repo", REPO, "--memory", "maya=example/team")
            # Shell syntax stays literal through both CLI layers.
            query = "retry $(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_CREATED`"
            call("prepare", "142", "--query", query, "--author", "Maya", "--revision", "abc123", "--out", "maya")
            call("render", "maya/handoff.json", success=False)
            eid = call("cite", "maya", "--memory", "maya", "--session", "demo-session", "--from", "4", "--to", "5").strip()
            handoff_path = root / "maya/handoff.json"
            handoff = read_json(handoff_path)
            handoff.update(summary="Ordinary retry works; renewal is untested.",
                           findings=[{"kind": "observation", "claim": "Retry passed without renewal.", "evidence": [eid]}],
                           questions=["Does renewal change the key?"], next_steps=["Force renewal between attempts."])
            write_json(handoff_path, handoff)
            self.assertEqual(parse_comment(call("render", "maya/handoff.json")), handoff)
            self.assertTrue(json.loads(call("publish", "maya/handoff.json"))["published"])
            self.assertFalse(json.loads(call("publish", "maya/handoff.json"))["published"])
            call("continue", "142", "--out", "leo", "--query", "token renewal")
            continuation = read_json(root / "leo/continuation.json")
            self.assertEqual(continuation["handoffs"][0]["handoff"]["next_steps"], handoff["next_steps"])
            self.assertEqual(next(iter(continuation["evidence"].values()))["status"], "matched")
            self.assertFalse(continuation["warnings"])
            self.assertFalse((root / "SHOULD_NOT_EXIST").exists())
            self.assertFalse((root / "ALSO_NOT_CREATED").exists())
            calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
            self.assertIn(["funes", "recall", query, "--memory", "example/team", "-k", "5"], calls)
            self.assertEqual(sum(args[:3] == ["gh", "issue", "comment"] for args in calls), 1)


if __name__ == "__main__":
    unittest.main()

