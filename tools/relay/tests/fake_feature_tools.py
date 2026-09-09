"""Executed as fake gh/funes by the CLI integration test; never used in production."""

import json
import os
import re
import sys
from pathlib import Path

root = Path(os.environ["RELAY_TEST_STATE"])
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([tool, *args]) + "\n")
state_path = root / "comments.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
if tool == "funes":
    if args[0] == "recall":
        print("Source available: get feature-session --from 1 --to 2 --memory example/feature-memory")
    else:
        print(f"[assistant text seq1] Evidence for session {args[1]}.\n---\nturns 1-2 of 4")
elif args[:2] == ["issue", "view"]:
    repo = args[args.index("--repo") + 1]
    number = int(args[2])
    print(json.dumps({"number": number, "title": f"Feature work #{number}", "body": "Implement the agreed contract.",
                      "url": f"https://github.com/{repo}/issues/{number}", "updatedAt": "2026-09-08T10:00:00Z"}))
elif args[0] == "api":
    match = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)/comments\?per_page=100", args[1])
    if not match or "--paginate" not in args or "--slurp" not in args:
        sys.exit(9)
    rows = state.get(f"{match[1]}#{match[2]}", [])
    print(json.dumps([rows[:1], rows[1:]]))
elif args[:2] == ["issue", "comment"]:
    if args[-2:] != ["--body-file", "-"]:
        sys.exit(9)
    repo, number = args[args.index("--repo") + 1], args[2]
    rows = state.setdefault(f"{repo}#{number}", [])
    url = f"https://github.com/{repo}/issues/{number}#issuecomment-{len(rows) + 1}"
    rows.append({"body": sys.stdin.read(), "user": {"login": os.environ.get("RELAY_TEST_POSTER", "maya")},
                 "html_url": url, "created_at": "2026-09-08T10:00:00Z", "updated_at": "2026-09-08T10:00:00Z"})
    state_path.write_text(json.dumps(state))
    print(url)
else:
    sys.exit(9)

