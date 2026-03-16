from __future__ import annotations

import logging
from dataclasses import dataclass, field
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

    新增字段：
    - confidence: 0.0~1.0，基于向量相似度 + 子图密度估算的置信度；
    - matched_entities: 检索命中的 (entity_id, distance) 列表，距离越小越相关。
    """

    answer: str
    mode: str  # "local" | "global" | "hybrid"
    sources: List[Dict[str, Any]]
    confidence: float = 0.0
    matched_entities: List[Tuple[str, float]] = field(default_factory=list)


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
        向后兼容接口：返回最匹配的单个实体 ID（内部委托给 _vector_route_intent_multi）。

        如需多候选检索请直接调用 _vector_route_intent_multi。
        """
        results = self._vector_route_intent_multi(
            query=query,
            client=client,
            embedding_model=embedding_model,
            top_k=top_k,
            max_distance=max_distance,
        )
        if not results:
            return None
        best_entity_id, best_distance = results[0]
        logger.info(
            "Vector intent routing (compat): best match entity_id=%s, distance=%.4f",
            best_entity_id,
            best_distance,
        )
        return best_entity_id

    def _vector_route_intent_multi(
        self,
        query: str,
        client: Any,
        embedding_model: str,
        top_k: int = 3,
        max_distance: float = 1.5,
    ) -> List[Tuple[str, float]]:
        """
        使用"向量检索"从用户问题中路由到最可能的多个核心实体。

        步骤：
        - 调用 embeddings.create 将 query 编码为向量；
        - 在 GraphBuilder 维护的 FAISS 向量索引中执行 top_k 最近邻检索；
        - 过滤掉距离超过阈值的候选，返回 (entity_id, distance) 列表。

        返回列表按距离从小到大排序（越靠前越相关）。
        """
        if not self.builder.has_vector_index():
            logger.warning("Vector intent routing requested but vector index is not available.")
            return []

        text = (query or "").strip()
        if not text:
            return []

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
                    "Embedding for multi-intent routing failed on attempt %d: %s; retry in %.1fs",
                    attempt + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)
        else:
            logger.error("Embedding for multi-intent routing permanently failed: %s", last_exc)
            return []

        results = self.builder.search_by_embedding(vec, top_k=top_k)
        candidates = [(eid, dist) for eid, dist in results if dist <= max_distance]
        logger.info(
            "Vector multi-intent routing: found %d/%d candidates within distance %.2f",
            len(candidates),
            len(results),
            max_distance,
        )
        return candidates

    def _collect_multi_entity_subgraph(
        self,
        candidates: List[Tuple[str, float]],
        max_hops: int = 2,
        max_nodes: int = 80,
    ) -> Tuple[Set[str], List[Dict[str, Any]], Dict[str, float]]:
        """
        合并多个候选实体的子图，返回节点集合、边列表和每个节点的综合得分。

        综合得分 = 相似度分数（1/(1+distance)）× (1 + 图中心性)，
        用于上下文中节点的重排序，使最相关的实体优先被 LLM 看到。
        若合并后节点数超过 max_nodes，则按得分截断。
        """
        g = self.builder.graph

        # 预计算度中心性作为图重要性权重（归一化到 0~1）
        try:
            centrality: Dict[str, float] = nx.degree_centrality(g)
        except Exception:  # noqa: BLE001
            centrality = {}

        entity_scores: Dict[str, float] = {}
        all_node_ids: Set[str] = set()
        edge_set: Set[Tuple[str, str, str]] = set()
        all_edges: List[Dict[str, Any]] = []

        for eid, dist in candidates:
            sim_score = 1.0 / (1.0 + dist)
            node_ids, edges = self._collect_local_subgraph(eid, max_hops=max_hops)

            for nid in node_ids:
                node_centrality = centrality.get(nid, 0.0)
                combined_score = sim_score * (1.0 + node_centrality)
                if nid not in entity_scores or combined_score > entity_scores[nid]:
                    entity_scores[nid] = combined_score

            all_node_ids.update(node_ids)

            for e in edges:
                edge_key = (e["source_id"], e["target_id"], e.get("relation_type", ""))
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    all_edges.append(e)

        # 节点过多时按综合得分截断，保留最相关的节点
        if len(all_node_ids) > max_nodes:
            sorted_nodes = sorted(entity_scores.items(), key=lambda x: x[1], reverse=True)
            keep_nodes = {nid for nid, _ in sorted_nodes[:max_nodes]}
            all_node_ids = keep_nodes
            all_edges = [
                e for e in all_edges
                if e["source_id"] in keep_nodes and e["target_id"] in keep_nodes
            ]

        logger.info(
            "Multi-entity subgraph: %d candidates → %d nodes, %d edges",
            len(candidates),
            len(all_node_ids),
            len(all_edges),
        )
        return all_node_ids, all_edges, entity_scores

    def _build_ranked_context(
        self,
        node_ids: Set[str],
        edges: List[Dict[str, Any]],
        node_scores: Dict[str, float],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        将节点与边组织成按综合得分（相似度 × 中心性）排序的文本上下文。

        节点按得分从高到低排列，使 LLM 优先看到最相关的实体。
        """
        g = self.builder.graph
        lines: List[str] = []
        all_sources: List[Dict[str, Any]] = []

        sorted_nodes = sorted(node_ids, key=lambda n: node_scores.get(n, 0.0), reverse=True)

        lines.append("【相关实体（按相关性得分排序）】")
        for nid in sorted_nodes:
            data = g.nodes.get(nid, {})
            entity_type = data.get("entity_type", "")
            name = data.get("name", "")
            content = (data.get("content") or "").strip()
            sources = data.get("sources", []) or []
            score = node_scores.get(nid, 0.0)

            all_sources.extend(s for s in sources if s and s not in all_sources)

            lines.append(f"- ID: {nid}  (type={entity_type}, name={name}, score={score:.3f})")
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
                lines.append(f"  evidence: {ev}")

        context = "\n".join(lines)
        return context, all_sources

    def _compute_confidence(
        self,
        candidates: List[Tuple[str, float]],
        node_ids: Set[str],
        edges: List[Dict[str, Any]],
    ) -> float:
        """
        基于以下因素计算搜索置信度（0.0~1.0）：

        - 候选实体的平均相似度得分（sim_score = 1/(1+distance)）；
        - 是否存在高置信核心实体（distance < 0.5）；
        - 子图密度（edge_count / node_count）。

        各因素权重：相似度 50%，高置信奖励 30%，子图密度 20%。
        """
        if not candidates:
            return 0.0

        avg_sim = sum(1.0 / (1.0 + d) for _, d in candidates) / len(candidates)
        has_close_match = any(d < 0.5 for _, d in candidates)
        density = len(edges) / max(len(node_ids), 1)
        density_score = min(density / 3.0, 1.0)

        confidence = (
            avg_sim * 0.5
            + (0.3 if has_close_match else 0.0)
            + density_score * 0.2
        )
        return min(round(confidence, 4), 1.0)

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

    def _keyword_fallback_candidates(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        关键词回退检索：当向量索引不可用或向量路由无结果时，通过关键词匹配
        在图谱实体的 name 和 content 字段中检索最相关的实体。

        匹配策略：
        - 将查询文本拆分为 token（英文单词 + 中文词，长度≥2）；
        - name/entity_id 中的命中权重 = 3，content 中的命中权重 = 1；
        - 以加权命中分数的负值作为伪"距离"（分数越高，距离越小）；
        - 返回 (entity_id, pseudo_distance) 列表，距离越小越相关。
        """
        import re

        g = self.builder.graph
        if not g.nodes:
            return []

        # 提取查询中的关键词
        tokens: List[str] = []
        # 英文词（含驼峰词整体保留）
        for word in re.findall(r"[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*", query):
            tokens.append(word.lower())
        # 数字+字母组合（如 Float64、Int32）
        for token in re.findall(r"[A-Za-z]+\d+", query):
            tokens.append(token.lower())
        # 中文关键词 —— 对每段连续中文字符做 2-gram 滑动窗口
        _stop_chars = set("的了是在有和与对从通过")
        for char_seq in re.findall(r"[\u4e00-\u9fff]+", query):
            # 取所有相邻 2 字组合（共 len-1 个）
            for i in range(len(char_seq) - 1):
                chunk = char_seq[i : i + 2]
                if not any(c in _stop_chars for c in chunk):
                    tokens.append(chunk)

        # 去重
        tokens = list(dict.fromkeys(tokens))

        if not tokens:
            return []

        scored: List[Tuple[str, float]] = []
        for nid, data in g.nodes(data=True):
            name = (data.get("name") or "").lower()
            content = (data.get("content") or "").lower()
            entity_id_lower = nid.lower()
            name_haystack = f"{entity_id_lower} {name}"

            # 名称/ID 命中权重 3，内容命中权重 1
            name_hits = sum(3 for tok in tokens if tok in name_haystack)
            content_hits = sum(1 for tok in tokens if tok in content)
            total_score = name_hits + content_hits

            if total_score > 0:
                scored.append((nid, total_score))

        # 按加权得分降序，取前 top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            return []
        max_score = scored[0][1]
        candidates = [
            (nid, float(max_score - score + 0.01))
            for nid, score in scored[:top_k]
        ]
        logger.info(
            "Keyword fallback: found %d candidates (top weighted score=%.1f) for query: %s",
            len(candidates),
            max_score,
            query[:60],
        )
        return candidates

    def _answer_local(
        self,
        client: Any,
        model: str,
        question: str,
        embedding_model: Optional[str] = None,
        top_k: int = 3,
    ) -> Optional[SearchResult]:
        """
        使用"本地图搜索"模式回答问题（优化版：多候选实体 + 融合子图 + 重排序）。

        优化点：
        1. 多候选实体检索（top_k=3~5），避免只取最近邻时遗漏相关实体；
        2. 多实体子图合并，融合多个相关实体的 1~2 跳邻居；
        3. 基于相似度 × 图中心性的综合得分对上下文节点重排序；
        4. 计算并返回置信度评分；
        5. 当向量索引不可用时，自动回退到关键词匹配检索。
        """
        embedding_model = embedding_model or model

        candidates = self._vector_route_intent_multi(
            query=question,
            client=client,
            embedding_model=embedding_model,
            top_k=top_k,
        )
        if not candidates:
            logger.info(
                "Local search: vector routing found no confident candidates; "
                "trying keyword fallback."
            )
            candidates = self._keyword_fallback_candidates(question, top_k=top_k)

        if not candidates:
            logger.info(
                "Local search: keyword fallback also found no candidates; "
                "will fall back to global mode if enabled."
            )
            return None

        node_ids, edges, node_scores = self._collect_multi_entity_subgraph(candidates)
        if not node_ids:
            logger.info("Local search: subgraph is empty for candidates: %s", candidates)
            return None

        context, sources = self._build_ranked_context(node_ids, edges, node_scores)
        confidence = self._compute_confidence(candidates, node_ids, edges)

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": LOCAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n图上下文：\n{context}"},
                ],
                temperature=0.2,
            )
            content_str = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local answer LLM call failed: %s", exc, exc_info=True)
            return None

        answer = content_str.strip()
        if not answer:
            return None

        return SearchResult(
            answer=answer,
            mode="local",
            sources=sources,
            confidence=confidence,
            matched_entities=candidates,
        )


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

        return SearchResult(answer=answer, mode="global", sources=all_sources, confidence=0.5)

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

