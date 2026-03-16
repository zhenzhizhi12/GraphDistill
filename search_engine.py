from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np

from graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


LOCAL_ANSWER_PROMPT = """
你是一个基于“技术架构知识图谱”的问答助手。

【提供给你的图上下文】
- 若干实体节点，每个包括：entity_id, entity_type, name, content, sources；
- 若干实体之间的关系，每条关系包括：source_id, target_id, relation_type, evidences。

【任务】
- 仅基于这些上下文，回答用户提出的技术细节问题；
- 尽量引用上下文中的关键术语与结构，而不要自己发明新概念；
- 若某个问题在上下文中没有足够信息支撑，必须明确说明“不确定”，而不是编造。

【输出要求】
- 用简洁的技术中文回答问题，可以分点列出；
- 不要在答案里附带 JSON，只返回自然语言答案。
"""


GLOBAL_COMMUNITY_SUMMARY_PROMPT = """
你是一个“架构级摘要器”，负责为一个技术社群（社区）生成高层次总结。

【输入】
- 一个技术社区中的若干实体（class、module、UI 组件、配置项、关键概念等）；
- 每个实体包含：entity_id, entity_type, name, content；

【任务】
- 识别该社区共同围绕的“技术主题”，例如：UI 渲染、并发调度、权限体系、配置系统等；
- 给出该社区在架构设计上的要点、关键组件及其大致分工；
- 可以点名少量代表性实体（id 或 name），但不要罗列所有节点。

【输出格式】
- 直接输出一段中文摘要，不要带 JSON、Markdown 代码块或无关解释。
"""


GLOBAL_ANSWER_PROMPT = """
你是一个面向“整体架构问题”的社会搜索助手。

【提供给你的输入】
- 若干技术社区的摘要，每个摘要概括了一个子领域（例如 UI、并发、存储、配置等）；
- 用户提出的一个宏观架构问题。

【任务】
- 根据问题，判断哪些社区摘要是相关的；
- 对相关社区中的信息做综合抽象，给出体系化的技术回答；
- 可以适当指出不同方案/模块之间的协作关系与权衡。

【输出要求】
- 输出结构清晰的中文回答，偏向“设计文档式”的解释；
- 不要引用 JSON 或内部数据结构名，只谈技术本身。
"""


@dataclass
class SearchResult:
    """
    问答结果封装，包含自然语言答案与溯源信息。
    """

    answer: str
    mode: str  # "local" | "global" | "hybrid"
    sources: List[Dict[str, Any]]


class SearchEngine:
    """
    基于 GraphBuilder 维护的全局图谱，实现：

    - 图搜索（Local / Graph Search）：围绕核心实体做 1~2 跳多跳检索；
    - 社会搜索（Global / Community Search）：基于社区发现和群落摘要的宏观问答；
    - 统一路由接口 answer_question。
    """

    def __init__(self, builder: GraphBuilder) -> None:
        self.builder = builder

    # ------------------------------------------------------------------
    # 本地图搜索：向量路由 + multi-hop + 图上下文 + LLM 回答
    # ------------------------------------------------------------------

    def _vector_route_intent(
        self,
        query: str,
        client: Any,
        embedding_model: str,
        top_k: int = 1,
        max_distance: float = 1.5,
    ) -> Optional[str]:
        """
        使用“向量检索”从用户问题中路由到最可能的核心实体 ID。

        步骤：
        - 调用 embeddings.create 将 query 编码为向量；
        - 在 GraphBuilder 维护的 FAISS 向量索引中执行最近邻检索；
        - 若最近邻距离超过阈值，则认为匹配不可靠，返回 None。
        """
        if not self.builder.has_vector_index():
            logger.warning("Vector intent routing requested but vector index is not available.")
            return None

        text = (query or "").strip()
        if not text:
            return None

        import time

        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = client.embeddings.create(  # type: ignore[call-arg]
                    model=embedding_model,
                    input=[text],
                )
                vec = np.asarray(resp.data[0].embedding, dtype="float32")  # type: ignore[attr-defined]
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 1.5 * (2 ** attempt)
                logger.warning(
                    "Embedding for intent routing failed on attempt %d: %s; retry in %.1fs",
                    attempt + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)
        else:
            logger.error("Embedding for intent routing permanently failed: %s", last_exc)
            return None

        results = self.builder.search_by_embedding(vec, top_k=top_k)
        if not results:
            return None

        best_entity_id, best_distance = results[0]
        logger.info(
            "Vector intent routing: best match entity_id=%s, distance=%.4f (threshold=%.4f)",
            best_entity_id,
            best_distance,
            max_distance,
        )
        if best_distance > max_distance:
            # 距离过大认为相关性不足，降级为“未匹配”
            return None

        return best_entity_id

    def _collect_local_subgraph(
        self,
        core_entity_id: str,
        max_hops: int = 2,
    ) -> Tuple[Set[str], List[Dict[str, Any]]]:
        """
        以 core_entity_id 为中心，在 MultiDiGraph 中做 1~max_hops 跳的邻居扩展。

        返回：
            - node_ids: 被纳入上下文的节点 ID 集合；
            - edges_payload: 结构化的边信息列表，用于向 LLM 提供上下文。
        """
        g = self.builder.graph
        if core_entity_id not in g:
            return set(), []

        node_ids: Set[str] = {core_entity_id}
        frontier: Set[str] = {core_entity_id}

        for _ in range(max_hops):
            next_frontier: Set[str] = set()
            for nid in frontier:
                # 出边
                for succ in g.successors(nid):
                    node_ids.add(succ)
                    next_frontier.add(succ)
                # 入边
                for pred in g.predecessors(nid):
                    node_ids.add(pred)
                    next_frontier.add(pred)
            if not next_frontier:
                break
            frontier = next_frontier

        edges_payload: List[Dict[str, Any]] = []
        for u, v, data in g.edges(node_ids, data=True):
            edges_payload.append(
                {
                    "source_id": u,
                    "target_id": v,
                    "relation_type": data.get("relation_type", ""),
                    "evidences": data.get("evidences", []),
                }
            )

        return node_ids, edges_payload

    def _build_local_context(
        self,
        node_ids: Set[str],
        edges: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        将节点与边组织成可读的文本上下文，并返回涉及的 source_metadata 列表。
        """
        g = self.builder.graph
        lines: List[str] = []
        all_sources: List[Dict[str, Any]] = []

        lines.append("【相关实体】")
        for nid in node_ids:
            data = g.nodes.get(nid, {})
            entity_type = data.get("entity_type", "")
            name = data.get("name", "")
            content = (data.get("content") or "").strip()
            sources = data.get("sources", []) or []

            all_sources.extend(s for s in sources if s and s not in all_sources)

            lines.append(f"- ID: {nid}  (type={entity_type}, name={name})")
            if content:
                lines.append(f"  描述: {content}")

        if edges:
            lines.append("")
            lines.append("【实体间关系】")
        for e in edges:
            s = e["source_id"]
            t = e["target_id"]
            rtype = e.get("relation_type", "")
            evidences = e.get("evidences", []) or []

            lines.append(f"- {s} -[{rtype}]-> {t}")
            for ev in evidences[:3]:
                # 只展示前几条证据，避免上下文过长
                lines.append(f"  evidence: {ev}")

        context = "\n".join(lines)
        return context, all_sources

    def _answer_local(
        self,
        client: Any,
        model: str,
        question: str,
        embedding_model: Optional[str] = None,
    ) -> Optional[SearchResult]:
        """
        使用“本地图搜索”模式回答问题。
        """
        embedding_model = embedding_model or model
        entity_id = self._vector_route_intent(
            query=question,
            client=client,
            embedding_model=embedding_model,
            top_k=1,
        )
        if not entity_id:
            logger.info(
                "Local search: vector routing failed to find a confident core entity; "
                "fall back to global mode if enabled."
            )
            return None

        node_ids, edges = self._collect_local_subgraph(entity_id, max_hops=2)
        if not node_ids:
            logger.info("Local search: entity_id not found in graph: %s", entity_id)
            return None

        context, sources = self._build_local_context(node_ids, edges)

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": LOCAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n图上下文：\n{context}"},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local answer LLM call failed: %s", exc, exc_info=True)
            return None

        answer = content.strip()
        if not answer:
            return None

        return SearchResult(answer=answer, mode="local", sources=sources)

    # ------------------------------------------------------------------
    # 社会搜索：社区发现 + 群落摘要 + 全局问答
    # ------------------------------------------------------------------

    def _detect_communities(self) -> List[Set[str]]:
        """
        使用 networkx 的社区发现算法对图做划分。

        优先使用 louvain_communities（若可用），否则回退到 greedy_modularity_communities。
        """
        g = self.builder.graph
        if g.number_of_nodes() == 0:
            return []

        undirected = g.to_undirected()

        # 优先尝试 Louvain（在较新版本 networkx 中提供）
        try:
            from networkx.algorithms.community import louvain_communities  # type: ignore

            communities = louvain_communities(undirected)
        except Exception:  # noqa: BLE001
            from networkx.algorithms.community import greedy_modularity_communities

            communities = greedy_modularity_communities(undirected)

        return [set(c) for c in communities]

    def _summarize_community(
        self,
        client: Any,
        model: str,
        nodes: Sequence[str],
    ) -> Optional[str]:
        """
        使用 LLM 为某个社区生成架构级摘要。
        """
        g = self.builder.graph
        lines: List[str] = []
        for nid in nodes:
            data = g.nodes.get(nid, {})
            entity_type = data.get("entity_type", "")
            name = data.get("name", "")
            content = (data.get("content") or "").strip()
            if not content:
                continue
            lines.append(f"- [{entity_type}] {name or nid}: {content}")
            if len("".join(lines)) > 4000:
                break

        if not lines:
            return None

        community_text = "\n".join(lines)

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": GLOBAL_COMMUNITY_SUMMARY_PROMPT},
                    {"role": "user", "content": community_text},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Community summary LLM call failed: %s", exc, exc_info=True)
            return None

        summary = content.strip()
        return summary or None

    def _answer_global(
        self,
        client: Any,
        model: str,
        question: str,
        max_communities: int = 8,
    ) -> Optional[SearchResult]:
        """
        使用“社会搜索 / 全局社区”模式回答宏观架构问题。
        """
        communities = self._detect_communities()
        if not communities:
            return None

        # 简单按社区大小排序，优先摘要较大的社区
        communities = sorted(communities, key=len, reverse=True)[:max_communities]

        community_summaries: List[Tuple[int, str]] = []
        all_sources: List[Dict[str, Any]] = []

        for idx, nodes in enumerate(communities):
            summary = self._summarize_community(client, model, list(nodes))
            if not summary:
                continue
            community_summaries.append((idx, summary))

            # 聚合该社区中所有实体的 source_metadata
            for nid in nodes:
                data = self.builder.graph.nodes.get(nid, {})
                sources = data.get("sources", []) or []
                all_sources.extend(s for s in sources if s and s not in all_sources)

        if not community_summaries:
            return None

        # 构造给 LLM 的“社区摘要”上下文
        lines: List[str] = []
        for idx, summary in community_summaries:
            lines.append(f"【社区 {idx} 摘要】")
            lines.append(summary)
            lines.append("")

        context = "\n".join(lines)

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": GLOBAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n相关社区摘要：\n{context}"},
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Global answer LLM call failed: %s", exc, exc_info=True)
            return None

        answer = content.strip()
        if not answer:
            return None

        return SearchResult(answer=answer, mode="global", sources=all_sources)

    # ------------------------------------------------------------------
    # 统一对外接口
    # ------------------------------------------------------------------

    def answer_question(
        self,
        client: Any,
        model: str,
        question: str,
        mode: str = "auto",
        embedding_model: Optional[str] = None,
    ) -> SearchResult:
        """
        主接口：根据问题与模式，路由到本地图搜索或社会搜索，或两者结合。

        参数:
            client: LLM 客户端（兼容 OpenAI chat.completions / embeddings 接口）。
            model: 用于推理回答的模型名称。
            question: 用户自然语言问题。
            mode: "local" | "global" | "auto"。
            embedding_model: 用于向量路由的 embedding 模型名称，默认与 model 一致。

        返回:
            SearchResult，其中 answer 为自然语言答案；
            sources 为参与回答的文档溯源元数据列表。
        """
        q = (question or "").strip()
        if not q:
            return SearchResult(answer="问题为空，无法回答。", mode="auto", sources=[])

        if mode not in {"local", "global", "auto"}:
            mode = "auto"
        if embedding_model is None:
            embedding_model = model

        # 简单启发式：包含“整体 / 架构 / 设计 / 原理”等词时优先走 global
        lower_q = q.lower()
        is_global_like = any(
            kw in q
            for kw in (
                "整体",
                "架构",
                "设计",
                "原理",
                "机制",
                "如何设计",
                "总体",
                "全局",
            )
        ) or len(lower_q) > 80

        local_result: Optional[SearchResult] = None
        global_result: Optional[SearchResult] = None

        if mode in {"local", "auto"} and not is_global_like:
            local_result = self._answer_local(client, model, q, embedding_model=embedding_model)
            if mode == "local":
                return local_result or SearchResult(
                    answer="当前图谱中无法找到与问题高度相关的实体或关系。",
                    mode="local",
                    sources=[],
                )

        if mode in {"global", "auto"} and (is_global_like or not local_result):
            global_result = self._answer_global(client, model, q)
            if mode == "global":
                return global_result or SearchResult(
                    answer="当前图谱规模或社区信息不足，无法给出可靠的全局架构回答。",
                    mode="global",
                    sources=[],
                )

        # auto 模式下的融合策略
        if local_result and global_result:
            # 简单拼接，两段回答分别标注来源模式
            combined_answer = (
                "【局部图搜索视角】\n"
                + local_result.answer
                + "\n\n【全局社区视角】\n"
                + global_result.answer
            )
            combined_sources: List[Dict[str, Any]] = []
            for s in local_result.sources + global_result.sources:
                if s and s not in combined_sources:
                    combined_sources.append(s)
            return SearchResult(answer=combined_answer, mode="hybrid", sources=combined_sources)

        if local_result:
            return local_result
        if global_result:
            return global_result

        return SearchResult(
            answer="当前图谱信息有限，无法基于现有知识回答这个问题。",
            mode=mode,
            sources=[],
        )


__all__ = ["SearchEngine", "SearchResult"]

