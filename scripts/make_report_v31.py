#!/usr/bin/env python3
"""Generate reports/V31_INTEGRATION_REPORT.md (Arabic) from the real v3.1.0-rc1 data."""
import argparse, collections, gzip, json, sys


def jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def table(rows, header):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); O = ap.parse_args().out
S = json.load(open(f"{O}/reports/build_summary.json", encoding="utf-8"))
V = json.load(open(f"{O}/reports/validation_results.json", encoding="utf-8"))
NE = json.load(open(f"{O}/reports/intake_not_exported.json", encoding="utf-8"))
I = jl(f"{O}/canonical/legislation/instruments.jsonl.gz")
old = [i for i in I if i["id"].startswith("inst:lb:")]; new = [i for i in I if i["id"].startswith("inst:in:")]
jf = jl(f"{O}/canonical/judgments/judgments_fulltext.jsonl.gz")
rev = jl(f"{O}/reports/human_review_items.jsonl.gz")
sub = S["intake"]; lg = S["legacy_laws"]; jr = S["judgment_law_refs"]; jx = S["judgments_fulltext"]
resolved_by_text = [o for o in old if any(m["basis"] == "text_alignment_identity_unconfirmed" for m in o["intake_matches"])]
rejected = [o for o in old if o["intake_matches_rejected"]]
rc = collections.Counter((r["category"], r["severity"]) for r in rev if r["category"].startswith(("law_intake", "law_legacy", "judgment_fulltext")))
rows = [[c, s, n] for (c, s), n in sorted(rc.items())]
reasons = [[k, v] for k, v in NE["by_reason"].items()]
jrows = [[r["citation_label"], r["court_label_original"], r["session_date"], (r["subject"] or "—")[:70], len(r["text_original"]),
          "نص مختلف (نسختين)" if r["variant_group"] else ("اندمج مع نسخة مطابقة" if len(r["provenance"]["sources"]) > 1 else "")] for r in sorted(jf, key=lambda r: (r["branch"], r["identity"]["year"], r["identity"]["case"]))]
md = f"""# تقرير دمج التشريعات الجديدة والأحكام — LexBridge v{S['release']}

**الحالة:** إصدار مرشح في مجلد منفصل مبني فوق v3.0.0-rc1، ولم يتم نشر شيء ولا لمس Production أو البحث أو RAKEEN أو الموقع. إصدار v3.0.0 والمصادر الأصلية لم يتغيروا (فحص hash). التحقق الآلي: **{V['passed']}/{V['total']}** ناجح، بما فيها إعادة بناء مطابقة بايت-ببايت.

**قاعدة الأولوية (حسب طلبك):** المصادر الجديدة (التشريعات والأحكام) لها الأولوية عند التعارض. تم تنفيذها كـ `precedence_rank = 1` للجديد، و`legacy_status` على القديم، **من غير حذف أي سجل قديم**.

## 1) الأعداد

{table([
    ["تشريعات جديدة (Law Intake)", f"{sub['laws']} قانون", f"{sub['articles']:,} مادة ({sub['articles_main']:,} رئيسية + {sub['articles_issuing']} إصدار)"],
    ["تشريعات قديمة (v3.0)", f"{lg['instruments']} قانون/مجموعة", f"{lg['article_records']:,} مادة — محفوظة كلها"],
    ["أحكام: مبادئ/فقرات (v3.0)", "—", "42,482 — بدون تغيير"],
    ["أحكام: نصوص كاملة (جديد)", f"{jx['raw_in_docx']} في الملف", f"{jx['canonical_records']} سجل ({jx['branch'].get('civil', 0)} مدني + {jx['branch'].get('crim', 0)} جنائي)"],
    ["الدستور (egypt-law)", "—", "513 — بدون تغيير"],
], ["القسم", "الحجم", "الناتج"])}

## 2) التشريعات الجديدة — وبالأمانة: التغطية ناقصة

- **{sub['laws']}** قانون و**{sub['articles']:,}** مادة اتضافوا، وكلهم: رقم/سنة من عنوان القانون جوه الملف، و`citation_label` بصيغة "المادة N من القانون رقم X لسنة Y"، والنص مطابق للـ intake (متحقق حرفيًا ضد الملف).
- **{NE['not_covered']} ملف من أصل {NE['total_source_files']} لسه ما دخلوش.** أسباب عدم دخولهم:

{table(reasons, ['السبب', 'عدد الملفات'])}

  القائمة الكاملة بأسماء الملفات: `reports/intake_not_exported.json`. القوانين دي **لسه موجودة في الداتا القديمة** بعلامة `legacy_not_replaced` لحد ما تتعالج.
- بنود المراجعة اللي طلعت من الـ intake نفسه ({sub['intake_open_review_items']:,} بند) اتنقلت كما هي للمراجعة، منها مواد اتسابت عمدًا لأن ترقيمها مكرر أو غير مرتّب في المصدر (يعني بعض القوانين المصدّرة **ناقصة مواد** وده معلَّم).
- **تحذير:** نص المواد الجديدة "مطابق للـ intake" مش "متحقق من الملف الأصلي" (الملفات الأصلية مش عندي). ضمان المطابقة للأصل جاي من عينة المراجعة اللي Claude عملها في الـ intake.

## 3) الأحكام (النصوص الكاملة) من ملف الورد

- **{jx['raw_in_docx']}** حكم في الملف ← **{jx['canonical_records']}** سجل. كل سجل فيه: رقم الطعن، السنة القضائية، تاريخ الجلسة، العنوان **كما هو حرفيًا**، الموضوع، والنص كامل بدون تعديل. سطر "المصدر: <رابط>" اتشال من كل السجلات (والملف الأصلي محفوظ في `raw_archive`)، وسطر العنوان "نص الحكم" اتفصل عن النص.
- **تكرار 1 (مطابق تمامًا):** اندمجوا في سجل واحد (النسختين محفوظتين في sources).
- **تكرار 2 (نفس الحكم، نص مختلف):** **{jx['variant_groups']}** حالة — الطعن 14108 لسنة 92 جلسة 4/5/2025 جه مرتين بنصين مختلفين (بفرق في الطول). **اتحفظ السجلين** ومعلَّمين للمراجعة بحجم الفرق وأول موضع اختلاف، لأن مفيش طريقة نحسم بيها أي نص هو الصحيح.
- مفيش تداخل مع الأحكام الموجودة (الموجودة سنواتها 1–66 والجديدة 77–95)، لكن الآلية جاهزة: لو حصل تداخل، السجل الجديد له الأولوية والقديم بيتربط به.
- فحوص الاتساق الداخلي: رقم الطعن/السنة اللي في العنوان موجود في نص الحكم نفسه في **75 من 75**. تاريخ الجلسة بيتطابق مع التاريخ الميلادي المكتوب في النص في **47** حكم، و**28** ما اتقارنوش (التاريخ الميلادي مش مكتوب بصيغة تتقرا آليًا في النص). **مفيش ولا تعارض**. سنوات الأحكام الجديدة من 77 إلى 95. ملاحظة: **63 من 75** عنوانهم مفيهوش موضوع (العنوان رقم + جلسة بس)، ومخترعتش موضوع لهم.

{table(jrows, ['الحكم', 'النوع', 'الجلسة', 'الموضوع (من العنوان)', 'طول النص', 'ملاحظة'])}

## 4) الأولوية والتعارض مع الداتا القديمة

- من {lg['instruments']} قانون قديم: {lg['status'].get('superseded_by_intake', 0)} **اتبدّل** (`superseded_by_intake`)، {lg['status'].get('partially_covered_by_intake', 0)} اتغطّى جزئيًا، {lg['status'].get('legacy_not_replaced', 0)} **لسه ما اتبدّلش**.
- **{lg['articles_with_intake_replacement']:,}** مادة قديمة ليها مقابل جديد (جدول `mappings/law_article_remap_legacy_to_intake.csv.gz`، وبعد تحقق نصي بنسبة تشابه ≥ 0.5 لكل مادة).
- **بوابة الهوية (مهمة):** لو القانون القديم رقمه وسنته معروفين، بيتربط بالجديد **بنفس الرقم والسنة فقط**. لقيت {len(rejected)} حالة نص متشابه لكن الرقم مختلف (قوانين تعديل بتقتبس نص قوانين تانية، زي 49/1977 مقابل 136/1981) **ومربطتهاش**، لأن ربط مراجع الأحكام بيها كان هيبقى ربط لقانون غلط.
- **{len(resolved_by_text)}** قانون قديم كان رقمه مجهول اتحسمت هويته بالتطابق النصي مع قانون جديد (حد أدنى تشابه 0.8، ومعلَّم `identity_unconfirmed`)، وفي حالة منهم اسم القديم بيقول سنة مختلفة عن الجديد (إيجارات 6/1996 مقابل 6/1997) اتعلّمت للمراجعة بأهمية عالية.
- **مراجع الأحكام للقوانين:** من {jr['legacy_refs']:,} مرجع، اتعمل remap لـ **{jr['remapped_to_intake']:,}** ({jr['remapped_to_intake'] / jr['legacy_refs']:.0%}) للمواد الجديدة، و**{jr['not_remapped']:,}** فضلوا على الـ IDs القديمة (لقوانين لسه ما دخلتش). المرجع الأصلي محفوظ دايمًا جنب الجديد (`law_refs_resolved` + `law_refs_remapped_to_intake` + `law_refs_not_remapped`).

## 5) بنود المراجعة الجديدة

{table(rows, ['الفئة', 'الأهمية', 'العدد'])}

## 6) المطلوب منك

1. استكمال الـ {NE['not_covered']} ملف (أغلبهم بدون رقم في العنوان أو PDF ممسوح) عبر دفعات جديدة من Claude بنفس البرومبت.
2. مراجعة الحكم 14108/92 (النصين).
3. مراجعة بنود الأهمية العالية في القوانين.
"""
open(f"{O}/reports/V31_INTEGRATION_REPORT.md", "w", encoding="utf-8").write(md)
print("ok", len(md))
