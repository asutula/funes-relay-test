import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from relay_cli import adapters, features, workflows
from relay_cli.feature_demo import comments_for, demo_context, run_demo, scenario
from relay_cli.feature_model import validate_feature
from relay_cli.feature_status import assess
from relay_cli.model import RelayError, parse_comment, render, validate
from relay_cli.storage import read_json, write_json


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.feature, self.handoffs, self.sources = scenario()

    def context(self, *names):
        return demo_context(self.feature, [self.handoffs[n] for n in names], self.sources)

    def test_feature_rejects_moving_refs_duplicate_issues_and_bad_paths(self):
        mutations = [lambda f: f["contract"].update(revision="main"),
                     lambda f: f["contract"].update(path="../private.yaml"),
                     lambda f: f["components"].update(client=f["parent"]),
                     lambda f: f["components"].update(client=f["components"]["server"]),
                     lambda f: f.update(version=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                feature = copy.deepcopy(self.feature)
                mutate(feature)
                with self.assertRaises(RelayError):
                    validate_feature(feature)

    def test_v2_component_and_integration_roundtrip(self):
        for h in self.handoffs.values():
            with self.subTest(kind=h["collaboration"]["kind"]):
                self.assertEqual(parse_comment(render(h)), h)
                with self.assertRaisesRegex(RelayError, "version disagree"):
                    parse_comment(render(h).replace("<!-- relay:handoff:v2", "<!-- relay:handoff:v1"))

    def test_integration_requires_consistent_tests_and_evidence(self):
        mutations = [lambda h: h["collaboration"].update(tests=[]),
                     lambda h: h["collaboration"]["tests"][0].update(evidence=[]),
                     lambda h: h["collaboration"]["tests"][0].update(evidence=["invented"]),
                     lambda h: h["collaboration"]["tests"][0].update(result="failed"),
                     lambda h: h["collaboration"]["implementations"].update(server="main")]
        for mutate in mutations:
            h = copy.deepcopy(self.handoffs["new-integration"])
            mutate(h)
            with self.assertRaises(RelayError):
                validate(h)

    def test_implemented_component_requires_immutable_revision(self):
        h = self.handoffs["server"]
        h["revision"] = "unknown"
        with self.assertRaises(RelayError):
            validate(h)

    def test_old_passing_result_does_not_verify_new_contract(self):
        c = self.context("server", "client-a", "old-integration")
        self.assertEqual(c["assessment"]["integration"]["status"], "not_verified")
        self.assertTrue(any("targets contract" in item for item in c["assessment"]["needs_attention"]))
        self.assertTrue(any("unresolved dependency" in item for item in c["assessment"]["needs_attention"]))
        self.assertFalse(c["assessment"]["integration"]["runs"][0]["matches_current_revisions"])

    def test_aligned_components_still_need_integration(self):
        c = self.context("server", "client-a", "client-b", "old-integration")
        a = c["assessment"]
        self.assertEqual([x["status"] for x in a["components"].values()], ["implemented", "implemented"])
        self.assertEqual(a["integration"]["status"], "not_verified")
        self.assertFalse(any("unresolved dependency" in item for item in a["needs_attention"]))

    def test_exact_tuple_and_matching_evidence_report_pass(self):
        c = self.context(*self.handoffs)
        self.assertEqual(c["assessment"]["integration"]["status"], "passed_recorded")
        self.assertFalse(c["assessment"]["needs_attention"])
        self.assertEqual(len(c["assessment"]["integration"]["runs"]), 1)

    def test_changed_implementation_invalidates_previous_pass(self):
        self.handoffs["server"]["revision"] = "4" * 40
        c = self.context(*self.handoffs)
        self.assertEqual(c["assessment"]["integration"]["status"], "not_verified")

    def test_missing_or_changed_test_sources_prevent_verified_result(self):
        c = self.context(*self.handoffs)
        for state in ("changed", "unavailable"):
            with self.subTest(state=state):
                sources = copy.deepcopy(c["evidence"])
                for source in sources.values():
                    source["status"] = state
                a = assess(self.feature, c["handoffs"], sources)
                self.assertEqual(a["integration"]["status"], "unverified_evidence")

    def test_multiple_active_components_do_not_select_the_latest(self):
        self.handoffs["client-b"]["supersedes"] = []
        c = self.context(*self.handoffs)
        self.assertEqual(c["assessment"]["components"]["client"]["status"], "multiple_contributions")
        self.assertEqual(c["assessment"]["integration"]["status"], "not_verified")

    def test_conflicting_integration_reports_remain_visible(self):
        failed = copy.deepcopy(self.handoffs["new-integration"])
        failed.update(id="76b6f74a-8d69-4388-9af2-35a779633e29", author="Leo", supersedes=[])
        failed["collaboration"].update(result="failed")
        failed["collaboration"]["tests"][0]["result"] = "failed"
        c = demo_context(self.feature, [*self.handoffs.values(), failed], self.sources)
        self.assertEqual(c["assessment"]["integration"]["status"], "conflicting_reports")

    def test_open_dependencies_are_not_resolved_by_other_component_state(self):
        self.handoffs["client-b"]["collaboration"]["dependencies"][0]["status"] = "open"
        c = self.context(*self.handoffs)
        self.assertTrue(any("unresolved dependency" in item for item in c["assessment"]["needs_attention"]))

    def test_another_feature_cannot_supersede_a_contribution(self):
        h = self.handoffs["server"]
        other = copy.deepcopy(h)
        other.update(id="76b6f74a-8d69-4388-9af2-35a779633e29", supersedes=[h["id"]])
        other["collaboration"]["feature_id"] = "other-feature"
        records, warnings = workflows.collect_handoffs(comments_for([h, other]), h["repo"], h["issue"])
        self.assertFalse(records[0]["superseded_by"])
        self.assertTrue(warnings)

    def test_incomplete_issue_history_prevents_a_green_result(self):
        c = self.context(*self.handoffs)
        a = assess(self.feature, c["handoffs"], c["evidence"], incomplete=True)
        self.assertEqual(a["integration"]["status"], "not_verified")

    def test_demo_outputs_are_readable_and_cannot_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = run_demo(Path(temporary) / "demo")
            statuses = [read_json(folder / stage / "feature-context.json")["assessment"]["integration"]["status"]
                        for stage in ("01-contract-mismatch", "02-aligned-but-untested", "03-integration-recorded")]
            self.assertEqual(statuses, ["not_verified", "not_verified", "passed_recorded"])
            with patch.object(adapters, "post") as post, self.assertRaisesRegex(RelayError, "Demo"):
                workflows.publish(folder / "contributions/new-integration/handoff.json")
            post.assert_not_called()


class FeatureReadTests(unittest.TestCase):
    def setUp(self):
        self.feature, self.handoffs, self.sources = scenario()
        self.project = {"repo": self.feature["parent"]["repo"], "memories": {"team": "example/feature-memory"}}

    def test_unreadable_component_preserves_other_work_and_warns(self):
        def issue(repo, number):
            if number == 202:
                raise RelayError("private repository not accessible")
            return {"number": number, "title": "Feature", "body": ""}
        server = self.handoffs["server"]
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(adapters, "issue", side_effect=issue), \
             patch.object(adapters, "comments", side_effect=lambda repo, number: comments_for([server]) if number == 201 else []), \
             patch.object(adapters, "evidence", return_value="changed output"):
            folder, warnings = features.continue_feature(self.project, self.feature, Path(temporary) / "context")
            c = read_json(folder / "feature-context.json")
            self.assertEqual(c["assessment"]["components"]["server"]["status"], "implemented")
            self.assertEqual(c["assessment"]["components"]["client"]["status"], "unknown")
            self.assertEqual(c["assessment"]["integration"]["status"], "not_verified")
            self.assertTrue(any("private repository" in w for w in warnings))

    def test_bad_dependency_cannot_hide_a_valid_predecessor(self):
        h = self.handoffs["server"]
        bad = copy.deepcopy(h)
        bad.update(id="76b6f74a-8d69-4388-9af2-35a779633e29", supersedes=[h["id"]])
        bad["collaboration"]["dependencies"] = [{"component": "unknown", "need": "something", "status": "open"}]
        with patch.object(adapters, "issue", return_value={"number": 201}), \
             patch.object(adapters, "comments", return_value=comments_for([h, bad])):
            snapshot = features.read_feature_issue(self.feature, self.feature["components"]["server"])
        self.assertEqual(len(snapshot["handoffs"]), 1)
        self.assertFalse(snapshot["handoffs"][0]["superseded_by"])
        self.assertFalse(snapshot["complete"])


class FeatureCliTests(unittest.TestCase):
    def test_server_client_publish_and_continue_from_real_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            stub = Path(__file__).with_name("fake_feature_tools.py").read_text()
            for name in ("gh", "funes"):
                path = binary / name
                path.write_text(f"#!{sys.executable}\n{stub}")
                path.chmod(0o755)
            env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"], "RELAY_TEST_STATE": str(root)}
            cli = Path(__file__).resolve().parents[1] / "relay.py"

            def call(*args, poster="maya", success=True):
                result = subprocess.run([sys.executable, str(cli), *args], cwd=root,
                                        env={**env, "RELAY_TEST_POSTER": poster}, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
                return result.stdout

            feature, _, _ = scenario()
            write_json(root / "feature.json", feature)
            call("init", "--repo", "example/payments", "--memory", "team=example/feature-memory")

            def prepare_component(component, revision, contract_revision, output, previous=None):
                call("prepare-feature", "feature.json", "--component", component, "--revision", revision,
                     "--contract-revision", contract_revision, "--author", "Leo" if component == "client" else "Maya",
                     "--query", "list payments pagination", "--out", output)
                eid = call("cite", output, "--memory", "team", "--session", output, "--from", "1", "--to", "2").strip()
                path = root / output / "handoff.json"
                h = read_json(path)
                h.update(summary=f"Implemented {component}.", next_steps=["Exercise the real server/client pair."],
                         findings=[{"kind": "observation", "claim": "Component tests passed.", "evidence": [eid]}])
                h["collaboration"]["state"] = "implemented"
                if previous:
                    h["supersedes"] = [previous]
                write_json(path, h)
                self.assertEqual(parse_comment(call("render", str(path))), h)
                call("publish", str(path), poster=h["author"].lower())
                return h

            prepare_component("server", "1" * 40, "b" * 40, "server")
            client = prepare_component("client", "2" * 40, "a" * 40, "client-a")
            call("continue-feature", "feature.json", "--out", "mismatch")
            mismatch = read_json(root / "mismatch/feature-context.json")
            self.assertTrue(any("targets contract" in w for w in mismatch["assessment"]["needs_attention"]))
            prepare_component("client", "3" * 40, "b" * 40, "client-b", client["id"])
            call("continue-feature", "feature.json", "--out", "aligned")
            self.assertEqual(read_json(root / "aligned/feature-context.json")["assessment"]["integration"]["status"], "not_verified")
            call("prepare-integration", "feature.json", "--implementation", "server=" + "1" * 40,
                 "--implementation", "client=" + "3" * 40, "--author", "Maya", "--query", "integration tests", "--out", "integration")
            eid = call("cite", "integration", "--memory", "team", "--session", "integration", "--from", "1", "--to", "2").strip()
            path = root / "integration/handoff.json"
            h = read_json(path)
            h.update(summary="The client exercised the server successfully.", next_steps=["Review test scope before rollout."])
            h["collaboration"].update(result="passed", tests=[{"name": "Cursor pagination against running server", "result": "passed", "evidence": [eid]}])
            write_json(path, h)
            self.assertEqual(parse_comment(call("render", str(path))), h)
            self.assertTrue(json.loads(call("publish", str(path)))["published"])
            self.assertFalse(json.loads(call("publish", str(path)))["published"])
            call("continue-feature", "feature.json", "--out", "complete")
            c = read_json(root / "complete/feature-context.json")
            self.assertEqual(c["assessment"]["integration"]["status"], "passed_recorded")
            self.assertFalse(c["warnings"])
            stored = read_json(root / "comments.json")
            self.assertEqual(len(stored["example/payments-sdk#202"]), 2)
            self.assertEqual(len(stored["example/payments#200"]), 1)
            self.assertEqual(len(stored["example/payments#201"]), 1)


if __name__ == "__main__":
    unittest.main()

