# Provenance

Traceable origin of every collection in `knowledge/`. No collection here was
generated, invented, or synthesized — everything traces back to a specific
source pass documented below.

## laws/ (21,093 articles, 139 files)

Source: 225 raw Egyptian legal code source files (`.doc`, some scanned PDFs)
under `اكواد القوانين/`, processed article-by-article into structured JSON
(`legal_article` shape). Filed by legal domain (criminal, civil, commercial,
labour, tax, family, constitutional, administrative, real estate, IP, etc.).
Some scanned PDFs had no extractable text and were excluded pending OCR —
tracked in `knowledge/references/legacy_indexes/laws_db/_pending_ocr_scanned_pdfs.json`.
No article text was rewritten or summarized; `content` is the literal
article text from the source file.

## judgments/ (44,190 records, 137 files)

Source: two pre-existing corpora, restructured (not re-authored) into the
unified `judgment_principle` shape:
- Criminal: 22,489 records, verified count-matched against the original
  `lexbridge_principles_enriched_v9.json`.
- Civil: 21,701 records, verified count-matched against the original
  `civil_all.json`. 31 pre-existing duplicate IDs originate from this file
  and were carried forward rather than silently dropped (see
  `KNOWLEDGE_BASE_REPORT.md` phase 2 for the original audit).

Filed by court branch (cassation/civil, cassation/criminal) then by legal
subject; criminal judgments are additionally bucketed by judicial-year
decade where the source volume required it.

## principles/doctrine/ (49 records, 1 file)

Source: Al-Sanhouri's *Al-Wasit fi Sharh Al-Qanun Al-Madani*, Volume 1,
converted into a compressed retrieval-oriented schema (`rule`,
`exam_triggers`, `common_confusions`, `choice_holder`, `burden_of_proof`)
in a separate June 2026 initiative.

## procedures/ (24 records, 15 files)

15 branch-level procedure summaries (civil, criminal, administrative,
family, execution, commercial/constitutional) plus 9 "deep" procedural
guides (filing, appeals/cassation, attachment, enforcement, family court,
etc.) built as part of the May–June 2026 V2 structured procedures
initiative — the same 12-analytical-layer procedures work referenced in
prior sprint history.

## deadlines/ (67 records, 10 files)

Procedural, appeal, limitation-period, and domain-specific (civil,
criminal, commercial, constitutional, administrative, personal-status)
deadlines, cross-referenced against `laws/` and `procedures/` during the
Knowledge Graph v1 merge via explicit book/article-number matching (not
semantic guessing).

## templates/ (7 records, 1 file)

Ready-to-use legal document templates library.

## Citation linking (Knowledge Graph v1 merge)

7,018 candidate citations were scanned across judgments, principles,
procedures, and deadlines. 6,158 were linked (1 at ≥0.9 confidence, 6,157
at 0.75–0.9) using explicit article-number + law-name/domain matching only.
860 could not be linked with sufficient confidence and were left
unlinked rather than guessed. Full methodology:
`knowledge/references/legacy_reports` (original Arabic report) and the
top-level `KNOWLEDGE_GRAPH_REPORT.md` produced alongside this repository.

## defenses/ and contracts/ (0 records — not yet created as folders)

No standalone `defense` or `contract` entity type exists in any source
corpus processed so far. `defense` records ARE derived at Knowledge Engine
ingestion time from `judgment_principle.source_fields.defense_args` where
present — that derivation is website-side logic, documented in
`schemas/document-types.registry.json`, and is not a stored collection
here. Real standalone data for either type will get its own folder + a
promoted registry entry when it exists — not before.
