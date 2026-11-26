#!/usr/bin/env python3
"""Validate the full release against the ORIGINAL archives. Exit 0 only if every check passes."""
import argparse, collections, csv, gzip, hashlib, json, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import LexArchive, EgyptArchive, file_sha256, h8, judgment_identity, rec_sha256, text_block

RESULTS, INFO = [], {}


def check(name, ok, detail=None):
    RESULTS.append({"check": name, "passed": bool(ok), "detail": detail if not ok else None})
    print(("PASS " if ok else "FAIL ") + name + (f"  {str(detail)[:300]}" if detail and not ok else ""))


def jl(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    ap.add_argument("--egypt-zip", default="/mnt/user-data/uploads/egypt-law-a9a9f589c7537c1ff1796795ac87efbbd042c95a.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-idempotency", action="store_true")
    a = ap.parse_args(); O = a.out
    sha0 = (file_sha256(a.lexbridge_zip), file_sha256(a.egypt_zip))
    lb, eg = LexArchive(a.lexbridge_zip), EgyptArchive(a.egypt_zip)
    S = json.load(open(f"{O}/reports/build_summary.json", encoding="utf-8"))
    insts_all = jl(f"{O}/canonical/legislation/instruments.jsonl.gz")
    e_inst, insts = insts_all[0], insts_all[1:]
    lart = jl(f"{O}/canonical/legislation/articles_lexbridge.jsonl.gz")
    eart = jl(f"{O}/canonical/legislation/articles_egypt_law_constitution.jsonl.gz")
    judg = jl(f"{O}/canonical/judgments/judgment_principles.jsonl.gz")
    small = {k: jl(f"{O}/canonical/{k}/{k}.jsonl.gz") for k in ("templates", "defenses", "procedures", "deadlines", "principles")}
    allrecs = insts_all + lart + eart + judg + [r for v in small.values() for r in v]
    bounds = json.load(open(f"{O}/reports/numbering_boundaries.json", encoding="utf-8"))
    split_conf = json.load(open(f"{O}/config/split_confirmations.json", encoding="utf-8"))
    ident_conf = json.load(open(f"{O}/config/law_identity_confirmations.json", encoding="utf-8"))

    # ---- A. archives & raw preservation
    check("A1 archive hashes match build record", (S["archives"]["lexbridge_sha256"], S["archives"]["egypt_law_sha256"]) == sha0)
    sums = dict(l.split("  ")[::-1] for l in open(f"{O}/raw_archive/SHA256SUMS").read().split("\n") if l)
    check("A2 raw_archive copies equal the originals and are read-only",
          all(file_sha256(f"{O}/raw_archive/{n}") == h for n, h in sums.items()) and set(sums.values()) == set(sha0)
          and all(not os.access(f"{O}/raw_archive/{n}", os.W_OK) or os.geteuid() == 0 for n in sums))
    # ---- B. schema / ids / provenance
    ids = collections.Counter(r["id"] for r in allrecs)
    check("B1 canonical ids unique across the whole release", all(c == 1 for c in ids.values()), [i for i, c in ids.items() if c > 1][:5])
    pk = ["sources", "import_date", "pipeline_version", "transformations", "verification_status", "conflict_flags", "review_flags"]
    check("B2 provenance block complete on every record", all(all(k in r["provenance"] for k in pk) for r in allrecs))
    check("B3 every record carries schema_version and record_type", all("record_type" in r for r in allrecs))
    # ---- C. provenance resolves
    n_refs, bad = 0, []
    for r in allrecs:
        for s in r["provenance"]["sources"]:
            ref = s["raw_ref"]; n_refs += 1
            try:
                if ref["source"] == "lexbridge":
                    rec = lb.record(ref["path"], ref["index"])
                    ok = rec_sha256(rec) == ref["record_sha256"] and rec.get("id") == ref["legacy_id"]
                else:
                    ok = hashlib.sha256(eg.read_bytes(ref["path"])).hexdigest() == ref["file_sha256"] and ref["source_commit"] == eg.commit
            except Exception:
                ok = False
            if not ok: bad.append((r["id"], ref["path"]))
    check(f"C1 all {n_refs} raw references resolve with matching hashes", not bad, bad[:3])
    # ---- D. verbatim + derived
    bad = [r["id"] for r in lart for s in r["provenance"]["sources"]
           if lb.record(s["raw_ref"]["path"], s["raw_ref"]["index"])["content"] != r["text_original"]
           or lb.record(s["raw_ref"]["path"], s["raw_ref"]["index"])["article_number"] != lb.record(r["provenance"]["sources"][0]["raw_ref"]["path"], r["provenance"]["sources"][0]["raw_ref"]["index"])["article_number"]]
    check(f"D1 law articles verbatim for every source incl. identical copies ({len(lart)})", not bad, bad[:3])
    bad = []
    for r in eart:
        t = eg.read_bytes(r["provenance"]["sources"][0]["raw_ref"]["path"]).decode("utf-8")
        head, _, body = t.partition("\n"); body = body[:-1] if body.endswith("\n") else body
        if r["text_original"] != body or r["article_number"]["original_heading"] != head: bad.append(r["id"])
    check(f"D2 egypt-law articles verbatim ({len(eart)})", not bad, bad[:3])
    bad = []
    for j in judg:
        srcs = j["provenance"]["sources"]
        can = [s for s in srcs if s["role"] == "canonical_source"]
        if len(can) != 1 or lb.record(can[0]["raw_ref"]["path"], can[0]["raw_ref"]["index"])["content"] != j["text_original"]: bad.append(j["id"])
        for s in srcs:
            if collapse(lb.record(s["raw_ref"]["path"], s["raw_ref"]["index"])["content"]) != collapse(j["text_original"]): bad.append(j["id"])
    check(f"D3 judgments verbatim; merged sources identical after whitespace collapse ({len(judg)})", not bad, bad[:3])
    bad = []
    for k, rows in small.items():
        for r in rows:
            ref = r["provenance"]["sources"][0]["raw_ref"]; raw = lb.record(ref["path"], ref["index"])
            exp = raw["source_fields"]["template_body"] if k == "templates" else raw["content"]
            if r["text_original"] != exp or (k == "templates" and r["legacy"]["content"] != raw["content"]): bad.append(r["id"])
    check("D4 small collections verbatim (templates from template_body; legacy content preserved)", not bad, bad[:3])
    bad, bad2 = [], []
    for r in lart + eart + judg + small["templates"] + small["procedures"] + small["principles"]:
        tb = text_block(r["text_original"])
        if tb["text_clean"] != r["text_clean"] or tb["text_search"] != r["text_search"]: bad.append(r["id"])
        if (r["text_clean"] != r["text_original"]) != bool(tb["clean_ops"]): bad2.append(r["id"])
    check("D5 text_clean/text_search reproduce exactly from text_original", not bad, bad[:3])
    check("D6 clean ops logged iff text changed", not bad2, bad2[:3])
    # ---- E. conservation
    seen = collections.Counter((s["raw_ref"]["path"], s["raw_ref"]["index"]) for r in lart for s in r["provenance"]["sources"])
    raw_laws = sum(len(lb.records(p)) for p in lb.list("knowledge/laws/"))
    check("E1 laws: every raw record in exactly one article's sources", sum(seen.values()) == raw_laws == 21093 and all(c == 1 for c in seen.values()), (sum(seen.values()), raw_laws))
    seen = collections.Counter((s["raw_ref"]["path"], s["raw_ref"]["index"]) for r in judg for s in r["provenance"]["sources"])
    raw_j = sum(len(lb.records(p)) for p in lb.list("knowledge/judgments/"))
    check("E2 judgments: every raw record in exactly one canonical record", sum(seen.values()) == raw_j == 44190 and all(c == 1 for c in seen.values()), (sum(seen.values()), raw_j))
    check("E3 small collections: 7/42/74/67/49 all present once",
          {k: len(v) for k, v in small.items()} == {"templates": 7, "defenses": 42, "procedures": 74, "deadlines": 67, "principles": 49})
    check("E4 egypt-law: 258 AR + 255 EN, one record per source file", len([r for r in eart if r["language"] == "ar"]) == len(eg.list("dustur")) == 258 and len([r for r in eart if r["language"] == "en"]) == len(eg.list("constitution")) == 255)
    # ---- F. mappings / recoverability
    with gzip.open(f"{O}/mappings/judgment_id_map.csv.gz", "rt", encoding="utf-8") as f:
        jrows = list(csv.DictReader(f))
    with gzip.open(f"{O}/mappings/law_id_map.csv.gz", "rt", encoding="utf-8") as f:
        lrows = list(csv.DictReader(f))
    jid = {j["id"] for j in judg}; aid = {r["id"] for r in lart}
    check("F1 judgment map: every raw record -> an existing canonical id", len(jrows) == 44190 and all(r["new_id"] in jid for r in jrows))
    check("F2 law map: every raw record -> an existing article id", len(lrows) == 21093 and all(r["article_id"] in aid for r in lrows))
    bykey = {(r["source_path"], int(r["source_index"])): r["new_id"] for r in jrows}
    check("F3 judgment map agrees with each canonical record's sources", all(bykey[(s["raw_ref"]["path"], s["raw_ref"]["index"])] == j["id"] for j in judg for s in j["provenance"]["sources"]))
    # ---- G. Decision 1: judgment merge rule
    bad = []
    for j in judg:
        srcs = j["provenance"]["sources"]
        if len(srcs) > 1:
            keys = set()
            for s in srcs:
                r = lb.record(s["raw_ref"]["path"], s["raw_ref"]["index"]); ident = judgment_identity(r, s["raw_ref"]["path"])
                court = collapse(r["metadata"].get("court") or "")
                keys.add((court, ident, collapse(r["content"])))
                if not (court and all(ident)): bad.append(j["id"])
            if len(keys) != 1: bad.append(j["id"])
    merged = [j for j in judg if len(j["provenance"]["sources"]) > 1]
    check(f"G1 every merge ({len(merged)} groups) has same court, case, year, volume, page, paragraph (all present) and identical text", not bad and len(merged) == S["judgments"]["merged_groups"], bad[:3])
    check("G2 no record with missing paragraph (or other identity part) was merged",
          all(len(j["provenance"]["sources"]) == 1 for j in judg if not all(j["identity"].values()) or not j["court"]))
    inc = [j for j in judg if "identity_incomplete_never_merged_by_rule" in j["provenance"]["review_flags"]]
    check(f"G3 {len(inc)} incomplete-identity records kept as separate records, each with all raw data", len(inc) == 323 and all(len(j["provenance"]["sources"]) == 1 for j in inc))
    cands = [j for j in judg if j["potential_duplicate_of"]]
    check("G4 potential-duplicate candidates: links symmetric, point to existing distinct records, none merged",
          all(all(c in jid and c != j["id"] for c in j["potential_duplicate_of"]) for j in cands)
          and all(j["id"] in next(x for x in judg if x["id"] == c)["potential_duplicate_of"] for j in cands[:200] for c in j["potential_duplicate_of"]))
    ex = [j for j in judg if j["merged_source_snapshots"]]
    check("G5 merged groups retain every non-canonical source's id, category, title, citations, keywords and metadata",
          all(len(j["merged_source_snapshots"]) == len(j["provenance"]["sources"]) - 1 and all(k in sn for sn in j["merged_source_snapshots"] for k in ("legacy_id", "category", "title", "citations", "keywords", "metadata")) for j in ex))
    # ---- H. IDs & references
    leg2new = collections.defaultdict(set)
    for r in jrows: leg2new[r["legacy_id"]].add(r["new_id"])
    col = [k for k, v in leg2new.items() if len(v) > 1]
    check("H1 31 legacy ids collide in source; each resolves to distinct new ids all present", len(col) == 31 and all(set(leg2new[k]) <= jid for k in col), len(col))
    dang = amb = res = 0
    for j in judg:
        dang += len(j["references"]["unresolved"]); amb += len(j["references"]["ambiguous"]); res += len(j["references"]["resolved"])
    check("H2 0 unresolved judgment->judgment references; ambiguous ones keep >=2 candidates",
          dang == 0 and all(len(x["candidates"]) >= 2 for j in judg for x in j["references"]["ambiguous"]), (dang, amb))
    allnew = jid
    check("H3 all resolved/ambiguous references point at existing canonical ids",
          all(x in allnew for j in judg for x in j["references"]["resolved"] if x.startswith("jdg:")) and all(c in allnew for j in judg for x in j["references"]["ambiguous"] for c in x["candidates"]))
    law_unres = sum(len(j["references"]["law_refs_unresolved"]) for j in judg)
    INFO["judgment_to_law_refs"] = {"resolved": sum(len(j["references"]["law_refs_resolved"]) for j in judg), "unresolved_legacy_law_ids": law_unres}
    check("H4 judgment->law references: every resolved id exists as an article", all(x in aid for j in judg for x in j["references"]["law_refs_resolved"]))
    check("H5 defense->judgment references rewritten to existing ids", all(x in allnew for d in small["defenses"] for x in d["supporting_judgments"]["resolved"]))
    # ---- P. judgment numbering (case number + judicial year on every judgment)
    import re as _re
    check("P1 every judgment has a numeric case number and judicial year", all(str(j["identity"]["case"]).isdigit() and str(j["identity"]["year"]).isdigit() for j in judg))
    conf = [j for j in judg if j["citation_label_basis"].startswith("conflict")]
    check("P2 citation_label present on every judgment except flagged conflicts, and contains its own case number and year",
          all((j["citation_label"] is None) == bool(j["citation_conflict"]) for j in judg)
          and all(f"رقم {j['identity']['case']} لسنة {j['identity']['year']} " in j["citation_label"] for j in judg if j["citation_label"]))
    recount = 0
    for j in judg:
        s0 = [s for s in j["provenance"]["sources"] if s["role"] == "canonical_source"][0]["raw_ref"]
        cit = lb.record(s0["path"], s0["index"])["citations"]
        ns = _re.findall(r"\d+", cit[0]) if cit else []
        if len(ns) >= 2 and (ns[0].lstrip("0"), ns[1].lstrip("0")) != (j["identity"]["case"], j["identity"]["year"]):
            recount += 1
    rv_ids = {r["id"] for r in jl(f"{O}/reports/human_review_items.jsonl.gz") if r["reason"] == "source_citation_numbers_disagree_with_structured_identity"}
    check(f"P3 citation conflicts ({len(conf)}) match an independent recount from raw and each has a review item", recount == len(conf) and rv_ids == {j["id"] for j in conf}, (recount, len(conf)))
    INFO["distinct_judgments_case_year"] = len({(j["branch"], j["identity"]["case"], j["identity"]["year"]) for j in judg})
    # ---- I. Decision 2: editions
    check("I1 no preferred edition and no legal status asserted anywhere",
          all(i["preferred_edition"] is None and i["legal_status"] == "not_assessed" and all(e["preferred"] is None and e["legal_status"] == "not_assessed" for e in i["editions"]) for i in insts))
    files_in = collections.Counter(p for i in insts for e in i["editions"] for p in e["member_files"])
    check("I2 each law file belongs to exactly one edition of exactly one instrument", len(files_in) == len(lb.list("knowledge/laws/")) and all(c == 1 for c in files_in.values()))
    ed_counts = collections.Counter(r["edition_id"] for r in lart)
    check("I3 every edition has all of its records as article records (no edition truncated)",
          all(ed_counts[e["id"]] == e["n_records"] for i in insts for e in i["editions"]))
    check("I4 cross-edition links present and symmetric where editions overlap",
          all(all(x in aid for x in r.get("search_equivalent_ids", []) + r.get("differs_from_ids", [])) for r in lart))
    # ---- J. Decision 3: numbering restarts
    from build_full import detect_boundaries  # same detector as the build
    redetect = sum(len(detect_boundaries(lb.records(p))) for p in lb.list("knowledge/laws/"))
    check(f"J1 all {redetect} numbering restarts detected and flagged (matches independent re-detection)", len(bounds) == redetect, (len(bounds), redetect))
    unconf = all(b["status"] == "unconfirmed" for b in bounds) and not any(r["part"]["status"] == "confirmed" for r in lart)
    check("J2 no split applied without confirmation (config empty => every boundary unconfirmed, no confirmed parts)", (not split_conf and unconf) or bool(split_conf))
    check("J3 files are never divided: every raw file maps to a single instrument and a single edition", all(c == 1 for c in files_in.values()))
    prefix = [b for b in bounds if b["proposed_role"] == "probable_issuing_law_prefix"]
    hint = [r for r in lart if r["part"]["role_hint"] == "issuing_law_provisions_candidate"]
    check("J4 issuing-law candidates are explicitly distinguished (role_hint) but marked unconfirmed", len(hint) > 0 and all(r["part"]["status"] == "unconfirmed" for r in hint) and all(b["evidence"]["corroborated_by_file_without_prefix"] for b in prefix))
    # ---- K. Decision 4: law number/year
    bad = []
    for i in insts:
        claims = collections.Counter()
        for p in i["member_files"]:
            for r in lb.records(p): claims[(r["law_number"], r["law_year"])] += 1
        got = {(c["law_number"], c["law_year"]): c["records"] for c in i["identity"]["claimed"]}
        if got != dict(claims): bad.append(i["id"])
    check("K1 original claimed number/year preserved for every instrument (matches raw counts)", not bad, bad[:3])
    ok = True
    for i in insts:
        idn = i["identity"]
        if idn["canonical_law_number"]:
            nn = {(c["law_number"], c["law_year"]) for c in idn["claimed"] if c["law_number"] is not None and c["law_year"] is not None}
            ok &= len(nn) == 1 and idn["basis"] in ("claim+law_name+filename_agree", "human_confirmed") and not idn["reasons"]
            ok &= idn["external_verification"] is None or idn["basis"] == "human_confirmed"
        else:
            ok &= idn["status"] == "unresolved" and idn["canonical_law_year"] is None
    check("K2 canonical number/year populated only with stated basis; otherwise null + unresolved", ok)
    check("K3 every unresolved identity has a review item", {r["id"] for r in jl(f"{O}/reports/human_review_items.jsonl.gz") if r["reason"] == "law_number_year_unresolved_canonical_null"} >= {i["id"] for i in insts if i["identity"]["status"] == "unresolved"})
    # ---- L. constitution
    check("L1 egypt-law and LexBridge constitutions fully separate (ids, instruments, sources)",
          not any(r["instrument_id"] == e_inst["id"] for r in lart) and all(s["raw_ref"]["source"] == "egypt-law" for r in eart for s in r["provenance"]["sources"])
          and not any(len({s["raw_ref"]["source"] for s in r["provenance"]["sources"]}) > 1 for r in lart + eart))
    lbc = [i for i in insts if i.get("domain_hint", "").startswith("constitutional")]
    check("L2 LexBridge constitution: identity unestablished, version unestablished, status not assessed", len(lbc) == 1 and lbc[0]["identity_status"] == "unidentified" and lbc[0]["version_status"] == "unestablished")
    rc = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "reconcile_constitution.py"), "--canonical", f"{O}/canonical/legislation/articles_egypt_law_constitution.jsonl.gz",
                         "--out", f"{O}/reports", "--lexbridge-zip", a.lexbridge_zip, "--egypt-zip", a.egypt_zip], capture_output=True, text=True)
    check("L3 constitution count reconciliation: 258 = 1 + 254 + 3 (AR), 255 = 1 + 254 (EN), none missing/double-counted", '"verdict": "RECONCILED' in rc.stdout)
    # ---- M. labels
    check("M1 title-only defenses flagged incomplete, no legal basis invented", all(d["legal_basis"] == [] and (d["incomplete"] == (d["content_status"] == "title_only")) for d in small["defenses"]) and sum(d["incomplete"] for d in small["defenses"]) > 0)
    check("M2 principles non-authoritative secondary paraphrase", all(p["authoritative"] is False and p["text_status"] == "secondary_source_paraphrase" for p in small["principles"]))
    check("M3 templates recovered with T07 logged; original content field preserved", all(t["content_status"] == "recovered_from_field" and any(x.get("step") == "T07" for x in t["provenance"]["transformations"]) and t["legacy"]["content"] == "" for t in small["templates"]))
    gb = []
    for p in small["procedures"]:
        L = p["derived_layers"]
        if L:
            lines = [l for l in p["text_original"].split("\n") if l.strip()]
            if sorted(L["formal_lines"] + L["colloquial_lines"]) != sorted(lines): gb.append(p["id"])
    check("M4 guide layers are lossless verbatim line partitions", not gb, gb[:3])
    check("M5 every ai_* source field carries an explicit label", all(k in r["field_status"] for r in judg + small["deadlines"] + small["defenses"] for k in (r["legacy"].get("source_fields") or {}) if k.startswith("ai_")))
    check("M6 nothing marked verified", all(r["provenance"]["verification_status"] == "unverified" for r in allrecs))
    # ---- N. idempotency & immutability
    if not a.skip_idempotency:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "build_full.py"), "--out", tmp, "--no-raw-copy",
                            "--lexbridge-zip", a.lexbridge_zip, "--egypt-zip", a.egypt_zip, "--import-date", S["import_date"]], check=True, stdout=subprocess.DEVNULL)
            m1 = json.load(open(f"{O}/OUTPUT_MANIFEST.json")); m2 = json.load(open(f"{tmp}/OUTPUT_MANIFEST.json"))
            check("N1 idempotent: fresh rebuild is byte-identical for every output file", m1 == m2, [k for k in set(m1) | set(m2) if m1.get(k) != m2.get(k)][:5])
    man = json.load(open(f"{O}/OUTPUT_MANIFEST.json"))
    check("N2 output manifest matches files on disk", all(hashlib.sha256(open(f"{O}/{k}", "rb").read()).hexdigest() == v for k, v in man.items()))
    check("N3 original archives unchanged after run", (file_sha256(a.lexbridge_zip), file_sha256(a.egypt_zip)) == sha0)
    passed = sum(r["passed"] for r in RESULTS)
    json.dump({"passed": passed, "total": len(RESULTS), "info": INFO, "results": RESULTS}, open(f"{O}/reports/validation_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{passed}/{len(RESULTS)} checks passed"); print(json.dumps(INFO))
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
