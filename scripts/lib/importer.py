"""
LEXBRIDGE Knowledge Repository — importer.py (Sprint 2.6, Part 10)
-------------------------------------------------------------------------
Accepts a future dataset file in PDF, DOCX, TXT, HTML, JSON, CSV, or XML
and turns it into normalized records following the standard schema
({id, type, category, title, content, keywords, citations, related_ids,
metadata, source_fields}), written to raw/<collection>/ (original file,
untouched) and staged into knowledge/<collection>/ for `kb build` to
pick up.

Design: text-bearing formats (txt/html/docx/pdf) become ONE record per
file (a document), tagged for manual category assignment. Structured
formats (json/csv/xml) are expanded — one record per row/element — since
that matches how every existing collection in this repo was built
(see KNOWLEDGE_BASE_REPORT.md §6: "تفكيك" / explode nested arrays).

This module intentionally does NOT invent metadata it cannot extract —
missing fields are left null, exactly as the existing v10/graph-v1
reorganization pipeline behaved. See metadata_extract.py for the
best-effort extraction pass applied afterwards.
"""
import csv
import io
import json
import os
import re
import xml.etree.ElementTree as ET

from .common import now_iso, write_json
from .metadata_extract import extract_metadata
from .citations import generate_citations

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".html", ".htm", ".json", ".csv", ".xml"}


def _read_text_file(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_docx_text(path: str) -> str:
    try:
        import docx  # python-docx, optional dependency
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)
    except ImportError:
        return ""  # importer still stages the raw file; text extraction deferred


def _extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except ImportError:
        return ""


def _extract_html_text(path: str) -> str:
    raw = _read_text_file(path)
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _make_single_doc_record(collection: str, file_path: str, content: str, id_prefix: str, index: int) -> dict:
    title = os.path.splitext(os.path.basename(file_path))[0]
    rec = {
        "id": f"{id_prefix}-{index:06d}",
        "type": "imported_document",
        "category": collection,
        "title": title,
        "content": content,
        "keywords": [],
        "citations": [],
        "related_ids": [],
        "related_articles": [], "related_judgments": [], "related_defenses": [],
        "related_procedures": [], "related_contracts": [], "related_principles": [],
        "metadata": {},
        "source_fields": {"imported_from": os.path.basename(file_path), "imported_at": now_iso()},
    }
    rec["metadata"] = extract_metadata(rec)
    rec["citations"] = generate_citations(rec)
    return rec


def _expand_json(collection: str, file_path: str, id_prefix: str) -> list:
    data = json.loads(_read_text_file(file_path))
    rows = data if isinstance(data, list) else [data]
    out = []
    for i, row in enumerate(rows):
        rec = {
            "id": row.get("id") or f"{id_prefix}-{i:06d}",
            "type": row.get("type", "imported_record"),
            "category": row.get("category", collection),
            "title": row.get("title") or row.get("name") or f"{collection} #{i}",
            "content": row.get("content") or json.dumps(row, ensure_ascii=False),
            "keywords": row.get("keywords", []),
            "citations": row.get("citations", []),
            "related_ids": row.get("related_ids", []),
            "related_articles": [], "related_judgments": [], "related_defenses": [],
            "related_procedures": [], "related_contracts": [], "related_principles": [],
            "metadata": row.get("metadata", {}),
            "source_fields": row,
        }
        if not rec["metadata"]:
            rec["metadata"] = extract_metadata(rec)
        if not rec["citations"]:
            rec["citations"] = generate_citations(rec)
        out.append(rec)
    return out


def _expand_csv(collection: str, file_path: str, id_prefix: str) -> list:
    out = []
    with open(file_path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            content = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
            rec = {
                "id": row.get("id") or f"{id_prefix}-{i:06d}",
                "type": "imported_record",
                "category": collection,
                "title": row.get("title") or row.get("name") or f"{collection} #{i}",
                "content": content,
                "keywords": [],
                "citations": [],
                "related_ids": [],
                "related_articles": [], "related_judgments": [], "related_defenses": [],
                "related_procedures": [], "related_contracts": [], "related_principles": [],
                "metadata": {},
                "source_fields": row,
            }
            rec["metadata"] = extract_metadata(rec)
            rec["citations"] = generate_citations(rec)
            out.append(rec)
    return out


def _expand_xml(collection: str, file_path: str, id_prefix: str) -> list:
    tree = ET.parse(file_path)
    root_el = tree.getroot()
    out = []
    for i, el in enumerate(list(root_el)):
        fields = {child.tag: (child.text or "").strip() for child in el}
        content = " | ".join(f"{k}: {v}" for k, v in fields.items() if v)
        rec = {
            "id": fields.get("id") or f"{id_prefix}-{i:06d}",
            "type": "imported_record",
            "category": collection,
            "title": fields.get("title") or fields.get("name") or f"{collection} #{i}",
            "content": content,
            "keywords": [],
            "citations": [],
            "related_ids": [],
            "related_articles": [], "related_judgments": [], "related_defenses": [],
            "related_procedures": [], "related_contracts": [], "related_principles": [],
            "metadata": {},
            "source_fields": fields,
        }
        rec["metadata"] = extract_metadata(rec)
        rec["citations"] = generate_citations(rec)
        out.append(rec)
    return out


def import_file(root: str, source_path: str, collection: str) -> dict:
    """Imports one file into knowledge/<collection>/, staging the raw
    original under raw/<collection>/ untouched. Returns a summary."""
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")

    raw_dir = os.path.join(root, "raw", collection)
    os.makedirs(raw_dir, exist_ok=True)
    raw_dest = os.path.join(raw_dir, os.path.basename(source_path))
    with open(source_path, "rb") as fsrc, open(raw_dest, "wb") as fdst:
        fdst.write(fsrc.read())

    id_prefix = collection.replace("/", "-")

    if ext == ".json":
        records = _expand_json(collection, source_path, id_prefix)
    elif ext == ".csv":
        records = _expand_csv(collection, source_path, id_prefix)
    elif ext == ".xml":
        records = _expand_xml(collection, source_path, id_prefix)
    else:
        if ext == ".docx":
            content = _extract_docx_text(source_path)
        elif ext == ".pdf":
            content = _extract_pdf_text(source_path)
        elif ext in (".html", ".htm"):
            content = _extract_html_text(source_path)
        else:  # .txt, .doc (best-effort)
            content = _read_text_file(source_path) if ext == ".txt" else ""
        records = [_make_single_doc_record(collection, source_path, content, id_prefix, 0)]

    out_path = os.path.join(root, "knowledge", collection, os.path.splitext(os.path.basename(source_path))[0] + ".json")
    write_json(out_path, records)

    return {
        "source": source_path,
        "collection": collection,
        "raw_copy": os.path.relpath(raw_dest, root),
        "staged_file": os.path.relpath(out_path, root),
        "records_created": len(records),
        "note": "Run `kb build` (or `kb index`) next to validate, extract citations/metadata fully, "
                "rebuild the graph, and register this collection in schemas/document-types.registry.json "
                "if it is new.",
    }
