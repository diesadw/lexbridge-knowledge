"""
LEXBRIDGE Knowledge Repository — shared helpers
-------------------------------------------------------------------------
Used by every pipeline module (validate, stats, graph, migrate, importer,
metadata_extract, citations, incremental). Single place that knows how to
load the registry and walk knowledge/<folder> — nothing else should
hardcode folder names or JSON-walking logic.
"""
import json
import os
import hashlib
from datetime import datetime, timezone


def load_registry(root: str) -> dict:
    path = os.path.join(root, "schemas", "document-types.registry.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def active_folders(registry: dict):
    return [e["folder"] for e in registry["document_types"] if e.get("status") == "active"]


def all_folders(registry: dict):
    return [e["folder"] for e in registry["document_types"]]


def iter_json_files(folder_path: str):
    if not os.path.isdir(folder_path):
        return
    for dirpath, _, filenames in os.walk(folder_path):
        for name in sorted(filenames):
            if name.endswith(".json"):
                yield os.path.join(dirpath, name)


def load_records(file_path: str):
    """A knowledge JSON file is either a list of records or a single record."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data]


def iter_all_records(root: str, registry: dict, folders=None):
    """Yields (folder, file_path, record) for every record in the given
    (or all active) folders. This is the ONE iteration primitive every
    other module should use."""
    folders = folders or active_folders(registry)
    for folder in folders:
        folder_path = os.path.join(root, "knowledge", folder)
        for fp in iter_json_files(folder_path):
            try:
                records = load_records(fp)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            for rec in records:
                if isinstance(rec, dict):
                    yield folder, fp, rec


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_id(rec: dict):
    return rec.get("id")


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
