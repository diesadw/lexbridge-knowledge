"""
LEXBRIDGE Knowledge Repository — migrate.py (Sprint 2.6, Part 9)
-------------------------------------------------------------------------
Lightweight versioning for the repository's data shape (NOT the legal
content itself, which is immutable/append-only per the "no data loss,
no edits" rule). A migration is a Python module in migrations/ with:

    VERSION = "1.1.0"
    DESCRIPTION = "..."
    def up(root: str) -> dict: ...

Applied migrations are recorded in indexes/migration_history.json so
`kb migrate` is idempotent and safe to run repeatedly. This is the
mechanism Part 9 asks for ("support future versions of datasets, support
migrations, keep history whenever possible") without inventing a heavy
schema-migration framework the repo doesn't need yet.
"""
import importlib.util
import os
import json

from .common import now_iso, write_json

VERSION_FILE = "VERSION"
HISTORY_FILE = os.path.join("indexes", "migration_history.json")
MIGRATIONS_DIR = "migrations"


def current_version(root: str) -> str:
    p = os.path.join(root, VERSION_FILE)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return "0.0.0"


def set_version(root: str, version: str) -> None:
    with open(os.path.join(root, VERSION_FILE), "w", encoding="utf-8") as f:
        f.write(version + "\n")


def load_history(root: str) -> list:
    p = os.path.join(root, HISTORY_FILE)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _discover_migrations(root: str):
    mdir = os.path.join(root, MIGRATIONS_DIR)
    if not os.path.isdir(mdir):
        return []
    mods = []
    for fname in sorted(os.listdir(mdir)):
        if fname.endswith(".py") and fname[0].isdigit():
            spec = importlib.util.spec_from_file_location(fname[:-3], os.path.join(mdir, fname))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mods.append((fname, mod))
    return mods


def run_migrations(root: str, dry_run: bool = False) -> dict:
    history = load_history(root)
    applied_files = {h["file"] for h in history}
    results = []

    for fname, mod in _discover_migrations(root):
        if fname in applied_files:
            continue
        entry = {
            "file": fname,
            "version": getattr(mod, "VERSION", "unknown"),
            "description": getattr(mod, "DESCRIPTION", ""),
            "applied_at": now_iso(),
            "dry_run": dry_run,
        }
        if not dry_run and hasattr(mod, "up"):
            entry["result"] = mod.up(root)
            set_version(root, entry["version"])
        results.append(entry)
        if not dry_run:
            history.append(entry)

    if not dry_run and results:
        write_json(os.path.join(root, HISTORY_FILE), history)

    return {
        "current_version": current_version(root),
        "migrations_applied_this_run": results,
        "total_migrations_in_history": len(history),
    }
