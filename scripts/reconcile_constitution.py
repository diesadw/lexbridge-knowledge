#!/usr/bin/env python3
"""Reconcile Constitution counts: upstream files vs upstream metadata vs canonical output vs LexBridge file."""
import argparse, collections, gzip, hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import LexArchive, EgyptArchive, canon_article


def opener(p):
    return gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    ap.add_argument("--egypt-zip", default="/mnt/user-data/uploads/egypt-law-a9a9f589c7537c1ff1796795ac87efbbd042c95a.zip")
    ap.add_argument("--canonical", required=True, help="articles_egypt_law_constitution.jsonl[.gz]")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    eg, lb = EgyptArchive(a.egypt_zip), LexArchive(a.lexbridge_zip)
    R = {}
    for lang, folder in (("ar", "dustur"), ("en", "constitution")):
        files = [os.path.basename(p)[:-3] for p in eg.list(folder)]
        pre = [f for f in files if f == "preamble"]
        num = sorted(int(m.group(1)) for f in files if (m := re.fullmatch(r"art-(\d+)", f)))
        bis = sorted(f for f in files if re.fullmatch(r"art-\d+-bis", f))
        other = [f for f in files if f not in pre and not re.fullmatch(r"art-\d+(-bis)?", f)]
        R[lang] = {"folder": folder, "md_files_excluding_README": len(files), "preamble": len(pre),
                   "numbered": len(num), "numbered_unique": len(set(num)), "numbered_range": [min(num), max(num)],
                   "numbered_gaps": [i for i in range(min(num), max(num) + 1) if i not in set(num)],
                   "bis_files": bis, "unrecognised_files": other,
                   "arithmetic": f"{len(pre)} + {len(num)} + {len(bis)} = {len(pre) + len(num) + len(bis)}"}
        readme = eg.read_bytes(f"{folder}/README.md").decode("utf-8")
        R[lang]["readme_article_rows"] = len(re.findall(r"\[art-[\w-]+\.md\]", readme))
    meta = json.loads(eg.read_bytes("data/versions.json"))
    R["upstream_versions_json_units"] = {x["slug"]: [v["units"] for v in x["versions"]] for x in meta["acts"]}
    emb = {}
    for n in (150, 241, 244):
        t = eg.read_bytes(f"constitution/art-{n:03d}.md").decode("utf-8")
        emb[n] = bool(re.search(rf"Article\s+{n}\s*\(bis\)", t, re.I))
    R["english_bis_embedded_in_parent"] = emb
    h = collections.Counter(hashlib.sha1(eg.read_bytes(p).decode().split("\n", 1)[1].strip().encode()).hexdigest() for p in eg.list("dustur"))
    R["arabic_articles_with_identical_text_to_another"] = sum(c for c in h.values() if c > 1)
    recs = [json.loads(l) for l in opener(a.canonical)]
    ids = collections.Counter(r["id"] for r in recs)
    ar = [r for r in recs if r["language"] == "ar"]
    en = [r for r in recs if r["language"] == "en"]
    R["canonical"] = {"total": len(recs), "ar": len(ar), "en": len(en), "duplicate_ids": [i for i, c in ids.items() if c > 1],
                      "ar_by_kind": {"preamble": sum(r["article_number"]["canonical"] == "preamble" for r in ar),
                                     "numbered": sum(bool(re.fullmatch(r"\d+", r["article_number"]["canonical"])) for r in ar),
                                     "bis": sum(r["article_number"]["canonical"].endswith("-bis") for r in ar)},
                      "en_by_kind": {"preamble": sum(r["article_number"]["canonical"] == "preamble" for r in en),
                                     "numbered": sum(bool(re.fullmatch(r"\d+", r["article_number"]["canonical"])) for r in en)},
                      "link_status": dict(collections.Counter(r["translation"]["status"] for r in ar))}
    p = [x for x in lb.list("knowledge/laws/constitutional/") if len(lb.records(x)) == 212][0]
    recs_lb = lb.records(p)
    nums = [canon_article(r["article_number"]) for r in recs_lb]
    ints = [int(n) for n in nums if n.isdigit()]
    R["lexbridge_constitution_file"] = {"records": len(recs_lb), "unique_canonical_numbers": len(set(nums)),
                                        "non_plain_integers": [n for n in nums if not re.fullmatch(r"\d+", n)],
                                        "integer_range": [min(ints), max(ints)]}
    ok = (R["ar"]["numbered_gaps"] == [] and R["en"]["numbered_gaps"] == [] and R["ar"]["numbered"] == R["ar"]["numbered_unique"] == 254
          and len(R["ar"]["bis_files"]) == 3 and R["ar"]["preamble"] == 1 and R["canonical"]["ar"] == 258 and R["canonical"]["en"] == 255
          and not R["canonical"]["duplicate_ids"] and all(emb.values()) and R["upstream_versions_json_units"]["dustur"] == [258]
          and R["upstream_versions_json_units"]["constitution"] == [255])
    R["verdict"] = "RECONCILED: no article missing or double-counted" if ok else "MISMATCH - investigate"
    os.makedirs(a.out, exist_ok=True)
    json.dump(R, open(f"{a.out}/constitution_count_reconciliation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(R, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
