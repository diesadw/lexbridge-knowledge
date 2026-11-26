#!/usr/bin/env python3
"""Validate v3.1.0-rc1 (law intake + full-text judgments + legacy precedence) against the original sources."""
import argparse, collections, csv, gzip, hashlib, json, os, re, subprocess, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import file_sha256, rec_sha256, text_block
from integrate_intake import docx_paragraphs, split_judgments, parse_title

RESULTS = []


def check(name, ok, detail=None):
    RESULTS.append({"check": name, "passed": bool(ok), "detail": None if ok else str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + (f"  {str(detail)[:250]}" if detail and not ok else ""))


def jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--intake-zip", required=True)
    ap.add_argument("--judgments-docx", required=True)
    ap.add_argument("--skip-idempotency", action="store_true")
    a = ap.parse_args(); O, B = a.out, a.base
    S = json.load(open(f"{O}/reports/build_summary.json", encoding="utf-8"))
    sha_in = (file_sha256(a.intake_zip), file_sha256(a.judgments_docx))
    m2 = None
    if not a.skip_idempotency:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "integrate_intake.py"), "--base", B, "--intake-zip", a.intake_zip,
                            "--judgments-docx", a.judgments_docx, "--out", tmp, "--no-raw-copy", "--import-date", S["import_date"]], check=True, stdout=subprocess.DEVNULL)
            m2 = json.load(open(f"{tmp}/OUTPUT_MANIFEST.json"))
    # ---- A raw archive
    sums = dict(l.rstrip("\n").split("  ", 1)[::-1] for l in open(f"{O}/raw_archive/SHA256SUMS", encoding="utf-8") if l.strip())
    check("A1 raw_archive has the 2 base zips + the intake zip + the judgments docx, hashes verified",
          len(sums) == 4 and all(file_sha256(f"{O}/raw_archive/{n}") == h for n, h in sums.items()) and set(sha_in) <= set(sums.values()))
    base_man = json.load(open(f"{B}/OUTPUT_MANIFEST.json"))
    check("A2 base release v3.0.0-rc1 untouched (every file hash matches its manifest)",
          all(hashlib.sha256(open(f"{B}/{k}", "rb").read()).hexdigest() == v for k, v in base_man.items()))
    # ---- load
    I = jl(f"{O}/canonical/legislation/instruments.jsonl.gz")
    old_inst = [i for i in I if i["id"].startswith("inst:lb:")]; new_inst = [i for i in I if i["id"].startswith("inst:in:")]
    old_art = jl(f"{O}/canonical/legislation/articles_lexbridge.jsonl.gz")
    new_art = jl(f"{O}/canonical/legislation/articles_law_intake.jsonl.gz")
    egy = jl(f"{O}/canonical/legislation/articles_egypt_law_constitution.jsonl.gz")
    jp = jl(f"{O}/canonical/judgments/judgment_principles.jsonl.gz")
    jf = jl(f"{O}/canonical/judgments/judgments_fulltext.jsonl.gz")
    small = {k: jl(f"{O}/canonical/{k}/{k}.jsonl.gz") for k in ("templates", "defenses", "procedures", "deadlines", "principles")}
    allrecs = I + old_art + new_art + egy + jp + jf + [r for v in small.values() for r in v]
    ids = collections.Counter(r["id"] for r in allrecs)
    check("B1 ids unique across the whole release", all(c == 1 for c in ids.values()), [i for i, c in ids.items() if c > 1][:5])
    # ---- B intake
    zi = zipfile.ZipFile(a.intake_zip)
    art_lines = [l for l in zi.read("law_intake_output/articles.jsonl").decode("utf-8").split("\n") if l.strip()]
    laws_src = [json.loads(l) for l in zi.read("law_intake_output/laws.jsonl").decode("utf-8").split("\n") if l.strip()]
    check("B2 all intake laws and articles imported exactly once",
          len(new_inst) == len(laws_src) == 386 and len(new_art) == len(art_lines) == 16597
          and {i["id"][8:] for i in new_inst} == {l["instrument_id"] for l in laws_src})
    bad = []
    for r in new_art:
        ref = r["provenance"]["sources"][0]["raw_ref"]
        obj = json.loads(art_lines[ref["index"]])
        if (r["text_original"] != obj["text"] or r["citation_label"] != obj["citation_label"] or rec_sha256(obj) != ref["record_sha256"]
                or r["article_number"]["canonical"] != obj["article_number"] or r["instrument_id"] != "inst:in:" + obj["instrument_id"]):
            bad.append(r["id"])
    check(f"B3 every intake article is verbatim vs the intake file (text, number, citation label, hash) ({len(new_art)})", not bad, bad[:3])
    bad = []
    for i in new_inst:
        l = laws_src[i["provenance"]["sources"][0]["raw_ref"]["index"]]
        q = (l["identity_evidence"]["quote"] or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        if not (i["law_number"] == l["law_number"] and i["law_year"] == l["law_year"] and str(l["law_number"]) in re.findall(r"\d+", q) and str(l["law_year"]) in re.findall(r"\d+", q)):
            bad.append(i["id"])
    check("B4 every intake law number/year equals the intake record and appears in its own heading quote", not bad, bad[:3])
    cnt = collections.Counter(r["instrument_id"] for r in new_art)
    check("B5 per-law exported counts match", all(cnt["inst:in:" + l["instrument_id"]] == i["counts"]["exported"] for l, i in zip(laws_src, new_inst)))
    with tempfile.TemporaryDirectory() as t:
        zi.extractall(t)
        rc = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "validate_law_intake.py"), f"{t}/law_intake_output"], capture_output=True, text=True)
    check("B6 the intake file itself passes the intake validator (ERRORS=0)", "ERRORS=0" in rc.stdout, rc.stdout[:200])
    check("B7 no citation label contains structure words (book/part/chapter)", not any(re.search("الكتاب|الباب|الفصل", r["citation_label"]) for r in new_art))
    # ---- C judgments full text
    P = docx_paragraphs(a.judgments_docx)
    J = split_judgments(P)
    srcs = collections.Counter(s["raw_ref"]["paragraph_title"] for r in jf for s in r["provenance"]["sources"])
    check(f"C1 every one of the {len(J)} judgments in the docx appears exactly once across canonical sources", len(J) == 76 and set(srcs) == {j["title_idx"] for j in J} and all(c == 1 for c in srcs.values()), (len(srcs), len(J)))
    byt = {j["title_idx"]: j for j in J}
    bad = []
    for r in jf:
        for s in r["provenance"]["sources"]:
            j = byt[s["raw_ref"]["paragraph_title"]]
            if "\n".join(j["body"]) != r["text_original"] or j["title"] != r["title_original"]:
                bad.append(r["id"])
    check("C2 full text and title verbatim vs the docx (all paragraphs, nothing added or removed)", not bad, bad[:3])
    leak = [r["id"] for r in jf if re.search(r"https?://|lawhub|المصدر\s*:", json.dumps({k: r[k] for k in ("title_original", "subject", "text_original", "text_clean")}, ensure_ascii=False))]
    check("C3 no source link / 'المصدر:' line remains in any judgment record", not leak, leak[:3])
    check("C4 body excludes the website heading line and the source line", all(not r["text_original"].startswith("نص الحكم") for r in jf))
    bad = []
    for r in jf:
        pt = parse_title(r["title_original"])
        if not (pt and r["identity"] == {"case": str(pt["case"]), "year": str(pt["year"])} and r["session_date"] == pt["date_iso"]
                and r["citation_label"] == f"الطعن رقم {pt['case']} لسنة {pt['year']} قضائية" and r["session_date"]):
            bad.append(r["id"])
    check("C5 every judgment has case number, judicial year, valid session date and a matching citation_label", not bad, bad[:3])
    byg = collections.defaultdict(list)
    for r in jf: byg[(r["branch"], r["identity"]["case"], r["identity"]["year"], r["session_date"])].append(r)
    ok = True
    for g in byg.values():
        texts = {x["text_original"] for x in g}
        ok &= len(texts) == len(g)  # same text => merged; different text => separate
        ok &= all((x["variant_group"] is not None) == (len(g) > 1) for x in g)
    check("C6 duplicates: identical texts merged; same judgment with different texts kept as separate flagged variants", ok and S["judgments_fulltext"]["variant_groups"] == 1)
    for r in jf:
        t = text_block(r["text_original"])
        if t["text_clean"] != r["text_clean"] or t["text_search"] != r["text_search"]:
            check("C7 derived text reproducible", False, r["id"]); break
    else:
        check("C7 derived text reproducible for every judgment", True)
    # ---- D precedence / preservation
    old_base = {r["id"]: r for r in jl(f"{B}/canonical/legislation/articles_lexbridge.jsonl.gz")}
    check("D1 no legacy law article was removed or altered (text and ids identical to v3.0.0)",
          set(old_base) == {r["id"] for r in old_art} and all(old_base[r["id"]]["text_original"] == r["text_original"] for r in old_art))
    base_inst = {i["id"]: i for i in jl(f"{B}/canonical/legislation/instruments.jsonl.gz")}
    check("D2 no legacy instrument removed", set(base_inst) <= {i["id"] for i in I})
    base_j = {r["id"]: r for r in jl(f"{B}/canonical/judgments/judgment_principles.jsonl.gz")}
    check("D3 judgment principles unchanged (ids and text identical to v3.0.0)", set(base_j) == {r["id"] for r in jp} and all(base_j[r["id"]]["text_original"] == r["text_original"] and base_j[r["id"]]["references"]["law_refs_resolved"] == r["references"]["law_refs_resolved"] for r in jp))
    allowed = {"superseded_by_intake", "partially_covered_by_intake", "legacy_not_replaced"}
    new_ids = {i["id"] for i in new_inst}
    check("D4 every legacy instrument has a legacy_status and rank; all matches point to real intake laws",
          all(i["legacy_status"] in allowed and i["precedence_rank"] in (2, 3) and (i["legacy_status"] == "superseded_by_intake") == (i["precedence_rank"] == 3) for i in old_inst)
          and all(m["intake_instrument"] in new_ids for i in old_inst for m in i["intake_matches"]))
    nmap = {i["id"]: (str(i["law_number"]), str(i["law_year"])) for i in new_inst}
    check("D5 identity gate: a legacy instrument with a known number/year is only linked to the SAME number/year",
          all(nmap[m["intake_instrument"]] == (i["identity"]["canonical_law_number"], i["identity"]["canonical_law_year"])
              for i in old_inst if i["identity"]["canonical_law_number"] for m in i["intake_matches"])
          and all(nmap[m["intake_instrument"]] != (i["identity"]["canonical_law_number"], i["identity"]["canonical_law_year"]) for i in old_inst for m in i["intake_matches_rejected"]))
    with gzip.open(f"{O}/mappings/law_article_remap_legacy_to_intake.csv.gz", "rt", encoding="utf-8") as f:
        rm = list(csv.DictReader(f))
    oid = {r["id"]: r for r in old_art}; nid = {r["id"] for r in new_art}
    check(f"D6 remap table ({len(rm)} rows): every id exists, similarity >= 0.5, consistent with the records",
          all(r["legacy_article_id"] in oid and r["intake_article_id"] in nid and float(r["similarity"]) >= 0.5 for r in rm)
          and sum(1 for r in old_art if r["intake_replacement"]) == len(rm)
          and all(oid[r["legacy_article_id"]]["intake_replacement"]["article_id"] == r["intake_article_id"] for r in rm))
    ok = True
    for j in jp:
        rr = j["references"]
        old = rr["law_refs_resolved"]
        ok &= set(rr["law_refs_remapped_to_intake"]) <= nid
        ok &= {x for x in old if x not in {r["legacy_article_id"] for r in rm}} == set(rr["law_refs_not_remapped"]) if False else True
    mapped_old = {r["legacy_article_id"] for r in rm}
    ok &= all(set(j["references"]["law_refs_not_remapped"]) == {x for x in j["references"]["law_refs_resolved"] if x not in mapped_old} for j in jp)
    check("D7 judgment->law references: original list kept; remapped + not_remapped account for every original reference", ok)
    check("D8 remapped references account: total = remapped + not remapped", S["judgment_law_refs"]["legacy_refs"] == S["judgment_law_refs"]["remapped_to_intake"] + S["judgment_law_refs"]["not_remapped"])
    # ---- E global safety
    check("E1 egypt-law constitution records unchanged and separate", len(egy) == 513 and all(r["provenance"]["sources"][0]["raw_ref"]["source"] == "egypt-law" for r in egy))
    check("E2 nothing marked verified; no legal status asserted; no preferred edition",
          all(r["provenance"]["verification_status"] == "unverified" for r in allrecs)
          and all(i["legal_status"] == "not_assessed" for i in I if "legal_status" in i) and all(i.get("preferred_edition") is None for i in old_inst))
    check("E3 intake laws carry source_heading_evidence only (no external verification claimed)", all(i["identity"]["external_verification"] is None for i in new_inst))
    # ---- F idempotency (rebuild ran at the start, before the data was loaded)
    if m2 is not None:
        m1 = json.load(open(f"{O}/OUTPUT_MANIFEST.json"))
        check("F1 idempotent: fresh rebuild is byte-identical for every output file", m1 == m2, [k for k in set(m1) | set(m2) if m1.get(k) != m2.get(k)][:5])
    man = json.load(open(f"{O}/OUTPUT_MANIFEST.json"))
    check("F2 output manifest matches files on disk", all(hashlib.sha256(open(f"{O}/{k}", "rb").read()).hexdigest() == v for k, v in man.items()))
    check("F3 inputs unchanged after run", (file_sha256(a.intake_zip), file_sha256(a.judgments_docx)) == sha_in)
    passed = sum(r["passed"] for r in RESULTS)
    json.dump({"passed": passed, "total": len(RESULTS), "results": RESULTS}, open(f"{O}/reports/validation_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{passed}/{len(RESULTS)} checks passed"); sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
