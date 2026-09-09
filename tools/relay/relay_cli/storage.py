import json
import os
import tempfile
from pathlib import Path

from .model import RelayError, require, validate_memory, validate_repo, TOKEN


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RelayError(f"Cannot read {path}: {exc}") from None


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Owner-only local snapshots can contain private session passages.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".relay-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def config(path):
    value = read_json(path)
    require(isinstance(value, dict) and value.get("version") == 1, "Invalid project configuration.")
    validate_repo(value.get("repo"))
    memories = value.get("memories")
    require(isinstance(memories, dict) and memories, "Configure at least one team memory.")
    for alias, memory in memories.items():
        require(TOKEN.fullmatch(alias), "Invalid memory alias.")
        validate_memory(memory)
    return value


def new_directory(path):
    path = Path(path)
    require(not path.exists(), f"{path} already exists. Choose a new output directory.")
    path.mkdir(parents=True, mode=0o700)
    return path

