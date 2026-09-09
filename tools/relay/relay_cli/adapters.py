"""External processes use argument arrays; retrieved text is never executed."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .model import RelayError, get_command


def run(args, input_text=None):
    try:
        result = subprocess.run(args, input=input_text, text=True, capture_output=True,
                                timeout=120, check=False)
    except FileNotFoundError:
        raise RelayError(f"{args[0]} is not installed or is not on PATH.") from None
    except subprocess.TimeoutExpired:
        raise RelayError(f"{args[0]} timed out after 120 seconds. Check the operation before retrying a write.") from None
    if result.returncode:
        detail = result.stderr.strip()[-1500:]
        raise RelayError(f"{args[0]} exited {result.returncode}: {detail or 'no error details'}")
    return result.stdout


def gh_json(args):
    try:
        return json.loads(run(["gh", *args]))
    except json.JSONDecodeError:
        raise RelayError("GitHub CLI returned invalid JSON.") from None


def issue(repo, number):
    return gh_json(["issue", "view", str(number), "--repo", repo,
                    "--json", "number,title,body,url,updatedAt"])


def comments(repo, number):
    pages = gh_json(["api", f"repos/{repo}/issues/{number}/comments?per_page=100",
                     "--paginate", "--slurp"])
    return [comment for page in pages for comment in page]


def post(repo, number, body):
    return run(["gh", "issue", "comment", str(number), "--repo", repo, "--body-file", "-"], body).strip()


def recall(memories, query):
    def one(item):
        alias, memory = item
        try:
            output = run(["funes", "recall", query, "--memory", memory, "-k", "5"])
            return {"alias": alias, "memory": memory, "output": output, "error": None}
        except RelayError as exc:
            return {"alias": alias, "memory": memory, "output": "", "error": str(exc)}
    with ThreadPoolExecutor(max_workers=min(4, len(memories) or 1)) as pool:
        return list(pool.map(one, memories.items()))


def evidence(e):
    output = run(get_command(e))
    if not output.strip() or output.strip().startswith(("no turns in that range", "no session ")):
        raise RelayError("Funes returned no evidence for this range.")
    if "turn(s) in range not shown" in output:
        raise RelayError("Funes truncated this range. Cite a smaller range.")
    return output

