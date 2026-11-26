#!/usr/bin/env python3
"""LexBridge pilot build. Deterministic and idempotent: same inputs ->
byte-identical output. Reads the original zips; writes ONLY to --out."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import os
import re
import statistics
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (PIPELINE_VERSION, LexArchive, EgyptArchive, canon_article, h8, judgment_branch,
                 judgment_identity, judgment_new_id, lead_int, rec_sha256, text_block)

# ----------------------------------------------------------------- config
# Pilot law files are chosen by (folder, record count): ASCII-only, reproducible.
PILOT_LAW_FILES = [("customs", 30), ("procedural", 165), ("civil", 1094), ("civil", 1093),
                   ("family", 173), ("administrative", 32), ("labour", 50),
                   ("commercial", 222), ("constitutional", 212)]
SEG_SCORE_MIN = 0.6
EMOJI = re.compile("^[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u23F0\u2705]")
EDITORIAL_KEYS = {"simplified", "legal_reasoning", "practical_usage", "importance",
                  "plain_language_explanation", "practical_meaning"}
NAME_NUM = re.compile(r"رق[\u0640]*م\s*\(?\s*(\d+)")
NAME_YEAR = re.compile(r"(1[89]\d\d|20\d\d)")

IMPORT_DATE = None
REVIEW = []      # human-review list
CONFLICTS = []   # preserved conflicts


def review(rid, category, severity, reason, detail=None):
    REVIEW.append({"id": rid, "category": category, "severity": severity, "reason": reason,
                   "detail": detail})


def prov(sources, transformations, verification="unverified", conflicts=None, flags=None, **extra):
    p = {"sources": sources, "import_date": IMPORT_DATE, "pipeline_version": PIPELINE_VERSION,
         "transformations": transformations, "verification_status": verification,
         "conflict_flags": conflicts or [], "review_flags": flags or []}
    p.update(extra)
    return p


def field_status(keys):
    out = {}
    for k in keys:
        if k.startswith("ai_"):
            out[k] = "ai_generated_per_field_name"
        elif k in EDITORIAL_KEYS:
            out[k] = "editorial_unverified_provenance"
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.write("\n")


# ------------------------------------------------------------------ laws
def segmentize(recs):
    """T06: split a file where article numbering restarts (n < previous, n <= 2)."""
    segs, prev = [[]], None
    for i, r in enumerate(recs):
        n = lead_int(r["article_number"])
        if prev is not None and n is not None and n < prev and n <= 2:
            segs.append([])
        segs[-1].append(i)
        if n is not None:
            prev = n
    return segs


def build_nodes(arch, paths, tb_cache):
    nodes = []
    for p in paths:
        recs = arch.records(p)
        for si, idxs in enumerate(segmentize(recs)):
            keys, seen = [], collections.Counter()
            for i in idxs:
                if (p, i) not in tb_cache:
                    tb_cache[(p, i)] = text_block(recs[i]["content"] or "")
                c = canon_article(recs[i]["article_number"])
                keys.append((c, seen[c]))
                seen[c] += 1
            sig = hashlib.sha256("\n".join(recs[i]["content"] or "" for i in idxs).encode()).hexdigest()[:10]
            nodes.append({"path": p, "seg": si, "idxs": idxs, "keys": keys, "lineage": sig,
                          "ts": {k: tb_cache[(p, i)]["text_search"] for k, i in zip(keys, idxs)}})
    return nodes


def seg_score(a, b):
    common = [k for k in a["ts"] if k in b["ts"]]
    if not common or len(common) < 0.5 * min(len(a["ts"]), len(b["ts"])):
        return 0.0
    step = max(1, len(common) // 150)
    sims = [SequenceMatcher(None, a["ts"][k], b["ts"][k]).ratio() for k in common[::step]]
    return sum(sims) / len(sims)


def cluster_nodes(nodes):
    par = list(range(len(nodes)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if seg_score(nodes[i], nodes[j]) >= SEG_SCORE_MIN:
                par[find(j)] = find(i)
    groups = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        groups[find(i)].append(n)
    return sorted(groups.values(), key=lambda g: min((n["path"], n["seg"]) for n in g))


def name_claims(rec):
    nm = rec["law_name"].replace("_", " ")
    mn, my = NAME_NUM.search(nm), NAME_YEAR.search(nm)
    bad = []
    if mn and rec["law_number"] and str(rec["law_number"]) != mn.group(1):
        bad.append(f"name says no.{mn.group(1)}, field law_number={rec['law_number']}")
    elif my and not mn and rec["law_year"] and str(rec["law_year"]) != my.group(1):
        bad.append(f"name says year {my.group(1)}, field law_year={rec['law_year']}")
    return bad


def build_law_clusters(arch, paths):
    tb = {}
    nodes = build_nodes(arch, paths, tb)
    instruments, articles = [], []
    stats = {"clusters": 0, "raw_records": 0, "articles": 0, "status": collections.Counter(),
             "basis": collections.Counter(), "severity": collections.Counter()}
    for grp in cluster_nodes(nodes):
        anchor = min(f"{n['path']}#{n['seg']}" for n in grp)
        inst_id = "inst:lb:" + hashlib.sha1(anchor.encode()).hexdigest()[:10]
        names, claims, flags = collections.Counter(), collections.Counter(), []
        for n in grp:
            first = arch.record(n["path"], n["idxs"][0])
            names[first["law_name"]] += 1
            claims[f"{first['law_number']}/{first['law_year']}"] += 1
            for b in name_claims(first):
                flags.append({"flag": "name_number_mismatch", "file": n["path"], "detail": b})
        sel = sorted(names.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
        if re.search(r"[A-Za-z*/=]", sel):
            flags.append({"flag": "law_name_contains_extraction_artifacts", "detail": sel})
        cat = grp[0]["path"].split("/")[2]
        first_rec = arch.record(grp[0]["path"], grp[0]["idxs"][0])
        lineages = collections.defaultdict(list)
        for n in grp:
            lineages[n["lineage"]].append(n)
        inst = {
            "id": inst_id, "record_type": "law_instrument", "schema_version": PIPELINE_VERSION,
            "folder_category": cat,
            "name": {"selected": sel, "candidates": dict(names), "selection_rule": "most frequent, then shortest",
                     "status": "unverified"},
            "title_hint": first_rec["content"][:90],
            "identity_status": "candidate_unverified",
            "legacy_claims": {"law_number_year": dict(claims), "note": "claims copied from source; NOT verified"},
            "segmentation_basis": "numbering_restart" if any(n["seg"] > 0 for n in grp) else "none",
            "members": [{"path": n["path"], "segment": n["seg"], "n_records": len(n["idxs"]),
                         "lineage_id": n["lineage"]} for n in grp],
            "legal_status": "not_assessed",
        }
        if len(claims) > 1:
            flags.append({"flag": "members_disagree_on_law_number_year", "detail": dict(claims)})
        for f in flags:
            review(inst_id, "law_instrument", "high", f["flag"], f)
        if any(n["seg"] > 0 for n in grp):
            review(inst_id, "law_instrument", "medium", "segment_split_is_heuristic",
                   "numbering restart used to split file; confirm these are separate instruments")
        inst["review_flags"] = flags
        inst["provenance"] = prov([{"raw_ref": arch.ref(n["path"], n["idxs"][0])} for n in grp[:1]],
                                  [{"step": "T06", "op": "segment_by_numbering_restart"},
                                   {"step": "T04", "op": "cluster_segments_by_aligned_text_similarity",
                                    "detail": f">= {SEG_SCORE_MIN}"}])
        instruments.append(inst)
        # ---- articles
        agg = {}

        def note(reason, sev, aid, ex=None):
            a_ = agg.setdefault(reason, {"severity": sev, "count": 0, "examples": []})
            a_["count"] += 1
            if len(a_["examples"]) < 5:
                a_["examples"].append(aid if ex is None else {"id": aid, "detail": ex})
        keyorder, entries = [], collections.defaultdict(list)
        for n in grp:
            for k, i in zip(n["keys"], n["idxs"]):
                if k not in entries:
                    keyorder.append(k)
                entries[k].append((n, i))
        for k in keyorder:
            groups = collections.defaultdict(list)
            for n, i in entries[k]:
                groups[tb[(n["path"], i)]["text_search"]].append((n, i))
            ranked = sorted(groups.items(), key=lambda kv: (
                -len({n["lineage"] for n, _ in kv[1]}), min((n["path"], i) for n, i in kv[1])))
            lead_lin = len({n["lineage"] for n, _ in ranked[0][1]})
            total = sum(len(v) for v in groups.values())
            if total == 1:
                basis = "only_source"
            elif len(groups) == 1:
                basis = "unanimous"
            elif len(ranked) > 1 and len({n["lineage"] for n, _ in ranked[1][1]}) == lead_lin:
                basis = "tie_unresolved"
            else:
                basis = "majority_of_independent_lineages"
            cn, ci = min(ranked[0][1], key=lambda e: (e[0]["path"], e[1]))
            ctb = tb[(cn["path"], ci)]
            crec = arch.record(cn["path"], ci)
            originals = {tb[(n["path"], i)]["text_original"] for n, i in entries[k]}
            if total == 1:
                vstatus = "single_source"
            elif len(originals) == 1:
                vstatus = "identical"
            elif len(groups) == 1:
                vstatus = "formatting_only_differences"
            else:
                vstatus = "conflicting_variants"
            srcs, variants, minsim = [], [], 1.0
            for ts, ents in ranked:
                for n, i in sorted(ents, key=lambda e: (e[0]["path"], e[1])):
                    t = tb[(n["path"], i)]
                    role = ("canonical" if (n, i) == (cn, ci) else
                            "identical_copy" if t["text_original"] == ctb["text_original"] else "variant")
                    srcs.append({"raw_ref": arch.ref(n["path"], i), "lineage_id": n["lineage"], "role": role})
            vmap = collections.defaultdict(list)
            for ts, ents in ranked:
                for n, i in ents:
                    o = tb[(n["path"], i)]["text_original"]
                    if o != ctb["text_original"]:
                        vmap[(ts, o)].append((n, i))
            for (ts, o), ents in sorted(vmap.items(), key=lambda kv: min((e[0]["path"], e[1]) for e in kv[1])):
                textual = ts != ranked[0][0]
                sim = SequenceMatcher(None, ctb["text_search"], ts).ratio() if textual else 1.0
                if textual:
                    minsim = min(minsim, sim)
                variants.append({"text_original": o, "kind": "textual" if textual else "formatting_only",
                                 "similarity_to_canonical": round(sim, 4),
                                 "raw_paths": sorted({n["path"] + f"#{i}" for n, i in ents})})
            aid = f"art:{inst_id}:{k[0]}" + (f"~{k[1]}" if k[1] else "")
            tr = [{"step": "T01", "op": "assign_stable_id"},
                  {"step": "T02", "op": "text_clean", "ops": ctb["clean_ops"]},
                  {"step": "T03", "op": "text_search", "pipeline": "search_v1"}]
            cflags, rflags = [], list(ctb["flags"])
            if len(srcs) > 1:
                tr.append({"step": "T04", "op": "merge_identical_or_aligned_sources", "n_sources": len(srcs)})
            if vstatus == "conflicting_variants":
                sev = ("minor_textual_difference" if minsim >= 0.97 else
                       "moderate_difference" if minsim >= 0.85 else "major_difference")
                cflags.append({"flag": "conflicting_variants", "severity": sev,
                               "min_similarity": round(minsim, 4), "basis": basis})
                tr.append({"step": "T05", "op": "variants_preserved", "n_variants": len(variants)})
                stats["severity"][sev] += 1
                CONFLICTS.append({"id": aid, "type": "law_article_variants", "basis": basis,
                                  "severity": sev, "min_similarity": round(minsim, 4)})
                note(f"conflicting_variants/{basis}/{sev}", "high" if (basis == "tie_unresolved" or sev == "major_difference") else "medium", aid)
            if ctb["extras"]:
                rflags.append("uncertain_auto_correction:trailing_breadcrumb_extracted")
                note("breadcrumb_extracted_from_clean_text", "low", aid, ctb["extras"]["breadcrumb_candidate"])
            if k[1]:
                rflags.append("duplicate_article_number_in_segment")
                note("duplicate_article_number_in_segment", "medium", aid)
            for fl in ctb["flags"]:
                note(fl, "low", aid)
            articles.append({
                "id": aid, "record_type": "law_article", "schema_version": PIPELINE_VERSION,
                "source_family": "lexbridge", "instrument_id": inst_id,
                "article_number": {"original": crec["article_number"], "canonical": k[0], "occurrence": k[1]},
                "text_original": ctb["text_original"], "text_clean": ctb["text_clean"],
                "text_search": ctb["text_search"], "clean_extras": ctb["extras"],
                "resolution": {"variant_status": vstatus, "canonical_basis": basis,
                               "distinct_variants": len(groups)},
                "variants": variants,
                "provenance": prov(srcs, tr, conflicts=cflags, flags=rflags,
                                   text_status="source_verbatim_extracted_from_doc"),
            })
            stats["status"][vstatus] += 1
            stats["basis"][basis] += 1
            stats["raw_records"] += len(srcs)
        for reason, v in sorted(agg.items()):
            review(inst_id, "law_instrument_aggregate", v["severity"], reason,
                   {"count": v["count"], "examples": v["examples"]})
        stats["clusters"] += 1
    stats["articles"] = len(articles)
    return instruments, articles, stats


# ------------------------------------------------------------ egypt-law
def import_egypt_constitution(eg):
    ver = None
    for p in ("data/versions.json", "data/laws.csv", "data/repo.json"):
        pass
    try:
        ver = json.loads(eg.read_bytes("data/versions.json").decode("utf-8"))
    except Exception as e:  # recorded, not fatal
        ver = {"error": str(e)}
    inst_id = "inst:eg:constitution-2014"
    base = {"source_family": "egypt-law", "schema_version": PIPELINE_VERSION}
    inst = {
        "id": inst_id, "record_type": "law_instrument", "kind": "constitution", "jurisdiction": "EG",
        "name": {"ar": "دستور جمهورية مصر العربية", "en": "Constitution of the Arab Republic of Egypt",
                 "status": "title assigned by pilot from upstream folder names; verify"},
        "identity_status": "source_asserted",
        "source_stated": {"versions_json": ver, "note":
                          "copied from upstream data/versions.json; NOT independently verified by LexBridge"},
        "legal_status": "not_assessed",
        "primary_language": "ar", "translations": ["en"],
        "provenance": prov([{"raw_ref": eg.ref("data/versions.json")}],
                           [{"step": "T01", "op": "assign_stable_id"}]),
    }
    inst.update({k: v for k, v in base.items() if k not in inst})
    ar_keys = {os.path.basename(p)[:-3]: p for p in eg.list("dustur")}
    en_keys = {os.path.basename(p)[:-3]: p for p in eg.list("constitution")}

    def canon(key):
        return re.sub(r"^art-0*(\d+)", r"\1", key)

    def parts(path):
        t = eg.read_bytes(path).decode("utf-8")
        head, _, body = t.partition("\n")
        return head, body[:-1] if body.endswith("\n") else body

    arts = []
    en_text = {}
    for k, p in sorted(en_keys.items()):
        head, body = parts(p)
        en_text[k] = body
    for k, p in sorted(ar_keys.items()):
        c = canon(k)
        head, body = parts(p)
        tb = text_block(body)
        ref = eg.ref(p)
        link = None
        if k in en_keys:
            link = {"target": f"art:eg:const2014:en:{canon(k)}", "status": "linked_same_key"}
        else:
            m = re.match(r"art-0*(\d+)-bis", k)
            parent = f"art-{int(m.group(1)):03d}" if m else None
            pat = re.compile(rf"Article\s+{int(m.group(1))}\s*\(bis\)", re.I) if m else None
            if parent in en_text and pat.search(en_text[parent]):
                link = {"target": f"art:eg:const2014:en:{canon(parent)}",
                        "status": "embedded_in_parent_article",
                        "evidence": "pattern 'Article N (bis)' found inside the English parent article"}
            else:
                link = {"target": None, "status": "no_translation_found"}
                review(f"art:eg:const2014:ar:{c}", "constitution", "medium", "no_english_counterpart")
        arts.append({
            "id": f"art:eg:const2014:ar:{c}", "record_type": "constitution_article", "language": "ar",
            "instrument_id": inst_id, "article_number": {"original_heading": head, "canonical": c},
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "clean_extras": tb["extras"], "translation": link, "authoritative": True,
            "provenance": prov([{"raw_ref": ref}], [
                {"step": "T01", "op": "assign_stable_id"},
                {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]},
                {"step": "T03", "op": "text_search", "pipeline": "search_v1"},
                {"step": "T00", "op": "heading_split_and_final_newline_removed",
                 "detail": "heading kept in article_number.original_heading; file terminator not part of text"}],
                text_status="source_verbatim_upstream_normalized",
                note="upstream already normalised typography (e.g. tatweel removed, heading rewritten)"),
            **base})
    for k, p in sorted(en_keys.items()):
        c = canon(k)
        head, body = parts(p)
        tb = text_block(body)
        arts.append({
            "id": f"art:eg:const2014:en:{c}", "record_type": "constitution_article", "language": "en",
            "instrument_id": inst_id, "article_number": {"original_heading": head, "canonical": c},
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "clean_extras": tb["extras"], "authoritative": False,
            "is_translation_of": f"art:eg:const2014:ar:{c}" if k in ar_keys else None,
            "translation_status": "upstream_translation_not_authoritative",
            "provenance": prov([{"raw_ref": eg.ref(p)}], [
                {"step": "T01", "op": "assign_stable_id"}, {"step": "T12", "op": "link_to_arabic_article"},
                {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}],
                text_status="translation_not_authoritative"),
            **base})
    return inst, arts


# ------------------------------------------------------------- judgments
def load_all(arch, prefix):
    out = []
    for p in arch.list(prefix):
        for i, r in enumerate(arch.records(p)):
            out.append((p, i, r))
    return out


def judgments_dry_run(arch):
    J = load_all(arch, "knowledge/judgments/")
    rows, by_new, legacy_map = [], collections.defaultdict(list), collections.defaultdict(set)
    for p, i, r in J:
        nid, complete = judgment_new_id(r, p)
        by_new[nid].append((p, i, r, complete))
        legacy_map[r["id"]].add(nid)
    for nid, mem in by_new.items():
        for p, i, r, complete in mem:
            if len(legacy_map[r["id"]]) > 1:
                st = "collision_resolved"
            elif len(mem) > 1:
                st = "merged_duplicate"
            elif not complete:
                st = "identity_incomplete"
            else:
                st = "unique"
            rows.append((r["id"], p, i, nid, len(mem), st))
    rows.sort(key=lambda x: (x[1], x[2]))
    return J, by_new, legacy_map, rows


def build_judgments(arch, J, by_new, legacy_map, all_ids):
    sel = set()
    for lid, nids in sorted(legacy_map.items()):
        if len(nids) > 1:
            sel |= nids
    merged = sorted((v for v in by_new.values() if len(v) > 1), key=lambda v: (v[0][0], v[0][1]))
    for br, n in (("/criminal", 3), ("/civil", 2)):
        c = 0
        for v in merged:
            if br in v[0][0] and c < n:
                sel.add(judgment_new_id(v[0][2], v[0][0])[0]); c += 1
    sel.add(judgment_new_id(max(merged, key=len)[0][2], max(merged, key=len)[0][0])[0])
    th = collections.defaultdict(set)
    for p, i, r in J:
        th[h8(r["content"])].add(judgment_new_id(r, p)[0])
    same_text = {h: v for h, v in th.items() if len(v) > 1}
    cnt = 0
    for h, v in sorted(same_text.items()):
        mem = [m for nid in v for m in by_new[nid]]
        if all(m[3] for m in mem) and cnt < 3:
            sel |= v; cnt += 1
    cnt = 0
    for h, v in sorted(same_text.items()):
        mem = [m for nid in v for m in by_new[nid]]
        if all(not m[2]["citations"] for m in mem) and cnt < 3:
            sel |= v; cnt += 1
    cnt = 0
    for nid, mem in sorted(by_new.items()):
        if not mem[0][3] and cnt < 3:
            sel.add(nid); cnt += 1
    out = []
    law_ids = all_ids["laws"]
    for nid in sorted(sel):
        mem = sorted(by_new[nid], key=lambda m: (m[0], m[1]))
        pick = sorted(mem, key=lambda m: (m[2].get("category") in ("uncategorized", "uncategorized_pool")
                                          or "uncategorized" in m[0], m[0], m[1]))[0]
        p, i, r, complete = pick
        tb = text_block(r["content"])
        refs_legacy = {k: r.get(k, []) for k in ("related_ids", "related_judgments") if r.get(k)}
        resolved, ambiguous, unresolved, self_dropped = [], [], [], 0
        for lid in dict.fromkeys(x for v in refs_legacy.values() for x in v):
            c = legacy_map.get(lid)
            if c is None:
                (unresolved if lid not in all_ids["other"] else resolved).append(lid)
            elif len(c) == 1:
                x = next(iter(c))
                if x == nid:
                    self_dropped += 1
                elif x not in resolved:
                    resolved.append(x)
            else:
                ambiguous.append({"legacy": lid, "candidates": sorted(c)})
        for a in ambiguous:
            review(nid, "judgment_reference", "medium", "ambiguous_reference_to_collided_legacy_id", a)
        law_refs = r.get("related_articles", [])
        law_status = collections.Counter("valid_legacy_law_id" if x in law_ids else "dangling" for x in law_refs)
        shared = sorted(legacy_map[r["id"]] - {nid})
        cflags = []
        if shared:
            cflags.append({"flag": "legacy_id_collision", "other_new_ids": shared,
                           "meaning": "same case/volume/page/paragraph carries different principle texts"})
            CONFLICTS.append({"id": nid, "type": "judgment_id_collision", "legacy_id": r["id"], "siblings": shared})
        tr = [{"step": "T01", "op": "assign_stable_id", "rule": "branch+identity+hash8(text)"},
              {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]},
              {"step": "T03", "op": "text_search", "pipeline": "search_v1"},
              {"step": "T11", "op": "rewrite_references", "resolved": len(resolved), "ambiguous": len(ambiguous)},
              {"step": "T10", "op": "label_derived_fields"}]
        rflags = []
        if len(mem) > 1:
            tr.append({"step": "T04", "op": "merge_same_identity_and_text", "n_sources": len(mem)})
        if not complete:
            rflags.append("identity_incomplete_never_merged_by_rule")
            review(nid, "judgment", "medium", "identity_incomplete")
        if not r["citations"]:
            rflags.append("no_citation_in_source")
        same = sorted(th[h8(r["content"])] - {nid})
        if same:
            rflags.append("same_text_as_other_distinct_judgments")
            review(nid, "judgment", "low", "same_text_not_merged_distinct_identity", same)
        out.append({
            "id": nid, "record_type": "judgment_principle", "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "branch": judgment_branch(p),
            "identity": dict(zip(("case", "year", "volume", "page", "paragraph"), judgment_identity(r, p))),
            "legacy_ids": sorted({m[2]["id"] for m in mem}),
            "title_original": r.get("title"), "category_original": r.get("category"),
            "categories_seen": sorted({m[2].get("category") for m in mem}),
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "citations_original": r["citations"],
            "same_text_as": same,
            "references": {"legacy": refs_legacy, "resolved": resolved, "ambiguous": ambiguous,
                           "unresolved": unresolved, "self_references_dropped": self_dropped,
                           "law_refs_legacy": law_refs, "law_refs_status": dict(law_status),
                           "law_refs_note": "law ids will be remapped when laws are migrated (full run)"},
            "field_status": field_status(r.get("source_fields", {}).keys()),
            "legacy": {"metadata": r.get("metadata"), "keywords": r.get("keywords"),
                       "source_fields": r.get("source_fields")},
            "provenance": prov(
                [{"raw_ref": arch.ref(m[0], m[1]), "legacy_id": m[2]["id"],
                  "role": "canonical" if m is pick else "identical_duplicate"} for m in mem],
                tr, conflicts=cflags, flags=rflags, text_status="source_verbatim"),
        })
    return out


# ------------------------------------------------------ small collections
def pick_strat(rows, key, n_extra=0):
    seen, out = set(), []
    for x in sorted(rows, key=lambda x: (key(x), x[2]["id"])):
        if key(x) not in seen:
            seen.add(key(x)); out.append(x)
    rest = [x for x in sorted(rows, key=lambda x: x[2]["id"]) if x not in out]
    return out + rest[:n_extra]


def resolve_refs(lst, legacy_map):
    res, amb = [], []
    for lid in dict.fromkeys(lst):
        c = legacy_map.get(lid)
        if c and len(c) == 1:
            res.append(next(iter(c)))
        elif c:
            amb.append({"legacy": lid, "candidates": sorted(c)})
    return list(dict.fromkeys(res)), amb


def small_collections(arch, legacy_map):
    out = {}
    # templates: all 7 -----------------------------------------------------
    T = load_all(arch, "knowledge/templates/")
    recs = []
    for p, i, r in T:
        sf = r["source_fields"]
        body = sf.get("template_body", "")
        tb = text_block(body)
        ph = sorted(set(re.findall(r"\{(\w+)\}", body)))
        fields = [f["field"] for f in sf.get("fields", [])]
        unused = sorted(set(fields) - set(ph))
        undeclared = sorted(set(ph) - set(fields))
        if unused or undeclared:
            review(r["id"], "template", "low", "placeholder_field_mismatch",
                   {"declared_but_unused": unused, "used_but_undeclared": undeclared})
        recs.append({
            "id": r["id"], "record_type": "legal_template", "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "title": r["title"], "template_category": sf.get("branch"),
            "content_status": "recovered_from_field" if body else "empty_in_source",
            "text_original": body, "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "recovered_from": "source_fields.template_body",
            "required_information": sf.get("fields", []), "auto_includes": sf.get("auto_includes", []),
            "placeholders_in_body": ph,
            "legal_references": [], "legal_references_status": "absent_in_source",
            "linked_procedure_id": sf.get("procedure_id"),
            "authorship": "lexbridge_internal_per_PROVENANCE_md",
            "legacy": {"content": r["content"], "source_fields": sf, "metadata": r["metadata"]},
            "provenance": prov([{"raw_ref": arch.ref(p, i)}], [
                {"step": "T07", "op": "recover_content_from_field", "from": "source_fields.template_body",
                 "to": "text_original", "original_field_preserved": True, "legacy_content_was_empty": not r["content"]},
                {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}], text_status="recovered_from_field"),
        })
    out["templates"] = recs
    # defenses ---------------------------------------------------------------
    D = pick_strat(load_all(arch, "knowledge/defenses/"), lambda x: x[2]["category"], 0)
    recs = []
    for p, i, r in [(x[0], x[1], x[2]) for x in D]:
        res, amb = resolve_refs(r.get("related_judgments", []) + r.get("related_ids", []), legacy_map)
        title_only = r["content"].strip() == r["title"].strip() or len(r["content"].strip()) < 60
        if title_only:
            review(r["id"], "defense", "high", "title_only_no_substantive_content")
        recs.append({
            "id": r["id"], "record_type": "legal_defense", "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "title": r["title"], "category_original": r["category"],
            "content_status": "title_only" if title_only else "has_content",
            "incomplete": title_only, "text_original": r["content"],
            "legal_basis": [], "legal_basis_status": "absent_in_source",
            "supporting_judgments": {"resolved": res, "ambiguous": amb, "count_legacy": len(r.get("related_judgments", []))},
            "supporting_legislation": r.get("related_articles", []),
            "field_status": field_status(r.get("source_fields", {}).keys()),
            "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields")},
            "provenance": prov([{"raw_ref": arch.ref(p, i)}], [
                {"step": "T08", "op": "mark_title_only", "detail": "no text was added or generated"},
                {"step": "T11", "op": "rewrite_references"}], flags=["title_only"] if title_only else [],
                text_status="title_only" if title_only else "lexbridge_internal"),
        })
    out["defenses"] = recs
    # procedures ---------------------------------------------------------------
    P = load_all(arch, "knowledge/procedures/")
    P_ = []
    for typ, n in (("procedure", 2), ("procedure_deep", 2), ("procedure_guide", 4)):
        P_ += sorted([x for x in P if x[2]["type"] == typ], key=lambda x: x[2]["id"])[:n]
    label_re = re.compile(r"^([\u0600-\u06ff ]{2,25}):")
    allg = [x for x in P if x[2]["type"] == "procedure_guide"]
    lc = collections.Counter()
    for _, _, r in allg:
        lc.update({m.group(1) for l in r["content"].split("\n") if not EMOJI.match(l) and (m := label_re.match(l))})
    labels = {l for l, c in lc.items() if c >= 0.5 * len(allg)}
    recs = []
    for p, i, r in P_:
        tb = text_block(r["content"])
        d = {}
        tr = [{"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}]
        if r["type"] == "procedure_guide":
            lines = r["content"].split("\n")
            formal = [l for l in lines if l.strip() and not EMOJI.match(l)]
            colloq = [l for l in lines if l.strip() and EMOJI.match(l)]
            sections, cur = {}, "_preamble"
            for l in formal:
                m = label_re.match(l)
                if m and m.group(1) in labels:
                    cur = m.group(1)
                sections.setdefault(cur, []).append(l)
            d = {"formal_lines": formal, "colloquial_lines": colloq, "sections": sections,
                 "note": "verbatim line subsets of text_original; nothing rewritten"}
            tr.append({"step": "T13", "op": "split_formal_vs_colloquial_layers", "rule": "line starts with emoji"})
        recs.append({
            "id": r["id"], "record_type": r["type"], "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "title": r["title"], "category_original": r["category"],
            "registered_in_registry": r["type"] != "procedure_guide",
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "derived_layers": d, "authorship": "lexbridge_internal_per_PROVENANCE_md",
            "related": {k: r.get(k) for k in ("related_ids", "related_procedures", "related_articles") if r.get(k)},
            "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields"),
                       "migration_note": r.get("_related_migration_note")},
            "provenance": prov([{"raw_ref": arch.ref(p, i)}], tr, text_status="lexbridge_internal"),
        })
        if r["type"] == "procedure_guide":
            review(r["id"], "procedure", "low", "type_missing_from_registry_pilot_proposes_adding")
    out["procedures"] = recs
    # deadlines ----------------------------------------------------------------
    Dl = pick_strat(load_all(arch, "knowledge/deadlines/"), lambda x: x[2]["category"], 1)
    recs = []
    for p, i, r in [(x[0], x[1], x[2]) for x in Dl]:
        sf = r["source_fields"]
        keys = ("trigger_event", "calculation_method", "legal_text")
        for k in keys:
            if not sf.get(k):
                review(r["id"], "deadline", "medium", f"missing_{k}")
        recs.append({
            "id": r["id"], "record_type": "deadline", "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "title": r["title"], "category_original": r["category"],
            "deadline": {"duration_text": sf.get("duration"), "duration_days": sf.get("duration_days"),
                         "deadline_type": sf.get("deadline_type")},
            "starting_event": sf.get("trigger_event"), "start_rule": sf.get("start_date_rule"),
            "calculation_method": sf.get("calculation_method"), "end_condition": sf.get("end_condition"),
            "exceptions": sf.get("exceptions", []), "interruptions": sf.get("interruptions", []),
            "suspension_causes": sf.get("suspension_causes", []),
            "legal_authority": {"article_number_claimed": r["metadata"].get("article_number"),
                                "references_claimed": sf.get("related_articles", []),
                                "legal_text_claimed": sf.get("legal_text"),
                                "authority_body": sf.get("court_or_authority"),
                                "status": "unverified_not_confirmed_as_verbatim_statute"},
            "text_original": r["content"],
            "field_status": field_status(sf.keys()),
            "legacy": {"metadata": r["metadata"], "source_fields": sf},
            "provenance": prov([{"raw_ref": arch.ref(p, i)}], [
                {"step": "T14", "op": "map_fields_to_deadline_schema",
                 "detail": "renames/groups only; no values changed"},
                {"step": "T10", "op": "label_derived_fields"}], text_status="lexbridge_internal"),
        })
    out["deadlines"] = recs
    # principles ---------------------------------------------------------------
    Pr = pick_strat(load_all(arch, "knowledge/principles/"), lambda x: x[2]["category"], 2)
    recs = []
    for p, i, r in [(x[0], x[1], x[2]) for x in Pr]:
        tb = text_block(r["content"])
        recs.append({
            "id": r["id"], "record_type": "legal_principle_secondary", "schema_version": PIPELINE_VERSION,
            "source_family": "lexbridge", "title": r["title"], "category_original": r["category"],
            "language": "en", "authoritative": False, "text_status": "secondary_source_paraphrase",
            "source_work_claimed": r["metadata"].get("source"),
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "original_language_text": None,
            "statutory_references_claimed": r.get("related_articles", []),
            "supporting_judgments": [], "supporting_judgments_status": "none_in_source",
            "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields"), "keywords": r.get("keywords")},
            "provenance": prov([{"raw_ref": arch.ref(p, i)}], [
                {"step": "T09", "op": "label_secondary_paraphrase"},
                {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}], text_status="secondary_source_paraphrase"),
        })
        review(r["id"], "principle", "low", "english_secondary_paraphrase_no_arabic_source_text")
    out["principles"] = recs
    return out


# ------------------------------------------------------------------ main
def main():
    global IMPORT_DATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    ap.add_argument("--egypt-zip", default="/mnt/user-data/uploads/egypt-law-a9a9f589c7537c1ff1796795ac87efbbd042c95a.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--import-date", default="2026-11-22")
    a = ap.parse_args()
    IMPORT_DATE = a.import_date
    lb, eg = LexArchive(a.lexbridge_zip), EgyptArchive(a.egypt_zip)

    # laws
    paths = []
    for folder, n in PILOT_LAW_FILES:
        paths += [p for p in lb.list(f"knowledge/laws/{folder}/") if len(lb.records(p)) == n]
    instruments, articles, lstats = build_law_clusters(lb, paths)
    # egypt-law
    e_inst, e_arts = import_egypt_constitution(eg)
    # mark LB constitutional instruments
    lb_const = []
    for inst in instruments:
        if inst["folder_category"] == "constitutional":
            txt = " ".join(x["text_original"] for x in articles if x["instrument_id"] == inst["id"])
            inst.update({"domain_hint": "constitutional (from folder)", "identity_status": "unidentified",
                         "version_status": "unestablished", "legal_status": "not_assessed",
                         "reviewer_hint": {"occurrences_مجلس_الشعب": txt.count("مجلس الشعب"),
                                           "occurrences_مجلس_النواب": txt.count("مجلس النواب"),
                                           "note": "textual indicators only; not a classification"}})
            review(inst["id"], "constitution", "high", "identity_and_version_of_lexbridge_constitution_unestablished",
                   inst["reviewer_hint"])
            lb_const.append(inst["id"])
    # cross-source overlap statistic (no links created)
    ar_by = {x["article_number"]["canonical"]: x for x in e_arts if x["language"] == "ar"}
    sims = []
    for x in articles:
        if x["instrument_id"] in lb_const and x["article_number"]["canonical"] in ar_by:
            sims.append(SequenceMatcher(None, x["text_search"], ar_by[x["article_number"]["canonical"]]["text_search"]).ratio())
    overlap = {"same_number_pairs": len(sims), "median_similarity": round(statistics.median(sims), 3) if sims else None,
               "pairs_ge_0_95": sum(s >= .95 for s in sims), "pairs_lt_0_5": sum(s < .5 for s in sims),
               "links_created": 0, "policy": "never match or overwrite constitutions by article number"}
    CONFLICTS.append({"type": "constitution_cross_source_number_overlap", **overlap})
    # judgments
    J, by_new, legacy_map, rows = judgments_dry_run(lb)
    all_ids = {"laws": {r["id"] for _, _, r in load_all(lb, "knowledge/laws/")},
               "other": {r["id"] for pre in ("principles", "procedures", "deadlines", "defenses", "templates")
                         for _, _, r in load_all(lb, f"knowledge/{pre}/")}}
    judg = build_judgments(lb, J, by_new, legacy_map, all_ids)
    small = small_collections(lb, legacy_map)

    out = a.out
    write_jsonl(f"{out}/canonical/legislation/instruments.jsonl", [e_inst] + instruments)
    write_jsonl(f"{out}/canonical/legislation/articles_lexbridge.jsonl", articles)
    write_jsonl(f"{out}/canonical/legislation/articles_egypt_law_constitution.jsonl", e_arts)
    write_jsonl(f"{out}/canonical/judgments/judgment_principles.jsonl", judg)
    for name, rows_ in small.items():
        write_jsonl(f"{out}/canonical/{name}/{name}.jsonl", rows_)
    # full ID dry-run mapping (mapping only; no records emitted for non-pilot judgments)
    os.makedirs(f"{out}/mappings", exist_ok=True)
    with gzip.GzipFile(f"{out}/mappings/judgment_id_map_full_dryrun.csv.gz", "wb", mtime=0) as gz:
        import io
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["legacy_id", "source_path", "source_index", "new_id", "group_size", "status"])
        w.writerows(rows)
        gz.write(buf.getvalue().encode("utf-8"))
    dry = collections.Counter(r[5] for r in rows)
    ref_total = collections.Counter()
    for p, i, r in J:
        for k in ("related_ids", "related_judgments"):
            for x in r.get(k, []):
                c = legacy_map.get(x)
                ref_total["dangling_or_non_judgment" if c is None else "resolved" if len(c) == 1 else "ambiguous"] += 1
    summary = {
        "pipeline_version": PIPELINE_VERSION, "import_date": IMPORT_DATE,
        "archives": {"lexbridge": {"sha256": lb.sha256}, "egypt_law": {"sha256": eg.sha256, "source_commit": eg.commit}},
        "laws": {"files_in_pilot": len(paths), "raw_records": lstats["raw_records"], "canonical_articles": lstats["articles"],
                 "instrument_candidates": lstats["clusters"], "variant_status": dict(lstats["status"]),
                 "canonical_basis": dict(lstats["basis"]), "conflict_severity": dict(lstats["severity"])},
        "egypt_constitution": {"ar_records": sum(1 for x in e_arts if x["language"] == "ar"),
                               "en_records": sum(1 for x in e_arts if x["language"] == "en"),
                               "translation_links": dict(collections.Counter(x["translation"]["status"] for x in e_arts if x["language"] == "ar"))},
        "constitution_cross_source_overlap": overlap,
        "judgments_dry_run_full_set": {"raw_records": len(J), "unique_new_ids": len(by_new), "status": dict(dry),
                                       "legacy_id_collisions": sum(1 for v in legacy_map.values() if len(v) > 1),
                                       "reference_resolution_full_set": dict(ref_total)},
        "judgments_pilot": {"canonical_records": len(judg), "raw_records": sum(len(x["provenance"]["sources"]) for x in judg)},
        "small_collections": {k: len(v) for k, v in small.items()},
    }
    write_json(f"{out}/reports/build_summary.json", summary)
    write_json(f"{out}/reports/conflicts.json", CONFLICTS)
    write_json(f"{out}/reports/human_review_list.json", REVIEW)
    write_json(f"{out}/registry/pilot_registry_proposals.json", {
        "status": "PROPOSAL ONLY - not applied to any registry",
        "add_kb_type": [{"kb_type": "procedure_guide", "folder": "procedures/guides",
                         "reason": "50 records of this type exist but are not in document-types.registry.json"}],
        "add_record_types": ["law_instrument", "law_article", "constitution_article", "judgment_principle",
                             "legal_template", "legal_defense", "deadline", "legal_principle_secondary"]})
    # manifest of outputs (for idempotency check)
    man = {}
    for root, _, files in os.walk(out):
        for f in sorted(files):
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, out)
            if rel.startswith(("scripts", "docs", "reports/BEFORE_AFTER", "reports/validation", "OUTPUT_MANIFEST", "PILOT_REPORT", "README")):
                continue
            man[rel] = hashlib.sha256(open(fp, "rb").read()).hexdigest()
    write_json(f"{out}/OUTPUT_MANIFEST.json", man)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
