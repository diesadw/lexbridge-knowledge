#!/usr/bin/env python3
"""Integrate (a) the Law Intake output and (b) full-text judgments (.docx) into a NEW release
(v3.1.0-rc1) built on top of v3.0.0-rc1. Nothing in the base release or the original archives is modified.

User precedence rule (explicit): the new sources win over existing records wherever they conflict.
Implemented as precedence_rank (1 = new source) + legacy_status on old records - old records are NEVER deleted.
"""
import argparse, collections, csv, difflib, gzip, hashlib, io, json, os, re, shutil, stat, sys, zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import PIPELINE_VERSION, file_sha256, rec_sha256, text_block

RELEASE = "3.1.0-rc1"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BIS_LETTERS = {"أ": "a", "ا": "a", "ب": "b", "ج": "c", "د": "d", "ه": "e", "هـ": "e", "و": "f", "ز": "g", "ح": "h", "ط": "i",
               "ي": "j", "ك": "k", "ل": "l", "م": "m", "ن": "n", "أولا": "first", "ثانيا": "second", "ثالثا": "third"}
MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8,
          "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}
MATCH_MEAN, MATCH_ART, MATCH_UNCONFIRMED = 0.6, 0.5, 0.8
IMPORT_DATE = None
REVIEW = []


def rv(rid, cat, sev, reason, detail=None):
    REVIEW.append({"id": rid, "category": cat, "severity": sev, "reason": reason, "detail": detail})


def prov(sources, transformations, flags=None, conflicts=None, **extra):
    p = {"sources": sources, "import_date": IMPORT_DATE, "pipeline_version": PIPELINE_VERSION, "release": RELEASE,
         "transformations": transformations, "verification_status": "unverified", "conflict_flags": conflicts or [],
         "review_flags": flags or []}
    p.update(extra)
    return p


def jl_read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def wjl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1); f.write("\n")


def wcsv(path, header, rows):
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow(header); w.writerows(rows)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def jac(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def bis_slug(bis):
    if not bis:
        return ""
    m = re.match(r"^مكرر[اًٌٍ]*\s*(?:\(\s*([^)]+?)\s*\))?$", bis.strip())
    if not m:
        return "-bis-x" + hashlib.sha1(bis.encode()).hexdigest()[:4]
    if not m.group(1):
        return "-bis"
    s = m.group(1)
    if s.isdigit():
        return "-bis-" + s
    return "-bis-" + BIS_LETTERS.get(s, "x" + hashlib.sha1(s.encode()).hexdigest()[:4])


def canon_key(num, bis):
    return str(num) + bis_slug(bis)


# ---------------------------------------------------------------- docx judgments
def docx_paragraphs(path):
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    out = []
    for p in root.find(W + "body").iter(W + "p"):
        o = []
        for e in p.iter():
            if e.tag == W + "t": o.append(e.text or "")
            elif e.tag == W + "tab": o.append("\t")
            elif e.tag in (W + "br", W + "cr"): o.append("\n")
        out.append("".join(o))
    return out


TITLE = re.compile(r"^(نقض مدني|نقض جنائي)\s*–\s*الطعن رقم\s*(\d+)\s*لسنة\s*(\d+)\s*ق\s*–\s*جلسة\s*([\d\s‏/]+)(?:–\s*(.*))?$")


def split_judgments(P):
    src = [i for i, t in enumerate(P) if t.startswith("المصدر")]
    out = []
    for k, s in enumerate(src):
        ti = s - 1
        while not P[ti].strip(): ti -= 1
        e = len(P)
        if k + 1 < len(src):
            e = src[k + 1] - 1
            while not P[e].strip(): e -= 1
        ni = next(i for i in range(s, e) if P[i].strip() == "نص الحكم")
        body = P[ni + 1:e]
        trimmed = 0
        while body and not body[-1].strip():
            body.pop(); trimmed += 1
        out.append({"title_idx": ti, "src_idx": s, "heading_idx": ni, "end_idx": e, "title": P[ti], "source_line": P[s],
                    "body": body, "trimmed_blank": trimmed})
    return out


def parse_title(t):
    m = TITLE.match(t.strip())
    if not m:
        return None
    d = [int(x) for x in re.findall(r"\d+", m.group(4))]
    iso = f"{d[2]:04d}-{d[1]:02d}-{d[0]:02d}" if len(d) == 3 and 1 <= d[1] <= 12 and 1 <= d[0] <= 31 else None
    return {"label": m.group(1), "case": int(m.group(2)), "year": int(m.group(3)), "date_iso": iso,
            "date_original": m.group(4).strip(), "subject": (m.group(5) or "").strip() or None}


def build_fulltext_judgments(docx_path, docx_sha, existing_keys):
    P = docx_paragraphs(docx_path)
    J = split_judgments(P)
    groups = collections.OrderedDict()
    for k, j in enumerate(J):
        pt = parse_title(j["title"])
        if pt is None:
            rv(f"docx:{k}", "judgment_fulltext", "high", "title_not_parsed_record_skipped", j["title"][:120]); continue
        j["pt"] = pt
        j["text"] = "\n".join(j["body"])
        branch = "civil" if pt["label"] == "نقض مدني" else "crim"
        j["branch"] = branch
        groups.setdefault((branch, pt["case"], pt["year"], pt["date_iso"]), []).append(j)
    recs, rows = [], []
    for key, mem in groups.items():
        by_text = collections.OrderedDict()
        for j in mem:
            by_text.setdefault(hashlib.sha256(j["text"].encode()).hexdigest(), []).append(j)
        vgroup = f"jdgf:{key[0]}:{key[1]}-{key[2]}:{(key[3] or 'nodate').replace('-', '')}"
        for th, same in by_text.items():
            j = same[0]; pt = j["pt"]
            tb = text_block(j["text"])
            nid = f"{vgroup}:{th[:8]}"
            cy = f"{pt['case']}\\s*لسنة\\s*{pt['year']}"
            gm = None
            m = re.search(r"الموافق\s*(\d+)\s*من\s*(\S+)\s*سنة\s*((?:19|20)\d{2})\s*م", j["text"])
            if m and MONTHS.get(m.group(2)):
                gm = (f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}") == pt["date_iso"]
            flags, confl = [], []
            if len(by_text) > 1:
                confl.append({"flag": "same_judgment_two_different_texts", "variant_group": vgroup})
            if gm is False:
                flags.append("gregorian_date_in_text_differs_from_title")
            if not re.search(cy, j["text"]):
                flags.append("title_case_number_not_found_in_text")
            if (key[0], pt["case"], pt["year"]) in existing_keys:
                flags.append("overlaps_existing_principle_records")
            recs.append({
                "id": nid, "record_type": "judgment_fulltext", "schema_version": PIPELINE_VERSION, "source_family": "judgments-docx",
                "precedence_rank": 1, "branch": key[0], "court": "Egyptian Court of Cassation",
                "court_label_original": pt["label"],
                "identity": {"case": str(pt["case"]), "year": str(pt["year"])},
                "session_date": pt["date_iso"], "session_date_original": pt["date_original"],
                "title_original": j["title"], "subject": pt["subject"],
                "citation_label": f"الطعن رقم {pt['case']} لسنة {pt['year']} قضائية",
                "body_heading_original": "نص الحكم",
                "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"],
                "variant_group": vgroup if len(by_text) > 1 else None,
                "checks": {"title_case_year_found_in_text": bool(re.search(cy, j["text"])), "gregorian_date_in_text_matches_title": gm},
                "legacy_principle_overlap": [],
                "provenance": prov(
                    [{"raw_ref": {"source": "judgments-docx", "archive_sha256": docx_sha, "path": "word/document.xml",
                                  "paragraph_title": x["title_idx"], "paragraph_heading": x["heading_idx"], "paragraph_end": x["end_idx"],
                                  "record_sha256": hashlib.sha256((x["title"] + "\n" + x["text"]).encode()).hexdigest()},
                      "role": "canonical_source" if x is j else "identical_duplicate",
                      "removed_source_line_sha256": hashlib.sha256(x["source_line"].encode()).hexdigest()} for x in same],
                    [{"step": "T20", "op": "split_title_fields", "detail": "case/year/date/subject parsed from the title line; title kept verbatim"},
                     {"step": "T21", "op": "remove_source_line", "detail": "the 'المصدر: <link>' line removed as requested; original file kept in raw_archive"},
                     {"step": "T01", "op": "assign_stable_id"}, {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]},
                     {"step": "T03", "op": "text_search", "pipeline": "search_v1"}]
                    + ([{"step": "T04", "op": "merge_identical_duplicate_records", "n_sources": len(same)}] if len(same) > 1 else [])
                    + ([{"step": "T05", "op": "variants_preserved_as_separate_records"}] if len(by_text) > 1 else []),
                    flags=flags, conflicts=confl, text_status="source_verbatim", trailing_blank_paragraphs_trimmed=j["trimmed_blank"]),
            })
            for x in same:
                rows.append((x["title_idx"], x["pt"]["case"], x["pt"]["year"], nid))
            for fl in flags:
                rv(nid, "judgment_fulltext", "medium", fl, None)
        if len(by_text) > 1:
            ts = [m_[0]["text"] for m_ in by_text.values()]
            sm = difflib.SequenceMatcher(None, ts[0], ts[1], autojunk=False)
            ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
            first = ops[0] if ops else None
            rv(vgroup, "judgment_fulltext", "high", "same_case_same_session_two_different_texts_both_kept",
               {"lengths": [len(t) for t in ts], "diff_blocks": len(ops),
                "first_diff": {"a": ts[0][first[1]:first[2]][:120], "b": ts[1][first[3]:first[4]][:120], "at": first[1]} if first else None})
    return recs, rows, len(J)


# -------------------------------------------------------------------- main
def main():
    global IMPORT_DATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="v3.0.0-rc1 release dir")
    ap.add_argument("--intake-zip", required=True)
    ap.add_argument("--judgments-docx", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--import-date", default="2026-11-25")
    ap.add_argument("--no-raw-copy", action="store_true")
    a = ap.parse_args(); O, B = a.out, a.base
    IMPORT_DATE = a.import_date
    intake_sha, docx_sha = file_sha256(a.intake_zip), file_sha256(a.judgments_docx)

    # ---- base tree (never modified) -> out
    keep_out = ("raw_archive", "OUTPUT_MANIFEST.json", "RELEASE.json")
    base_rep = ("FINAL_DATA_REPORT.md", "DECISION_EXAMPLES.md", "validation_results.json", "build_summary.json", "final_report_numbers.json")
    for root, dirs, files in os.walk(B):
        rel = os.path.relpath(root, B)
        if rel.split(os.sep)[0] in keep_out or "__pycache__" in rel:
            continue
        for f in files:
            if f in keep_out or (rel == "reports" and f in base_rep):
                continue
            if rel.startswith("canonical") or rel.startswith("mappings"):
                if f in ("articles_lexbridge.jsonl.gz", "instruments.jsonl.gz", "judgment_principles.jsonl.gz") or rel.startswith("canonical/defenses") \
                        or rel.startswith("canonical/deadlines") or rel.startswith("canonical/procedures") or rel.startswith("canonical/principles"):
                    continue  # rewritten below
            dst = os.path.join(O, rel, f); os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, f), dst)
    os.makedirs(f"{O}/reports/baseline_v3.0.0", exist_ok=True)
    for f in base_rep:
        if os.path.exists(f"{B}/reports/{f}"):
            shutil.copyfile(f"{B}/reports/{f}", f"{O}/reports/baseline_v3.0.0/{f}")

    # ---- intake
    zi = zipfile.ZipFile(a.intake_zip)
    rd = lambda n: zi.read("law_intake_output/" + n).decode("utf-8")
    laws = [json.loads(l) for l in rd("laws.jsonl").split("\n") if l.strip()]
    art_raw = [l for l in rd("articles.jsonl").split("\n") if l.strip()]
    arts_in = [json.loads(l) for l in art_raw]
    review_in = [json.loads(l) for l in rd("review_list.jsonl").split("\n") if l.strip()]
    manifest = json.loads(rd("source_manifest.json"))["files"]
    file_sha = {m["file"]: m["sha256"] for m in manifest}
    law_by = {l["instrument_id"]: l for l in laws}
    new_inst, new_art = [], []
    per = collections.defaultdict(list)
    seen_ids = set()
    for i, (r, obj) in enumerate(zip(art_raw, arts_in)):
        iid = obj["instrument_id"]; role = "m" if obj["article_role"] == "main" else "i"
        ck = canon_key(obj["article_number"], obj["bis"])
        aid = f"art:in:{iid}:{role}:{ck}"
        assert aid not in seen_ids, aid
        seen_ids.add(aid)
        tb = text_block(obj["text"])
        rec = {"id": aid, "record_type": "law_article", "schema_version": PIPELINE_VERSION, "source_family": "law-intake", "precedence_rank": 1,
               "instrument_id": "inst:in:" + iid, "article_role": obj["article_role"],
               "article_number": {"original": obj["article_number_original"], "canonical": obj["article_number"], "bis": obj["bis"], "key": ck},
               "citation_label": obj["citation_label"], "structure": obj["structure"],
               "text_original": tb["text_original"], "text_clean": tb["text_clean"], "text_search": tb["text_search"], "clean_extras": tb["extras"],
               "source_annotations": obj["source_annotations"], "cleanup_log_from_intake": obj["cleanup_log"],
               "extraction_confidence": obj["extraction_confidence"], "ocr_uncertain": obj["ocr_uncertain"],
               "provenance": prov([{"raw_ref": {"source": "law-intake", "archive_sha256": intake_sha, "path": "law_intake_output/articles.jsonl",
                                                "index": i, "record_sha256": rec_sha256(obj), "source_file": obj["source_file"],
                                                "source_file_sha256": file_sha.get(obj["source_file"])}}],
                                  [{"step": "T01", "op": "assign_stable_id"}, {"step": "T02", "op": "text_clean", "ops": tb["clean_ops"]},
                                   {"step": "T03", "op": "text_search", "pipeline": "search_v1"}],
                                  flags=list(tb["flags"]), text_status="source_verbatim_per_intake_unverified_by_lexbridge")}
        new_art.append(rec); per[iid].append(rec)
    for j, l in enumerate(laws):
        iid = l["instrument_id"]
        new_inst.append({
            "id": "inst:in:" + iid, "record_type": "law_instrument", "schema_version": PIPELINE_VERSION, "source_family": "law-intake",
            "precedence_rank": 1, "instrument_type": l["instrument_type"], "title_original": l["instrument_title"], "code_name": l["code_name"],
            "law_number": l["law_number"], "law_year": l["law_year"],
            "identity": {"canonical_law_number": str(l["law_number"]), "canonical_law_year": str(l["law_year"]),
                         "basis": "heading_evidence_in_source_file", "evidence_quote": l["identity_evidence"]["quote"],
                         "external_verification": None, "status": "source_heading_evidence"},
            "gazette_reference": l["gazette_reference"], "source_file": l["source_file"], "filename_hint": l["filename_hint"],
            "filename_agrees": l["filename_agrees"], "intake_issues": l["issues"],
            "counts": {"main": l["article_count_main"], "issuing": l["article_count_issuing"], "exported": len(per[iid])},
            "legal_status": "not_assessed", "legacy_comparison": None,
            "provenance": prov([{"raw_ref": {"source": "law-intake", "archive_sha256": intake_sha, "path": "law_intake_output/laws.jsonl",
                                             "index": j, "record_sha256": rec_sha256(l), "source_file": l["source_file"],
                                             "source_file_sha256": file_sha.get(l["source_file"])}}],
                               [{"step": "T01", "op": "assign_stable_id"}])})

    # ---- legacy laws + matching (new sources take precedence)
    old_inst_all = jl_read(f"{B}/canonical/legislation/instruments.jsonl.gz")
    egypt_inst, old_inst = old_inst_all[0], old_inst_all[1:]
    old_art = jl_read(f"{B}/canonical/legislation/articles_lexbridge.jsonl.gz")
    old_by_ed = collections.defaultdict(list)
    for r in old_art:
        old_by_ed[r["edition_id"]].append(r)
    words_old = {r["id"]: set(r["text_search"].split()) for r in old_art}
    newkey = {}
    for iid, rs in per.items():
        d = collections.defaultdict(list)
        for r in rs:
            d[r["article_number"]["key"]].append(r)
        newkey[iid] = d
    remap, comps = {}, collections.defaultdict(list)   # old article id -> (new id, sim, basis)
    inst_matches = collections.defaultdict(list)
    rejected = {}
    for oi in old_inst:
        for ed in oi["editions"]:
            ed_arts = old_by_ed[ed["id"]]
            idx = collections.defaultdict(list)
            for r in ed_arts:
                idx[r["article_number"]["canonical"]].append(r)
            for iid, d in newkey.items():
                aligned = [(k, rs) for k, rs in d.items() if k in idx]
                tot = sum(len(rs) for rs in d.values())
                if len(aligned) < 2 or len(aligned) < 0.5 * min(len(d), len(idx)):
                    continue
                pairs = []
                for k, rs in aligned:
                    for nr in rs:
                        nw = set(nr["text_search"].split())
                        best = max(((jac(nw, words_old[o["id"]]), o) for o in idx[k]), key=lambda x: x[0])
                        pairs.append((nr, best[1], best[0]))
                mean = sum(p[2] for p in pairs) / len(pairs)
                L_ = law_by[iid]
                can = (oi["identity"]["canonical_law_number"], oi["identity"]["canonical_law_year"])
                if can[0]:
                    ok = (str(L_["law_number"]), str(L_["law_year"])) == can and mean >= MATCH_MEAN
                    basis = "canonical_identity_equal+text_alignment"
                    if not ok and mean >= MATCH_MEAN:
                        rejected.setdefault(oi["id"], []).append({"intake_instrument": "inst:in:" + iid, "mean_similarity": round(mean, 4),
                                                                   "reason": "text_similar_but_law_number_year_differ (likely quotation/amendment) - not linked"})
                else:
                    ok = mean >= MATCH_UNCONFIRMED
                    basis = "text_alignment_identity_unconfirmed"
                if ok:
                    inst_matches[oi["id"]].append({"edition_id": ed["id"], "intake_instrument": "inst:in:" + iid, "mean_similarity": round(mean, 4),
                                                   "aligned_articles": len(pairs), "intake_articles": tot, "old_edition_records": len(ed_arts), "basis": basis})
                    for nr, orr, s in pairs:
                        if s >= MATCH_ART:
                            cur = remap.get(orr["id"])
                            if cur is None or s > cur[1]:
                                remap[orr["id"]] = (nr["id"], round(s, 4), basis)
    matched_old = collections.defaultdict(set)
    for oid, (nid, s, b) in remap.items():
        matched_old[oid.split(":")[1] + ":" + oid.split(":")[2]].add(oid)  # key = edition prefix inst:lb:xxx
    # old instrument / edition status
    ed_cov = {}
    for oi in old_inst:
        for ed in oi["editions"]:
            n = sum(1 for r in old_by_ed[ed["id"]] if r["id"] in remap)
            ed_cov[ed["id"]] = (n, len(old_by_ed[ed["id"]]))
    new_old_inst = []
    for oi in old_inst:
        covs = [ed_cov[e["id"]] for e in oi["editions"]]
        best = max(covs, key=lambda c: c[0] / c[1] if c[1] else 0)
        frac = best[0] / best[1] if best[1] else 0
        status = "superseded_by_intake" if frac >= 0.5 else "partially_covered_by_intake" if best[0] > 0 else "legacy_not_replaced"
        rank = 3 if status == "superseded_by_intake" else 2
        oi = dict(oi)
        oi.update({"legacy_status": status, "precedence_rank": rank, "intake_matches": inst_matches.get(oi["id"], []), "intake_matches_rejected": rejected.get(oi["id"], []),
                   "intake_coverage": {"matched_articles_best_edition": best[0], "records_best_edition": best[1], "fraction": round(frac, 4)}})
        oi["editions"] = [dict(e, intake_coverage={"matched": ed_cov[e["id"]][0], "records": ed_cov[e["id"]][1]}) for e in oi["editions"]]
        new_old_inst.append(oi)
        for m_ in oi["intake_matches"]:
            if m_["basis"] != "text_alignment_identity_unconfirmed":
                continue
            nm = oi["name"]["selected"].replace("_", " ")
            mn, my = re.search(r"رق[\u0640]*م\s*\(?\s*(\d+)", nm), re.search(r"(1[89]\d\d|20\d\d)", nm)
            Lm = law_by[m_["intake_instrument"][8:]]
            if (mn and mn.group(1) != str(Lm["law_number"])) or (my and my.group(1) != str(Lm["law_year"])):
                rv(oi["id"], "law_legacy_vs_intake", "high", "legacy_name_states_different_number_or_year_than_matched_intake_law",
                   {"legacy_name": oi["name"]["selected"], "matched_intake": [Lm["law_number"], Lm["law_year"]], "similarity": m_["mean_similarity"]})
        if rejected.get(oi["id"]):
            rv(oi["id"], "law_legacy_vs_intake", "medium", "similar_text_but_different_law_number_not_linked", rejected[oi["id"]][:4])
        if status != "legacy_not_replaced":
            ids = {m["intake_instrument"] for m in oi["intake_matches"]}
            rv(oi["id"], "law_legacy_vs_intake", "medium", f"legacy_{status}", {"name": oi["name"]["selected"], "intake_instruments": sorted(ids)[:8], "coverage": oi["intake_coverage"]})
    st_by_inst = {o["id"]: o["legacy_status"] for o in new_old_inst}
    out_old_art = []
    for r in old_art:
        r = dict(r)
        r["legacy_status"] = st_by_inst[r["instrument_id"]]
        r["precedence_rank"] = 3 if r["legacy_status"] == "superseded_by_intake" else 2
        r["intake_replacement"] = ({"article_id": remap[r["id"]][0], "similarity": remap[r["id"]][1], "basis": remap[r["id"]][2]} if r["id"] in remap else None)
        out_old_art.append(r)
    # per intake law: comparison with legacy
    for ni in new_inst:
        iid = ni["id"]
        sims = [s for (nid, s, b) in remap.values() if nid.startswith(f"art:in:{iid[8:]}:")]
        olds = sorted({m["intake_instrument"] and oi_id for oi_id, ms in inst_matches.items() for m in ms if m["intake_instrument"] == iid})
        if olds:
            ni["legacy_comparison"] = {"legacy_instruments": olds, "articles_matched": len(sims),
                                       "identical_text_search": sum(1 for s in sims if s >= 0.9999),
                                       "differing": sum(1 for s in sims if s < 0.9999), "min_similarity": round(min(sims), 4) if sims else None}
            if sims and min(sims) < 0.85:
                rv(iid, "law_intake_vs_legacy", "medium", "some_articles_differ_from_legacy_intake_wins",
                   {"articles_below_0.85": sum(1 for s in sims if s < 0.85), "of": len(sims)})
    for r in new_art:
        pass
    # ---- references remap (judgments + small collections)
    ids_new = {r["id"] for r in new_art}
    judg = jl_read(f"{B}/canonical/judgments/judgment_principles.jsonl.gz")
    cnt = collections.Counter()
    for j in judg:
        rr = j["references"]
        old = rr.get("law_refs_resolved", [])
        rr["law_refs_remapped_to_intake"] = list(dict.fromkeys(remap[x][0] for x in old if x in remap))
        rr["law_refs_not_remapped"] = [x for x in old if x not in remap]
        cnt["refs"] += len(old); cnt["remapped"] += sum(1 for x in old if x in remap)
        j["provenance"]["transformations"] = j["provenance"]["transformations"] + [{"step": "T22", "op": "remap_law_references_to_intake_where_text_verified"}]
    small = {}
    for k in ("defenses", "deadlines", "procedures", "principles"):
        small[k] = jl_read(f"{B}/canonical/{k}/{k}.jsonl.gz")

    def addmap(d):
        old = d.get("resolved", [])
        d["resolved_remapped_to_intake"] = list(dict.fromkeys(remap[x][0] for x in old if x in remap))
        d["not_remapped"] = [x for x in old if x not in remap]
    for r in small["defenses"]: addmap(r["supporting_legislation"])
    for r in small["deadlines"]: addmap(r["legal_authority"]["references_claimed"])
    for r in small["procedures"]: addmap(r["related"]["related_articles"])
    for r in small["principles"]: addmap(r["statutory_references_claimed"])

    # ---- full-text judgments
    existing_keys = {(j["branch"], int(j["identity"]["case"]), int(j["identity"]["year"])) for j in judg}
    fj, fj_rows, n_raw_j = build_fulltext_judgments(a.judgments_docx, docx_sha, existing_keys)
    for r in fj:
        ov = [j["id"] for j in judg if j["branch"] == r["branch"] and j["identity"]["case"] == r["identity"]["case"] and j["identity"]["year"] == r["identity"]["year"]]
        r["legacy_principle_overlap"] = ov

    # ---- intake's own review list + not-covered files
    for x in review_in:
        rv(x.get("instrument_id") or x.get("source_file"), "law_intake_open_item", "medium" if x["type"] != "other" else "low", x["type"],
           {"source_file": x.get("source_file"), "detail": x.get("detail"), "article_numbers": (x.get("article_numbers") or [])[:20]})
    notcov = [m for m in manifest if not m["status"].startswith(("exported", "removed duplicate", "skipped: byte"))]
    reasons = collections.Counter(re.sub(r"law-\d+-\d+", "law-N", m["status"]) for m in notcov)
    wjson(f"{O}/reports/intake_not_exported.json", {"total_source_files": len(manifest), "not_covered": len(notcov),
          "by_reason": dict(reasons.most_common()), "files": [{"file": m["file"], "status": m["status"], "type": m["type"], "scanned": m["scanned"]} for m in notcov]})

    # ---- write
    wjl(f"{O}/canonical/legislation/instruments.jsonl.gz", [egypt_inst] + new_old_inst + new_inst)
    wjl(f"{O}/canonical/legislation/articles_lexbridge.jsonl.gz", out_old_art)
    wjl(f"{O}/canonical/legislation/articles_law_intake.jsonl.gz", new_art)
    wjl(f"{O}/canonical/judgments/judgment_principles.jsonl.gz", judg)
    wjl(f"{O}/canonical/judgments/judgments_fulltext.jsonl.gz", fj)
    for k, v in small.items():
        wjl(f"{O}/canonical/{k}/{k}.jsonl.gz", v)
    wcsv(f"{O}/mappings/law_article_remap_legacy_to_intake.csv.gz", ["legacy_article_id", "intake_article_id", "similarity", "basis"],
         sorted((k, v[0], v[1], v[2]) for k, v in remap.items()))
    wcsv(f"{O}/mappings/judgment_fulltext_source_map.csv.gz", ["docx_title_paragraph", "case", "year", "new_id"], fj_rows)
    wjl(f"{O}/reports/human_review_items.jsonl.gz", jl_read(f"{B}/reports/human_review_items.jsonl.gz") + REVIEW)
    # raw archive: base copies + the two new sources
    if not a.no_raw_copy:
        os.makedirs(f"{O}/raw_archive", exist_ok=True)
        srcs = [os.path.join(B, "raw_archive", f) for f in sorted(os.listdir(f"{B}/raw_archive")) if f.endswith(".zip")] + [a.intake_zip, a.judgments_docx]
        lines = []
        for s in srcs:
            dst = f"{O}/raw_archive/{os.path.basename(s)}"
            if not os.path.exists(dst):
                shutil.copyfile(s, dst)
            os.chmod(dst, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            lines.append(f"{file_sha256(dst)}  {os.path.basename(s)}")
        open(f"{O}/raw_archive/SHA256SUMS", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    statc = collections.Counter(o["legacy_status"] for o in new_old_inst)
    summary = {
        "release": RELEASE, "base": "3.0.0-rc1", "import_date": IMPORT_DATE,
        "intake": {"archive_sha256": intake_sha, "source_files": len(manifest), "laws": len(new_inst), "articles": len(new_art),
                   "articles_main": sum(1 for r in new_art if r["article_role"] == "main"), "articles_issuing": sum(1 for r in new_art if r["article_role"] == "issuing"),
                   "files_not_covered": len(notcov), "not_covered_by_reason": dict(reasons.most_common(8)), "intake_open_review_items": len(review_in)},
        "legacy_laws": {"instruments": len(new_old_inst), "status": dict(statc), "article_records": len(out_old_art),
                        "articles_with_intake_replacement": sum(1 for r in out_old_art if r["intake_replacement"])},
        "judgment_law_refs": {"legacy_refs": cnt["refs"], "remapped_to_intake": cnt["remapped"], "not_remapped": cnt["refs"] - cnt["remapped"]},
        "judgments_fulltext": {"raw_in_docx": n_raw_j, "canonical_records": len(fj), "branch": dict(collections.Counter(r["branch"] for r in fj)),
                               "merged_identical_duplicates": sum(len(r["provenance"]["sources"]) - 1 for r in fj),
                               "variant_groups": len({r["variant_group"] for r in fj if r["variant_group"]})},
        "review_items_total": len(jl_read(f"{O}/reports/human_review_items.jsonl.gz")),
    }
    wjson(f"{O}/reports/build_summary.json", summary)
    man = {}
    for root, _, files in os.walk(O):
        for f in sorted(files):
            fp = os.path.join(root, f); rel = os.path.relpath(fp, O)
            if rel.startswith(("scripts", "docs", "raw_archive", "OUTPUT_MANIFEST", "RELEASE", "README", "reports/validation", "reports/baseline", "config/")) or (rel.startswith("reports/") and rel.endswith(".md")):
                continue
            man[rel] = hashlib.sha256(open(fp, "rb").read()).hexdigest()
    wjson(f"{O}/OUTPUT_MANIFEST.json", man)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
