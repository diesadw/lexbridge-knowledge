"""
LEXBRIDGE Knowledge Repository — stats.py (Sprint 2.6, Part 6)
-------------------------------------------------------------------------
Generates the Knowledge Statistics report: totals per document type,
per-category breakdowns, metadata coverage, relationship coverage, and
broken-reference counts (reuses validate.py rather than re-scanning).
"""
from collections import defaultdict

from .common import load_registry, iter_all_records, now_iso
from .validate import validate, RELATION_FIELDS


def build_stats(root: str) -> dict:
    registry = load_registry(root)
    v = validate(root)

    per_type_totals = defaultdict(int)
    per_type_per_category = defaultdict(lambda: defaultdict(int))
    metadata_field_coverage = defaultdict(lambda: defaultdict(int))
    relation_field_coverage = defaultdict(int)
    citation_coverage = 0
    total = 0

    for folder, _fp, rec in iter_all_records(root, registry):
        total += 1
        kb_type = rec.get("type") or folder
        per_type_totals[kb_type] += 1
        category = rec.get("category") or "غير مصنف"
        per_type_per_category[kb_type][category] += 1

        meta = rec.get("metadata") or {}
        for k, val in meta.items():
            if val not in (None, "", []):
                metadata_field_coverage[kb_type][k] += 1

        for field in RELATION_FIELDS:
            if rec.get(field):
                relation_field_coverage[field] += 1

        if rec.get("citations"):
            citation_coverage += 1

    report = {
        "generated_at": now_iso(),
        "totals": {
            "total_records": total,
            "by_type": dict(per_type_totals),
        },
        "by_type_by_category": {
            t: dict(cats) for t, cats in per_type_per_category.items()
        },
        "metadata_coverage": {
            t: dict(fields) for t, fields in metadata_field_coverage.items()
        },
        "relationship_coverage": dict(relation_field_coverage),
        "citation_coverage_records": citation_coverage,
        "citation_coverage_pct": round(100 * citation_coverage / total, 2) if total else 0,
        "validation_summary": {
            "duplicate_ids_count": v["errors"]["duplicate_ids_count"],
            "broken_relationship_links_count": v["errors"]["broken_relationship_links_count"],
            "invalid_json_files_count": len(v["errors"]["invalid_json_files"]),
            "orphan_records": v["warnings"]["orphan_records_zero_relations_and_citations"],
            "missing_required_metadata_count": v["warnings"]["missing_required_metadata_count"],
        },
        "registered_collections": [
            {
                "folder": e["folder"],
                "label_en": e.get("label_en"),
                "status": e.get("status"),
                "registered_record_count": e.get("record_count"),
            }
            for e in registry["document_types"]
        ],
    }
    return report
