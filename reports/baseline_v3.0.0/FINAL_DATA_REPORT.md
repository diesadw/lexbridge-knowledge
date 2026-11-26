# التقرير النهائي للبيانات بعد التنظيف — LexBridge v3.0.0-rc1

**الحالة:** إصدار مرشح (release candidate) في مجلد منفصل. لم يتم تعديل Production أو البحث أو RAKEEN أو الموقع، ولم يتم نشر شيء. الأرشيفان الأصليان لم يتغيرا (تم فحص الـ hash بعد التشغيل). نتيجة التحقق الآلي: **55/55** فحص ناجح.

## 1) عدد السجلات قبل وبعد — حسب القسم

| القسم | قبل (Raw) | بعد (Canonical) | ملاحظة |
|---|---|---|---|
| التشريعات (Laws) | 21,093 | 19,310 | 1,783 سجل مطابق تمامًا (نسخ ملفات متطابقة) اتدمج كـ sources — مفيش حذف؛ 105 instrument / 135 edition |
| الدستور — egypt-law (جديد) | — | 258 AR + 255 EN | إضافة جديدة؛ الأصل العربي + ترجمة إنجليزية مرتبطة |
| أحكام النقض المدني | 21,701 | 21,701 | 0 سجل زائد |
| أحكام النقض الجنائي | 22,489 | 20,781 | 1,708 سجل زائد |
| المبادئ (Principles) | 49 | 49 | بدون دمج |
| الإجراءات (Procedures) | 74 | 74 | بدون دمج |
| المواعيد (Deadlines) | 67 | 67 | بدون دمج |
| الدفوع (Defenses) | 42 | 42 | بدون دمج |
| النماذج (Templates) | 7 | 7 | بدون دمج |
| **الإجمالي** | **65,522** | **62,544** | كل سجل خام ممثَّل مرة واحدة بالظبط داخل sources لسجل Canonical |

**معنى الأرقام:** السجلات "الزائدة" لا تعني فقدان أحكام. ففي الأحكام: **1,708** سجل زائد اندمج داخل **1,367** سجل Canonical، وكل سجل أصلي منهم ما زال موجودًا في `provenance.sources` (مع الـ ID القديم والمصدر والـ hash) وفي `merged_source_snapshots` وفي الأرشيف الخام، وقابل للاسترجاع بـ `scripts/recover.py`. في التشريعات، الفرق (1,783) هو نسخ ملفات مطابقة حرفيًا.

حالة سجلات الأحكام الخام (44,190): {'collision_resolved': 66, 'identity_incomplete': 323, 'merged_duplicate': 3075, 'unique': 40726}

## 2) السجلات غير المصنَّفة أو غير المرتبطة

| البند | العدد | ملاحظة |
|---|---|---|
| أحكام بدون تصنيف (uncategorized) | 192 | من 42,482؛ قبل التنظيف: 1,900 من 44,190 (الفرق من دمج نسخ الـ uncategorized_pool مع نسخها المصنَّفة) |
| أحكام بدون أي ربط (لا أحكام/نصوص/دفوع/إجراءات) | 771 | قبل: 771؛ تحتاج Linking لاحقًا |
| أحكام بدون ربط بنص تشريعي | 37,799 | قبل: 39,229 |
| أحكام بدون citation في المصدر | 10,450 | قبل: 11,418؛ مش مُخترَع، الحقل فاضي في الأصل |
| إشارات حكم→قانون لم تُحَل (legacy law id غير موجود) | 0 | محفوظة كما هي في law_refs_unresolved |
| مواد تشريعية لا يشير إليها أي سجل | 16,225 | من 19,310 (معلومة، مش عيب) |
| قوانين (instruments) رقمها/سنتها الـ canonical = null | 65 | من 105؛ الـ claims الأصلية محفوظة |
| قوانين فيها أكثر من إصدار (edition) | 18 | قرار بشري على مستوى الـ instrument |
| حدود ترقيم (numbering restarts) غير مؤكدة | 86 | لم يُطبَّق أي تقسيم |
| دفوع عنوان فقط (title-only) | 42 | من 42 |
| دفوع بدون أحكام مرتبطة | 0 |  |
| نماذج بدون رابط إجراء صالح | 0 |  |
| مبادئ إنجليزية (secondary paraphrase) | 49 | غير موثوقة كنص قانوني |
| أحكام IDs قديمة متعارضة (collisions) | 31 id / 66 سجل | كل واحد بقى له ID فريد |
| سجلات هوية ناقصة (من غير رقم فقرة) | 323 | لم تُدمَج |
| أحكام مرشحة للتكرار (potential duplicates) | 87 | لم تُدمَج، للمراجعة |

## 3) بنود المراجعة البشرية

إجمالي 552 بند في `reports/human_review_items.jsonl.gz` (مجمّعة على مستوى الـ instrument/الإصدار حيث أمكن).

| فئة المراجعة | الأهمية | عدد البنود |
|---|---|---|
| constitution | high | 1 |
| defense | high | 1 |
| judgment_citation_conflict | high | 30 |
| judgment_duplicate_candidates | medium | 36 |
| judgment_reference | medium | 312 |
| law_instrument | high | 28 |
| law_instrument | medium | 97 |
| law_instrument_aggregate | low | 27 |
| law_instrument_aggregate | medium | 12 |
| principle | low | 1 |
| procedure | low | 1 |
| template | low | 6 |

## 4) نتائج التحقق الآلي

| فحص | نتيجة |
|---|---|
| A1 archive hashes match build record | PASS |
| A2 raw_archive copies equal the originals and are read-only | PASS |
| B1 canonical ids unique across the whole release | PASS |
| B2 provenance block complete on every record | PASS |
| B3 every record carries schema_version and record_type | PASS |
| C1 all 66141 raw references resolve with matching hashes | PASS |
| D1 law articles verbatim for every source incl. identical copies (19310) | PASS |
| D2 egypt-law articles verbatim (513) | PASS |
| D3 judgments verbatim; merged sources identical after whitespace collapse (42482) | PASS |
| D4 small collections verbatim (templates from template_body; legacy content preserved) | PASS |
| D5 text_clean/text_search reproduce exactly from text_original | PASS |
| D6 clean ops logged iff text changed | PASS |
| E1 laws: every raw record in exactly one article's sources | PASS |
| E2 judgments: every raw record in exactly one canonical record | PASS |
| E3 small collections: 7/42/74/67/49 all present once | PASS |
| E4 egypt-law: 258 AR + 255 EN, one record per source file | PASS |
| F1 judgment map: every raw record -> an existing canonical id | PASS |
| F2 law map: every raw record -> an existing article id | PASS |
| F3 judgment map agrees with each canonical record's sources | PASS |
| G1 every merge (1367 groups) has same court, case, year, volume, page, paragraph (all present) and identical text | PASS |
| G2 no record with missing paragraph (or other identity part) was merged | PASS |
| G3 323 incomplete-identity records kept as separate records, each with all raw data | PASS |
| G4 potential-duplicate candidates: links symmetric, point to existing distinct records, none merged | PASS |
| G5 merged groups retain every non-canonical source's id, category, title, citations, keywords and metadata | PASS |
| H1 31 legacy ids collide in source; each resolves to distinct new ids all present | PASS |
| H2 0 unresolved judgment->judgment references; ambiguous ones keep >=2 candidates | PASS |
| H3 all resolved/ambiguous references point at existing canonical ids | PASS |
| H4 judgment->law references: every resolved id exists as an article | PASS |
| H5 defense->judgment references rewritten to existing ids | PASS |
| P1 every judgment has a numeric case number and judicial year | PASS |
| P2 citation_label present on every judgment except flagged conflicts, and contains its own case number and year | PASS |
| P3 citation conflicts (30) match an independent recount from raw and each has a review item | PASS |
| I1 no preferred edition and no legal status asserted anywhere | PASS |
| I2 each law file belongs to exactly one edition of exactly one instrument | PASS |
| I3 every edition has all of its records as article records (no edition truncated) | PASS |
| I4 cross-edition links present and symmetric where editions overlap | PASS |
| J1 all 86 numbering restarts detected and flagged (matches independent re-detection) | PASS |
| J2 no split applied without confirmation (config empty => every boundary unconfirmed, no confirmed parts) | PASS |
| J3 files are never divided: every raw file maps to a single instrument and a single edition | PASS |
| J4 issuing-law candidates are explicitly distinguished (role_hint) but marked unconfirmed | PASS |
| K1 original claimed number/year preserved for every instrument (matches raw counts) | PASS |
| K2 canonical number/year populated only with stated basis; otherwise null + unresolved | PASS |
| K3 every unresolved identity has a review item | PASS |
| L1 egypt-law and LexBridge constitutions fully separate (ids, instruments, sources) | PASS |
| L2 LexBridge constitution: identity unestablished, version unestablished, status not assessed | PASS |
| L3 constitution count reconciliation: 258 = 1 + 254 + 3 (AR), 255 = 1 + 254 (EN), none missing/double-counted | PASS |
| M1 title-only defenses flagged incomplete, no legal basis invented | PASS |
| M2 principles non-authoritative secondary paraphrase | PASS |
| M3 templates recovered with T07 logged; original content field preserved | PASS |
| M4 guide layers are lossless verbatim line partitions | PASS |
| M5 every ai_* source field carries an explicit label | PASS |
| M6 nothing marked verified | PASS |
| N1 idempotent: fresh rebuild is byte-identical for every output file | PASS |
| N2 output manifest matches files on disk | PASS |
| N3 original archives unchanged after run | PASS |

## 5) ترقيم الأحكام (طعن/نقض رقم كذا لسنة كذا)

- **42,482** سجل (مبدأ/فقرة) — **كلهم** ليهم رقم طعن وسنة قضائية رقميين (السنة بين 1 و66؛ مفيش صفر ولا قيم غريبة).
- عدد الأحكام المميّزة (محكمة + رقم طعن + سنة): **21,125** (9,489 مدني + 11,636 جنائي). السجلات الأكتر هي مبادئ متعددة من نفس الحكم.
- حقل `citation_label` ("الطعن رقم X لسنة Y قضائية") موجود على **42,452** سجل، مبني على الحقول المنظَّمة ومتحقق منه ضد الـ citation الأصلي: {'structured_identity_matches_source_citation': 32002, 'no_source_citation_structured_identity_used': 10450, 'conflict_source_citation_vs_structured_identity': 30}.
- **30** سجل فيهم الـ citation الأصلي بيتعارض مع الرقم/السنة المسجّلين (أرقام مقلوبة أو مبدّلة). **لم أختَر بالتخمين**: `citation_label = null` و`citation_conflict` فيه القيمتين، والسجل في المراجعة بأهمية عالية:

| سجل | نص الـ citation في المصدر | الرقم/السنة المسجّلان | تاريخ الجلسة |
|---|---|---|---|
| jdg:crim:1039-31:v13:p329:n1:80d9fad6 | ( الطعن رقم 1093 لسنة 31 ق ، جلسة 1962/4/10 ) | 1039 / 31 | 10-04-1962 |
| jdg:crim:1147-24:v6:p557:n2:080834ab | ( الطعن رقم 24 لسنة 1147 ق ، جلسة 1955/2/22 ) | 1147 / 24 | 22-02-1955 |
| jdg:crim:1266-37:v19:p4:n5:16e85440 | ( الطعن رقم 37 لسنة 1266 ق ، جلسة 1968/1/8 ) | 1266 / 37 | 08-01-1968 |
| jdg:crim:1379-30:v11:p848:n4:be83a764 | ( الطعن رقم 1397لسنه 30ق ، جلسه 1960/11/28 ) | 1379 / 30 | 28-11-1960 |
| jdg:crim:1452-48:v29:p980:n4:4610d8ca | ( الطعن رقم 48 لسنة 1452 ق ، جلسة 1978/12/28 ) | 1452 / 48 | 28-12-1978 |
| jdg:crim:1453-40:v22:p151:n3:7b142882 | ( الطعن رقم 1596 لسنة 2 ق ، جلسة 1932/3/28 ) | 1453 / 40 | 15-02-1971 |
| jdg:crim:1676-2:v2ع:p557:n2:5b33a6fc | ( الطعن رقم 505 لسنة 41 ق ، جلسة 1971/12/12 ) | 1676 / 2 | 23-05-1932 |
| jdg:crim:1853-36:v18:p114:n1:2c2af81c | ( الطعن رقم 180 لسنة 60 ق ، جلسة 1991/2/19 ) | 1853 / 36 | 30-01-1967 |
| jdg:crim:1885-20:v2:p578:n5:159fb241 | ( الطعن رقم 22 لسنة 21 ق ، جلسة 1952/2/16 ) | 1885 / 20 | 16-02-1952 |
| jdg:crim:1902-20:v2:p618:n4:a9b10ae6 | ( الطعن رقم 11 سنة 21 ق ، جلسة 1952/2/16 ) | 1902 / 20 | 16-02-1952 |
| jdg:crim:1932-58:v40:p630:n5:72c57355 | ( الطعن رقم 1932 لسنة 85 ق ، جلسة 1989/6/15 ) | 1932 / 58 | 15-06-1989 |
| jdg:crim:2113-37:v19:p165:n9:1e9bf376 | ( الطعن رقم 37 لسنة 2113 ق ، جلسة 1968/2/5 ) | 2113 / 37 | 05-02-1968 |
| jdg:crim:2139-23:v5:p585:n2:15f4e12a | ( الطعن رقم 23 لسنة 2139 ق ، جلسة 1954/5/4 ) | 2139 / 23 | 04-05-1954 |
| jdg:crim:2239-47:v2ع:p154:n2:d008f5c0 | ( الطعن رقم 2339 لسنة 47 ق ، جلسة 1930/12/11 ) | 2239 / 47 | 11-12-1930 |
| jdg:crim:2483-3:v3ع:p345:n1:d3bc5529 | ( الطعن رقم 2483 لسنة 4 ق ، جلسة 1934/6/4 ) | 2483 / 3 | 04-06-1934 |
| jdg:crim:2639-46:v1ع:p392:n1:198aded4 | ( الطعن رقم 46 لسنة 2639 ق ، جلسة 1929/11/28 ) | 2639 / 46 | 28-11-1929 |
| jdg:crim:2948-32:v14:p445:n1:1ee220f0 | ( الطعن رقم 2984 لسنة 32 ق ، جلسة 1963/5/27 ) | 2948 / 32 | 27-05-1963 |
| jdg:crim:298-33:v14:p456:n2:400055b1 | ( الطعن رقم 289 لسنة 32 ق ، جلسة 1963/5/27 ) | 298 / 33 | 27-05-1963 |
| jdg:crim:3126-31:v13:p767:n1:3534c91a | ( الطعن رقم 3126 لسنة 32 ق ، جلسة 1962/11/26 ) | 3126 / 31 | 26-11-1962 |
| jdg:crim:3725-58:v39:p853:n1:fa442372 | ( الطعن رقم 1 لسنة 21 ق ، جلسة 1951/11/17 ) | 3725 / 58 | 17-11-1951 |
| jdg:crim:428-40:v21:p613:n3:8e910d68 | ( الطعن رقم 428 لسنة ق ، جلسة 1970/4/19 ) | 428 / 40 | 19-04-1970 |
| jdg:crim:4602-55:v39:p741:n3:4ece2325 | ( الطعن رقم 2602 لسنة 55 ق ، جلسة 1988/6/2 ) | 4602 / 55 | 02-06-1988 |
| jdg:crim:53-23:v5:p105:n1:ef11cee3 | ( الطعن رقم 23 لسنة 53 ق ، جلسة 1953/11/24 ) | 53 / 23 | 24-11-1953 |
| jdg:crim:583-28:v9:p684:n2:30838fcf | ( الطعن رقم 853 لسنة 28 ق ، جلسة 1958/6/17 ) | 583 / 28 | 17-06-1958 |
| jdg:crim:7-33:v15:p233:n2:4ef1c51f | ( الطعن رقم 33 لسنة 7 ق ، جلسة 1964/4/13 ) | 7 / 33 | 13-04-1964 |
| jdg:crim:701-29:v11:p290:n1:a8d2cec7 | ( الطعن رقم 29 لسنة 701 ق ، جلسة 1960/3/22 ) | 701 / 29 | 22-03-1960 |
| jdg:crim:748-40:v21:p889:n2:99d8a642 | ( الطعن رقم 954 لسنة 40 ق ، جلسة 1970/10/4 ) | 748 / 40 | 15-06-1970 |
| jdg:crim:748-40:v21:p889:n3:bca1dbc5 | ( الطعن رقم 954 لسنة 40 ق ، جلسة 1970/10/4 ) | 748 / 40 | 15-06-1970 |
| jdg:crim:759-40:v21:p935:n3:de361c48 | ( الطعن رقم 727 لسنة 40 ق ، جلسة 1970/6/29 ) | 759 / 40 | 29-06-1970 |
| jdg:crim:994-20:v2:p398:n1:36c50876 | ( الطعن رقم 944 لسنة 20 ق ، جلسة 1950/12/19 ) | 994 / 20 | 19-12-1950 |

## 6) حدود معروفة

- لم أطّلع على كود الموقع أو RAKEEN؛ لذلك لا أستطيع الجزم بأن أي endpoint يعتمد على IDs قديمة سيعمل — الضمان المُثبَت هو أن جداول الـ mapping تحل كل ID قديم (فحوص F1–F3، H1–H2).
- "الرقم/السنة canonical" معناه *اتساق داخلي* وليس تحققًا خارجيًا (`external_verification: null`).
- لم يُحدَّد إصدار تشريعي مفضَّل ولم تُقيَّم حالة نفاذ أي نص (`legal_status: not_assessed`).
