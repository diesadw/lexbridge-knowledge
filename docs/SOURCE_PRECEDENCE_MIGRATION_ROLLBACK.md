# Source mapping, precedence policy, migration and rollback — v3.0.0-rc1

## 1. Source mapping

| Source path (original) | Canonical output | Notes |
|---|---|---|
| LexBridge `knowledge/laws/**` (139 files, 21,093 records) | `canonical/legislation/instruments.jsonl.gz`, `articles_lexbridge.jsonl.gz` | files → instruments → editions → articles |
| LexBridge `knowledge/judgments/**` (44,190) | `canonical/judgments/judgment_principles.jsonl.gz` | civil + criminal cassation |
| LexBridge `principles/`, `procedures/`, `deadlines/`, `defenses/`, `templates/` | `canonical/<name>/<name>.jsonl.gz` | one canonical record per source record |
| egypt-law `dustur/*.md` (258) | `articles_egypt_law_constitution.jsonl.gz` (`language: ar`) | primary text |
| egypt-law `constitution/*.md` (255) | same file (`language: en`) | linked translation, `authoritative: false` |
| LexBridge `indexes/`, `metadata/`, `schemas/`, `migrations/`, `kb` CLI | **not transformed** | out of scope; untouched in the raw archive |

## 2. Source precedence and conflict policy

1. **egypt-law is a dedicated constitutional source**, not a general legislation source. It has **no precedence** over any LexBridge law. (It has no statutes and no overlap with LexBridge legislation.)
2. Constitutions are **never** matched, merged or overwritten by article number. egypt-law's 2014/2019 text and LexBridge's own constitution file are separate instruments. The LexBridge file stays `identity_status: unidentified`, `version_status: unestablished`.
3. Within LexBridge laws: identical files fold into one edition; **different editions are all kept**; no edition is preferred, none is declared in force. Humans decide per instrument (`multiple_editions_differ_human_decision_needed`).
4. Judgments: merge only under rule D1; everything else stays separate and is linked or flagged.
5. Any value not backed by evidence stays `null` / `unverified` / `not_assessed`. Source claims are stored as claims.
6. Editorial, AI-named, translated or summarised content never replaces source text and is labelled.

## 3. Migration plan (nothing is deployed by this release)

1. Review `reports/FINAL_DATA_REPORT.md`, `DECISION_EXAMPLES.md`, `human_review_items.jsonl.gz`.
2. Decide the human items (editions, identity, boundary confirmations). Put approvals in `config/*.json`; re-run `build_full.py` — output is deterministic, so only intended records change.
3. Re-run `validate_full.py` (all checks must pass) and `verify_release.py`.
4. Integration into LexBridge (separate, future, requires the website/RAKEEN code which this work has not seen): load the canonical files into a **staging** copy of the knowledge store; run existing search regression queries side-by-side; only then consider switching. Consumers must (a) use the mapping tables for any stored legacy ID, (b) treat a legacy ID as possibly one-to-many, (c) use `categories_seen` / `titles_seen` / `keywords_union` if they want the merged topic signals — the canonical record's own `category_original` / `title_original` alone do not show them.

## 4. Rollback and recovery

- **The original data is never modified.** Both original zips are copied unchanged, read-only, to `raw_archive/` with `SHA256SUMS`; the build only reads them.
- **Rollback = keep using the original database.** This release is a separate directory; production does not read it. Rolling back means not switching, or switching back to the original dataset (which is byte-identical to `raw_archive/`).
- **Recovery of any record:** `python scripts/recover.py --out . <canonical id or legacy id>` prints the verbatim raw record(s) with hash verification, including every candidate for a collided legacy ID.
- **Integrity:** `python scripts/verify_release.py --out . [--originals A.zip B.zip]` re-hashes the raw archive, your originals and every output file.
- **Reproduce from scratch:** `python scripts/build_full.py --out NEW && python scripts/validate_full.py --out NEW` (validation includes a byte-identical rebuild check).
