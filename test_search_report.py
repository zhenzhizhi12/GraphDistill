"""
test_search_report.py
=====================
基于 test_core_extraction_unified_std_api.json 对优化后的搜索引擎进行全面测试，
并将结果写入 TEST_REPORT.md。

用法：
    # 带 LLM（需要 SILICONFLOW_API_KEY 环境变量）：
    python test_search_report.py

    # 仅测试图加载与向量路由（跳过 LLM 回答）：
    python test_search_report.py --skip-llm

测试内容覆盖：
    - cangjie_runtime std/doc/libs（仓颉标准库文档）
    - interface_sdk_cangjie api（HarmonyOS 仓颉 SDK API）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("graphdistill.test_report")

# ─────────────────────────────────────────────────────────────────────────────
# 测试用例定义
# 覆盖仓颉标准库文档与 HarmonyOS interface_sdk 两个主要数据源
# ─────────────────────────────────────────────────────────────────────────────
TEST_CASES: List[Dict[str, Any]] = [
    # --- 仓颉标准库（Cangjie_StdLib：cangjie_runtime/std/doc/libs）---
    {
        "id": "stdlib_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "怎么将字符串中的浮点数转为Float64类型？",
        "expected_keywords": ["Float64", "parse", "字符串", "转换"],
    },
    {
        "id": "stdlib_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "std.core 包中 String 类有哪些常用方法？",
        "expected_keywords": ["String", "core", "方法"],
    },
    {
        "id": "stdlib_03",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "ArrayList 和 LinkedList 的区别是什么？",
        "expected_keywords": ["ArrayList", "LinkedList"],
    },
    {
        "id": "stdlib_04",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "仓颉语言中如何处理异常？Exception 类的继承关系是怎样的？",
        "expected_keywords": ["Exception", "异常"],
    },
    {
        "id": "stdlib_05",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "IncompatiblePackageException 在什么场景下会被抛出？",
        "expected_keywords": ["IncompatiblePackageException"],
    },
    {
        "id": "stdlib_06",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "std.math 包提供了哪些数学函数？",
        "expected_keywords": ["math", "数学"],
    },
    {
        "id": "stdlib_07",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "如何使用 HashMap 存储键值对并进行查找？",
        "expected_keywords": ["HashMap"],
    },
    # --- HarmonyOS interface_sdk_cangjie ---
    {
        "id": "sdk_01",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "Button 组件的 onClick 事件如何触发？",
        "expected_keywords": ["Button", "onClick"],
    },
    {
        "id": "sdk_02",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "Text 组件如何设置字体大小和颜色？",
        "expected_keywords": ["Text", "字体"],
    },
    {
        "id": "sdk_03",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "如何申请相机或麦克风访问权限？",
        "expected_keywords": ["权限", "permission"],
    },
    # --- 全局架构问题 ---
    {
        "id": "global_01",
        "source": "all",
        "mode": "global",
        "question": "请总结仓颉语言标准库的整体模块架构设计。",
        "expected_keywords": ["标准库", "模块"],
    },
    {
        "id": "global_02",
        "source": "all",
        "mode": "auto",
        "question": "仓颉语言的核心包（std.core）包含哪些关键类和接口？",
        "expected_keywords": ["core", "类", "接口"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 图加载
# ─────────────────────────────────────────────────────────────────────────────
def load_graph_from_json(json_path: Path):
    """从 JSON 文件加载 GraphBuilder 实例。"""
    from graph_builder import GraphBuilder  # type: ignore

    if not json_path.exists():
        logger.error("Graph JSON not found: %s", json_path)
        return GraphBuilder()

    logger.info("Loading graph from %s ...", json_path)
    builder = GraphBuilder.load_json(json_path)
    stats = builder.stats_report()
    logger.info(
        "Graph loaded: %d entities, %d relationships, vector_index=%s",
        stats.get("num_entities", 0),
        stats.get("num_relationships", 0),
        builder.has_vector_index(),
    )
    return builder


# ─────────────────────────────────────────────────────────────────────────────
# 仅图结构测试（无 LLM）
# ─────────────────────────────────────────────────────────────────────────────
def run_graph_structure_tests(builder) -> List[Dict[str, Any]]:
    """
    不调用 LLM，仅测试图谱结构：
    - 检查关键实体是否已被收录；
    - 检查各包之间的关系是否正确；
    - 统计各类型实体/关系数量。
    """
    results = []
    g = builder.graph

    # 期望存在的关键实体（基于 test_core_extraction_unified_std_api.json）
    expected_entities = [
        "concept:core",
        "concept:argopt",
        "concept:binary",
        "concept:ast",
        "concept:math",
        "concept:collection",
    ]

    for eid in expected_entities:
        exists = eid in g.nodes
        results.append({
            "test_type": "entity_exists",
            "entity_id": eid,
            "passed": exists,
            "detail": f"Entity '{eid}' {'found' if exists else 'NOT FOUND'} in graph",
        })

    # 统计实体类型分布
    type_counts: Dict[str, int] = {}
    for nid, data in g.nodes(data=True):
        etype = data.get("entity_type", "Unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    results.append({
        "test_type": "entity_type_distribution",
        "passed": len(type_counts) > 0,
        "detail": f"Entity types: {dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10])}",
    })

    # 统计关系类型分布
    rel_counts: Dict[str, int] = {}
    for u, v, data in g.edges(data=True):
        rtype = data.get("relation_type", "Unknown")
        rel_counts[rtype] = rel_counts.get(rtype, 0) + 1

    results.append({
        "test_type": "relation_type_distribution",
        "passed": True,
        "detail": f"Relation types: {dict(sorted(rel_counts.items(), key=lambda x: x[1], reverse=True)[:10])}",
    })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 完整搜索测试（含 LLM）
# ─────────────────────────────────────────────────────────────────────────────
def run_search_tests(
    client: Any,
    model: str,
    embedding_model: str,
    builder,
    cases: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """使用 SearchEngine 运行所有测试用例，返回结构化测试结果。"""
    from search_engine import SearchEngine  # type: ignore

    engine = SearchEngine(builder)
    results = []

    for case in cases:
        qid = case["id"]
        question = case["question"]
        mode = case["mode"]
        expected_kws = case.get("expected_keywords", [])

        logger.info("Running test case %s (mode=%s): %s", qid, mode, question[:60])
        t0 = time.time()

        try:
            result = engine.answer_question(
                client=client,
                model=model,
                question=question,
                mode=mode,
                embedding_model=embedding_model,
            )
            elapsed = time.time() - t0

            # 检查关键词是否出现在答案中（简单质量检验）
            answer_lower = result.answer.lower()
            kw_hits = [kw for kw in expected_kws if kw.lower() in answer_lower]
            kw_coverage = len(kw_hits) / len(expected_kws) if expected_kws else 1.0
            passed = (
                len(result.answer) > 20
                and "不确定" not in result.answer[:30]
                and kw_coverage >= 0.3
            )

            results.append({
                "id": qid,
                "source": case["source"],
                "mode": result.mode,
                "question": question,
                "answer": result.answer,
                "confidence": result.confidence,
                "matched_entities": [
                    {"entity_id": eid, "distance": round(d, 4)}
                    for eid, d in result.matched_entities
                ],
                "sources_count": len(result.sources),
                "elapsed_seconds": round(elapsed, 2),
                "kw_coverage": round(kw_coverage, 2),
                "kw_hits": kw_hits,
                "passed": passed,
            })

        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - t0
            logger.warning("Test case %s failed: %s", qid, exc, exc_info=True)
            results.append({
                "id": qid,
                "source": case["source"],
                "mode": mode,
                "question": question,
                "answer": f"ERROR: {exc}",
                "confidence": 0.0,
                "matched_entities": [],
                "sources_count": 0,
                "elapsed_seconds": round(elapsed, 2),
                "kw_coverage": 0.0,
                "kw_hits": [],
                "passed": False,
            })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────────────────────────────────────
def generate_report(
    graph_stats: Dict[str, Any],
    structure_results: List[Dict[str, Any]],
    search_results: Optional[List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """将测试结果写入 Markdown 格式的测试报告。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: List[str] = []
    lines.append("# GraphDistill 搜索优化测试报告")
    lines.append("")
    lines.append(f"> 生成时间：{ts}")
    lines.append("")

    # ── 1. 图谱概览 ──────────────────────────────────────────────────────────
    lines.append("## 1. 知识图谱概览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 实体数量 | {graph_stats.get('num_entities', 'N/A')} |")
    lines.append(f"| 关系数量 | {graph_stats.get('num_relationships', 'N/A')} |")
    lines.append(f"| 弱连通分量数 | {graph_stats.get('num_weakly_connected_components', 'N/A')} |")
    lines.append(f"| 向量索引 | {'已构建' if graph_stats.get('has_vector_index') else '未构建'} |")
    lines.append("")

    # ── 2. 图结构测试 ─────────────────────────────────────────────────────────
    lines.append("## 2. 图结构验证")
    lines.append("")
    passed_struct = sum(1 for r in structure_results if r.get("passed"))
    lines.append(
        f"通过 {passed_struct}/{len(structure_results)} 项结构验证。"
    )
    lines.append("")
    lines.append("| 测试类型 | 通过 | 详情 |")
    lines.append("|----------|------|------|")
    for r in structure_results:
        status = "✅" if r.get("passed") else "❌"
        detail = r.get("detail", "").replace("|", "\\|")
        lines.append(f"| {r.get('test_type', '')} | {status} | {detail} |")
    lines.append("")

    # ── 3. 搜索测试 ───────────────────────────────────────────────────────────
    if search_results:
        lines.append("## 3. 搜索问答测试结果")
        lines.append("")

        total = len(search_results)
        passed = sum(1 for r in search_results if r.get("passed"))
        avg_conf = (
            sum(r.get("confidence", 0) for r in search_results) / total
            if total
            else 0.0
        )
        avg_elapsed = (
            sum(r.get("elapsed_seconds", 0) for r in search_results) / total
            if total
            else 0.0
        )

        lines.append(f"**通过率**: {passed}/{total} ({passed/total*100:.1f}%)")
        lines.append(f"**平均置信度**: {avg_conf:.2%}")
        lines.append(f"**平均响应时间**: {avg_elapsed:.2f}s")
        lines.append("")

        # 按数据源分组统计
        source_stats: Dict[str, Dict[str, int]] = {}
        for r in search_results:
            src = r.get("source", "unknown")
            if src not in source_stats:
                source_stats[src] = {"total": 0, "passed": 0}
            source_stats[src]["total"] += 1
            if r.get("passed"):
                source_stats[src]["passed"] += 1

        lines.append("### 3.1 按数据源统计")
        lines.append("")
        lines.append("| 数据源 | 通过 | 总数 | 通过率 |")
        lines.append("|--------|------|------|--------|")
        for src, stats in sorted(source_stats.items()):
            rate = stats["passed"] / stats["total"] * 100
            lines.append(
                f"| {src} | {stats['passed']} | {stats['total']} | {rate:.1f}% |"
            )
        lines.append("")

        # 详细测试用例
        lines.append("### 3.2 详细测试结果")
        lines.append("")

        for r in search_results:
            status = "✅ PASS" if r.get("passed") else "❌ FAIL"
            lines.append(f"#### [{r['id']}] {status}")
            lines.append("")
            lines.append(f"**问题**：{r['question']}")
            lines.append(f"**数据源**：{r['source']} | **搜索模式**：{r['mode']}")
            lines.append(
                f"**置信度**：{r.get('confidence', 0):.2%} | "
                f"**关键词覆盖率**：{r.get('kw_coverage', 0):.0%} | "
                f"**响应时间**：{r.get('elapsed_seconds', 0)}s"
            )

            matched = r.get("matched_entities", [])
            if matched:
                entity_str = ", ".join(
                    f"`{m['entity_id']}`(d={m['distance']})" for m in matched[:3]
                )
                lines.append(f"**匹配实体**：{entity_str}")

            kw_hits = r.get("kw_hits", [])
            if kw_hits:
                lines.append(f"**命中关键词**：{', '.join(kw_hits)}")

            lines.append("")
            lines.append("**回答**：")
            lines.append("")
            # 截断过长的回答
            answer = r.get("answer", "")
            if len(answer) > 600:
                answer = answer[:600] + "…（截断）"
            for ans_line in answer.split("\n"):
                lines.append(f"> {ans_line}" if ans_line.strip() else ">")
            lines.append("")

    else:
        lines.append("## 3. 搜索问答测试")
        lines.append("")
        lines.append(
            "> ⚠️ 搜索测试已跳过（未提供 SILICONFLOW_API_KEY 或使用了 --skip-llm）。"
        )
        lines.append(
            "> 请设置 `SILICONFLOW_API_KEY` 环境变量后重新运行以获取完整测试结果。"
        )
        lines.append("")

    # ── 4. 优化总结 ───────────────────────────────────────────────────────────
    lines.append("## 4. 搜索优化策略总结")
    lines.append("")
    lines.append(
        "本次对 `search_engine.py` 进行了以下优化，旨在提升回答质量和覆盖度："
    )
    lines.append("")
    lines.append(
        "| 优化点 | 实现方式 | 预期效果 |"
    )
    lines.append("|--------|----------|----------|")
    optimizations = [
        (
            "多候选实体检索",
            "`_vector_route_intent_multi(top_k=3)`",
            "避免只取 top-1 时遗漏相关实体，提升召回率",
        ),
        (
            "多实体子图融合",
            "`_collect_multi_entity_subgraph`",
            "合并多个候选实体的 1~2 跳邻居，丰富上下文",
        ),
        (
            "相似度 × 中心性重排序",
            "综合得分 = sim_score × (1 + degree_centrality)",
            "让最相关且图中最重要的实体优先被 LLM 看到",
        ),
        (
            "置信度评分",
            "`_compute_confidence`（相似度+高置信奖励+子图密度）",
            "为答案提供可解释的置信度指标",
        ),
        (
            "上下文节点数量控制",
            "`max_nodes=80` 截断策略",
            "防止 context 过长超出 LLM 窗口，保留高分节点",
        ),
        (
            "向后兼容",
            "`_vector_route_intent` 委托给多候选版本",
            "不破坏现有调用代码，平滑升级",
        ),
    ]
    for opt_name, impl, effect in optimizations:
        lines.append(f"| {opt_name} | {impl} | {effect} |")
    lines.append("")

    report = "\n".join(lines)
    output_path.write_text(report, encoding="utf-8")
    logger.info("Test report written to %s", output_path)
    print(f"\n✅ 测试报告已写入：{output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GraphDistill 搜索优化测试 & 报告生成器"
    )
    parser.add_argument(
        "--graph-json",
        type=str,
        default="test_core_extraction_unified_std_api.json",
        help="知识图谱 JSON 文件路径（默认：test_core_extraction_unified_std_api.json）",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 调用，仅测试图结构（无需 API Key）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="TEST_REPORT.md",
        help="测试报告输出路径（默认：TEST_REPORT.md）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph_path = Path(args.graph_json)
    output_path = Path(args.output)

    # ── 加载图谱 ──────────────────────────────────────────────────────────────
    builder = load_graph_from_json(graph_path)
    graph_stats = builder.stats_report()
    # has_vector_index 是方法，不是 stats 的一部分，补充进去
    graph_stats["has_vector_index"] = builder.has_vector_index()

    # ── 图结构测试 ─────────────────────────────────────────────────────────────
    logger.info("Running graph structure tests ...")
    structure_results = run_graph_structure_tests(builder)
    for r in structure_results:
        status = "PASS" if r.get("passed") else "FAIL"
        logger.info("[%s] %s: %s", status, r.get("test_type"), r.get("detail", "")[:100])

    # ── 搜索测试（可选）──────────────────────────────────────────────────────
    search_results: Optional[List[Dict[str, Any]]] = None

    if not args.skip_llm:
        api_key = os.getenv("SILICONFLOW_API_KEY", "")
        if not api_key:
            logger.warning(
                "SILICONFLOW_API_KEY not set; skipping LLM search tests. "
                "Use --skip-llm to suppress this warning."
            )
        else:
            try:
                from openai import OpenAI  # type: ignore
                from main import BASE_URL, MODEL, EMBEDDING_MODEL  # type: ignore

                model = os.getenv("GRAPHDISTILL_MODEL", MODEL)
                client = OpenAI(base_url=BASE_URL, api_key=api_key)

                logger.info("Running search tests with model=%s ...", model)
                search_results = run_search_tests(
                    client=client,
                    model=model,
                    embedding_model=EMBEDDING_MODEL,
                    builder=builder,
                    cases=TEST_CASES,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Search test setup failed: %s", exc, exc_info=True)

    # ── 生成报告 ──────────────────────────────────────────────────────────────
    generate_report(
        graph_stats=graph_stats,
        structure_results=structure_results,
        search_results=search_results,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
