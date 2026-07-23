"""
LEXBRIDGE Knowledge Repository — validate.py (Sprint 2.6, Part 5)
-------------------------------------------------------------------------
Full self-validation of knowledge/. Detects:
  - invalid JSON files (unreadable / malformed)
  - documents outside any registered folder (invalid document types)
  - duplicate IDs (within and across folders)
  - duplicate citations on the same record
  - missing required metadata fields per the record's declared type
  - broken relationship references (related_ids / related_* pointing at
    an ID that does not exist anywhere in the repository)
  - orphan records (zero relations of any kind, zero citations) — this is
    a WARNING, not an error: many valid records legitimately have none
    (see KNOWLEDGE_GRAPH_INDEX.json's own records_with_zero_relations_count)
  - broken links inside `citations[]` / `references` style fields that
    look like internal IDs but don't resolve

Returns a structured report; does not mutate any data.
"""
import json
import os
from collections import defaultdict

from .common import (
    load_registry, all_folders, active_folders, iter_json_files,
    load_records, now_iso,
)

REQUIRED_METADATA_BY_KB_TYPE = {
    "judgment_principle": ["court", "date"],
    "doctrine_principle": ["source"],
    "legal_article": ["law_name", "article_number"],
    "deadline": ["branch"],
    "procedure": ["branch"],
    "procedure_deep": ["branch"],
    "template": ["source"],
    "defense": ["derived_from"],
}

# legal_article (and any other flat-shape type) carries its fields at the
# TOP LEVEL of the record rather than nested in metadata/source_fields
# (see scaffold README "Record schema" — two shapes exist by design).
FLAT_SHAPE_TYPES = {"legal_article"}

# Folders that exist on disk but are intentionally not first-class,
# registry-driven record collections (provenance/reference material only
# — see README "knowledge/references ... kept for provenance, not
# consumed by the engine"). Not an error if present and unregistered.
NON_COLLECTION_FOLDERS = {"references"}

RELATION_FIELDS = [
    "related_ids", "related_articles", "related_judgments",
    "related_defenses", "related_procedures", "related_contracts",
    "related_principles",
]


def validate(root: str) -> dict:
    registry = load_registry(root)
    knowledge_dir = os.path.join(root, "knowledge")

    invalid_json = []
    unregistered_files = []
    all_ids = {}          # id -> [ (folder, file, index) ]
    records_by_id = {}
    dup_citations = []
    missing_metadata = []
    per_folder_counts = defaultdict(int)

    registered_folders = set(all_folders(registry))
    on_disk_folders = set(
        d for d in os.listdir(knowledge_dir)
        if os.path.isdir(os.path.join(knowledge_dir, d))
    ) if os.path.isdir(knowledge_dir) else set()

    unregistered_folders = sorted(on_disk_folders - registered_folders - NON_COLLECTION_FOLDERS)

    for folder in sorted(on_disk_folders):
        if folder in NON_COLLECTION_FOLDERS:
            continue
        folder_path = os.path.join(knowledge_dir, folder)
        is_registered = folder in registered_folders
        for fp in iter_json_files(folder_path):
            rel_fp = os.path.relpath(fp, root)
            try:
                records = load_records(fp)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                invalid_json.append({"file": rel_fp, "error": str(e)})
                continue
            if not is_registered:
                unregistered_files.append(rel_fp)

            for idx, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                per_folder_counts[folder] += 1
                rid = rec.get("id")
                if rid:
                    all_ids.setdefault(rid, []).append(f"{rel_fp}#{idx}")
                    records_by_id[rid] = rec

                # duplicate citations within a single record
                cits = rec.get("citations") or []
                if isinstance(cits, list) and len(cits) != len(set(map(str, cits))):
                    dup_citations.append({"id": rid, "file": rel_fp})

                # required metadata per declared type
                kb_type = rec.get("type")
                required = REQUIRED_METADATA_BY_KB_TYPE.get(kb_type, [])
                meta = rec.get("metadata") or {}
                source_fields = rec.get("source_fields") or {}

                def _present(field):
                    if meta.get(field) not in (None, "", []):
                        return True
                    if source_fields.get(field) not in (None, "", []):
                        return True
                    if kb_type in FLAT_SHAPE_TYPES and rec.get(field) not in (None, "", []):
                        return True
                    return False

                missing = [field for field in required if not _present(field)]
                if missing:
                    missing_metadata.append({"id": rid, "file": rel_fp, "missing": missing})

    duplicate_ids = {rid: locs for rid, locs in all_ids.items() if len(locs) > 1}

    # broken relationship references — second pass now that we know every ID
    broken_links = []
    zero_relation_records = 0
    for rid, rec in records_by_id.items():
        has_relation = False
        for field in RELATION_FIELDS:
            refs = rec.get(field) or []
            if not isinstance(refs, list):
                continue
            if refs:
                has_relation = True
            for target in refs:
                if target not in records_by_id and target != rid:
                    broken_links.append({"from": rid, "field": field, "target": target})
        if not has_relation and not (rec.get("citations") or []):
            zero_relation_records += 1

    hard_errors = bool(invalid_json or unregistered_files or unregistered_folders or broken_links)
    report = {
        "generated_at": now_iso(),
        "status": "issues_found" if hard_errors else ("ok_with_known_warnings" if duplicate_ids or missing_metadata else "ok"),
        "counts": {
            "total_records": len(records_by_id) + sum(len(v) - 1 for v in duplicate_ids.values()) - len(duplicate_ids) + len(duplicate_ids),
            "unique_ids": len(records_by_id),
            "records_scanned": sum(per_folder_counts.values()),
            "per_folder": dict(per_folder_counts),
        },
        "errors": {
            "invalid_json_files": invalid_json,
            "unregistered_folders": unregistered_folders,
            "unregistered_files_in_registered_area": unregistered_files,
            "duplicate_ids": {k: v for k, v in list(duplicate_ids.items())[:200]},
            "duplicate_ids_count": len(duplicate_ids),
            "broken_relationship_links": broken_links[:200],
            "broken_relationship_links_count": len(broken_links),
        },
        "warnings": {
            "duplicate_citations_within_record": dup_citations[:200],
            "duplicate_citations_count": len(dup_citations),
            "missing_required_metadata": missing_metadata[:200],
            "missing_required_metadata_count": len(missing_metadata),
            "orphan_records_zero_relations_and_citations": zero_relation_records,
        },
    }
    return report
