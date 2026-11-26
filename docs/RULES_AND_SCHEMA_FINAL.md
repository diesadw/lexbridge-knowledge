# Finalized rules and schema — v3.0.0-rc1

Supersedes the pilot rules (`lexbridge-pilot/docs/PILOT_RULES_AND_SCHEMA.md`) wherever they differ. All rules below are enforced by `scripts/build_full.py` and re-checked by `scripts/validate_full.py`.

## Decisions (approved)

| # | Rule | Implementation |
|---|---|---|
| D1 | A judgment merge needs **court + case number + judicial year + volume + page + paragraph (all present and equal) + identical text**. Citation strings are never a merge key. A record with a missing paragraph is **never merged**; it becomes a *potential duplicate candidate*. | Merge key `(branch, court, case, year, volume, page, paragraph, sha256(collapsed text))`. Candidates: same text + same case/year/volume/page but not eligible → separate records, `potential_duplicate_of`, review item. Checks G1–G5. |
| D2 | Preserve every distinct law edition and variant. Review at instrument/edition level. Never pick a preferred or "in force" edition. | Files are clustered into an *instrument*; identical files = one *edition*; every edition keeps all its own article records. `preferred_edition: null`, `legal_status: not_assessed`. Cross-edition links: `align_group`, `search_equivalent_ids`, `differs_from_ids`. One review item per instrument with a pairwise edition comparison. Checks I1–I4. |
| D3 | Numbering restarts are flagged, not split. Splits only after confirmation. Issuing-law articles must be clearly distinguished. | Restarts (`n < previous` and `n ≤ 2`) are listed in `reports/numbering_boundaries.json` with evidence. Records carry `part.numbering_segment`, `part.status` (`none` / `unconfirmed` / `confirmed`) and `part.role_hint` (`issuing_law_provisions_candidate` / `main_instrument_candidate` / `unclassified_segment`). Confirmation file: `config/split_confirmations.json` (empty); ready proposals: `config/split_confirmations.PROPOSED.json`. Confirmation applies the role and status; it never deletes or reorders. Checks J1–J4. |
| D4 | Preserve claimed law number/year; fill canonical fields only on sufficiently reliable evidence; else null + review. | `identity.claimed` = every (number, year) claim with record counts. `canonical_law_number/year` only when exactly one claim exists, the law name **opens as a law title** (`قانون…`, not a preamble fragment) and states the same number+year, and the filename agrees; or when a human lists it in `config/law_identity_confirmations.json`. `external_verification` is always `null` unless a human provides evidence. Checks K1–K3. |

## ID rules

| Record | ID |
|---|---|
| Law instrument | `inst:lb:` + sha1(anchor file path)[:10] (cluster status `candidate_unverified`) |
| Edition | `ed:{instrument}:{sha256 of ordered (article_number, text) pairs}[:10]` |
| Law article | `art:{edition}:{canonical number}[~k]` (`k` = occurrence of a repeated number in that file) |
| Alignment group | `artgrp:{instrument}:{canonical number}[~k]` (links the same article across editions) |
| Constitution (egypt-law) | `art:eg:const2014:{ar\|en}:{n}` |
| Judgment (eligible) | `jdg:{civil\|crim}:{case}-{year}:v{volume}:p{page}:n{paragraph}:{hash8(text)}` |
| Judgment (not eligible) | `jdg:{branch}:legacy:{legacy id}:{hash8}` (plus a short suffix only if still not unique) |
| Templates, defenses, procedures, deadlines, principles | legacy ID kept (unique) |

Legacy → new mappings: `mappings/judgment_id_map.csv.gz`, `law_id_map.csv.gz`, `other_collections_id_map.csv.gz`. One legacy ID may map to several new IDs (the 31 collided judgment IDs): consumers must treat the mapping as one-to-many.

## Record envelope

`id`, `record_type`, `schema_version`, `source_family`, type-specific fields, and `provenance{sources[] (raw_ref: archive sha256, path, index, legacy_id, record_sha256 — egypt-law: commit + file sha256), import_date, pipeline_version, release, transformations[], verification_status, conflict_flags[], review_flags[]}`.

Text fields: `text_original` (verbatim), `text_clean` (conservative, ops logged in transformations), `text_search` (`search_v1`, search only).

Judgment retrieval helpers: `categories_seen`, `titles_seen`, `keywords_union` (union over merged copies), `same_text_group`, `potential_duplicate_of`, `references{resolved, ambiguous, unresolved, law_refs_resolved, law_refs_unresolved, legacy}`.

## Labels

`text_status`: `source_verbatim`, `source_verbatim_extracted_from_doc`, `source_verbatim_upstream_normalized` (egypt-law), `translation_not_authoritative`, `secondary_source_paraphrase`, `recovered_from_field`, `title_only`, `lexbridge_internal`. `field_status`: `ai_generated_per_field_name` (any `ai_*` key), `editorial_unverified_provenance`. `content_status`: `has_content`, `title_only`, `recovered_from_field`, `empty_in_source`.

## Transformation catalog

T00 split upstream markdown heading/body · T01 stable ID · T02 `text_clean` · T03 `text_search` · T04 merge (identical file copies / judgment duplicates / cluster files) — sources always listed · T05 editions preserved without preference · T06 numbering restart flagged (no split) · T07 template content recovered from `source_fields.template_body` (original field kept) · T08 title-only marked · T09 secondary paraphrase labelled · T10 derived/AI-named fields labelled · T11 references rewritten via mapping (ambiguous kept with candidates) · T12 English→Arabic link · T13 guide formal/colloquial line partition · T14 deadline field regrouping.
