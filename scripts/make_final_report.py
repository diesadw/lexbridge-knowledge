#!/usr/bin/env python3
"""Generate reports/FINAL_DATA_REPORT.md (Arabic) + reports/final_report_numbers.json from the real release data."""
import argparse, collections, gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import LexArchive


def jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--lexbridge-zip", default="/mnt/user-data/uploads/lexbridge-knowledge-main__1_.zip")
    a = ap.parse_args(); O = a.out
    lb = LexArchive(a.lexbridge_zip)
    S = json.load(open(f"{O}/reports/build_summary.json", encoding="utf-8"))
    V = json.load(open(f"{O}/reports/validation_results.json", encoding="utf-8"))
    insts_all = jl(f"{O}/canonical/legislation/instruments.jsonl.gz")
    insts = insts_all[1:]
    lart = jl(f"{O}/canonical/legislation/articles_lexbridge.jsonl.gz")
    eart = jl(f"{O}/canonical/legislation/articles_egypt_law_constitution.jsonl.gz")
    judg = jl(f"{O}/canonical/judgments/judgment_principles.jsonl.gz")
    small = {k: jl(f"{O}/canonical/{k}/{k}.jsonl.gz") for k in ("principles", "procedures", "deadlines", "defenses", "templates")}
    rev = jl(f"{O}/reports/human_review_items.jsonl.gz")
    bounds = json.load(open(f"{O}/reports/numbering_boundaries.json", encoding="utf-8"))
    N = {}
    # ---- before (raw) counts
    raw = {"laws": sum(len(lb.records(p)) for p in lb.list("knowledge/laws/")),
           "civil": sum(len(lb.records(p)) for p in lb.list("knowledge/judgments/") if "/criminal" not in p),
           "crim": sum(len(lb.records(p)) for p in lb.list("knowledge/judgments/") if "/criminal" in p)}
    for k in small:
        raw[k] = sum(len(lb.records(p)) for p in lb.list(f"knowledge/{k}/"))
    jc = collections.Counter(j["branch"] for j in judg)
    merged_by_branch = collections.Counter()
    for j in judg:
        merged_by_branch[j["branch"]] += len(j["provenance"]["sources"]) - 1
    rows = [
        ["التشريعات (Laws)", f"{raw['laws']:,}", f"{len(lart):,}", f"{raw['laws'] - len(lart):,} سجل مطابق تمامًا (نسخ ملفات متطابقة) اتدمج كـ sources — مفيش حذف؛ {len(insts)} instrument / {S['laws']['editions']} edition"],
        ["الدستور — egypt-law (جديد)", "—", f"{S['egypt_constitution']['ar']} AR + {S['egypt_constitution']['en']} EN", "إضافة جديدة؛ الأصل العربي + ترجمة إنجليزية مرتبطة"],
        ["أحكام النقض المدني", f"{raw['civil']:,}", f"{jc['civil']:,}", f"{merged_by_branch['civil']:,} سجل زائد"],
        ["أحكام النقض الجنائي", f"{raw['crim']:,}", f"{jc['crim']:,}", f"{merged_by_branch['crim']:,} سجل زائد"],
    ]
    for k, lab in (("principles", "المبادئ (Principles)"), ("procedures", "الإجراءات (Procedures)"), ("deadlines", "المواعيد (Deadlines)"),
                   ("defenses", "الدفوع (Defenses)"), ("templates", "النماذج (Templates)")):
        rows.append([lab, raw[k], len(small[k]), "بدون دمج"])
    total_raw = raw["laws"] + raw["civil"] + raw["crim"] + sum(raw[k] for k in small)
    total_new = len(lart) + len(eart) + len(judg) + sum(len(v) for v in small.values())
    rows.append(["**الإجمالي**", f"**{total_raw:,}**", f"**{total_new:,}**", "كل سجل خام ممثَّل مرة واحدة بالظبط داخل sources لسجل Canonical"])
    N["totals"] = {"raw": total_raw, "canonical": total_new}
    sec1 = table(rows, ["القسم", "قبل (Raw)", "بعد (Canonical)", "ملاحظة"])
    # ---- judgments detail
    merged = [j for j in judg if len(j["provenance"]["sources"]) > 1]
    red = sum(len(j["provenance"]["sources"]) - 1 for j in merged)
    status = S["judgments"]["status_by_raw_record"]
    # ---- unclassified / unlinked
    unc = [j for j in judg if all("uncategorized" in (c or "") for c in j["categories_seen"]) or not j["category_original"]]
    def has_rel(j):
        r = j["references"]
        return bool(r["resolved"] or r["ambiguous"] or r["law_refs_resolved"] or r["legacy"].get("related_defenses") or r["legacy"].get("related_procedures")
                    or r["legacy"].get("related_principles") or r["legacy"].get("related_contracts"))
    unl = [j for j in judg if not has_rel(j)]
    nolaw = [j for j in judg if not j["references"]["law_refs_resolved"]]
    nocit = [j for j in judg if not j["citations_original"]]
    law_ref_unres = sum(len(j["references"]["law_refs_unresolved"]) for j in judg)
    referenced = set()
    for j in judg: referenced.update(j["references"]["law_refs_resolved"])
    for k in ("defenses",):
        for r in small[k]: referenced.update(r["supporting_legislation"]["resolved"])
    for r in small["deadlines"]: referenced.update(r["legal_authority"]["references_claimed"]["resolved"])
    for r in small["procedures"]: referenced.update(r["related"]["related_articles"]["resolved"])
    for r in small["principles"]: referenced.update(r["statutory_references_claimed"]["resolved"])
    proc_ids = {p["id"] for p in small["procedures"]}
    tpl_unlinked = [t["id"] for t in small["templates"] if t["linked_procedure_id"] not in proc_ids]
    d_nojudg = [d["id"] for d in small["defenses"] if not d["supporting_judgments"]["resolved"] and not d["supporting_judgments"]["ambiguous"]]
    d_title = [d["id"] for d in small["defenses"] if d["incomplete"]]
    inst_null = [i for i in insts if not i["identity"]["canonical_law_number"]]
    inst_multi = [i for i in insts if len(i["editions"]) > 1]
    N["unclassified_unlinked"] = {
        "judgments_uncategorized": len(unc), "judgments_without_any_relation": len(unl), "judgments_without_law_link": len(nolaw),
        "judgments_without_citation": len(nocit), "judgment_to_law_refs_unresolved": law_ref_unres,
        "law_articles_referenced_by_anything": len(referenced & {r["id"] for r in lart}), "law_articles_total": len(lart),
        "instruments_canonical_identity_null": len(inst_null), "instruments_multi_edition": len(inst_multi),
        "boundaries_unconfirmed": sum(1 for b in bounds if b["status"] == "unconfirmed"),
        "defenses_title_only": len(d_title), "defenses_without_judgments": len(d_nojudg), "templates_without_valid_procedure_link": len(tpl_unlinked)}
    RJ = [r for q in lb.list("knowledge/judgments/") for r in lb.records(q)]
    relk = ("related_ids", "related_judgments", "related_articles", "related_defenses", "related_procedures", "related_contracts", "related_principles")
    b_unc = sum(1 for r in RJ if "uncategorized" in (r.get("category") or "") or not r.get("category"))
    b_unl = sum(1 for r in RJ if not any(r.get(k) for k in relk))
    b_nolaw = sum(1 for r in RJ if not r.get("related_articles"))
    b_nocit = sum(1 for r in RJ if not r["citations"])
    N["before"] = {"uncategorized": b_unc, "no_relation": b_unl, "no_law_link": b_nolaw, "no_citation": b_nocit}
    rows2 = [
        ["أحكام بدون تصنيف (uncategorized)", f"{len(unc):,}", f"من {len(judg):,}؛ قبل التنظيف: {b_unc:,} من {len(RJ):,} (الفرق من دمج نسخ الـ uncategorized_pool مع نسخها المصنَّفة)"],
        ["أحكام بدون أي ربط (لا أحكام/نصوص/دفوع/إجراءات)", f"{len(unl):,}", f"قبل: {b_unl:,}؛ تحتاج Linking لاحقًا"],
        ["أحكام بدون ربط بنص تشريعي", f"{len(nolaw):,}", f"قبل: {b_nolaw:,}"],
        ["أحكام بدون citation في المصدر", f"{len(nocit):,}", f"قبل: {b_nocit:,}؛ مش مُخترَع، الحقل فاضي في الأصل"],
        ["إشارات حكم→قانون لم تُحَل (legacy law id غير موجود)", f"{law_ref_unres:,}", "محفوظة كما هي في law_refs_unresolved"],
        ["مواد تشريعية لا يشير إليها أي سجل", f"{len(lart) - len(referenced & {r['id'] for r in lart}):,}", f"من {len(lart):,} (معلومة، مش عيب)"],
        ["قوانين (instruments) رقمها/سنتها الـ canonical = null", f"{len(inst_null)}", f"من {len(insts)}؛ الـ claims الأصلية محفوظة"],
        ["قوانين فيها أكثر من إصدار (edition)", f"{len(inst_multi)}", "قرار بشري على مستوى الـ instrument"],
        ["حدود ترقيم (numbering restarts) غير مؤكدة", f"{N['unclassified_unlinked']['boundaries_unconfirmed']}", "لم يُطبَّق أي تقسيم"],
        ["دفوع عنوان فقط (title-only)", f"{len(d_title)}", f"من {len(small['defenses'])}"],
        ["دفوع بدون أحكام مرتبطة", f"{len(d_nojudg)}", ""],
        ["نماذج بدون رابط إجراء صالح", f"{len(tpl_unlinked)}", ""],
        ["مبادئ إنجليزية (secondary paraphrase)", f"{len(small['principles'])}", "غير موثوقة كنص قانوني"],
        ["أحكام IDs قديمة متعارضة (collisions)", f"{S['judgments']['legacy_id_collisions']} id / {status.get('collision_resolved', 0)} سجل", "كل واحد بقى له ID فريد"],
        ["سجلات هوية ناقصة (من غير رقم فقرة)", f"{status.get('identity_incomplete', 0)}", "لم تُدمَج"],
        ["أحكام مرشحة للتكرار (potential duplicates)", f"{S['judgments']['potential_duplicate_candidates']}", "لم تُدمَج، للمراجعة"],
    ]
    sec2 = table(rows2, ["البند", "العدد", "ملاحظة"])
    rc = collections.Counter((r["category"], r["severity"]) for r in rev)
    sec3 = table([[c, s, n] for (c, s), n in sorted(rc.items())], ["فئة المراجعة", "الأهمية", "عدد البنود"])
    val_rows = [[r["check"][:2] + " " + r["check"][3:], "PASS" if r["passed"] else "FAIL"] for r in V["results"]]
    sec4 = table(val_rows, ["فحص", "نتيجة"])
    conf = [j for j in judg if j["citation_conflict"]]
    labeled = sum(1 for j in judg if j["citation_label"])
    dj = {(j["branch"], j["identity"]["case"], j["identity"]["year"]) for j in judg}
    bas = collections.Counter(j["citation_label_basis"] for j in judg)
    yrs = [int(j["identity"]["year"]) for j in judg]
    N["judgment_numbering"] = {"records": len(judg), "with_case_and_year": len(judg), "citation_label": labeled, "conflicts": len(conf),
                               "distinct_judgments": len(dj)}
    sec5 = table([[j["id"], j["citation_conflict"]["source_citation"], f"{j['citation_conflict']['structured_case']} / {j['citation_conflict']['structured_year']}", j["session_date"]] for j in conf],
                 ["سجل", "نص الـ citation في المصدر", "الرقم/السنة المسجّلان", "تاريخ الجلسة"])
    md = f"""# التقرير النهائي للبيانات بعد التنظيف — LexBridge v{S['release']}

**الحالة:** إصدار مرشح (release candidate) في مجلد منفصل. لم يتم تعديل Production أو البحث أو RAKEEN أو الموقع، ولم يتم نشر شيء. الأرشيفان الأصليان لم يتغيرا (تم فحص الـ hash بعد التشغيل). نتيجة التحقق الآلي: **{V['passed']}/{V['total']}** فحص ناجح.

## 1) عدد السجلات قبل وبعد — حسب القسم

{sec1}

**معنى الأرقام:** السجلات "الزائدة" لا تعني فقدان أحكام. ففي الأحكام: **{red:,}** سجل زائد اندمج داخل **{len(merged):,}** سجل Canonical، وكل سجل أصلي منهم ما زال موجودًا في `provenance.sources` (مع الـ ID القديم والمصدر والـ hash) وفي `merged_source_snapshots` وفي الأرشيف الخام، وقابل للاسترجاع بـ `scripts/recover.py`. في التشريعات، الفرق ({raw['laws'] - len(lart):,}) هو نسخ ملفات مطابقة حرفيًا.

حالة سجلات الأحكام الخام ({sum(status.values()):,}): { {k: v for k, v in sorted(status.items())} }

## 2) السجلات غير المصنَّفة أو غير المرتبطة

{sec2}

## 3) بنود المراجعة البشرية

إجمالي {len(rev):,} بند في `reports/human_review_items.jsonl.gz` (مجمّعة على مستوى الـ instrument/الإصدار حيث أمكن).

{sec3}

## 4) نتائج التحقق الآلي

{sec4}

## 5) ترقيم الأحكام (طعن/نقض رقم كذا لسنة كذا)

- **{len(judg):,}** سجل (مبدأ/فقرة) — **كلهم** ليهم رقم طعن وسنة قضائية رقميين (السنة بين {min(yrs)} و{max(yrs)}؛ مفيش صفر ولا قيم غريبة).
- عدد الأحكام المميّزة (محكمة + رقم طعن + سنة): **{len(dj):,}** ({sum(1 for b, _, _ in dj if b == 'civil'):,} مدني + {sum(1 for b, _, _ in dj if b == 'crim'):,} جنائي). السجلات الأكتر هي مبادئ متعددة من نفس الحكم.
- حقل `citation_label` ("الطعن رقم X لسنة Y قضائية") موجود على **{labeled:,}** سجل، مبني على الحقول المنظَّمة ومتحقق منه ضد الـ citation الأصلي: {dict(bas)}.
- **{len(conf)}** سجل فيهم الـ citation الأصلي بيتعارض مع الرقم/السنة المسجّلين (أرقام مقلوبة أو مبدّلة). **لم أختَر بالتخمين**: `citation_label = null` و`citation_conflict` فيه القيمتين، والسجل في المراجعة بأهمية عالية:

{sec5}

## 6) حدود معروفة

- لم أطّلع على كود الموقع أو RAKEEN؛ لذلك لا أستطيع الجزم بأن أي endpoint يعتمد على IDs قديمة سيعمل — الضمان المُثبَت هو أن جداول الـ mapping تحل كل ID قديم (فحوص F1–F3، H1–H2).
- "الرقم/السنة canonical" معناه *اتساق داخلي* وليس تحققًا خارجيًا (`external_verification: null`).
- لم يُحدَّد إصدار تشريعي مفضَّل ولم تُقيَّم حالة نفاذ أي نص (`legal_status: not_assessed`).
"""
    open(f"{O}/reports/FINAL_DATA_REPORT.md", "w", encoding="utf-8").write(md)
    json.dump(N, open(f"{O}/reports/final_report_numbers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(N, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
