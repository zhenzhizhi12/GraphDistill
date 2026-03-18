"""Spot test for two previously-uncertain queries."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from query import ask

cases = [
    "Duration 和 TimeZone 类型各自的作用是什么？",
    "HashSet 和 TreeSet 各自的特点是什么？如何选择使用？",
    "ArrayList 和 LinkedList 有什么区别？各自适合什么场景？",
]

for q in cases:
    print(f"\n{'='*60}")
    print(f"Q: {q}")
    r = ask(q, mode="local")
    import re
    unc_pat = re.compile(r"不确定|无法确定|未包含.*信息|没有包含.*信息|缺少.*信息|未提供.*信息")
    has_unc = bool(unc_pat.search(r.answer))
    print(f"HAS_UNCERTAIN_BROAD: {has_unc}")
    print(f"CONFIDENCE: {r.confidence:.2%}")
    print(f"MATCHED: {[(e,round(d,3)) for e,d in r.matched_entities[:5]]}")
    print(f"DOC_REFS: {len(r.doc_references)}")
    for dr in r.doc_references:
        print(f"  - {dr.get('concept')} -> {dr.get('doc_path')}")
    print(f"ANSWER:\n{r.answer[:1000]}")
    print("="*60)
