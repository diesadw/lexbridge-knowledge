"""LexBridge pilot - shared library.

Everything here READS the original archives; nothing writes to them.
Three concerns: (1) raw archive access + record hashing, (2) text
normalization into DERIVED fields, (3) deterministic ID rules.
"""
import hashlib
import json
import re
import zipfile

PIPELINE_VERSION = "pilot-0.1"
LB_PREFIX = "lexbridge-knowledge-main/"


# --------------------------------------------------------------- raw access
def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rec_sha256(rec):
    """Hash of a raw JSON record, independent of file formatting."""
    s = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fix_name(n):
    """The LexBridge zip stores Arabic names as UTF-8 bytes mis-decoded as
    cp437. Reverse that losslessly; leave ASCII/unfixable names unchanged."""
    try:
        return n.encode("cp437").decode("utf-8")
    except Exception:
        return n


class LexArchive:
    """Read-only view of the LexBridge zip, with repaired Arabic paths."""

    def __init__(self, path):
        self.path = path
        self.sha256 = file_sha256(path)
        self.z = zipfile.ZipFile(path)
        self.map = {}
        for i in self.z.infolist():
            if i.is_dir():
                continue
            rel = "/".join(fix_name(p) for p in i.filename.split("/"))
            if rel.startswith(LB_PREFIX):
                rel = rel[len(LB_PREFIX):]
            self.map[rel] = i
        self._cache = {}

    def list(self, prefix):
        return sorted(p for p in self.map if p.startswith(prefix) and p.endswith(".json"))

    def records(self, rel):
        if rel not in self._cache:
            data = json.loads(self.z.read(self.map[rel]).decode("utf-8"))
            self._cache[rel] = data if isinstance(data, list) else [data]
        return self._cache[rel]

    def record(self, rel, index):
        return self.records(rel)[index]

    def ref(self, rel, index):
        rec = self.record(rel, index)
        return {
            "source": "lexbridge",
            "archive_sha256": self.sha256,
            "path": rel,
            "index": index,
            "legacy_id": rec.get("id"),
            "record_sha256": rec_sha256(rec),
        }


class EgyptArchive:
    """Read-only view of the egypt-law zip (markdown files)."""

    def __init__(self, path):
        self.path = path
        self.sha256 = file_sha256(path)
        self.z = zipfile.ZipFile(path)
        names = [n for n in self.z.namelist() if not n.endswith("/")]
        self.root = names[0].split("/")[0] + "/"
        m = re.search(r"egypt-law-([0-9a-f]{40})", self.root)
        self.commit = m.group(1) if m else None
        self.files = {n[len(self.root):]: n for n in names}

    def list(self, folder):
        return sorted(p for p in self.files if p.startswith(folder + "/") and p.endswith(".md")
                      and not p.endswith("README.md"))

    def read_bytes(self, rel):
        return self.z.read(self.files[rel])

    def ref(self, rel):
        b = self.read_bytes(rel)
        return {
            "source": "egypt-law",
            "archive_sha256": self.sha256,
            "source_commit": self.commit,
            "path": rel,
            "file_sha256": hashlib.sha256(b).hexdigest(),
        }


# ------------------------------------------------------------ normalization
BIDI = "[\u200e\u200f\u202a-\u202e\u2066-\u2069]"
DIACRITICS = re.compile("[\u064b-\u065f\u0670]")
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
BREADCRUMB = re.compile(r"\n([^\n/]{2,80} /[^\n/]+/[^\n]+)$")
FOOTNOTE = re.compile(r"\(\[\d+\]\)")


def make_clean(text):
    """text_clean: conservative, keeps diacritics and wording.
    Returns (clean_text, ops, extras). Every change is logged in ops."""
    ops = []

    def sub(name, pattern, repl, t):
        n = len(re.findall(pattern, t))
        if n:
            t = re.sub(pattern, repl, t)
            ops.append({"op": name, "count": n})
        return t

    t = text
    t = sub("nbsp_to_space", "\u00a0", " ", t)
    t = sub("strip_bidi_controls", BIDI, "", t)
    t = sub("strip_tatweel", "\u0640", "", t)
    t = sub("remove_empty_markdown_bold", r"\*\*\s*\*\*", "", t)
    t = sub("unwrap_markdown_bold", r"\*\*([^*\n]+?)\*\*", r"\1", t)
    t = sub("collapse_spaces", r"[ \t]{2,}", " ", t)
    t = sub("strip_line_edge_spaces", r"[ \t]+(?=\n)|(?<=\n)[ \t]+", "", t)
    t = sub("collapse_blank_lines", r"\n{3,}", "\n\n", t)
    if t != t.strip():
        t = t.strip()
        ops.append({"op": "strip_edges", "count": 1})
    extras = {}
    m = BREADCRUMB.search(t)
    if m:
        extras["breadcrumb_candidate"] = m.group(1)
        t = t[: m.start()]
        ops.append({"op": "extract_trailing_breadcrumb", "count": 1, "uncertain": True})
    flags = []
    if FOOTNOTE.search(t):
        flags.append("footnote_marker_left_in_text")
    return t, ops, extras, flags


def make_search(clean_text):
    """text_search: aggressive normalization for matching only. Never shown
    as legal text. Pipeline id: search_v1."""
    t = DIACRITICS.sub("", clean_text)
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = t.translate(DIGITS).lower()
    t = re.sub(r"[^0-9a-z\u0621-\u064a]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def text_block(original):
    """The standard triple: verbatim original + two derived fields."""
    clean, ops, extras, flags = make_clean(original)
    return {
        "text_original": original,
        "text_clean": clean,
        "text_search": make_search(clean),
        "clean_ops": ops,
        "extras": extras,
        "flags": flags,
    }


# ---------------------------------------------------------------- ID rules
def canon_article(raw):
    """'0005' -> '5'; '5 مكررا' -> '5-bis'; '5 مكررا 1' -> '5-bis-1'."""
    s = str(raw).translate(DIGITS).strip()
    m = re.match(r"^0*(\d+)\s*(?:(مكرر[اًٌٍ]*)\s*(?:\(?\s*(\d+)\s*\)?)?)?\s*$", s)
    if not m:
        return "x" + hashlib.sha1(s.encode()).hexdigest()[:6]
    out = m.group(1)
    if m.group(2):
        out += "-bis"
        if m.group(3):
            out += "-" + m.group(3)
    return out


def lead_int(raw):
    m = re.match(r"\s*0*(\d+)", str(raw).translate(DIGITS))
    return int(m.group(1)) if m else None


def h8(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:8]


def _z(v):
    v = "" if v is None else str(v).strip()
    return v.lstrip("0") or ("0" if v else "")


def judgment_branch(path):
    return "crim" if "/criminal" in path else "civil"


def judgment_identity(rec, path):
    """(case, year, volume, page, paragraph) as recorded by the source."""
    m = rec.get("metadata", {})
    if judgment_branch(path) == "crim":
        parts = (m.get("cassation_number"), m.get("judicial_year"), m.get("office_vol"),
                 m.get("page"), m.get("paragraph_number"))
    else:
        parts = (m.get("case_number"), m.get("judicial_year"), m.get("office_volume"),
                 m.get("page"), m.get("paragraph_number"))
    return tuple(_z(p) for p in parts)


def judgment_new_id(rec, path):
    """Stable ID = branch + identity + hash of the verbatim principle text.
    Two records get the same ID only if identity AND text are identical.
    Incomplete identity -> never merges: legacy id is part of the ID."""
    b = judgment_branch(path)
    ident = judgment_identity(rec, path)
    th = h8(rec["content"])
    if all(ident):
        return f"jdg:{b}:{ident[0]}-{ident[1]}:v{ident[2]}:p{ident[3]}:n{ident[4]}:{th}", True
    return f"jdg:{b}:legacy:{rec['id']}:{th}", False
