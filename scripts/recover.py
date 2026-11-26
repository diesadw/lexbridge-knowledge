#!/usr/bin/env python3
"""Trace any canonical id OR any legacy (old) id back to the verbatim raw record(s).

  python scripts/recover.py --out . <canonical-or-legacy-id>

Reads the immutable archives in raw_archive/ by default, verifies each record hash,
and prints every candidate (a legacy id that collided maps to several records)."""
import argparse, csv, glob, gzip, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import LexArchive, EgyptArchive, rec_sha256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lexbridge-zip", default=None)
    ap.add_argument("--egypt-zip", default=None)
    a = ap.parse_args(); O = a.out
    lbz = a.lexbridge_zip or glob.glob(f"{O}/raw_archive/lexbridge-knowledge-main*.zip")[0]
    egz = a.egypt_zip or glob.glob(f"{O}/raw_archive/egypt-law-*.zip")[0]
    lb, eg = LexArchive(lbz), EgyptArchive(egz)
    ids = {a.id}
    for m in ("judgment_id_map", "law_id_map", "other_collections_id_map"):
        with gzip.open(f"{O}/mappings/{m}.csv.gz", "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["legacy_id"] == a.id:
                    ids.add(r.get("new_id") or r.get("article_id"))
    if len(ids) > 1:
        print(f"legacy id {a.id} resolves to {len(ids) - 1} canonical id(s): {sorted(ids - {a.id})}")
    found = False
    for fp in sorted(glob.glob(f"{O}/canonical/**/*.jsonl.gz", recursive=True)):
        with gzip.open(fp, "rt", encoding="utf-8") as f:
            for line in f:
                if not any(i in line[:400] for i in ids):
                    continue
                r = json.loads(line)
                if r["id"] not in ids:
                    continue
                found = True
                print(f"\n=== {r['id']} ({r['record_type']}) in {os.path.relpath(fp, O)}")
                for s in r["provenance"]["sources"]:
                    ref = s["raw_ref"]
                    if ref["source"] == "lexbridge":
                        rec = lb.record(ref["path"], ref["index"])
                        ok = rec_sha256(rec) == ref["record_sha256"]
                        print(f"- raw [{s.get('role', '')}] {ref['path']} #{ref['index']} legacy_id={ref['legacy_id']} hash {'OK' if ok else 'MISMATCH'}")
                        print("  " + json.dumps(rec, ensure_ascii=False)[:300])
                    elif ref["source"] in ("law-intake", "judgments-docx"):
                        zname = {"law-intake": "law_intake_output", "judgments-docx": ".docx"}[ref["source"]]
                        arch = [x for x in glob.glob(f"{O}/raw_archive/*") if (zname in x)]
                        print(f"- raw [{s.get('role', '')}] source={ref['source']} archive={os.path.basename(arch[0]) if arch else '?'} "
                              f"sha256={ref['archive_sha256'][:12]} " + " ".join(f"{k}={v}" for k, v in ref.items() if k in ("path", "index", "paragraph_title", "paragraph_end", "source_file")))
                        if ref["source"] == "law-intake" and arch:
                            import zipfile
                            lines = [l for l in zipfile.ZipFile(arch[0]).read(ref["path"]).decode("utf-8").split("\n") if l.strip()]
                            print("  " + lines[ref["index"]][:300])
                    else:
                        b = eg.read_bytes(ref["path"])
                        ok = hashlib.sha256(b).hexdigest() == ref["file_sha256"]
                        print(f"- raw {ref['path']} @ egypt-law {ref['source_commit'][:10]} hash {'OK' if ok else 'MISMATCH'}")
                        print("  " + b.decode("utf-8")[:240].replace("\n", "\\n"))
    if not found:
        print("id not found in canonical output")


if __name__ == "__main__":
    main()
