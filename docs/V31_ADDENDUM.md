# v3.1.0-rc1 addendum (on top of docs/RULES_AND_SCHEMA_FINAL.md)

**User precedence rule:** the new sources (Law Intake output, full-text judgments docx) win over existing records wherever they conflict. Implemented without deleting anything: new records `precedence_rank: 1`; legacy records get `legacy_status` (`superseded_by_intake` → rank 3, `partially_covered_by_intake` / `legacy_not_replaced` → rank 2). Retrieval should prefer lower rank and may hide rank 3 by default.

**New record fields/IDs**
- Intake law: `inst:in:law-N-Y`; article `art:in:law-N-Y:{m|i}:{number}[-bis[-x]]` (`m` main, `i` issuing). Number/year come from the heading evidence in the source file (`identity.status: source_heading_evidence`), never externally verified. `citation_label` is copied from the intake.
- Full-text judgment: `jdgf:{civil|crim}:{case}-{year}:{yyyymmdd}:{hash8(text)}`; fields `citation_label`, `court_label_original`, `session_date` (+ original string), `title_original` (verbatim), `subject`, `text_original` (verbatim, source line and the website heading removed), `variant_group`.

**Identity gate for legacy ↔ intake matching:** a legacy instrument with a known number/year is linked only to the intake law with the same number/year (text similarity ≥ 0.6). A legacy instrument with unknown identity may be linked by text alignment only at mean similarity ≥ 0.8 and is marked `text_alignment_identity_unconfirmed`. Similar text with a different number/year is recorded in `intake_matches_rejected`, never linked (amending laws quote other laws).

**Reference remap:** `references.law_refs_remapped_to_intake` (new ids) beside the untouched `law_refs_resolved` (legacy ids) and `law_refs_not_remapped`. Article-level remap requires similarity ≥ 0.5 (`mappings/law_article_remap_legacy_to_intake.csv.gz`).

**Transformations added:** T20 split title fields · T21 remove the source-link line (original kept in `raw_archive`) · T22 remap law references to intake.

**Rebuild:** `python scripts/integrate_intake.py --base <v3.0.0-rc1 dir> --intake-zip <zip> --judgments-docx <docx> --out <dir>`; `python scripts/validate_v31.py --out <dir> --base <v3.0.0-rc1 dir> --intake-zip <zip> --judgments-docx <docx>`.
