# Changelog

## v1.0.0 — 2026-07-17 (Sprint 2.5 — repository split)

- Extracted the LEXBRIDGE Knowledge Base out of ad-hoc delivery zips
  (`LEXBRIDGE_Knowledge_Base_v10.zip`, `LEXBRIDGE_Knowledge_Graph_v1.zip`)
  into this dedicated, independently versioned repository.
- No records moved, renamed, deleted, or reshaped — this is the exact
  `kb_merged/knowledge/` tree from Knowledge Graph v1, unchanged.
- Added `schemas/document-types.registry.json`: the registry that makes
  future dataset additions a config change instead of a code change.
- Added `scripts/build_index.py`: registry-driven manifest builder,
  validated against the registry with zero drift, zero unregistered
  folders at time of writing.
- Added `metadata/PROVENANCE.md` documenting the traceable origin of
  every collection.
- Carried forward from Knowledge Graph v1 (2026-07-02): merge of the
  v10 Knowledge Base (44,337 records: judgments, principles, procedures,
  deadlines, templates) with the separately-processed laws database
  (21,093 articles / 139 laws), plus citation-linking pass (6,158 of
  7,018 candidate citations linked).

Total: 65,430 records (65,395 unique IDs) across 6 active collections.
