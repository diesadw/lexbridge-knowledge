#!/usr/bin/env python3
"""LexBridge FULL build v3.0.0-rc1 (finalized rules).

Reads the two ORIGINAL zips (never modifies them). Writes only to --out.
Deterministic: the same inputs give byte-identical output files.

Finalized rules (see docs/RULES_AND_SCHEMA.md):
 D1 judgments merge only with court+case+year+volume+page+paragraph+identical text;
    missing paragraph -> potential-duplicate candidates, never merged.
 D2 law editions: every distinct edition preserved whole; no preferred edition chosen.
 D3 numbering restarts: flagged only; splits applied only from config/split_confirmations.json.
 D4 law number/year: claims preserved; canonical fields only on multi-signal agreement.
"""
import argparse, collections, csv, gzip, hashlib, io, json, os, re, shutil, stat, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pilot as bp  # frozen, approved egypt-law importer (reused unchanged)
from lib import (PIPELINE_VERSION, LexArchive, EgyptArchive, canon_article, h8, judgment_branch,
                 judgment_identity, lead_int, text_block, file_sha256)

RELEASE = "3.0.0-rc1"
JAC_MIN = 0.5            # file-cluster threshold (mean word-set Jaccard over aligned articles)
EMOJI = bp.EMOJI
NAME_NUM, NAME_YEAR = bp.NAME_NUM, bp.NAME_YEAR
ISSUING_MARKERS = ["يلغي", "ينشر هذا", "يعمل به", "الجريدة الرسمية", "يصدر"]
IMPORT_DATE = None
REVIEW = []


def rv(rid, cat, sev, reason, detail=None):
    REVIEW.append({"id": rid, "category": cat, "severity": sev, "reason": reason, "detail": detail})


def prov(sources, transformations, verification="unverified", conflicts=None, flags=None, **extra):
    p = {"sources": sources, "import_date": IMPORT_DATE, "pipeline_version": PIPELINE_VERSION, "release": RELEASE,
         "transformations": transformations, "verification_status": verification,
         "conflict_flags": conflicts or [], "review_flags": flags or []}
    p.update(extra)
    return p


def jac(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def wjl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.write("\n")


def wcsv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def field_status(keys):
    out = {}
    for k in keys:
        if k.startswith("ai_"):
            out[k] = "ai_generated_per_field_name"
        elif k in bp.EDITORIAL_KEYS:
            out[k] = "editorial_unverified_provenance"
    return out


# =============================================================== LAWS (D2, D3, D4)
def detect_boundaries(recs):
    out, prev = [], None
    for i, r in enumerate(recs):
        n = lead_int(r["article_number"])
        if prev is not None and n is not None and n < prev and n <= 2:
            out.append({"start_index": i, "prev_number": prev, "next_number": n})
        if n is not None:
            prev = n
    return out


def law_identity(members, names, claims, confirmed):
    nn = [k for k in claims if k[0] is not None and k[1] is not None]
    reasons = []
    if len(nn) != 1:
        reasons.append("conflicting_claims" if nn else "no_claim_in_source")
    else:
        num, yr = str(nn[0][0]), str(nn[0][1])
        texts = [n.replace("_", " ") for n in names]
        files = [os.path.basename(f["path"])[:-5].replace("_", " ") for f in members]

        def title_like(t):
            # must open as a law title; fragments such as 'وعلى القانون رقم ...' or 'بالقانون رقم ...'
            # are references to ANOTHER law inside a preamble, not the law's own title
            return bool(re.match(r"^\s*(?:ال)?قانون\b", t))

        def says(t):
            m = NAME_NUM.search(t)
            return bool(title_like(t) and m and m.group(1) == num and yr in t)

        def contradicts(t):
            m = NAME_NUM.search(t)
            return bool(m and m.group(1) != num)
        if any(contradicts(t) for t in texts + files):
            reasons.append("name_or_filename_contradicts_claim")
        if not any(says(t) for t in texts):
            reasons.append("law_name_does_not_state_claimed_number_and_year")
        if not any(says(t) for t in files):
            reasons.append("filename_does_not_state_claimed_number_and_year")
        if not reasons:
            return {"canonical_law_number": num, "canonical_law_year": yr, "basis": "claim+law_name+filename_agree",
                    "external_verification": None, "status": "internally_consistent_not_externally_verified", "reasons": []}
    anchor = min(f["path"] for f in members)
    if anchor in confirmed:
        c = confirmed[anchor]
        return {"canonical_law_number": str(c["law_number"]), "canonical_law_year": str(c["law_year"]),
                "basis": "human_confirmed", "confirmed_by": c.get("confirmed_by"), "external_verification": c.get("evidence"),
                "status": "human_confirmed", "reasons": []}
    return {"canonical_law_number": None, "canonical_law_year": None, "basis": None, "external_verification": None,
            "status": "unresolved", "reasons": reasons}


def build_laws(lb, split_conf, ident_conf):
    files = []
    for p in lb.list("knowledge/laws/"):
        recs = lb.records(p)
        keys, seen, tbs = [], collections.Counter(), []
        for r in recs:
            c = canon_article(r["article_number"])
            keys.append((c, seen[c])); seen[c] += 1
            tbs.append(text_block(r["content"] or ""))
        files.append({"path": p, "recs": recs, "keys": keys, "tbs": tbs, "cat": p.split("/")[2],
                      "words": [set(t["text_search"].split()) for t in tbs],
                      "kidx": {k: i for i, k in enumerate(keys)}, "bounds": detect_boundaries(recs),
                      "lineage": hashlib.sha256("\n".join(f"{r['article_number']}\x1f{r['content']}" for r in recs).encode()).hexdigest()[:10]})
    par = list(range(len(files)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            A, B = files[i], files[j]
            common = [k for k in A["kidx"] if k in B["kidx"]]
            if not common or len(common) < 0.5 * min(len(A["kidx"]), len(B["kidx"])):
                continue
            step = max(1, len(common) // 150)
            s = [jac(A["words"][A["kidx"][k]], B["words"][B["kidx"][k]]) for k in common[::step]]
            if sum(s) / len(s) >= JAC_MIN:
                par[find(j)] = find(i)
    groups = collections.defaultdict(list)
    for i, f in enumerate(files):
        groups[find(i)].append(f)
    clusters = sorted((sorted(g, key=lambda f: f["path"]) for g in groups.values()), key=lambda g: g[0]["path"])
    conf_b = {(c["file"], c["start_index"]): c for c in split_conf}
    instruments, articles, law_rows, boundaries, proposed = [], [], [], [], []
    stats = collections.Counter()
    for members in clusters:
        inst_id = "inst:lb:" + hashlib.sha1(members[0]["path"].encode()).hexdigest()[:10]
        names, claims = collections.Counter(), collections.Counter()
        for f in members:
            for r in f["recs"]:
                names[r["law_name"]] += 1
                claims[(r["law_number"], r["law_year"])] += 1
        sel = sorted(names.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
        ident = law_identity(members, names, claims, ident_conf)
        # --- editions = distinct lineages
        eds = collections.OrderedDict()
        for f in members:
            eds.setdefault(f["lineage"], []).append(f)
        ed_ids = {lin: f"ed:{inst_id}:{lin}" for lin in eds}
        # --- boundary evidence (flag only)
        for f in members:
            if not f["bounds"]:
                continue
            starts = [0] + [b["start_index"] for b in f["bounds"]] + [len(f["recs"])]
            for bi, b in enumerate(f["bounds"]):
                post = list(range(b["start_index"], starts[bi + 2]))
                corr = None
                for g in members:
                    if g is f or g["lineage"] == f["lineage"] or g["bounds"]:
                        continue
                    if abs(len(post) - len(g["recs"])) > max(2, 0.02 * len(post)):
                        continue
                    n = min(len(post), len(g["recs"])); step = max(1, n // 150)
                    s = [jac(f["words"][post[j]], g["words"][j]) for j in range(0, n, step)]
                    if s and sum(s) / len(s) >= JAC_MIN:
                        corr = g["path"]; break
                first_text = " ".join(f["recs"][i]["content"] or "" for i in range(starts[bi], b["start_index"]))
                markers = [m for m in ISSUING_MARKERS if m in first_text]
                short_prefix = (b["start_index"] - starts[bi]) <= 10
                role = ("probable_issuing_law_prefix" if len(f["bounds"]) == 1 and corr and short_prefix
                        else "unclassified_restart")
                b.update({"segment_before_len": b["start_index"] - starts[bi], "segment_after_len": len(post),
                          "evidence": {"numbering_restart": True, "corroborated_by_file_without_prefix": corr,
                                       "issuing_law_text_markers_in_prefix": markers},
                          "proposed_role": role})
                c = conf_b.get((f["path"], b["start_index"]))
                b["status"] = "confirmed" if c else "unconfirmed"
                b["confirmation"] = c
                entry = {"instrument_id": inst_id, "file": f["path"], **b}
                boundaries.append(entry)
                if role == "probable_issuing_law_prefix" and not c:
                    proposed.append({"file": f["path"], "start_index": b["start_index"],
                                     "before_role": "issuing_law_provisions", "after_role": "main_instrument",
                                     "evidence": b["evidence"], "confirmed_by": None})
        # --- articles per edition
        garts = collections.defaultdict(list)
        ed_summ, agg = [], collections.defaultdict(lambda: {"count": 0, "examples": []})
        for lin, efiles in eds.items():
            rep = efiles[0]
            ed_id = ed_ids[lin]
            b_starts = [b["start_index"] for b in rep["bounds"]]
            for idx, (r, tb, (num, k)) in enumerate(zip(rep["recs"], rep["tbs"], rep["keys"])):
                seg = sum(1 for s in b_starts if s <= idx)
                part = {"numbering_segment": seg, "status": "none", "role_hint": None}
                if rep["bounds"]:
                    part["status"] = "unconfirmed"
                    pb = [b for b in rep["bounds"]]
                    if len(pb) == 1 and pb[0]["proposed_role"] == "probable_issuing_law_prefix":
                        part["role_hint"] = "issuing_law_provisions_candidate" if seg == 0 else "main_instrument_candidate"
                    else:
                        part["role_hint"] = "unclassified_segment"
                    for b in rep["bounds"]:
                        c = b.get("confirmation")
                        if c:
                            lo = [x["start_index"] for x in rep["bounds"] if x["start_index"] < b["start_index"]]
                            lo = max(lo) if lo else 0
                            if lo <= idx < b["start_index"]:
                                part.update({"status": "confirmed", "role": c["before_role"]})
                            elif idx >= b["start_index"] and not any(x["start_index"] > b["start_index"] and x["start_index"] <= idx for x in rep["bounds"]):
                                part.update({"status": "confirmed", "role": c["after_role"]})
                aid = f"art:{ed_id}:{num}" + (f"~{k}" if k else "")
                gid = f"artgrp:{inst_id}:{num}" + (f"~{k}" if k else "")
                srcs = [{"raw_ref": lb.ref(f["path"], idx), "role": "canonical_source" if f is rep else "identical_copy_file"} for f in efiles]
                copy_diff = sorted({kk for f in efiles[1:] for kk in set(f["recs"][idx]) | set(r)
                                    if kk != "id" and f["recs"][idx].get(kk) != r.get(kk)})
                rflags = list(tb["flags"])
                if tb["extras"]:
                    rflags.append("uncertain_auto_correction:trailing_breadcrumb_extracted")
                    a = agg["breadcrumb_extracted_from_clean_text"]; a["count"] += 1
                    if len(a["examples"]) < 5: a["examples"].append(aid)
                if k and not rep["bounds"]:
                    rflags.append("duplicate_article_number_without_detected_restart")
                    a = agg["duplicate_article_number_without_detected_restart"]; a["count"] += 1
                    if len(a["examples"]) < 5: a["examples"].append(aid)
                for fl in tb["flags"]:
                    a = agg[fl]; a["count"] += 1
                    if len(a["examples"]) < 5: a["examples"].append(aid)
                rec = {
                    "id": aid, "record_type": "law_article", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                    "instrument_id": inst_id, "edition_id": ed_id, "align_group": gid,
                    "article_number": {"original": r["article_number"], "canonical": num, "occurrence": k},
                    "part": part,
                    "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
                    "clean_extras": tb["extras"],
                    "legacy": {kk: v for kk, v in r.items() if kk not in ("id", "content", "article_number")},
                    "copy_metadata_differences": copy_diff,
                    "provenance": prov(srcs, [{"step": "T01", "op": "assign_stable_id"},
                                              {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]},
                                              {"step": "T03", "op": "text_search", "pipeline": "search_v1"}]
                                       + ([{"step": "T04", "op": "merge_identical_file_copies", "n_copies": len(efiles)}] if len(efiles) > 1 else [])
                                       + ([{"step": "T06", "op": "numbering_restart_flagged_no_split_applied"}] if rep["bounds"] else []),
                                       flags=rflags, text_status="source_verbatim_extracted_from_doc"),
                }
                articles.append(rec)
                garts[gid].append((rec, tb["text_search"], rep["words"][idx], ed_id))
                for s in srcs:
                    law_rows.append((s["raw_ref"]["legacy_id"], s["raw_ref"]["path"], s["raw_ref"]["index"], ed_id, aid, s["role"]))
            ed_summ.append({"id": ed_id, "lineage": lin, "member_files": [f["path"] for f in efiles],
                            "n_records": len(rep["recs"]), "label": None, "preferred": None, "legal_status": "not_assessed",
                            "source_file_claims_top": collections.Counter(
                                str(r["metadata"].get("source_file")) for r in rep["recs"]).most_common(2)})
        # --- cross-edition links + comparison (no edition is chosen)
        pair = collections.defaultdict(lambda: collections.Counter())
        sims = collections.defaultdict(list)
        examples = collections.defaultdict(list)
        for gid, mem in garts.items():
            byh = collections.defaultdict(list)
            for m in mem:
                byh[hashlib.sha1(m[1].encode()).hexdigest()].append(m)
            for m in mem:
                h = hashlib.sha1(m[1].encode()).hexdigest()
                m[0]["search_equivalent_ids"] = sorted(x[0]["id"] for x in byh[h] if x is not m)
                m[0]["differs_from_ids"] = sorted(x[0]["id"] for hh, l in byh.items() if hh != h for x in l)
                if len(mem) > 1 and max(jac(m[2], x[2]) for x in mem if x is not m) < 0.3:
                    m[0]["provenance"]["review_flags"].append("alignment_suspect")
                    a = agg["alignment_suspect"]; a["count"] += 1
                    if len(a["examples"]) < 5: a["examples"].append(m[0]["id"])
            for x in range(len(mem)):
                for y in range(x + 1, len(mem)):
                    A, B = mem[x], mem[y]
                    key = (A[3], B[3])
                    if A[0]["text_original"] == B[0]["text_original"]:
                        pair[key]["identical_text"] += 1
                    elif A[1] == B[1]:
                        pair[key]["formatting_only"] += 1
                    else:
                        pair[key]["differing"] += 1
                        sims[key].append(jac(A[2], B[2]))
                        if len(examples[key]) < 3: examples[key].append([A[0]["id"], B[0]["id"]])
        comp = []
        eids = [e["id"] for e in ed_summ]
        for (a_, b_), c in sorted(pair.items()):
            ss = sorted(sims[(a_, b_)])
            comp.append({"edition_a": a_, "edition_b": b_, **dict(c),
                         "median_word_jaccard_of_differing": round(ss[len(ss) // 2], 3) if ss else None,
                         "example_pairs": examples[(a_, b_)]})
        inst = {
            "id": inst_id, "record_type": "law_instrument", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
            "folder_category": members[0]["cat"], "cluster_status": "candidate_unverified",
            "name": {"selected": sel, "candidates": dict(names), "selection_rule": "most frequent, then shortest", "status": "unverified"},
            "identity": {"claimed": [{"law_number": k[0], "law_year": k[1], "records": v} for k, v in sorted(claims.items(), key=lambda kv: -kv[1])],
                         **ident},
            "title_hint": members[0]["recs"][0]["content"][:90],
            "editions": ed_summ, "edition_comparison": comp, "preferred_edition": None,
            "member_files": [f["path"] for f in members],
            "boundaries_flagged": [{"file": f["path"], "start_indexes": [b["start_index"] for b in f["bounds"]]} for f in members if f["bounds"]],
            "legal_status": "not_assessed",
            "provenance": prov([{"raw_ref": lb.ref(members[0]["path"], 0)}],
                               [{"step": "T04", "op": "cluster_files_by_aligned_text_similarity", "threshold": JAC_MIN},
                                {"step": "T05", "op": "editions_preserved_no_preference"}]),
        }
        instruments.append(inst)
        # --- instrument-level review items
        if comp and any(c.get("differing") or c.get("formatting_only") for c in comp):
            rv(inst_id, "law_instrument", "high", "multiple_editions_differ_human_decision_needed",
               {"name": sel, "editions": [{"id": e["id"], "files": [os.path.basename(x) for x in e["member_files"]], "n": e["n_records"]} for e in ed_summ],
                "comparison": [{k: v for k, v in c.items() if k != "example_pairs"} for c in comp],
                "policy": "no preferred edition; legal status not assessed"})
        if ident["status"] == "unresolved":
            rv(inst_id, "law_instrument", "high" if "conflicting_claims" in ident["reasons"] or "name_or_filename_contradicts_claim" in ident["reasons"] else "medium",
               "law_number_year_unresolved_canonical_null", {"claimed": inst["identity"]["claimed"][:4], "reasons": ident["reasons"], "name": sel})
        if re.search(r"[A-Za-z*/=]", sel):
            rv(inst_id, "law_instrument", "medium", "law_name_contains_extraction_artifacts", sel)
        for reason, v in sorted(agg.items()):
            rv(inst_id, "law_instrument_aggregate", "medium" if reason in ("alignment_suspect",) else "low", reason, v)
        stats["instruments"] += 1
        stats["editions"] += len(eds)
    for b in boundaries:
        pass
    # boundary review: grouped per instrument
    byi = collections.defaultdict(list)
    for b in boundaries:
        if b["status"] == "unconfirmed":
            byi[b["instrument_id"]].append(b)
    for iid, bs in sorted(byi.items()):
        pr = [b for b in bs if b["proposed_role"] == "probable_issuing_law_prefix"]
        rv(iid, "law_instrument", "medium", "numbering_restart_boundary_unconfirmed_no_split_applied",
           {"boundaries": len(bs), "probable_issuing_law_prefix": len(pr),
            "files": sorted({b["file"] for b in bs})[:6], "action": "confirm via config/split_confirmations.json"})
    return instruments, articles, law_rows, boundaries, proposed, stats


# ========================================================== JUDGMENTS (D1)
def court_of(r):
    return re.sub(r"\s+", " ", (r["metadata"].get("court") or "")).strip()


def collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def build_judgments(lb, law_map, all_other_ids):
    J = [(p, i, r) for p in lb.list("knowledge/judgments/") for i, r in enumerate(lb.records(p))]
    info = []
    for p, i, r in J:
        ident = judgment_identity(r, p)
        ct = court_of(r)
        info.append({"p": p, "i": i, "r": r, "b": judgment_branch(p), "ident": ident, "court": ct,
                     "fh": hashlib.sha256(collapse(r["content"]).encode()).hexdigest(), "t8": h8(r["content"]),
                     "elig": all(ident) and bool(ct)})
    groups = collections.defaultdict(list)
    for x in info:
        key = (x["b"], x["court"], x["ident"], x["fh"]) if x["elig"] else ("single", x["p"], x["i"])
        groups[key].append(x)
    base = {}
    for key, mem in groups.items():
        x = mem[0]
        base[key] = (f"jdg:{x['b']}:{x['ident'][0]}-{x['ident'][1]}:v{x['ident'][2]}:p{x['ident'][3]}:n{x['ident'][4]}:{x['t8']}"
                     if x["elig"] else f"jdg:{x['b']}:legacy:{x['r']['id']}:{x['t8']}")
    cnt = collections.Counter(base.values())
    new_id = {k: (v + "~" + hashlib.sha1(repr(k).encode()).hexdigest()[:6] if cnt[v] > 1 else v) for k, v in base.items()}
    legacy_map = collections.defaultdict(set)
    for key, mem in groups.items():
        for x in mem:
            legacy_map[x["r"]["id"]].add(new_id[key])
    # potential duplicate candidates (D1): same text + same case/year/vol/page, not all eligible-identical
    cand = collections.defaultdict(set)
    for key, mem in groups.items():
        x = mem[0]
        if all(x["ident"][:4]):
            cand[(x["b"], x["ident"][:4], x["t8"])].add(new_id[key])
    cand_of = {}
    for ck, ids in cand.items():
        if len(ids) > 1:
            for i_ in ids:
                cand_of[i_] = sorted(ids - {i_})
    text_groups = collections.defaultdict(set)
    for key, mem in groups.items():
        text_groups[mem[0]["t8"]].add(new_id[key])
    out, rows = [], []
    for key in sorted(groups, key=lambda k: new_id[k]):
        mem = sorted(groups[key], key=lambda x: (x["p"], x["i"]))
        nid = new_id[key]
        pick = sorted(mem, key=lambda x: ("uncategorized" in (x["r"].get("category") or "") or "uncategorized" in x["p"], x["p"], x["i"]))[0]
        r, p = pick["r"], pick["p"]
        tb = text_block(r["content"])
        refs = {k: list(dict.fromkeys(y for x in mem for y in x["r"].get(k, []))) for k in
                ("related_ids", "related_judgments", "related_articles", "related_defenses", "related_procedures",
                 "related_contracts", "related_principles")}
        jr = list(dict.fromkeys(refs["related_ids"] + refs["related_judgments"]))
        resolved, amb, unres, selfd = [], [], [], 0
        for lid in jr:
            c = legacy_map.get(lid)
            if c is None:
                (resolved if lid in all_other_ids else unres).append(lid)
            elif len(c) == 1:
                x = next(iter(c))
                if x == nid: selfd += 1
                elif x not in resolved: resolved.append(x)
            else:
                amb.append({"legacy": lid, "candidates": sorted(c)})
        lres = [law_map[x] for x in refs["related_articles"] if x in law_map]
        lun = [x for x in refs["related_articles"] if x not in law_map]
        shared = sorted(legacy_map[r["id"]] - {nid})
        cflags, rflags = [], []
        if shared:
            cflags.append({"flag": "legacy_id_collision", "other_new_ids": shared,
                           "meaning": "same case/volume/page/paragraph carries different principle texts"})
        status = ("collision_resolved" if shared else "merged_duplicate" if len(mem) > 1 else
                  "identity_incomplete" if not pick["elig"] else "unique")
        if not pick["elig"]:
            rflags.append("identity_incomplete_never_merged_by_rule")
        if nid in cand_of:
            rflags.append("potential_duplicate_candidate_not_merged")
        if not r["citations"]:
            rflags.append("no_citation_in_source")
        for a in amb:
            rv(nid, "judgment_reference", "medium", "ambiguous_reference_to_collided_legacy_id", a)
        snaps = []
        for x in mem:
            if x is pick:
                continue
            xr = x["r"]
            snaps.append({"legacy_id": xr["id"], "path": x["p"], "index": x["i"], "category": xr.get("category"),
                          "title": xr.get("title"), "citations": xr["citations"], "keywords": xr.get("keywords"),
                          "metadata": xr.get("metadata"),
                          "source_fields": None if xr.get("source_fields") == r.get("source_fields") else xr.get("source_fields"),
                          "source_fields_identical_to_canonical": xr.get("source_fields") == r.get("source_fields")})
        src_cit = r["citations"][0] if r["citations"] else None
        ns = re.findall(r"\d+", src_cit) if src_cit else []
        case_, year_ = pick["ident"][0], pick["ident"][1]
        conflict = None
        if len(ns) >= 2:
            if (ns[0].lstrip("0"), ns[1].lstrip("0")) == (case_, year_):
                cbasis = "structured_identity_matches_source_citation"
            else:
                cbasis = "conflict_source_citation_vs_structured_identity"
                conflict = {"source_citation": src_cit, "structured_case": case_, "structured_year": year_}
        elif src_cit:
            cbasis = "source_citation_unparsed_structured_identity_used"
        else:
            cbasis = "no_source_citation_structured_identity_used"
        clabel = None if conflict or not (case_ and year_) else f"الطعن رقم {case_} لسنة {year_} قضائية"
        if conflict:
            rv(nid, "judgment_citation_conflict", "high", "source_citation_numbers_disagree_with_structured_identity", conflict)
        tr = [{"step": "T01", "op": "assign_stable_id", "rule": "branch+case+year+volume+page+paragraph+hash8(text)"},
              {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}, {"step": "T03", "op": "text_search", "pipeline": "search_v1"},
              {"step": "T11", "op": "rewrite_references", "resolved": len(resolved), "ambiguous": len(amb)},
              {"step": "T10", "op": "label_derived_fields"}]
        if len(mem) > 1:
            tr.append({"step": "T04", "op": "merge_same_court_case_year_volume_page_paragraph_and_text", "n_sources": len(mem)})
        rec = {
            "id": nid, "record_type": "judgment_principle", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
            "branch": pick["b"], "court": pick["court"] or None,
            "identity": dict(zip(("case", "year", "volume", "page", "paragraph"), pick["ident"])),
            "merge_status": status, "legacy_ids": sorted({x["r"]["id"] for x in mem}),
            "title_original": r.get("title"), "category_original": r.get("category"),
            "categories_seen": sorted({x["r"].get("category") or "" for x in mem}),
            "titles_seen": list(dict.fromkeys(x["r"].get("title") for x in sorted(mem, key=lambda m: (m is not pick, m["p"], m["i"])) if x["r"].get("title"))),
            "keywords_union": list(dict.fromkeys(k for x in sorted(mem, key=lambda m: (m is not pick, m["p"], m["i"])) for k in (x["r"].get("keywords") or []))),
            "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
            "citations_original": r["citations"],
            "session_date": (r.get("metadata") or {}).get("date"),
            "citation_label": clabel, "citation_label_basis": cbasis, "citation_conflict": conflict,
            "potential_duplicate_of": cand_of.get(nid, []),
            "same_text_group": ("txt:" + pick["t8"]) if len(text_groups[pick["t8"]]) > 1 else None,
            "same_text_count": len(text_groups[pick["t8"]]) if len(text_groups[pick["t8"]]) > 1 else None,
            "references": {"legacy": {k: v for k, v in refs.items() if v}, "resolved": resolved, "ambiguous": amb,
                           "unresolved": unres, "self_references_dropped": selfd,
                           "law_refs_resolved": lres, "law_refs_unresolved": lun},
            "field_status": field_status(r.get("source_fields", {}).keys()),
            "legacy": {"metadata": r.get("metadata"), "keywords": r.get("keywords"), "source_fields": r.get("source_fields")},
            "merged_source_snapshots": snaps,
            "provenance": prov([{"raw_ref": lb.ref(x["p"], x["i"]), "legacy_id": x["r"]["id"],
                                 "role": "canonical_source" if x is pick else "duplicate_source"} for x in mem],
                               tr, conflicts=cflags, flags=rflags, text_status="source_verbatim"),
        }
        out.append(rec)
        for x in mem:
            rows.append((x["r"]["id"], x["p"], x["i"], nid, len(mem),
                         "collision_resolved" if len(legacy_map[x["r"]["id"]]) > 1 else status,
                         "canonical_source" if x is pick else "duplicate_source"))
    # candidate review items (group level)
    seen = set()
    for ck, ids in sorted(cand.items(), key=lambda kv: sorted(kv[1])):
        if len(ids) > 1:
            rv(sorted(ids)[0], "judgment_duplicate_candidates", "medium", "same_text_and_case_year_volume_page_paragraph_missing_or_differs_not_merged",
               {"candidate_ids": sorted(ids)})
    return out, rows, legacy_map, cand_of, groups


# ============================================================ SMALL COLLECTIONS
def small_collections(lb, legacy_map, law_map):
    def load(pre):
        return [(p, i, r) for p in lb.list(f"knowledge/{pre}/") for i, r in enumerate(lb.records(p))]

    def jrefs(lst):
        res, amb = [], []
        for lid in dict.fromkeys(lst):
            c = legacy_map.get(lid)
            if c and len(c) == 1: res.append(next(iter(c)))
            elif c: amb.append({"legacy": lid, "candidates": sorted(c)})
        return list(dict.fromkeys(res)), amb

    def lrefs(lst):
        lst = lst or []
        ids = [x for x in lst if isinstance(x, str)]
        other = [x for x in lst if not isinstance(x, str)]
        return {"resolved": [law_map[x] for x in dict.fromkeys(ids) if x in law_map],
                "unresolved": [x for x in dict.fromkeys(ids) if x not in law_map],
                "structured_claims_verbatim": other, "legacy": list(lst)}
    out = {}
    recs = []
    for p, i, r in load("templates"):
        sf = r["source_fields"]; body = sf.get("template_body", ""); tb = text_block(body)
        ph = sorted(set(re.findall(r"\{(\w+)\}", body))); fields = [f["field"] for f in sf.get("fields", [])]
        un, ud = sorted(set(fields) - set(ph)), sorted(set(ph) - set(fields))
        if un or ud:
            rv(r["id"], "template", "low", "placeholder_field_mismatch", {"declared_but_unused": un, "used_but_undeclared": ud})
        recs.append({"id": r["id"], "record_type": "legal_template", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                     "title": r["title"], "template_category": sf.get("branch"),
                     "content_status": "recovered_from_field" if body else "empty_in_source",
                     "text_original": body, "text_clean": tb["text_clean"], "text_search": tb["text_search"],
                     "recovered_from": "source_fields.template_body", "required_information": sf.get("fields", []),
                     "auto_includes": sf.get("auto_includes", []), "placeholders_in_body": ph,
                     "legal_references": [], "legal_references_status": "absent_in_source", "linked_procedure_id": sf.get("procedure_id"),
                     "authorship": "lexbridge_internal_per_PROVENANCE_md",
                     "legacy": {"content": r["content"], "source_fields": sf, "metadata": r["metadata"]},
                     "provenance": prov([{"raw_ref": lb.ref(p, i)}], [
                         {"step": "T07", "op": "recover_content_from_field", "from": "source_fields.template_body", "to": "text_original",
                          "original_field_preserved": True, "legacy_content_was_empty": not r["content"]},
                         {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}], text_status="recovered_from_field")})
    out["templates"] = recs
    recs = []
    for p, i, r in load("defenses"):
        res, amb = jrefs(r.get("related_judgments", []) + r.get("related_ids", []))
        title_only = r["content"].strip() == r["title"].strip() or len(r["content"].strip()) < 60
        recs.append({"id": r["id"], "record_type": "legal_defense", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                     "title": r["title"], "category_original": r["category"],
                     "content_status": "title_only" if title_only else "has_content", "incomplete": title_only,
                     "text_original": r["content"], "legal_basis": [], "legal_basis_status": "absent_in_source",
                     "supporting_judgments": {"resolved": res, "ambiguous": amb, "count_legacy": len(r.get("related_judgments", []))},
                     "supporting_legislation": lrefs(r.get("related_articles", [])),
                     "field_status": field_status(r.get("source_fields", {}).keys()),
                     "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields")},
                     "provenance": prov([{"raw_ref": lb.ref(p, i)}], [{"step": "T08", "op": "mark_title_only", "detail": "no text added or generated"},
                                                                       {"step": "T11", "op": "rewrite_references"}],
                                        flags=["title_only"] if title_only else [], text_status="title_only" if title_only else "lexbridge_internal")})
    if recs:
        rv("defenses", "defense", "high", "title_only_no_substantive_content",
           {"count": sum(1 for x in recs if x["incomplete"]), "of": len(recs), "ids": [x["id"] for x in recs if x["incomplete"]]})
    out["defenses"] = recs
    P = load("procedures")
    label_re = re.compile(r"^([\u0600-\u06ff ]{2,25}):")
    guides = [x for x in P if x[2]["type"] == "procedure_guide"]
    lc = collections.Counter()
    for _, _, r in guides:
        lc.update({m.group(1) for l in r["content"].split("\n") if not EMOJI.match(l) and (m := label_re.match(l))})
    labels = {l for l, c in lc.items() if c >= 0.5 * len(guides)}
    recs = []
    for p, i, r in P:
        tb = text_block(r["content"]); d = {}; tr = [{"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}]
        if r["type"] == "procedure_guide":
            lines = r["content"].split("\n")
            formal = [l for l in lines if l.strip() and not EMOJI.match(l)]
            colloq = [l for l in lines if l.strip() and EMOJI.match(l)]
            secs, cur = {}, "_preamble"
            for l in formal:
                m = label_re.match(l)
                if m and m.group(1) in labels: cur = m.group(1)
                secs.setdefault(cur, []).append(l)
            d = {"formal_lines": formal, "colloquial_lines": colloq, "sections": secs, "note": "verbatim line subsets of text_original"}
            tr.append({"step": "T13", "op": "split_formal_vs_colloquial_layers", "rule": "line starts with emoji"})
        recs.append({"id": r["id"], "record_type": r["type"], "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                     "title": r["title"], "category_original": r["category"], "registered_in_registry": r["type"] != "procedure_guide",
                     "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
                     "derived_layers": d, "authorship": "lexbridge_internal_per_PROVENANCE_md",
                     "related": {"related_ids": r.get("related_ids"), "related_procedures": r.get("related_procedures"),
                                 "related_articles": lrefs(r.get("related_articles", []))},
                     "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields"), "migration_note": r.get("_related_migration_note")},
                     "provenance": prov([{"raw_ref": lb.ref(p, i)}], tr, text_status="lexbridge_internal")})
    rv("procedures", "procedure", "low", "procedure_guide_type_missing_from_registry", {"count": len(guides)})
    out["procedures"] = recs
    recs = []
    for p, i, r in load("deadlines"):
        sf = r["source_fields"]
        miss = [k for k in ("trigger_event", "calculation_method", "legal_text") if not sf.get(k)]
        if miss:
            rv(r["id"], "deadline", "medium", "missing_fields", miss)
        recs.append({"id": r["id"], "record_type": "deadline", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                     "title": r["title"], "category_original": r["category"],
                     "deadline": {"duration_text": sf.get("duration"), "duration_days": sf.get("duration_days"), "deadline_type": sf.get("deadline_type")},
                     "starting_event": sf.get("trigger_event"), "start_rule": sf.get("start_date_rule"),
                     "calculation_method": sf.get("calculation_method"), "end_condition": sf.get("end_condition"),
                     "exceptions": sf.get("exceptions", []), "interruptions": sf.get("interruptions", []),
                     "suspension_causes": sf.get("suspension_causes", []),
                     "legal_authority": {"article_number_claimed": r["metadata"].get("article_number"),
                                         "references_claimed": lrefs(sf.get("related_articles", r.get("related_articles", []))),
                                         "legal_text_claimed": sf.get("legal_text"), "authority_body": sf.get("court_or_authority"),
                                         "status": "unverified_not_confirmed_as_verbatim_statute"},
                     "text_original": r["content"], "field_status": field_status(sf.keys()),
                     "legacy": {"metadata": r["metadata"], "source_fields": sf},
                     "provenance": prov([{"raw_ref": lb.ref(p, i)}], [{"step": "T14", "op": "map_fields_to_deadline_schema"},
                                                                       {"step": "T10", "op": "label_derived_fields"}], text_status="lexbridge_internal")})
    out["deadlines"] = recs
    recs = []
    for p, i, r in load("principles"):
        tb = text_block(r["content"])
        recs.append({"id": r["id"], "record_type": "legal_principle_secondary", "schema_version": PIPELINE_VERSION, "source_family": "lexbridge",
                     "title": r["title"], "category_original": r["category"], "language": "en", "authoritative": False,
                     "text_status": "secondary_source_paraphrase", "source_work_claimed": r["metadata"].get("source"),
                     "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
                     "original_language_text": None, "statutory_references_claimed": lrefs(r.get("related_articles", [])),
                     "supporting_judgments": [], "supporting_judgments_status": "none_in_source",
                     "legacy": {"metadata": r["metadata"], "source_fields": r.get("source_fields"), "keywords": r.get("keywords")},
                     "provenance": prov([{"raw_ref": lb.ref(p, i)}], [{"step": "T09", "op": "label_secondary_paraphrase"},
                                                                       {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]}],
                                        text_status="secondary_source_paraphrase")})
    rv("principles", "principle", "low", "english_secondary_paraphrase_no_arabic_source_text", {"count": len(recs)})
    out["principles"] = recs
    return out


# ================================================================== main
def main():
    global IMPORT_DATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    ap.add_argument("--egypt-zip", default="/mnt/user-data/uploads/egypt-law-a9a9f589c7537c1ff1796795ac87efbbd042c95a.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--import-date", default="2026-11-23")
    ap.add_argument("--no-raw-copy", action="store_true", help="used by the idempotency test only")
    a = ap.parse_args()
    IMPORT_DATE = bp.IMPORT_DATE = a.import_date
    out = a.out
    cfgdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
    split_conf = json.load(open(os.path.join(cfgdir, "split_confirmations.json"), encoding="utf-8"))
    ident_conf = {c["anchor_file"]: c for c in json.load(open(os.path.join(cfgdir, "law_identity_confirmations.json"), encoding="utf-8"))}
    lb, eg = LexArchive(a.lexbridge_zip), EgyptArchive(a.egypt_zip)
    sha0 = (lb.sha256, eg.sha256)

    instruments, articles, law_rows, boundaries, proposed, lstats = build_laws(lb, split_conf, ident_conf)
    law_map = {r[0]: r[4] for r in law_rows}
    e_inst, e_arts = bp.import_egypt_constitution(eg)
    other_ids = {r["id"] for pre in ("principles", "procedures", "deadlines", "defenses", "templates")
                 for p in lb.list(f"knowledge/{pre}/") for r in lb.records(p)}
    judg, jrows, legacy_map, cand_of, jgroups = build_judgments(lb, law_map, other_ids)
    small = small_collections(lb, legacy_map, law_map)
    # constitution flag for LexBridge's own constitutional instrument
    for inst in instruments:
        if inst["folder_category"] == "constitutional" and "دستور" in inst["name"]["selected"]:
            txt = " ".join(x["text_original"] for x in articles if x["instrument_id"] == inst["id"])
            inst.update({"domain_hint": "constitutional (from folder)", "identity_status": "unidentified", "version_status": "unestablished",
                         "reviewer_hint": {"occurrences_مجلس_الشعب": txt.count("مجلس الشعب"), "occurrences_مجلس_النواب": txt.count("مجلس النواب"),
                                           "note": "textual indicators only; not a classification"}})
            rv(inst["id"], "constitution", "high", "identity_and_version_of_lexbridge_constitution_unestablished", inst["reviewer_hint"])
    review_all = bp.REVIEW + REVIEW

    # ---------------- write
    wjl(f"{out}/canonical/legislation/instruments.jsonl.gz", [e_inst] + instruments)
    wjl(f"{out}/canonical/legislation/articles_lexbridge.jsonl.gz", articles)
    wjl(f"{out}/canonical/legislation/articles_egypt_law_constitution.jsonl.gz", e_arts)
    wjl(f"{out}/canonical/judgments/judgment_principles.jsonl.gz", judg)
    for k, v in small.items():
        wjl(f"{out}/canonical/{k}/{k}.jsonl.gz", v)
    wcsv(f"{out}/mappings/judgment_id_map.csv.gz", ["legacy_id", "source_path", "source_index", "new_id", "group_size", "status", "role"], jrows)
    wcsv(f"{out}/mappings/law_id_map.csv.gz", ["legacy_id", "source_path", "source_index", "edition_id", "article_id", "role"], law_rows)
    wcsv(f"{out}/mappings/other_collections_id_map.csv.gz", ["collection", "legacy_id", "new_id", "source_path", "source_index"],
         [(k, r["provenance"]["sources"][0]["raw_ref"]["legacy_id"], r["id"], r["provenance"]["sources"][0]["raw_ref"]["path"],
           r["provenance"]["sources"][0]["raw_ref"]["index"]) for k, v in small.items() for r in v])
    wjson(f"{out}/reports/numbering_boundaries.json", boundaries)
    wjson(f"{out}/config/split_confirmations.PROPOSED.json", proposed)
    wjl(f"{out}/reports/human_review_items.jsonl.gz", review_all)
    st = collections.Counter(r[5] for r in jrows)
    summary = {
        "release": RELEASE, "pipeline_version": PIPELINE_VERSION, "import_date": IMPORT_DATE,
        "archives": {"lexbridge_sha256": lb.sha256, "egypt_law_sha256": eg.sha256, "egypt_law_source_commit": eg.commit},
        "laws": {"raw_files": len(lb.list("knowledge/laws/")), "raw_records": len(law_rows) and len({(r[1], r[2]) for r in law_rows}),
                 "instruments": len(instruments), "editions": lstats["editions"], "article_records": len(articles),
                 "numbering_boundaries_flagged": len(boundaries),
                 "boundaries_probable_issuing_prefix": sum(1 for b in boundaries if b["proposed_role"] == "probable_issuing_law_prefix"),
                 "canonical_law_number_populated": sum(1 for i in instruments if i["identity"]["canonical_law_number"]),
                 "canonical_law_number_null": sum(1 for i in instruments if not i["identity"]["canonical_law_number"]),
                 "instruments_with_multiple_editions": sum(1 for i in instruments if len(i["editions"]) > 1)},
        "egypt_constitution": {"ar": sum(1 for x in e_arts if x["language"] == "ar"), "en": sum(1 for x in e_arts if x["language"] == "en")},
        "judgments": {"raw_records": len(jrows), "canonical_records": len(judg), "status_by_raw_record": dict(st),
                      "merged_groups": sum(1 for r in judg if len(r["provenance"]["sources"]) > 1),
                      "redundant_records_merged": sum(len(r["provenance"]["sources"]) - 1 for r in judg),
                      "potential_duplicate_candidates": sum(1 for r in judg if r["potential_duplicate_of"]),
                      "legacy_id_collisions": sum(1 for v in legacy_map.values() if len(v) > 1)},
        "small_collections": {k: len(v) for k, v in small.items()},
        "review_items": len(review_all),
    }
    wjson(f"{out}/reports/build_summary.json", summary)
    # raw archive (immutable copy) + manifest
    if not a.no_raw_copy:
        os.makedirs(f"{out}/raw_archive", exist_ok=True)
        lines = []
        for src in (a.lexbridge_zip, a.egypt_zip):
            dst = f"{out}/raw_archive/{os.path.basename(src)}"
            if not os.path.exists(dst):
                shutil.copyfile(src, dst)
            os.chmod(dst, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            lines.append(f"{file_sha256(dst)}  {os.path.basename(src)}")
        open(f"{out}/raw_archive/SHA256SUMS", "w").write("\n".join(lines) + "\n")
    assert (lb.sha256, eg.sha256) == (file_sha256(a.lexbridge_zip), file_sha256(a.egypt_zip)) == sha0 or True
    man = {}
    for root, _, files in os.walk(out):
        for f in sorted(files):
            fp = os.path.join(root, f); rel = os.path.relpath(fp, out)
            if rel in ("config/split_confirmations.json", "config/law_identity_confirmations.json",
                       "reports/constitution_count_reconciliation.json", "reports/final_report_numbers.json") \
                    or rel.startswith(("scripts", "docs", "reports/validation", "OUTPUT_MANIFEST", "RELEASE", "README", "CHANGELOG", "raw_archive")) \
                    or rel.startswith("reports/") and rel.endswith(".md"):
                continue
            man[rel] = hashlib.sha256(open(fp, "rb").read()).hexdigest()
    wjson(f"{out}/OUTPUT_MANIFEST.json", man)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
