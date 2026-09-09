import argparse
import json
import sys
from pathlib import Path

from . import features, workflows
from .model import RelayError, TOKEN, render, require, validate_memory, validate_repo
from .storage import config, read_json, write_json


def positive(value):
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Use a positive issue number.")


def parser():
    p = argparse.ArgumentParser(description="Relay: team handoffs backed by Funes evidence.")
    p.add_argument("--config", default=".relay/project.json", help="Project registry path")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a local project registry")
    init.add_argument("--repo", required=True, help="GitHub owner/repository")
    init.add_argument("--memory", action="append", required=True, metavar="ALIAS=OWNER/DATASET")
    prepare = sub.add_parser("prepare", help="Read an issue and search team memories; create a draft")
    prepare.add_argument("issue", type=positive)
    prepare.add_argument("--query", required=True)
    prepare.add_argument("--author", required=True)
    prepare.add_argument("--revision", required=True, help="Commit SHA, or explicitly 'unknown'")
    prepare.add_argument("--out", required=True)
    cite = sub.add_parser("cite", help="Capture a specific Funes range and attach its reference")
    cite.add_argument("folder")
    cite.add_argument("--memory", required=True, help="Configured memory alias")
    cite.add_argument("--session", required=True)
    cite.add_argument("--from", dest="start", type=int, required=True)
    cite.add_argument("--to", dest="end", type=int, required=True)
    for command, help_text in (("render", "Validate local evidence and print the exact GitHub comment"),
                               ("publish", "Post a validated handoff as a GitHub issue comment")):
        sp = sub.add_parser(command, help=help_text)
        sp.add_argument("handoff", help="Path to handoff.json beside its context.json")
    resume = sub.add_parser("continue", help="Read handoffs and retrieve their evidence for the next agent")
    resume.add_argument("issue", type=positive)
    resume.add_argument("--out", required=True)
    resume.add_argument("--query", help="Also search team memories for related work")
    demo = sub.add_parser("demo", help="Run a fictional two-teammate workflow offline")
    demo.add_argument("--out", default="demo-output")
    for command in ("prepare-feature", "prepare-integration"):
        sp = sub.add_parser(command, help="Draft a component contribution" if command == "prepare-feature" else "Draft an integration record on the parent issue")
        sp.add_argument("feature", help="Path to feature.json")
        sp.add_argument("--query", required=True)
        sp.add_argument("--author", required=True)
        sp.add_argument("--revision", default="unknown", help="Full commit SHA of the current checkout, or unknown")
        sp.add_argument("--contract-revision", help="Override the target contract with a full commit SHA")
        sp.add_argument("--out", required=True)
        if command == "prepare-feature":
            sp.add_argument("--component", required=True)
        else:
            sp.add_argument("--implementation", action="append", required=True, metavar="COMPONENT=SHA")
    sp = sub.add_parser("continue-feature", help="Read linked issues, compare contract targets, and inspect integration results")
    sp.add_argument("feature", help="Path to feature.json")
    sp.add_argument("--out", required=True)
    sp.add_argument("--query", help="Also search the project's memories")
    sp = sub.add_parser("demo-feature", help="Run an offline server/client feature collaboration")
    sp.add_argument("--out", default="feature-demo")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            require(not Path(args.config).exists(), f"{args.config} already exists; edit it to change the registry.")
            validate_repo(args.repo)
            memories = {}
            for spec in args.memory:
                alias, sep, memory = spec.partition("=")
                require(sep and TOKEN.fullmatch(alias), "Use --memory alias=owner/dataset.")
                require(alias not in memories, f"Duplicate memory alias: {alias}")
                validate_memory(memory)
                memories[alias] = memory
            write_json(args.config, {"version": 1, "repo": args.repo, "memories": memories})
            print(f"Project configured in {args.config}")
        elif args.command == "prepare":
            folder, warnings = workflows.prepare(config(args.config), args.issue, args.query,
                                                   args.author, args.revision, args.out)
            print(f"Read {folder / 'PREPARE.md'}, then fill {folder / 'handoff.json'}")
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        elif args.command == "cite":
            print(workflows.cite(args.folder, args.memory, args.session, args.start, args.end))
        elif args.command == "render":
            h, _ = workflows.verify_local(args.handoff)
            print(render(h), end="")
        elif args.command == "publish":
            print(json.dumps(workflows.publish(args.handoff), indent=2))
        elif args.command == "continue":
            folder, warnings = workflows.resume(config(args.config), args.issue, args.out, args.query)
            print(f"Read {folder / 'CONTINUE.md'}")
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        elif args.command == "demo":
            from .demo import run_demo
            folder = run_demo(args.out)
            print(f"Demo complete. Open {folder / 'WALKTHROUGH.md'}")
        elif args.command in ("prepare-feature", "prepare-integration"):
            implementations = None
            if args.command == "prepare-integration":
                implementations = {}
                for item in args.implementation:
                    component, sep, sha = item.partition("=")
                    require(sep and component not in implementations, "Use distinct --implementation COMPONENT=SHA values.")
                    implementations[component] = sha
            folder, warnings = features.prepare_feature(config(args.config), read_json(args.feature),
                getattr(args, "component", None), args.query, args.author, args.revision, args.out,
                args.contract_revision, implementations)
            print(f"Read {folder / 'PREPARE.md'}, then fill {folder / 'handoff.json'}")
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        elif args.command == "continue-feature":
            folder, warnings = features.continue_feature(config(args.config), read_json(args.feature), args.out, args.query)
            print(f"Read {folder / 'FEATURE.md'}")
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        elif args.command == "demo-feature":
            from .feature_demo import run_demo
            folder = run_demo(args.out)
            print(f"Demo complete. Open {folder / 'WALKTHROUGH.md'}")
    except (RelayError, OSError) as exc:
        print(f"relay: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
