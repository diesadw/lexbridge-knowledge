# LexBridge knowledge — v3.1.0-rc1 (release candidate, NOT deployed)

v3.0.0-rc1 + the new Law Intake output (386 laws / 16,597 articles) + 75 full-text judgments from the Word file. The base release and all original sources are untouched; nothing here modifies Production, live search, RAKEEN or the website.

Start with `reports/V31_INTEGRATION_REPORT.md`, then `docs/V31_ADDENDUM.md` and `docs/RULES_AND_SCHEMA_FINAL.md`. Baseline v3.0.0 reports are in `reports/baseline_v3.0.0/`.

Precedence: new sources win (`precedence_rank` 1); legacy records are kept, flagged with `legacy_status`.
Recover any record: `python scripts/recover.py --out . <id>` (note: recover.py reads canonical + mapping files of v3.0 layout; for intake/judgment records open the jsonl.gz directly).
Integrity: `python scripts/verify_release.py --out .`
