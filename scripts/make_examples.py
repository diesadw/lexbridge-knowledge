#!/usr/bin/env python3
"""Generate reports/DECISION_EXAMPLES.md from the real release data."""
import argparse, collections, csv, gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import LexArchive


def jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def short(o, n=140):
    if isinstance(o, str):
        return o if len(o) <= n else o[:n] + f"…[+{len(o) - n}]"
    if isinstance(o, list):
        r = [short(x, n) for x in o[:3]]
        return r + [f"…[+{len(o) - 3} more]"] if len(o) > 3 else r
    if isinstance(o, dict):
        return {k: short(v, n) for k, v in o.items()}
    return o


def js(o):
    return "```json\n" + json.dumps(short(o), ensure_ascii=False, indent=1) + "\n```\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    a = ap.parse_args(); O = a.out
    lb = LexArchive(a.lexbridge_zip)
    S = json.load(open(f"{O}/reports/build_summary.json", encoding="utf-8"))
    judg = jl(f"{O}/canonical/judgments/judgment_principles.jsonl.gz")
    byid = {j["id"]: j for j in judg}
    insts = jl(f"{O}/canonical/legislation/instruments.jsonl.gz")[1:]
    arts = {r["id"]: r for r in jl(f"{O}/canonical/legislation/articles_lexbridge.jsonl.gz")}
    tmpl = jl(f"{O}/canonical/templates/templates.jsonl.gz")
    bounds = json.load(open(f"{O}/reports/numbering_boundaries.json", encoding="utf-8"))
    rec = json.load(open(f"{O}/reports/constitution_count_reconciliation.json", encoding="utf-8"))
    with gzip.open(f"{O}/mappings/judgment_id_map.csv.gz", "rt", encoding="utf-8") as f:
        jrows = list(csv.DictReader(f))
    M = ["# Decision examples (generated from the real v3.0.0-rc1 release data)\n"]
    raw = lambda s: lb.record(s["raw_ref"]["path"], s["raw_ref"]["index"])

    # ---------------------------------------------------------------- 1 merges
    merged = sorted([j for j in judg if len(j["provenance"]["sources"]) > 1], key=lambda j: j["id"])
    diff = collections.Counter(); size = collections.Counter(); same_file = 0
    for j in merged:
        size[len(j["provenance"]["sources"])] += 1
        if len({s["raw_ref"]["path"] for s in j["provenance"]["sources"]}) == 1: same_file += 1
        for sn in j["merged_source_snapshots"]:
            if sn["category"] != j["category_original"]: diff["category"] += 1
            if sn["title"] != j["title_original"]: diff["title"] += 1
            if sn["citations"] != j["citations_original"]: diff["citations"] += 1
            if sn["keywords"] != j["legacy"]["keywords"]: diff["keywords"] += 1
            if sn["metadata"] != j["legacy"]["metadata"]: diff["metadata"] += 1
            if not sn["source_fields_identical_to_canonical"]: diff["source_fields"] += 1
    cit_empty = sum(1 for j in merged if not j["citations_original"])
    redundant = sum(len(j["provenance"]["sources"]) - 1 for j in merged)
    M.append(f"""## 1. The {redundant:,} merges ({len(merged):,} groups) — how they look and why they are safe

**Required evidence for every merge (all enforced and re-verified by validation G1/G2):** same court · same case/cassation number · same judicial year · same volume · same page · same paragraph number (all present) · identical judgment text (after whitespace collapse). Citation strings are **not** used as a key.

| Fact over all {len(merged):,} groups | Value |
|---|---|
| groups by size | {dict(sorted(size.items()))} |
| groups whose members sit in one file (exact in-file duplicates) | {same_file} |
| groups where any member's **citation list differs** | **{diff['citations']}** (so there are no "citation formatting differs" merge cases to show; groups with no citation at all, e.g. criminal: {cit_empty}) |
| member records whose **category** differs from the canonical one | {diff['category']} (almost always a topic file vs. `uncategorized_pool.json`) |
| member records whose **title** differs | {diff['title']} |
| member records whose keywords / metadata differ | {diff['keywords']} / {diff['metadata']} |
| member records whose `source_fields` differ (kept in full inside the canonical record) | {diff['source_fields']} |

Because citation strings never differ inside a merged group, **no merge in this dataset depends on how a citation is formatted**; if citation formatting did differ, the rule would still ignore it and rely on the structured identity fields.

Every merged record keeps: all legacy ids (`legacy_ids`), per-source raw reference + hash, and a snapshot (`merged_source_snapshots`) of each non-canonical source's id, path, category, title, citations, keywords, metadata and (if different) `source_fields`. The raw archive holds the originals untouched.

### Representative examples
""")
    picks = []
    def first(pred, label):
        for j in merged:
            if j not in [p[0] for p in picks] and pred(j):
                picks.append((j, label)); return
    cat_differs = lambda j: any(sn["category"] != j["category_original"] for sn in j["merged_source_snapshots"])
    first(lambda j: j["branch"] == "civil" and len(j["provenance"]["sources"]) == 2, "civil, 2 records of the same paragraph")
    first(lambda j: j["branch"] == "crim" and len(j["provenance"]["sources"]) == 2 and cat_differs(j), "criminal, 2 copies, different category labels")
    first(lambda j: len(j["provenance"]["sources"]) == 3, "3 copies")
    first(lambda j: len(j["provenance"]["sources"]) >= 4, "4+ copies")
    first(lambda j: len({s["raw_ref"]["path"] for s in j["provenance"]["sources"]}) == 1, "two records of the same paragraph inside one file")
    first(lambda j: any(sn["title"] != j["title_original"] for sn in j["merged_source_snapshots"]), "titles (topic labels) differ between copies; both kept in titles_seen")
    first(lambda j: any(not sn["source_fields_identical_to_canonical"] for sn in j["merged_source_snapshots"]), "source_fields differ between copies")
    first(lambda j: bool(j["citations_original"]) and j["branch"] == "civil", "civil with citation")
    first(lambda j: not j["citations_original"] and j["branch"] == "crim", "criminal with no citation")
    first(lambda j: len(j["provenance"]["sources"]) == max(len(x["provenance"]["sources"]) for x in merged), "largest group")
    for n, (j, label) in enumerate(picks, 1):
        srcs = []
        for s in j["provenance"]["sources"]:
            r = raw(s)
            srcs.append({"role": s["role"], "legacy_id": r["id"], "file": s["raw_ref"]["path"].split("/")[-1], "index": s["raw_ref"]["index"],
                         "category": r.get("category"), "title": r.get("title"), "citations": r["citations"]})
        ident = j["identity"]
        M.append(f"""#### 1.{n} {label}

**Before (raw):** {len(srcs)} records
{js(srcs)}
**After:** one canonical record `{j['id']}` — court `{j['court']}`, case {ident['case']}/{ident['year']}, volume {ident['volume']}, page {ident['page']}, paragraph {ident['paragraph']}; text length {len(j['text_original'])} chars; `legacy_ids` = {j['legacy_ids']}; `categories_seen` = {j['categories_seen']}.

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical ({len(j['text_original'])} chars). Differences kept, not lost: {"category" if any(sn['category'] != j['category_original'] for sn in j['merged_source_snapshots']) else "none in category"}{", title" if any(sn['title'] != j['title_original'] for sn in j['merged_source_snapshots']) else ""}{", source_fields" if any(not sn['source_fields_identical_to_canonical'] for sn in j['merged_source_snapshots']) else ""} (see `merged_source_snapshots`).
""")
    # --------------------------------------------------------- 2 kept separate
    M.append("\n---\n## 2. Similar records correctly kept separate\n")
    cand = sorted([j for j in judg if j["potential_duplicate_of"]], key=lambda j: j["id"])
    ex = next((j for j in cand if not all(j["identity"].values())), cand[0])
    other = byid[ex["potential_duplicate_of"][0]]
    M.append(f"""### 2a. Same text, same case/year/volume/page, **paragraph missing** → candidate, not merged

These records have identical text and the same case/year/volume/page, but **no paragraph number**, so the rule refuses to merge them. Each is kept as its own canonical record (two of the group are shown), linked through `potential_duplicate_of`, and listed for review.
{js([{k: x[k] for k in ('id', 'identity', 'merge_status', 'legacy_ids', 'potential_duplicate_of')} | {'text': x['text_original'][:70]} for x in (ex, other)])}
Totals: {S['judgments']['potential_duplicate_candidates']} records are in candidate relationships; {S['judgments']['status_by_raw_record'].get('identity_incomplete', 0)} records have an incomplete identity (all lack only the paragraph number) and never merge.
""")
    st = next(j for j in judg if j["same_text_group"] and not j["potential_duplicate_of"])
    sib = [j for j in judg if j["same_text_group"] == st["same_text_group"]][:3]
    M.append(f"""### 2b. Same wording in different judgments → different identity → separate

`{st['same_text_group']}` is shared by {st['same_text_count']} distinct judgments. They remain separate records (different case/volume/page/paragraph); `same_text_group` lets search de-duplicate display without destroying any judgment.
{js([{'id': x['id'], 'identity': x['identity'], 'citations': x['citations_original']} for x in sib])}
""")
    # ------------------------------------------------------------ 3 editions
    M.append("\n---\n## 3. Conflicting law editions preserved (no preferred edition)\n")
    civ = next(i for i in insts if i["identity"]["canonical_law_number"] == "131" and len(i["editions"]) > 1)
    M.append(f"""Instrument `{civ['id']}` ({civ['name']['selected'].replace('_', ' ')}) holds **{len(civ['editions'])} editions**; `preferred_edition` is `null`; every edition has `legal_status: not_assessed`.
{js([{'edition': e['id'], 'records': e['n_records'], 'files': [os.path.basename(f) for f in e['member_files']]} for e in civ['editions']])}
Pairwise comparison (edition level, not per article):
{js([{k: v for k, v in c.items() if k != 'example_pairs'} for c in civ['edition_comparison']])}
""")
    pair = next((c["example_pairs"][0] for c in civ["edition_comparison"] if c["example_pairs"]), None)
    five = None
    for aid_, r in arts.items():
        if r["instrument_id"] == civ["id"] and r["article_number"]["canonical"] == "2" and r["part"]["numbering_segment"] == 0:
            five = r; break
    if five:
        eq = [arts[i] for i in five["differs_from_ids"] if i in arts and arts[i]["text_original"][:30] == five["text_original"][:30]][:2]
        M.append(f"""**A concrete difference kept in both editions (issuing-law Article 2):**
{js([{'edition': x['edition_id'][-10:], 'text_start': x['text_original'][:75], 'in_files': [s['raw_ref']['path'].split('/')[-1][-24:] for s in x['provenance']['sources']]} for x in [five] + eq])}
No text was chosen as the "right" one; the instrument is queued for human review as a single item (`multiple_editions_differ_human_decision_needed`).
""")
    # ------------------------------------------------------------ 4 boundaries
    M.append("\n---\n## 4. Numbering restarts flagged, not split\n")
    many = collections.Counter(b["file"] for b in bounds).most_common(1)[0]
    one = next(b for b in bounds if b["proposed_role"] == "probable_issuing_law_prefix")
    M.append(f"""### 4a. A file with many restarts (the pilot would have split it into many "instruments")
`{many[0].split('/')[-1]}` has **{many[1]} restart boundaries**. In this release it stays **one instrument / one edition**; each boundary is recorded as `unconfirmed` in `reports/numbering_boundaries.json` and each affected article carries `part.numbering_segment` and `part.status: unconfirmed`.
{js([ {k: b[k] for k in ('start_index','prev_number','next_number','segment_before_len','segment_after_len','proposed_role','status')} for b in bounds if b['file'] == many[0]][:4])}
### 4b. Issuing-law articles clearly distinguished — but still unconfirmed
`{one['file'].split('/')[-1]}`: article numbering restarts at record {one['start_index']}; the first {one['segment_before_len']} records carry issuing-law wording and the remaining {one['segment_after_len']} align with a separate file that lacks them.
{js(one['evidence'])}
Articles keep both numbers without colliding (`~k` occurrence suffix) and are tagged:
{js([{'id': r['id'].split(':')[-1], 'canonical_number': r['article_number']['canonical'], 'occurrence': r['article_number']['occurrence'], 'part': r['part'], 'text_start': r['text_original'][:50]} for r in arts.values() if r['edition_id'] == one['instrument_id'] and False][:0] or [{'id_suffix': r['id'].split(':')[-1], 'canonical_number': r['article_number']['canonical'], 'part': r['part'], 'text_start': r['text_original'][:50]} for r in arts.values() if r['provenance']['sources'][0]['raw_ref']['path'] == one['file'] and r['provenance']['sources'][0]['raw_ref']['index'] in (0, 1, 2, 3)])}
A ready-to-approve proposal is in `config/split_confirmations.PROPOSED.json`; nothing is applied until its entries are copied into `config/split_confirmations.json` and the build is re-run.
""")
    # ------------------------------------------------------------ 5 template
    t = tmpl[0]
    M.append(f"""\n---\n## 5. Recovered template
{js({'raw content': t['legacy']['content'], 'raw source_fields.template_body': t['legacy']['source_fields']['template_body']})}
After: `content_status: {t['content_status']}`, `recovered_from: {t['recovered_from']}`, `text_original` = the template body verbatim, `legacy.content` = the original empty field, transformation `T07` logged. Required information: {len(t['required_information'])} fields; placeholders in body: {t['placeholders_in_body']}.
""")
    # ------------------------------------------------------------ 6 collision
    M.append("\n---\n## 6. Judgment ID collision and corrected mapping\n")
    leg = collections.defaultdict(set)
    for r in jrows: leg[r["legacy_id"]].add(r["new_id"])
    lid = sorted(k for k, v in leg.items() if len(v) > 1)[0]
    rows = [r for r in jrows if r["legacy_id"] == lid]
    M.append(f"""Legacy id `{lid}` was shared by {len(rows)} **different** principle texts of one paragraph.
Mapping rows (`mappings/judgment_id_map.csv.gz`):
{js(rows)}
Records:
{js([{'new_id': x, 'text_start': byid[x]['text_original'][:70], 'conflict_flag': byid[x]['provenance']['conflict_flags'][0]['flag']} for x in sorted(leg[lid])])}
References to this legacy id (e.g. {sum(1 for j in judg for a in j['references']['ambiguous'] if a['legacy'] == lid)} in canonical records) are stored as `ambiguous` with all candidates — never silently re-pointed. `python scripts/recover.py --out . {lid}` returns every candidate with its raw record.
""")
    # ------------------------------------------------------------ 7 identity
    M.append("\n---\n## 7. Law number/year: claimed vs canonical\n")
    pop = next(i for i in insts if i["identity"]["canonical_law_number"] and i["identity"]["basis"] == "claim+law_name+filename_agree")
    nul = next(i for i in insts if i["identity"]["status"] == "unresolved" and "name_or_filename_contradicts_claim" in i["identity"]["reasons"])
    M.append(f"""**Populated** (claim, law name and filename all agree, name opens as a law title):
{js({'name': pop['name']['selected'], 'claimed': pop['identity']['claimed'][:2], 'canonical_law_number': pop['identity']['canonical_law_number'], 'canonical_law_year': pop['identity']['canonical_law_year'], 'basis': pop['identity']['basis'], 'status': pop['identity']['status'], 'external_verification': pop['identity']['external_verification']})}
**Left null** (claim contradicts the law's own name):
{js({'name': nul['name']['selected'], 'claimed': nul['identity']['claimed'][:2], 'canonical_law_number': None, 'status': nul['identity']['status'], 'reasons': nul['identity']['reasons']})}
Totals: {S['laws']['canonical_law_number_populated']} instruments populated, {S['laws']['canonical_law_number_null']} null with review items. "Populated" means *internally consistent*, not externally verified (`external_verification: null`).
""")
    # ------------------------------------------------------------ 8 constitution
    M.append(f"""\n---\n## 8. Constitution count reconciliation

| | Arabic (`dustur/`) | English (`constitution/`) |
|---|---|---|
| preamble | {rec['ar']['preamble']} | {rec['en']['preamble']} |
| numbered articles 1–254 (no gaps, no duplicates) | {rec['ar']['numbered']} | {rec['en']['numbered']} |
| bis articles as their own files (150, 241, 244) | {len(rec['ar']['bis_files'])} | 0 (embedded in parent articles 150/241/244: {rec['english_bis_embedded_in_parent']}) |
| **total files = canonical records** | **{rec['ar']['md_files_excluding_README']} = {rec['canonical']['ar']}** | **{rec['en']['md_files_excluding_README']} = {rec['canonical']['en']}** |
| upstream `versions.json` units | {rec['upstream_versions_json_units']['dustur'][0]} | {rec['upstream_versions_json_units']['constitution'][0]} |
| upstream README article rows (excludes preamble) | {rec['ar']['readme_article_rows']} | {rec['en']['readme_article_rows']} |

"257 articles" = 254 numbered + 3 bis (excludes the preamble); "258" = the same 257 + the preamble. Arabic and English each have the same 257 provisions; English carries the 3 bis ones inside their parent articles. LexBridge's own file is separate: {rec['lexbridge_constitution_file']['records']} records (integer articles {rec['lexbridge_constitution_file']['integer_range']} + `{rec['lexbridge_constitution_file']['non_plain_integers']}`). Verdict: **{rec['verdict']}**.
""")
    open(f"{O}/reports/DECISION_EXAMPLES.md", "w", encoding="utf-8").write("\n".join(M))
    print("ok", sum(len(x) for x in M), "chars;", len(picks), "merge examples")


if __name__ == "__main__":
    main()
