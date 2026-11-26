# Decision examples (generated from the real v3.0.0-rc1 release data)

## 1. The 1,708 merges (1,367 groups) — how they look and why they are safe

**Required evidence for every merge (all enforced and re-verified by validation G1/G2):** same court · same case/cassation number · same judicial year · same volume · same page · same paragraph number (all present) · identical judgment text (after whitespace collapse). Citation strings are **not** used as a key.

| Fact over all 1,367 groups | Value |
|---|---|
| groups by size | {2: 1064, 3: 279, 4: 10, 5: 14} |
| groups whose members sit in one file (exact in-file duplicates) | 5 |
| groups where any member's **citation list differs** | **0** (so there are no "citation formatting differs" merge cases to show; groups with no citation at all, e.g. criminal: 759) |
| member records whose **category** differs from the canonical one | 1702 (almost always a topic file vs. `uncategorized_pool.json`) |
| member records whose **title** differs | 229 |
| member records whose keywords / metadata differ | 1703 / 1702 |
| member records whose `source_fields` differ (kept in full inside the canonical record) | 1708 |

Because citation strings never differ inside a merged group, **no merge in this dataset depends on how a citation is formatted**; if citation formatting did differ, the rule would still ignore it and rely on the structured identity fields.

Every merged record keeps: all legacy ids (`legacy_ids`), per-source raw reference + hash, and a snapshot (`merged_source_snapshots`) of each non-canonical source's id, path, category, title, citations, keywords, metadata and (if different) `source_fields`. The raw archive holds the originals untouched.

### Representative examples

#### 1.1 criminal, 2 copies, different category labels

**Before (raw):** 2 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-15638",
  "file": "judicial_year_10s.json",
  "index": 434,
  "category": "الإثبات الجنائي",
  "title": "القبض",
  "citations": []
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-22194",
  "file": "uncategorized_pool.json",
  "index": 1818,
  "category": "uncategorized",
  "title": "مأمور الضبط القضائي",
  "citations": []
 }
]
```

**After:** one canonical record `jdg:crim:1000-14:v6ع:p498:n1:e0216b4f` — court `Egyptian Court of Cassation`, case 1000/14, volume 6ع, page 498, paragraph 1; text length 604 chars; `legacy_ids` = ['EGY-CRIM-15638', 'EGY-CRIM-22194']; `categories_seen` = ['uncategorized', 'الإثبات الجنائي'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (604 chars). Differences kept, not lost: category, title, source_fields (see `merged_source_snapshots`).

#### 1.2 3 copies

**Before (raw):** 3 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-04559",
  "file": "criminal_liability.json",
  "index": 174,
  "category": "المسؤولية الجنائية",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 1 لسنة 13 ق ، جلسة 1942/12/7 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-14940",
  "file": "uncategorized_pool.json",
  "index": 601,
  "category": "uncategorized",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 1 لسنة 13 ق ، جلسة 1942/12/7 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-21998",
  "file": "uncategorized_pool.json",
  "index": 1622,
  "category": "uncategorized",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 1 لسنة 13 ق ، جلسة 1942/12/7 )"
  ]
 }
]
```

**After:** one canonical record `jdg:crim:1-13:v6ع:p43:n1:20851d43` — court `Egyptian Court of Cassation`, case 1/13, volume 6ع, page 43, paragraph 1; text length 1266 chars; `legacy_ids` = ['EGY-CRIM-04559', 'EGY-CRIM-14940', 'EGY-CRIM-21998']; `categories_seen` = ['uncategorized', 'المسؤولية الجنائية'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (1266 chars). Differences kept, not lost: category, source_fields (see `merged_source_snapshots`).

#### 1.3 4+ copies

**Before (raw):** 4 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-04028",
  "file": "homicide.json",
  "index": 383,
  "category": "جرائم الأشخاص",
  "title": "القتل العمد",
  "citations": [
   "( الطعن رقم 107 لسنة 46 ق ، جلسة 1928/12/27 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-04051",
  "file": "uncategorized_pool.json",
  "index": 36,
  "category": "uncategorized",
  "title": "القتل العمد",
  "citations": [
   "( الطعن رقم 107 لسنة 46 ق ، جلسة 1928/12/27 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-04074",
  "file": "uncategorized_pool.json",
  "index": 59,
  "category": "uncategorized",
  "title": "القتل العمد",
  "citations": [
   "( الطعن رقم 107 لسنة 46 ق ، جلسة 1928/12/27 )"
  ]
 },
 "…[+1 more]"
]
```

**After:** one canonical record `jdg:crim:107-46:v1ع:p91:n1:1e763821` — court `Egyptian Court of Cassation`, case 107/46, volume 1ع, page 91, paragraph 1; text length 167 chars; `legacy_ids` = ['EGY-CRIM-04028', 'EGY-CRIM-04051', 'EGY-CRIM-04074', 'EGY-CRIM-04113']; `categories_seen` = ['uncategorized', 'جرائم الأشخاص'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (167 chars). Differences kept, not lost: category, source_fields (see `merged_source_snapshots`).

#### 1.4 two records of the same paragraph inside one file

**Before (raw):** 2 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-15567",
  "file": "uncategorized_pool.json",
  "index": 649,
  "category": "uncategorized",
  "title": "القبض",
  "citations": []
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-22123",
  "file": "uncategorized_pool.json",
  "index": 1747,
  "category": "uncategorized",
  "title": "مأمور الضبط القضائي",
  "citations": []
 }
]
```

**After:** one canonical record `jdg:crim:1183-42:v24:p27:n2:faca5577` — court `Egyptian Court of Cassation`, case 1183/42, volume 24, page 27, paragraph 2; text length 117 chars; `legacy_ids` = ['EGY-CRIM-15567', 'EGY-CRIM-22123']; `categories_seen` = ['uncategorized'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (117 chars). Differences kept, not lost: none in category, title, source_fields (see `merged_source_snapshots`).

#### 1.5 titles (topic labels) differ between copies; both kept in titles_seen

**Before (raw):** 2 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-15639",
  "file": "judicial_year_10s.json",
  "index": 435,
  "category": "الإثبات الجنائي",
  "title": "القبض",
  "citations": [
   "( الطعن رقم 1000 لسنة 14 ق ، جلسة 1944/6/5 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-22195",
  "file": "uncategorized_pool.json",
  "index": 1819,
  "category": "uncategorized",
  "title": "مأمور الضبط القضائي",
  "citations": [
   "( الطعن رقم 1000 لسنة 14 ق ، جلسة 1944/6/5 )"
  ]
 }
]
```

**After:** one canonical record `jdg:crim:1000-14:v6ع:p498:n2:bf06fd62` — court `Egyptian Court of Cassation`, case 1000/14, volume 6ع, page 498, paragraph 2; text length 253 chars; `legacy_ids` = ['EGY-CRIM-15639', 'EGY-CRIM-22195']; `categories_seen` = ['uncategorized', 'الإثبات الجنائي'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (253 chars). Differences kept, not lost: category, title, source_fields (see `merged_source_snapshots`).

#### 1.6 source_fields differ between copies

**Before (raw):** 3 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-04455",
  "file": "criminal_liability.json",
  "index": 70,
  "category": "المسؤولية الجنائية",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 10 لسنة 4 ق ، جلسة 1934/1/8 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-14836",
  "file": "uncategorized_pool.json",
  "index": 497,
  "category": "uncategorized",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 10 لسنة 4 ق ، جلسة 1934/1/8 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-21894",
  "file": "uncategorized_pool.json",
  "index": 1518,
  "category": "uncategorized",
  "title": "الاشتراك الجنائي",
  "citations": [
   "( الطعن رقم 10 لسنة 4 ق ، جلسة 1934/1/8 )"
  ]
 }
]
```

**After:** one canonical record `jdg:crim:10-4:v3ع:p234:n1:e9c001e3` — court `Egyptian Court of Cassation`, case 10/4, volume 3ع, page 234, paragraph 1; text length 1318 chars; `legacy_ids` = ['EGY-CRIM-04455', 'EGY-CRIM-14836', 'EGY-CRIM-21894']; `categories_seen` = ['uncategorized', 'المسؤولية الجنائية'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (1318 chars). Differences kept, not lost: category, source_fields (see `merged_source_snapshots`).

#### 1.7 criminal with no citation

**Before (raw):** 2 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-16068",
  "file": "criminal_liability.json",
  "index": 827,
  "category": "المسؤولية الجنائية",
  "title": "المسؤولية الجنائية",
  "citations": []
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-16433",
  "file": "uncategorized_pool.json",
  "index": 740,
  "category": "uncategorized",
  "title": "المسؤولية الجنائية",
  "citations": []
 }
]
```

**After:** one canonical record `jdg:crim:1002-47:v29:p132:n1:af4b2027` — court `Egyptian Court of Cassation`, case 1002/47, volume 29, page 132, paragraph 1; text length 572 chars; `legacy_ids` = ['EGY-CRIM-16068', 'EGY-CRIM-16433']; `categories_seen` = ['uncategorized', 'المسؤولية الجنائية'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (572 chars). Differences kept, not lost: category, source_fields (see `merged_source_snapshots`).

#### 1.8 largest group

**Before (raw):** 5 records
```json
[
 {
  "role": "canonical_source",
  "legacy_id": "EGY-CRIM-05100",
  "file": "judicial_year_10s.json",
  "index": 208,
  "category": "الإثبات الجنائي",
  "title": "البلاغ الكاذب",
  "citations": [
   "( الطعن رقم 1264 سنة 19 ق ، جلسة 1949/11/8 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-05101",
  "file": "uncategorized_pool.json",
  "index": 133,
  "category": "uncategorized",
  "title": "البلاغ الكاذب",
  "citations": [
   "( الطعن رقم 1264 سنة 19 ق ، جلسة 1949/11/8 )"
  ]
 },
 {
  "role": "duplicate_source",
  "legacy_id": "EGY-CRIM-05180",
  "file": "uncategorized_pool.json",
  "index": 136,
  "category": "uncategorized",
  "title": "البلاغ الكاذب",
  "citations": [
   "( الطعن رقم 1264 سنة 19 ق ، جلسة 1949/11/8 )"
  ]
 },
 "…[+2 more]"
]
```

**After:** one canonical record `jdg:crim:1264-19:v1:p59:n1:65227519` — court `Egyptian Court of Cassation`, case 1264/19, volume 1, page 59, paragraph 1; text length 461 chars; `legacy_ids` = ['EGY-CRIM-05100', 'EGY-CRIM-05101', 'EGY-CRIM-05180', 'EGY-CRIM-05252', 'EGY-CRIM-05321']; `categories_seen` = ['uncategorized', 'الإثبات الجنائي'].

**Why safe:** all six identity fields are present and equal on every member; the whitespace-collapsed texts are identical (461 chars). Differences kept, not lost: category, source_fields (see `merged_source_snapshots`).


---
## 2. Similar records correctly kept separate

### 2a. Same text, same case/year/volume/page, **paragraph missing** → candidate, not merged

These records have identical text and the same case/year/volume/page, but **no paragraph number**, so the rule refuses to merge them. Each is kept as its own canonical record (two of the group are shown), linked through `potential_duplicate_of`, and listed for review.
```json
[
 {
  "id": "jdg:crim:legacy:EGY-CRIM-04031:5445299b",
  "identity": {
   "case": "176",
   "page": "759",
   "paragraph": "",
   "volume": "28",
   "year": "47"
  },
  "merge_status": "identity_incomplete",
  "legacy_ids": [
   "EGY-CRIM-04031"
  ],
  "potential_duplicate_of": [
   "jdg:crim:legacy:EGY-CRIM-04054:5445299b",
   "jdg:crim:legacy:EGY-CRIM-04077:5445299b",
   "jdg:crim:legacy:EGY-CRIM-04116:5445299b"
  ],
  "text": "فقرة رقم : ج 1) من المقرر أن الدفع ببطلان القبض و التفتيش إنما هو من ا"
 },
 {
  "id": "jdg:crim:legacy:EGY-CRIM-04054:5445299b",
  "identity": {
   "case": "176",
   "page": "759",
   "paragraph": "",
   "volume": "28",
   "year": "47"
  },
  "merge_status": "identity_incomplete",
  "legacy_ids": [
   "EGY-CRIM-04054"
  ],
  "potential_duplicate_of": [
   "jdg:crim:legacy:EGY-CRIM-04031:5445299b",
   "jdg:crim:legacy:EGY-CRIM-04077:5445299b",
   "jdg:crim:legacy:EGY-CRIM-04116:5445299b"
  ],
  "text": "فقرة رقم : ج 1) من المقرر أن الدفع ببطلان القبض و التفتيش إنما هو من ا"
 }
]
```

Totals: 87 records are in candidate relationships; 323 records have an incomplete identity (all lack only the paragraph number) and never merge.

### 2b. Same wording in different judgments → different identity → separate

`txt:d68b124c` is shared by 2 distinct judgments. They remain separate records (different case/volume/page/paragraph); `same_text_group` lets search de-duplicate display without destroying any judgment.
```json
[
 {
  "id": "jdg:civil:185-45:v29:p751:n1:d68b124c",
  "identity": {
   "case": "185",
   "page": "751",
   "paragraph": "1",
   "volume": "29",
   "year": "45"
  },
  "citations": [
   "طعن رقم 0185 لسنة 45"
  ]
 },
 {
  "id": "jdg:civil:520-34:v21:p18:n1:d68b124c",
  "identity": {
   "case": "520",
   "page": "18",
   "paragraph": "1",
   "volume": "21",
   "year": "34"
  },
  "citations": [
   "طعن رقم 0520 لسنة 34"
  ]
 }
]
```



---
## 3. Conflicting law editions preserved (no preferred edition)

Instrument `inst:lb:101b0c0979` (القانون رقم 131 لسنة 1948 بإصدار -=) holds **4 editions**; `preferred_edition` is `null`; every edition has `legal_status: not_assessed`.
```json
[
 {
  "edition": "ed:inst:lb:101b0c0979:acd916c904",
  "records": 1094,
  "files": [
   "القانون_رقم_131_لسنة_1948_بإصدار_-=.json",
   "القانون_رقم_131_لسنة_1948_بإصدار_-=_1.json"
  ]
 },
 {
  "edition": "ed:inst:lb:101b0c0979:06c00eccc6",
  "records": 1094,
  "files": [
   "القانون_رقم_131_لسنة_1948_بإصدار_القانون_المدني.json"
  ]
 },
 {
  "edition": "ed:inst:lb:101b0c0979:932d76c897",
  "records": 1093,
  "files": [
   "كود_القانون_المدنى.json"
  ]
 },
 "…[+1 more]"
]
```

Pairwise comparison (edition level, not per article):
```json
[
 {
  "differing": 1085,
  "edition_a": "ed:inst:lb:101b0c0979:06c00eccc6",
  "edition_b": "ed:inst:lb:101b0c0979:6b1575000d",
  "formatting_only": 9,
  "median_word_jaccard_of_differing": 0.909
 },
 {
  "differing": 1086,
  "edition_a": "ed:inst:lb:101b0c0979:06c00eccc6",
  "edition_b": "ed:inst:lb:101b0c0979:932d76c897",
  "formatting_only": 4,
  "median_word_jaccard_of_differing": 0.811
 },
 {
  "differing": 901,
  "edition_a": "ed:inst:lb:101b0c0979:932d76c897",
  "edition_b": "ed:inst:lb:101b0c0979:6b1575000d",
  "formatting_only": 190,
  "median_word_jaccard_of_differing": 0.853
 },
 "…[+3 more]"
]
```


**A concrete difference kept in both editions (issuing-law Article 2):**
```json
[
 {
  "edition": "acd916c904",
  "text_start": "على وزير العدل تنفيذ هذا القانون ويعمل به ابتداء من 15 أكتوبر سنة 1949.\nنأم",
  "in_files": [
   "لسنة_1948_بإصدار_-=.json",
   "نة_1948_بإصدار_-=_1.json"
  ]
 },
 {
  "edition": "06c00eccc6",
  "text_start": "على وزير العدل تنفيذ هذا القانون ويعمل به ابتداء من 51 أكتوبر سنة 1949.\nنأم",
  "in_files": [
   "صدار_القانون_المدني.json"
  ]
 }
]
```

No text was chosen as the "right" one; the instrument is queued for human review as a single item (`multiple_editions_differ_human_decision_needed`).


---
## 4. Numbering restarts flagged, not split

### 4a. A file with many restarts (the pilot would have split it into many "instruments")
`القانون_رقم_25_لسنة_1920_م.json` has **7 restart boundaries**. In this release it stays **one instrument / one edition**; each boundary is recorded as `unconfirmed` in `reports/numbering_boundaries.json` and each affected article carries `part.numbering_segment` and `part.status: unconfirmed`.
```json
[
 {
  "start_index": 13,
  "prev_number": 13,
  "next_number": 1,
  "segment_before_len": 13,
  "segment_after_len": 32,
  "proposed_role": "unclassified_restart",
  "status": "unconfirmed"
 },
 {
  "start_index": 45,
  "prev_number": 25,
  "next_number": 1,
  "segment_before_len": 32,
  "segment_after_len": 79,
  "proposed_role": "unclassified_restart",
  "status": "unconfirmed"
 },
 {
  "start_index": 124,
  "prev_number": 79,
  "next_number": 1,
  "segment_before_len": 79,
  "segment_after_len": 2,
  "proposed_role": "unclassified_restart",
  "status": "unconfirmed"
 },
 "…[+1 more]"
]
```

### 4b. Issuing-law articles clearly distinguished — but still unconfirmed
`القانون_رقم_131_لسنة_1948_بإصدار_-=.json`: article numbering restarts at record 2; the first 2 records carry issuing-law wording and the remaining 1092 align with a separate file that lacks them.
```json
{
 "corroborated_by_file_without_prefix": "knowledge/laws/civil/كود_القانون_المدنى.json",
 "issuing_law_text_markers_in_prefix": [
  "يلغي",
  "يعمل به",
  "الجريدة الرسمية"
 ],
 "numbering_restart": true
}
```

Articles keep both numbers without colliding (`~k` occurrence suffix) and are tagged:
```json
[
 {
  "id_suffix": "1",
  "canonical_number": "1",
  "part": {
   "numbering_segment": 0,
   "role_hint": "issuing_law_provisions_candidate",
   "status": "unconfirmed"
  },
  "text_start": "يلغي القانون المدني المعمول به أمام المحاكم الوطني"
 },
 {
  "id_suffix": "2",
  "canonical_number": "2",
  "part": {
   "numbering_segment": 0,
   "role_hint": "issuing_law_provisions_candidate",
   "status": "unconfirmed"
  },
  "text_start": "على وزير العدل تنفيذ هذا القانون ويعمل به ابتداء م"
 },
 {
  "id_suffix": "1~1",
  "canonical_number": "1",
  "part": {
   "numbering_segment": 1,
   "role_hint": "main_instrument_candidate",
   "status": "unconfirmed"
  },
  "text_start": "(1) تسري النصوص التشريعية على جميع المسائل التي تت"
 },
 "…[+1 more]"
]
```

A ready-to-approve proposal is in `config/split_confirmations.PROPOSED.json`; nothing is applied until its entries are copied into `config/split_confirmations.json` and the build is re-run.


---
## 5. Recovered template
```json
{
 "raw content": "",
 "raw source_fields.template_body": "بسم الله الرحمن الرحيم\n\nمحكمة {court_name}\n\nصحيفة دعوى\n\nمن / {plaintiff_name} — {plaintiff_job} — المقيم بـ {plaintiff_address} ومختار الإقا…[+326]"
}
```

After: `content_status: recovered_from_field`, `recovered_from: source_fields.template_body`, `text_original` = the template body verbatim, `legacy.content` = the original empty field, transformation `T07` logged. Required information: 12 fields; placeholders in body: ['court_name', 'date', 'defendant_address', 'defendant_job', 'defendant_name', 'facts', 'legal_grounds', 'plaintiff_address', 'plaintiff_elected_address', 'plaintiff_job', 'plaintiff_name', 'requests'].


---
## 6. Judgment ID collision and corrected mapping

Legacy id `cass_civil_cassation_rulings_003_30_1` was shared by 2 **different** principle texts of one paragraph.
Mapping rows (`mappings/judgment_id_map.csv.gz`):
```json
[
 {
  "legacy_id": "cass_civil_cassation_rulings_003_30_1",
  "source_path": "knowledge/judgments/cassation/civil/cassation_rulings.json",
  "source_index": "110",
  "new_id": "jdg:civil:3-30:v11:p512:n1:36be8f0c",
  "group_size": "1",
  "status": "collision_resolved",
  "role": "canonical_source"
 },
 {
  "legacy_id": "cass_civil_cassation_rulings_003_30_1",
  "source_path": "knowledge/judgments/cassation/civil/cassation_rulings.json",
  "source_index": "109",
  "new_id": "jdg:civil:3-30:v11:p512:n1:d8bbbdd5",
  "group_size": "1",
  "status": "collision_resolved",
  "role": "canonical_source"
 }
]
```

Records:
```json
[
 {
  "new_id": "jdg:civil:3-30:v11:p512:n1:36be8f0c",
  "text_start": "تنص المادة 21 من قانون السلطة القضائية رقم 56 لسنة 1959 على أن الهيئة ",
  "conflict_flag": "legacy_id_collision"
 },
 {
  "new_id": "jdg:civil:3-30:v11:p512:n1:d8bbbdd5",
  "text_start": "ليس فى المواد 17 فقرة ثانية ، 18 ، 19 ، 21 من القانون رقم 56 لسنة 1959",
  "conflict_flag": "legacy_id_collision"
 }
]
```

References to this legacy id (e.g. 0 in canonical records) are stored as `ambiguous` with all candidates — never silently re-pointed. `python scripts/recover.py --out . cass_civil_cassation_rulings_003_30_1` returns every candidate with its raw record.


---
## 7. Law number/year: claimed vs canonical

**Populated** (claim, law name and filename all agree, name opens as a law title):
```json
{
 "name": "القانون رقم 62 لسنة 1975 بشأن الكسب غير المشروع",
 "claimed": [
  {
   "law_number": "62",
   "law_year": "1975",
   "records": 47
  }
 ],
 "canonical_law_number": "62",
 "canonical_law_year": "1975",
 "basis": "claim+law_name+filename_agree",
 "status": "internally_consistent_not_externally_verified",
 "external_verification": null
}
```

**Left null** (claim contradicts the law's own name):
```json
{
 "name": "القانون رقم 144 لسنة بإصدارقانون الجهاز المركزى للمحاسبات 1988",
 "claimed": [
  {
   "law_number": "157",
   "law_year": "1998",
   "records": 32
  }
 ],
 "canonical_law_number": null,
 "status": "unresolved",
 "reasons": [
  "name_or_filename_contradicts_claim",
  "law_name_does_not_state_claimed_number_and_year",
  "filename_does_not_state_claimed_number_and_year"
 ]
}
```

Totals: 40 instruments populated, 65 null with review items. "Populated" means *internally consistent*, not externally verified (`external_verification: null`).


---
## 8. Constitution count reconciliation

| | Arabic (`dustur/`) | English (`constitution/`) |
|---|---|---|
| preamble | 1 | 1 |
| numbered articles 1–254 (no gaps, no duplicates) | 254 | 254 |
| bis articles as their own files (150, 241, 244) | 3 | 0 (embedded in parent articles 150/241/244: {'150': True, '241': True, '244': True}) |
| **total files = canonical records** | **258 = 258** | **255 = 255** |
| upstream `versions.json` units | 258 | 255 |
| upstream README article rows (excludes preamble) | 257 | 254 |

"257 articles" = 254 numbered + 3 bis (excludes the preamble); "258" = the same 257 + the preamble. Arabic and English each have the same 257 provisions; English carries the 3 bis ones inside their parent articles. LexBridge's own file is separate: 212 records (integer articles [1, 211] + `['192-bis']`). Verdict: **RECONCILED: no article missing or double-counted**.
