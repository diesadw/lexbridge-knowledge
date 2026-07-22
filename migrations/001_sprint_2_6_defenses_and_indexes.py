"""
Migration 001 — Sprint 2.6
Adds the derived `defenses` collection and the graph/stats/validation
index artifacts. Does not touch any existing legal content record.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

VERSION = "2.6.0"
DESCRIPTION = "Derive defenses collection from judgment defense_args; add graph/stats/validation indexes; promote defenses registry entry from planned to active."


def up(root: str) -> dict:
    from lib.derive_defenses import derive_defenses
    from lib.graph import build_graph, save_graph
    from lib.stats import build_stats
    from lib.validate import validate
    from lib.common import write_json
    import json

    defense_result = derive_defenses(root)

    graph = build_graph(root)
    save_graph(root, graph, os.path.join(root, "indexes", "graph_index.json"))

    stats = build_stats(root)
    write_json(os.path.join(root, "indexes", "statistics_report.json"), stats)

    report = validate(root)
    write_json(os.path.join(root, "indexes", "validation_report.json"), report)

    # promote the registry entry now that real derived data exists
    reg_path = os.path.join(root, "schemas", "document-types.registry.json")
    with open(reg_path, encoding="utf-8") as f:
        registry = json.load(f)
    for entry in registry["document_types"]:
        if entry["folder"] == "defenses":
            entry["status"] = "active"
            entry["record_count"] = defense_result["defense_records_generated"]
            entry["file_count"] = len(defense_result["branches"])
            entry["note"] = (
                "Derived at build time from judgment_principle.source_fields.defense_args "
                "by scripts/lib/derive_defenses.py (kb build). Regenerated on every build; "
                "not hand-authored. Zero invented content — every defense string and its "
                "supporting judgments trace back to real judgment_principle records."
            )
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    return {"defenses": defense_result, "graph_nodes": graph["node_count"], "stats_total": stats["totals"]["total_records"]}
