#!/usr/bin/env python3
"""Fast integrity check of a release directory (no rebuild).

  python scripts/verify_release.py --out .                    # raw_archive + output manifest
  python scripts/verify_release.py --out . --originals A.zip B.zip   # also compare with your original uploads
"""
import argparse, hashlib, json, os, sys


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--originals", nargs="*", default=[])
    a = ap.parse_args(); O = a.out
    bad = 0
    sums = {}
    for line in open(f"{O}/raw_archive/SHA256SUMS", encoding="utf-8"):
        if line.strip():
            h, n = line.strip().split("  ", 1); sums[n] = h
    for n, h in sums.items():
        ok = sha(f"{O}/raw_archive/{n}") == h
        print(("OK   " if ok else "FAIL ") + f"raw_archive/{n}"); bad += not ok
    for p in a.originals:
        ok = sha(p) in sums.values()
        print(("OK   " if ok else "FAIL ") + f"original {os.path.basename(p)} matches an archived copy"); bad += not ok
    man = json.load(open(f"{O}/OUTPUT_MANIFEST.json", encoding="utf-8"))
    miss = [k for k, v in man.items() if not os.path.exists(f"{O}/{k}") or sha(f"{O}/{k}") != v]
    print(("OK   " if not miss else "FAIL ") + f"output manifest ({len(man)} files)" + (f" changed/missing: {miss[:5]}" if miss else ""))
    bad += bool(miss)
    print("RELEASE INTACT" if not bad else "RELEASE MODIFIED OR INCOMPLETE")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
