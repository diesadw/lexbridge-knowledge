#!/usr/bin/env python3
"""Validate the output of the LexBridge Law Intake task (schema lexbridge-law-intake-v1).

  python validate_law_intake.py law_intake_output/            # prints a report, writes validation_report.json
Exit code 1 if there is any ERROR. Warnings need human attention but do not fail.
"""
import collections, json, os, re, sys

AD = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
ERR, WARN = [], []


def jl(path, required=True):
    if not os.path.exists(path):
        if required:
            ERR.append(("E00", path, "missing file"))
        return []
    out = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception as e:
                ERR.append(("E00", f"{path}:{n}", f"invalid JSON: {e}"))
    return out


def label(a, L):
    n = a["article_number"]
    num = f"{n} {a['bis']}" if a.get("bis") else f"{n}"
    N, Y = L["law_number"], L["law_year"]
    if a["article_role"] == "issuing":
        return f"المادة {num} من القانون رقم {N} لسنة {Y} (مواد الإصدار)"
    if L.get("code_name"):
        return f"المادة {num} من {L['code_name']} (الصادر بالقانون رقم {N} لسنة {Y})"
    return f"المادة {num} من القانون رقم {N} لسنة {Y}"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    D = sys.argv[1]
    laws = jl(f"{D}/laws.jsonl"); arts = jl(f"{D}/articles.jsonl"); review = jl(f"{D}/review_list.jsonl", required=False)
    manifest = {}
    if os.path.exists(f"{D}/source_manifest.json"):
        m = json.load(open(f"{D}/source_manifest.json", encoding="utf-8"))
        manifest = {x["file"]: x for x in (m if isinstance(m, list) else m.get("files", []))}
    else:
        ERR.append(("E00", "source_manifest.json", "missing file"))
    L = {}
    for l in laws:
        iid = l.get("instrument_id")
        if iid in L:
            ERR.append(("E03", iid, "duplicate instrument_id"))
        L[iid] = l
        n, y = l.get("law_number"), l.get("law_year")
        if not (isinstance(n, int) and isinstance(y, int) and 1800 <= y <= 2100 and n > 0):
            ERR.append(("E01", iid, f"law_number/law_year must be integers (got {n!r}/{y!r}); if unknown the law must not be exported"))
            continue
        q = ((l.get("identity_evidence") or {}).get("quote") or "").translate(AD)
        nums = re.findall(r"\d+", q)
        if not q or str(n) not in nums or str(y) not in nums:
            ERR.append(("E02", iid, f"identity_evidence.quote must be the heading and contain {n} and {y}: {q[:80]!r}"))
        if l.get("source_file") not in manifest:
            ERR.append(("E10", iid, f"source_file not in source_manifest: {l.get('source_file')}"))
        if l.get("filename_agrees") is False:
            WARN.append(("W03", iid, "filename disagrees with the heading (heading was used)"))
        if re.search(r"الكتاب|الباب|الفصل|الفرع", l.get("instrument_title", "")[:40]) and not l.get("code_name"):
            WARN.append(("W06", iid, "instrument_title mentions a structure label (book/part/chapter) - check it is really the law title"))
    seen = collections.Counter()
    per = collections.defaultdict(list)
    for a in arts:
        iid = a.get("instrument_id")
        k = (iid, a.get("article_role"), a.get("article_number"), a.get("bis") or "")
        l = L.get(iid)
        if l is None:
            ERR.append(("E04", str(k), "article references unknown instrument_id")); continue
        if (a.get("law_number"), a.get("law_year")) != (l["law_number"], l["law_year"]):
            ERR.append(("E04", str(k), "article law_number/law_year differ from its instrument"))
        if not isinstance(a.get("article_number"), int) or a.get("article_role") not in ("main", "issuing"):
            ERR.append(("E09", str(k), "article_number must be int and article_role 'main' or 'issuing'")); continue
        seen[k] += 1
        per[(iid, a["article_role"])].append(a["article_number"] if not a.get("bis") else None)
        if a.get("citation_label") != label(a, l):
            ERR.append(("E05", str(k), f"citation_label should be {label(a, l)!r}, got {a.get('citation_label')!r}"))
        t = a.get("text") or ""
        if len(t.strip()) < 10 and not a.get("source_annotations"):
            ERR.append(("E06", str(k), f"empty/very short text {t!r} without source_annotations"))
        if re.match(r"^\s*(?:ال)?مادة\s*\(?\s*[\d٠-٩]+", t):
            ERR.append(("E08", str(k), "text starts with an article header; header belongs in article_number_original"))
        if re.search(r"<[a-zA-Z/][^>]*>|\*\*|^#{1,6} ", t, re.M) or BIDI.search(t):
            ERR.append(("E08", str(k), "text contains HTML/markdown/bidi control characters"))
        if re.search(r"^\s*-?\s*[\d٠-٩]{1,4}\s*-?\s*$", t, re.M):
            WARN.append(("W07", str(k), "text has a line that looks like a stray page number"))
        if re.search(r"الكتاب|الباب|الفصل", a.get("citation_label", "")):
            ERR.append(("E11", str(k), "structure label leaked into citation_label"))
        if a.get("source_file") not in manifest:
            ERR.append(("E10", str(k), f"source_file not in source_manifest: {a.get('source_file')}"))
        if a.get("ocr_uncertain") or a.get("extraction_confidence") == "low":
            WARN.append(("W05", str(k), "low confidence / OCR uncertain"))
    for k, c in seen.items():
        if c > 1:
            ERR.append(("E07", str(k), f"duplicate article key x{c} (same law, role, number, bis)"))
    gaps_reviewed = {r.get("instrument_id") for r in review if r.get("type") == "sequence_gap"}
    for (iid, role), nums in sorted(per.items()):
        plain = [n for n in nums if n is not None]
        if not plain:
            continue
        missing = [i for i in range(min(plain), max(plain) + 1) if i not in set(plain)]
        if missing:
            WARN.append(("W01", f"{iid}/{role}", f"gaps {missing[:15]}{'...' if len(missing) > 15 else ''}" + (" (has review entry)" if iid in gaps_reviewed else " (NO review entry)")))
        if min(plain) != 1:
            WARN.append(("W02", f"{iid}/{role}", f"numbering starts at {min(plain)}, not 1"))
        if plain != sorted(plain):
            WARN.append(("W02", f"{iid}/{role}", "articles are not in ascending order in the output"))
    for iid, l in L.items():
        got = sum(1 for a in arts if a.get("instrument_id") == iid and a.get("article_role") == "main")
        if "article_count_main" in l and l["article_count_main"] != got:
            WARN.append(("W04", iid, f"article_count_main={l['article_count_main']} but {got} articles exported"))
    rep = {"laws": len(laws), "articles": len(arts), "errors": len(ERR), "warnings": len(WARN),
           "error_list": [dict(code=c, ref=r, msg=m) for c, r, m in ERR], "warning_list": [dict(code=c, ref=r, msg=m) for c, r, m in WARN]}
    json.dump(rep, open(f"{D}/validation_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"laws={len(laws)} articles={len(arts)} ERRORS={len(ERR)} WARNINGS={len(WARN)}")
    for c, r, m in ERR[:40]:
        print(f"ERROR   {c} {r}: {m}")
    for c, r, m in WARN[:25]:
        print(f"warning {c} {r}: {m}")
    sys.exit(1 if ERR else 0)


if __name__ == "__main__":
    main()
