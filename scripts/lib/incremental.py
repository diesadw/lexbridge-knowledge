"""
LEXBRIDGE Knowledge Repository — incremental.py (Sprint 2.6, Part 8)
-------------------------------------------------------------------------
Tracks a SHA-256 per knowledge/ JSON file in .kb/state.json. `kb build`
and `kb index` use this to process only files that changed since the
last run, instead of re-walking all 65k+ records every time. Full
rebuilds remain available via `kb build --full`.

State file shape:
{
  "updated_at": "...",
  "files": { "<relpath>": {"sha256": "...", "record_count": N} }
}
"""
import os
import json

from .common import load_registry, active_folders, iter_json_files, load_records, file_sha256, now_iso

STATE_PATH_REL = os.path.join(".kb", "state.json")


def _state_path(root: str) -> str:
    return os.path.join(root, STATE_PATH_REL)


def load_state(root: str) -> dict:
    p = _state_path(root)
    if not os.path.exists(p):
        return {"updated_at": None, "files": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_state(root: str, state: dict) -> None:
    p = _state_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def diff(root: str, full: bool = False):
    """Returns (changed_files, deleted_files, unchanged_count) relative
    to the last saved state. If full=True, everything is 'changed'."""
    registry = load_registry(root)
    state = load_state(root)
    prev_files = state.get("files", {})

    current = {}
    for folder in active_folders(registry):
        folder_path = os.path.join(root, "knowledge", folder)
        for fp in iter_json_files(folder_path):
            rel = os.path.relpath(fp, root)
            current[rel] = fp

    changed = []
    unchanged = 0
    new_hashes = {}
    for rel, fp in current.items():
        h = file_sha256(fp)
        try:
            rec_count = len(load_records(fp))
        except Exception:
            rec_count = 0
        new_hashes[rel] = {"sha256": h, "record_count": rec_count}
        if full or rel not in prev_files or prev_files[rel].get("sha256") != h:
            changed.append(rel)
        else:
            unchanged += 1

    deleted = sorted(set(prev_files.keys()) - set(current.keys()))
    return changed, deleted, unchanged, new_hashes


def commit(root: str, new_hashes: dict) -> None:
    state = {"updated_at": now_iso(), "files": new_hashes}
    save_state(root, state)
