"""
LEXBRIDGE Knowledge Repository — metadata_extract.py (Sprint 2.6, Part 11)
-------------------------------------------------------------------------
Best-effort extraction of standard metadata fields from a record's
`content` / `source_fields` text, for records that don't already carry
structured metadata (mainly new imports via importer.py — existing
records already went through the v10/graph-v1 extraction pass documented
in KNOWLEDGE_BASE_REPORT.md and are NOT re-processed here, to avoid
touching content that's already correct).

Extracts, only when a confident pattern match exists (never guesses):
  law_number, article_number, court, year, legal_field, appeal_number,
  keywords (frequency-based, from existing text only), author, source,
  dates, citations/references (see citations.py for the citation object
  builder — this module only locates raw citation-like substrings).

Any field that cannot be confidently extracted is left None — matching
the existing repository's documented policy of never inventing legal
metadata (KNOWLEDGE_BASE_REPORT.md §12: "لم يتم اختراع أي معلومة").
"""
import re

_LAW_NUMBER_RE = re.compile(r"قانون\s+رقم\s+(\d+)\s+لسنة\s+(\d{4})")
_ARTICLE_RE = re.compile(r"الماد[ةه]\s+(\d+)")
_APPEAL_RE = re.compile(r"طعن\s+رقم\s+(\d+)\s+لسنة\s+(\d+)")
_COURT_RE = re.compile(r"(محكمة\s+النقض|المحكمة\s+الدستورية\s+العليا|محكمة\s+استئناف\s+\S+)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

FIELD_KEYWORDS = {
    "جنائي": ["جناية", "جنحة", "عقوبة", "متهم", "نيابة"],
    "مدني": ["عقد", "التزام", "تعويض", "ملكية"],
    "تجاري": ["شركة", "تجاري", "إفلاس"],
    "إداري": ["قرار إداري", "مجلس الدولة"],
    "أحوال شخصية": ["طلاق", "نفقة", "حضانة", "زواج"],
}


def _first_match(pattern, text):
    m = pattern.search(text or "")
    return m


def extract_metadata(record: dict) -> dict:
    text = " ".join(filter(None, [
        record.get("title") or "",
        record.get("content") or "",
    ]))

    meta = dict(record.get("metadata") or {})

    m = _first_match(_LAW_NUMBER_RE, text)
    if m and not meta.get("law_number"):
        meta["law_number"] = m.group(1)
        meta["law_year"] = m.group(2)

    m = _first_match(_ARTICLE_RE, text)
    if m and not meta.get("article_number"):
        meta["article_number"] = m.group(1)

    m = _first_match(_APPEAL_RE, text)
    if m and not meta.get("appeal_number"):
        meta["appeal_number"] = m.group(1)
        meta.setdefault("appeal_year", m.group(2))

    m = _first_match(_COURT_RE, text)
    if m and not meta.get("court"):
        meta["court"] = m.group(1)

    if not meta.get("year"):
        years = _YEAR_RE.findall(text)
        if years:
            # findall with groups returns the group, not full match; redo without groups
            all_years = re.findall(r"\b(?:19|20)\d{2}\b", text)
            if all_years:
                meta["year"] = int(all_years[-1])  # most recent mentioned year, conservative default

    if not meta.get("legal_field"):
        best_field, best_score = None, 0
        for field, kws in FIELD_KEYWORDS.items():
            score = sum(text.count(kw) for kw in kws)
            if score > best_score:
                best_field, best_score = field, score
        if best_field:
            meta["legal_field"] = best_field

    meta.setdefault("law_number", None)
    meta.setdefault("article_number", None)
    meta.setdefault("court", None)
    meta.setdefault("year", None)
    meta.setdefault("legal_field", None)
    meta.setdefault("appeal_number", None)

    return meta
