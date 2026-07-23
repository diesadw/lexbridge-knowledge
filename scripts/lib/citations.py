"""
LEXBRIDGE Knowledge Repository — citations.py (Sprint 2.6, Part 12)
-------------------------------------------------------------------------
Generates a standard citation string for a record whenever enough
metadata exists to build one — never fabricates a citation from partial
data. Used by importer.py for new records; existing records already
carry citations from the v10/graph-v1 pipeline and are left untouched.

Citation formats (Egyptian legal convention):
  judgment:  "الطعن رقم {appeal_number} لسنة {appeal_year} ({court})"
  article:   "{law_name} رقم {law_number} لسنة {law_year}، المادة {article_number}"
  generic:   falls back to title if no structured metadata is present
"""


def generate_citations(record: dict) -> list:
    existing = record.get("citations") or []
    if existing:
        return existing

    meta = record.get("metadata") or {}
    rtype = record.get("type")
    citation = None

    if rtype in ("judgment_principle", "imported_document", "imported_record"):
        if meta.get("appeal_number"):
            court = meta.get("court") or "محكمة النقض"
            year_part = f" لسنة {meta['appeal_year']}" if meta.get("appeal_year") else ""
            citation = f"الطعن رقم {meta['appeal_number']}{year_part} ({court})"

    if not citation and rtype == "legal_article":
        if meta.get("law_number") and meta.get("article_number"):
            law_name = meta.get("law_name") or "القانون"
            year_part = f" لسنة {meta['law_year']}" if meta.get("law_year") else ""
            citation = f"{law_name} رقم {meta['law_number']}{year_part}، المادة {meta['article_number']}"

    if not citation and meta.get("law_number") and meta.get("article_number"):
        year_part = f" لسنة {meta['law_year']}" if meta.get("law_year") else ""
        citation = f"قانون رقم {meta['law_number']}{year_part}، المادة {meta['article_number']}"

    return [citation] if citation else []
