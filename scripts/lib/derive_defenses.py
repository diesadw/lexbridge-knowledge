"""
LEXBRIDGE Knowledge Repository — derive_defenses.py (Sprint 2.6, Part 13 support)
-------------------------------------------------------------------------
The source data has no standalone "defense" entity (0 per
KNOWLEDGE_GRAPH_INDEX.json / KNOWLEDGE_BASE_REPORT.md §3 — defense
arguments live inside judgment_principle.source_fields.defense_args).

Rather than hand the "Defense & Verdict Finder" tool a hardcoded mock
list (as the current website implementation does in DefenseResearch.tsx
— DEFENSES_DB / VERDICTS_DB / ARTICLES_DB), this derives ONE defense
record per unique defense_args string, grouping every judgment that
actually argues it. This is not invented data: every string comes
verbatim from an existing judgment_principle record, and every derived
record cites back to its exact source judgments (traceability, not
generation).

Output: knowledge/defenses/<branch>.json, one file per branch
(criminal, civil, ...), id_prefix "defense-".

Idempotent: re-running fully regenerates the folder from current
judgment data, so it is safe to call from `kb build` every time (this
folder is generated, not hand-authored — see PROVENANCE.md note added
alongside).
"""
import hashlib
import os
import re
from collections import defaultdict

from .common import load_registry, iter_all_records, write_json, now_iso


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\u0600-\u06FF]+", "-", text.strip())
    return text.strip("-")[:60] or "defense"


def derive_defenses(root: str) -> dict:
    registry = load_registry(root)
    # group by (branch, defense text) -> supporting judgment ids
    groups = defaultdict(lambda: {"judgment_ids": [], "branch": None, "category": None})

    for folder, _fp, rec in iter_all_records(root, registry, folders=["judgments"]):
        if rec.get("type") != "judgment_principle":
            continue
        sf = rec.get("source_fields") or {}
        defense_args = sf.get("defense_args") or []
        if not isinstance(defense_args, list):
            continue
        branch = rec.get("metadata", {}).get("branch") or rec.get("category") or "عام"
        for arg in defense_args:
            if not isinstance(arg, str) or not arg.strip():
                continue
            key = (branch, arg.strip())
            groups[key]["judgment_ids"].append(rec.get("id"))
            groups[key]["branch"] = branch
            groups[key]["category"] = rec.get("category")

    by_branch = defaultdict(list)
    for (branch, arg_text), info in groups.items():
        stable_key = f"{branch}\x1f{arg_text}".encode("utf-8")
        stable_suffix = hashlib.md5(stable_key).hexdigest()[:8]
        did = f"defense-{_slug(branch)}-{_slug(arg_text)}-{stable_suffix}"
        rec = {
            "id": did,
            "type": "defense",
            "category": info["category"] or branch,
            "title": arg_text,
            "content": arg_text,
            "keywords": [],
            "citations": [],
            "related_ids": [],
            "related_judgments": sorted(set(info["judgment_ids"])),
            "related_articles": [],
            "related_defenses": [],
            "related_procedures": [],
            "related_contracts": [],
            "related_principles": [],
            "metadata": {
                "branch": branch,
                "derived_from": "judgment_principle.source_fields.defense_args",
                "supporting_judgment_count": len(set(info["judgment_ids"])),
            },
            "source_fields": {"derived": True},
        }
        by_branch[branch].append(rec)

    out_dir = os.path.join(root, "knowledge", "defenses")
    total = 0
    for branch, recs in by_branch.items():
        fname = _slug(branch) + ".json"
        write_json(os.path.join(out_dir, fname), recs)
        total += len(recs)

    return {
        "generated_at": now_iso(),
        "defense_records_generated": total,
        "branches": {b: len(r) for b, r in by_branch.items()},
        "source": "judgment_principle.source_fields.defense_args (real data, zero invented content)",
    }
