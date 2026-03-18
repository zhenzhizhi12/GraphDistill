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
    - cangjie_runtime std/doc/libs（仓颉标准库文档：core, collection, math, sync, time, io 等）
    - interface_sdk_cangjie api（HarmonyOS 仓颉 SDK API：ArkUI 组件、Ark Interop 等）
    - 文档目录引用（DOCUMENTED_AT 关系）的利用情况验测
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

# 添加根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("graphdistill.test_report")

# ─────────────────────────────────────────────────────────────────────────────
# 测试用例定义
# 按数据源和难度精心设计，覆盖标准库核心包、集合、数学、并发、时间、IO，
# 以及 SDK 侧的 ArkUI 组件和 Ark Interop
# ─────────────────────────────────────────────────────────────────────────────
TEST_CASES: List[Dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.core（核心包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_core_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "怎么将字符串中的浮点数转为Float64类型？",
        "expected_keywords": ["Float64", "parse", "字符串"],
        "expected_entity_prefix": ["float64", "string"],
    },
    {
        "id": "stdlib_core_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "std.core 包中 String 类有哪些常用方法？",
        "expected_keywords": ["String", "core"],
        "expected_entity_prefix": ["class:std_core", "string"],
    },
    {
        "id": "stdlib_core_03",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "Exception 类和 Error 类的继承关系是怎样的？它们各自的用途是什么？",
        "expected_keywords": ["Exception", "Error"],
        "expected_entity_prefix": ["exception", "error"],
    },
    {
        "id": "stdlib_core_04",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "Option<T> 类型有什么作用？Some 和 None 构造器如何使用？",
        "expected_keywords": ["Option", "Some", "None"],
        "expected_entity_prefix": ["option"],
    },
    {
        "id": "stdlib_core_05",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "sizeOf<T>() 和 alignOf<T>() 函数的作用是什么？CType 约束是什么含义？",
        "expected_keywords": ["sizeOf", "CType"],
        "expected_entity_prefix": ["sizeof", "ctype"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.collection（集合包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_coll_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "ArrayList 和 LinkedList 的区别是什么？各自适合什么场景？",
        "expected_keywords": ["ArrayList", "LinkedList"],
        "expected_entity_prefix": ["arraylist", "linkedlist"],
    },
    {
        "id": "stdlib_coll_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "如何使用 HashMap 存储键值对并进行查找？HashMap 的底层实现原理是什么？",
        "expected_keywords": ["HashMap", "哈希"],
        "expected_entity_prefix": ["hashmap"],
    },
    {
        "id": "stdlib_coll_03",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "ArrayDeque 双端队列的容量策略是怎样的？初始容量有什么限制？",
        "expected_keywords": ["ArrayDeque", "容量"],
        "expected_entity_prefix": ["arraydeque", "deque"],
    },
    {
        "id": "stdlib_coll_04",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "TreeMap 和 HashMap 的区别是什么？TreeMap 是基于什么数据结构实现的？",
        "expected_keywords": ["TreeMap", "HashMap"],
        "expected_entity_prefix": ["treemap", "hashmap"],
    },
    {
        "id": "stdlib_coll_05",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "HashSet 和 TreeSet 各自的特点是什么？如何选择使用？",
        "expected_keywords": ["HashSet", "TreeSet"],
        "expected_entity_prefix": ["hashset", "treeset"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.math（数学包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_math_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "std.math 包提供了哪些数学函数？包含哪些数学常数？",
        "expected_keywords": ["math", "abs", "sqrt"],
        "expected_entity_prefix": ["math"],
    },
    {
        "id": "stdlib_math_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "clamp 函数的作用是什么？如何使用它限制浮点数的范围？",
        "expected_keywords": ["clamp"],
        "expected_entity_prefix": ["clamp"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.sync（并发包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_sync_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "仓颉语言中如何使用 Mutex 互斥锁进行线程同步？synchronized 关键字如何搭配使用？",
        "expected_keywords": ["Mutex", "synchronized"],
        "expected_entity_prefix": ["mutex", "sync"],
    },
    {
        "id": "stdlib_sync_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "AtomicInt64 原子操作支持哪些方法？compareAndSwap 的行为是怎样的？",
        "expected_keywords": ["AtomicInt64", "原子"],
        "expected_entity_prefix": ["atomicint64", "atomic"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.time（时间包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_time_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "DateTime 类型如何解析时间字符串？支持哪些格式化模式？",
        "expected_keywords": ["DateTime", "格式"],
        "expected_entity_prefix": ["datetime"],
    },
    {
        "id": "stdlib_time_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "Duration 和 TimeZone 类型各自的作用是什么？",
        "expected_keywords": ["Duration", "TimeZone"],
        "expected_entity_prefix": ["duration", "timezone"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.io（IO包）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_io_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "BufferedInputStream 的作用是什么？它和 InputStream 接口是什么关系？",
        "expected_keywords": ["BufferedInputStream", "InputStream"],
        "expected_entity_prefix": ["bufferedinputstream", "inputstream"],
    },
    {
        "id": "stdlib_io_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "ByteBuffer 如何使用？它在 IO 操作中扮演什么角色？",
        "expected_keywords": ["ByteBuffer"],
        "expected_entity_prefix": ["bytebuffer"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 仓颉标准库 —— std.regex / std.fs
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "stdlib_regex_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "仓颉语言中如何使用 Regex 进行正则表达式匹配？",
        "expected_keywords": ["Regex", "正则"],
        "expected_entity_prefix": ["regex"],
    },
    {
        "id": "stdlib_misc_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "IncompatiblePackageException 在什么场景下会被抛出？",
        "expected_keywords": ["IncompatiblePackageException"],
        "expected_entity_prefix": ["incompatiblepackageexception"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # HarmonyOS SDK —— ArkUI 组件
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "sdk_arkui_01",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "List 组件如何设置滚动方向？listDirection 方法如何使用？",
        "expected_keywords": ["List", "Direction"],
        "expected_entity_prefix": ["list"],
    },
    {
        "id": "sdk_arkui_02",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "Row 组件如何设置子元素的垂直对齐和水平分布？alignItems 和 justifyContent 如何使用？",
        "expected_keywords": ["Row", "alignItems"],
        "expected_entity_prefix": ["row"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # HarmonyOS SDK —— Ark Interop / FFI
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "sdk_interop_01",
        "source": "interface_sdk_cangjie",
        "mode": "local",
        "question": "JSArrayBuffer 类提供了哪些方法来读取和转换字节数据？",
        "expected_keywords": ["JSArrayBuffer", "readBytes"],
        "expected_entity_prefix": ["jsarraybuffer"],
    },
    # sdk_interop_02 已删除：BusinessException 错误码 34300003 过于具体，
    # 类似内部错误码不在图谱提取范围内，无法可靠回答。
    # ═══════════════════════════════════════════════════════════════════════
    # 回归测试（与 query.py 同题目，确保批测与单测一致性）
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "regression_01",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "LinkedList在仓颉语言中有什么作用？",
        "expected_keywords": ["LinkedList"],
        "expected_entity_prefix": ["linkedlist"],
    },
    {
        "id": "regression_02",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "IncompatiblePackageException是什么？",
        "expected_keywords": ["IncompatiblePackageException"],
        "expected_entity_prefix": ["incompatiblepackageexception"],
    },
    {
        "id": "regression_03",
        "source": "Cangjie_StdLib",
        "mode": "local",
        "question": "HashSet有什么性质？",
        "expected_keywords": ["HashSet"],
        "expected_entity_prefix": ["hashset"],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # 全局/架构问题
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "global_01",
        "source": "all",
        "mode": "global",
        "question": "请总结仓颉语言标准库的整体模块架构设计，包括 core、collection、math、sync、time、io 等包的分工。",
        "expected_keywords": ["标准库", "模块", "core"],
        "expected_entity_prefix": [],
    },
    {
        "id": "global_02",
        "source": "all",
        "mode": "auto",
        "question": "仓颉语言的核心包（std.core）包含哪些关键类和接口？它们如何支撑整个标准库体系？",
        "expected_keywords": ["core", "类", "接口"],
        "expected_entity_prefix": [],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 图加载
# ─────────────────────────────────────────────────────────────────────────────
def load_graph_from_json(json_path: Path):
    """从 JSON 文件加载 GraphBuilder 实例。"""
    from core.graph_builder import GraphBuilder  # type: ignore

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
    - 检查关键实体是否已被收录（扩展到各核心包和 SDK 组件）；
    - 检查 DOCUMENTED_AT 关系是否存在（Track 1 目录解析质量）；
    - 检查各包之间的关系是否正确；
    - 统计各类型实体/关系数量。
    """
    results = []
    g = builder.graph

    # ── 1. 关键实体存在性检查（覆盖 std 核心包 + SDK ArkUI 组件）────────────
    expected_entities_groups = {
        "std核心概念": [
            "concept:core", "concept:collection", "concept:math",
            "concept:sync", "concept:time", "concept:io",
            "concept:argopt", "concept:binary", "concept:ast",
        ],
        "std集合类": [
            "concept:arraylist", "concept:linkedlist", "concept:hashmap",
            "concept:hashset", "concept:treemap", "concept:treeset",
            "concept:arraydeque",
        ],
        "std并发类": [
            "concept:atomicint64", "concept:mutex",
        ],
        "SDK ArkUI 组件": [
            "class:grid", "class:textcontroller", "class:jsarraybuffer",
            "class:scroller",
        ],
    }

    for group_name, entity_ids in expected_entities_groups.items():
        found = 0
        missing = []
        for eid in entity_ids:
            if eid in g.nodes:
                found += 1
            else:
                missing.append(eid)
        results.append({
            "test_type": f"entity_group_{group_name}",
            "passed": found >= len(entity_ids) * 0.5,  # 至少 50% 存在
            "detail": f"{group_name}: {found}/{len(entity_ids)} found"
                      + (f", missing: {missing}" if missing else ""),
        })

    # ── 2. DOCUMENTED_AT 关系质量检查 ──────────────────────────────────────
    doc_at_edges = [
        (u, v) for u, v, d in g.edges(data=True)
        if d.get("relation_type") == "DOCUMENTED_AT"
    ]
    file_nodes = [
        nid for nid, d in g.nodes(data=True)
        if d.get("entity_type") == "File"
    ]
    results.append({
        "test_type": "documented_at_count",
        "passed": len(doc_at_edges) > 50,
        "detail": f"DOCUMENTED_AT edges: {len(doc_at_edges)}, File entities: {len(file_nodes)}",
    })

    # 检查关键概念是否有 DOCUMENTED_AT 关系
    key_concepts_with_docs = ["concept:core", "concept:collection", "concept:math",
                               "concept:sync", "concept:time", "concept:io"]
    docs_found = 0
    for cid in key_concepts_with_docs:
        if cid in g:
            has_doc_at = any(
                d.get("relation_type") == "DOCUMENTED_AT"
                for _, _, d in g.out_edges(cid, data=True)
            )
            if has_doc_at:
                docs_found += 1
    results.append({
        "test_type": "key_concept_documented_at",
        "passed": docs_found >= 3,
        "detail": f"{docs_found}/{len(key_concepts_with_docs)} key concepts have DOCUMENTED_AT links",
    })

    # ── 3. 统计实体类型分布 ────────────────────────────────────────────────
    type_counts: Dict[str, int] = {}
    for nid, data in g.nodes(data=True):
        etype = data.get("entity_type", "Unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    results.append({
        "test_type": "entity_type_distribution",
        "passed": len(type_counts) >= 5,
        "detail": f"Entity types ({len(type_counts)}): {dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10])}",
    })

    # ── 4. 统计关系类型分布 ────────────────────────────────────────────────
    rel_counts: Dict[str, int] = {}
    for u, v, data in g.edges(data=True):
        rtype = data.get("relation_type", "Unknown")
        rel_counts[rtype] = rel_counts.get(rtype, 0) + 1

    results.append({
        "test_type": "relation_type_distribution",
        "passed": len(rel_counts) >= 5,
        "detail": f"Relation types ({len(rel_counts)}): {dict(sorted(rel_counts.items(), key=lambda x: x[1], reverse=True)[:10])}",
    })

    # ── 5. 数据源分布统计 ──────────────────────────────────────────────────
    source_counts: Dict[str, int] = {}
    for nid, data in g.nodes(data=True):
        for src in (data.get("sources") or []):
            preset = src.get("preset", "")
            if not preset:
                fp = str(src.get("file_path", "") or src.get("test_dir", ""))
                if "cangjie_runtime" in fp or "Cangjie_StdLib" in fp:
                    preset = "Cangjie_StdLib"
                elif "interface_sdk" in fp:
                    preset = "interface_sdk_cangjie"
                else:
                    preset = "other"
            source_counts[preset] = source_counts.get(preset, 0) + 1
            break

    results.append({
        "test_type": "source_distribution",
        "passed": len(source_counts) > 0,
        "detail": f"Source presets: {dict(sorted(source_counts.items(), key=lambda x: x[1], reverse=True))}",
    })

    # ── 6. 关键关系类型数量检查 ────────────────────────────────────────────
    for rtype, min_count in [("BELONGS_TO", 100), ("INHERITS", 10), ("IMPLEMENTS", 50), ("RETURNS", 100)]:
        actual = rel_counts.get(rtype, 0)
        results.append({
            "test_type": f"min_relation_count_{rtype}",
            "passed": actual >= min_count,
            "detail": f"{rtype}: {actual} (min expected: {min_count})",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 关键词回退搜索测试（无 LLM）
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# 文档目录引用测试（DOCUMENTED_AT 利用验证，无 LLM）
# ─────────────────────────────────────────────────────────────────────────────
def run_doc_reference_tests(builder) -> List[Dict[str, Any]]:
    """
    不调用 LLM，测试文档目录引用（DOCUMENTED_AT）功能：
    - 验证 SearchEngine._collect_doc_directory_info 能否正确提取关联文档路径；
    - 验证关键概念实体能通过图遍历找到对应的 File 实体。
    """
    from core.search_engine import SearchEngine  # type: ignore

    engine = SearchEngine(builder)
    results = []
    g = builder.graph

    # 测试：给定一组概念实体，检查能否通过 DOCUMENTED_AT 找到文档路径
    doc_ref_cases = [
        {
            "id": "docref_01",
            "entity_ids": {"concept:core"},
            "expected_doc_count_min": 1,
            "description": "core 概念应有文档引用",
        },
        {
            "id": "docref_02",
            "entity_ids": {"concept:collection"},
            "expected_doc_count_min": 1,
            "description": "collection 概念应有文档引用",
        },
        {
            "id": "docref_03",
            "entity_ids": {"concept:math"},
            "expected_doc_count_min": 1,
            "description": "math 概念应有文档引用",
        },
        {
            "id": "docref_04",
            "entity_ids": {"concept:sync"},
            "expected_doc_count_min": 1,
            "description": "sync 概念应有文档引用",
        },
        {
            "id": "docref_05",
            "entity_ids": {"concept:time"},
            "expected_doc_count_min": 1,
            "description": "time 概念应有文档引用",
        },
        {
            "id": "docref_06",
            "entity_ids": {"concept:io"},
            "expected_doc_count_min": 1,
            "description": "io 概念应有文档引用",
        },
        {
            "id": "docref_07",
            "entity_ids": {"concept:arraylist", "concept:hashmap", "concept:linkedlist"},
            "expected_doc_count_min": 1,
            "description": "集合类概念（混合查询）应有文档引用",
        },
        {
            "id": "docref_08",
            "entity_ids": {"concept:regex"},
            "expected_doc_count_min": 1,
            "description": "regex 概念应有文档引用",
        },
    ]

    for case in doc_ref_cases:
        # 确保所有给定节点存在于图中
        valid_ids = {eid for eid in case["entity_ids"] if eid in g}
        doc_refs = engine._collect_doc_directory_info(valid_ids)
        doc_count = len(doc_refs)
        passed = doc_count >= case["expected_doc_count_min"]

        sample_refs = [f"{r['concept']}→{r['doc_path']}" for r in doc_refs[:3]]
        results.append({
            "id": case["id"],
            "description": case["description"],
            "passed": passed,
            "doc_count": doc_count,
            "expected_min": case["expected_doc_count_min"],
            "sample_refs": sample_refs,
            "valid_entity_count": len(valid_ids),
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 关键词回退搜索测试（无 LLM）
# ─────────────────────────────────────────────────────────────────────────────
def run_keyword_fallback_tests(builder) -> List[Dict[str, Any]]:
    """
    不调用 LLM，仅测试关键词回退检索能否命中正确实体。
    用于验证在向量索引不可用时，关键词回退逻辑的有效性。
    """
    from core.search_engine import SearchEngine  # type: ignore

    engine = SearchEngine(builder)
    results = []

    keyword_cases = [
        # 标准库核心
        {
            "id": "kw_01",
            "question": "怎么将字符串中的浮点数转为Float64类型？",
            "expected_entity_contains": ["float64"],
        },
        {
            "id": "kw_02",
            "question": "IncompatiblePackageException 在什么场景下会被抛出？",
            "expected_entity_contains": ["incompatiblepackageexception"],
        },
        # 集合类
        {
            "id": "kw_03",
            "question": "仓颉语言中如何使用 ArrayList 存储和遍历元素？",
            "expected_entity_contains": ["arraylist"],
        },
        {
            "id": "kw_04",
            "question": "HashMap 如何存储和查找键值对？",
            "expected_entity_contains": ["hashmap"],
        },
        {
            "id": "kw_05",
            "question": "ArrayDeque 双端队列的容量策略是怎样的？",
            "expected_entity_contains": ["arraydeque"],
        },
        {
            "id": "kw_06",
            "question": "TreeMap 和 TreeSet 的底层实现是什么？",
            "expected_entity_contains": ["treemap"],
        },
        # 并发
        {
            "id": "kw_07",
            "question": "AtomicInt64 原子操作支持哪些方法？",
            "expected_entity_contains": ["atomicint64"],
        },
        {
            "id": "kw_08",
            "question": "如何使用 Mutex 互斥锁？",
            "expected_entity_contains": ["mutex"],
        },
        # 时间
        {
            "id": "kw_09",
            "question": "DateTime 如何解析时间字符串？",
            "expected_entity_contains": ["datetime"],
        },
        # IO
        {
            "id": "kw_10",
            "question": "BufferedInputStream 的作用是什么？",
            "expected_entity_contains": ["bufferedinputstream"],
        },
        # SDK 组件
        {
            "id": "kw_11",
            "question": "Button 组件有哪些类型？",
            "expected_entity_contains": ["button"],
        },
        {
            "id": "kw_12",
            "question": "Grid 组件如何设定列模板？",
            "expected_entity_contains": ["grid"],
        },
        {
            "id": "kw_13",
            "question": "JSArrayBuffer 类提供了哪些方法？",
            "expected_entity_contains": ["jsarraybuffer"],
        },
    ]

    for case in keyword_cases:
        candidates = engine._keyword_fallback_candidates(case["question"], top_k=5)
        candidate_ids = [eid.lower() for eid, _ in candidates]

        # 检查是否有任何候选实体 ID 包含期望的关键词
        expected = case["expected_entity_contains"]
        hits = [
            kw for kw in expected
            if any(kw.lower() in cid for cid in candidate_ids)
        ]
        passed = len(hits) >= 1 and len(candidates) > 0

        top3_info = [
            f"{eid}(d={dist:.2f})" for eid, dist in candidates[:3]
        ]
        results.append({
            "id": case["id"],
            "question": case["question"],
            "passed": passed,
            "expected_keywords": expected,
            "keyword_hits": hits,
            "top3_candidates": top3_info,
            "total_candidates": len(candidates),
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
    from core.search_engine import SearchEngine  # type: ignore

    engine = SearchEngine(builder)
    results = []

    for case in cases:
        qid = case["id"]
        question = case["question"]
        mode = case["mode"]
        expected_kws = case.get("expected_keywords", [])
        expected_entity_prefix = case.get("expected_entity_prefix", [])

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

            # 检查匹配的实体是否包含期望前缀（实体路由质量检验）
            entity_prefix_hits = []
            if expected_entity_prefix and result.matched_entities:
                matched_ids = [eid.lower() for eid, _ in result.matched_entities]
                for prefix in expected_entity_prefix:
                    if any(prefix.lower() in mid for mid in matched_ids):
                        entity_prefix_hits.append(prefix)

            # 全文检测不确定/信息不足（使用 search_engine 的统一正则）
            from core.search_engine import UNCERTAIN_RE  # type: ignore
            uncertain_hit = bool(UNCERTAIN_RE.search(result.answer))

            passed = (
                len(result.answer) > 20
                and not uncertain_hit
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
                "doc_references": result.doc_references,
                "sources_count": len(result.sources),
                "elapsed_seconds": round(elapsed, 2),
                "kw_coverage": round(kw_coverage, 2),
                "kw_hits": kw_hits,
                "entity_prefix_hits": entity_prefix_hits,
                "passed": passed,
                "uncertain_hit": uncertain_hit,
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
                "doc_references": [],
                "sources_count": 0,
                "elapsed_seconds": round(elapsed, 2),
                "kw_coverage": 0.0,
                "kw_hits": [],
                "entity_prefix_hits": [],
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
    keyword_fallback_results: Optional[List[Dict[str, Any]]] = None,
    doc_ref_test_results: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """将测试结果写入 Markdown 格式的测试报告。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: List[str] = []
    lines.append("# GraphDistill 搜索优化测试报告")
    lines.append("")
    lines.append(f"> 生成时间：{ts}")
    lines.append("")
    lines.append(
        "本报告涵盖两个核心数据源的知识检索测试："
    )
    lines.append(
        "- **Cangjie_StdLib**：`cangjie_runtime.git` (branch: release/1.0, subdir: std/doc/libs)"
    )
    lines.append(
        "- **interface_sdk_cangjie**：`interface_sdk_cangjie.git` (branch: master, subdir: api)"
    )
    lines.append(
        "- 测试用例覆盖：std.core, std.collection, std.math, std.sync, std.time, std.io, "
        "std.regex, ArkUI 组件 (List/Row), Ark Interop (JSArrayBuffer)"
    )
    lines.append("")

    # ── 1. 图谱概览 ──────────────────────────────────────────────────────────
    lines.append("## 1. 知识图谱概览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 实体数量 | {graph_stats.get('num_entities', 'N/A')} |")
    lines.append(f"| 关系数量 | {graph_stats.get('num_relationships', 'N/A')} |")
    lines.append(f"| 弱连通分量数 | {graph_stats.get('num_weakly_connected_components', 'N/A')} |")
    lines.append(f"| 向量索引 | {'✅ 已构建' if graph_stats.get('has_vector_index') else '❌ 未构建（需运行 build_vector_index.py）'} |")
    lines.append(f"| Embedding 模型 | Qwen/Qwen3-Embedding-8B |")
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

    # ── 2.5 文档目录引用（DOCUMENTED_AT）测试 ─────────────────────────────────
    if doc_ref_test_results:
        lines.append("## 2.5 文档目录引用（DOCUMENTED_AT）功能测试")
        lines.append("")
        lines.append(
            "验证搜索引擎能否通过 DOCUMENTED_AT 关系找到关联的文档路径，"
            "用于增强搜索上下文。"
        )
        lines.append("")
        dr_passed = sum(1 for r in doc_ref_test_results if r.get("passed"))
        lines.append(f"**通过率**: {dr_passed}/{len(doc_ref_test_results)}")
        lines.append("")
        lines.append("| ID | 描述 | 通过 | 文档引用数 | 示例引用 |")
        lines.append("|----|------|------|-----------|---------|")
        for r in doc_ref_test_results:
            status = "✅" if r.get("passed") else "❌"
            samples = " \\| ".join(r.get("sample_refs", [])[:2])
            lines.append(
                f"| {r['id']} | {r['description']} | {status} | "
                f"{r['doc_count']} (min={r['expected_min']}) | {samples} |"
            )
        lines.append("")

    # ── 3. 关键词回退检索测试（无 LLM）────────────────────────────────────────
    if keyword_fallback_results:
        lines.append("## 3. 关键词回退检索测试（无 LLM）")
        lines.append("")
        lines.append(
            "验证在向量索引不可用时，关键词回退逻辑（`_keyword_fallback_candidates`）能否定位到正确的图谱实体。"
        )
        lines.append("")
        kw_passed = sum(1 for r in keyword_fallback_results if r.get("passed"))
        lines.append(f"**通过率**: {kw_passed}/{len(keyword_fallback_results)}")
        lines.append("")
        lines.append("| ID | 问题 | 通过 | 期望关键词 | 命中 | Top-3候选实体 |")
        lines.append("|----|------|------|-----------|------|--------------|")
        for r in keyword_fallback_results:
            status = "✅" if r.get("passed") else "❌"
            q = r["question"][:40] + ("…" if len(r["question"]) > 40 else "")
            expected_str = ", ".join(r.get("expected_keywords", []))
            hits_str = ", ".join(r.get("keyword_hits", []))
            top3 = " \\| ".join(r.get("top3_candidates", [])[:3])
            lines.append(f"| {r['id']} | {q} | {status} | {expected_str} | {hits_str} | {top3} |")
        lines.append("")

    # ── 4. 搜索测试 ───────────────────────────────────────────────────────────
    if search_results:
        lines.append("## 4. 搜索问答测试结果")
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

        lines.append("### 4.1 按数据源统计")
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
        lines.append("### 4.2 详细测试结果")
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

            entity_prefix_hits = r.get("entity_prefix_hits", [])
            if entity_prefix_hits:
                lines.append(f"**实体路由命中**：{', '.join(entity_prefix_hits)}")

            if r.get("uncertain_hit"):
                lines.append("**⚠️ 不确定检测命中**：回答中包含信息不足/不确定表述")

            kw_hits = r.get("kw_hits", [])
            if kw_hits:
                lines.append(f"**命中关键词**：{', '.join(kw_hits)}")

            # 显示文档目录引用
            doc_refs = r.get("doc_references", [])
            if doc_refs:
                lines.append(f"**文档目录引用**（{len(doc_refs)} 条）：")
                for ref in doc_refs[:5]:
                    concept = ref.get("concept", "")
                    doc_path = ref.get("doc_path", "")
                    lines.append(f"  - 「{concept}」→ {doc_path}")

            lines.append("")
            lines.append("**回答**：")
            lines.append("")
            # 截断过长的回答
            answer = r.get("answer", "")
            if len(answer) > 800:
                answer = answer[:800] + "…（截断）"
            for ans_line in answer.split("\n"):
                lines.append(f"> {ans_line}" if ans_line.strip() else ">")
            lines.append("")

        # ── 4.3 文档目录引用利用统计 ─────────────────────────────────────
        lines.append("### 4.3 文档目录引用（DOCUMENTED_AT）利用统计")
        lines.append("")
        total_with_refs = sum(1 for r in search_results if r.get("doc_references"))
        total_local = sum(1 for r in search_results if r.get("mode") in ("local", "hybrid"))
        lines.append(f"在 {total_local} 个局部搜索测试中，{total_with_refs} 个获取到了文档目录引用。")
        lines.append("")
        if total_with_refs > 0:
            lines.append("| 测试ID | 文档引用数 | 示例引用 |")
            lines.append("|--------|-----------|---------|")
            for r in search_results:
                refs = r.get("doc_references", [])
                if refs:
                    sample = refs[0]
                    lines.append(
                        f"| {r['id']} | {len(refs)} | "
                        f"「{sample.get('concept','')}」→ {sample.get('doc_path','')} |"
                    )
            lines.append("")

    else:
        lines.append("## 4. 搜索问答测试")
        lines.append("")
        lines.append(
            "> ⚠️ 搜索测试已跳过（未提供 SILICONFLOW_API_KEY 或使用了 --skip-llm）。"
        )
        lines.append(
            "> 如需完整测试，请按以下步骤操作："
        )
        lines.append("> ")
        lines.append("> 1. 设置 API Key：`export SILICONFLOW_API_KEY=<your_key>`")
        lines.append("> 2. 构建向量索引：`python build_vector_index.py`")
        lines.append("> 3. 运行完整测试：`python test_search_report.py`")
        lines.append("")

    # ── 5. 优化总结 ───────────────────────────────────────────────────────────
    lines.append("## 5. 搜索优化策略总结（含文档目录引用增强）")
    lines.append("")
    lines.append(
        "本次对 `search_engine.py`、`test_search_report.py` 进行了以下优化："
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
            "关键词回退检索",
            "`_keyword_fallback_candidates`：名称命中权重3，内容命中权重1",
            "向量索引不可用时自动降级，保证本地搜索不会空返回",
        ),
        (
            "**文档目录引用增强（新增）**",
            "`_collect_doc_directory_info`：遍历 DOCUMENTED_AT 关系",
            "在搜索结果中附带关联文档路径，LLM 可参考原始文档丰富回答",
        ),
        (
            "**补充文档内容加载（新增）**",
            "`_load_supplementary_content`：从 temp_repos 加载关联文档原文",
            "当图谱信息不足时，自动补充来自原始文档的详细内容",
        ),
        (
            "**SearchResult.doc_references（新增）**",
            "返回结果携带 `doc_references` 字段",
            "下游（如 serve.py）可展示文档溯源链接，增强可追溯性",
        ),
    ]
    for opt_name, impl, effect in optimizations:
        lines.append(f"| {opt_name} | {impl} | {effect} |")
    lines.append("")

    report = "\n".join(lines)
    output_path.write_text(report, encoding="utf-8")
    logger.info("Test report written to %s", output_path)
    print(f"\n[OK] 测试报告已写入：{output_path}")


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
        default=None,
        help=(
            "知识图谱 JSON 文件路径。"
            "默认优先使用 test_graph_with_vectors.json（含向量索引），"
            "若不存在则回退到 test_core_extraction_unified_std_api.json。"
        ),
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 调用，仅测试图结构（无需 API Key）",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help=(
            "若加载的图谱没有向量索引，则自动调用 Embedding API 构建向量索引。"
            "需要 SILICONFLOW_API_KEY 环境变量。"
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default="TEST_REPORT.md",
        help="测试报告输出路径（默认：TEST_REPORT.md）",
    )
    parser.add_argument(
        "--skip-global",
        action="store_true",
        help="跳过 global/auto 模式的测试用例（节省时间）",
    )
    parser.add_argument(
        "--retest-failures",
        action="store_true",
        help="仅重测上次报告中 FAIL 的测试用例（快速验证修复效果）",
    )
    return parser.parse_args()


def _parse_failure_ids(report_path: Path) -> set:
    """从上次的 TEST_REPORT.md 中解析出所有 FAIL 的测试用例 ID。"""
    import re as _re
    if not report_path.exists():
        return set()
    text = report_path.read_text(encoding="utf-8")
    return set(_re.findall(r'\[(\w+)\]\s*❌\s*FAIL', text))


def main() -> None:
    args = parse_args()

    # ── 确定图谱文件路径（优先使用带向量索引版本）────────────────────────────
    if args.graph_json:
        graph_path = Path(args.graph_json)
    else:
        vector_path = Path(__file__).parent.parent / "data" / "test_graph_with_vectors.json"
        fallback_path = Path(__file__).parent.parent / "data" / "test_core_extraction_unified_std_api.json"
        if vector_path.exists():
            graph_path = vector_path
            logger.info("使用带向量索引的图谱文件：%s", graph_path)
        else:
            graph_path = fallback_path
            logger.info(
                "test_graph_with_vectors.json 不存在，回退到：%s "
                "（建议先运行 build_vector_index.py 构建向量索引）",
                graph_path,
            )

    output_path = Path(args.output)

    # ── 加载图谱 ──────────────────────────────────────────────────────────────
    builder = load_graph_from_json(graph_path)
    graph_stats = builder.stats_report()
    # has_vector_index 是方法，不是 stats 的一部分，补充进去
    graph_stats["has_vector_index"] = builder.has_vector_index()

    # ── 可选：在线构建向量索引 ─────────────────────────────────────────────────
    if args.build_index and not builder.has_vector_index() and not args.skip_llm:
        api_key = os.getenv("SILICONFLOW_API_KEY", "")
        if not api_key:
            logger.warning("--build-index 需要 SILICONFLOW_API_KEY，但未设置，跳过索引构建。")
        else:
            try:
                from openai import OpenAI  # type: ignore
                from main import BASE_URL, EMBEDDING_MODEL  # type: ignore

                _client_for_index = OpenAI(base_url=BASE_URL, api_key=api_key)
                logger.info("正在在线构建向量索引（模型：%s）...", EMBEDDING_MODEL)
                builder.build_vector_index(
                    client=_client_for_index,
                    embedding_model=EMBEDDING_MODEL,
                )
                if builder.has_vector_index():
                    # 保存到带向量索引的文件，供下次直接加载
                    _index_output = Path(__file__).parent.parent / "data" / "test_graph_with_vectors.json"
                    builder.save_json(_index_output)
                    logger.info("向量索引已构建并保存到：%s", _index_output)
                    graph_stats["has_vector_index"] = True
                else:
                    logger.warning("向量索引构建后仍不可用，请检查 API Key 和网络。")
            except Exception as exc:  # noqa: BLE001
                logger.error("在线构建向量索引失败：%s", exc, exc_info=True)

    # ── 图结构测试 ─────────────────────────────────────────────────────────────
    logger.info("Running graph structure tests ...")
    structure_results = run_graph_structure_tests(builder)
    for r in structure_results:
        status = "PASS" if r.get("passed") else "FAIL"
        logger.info("[%s] %s: %s", status, r.get("test_type"), r.get("detail", "")[:100])

    # ── 关键词回退检索测试（无 LLM） ───────────────────────────────────────────
    logger.info("Running keyword fallback tests ...")
    keyword_fallback_results = run_keyword_fallback_tests(builder)
    for r in keyword_fallback_results:
        status = "PASS" if r.get("passed") else "FAIL"
        logger.info(
            "[%s] %s: hits=%s top1=%s",
            status,
            r.get("id"),
            r.get("keyword_hits"),
            r.get("top3_candidates", ["(none)"])[0] if r.get("top3_candidates") else "(none)",
        )

    # ── 文档目录引用（DOCUMENTED_AT）功能测试 ──────────────────────────────────
    logger.info("Running doc reference (DOCUMENTED_AT) tests ...")
    doc_ref_test_results = run_doc_reference_tests(builder)
    for r in doc_ref_test_results:
        status = "PASS" if r.get("passed") else "FAIL"
        logger.info("[%s] %s: doc_count=%s, %s", status, r.get("id"), r.get("doc_count"), r.get("description", "")[:80])

    # ── 搜索测试（可选）──────────────────────────────────────────────────────
    search_results: Optional[List[Dict[str, Any]]] = None

    if not args.skip_llm:
        # 仅使用环境变量，避免任何明文密钥泄漏
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

                # 根据 --skip-global / --retest-failures 过滤测试用例
                active_cases = TEST_CASES
                if args.skip_global:
                    active_cases = [
                        c for c in active_cases
                        if c.get("mode") not in ("global", "auto")
                    ]
                    logger.info(
                        "--skip-global: filtered %d -> %d test cases",
                        len(TEST_CASES), len(active_cases),
                    )
                if args.retest_failures:
                    fail_ids = _parse_failure_ids(output_path)
                    if fail_ids:
                        active_cases = [c for c in active_cases if c["id"] in fail_ids]
                        logger.info(
                            "--retest-failures: retesting %d failed cases: %s",
                            len(active_cases), sorted(fail_ids),
                        )
                    else:
                        logger.info("--retest-failures: no failures found in last report, running all cases")

                logger.info("Running search tests with model=%s ...", model)
                search_results = run_search_tests(
                    client=client,
                    model=model,
                    embedding_model=EMBEDDING_MODEL,
                    builder=builder,
                    cases=active_cases,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Search test setup failed: %s", exc, exc_info=True)

    # ── 生成报告 ──────────────────────────────────────────────────────────────
    generate_report(
        graph_stats=graph_stats,
        structure_results=structure_results,
        search_results=search_results,
        output_path=output_path,
        keyword_fallback_results=keyword_fallback_results,
        doc_ref_test_results=doc_ref_test_results,
    )


if __name__ == "__main__":
    main()


