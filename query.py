"""
query.py — GraphDistill 简易查询接口
=====================================

使用方法（直接修改下方 ★ 标注的三处配置，再运行即可）：

    python query.py

或在代码中作为模块导入：

    from query import ask
    result = ask("HashMap 和 TreeMap 的区别是什么？")
    print(result.answer)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# ★ 用户配置区 —— 修改这里即可
# ─────────────────────────────────────────────────────────────────────────────

# 你的 SiliconFlow API Key（也可通过环境变量 SILICONFLOW_API_KEY 传入）
API_KEY: str = ""

# 推理模型（默认 GLM-4.7，可换成其他 SiliconFlow 兼容模型）
MODEL: str = "Pro/zai-org/GLM-4.7"

# 向量 Embedding 模型（用于意图路由，默认 Qwen3-Embedding-8B）
EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-8B"

# ─────────────────────────────────────────────────────────────────────────────
# 以下配置通常不需要修改
# ─────────────────────────────────────────────────────────────────────────────

# SiliconFlow OpenAI 兼容接口地址
BASE_URL: str = "https://api.siliconflow.cn/v1"

# 知识图谱文件路径（优先使用含向量索引版本）
_GRAPH_WITH_VECTORS = Path(__file__).parent / "data" / "test_graph_with_vectors.json"
_GRAPH_FALLBACK = Path(__file__).parent / "data" / "test_core_extraction_unified_std_api.json"

# ─────────────────────────────────────────────────────────────────────────────
# 内部：懒加载图谱与引擎（只初始化一次，重复调用 ask() 时复用）
# ─────────────────────────────────────────────────────────────────────────────
_engine = None
_client = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine

    from core.graph_builder import GraphBuilder
    from core.search_engine import SearchEngine

    graph_path = _GRAPH_WITH_VECTORS if _GRAPH_WITH_VECTORS.exists() else _GRAPH_FALLBACK
    if not graph_path.exists():
        raise FileNotFoundError(
            f"找不到知识图谱文件，请先运行 main.py 构建图谱。\n"
            f"尝试路径：{_GRAPH_WITH_VECTORS} 或 {_GRAPH_FALLBACK}"
        )

    print(f"[GraphDistill] 正在加载知识图谱：{graph_path.name} ...")
    builder = GraphBuilder.load_json(graph_path)
    stats = builder.stats_report()
    print(
        f"[GraphDistill] 图谱加载完成："
        f"{stats.get('num_entities', 0)} 个实体，"
        f"{stats.get('num_relationships', 0)} 条关系，"
        f"向量索引={'已就绪' if builder.has_vector_index() else '未构建'}。"
    )

    _engine = SearchEngine(builder)
    return _engine


def _get_client(api_key: Optional[str] = None):
    global _client
    import os
    from openai import OpenAI

    key = api_key or API_KEY or os.getenv("SILICONFLOW_API_KEY", "")
    if not key:
        raise ValueError(
            "未提供 API Key。\n"
            "请在 query.py 顶部的 API_KEY 变量中填写，"
            "或通过环境变量 SILICONFLOW_API_KEY 传入，"
            "或调用 ask() 时传入 api_key 参数。"
        )

    # 若 Key 已存在且一致，复用客户端
    if _client is not None and getattr(_client, "_api_key_hint", None) == key[:8]:
        return _client

    client = OpenAI(base_url=BASE_URL, api_key=key)
    client._api_key_hint = key[:8]  # type: ignore[attr-defined]
    _client = client
    return client


# ─────────────────────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────────────────────

def ask(
    question: str,
    *,
    mode: str = "auto",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    embedding_model: Optional[str] = None,
):
    """
    向知识图谱提问，返回 SearchResult 对象。

    参数：
        question        — 你的问题（中文或英文均可）
        mode            — 搜索模式："local"（精确实体检索）| "global"（宏观架构问答）| "auto"（自动选择）
        api_key         — API Key，优先级高于模块顶部的 API_KEY 变量
        model           — 推理模型名，默认使用顶部 MODEL 配置
        embedding_model — Embedding 模型名，默认使用顶部 EMBEDDING_MODEL 配置

    返回：
        SearchResult，主要字段：
            .answer          — 自然语言回答（str）
            .mode            — 实际使用的搜索模式（"local" | "global" | "hybrid"）
            .confidence      — 置信度 0.0~1.0（float）
            .matched_entities — 命中的图谱实体列表（List[Tuple[str, float]]）
            .doc_references  — 关联的文档目录引用（List[Dict]）
            .sources         — 参与回答的原始文档元数据（List[Dict]）
    """
    engine = _get_engine()
    client = _get_client(api_key)

    result = engine.answer_question(
        client=client,
        model=model or MODEL,
        question=question,
        mode=mode,
        embedding_model=embedding_model or EMBEDDING_MODEL,
    )
    return result


def ask_and_print(
    question: str,
    *,
    mode: str = "auto",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> None:
    """
    向知识图谱提问，并将结果格式化打印到终端。
    适合在命令行交互时直接调用。
    """
    print(f"\n{'='*60}")
    print(f"问题：{question}")
    print(f"{'='*60}")

    result = ask(
        question,
        mode=mode,
        api_key=api_key,
        model=model,
        embedding_model=embedding_model,
    )

    print(f"模式：{result.mode}  |  置信度：{result.confidence:.0%}")

    if result.matched_entities:
        entities = ", ".join(eid for eid, _ in result.matched_entities[:3])
        print(f"命中实体：{entities}")

    if result.doc_references:
        print(f"关联文档（{len(result.doc_references)} 条）：")
        for ref in result.doc_references[:3]:
            print(f"  - 「{ref.get('concept', '')}」→ {ref.get('doc_path', '')}")

    print(f"\n回答：\n{result.answer}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 直接运行时的示例
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os

    # ── 在这里填写你的问题 ────────────────────────────────
    QUESTIONS = [
        "LinkedList 的作用有哪些？",
        "IncompatiblePackageException 是什么？",
        "HashSet 的性质有哪些？"
    ]
    # ─────────────────────────────────────────────────────

    for q in QUESTIONS:
        ask_and_print(q)
