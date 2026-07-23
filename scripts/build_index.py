#!/usr/bin/env python3
"""
LEXBRIDGE Knowledge Repository — build_index.py
-------------------------------------------------------------------------
Registry-driven manifest builder. This is the ONLY script that needs to
run when new data is added to knowledge/<folder>/. It does not talk to
Meilisearch or the website — it just walks the data, validates it against
schemas/document-types.registry.json, and writes indexes/registry_manifest.json:
a single, versioned contract describing exactly what data exists.

The website's scripts/knowledge-engine/buildIndexData.ts reads this
manifest (or walks knowledge/ directly using the same registry file) to
build its NDJSON -> Meilisearch pipeline. This script never writes
NDJSON or touches search infrastructure — that stays inside the website
repo's Knowledge Engine, per the "no duplicate Knowledge Engine" rule.

Usage:
    python3 scripts/build_index.py [--root .]

Exit codes:
    0  = manifest written, no unregistered folders found
    1  = manifest written, but knowledge/ contains folder(s) not present
         in the registry (new dataset added but registry not updated yet)
"""
import json
import os
import sys
import argparse
import hashlib
from datetime import datetime, timezone


def load_registry(root: str) -> dict:
    path = os.path.join(root, "schemas", "document-types.registry.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def walk_folder(folder_path: str):
    """Returns (file_count, record_count, files[]) for a knowledge/<folder>."""
    file_count = 0
    record_count = 0
    files = []
    for dirpath, _, filenames in os.walk(folder_path):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            full = os.path.join(dirpath, name)
            file_count += 1
            try:
                with open(full, encoding="utf-8") as f:
                    data = json.load(f)
                n = len(data) if isinstance(data, list) else 1
                record_count += n
            except Exception as e:
                print(f"  ! parse error in {full}: {e}", file=sys.stderr)
                n = 0
            files.append({
                "path": os.path.relpath(full, folder_path).replace(os.sep, "/"),
                "records": n,
                "size_bytes": os.path.getsize(full),
            })
    return file_count, record_count, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()
    root = args.root

    registry = load_registry(root)
    registered_folders = {dt["folder"] for dt in registry["document_types"]}

    knowledge_dir = os.path.join(root, "knowledge")
    actual_folders = {
        d for d in os.listdir(knowledge_dir)
        if os.path.isdir(os.path.join(knowledge_dir, d)) and d != "references"
    }

    unregistered = actual_folders - registered_folders
    missing_on_disk = {
        dt["folder"] for dt in registry["document_types"]
        if dt["status"] == "active" and dt["folder"] not in actual_folders
    }

    collections = []
    total_records = 0
    total_files = 0
    for dt in registry["document_types"]:
        folder_path = os.path.join(knowledge_dir, dt["folder"])
        if not os.path.isdir(folder_path):
            collections.append({**dt, "actual_file_count": 0, "actual_record_count": 0})
            continue
        fc, rc, files = walk_folder(folder_path)
        total_records += rc
        total_files += fc
        collections.append({
            "folder": dt["folder"],
            "engine_type": dt["engine_type"],
            "label_en": dt["label_en"],
            "status": dt["status"],
            "actual_file_count": fc,
            "actual_record_count": rc,
            "registered_record_count": dt.get("record_count"),
            "drift": rc != dt.get("record_count"),
        })

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": registry["registry_version"],
        "total_files": total_files,
        "total_records": total_records,
        "collections": collections,
        "unregistered_folders_found": sorted(unregistered),
        "registered_but_missing_on_disk": sorted(missing_on_disk),
    }

    out_dir = os.path.join(root, "indexes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "registry_manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nManifest written to {out_path}")

    if unregistered:
        print(
            f"\nWARNING: folder(s) present on disk but not in the registry: {sorted(unregistered)}. "
            "Add them to schemas/document-types.registry.json before running the website's reindex.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
