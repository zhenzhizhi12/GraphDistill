from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np

import re as _re

from .graph_builder import GraphBuilder

logger = logging.getLogger(__name__)

# 统一的"不确定"检测正则：覆盖 LLM 常见的信息不足表述
UNCERTAIN_RE = _re.compile(
    r"不确定|无法确定|未包含.*信息|没有包含.*信息|缺少.*信息|未提供.*信息"
    r"|没有.*相关信息|缺乏.*信息|信息不足|无法给出|上下文中未提供"
    r"|未提供具体.*描述|没有足够.*信息|无法从.*判断|无法回答"
    r"|未明确说明|未在.*中提及|未涉及|无从得知"
)

LOCAL_ANSWER_PROMPT = """
你是一个基于“技术架构知识图谱”的问答助手。

【提供给你的图上下文】
- 若干实体节点，每个包括：entity_id, entity_type, name, content, sources；
- 若干实体之间的关系，每条关系包括：source_id, target_id, relation_type, evidences；
- 可能包含【相关文档目录】：列出了与查询实体关联的文档文件路径，这些路径来自索引/目录页的 DOCUMENTED_AT 关系。

【任务】
- 仅基于这些上下文，回答用户提出的技术细节问题；
- 尽量引用上下文中的关键术语与结构，而不要自己发明新概念；
- 只要上下文中有任何相关信息，就尽量基于已有内容给出有价值的技术参考，不必因信息不完整就说"不确定"；
  只有当上下文完全没有提及相关内容时，才简短说明"当前图谱信息不涉及此问题"；
- 如果上下文中提供了【补充文档内容】，优先参考这些来自原始文档的详细内容来丰富你的回答。

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
    doc_references: List[Dict[str, str]] = field(default_factory=list)


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
    # 文档目录信息收集：通过 DOCUMENTED_AT 关系发现关联文档
    # ------------------------------------------------------------------

    def _collect_doc_directory_info(
        self,
        node_ids: Set[str],
        focus_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        遍历搜索子图中的实体，通过 DOCUMENTED_AT 关系找到关联的 File 实体，
        提取文档路径信息，返回去重后的文档引用列表。

        返回：
            [{"concept": "concept_name", "doc_path": "relative/path.md", "entity_id": "file:..."}, ...]
        """
        g = self.builder.graph
        doc_refs: List[Dict[str, str]] = []
        seen_file_ids: Set[str] = set()

        # 收集需要检查的节点：原始节点集 + BELONGS_TO 父节点（向上追溯1层）
        extended_ids: Set[str] = set(node_ids)
        for nid in node_ids:
            if nid not in g:
                continue
            for _, target, edata in g.out_edges(nid, data=True):
                if edata.get("relation_type") == "BELONGS_TO":
                    extended_ids.add(target)
            for source, _, edata in g.in_edges(nid, data=True):
                if edata.get("relation_type") == "CONTAINS":
                    extended_ids.add(source)

        # 名称匹配：查找与焦点实体同名的 Concept 节点
        # 解决 class:std_time_timezone 没有 BELONGS_TO 但同名的
        # concept:timezone 拥有 DOCUMENTED_AT 的问题
        # 仅对焦点实体（候选实体）做名称查找，避免子图80个节点全部匹配导致无关doc_ref过多
        name_lookup_ids = focus_ids if focus_ids is not None else node_ids
        entity_names: Set[str] = set()
        for nid in name_lookup_ids:
            name = (g.nodes.get(nid, {}).get("name") or "").lower()
            if name and len(name) >= 3:
                entity_names.add(name)
        if entity_names:
            for nid, ndata in g.nodes(data=True):
                if nid in extended_ids:
                    continue
                if ndata.get("entity_type") in ("Concept", "Module"):
                    cname = (ndata.get("name") or "").lower()
                    if cname in entity_names:
                        extended_ids.add(nid)

        for nid in extended_ids:
            if nid not in g:
                continue
            # 检查该实体的出边中是否有 DOCUMENTED_AT
            for _, target, data in g.out_edges(nid, data=True):
                if data.get("relation_type") == "DOCUMENTED_AT":
                    if target in seen_file_ids:
                        continue
                    seen_file_ids.add(target)
                    target_data = g.nodes.get(target, {})
                    doc_path = target_data.get("name", "")
                    concept_name = g.nodes.get(nid, {}).get("name", nid)
                    doc_refs.append({
                        "concept": concept_name,
                        "doc_path": doc_path,
                        "entity_id": target,
                    })

            # 也检查入边：如果当前节点是 File 类型，找到指向它的 Concept
            node_data = g.nodes.get(nid, {})
            if node_data.get("entity_type") == "File" and nid not in seen_file_ids:
                seen_file_ids.add(nid)
                doc_path = node_data.get("name", "")
                # 找到指向此 File 的 Concept
                concepts = []
                for pred in g.predecessors(nid):
                    for _, _, edata in g.edges(pred, data=True):
                        if edata.get("relation_type") == "DOCUMENTED_AT":
                            concepts.append(g.nodes.get(pred, {}).get("name", pred))
                doc_refs.append({
                    "concept": ", ".join(concepts[:3]) if concepts else "",
                    "doc_path": doc_path,
                    "entity_id": nid,
                })

        return doc_refs

    def _resolve_doc_paths(
        self,
        doc_refs: List[Dict[str, str]],
        sources: List[Dict[str, Any]],
    ) -> List[Path]:
        """
        将文档引用中的相对路径解析为本地文件系统的绝对路径。

        通过 sources 中的 file_path 推断仓库根目录和子目录位置。
        """
        if not doc_refs or not sources:
            return []

        # 从 sources 推断可能的文档根目录
        candidate_roots: List[Path] = []
        for src in sources:
            fp = src.get("file_path", "")
            if not fp:
                continue
            p = Path(fp)
            # 向上找到 temp_repos 下的仓库根目录
            for parent in p.parents:
                if parent.parent.name == "temp_repos" or parent.name == "temp_repos":
                    candidate_roots.append(parent)
                    break
                # 也尝试匹配已知的子目录结构
                for known_subdir in ("std/doc/libs", "doc", "api", "zh-cn/application-dev"):
                    subdir_path = parent / known_subdir
                    if subdir_path.exists():
                        candidate_roots.append(subdir_path)

        # 去重
        candidate_roots = list(dict.fromkeys(candidate_roots))

        resolved: List[Path] = []
        for ref in doc_refs:
            raw_path = ref.get("doc_path", "")
            if not raw_path:
                continue
            # 清理相对路径前缀
            clean = raw_path.lstrip("./")
            for root in candidate_roots:
                full = root / clean
                if full.exists():
                    resolved.append(full)
                    break
                # 也尝试在子目录中查找
                for sub in root.rglob(Path(clean).name):
                    if sub.is_file():
                        resolved.append(sub)
                        break

        return resolved

    def _load_supplementary_content(
        self,
        doc_paths: List[Path],
        max_files: int = 3,
        max_chars_per_file: int = 2000,
        focus_keywords: Optional[List[str]] = None,
    ) -> str:
        """
        从文档文件中加载补充内容，用于增强 LLM 回答。

        当 focus_keywords 非空时，对大文件采用"关键词段落提取"策略：
        以 Markdown 标题（# / ## / ###）为边界分段，优先选择包含关键词的段落，
        避免简单截头导致遗漏文件中后半部分的关键信息。

        限制：最多读取 max_files 个文件，每个文件最多 max_chars_per_file 字符。
        """
        lines: List[str] = []
        loaded = 0
        seen_paths: Set[Path] = set()
        kw_lower = [k.lower() for k in (focus_keywords or [])]

        for doc_path in doc_paths:
            if loaded >= max_files:
                break
            resolved = doc_path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            if not doc_path.exists() or not doc_path.is_file():
                continue
            try:
                text = doc_path.read_text(encoding="utf-8", errors="ignore")
                if not text.strip():
                    continue

                # 如果文件不大或无 focus_keywords，走原来的截头逻辑
                if len(text) <= max_chars_per_file or not kw_lower:
                    snippet = text[:max_chars_per_file]
                    if len(text) > max_chars_per_file:
                        snippet += "\n...（截断）"
                else:
                    # 按 Markdown 标题切分段落，提取包含关键词的段落
                    snippet = self._extract_keyword_sections(
                        text, kw_lower, max_chars_per_file,
                    )

                lines.append(f"--- 文档: {doc_path.name} ---")
                lines.append(snippet)
                lines.append("")
                loaded += 1
            except Exception:  # noqa: BLE001
                continue

        if not lines:
            return ""
        return "\n【补充文档内容】\n" + "\n".join(lines)

    @staticmethod
    def _extract_keyword_sections(
        text: str,
        keywords: List[str],
        max_chars: int,
    ) -> str:
        """按 Markdown 标题切分段落，优先提取包含关键词的段落。"""
        sections: List[Tuple[str, bool]] = []
        current_lines: List[str] = []
        for line in text.split("\n"):
            if line.startswith("#") and current_lines:
                block = "\n".join(current_lines)
                block_lower = block.lower()
                has_kw = any(kw in block_lower for kw in keywords)
                sections.append((block, has_kw))
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            block = "\n".join(current_lines)
            block_lower = block.lower()
            has_kw = any(kw in block_lower for kw in keywords)
            sections.append((block, has_kw))

        # 先选包含关键词的段落，再按原始顺序填充其余段落
        result_parts: List[str] = []
        used = 0
        for block, has_kw in sections:
            if has_kw and used + len(block) <= max_chars:
                result_parts.append(block)
                used += len(block)
        # 如果关键词段落不够，补充非关键词段落（保持顺序）
        if used < max_chars // 2:
            for block, has_kw in sections:
                if not has_kw and used + len(block) <= max_chars:
                    result_parts.append(block)
                    used += len(block)
        if used < len(text):
            result_parts.append("\n...（关键词定向截取）")
        return "\n".join(result_parts)

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
        doc_refs: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        将节点与边组织成按综合得分（相似度 × 中心性）排序的文本上下文。

        节点按得分从高到低排列，使 LLM 优先看到最相关的实体。
        如果 doc_refs 非空，会附加【相关文档目录】段落。
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

        # 附加文档目录信息
        if doc_refs:
            lines.append("")
            lines.append("【相关文档目录】")
            for ref in doc_refs:
                concept = ref.get("concept", "")
                doc_path = ref.get("doc_path", "")
                if concept and doc_path:
                    lines.append(f"- 概念「{concept}」的详细文档: {doc_path}")
                elif doc_path:
                    lines.append(f"- 相关文档: {doc_path}")

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
            # 名称精确匹配奖励：若 name 完全等于某 token，额外 +5
            # 确保概念/类节点（name="HashSet"）优先于名称只包含 token 的函数节点
            exact_name_bonus = sum(5 for tok in tokens if name == tok)
            total_score = name_hits + content_hits + exact_name_bonus

            if total_score > 0:
                scored.append((nid, total_score))

        # 按加权得分降序
        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            return []

        # ── 主题多样性保证 ──────────────────────────────────────────────
        # 提取查询中的英文关键词作为"主题"标签（如 hashset、treeset）。
        # 确保每个主题至少有一个代表进入最终候选列表，
        # 防止某一主题的实体因得分稍高而独占全部 top_k 名额。
        topic_tokens = [t for t in tokens if re.fullmatch(r"[a-z][a-z0-9]*", t) and len(t) >= 4]

        selected: List[Tuple[str, float]] = []
        selected_ids: Set[str] = set()

        if len(topic_tokens) > 1:
            # 多主题：为每个主题选最多 min_per_topic 个代表
            # 确保每个关键词实体至少有足够的节点覆盖，避免信息不足导致"不确定"
            min_per_topic = 3
            for topic in topic_tokens:
                topic_candidates: List[Tuple[str, float, float]] = []
                for nid, score in scored:
                    if nid in selected_ids:
                        continue
                    nid_lower = nid.lower()
                    node_name = (g.nodes.get(nid, {}).get("name") or "").lower()
                    if topic in nid_lower or topic == node_name:
                        # 计算实体丰富度：图连接数（权重高）+ 内容长度
                        # 高连接度节点（如 class）能展开出更丰富的子图
                        # 对 hub 类型（Class/Struct/Concept）额外加权，
                        # 它们才是主题的核心代表，而非某个方法/代码片段
                        node_data = g.nodes.get(nid, {})
                        etype = (node_data.get("entity_type") or "").lower()
                        hub_bonus = 500 if etype in ("class", "struct", "concept", "interface", "module") else 0
                        richness = hub_bonus + g.degree(nid) * 10 + len(node_data.get("content") or "")
                        topic_candidates.append((nid, score, richness))
                # 按丰富度排序，选前 min_per_topic 个
                topic_candidates.sort(key=lambda x: x[2], reverse=True)
                for nid, score, _ in topic_candidates[:min_per_topic]:
                    if nid not in selected_ids:
                        selected.append((nid, score))
                        selected_ids.add(nid)
            # 再用剩余名额按得分填充
            effective_cap = max(top_k, len(topic_tokens) * min_per_topic + 2)
            for nid, score in scored:
                if len(selected) >= effective_cap:
                    break
                if nid not in selected_ids:
                    selected.append((nid, score))
                    selected_ids.add(nid)
        else:
            # 单主题或无显式英文关键词：直接按得分取 top_k
            selected = scored[:top_k]

        max_score = scored[0][1]
        candidates = [
            (nid, float(max_score - score + 0.01))
            for nid, score in selected
        ]
        logger.info(
            "Keyword fallback: found %d candidates (top weighted score=%.1f, topics=%s) for query: %s",
            len(candidates),
            max_score,
            topic_tokens,
            query[:60],
        )
        return candidates

    def _merge_vector_keyword_candidates(
        self,
        vector_candidates: List[Tuple[str, float]],
        keyword_candidates: List[Tuple[str, float]],
        max_total: int = 6,
    ) -> List[Tuple[str, float]]:
        """
        合并向量路由和关键词匹配的候选实体列表。

        解决的问题：当用户查询涉及多个主题（如 "HashSet 和 TreeSet 的区别"）时，
        单一 embedding 向量可能只匹配到其中一个主题的实体。通过关键词补充，
        确保查询中明确提到的实体不会因 embedding 混合效应而被遗漏。

        策略：
        - 向量候选优先保留（距离值可直接使用）；
        - 关键词候选仅补充向量未覆盖的实体（去重）；
        - 关键词候选的伪距离设为略大于向量最大距离，保持排序合理；
        - 总数上限 max_total，防止子图过度膨胀。
        """
        if not vector_candidates and not keyword_candidates:
            return []

        merged = list(vector_candidates)
        existing_ids = {eid for eid, _ in merged}

        # 为关键词候选分配合理的伪距离
        if vector_candidates:
            max_vec_dist = max(d for _, d in vector_candidates)
            kw_base_dist = max_vec_dist + 0.05
        else:
            kw_base_dist = 1.0

        added = 0
        for i, (eid, _kw_dist) in enumerate(keyword_candidates):
            if eid not in existing_ids:
                merged.append((eid, kw_base_dist + i * 0.01))
                existing_ids.add(eid)
                added += 1

        if added > 0:
            logger.info(
                "Candidate merge: %d vector + %d keyword-supplement = %d total (cap %d)",
                len(vector_candidates),
                added,
                len(merged),
                max_total,
            )

        return merged[:max_total]

    # ------------------------------------------------------------------
    # 多主题查询拆分：问题涉及 2+ 个实体时，分别搜索再合并上下文
    # ------------------------------------------------------------------

    def _detect_query_topics(self, question: str) -> List[str]:
        """
        检测问题中提到的多个独立实体主题（PascalCase 标识符）。

        仅当检测到 2+ 个不同的实体名时，调用方才启用多主题拆分策略。
        返回去重后的实体名列表。
        """
        entities = _re.findall(r"[A-Z][a-zA-Z0-9]{2,}", question)
        _stop_words = {"Type", "How", "What", "Each", "All", "The", "This", "None", "Some"}
        seen: Set[str] = set()
        topics: List[str] = []
        for e in entities:
            e_lower = e.lower()
            if e_lower not in seen and e not in _stop_words:
                seen.add(e_lower)
                topics.append(e)
        return topics

    def _answer_local_multi_topic(
        self,
        client: Any,
        model: str,
        question: str,
        topics: List[str],
        embedding_model: str,
        top_k: int = 3,
    ) -> Optional[SearchResult]:
        """
        多主题拆分策略：当问题涉及 2+ 个实体（如 "ArrayList 和 LinkedList 的区别"），
        对每个主题独立进行候选检索和子图收集，保证每个主题获得充分的上下文节点，
        然后合并所有上下文，使用一次 LLM 调用统一回答原始问题。

        解决的问题：
        单次 embedding 检索会将多主题查询编码为一个"混合"向量，导致部分主题
        的实体被遗漏或在 80 节点上限中被挤出。拆分后每个主题独立占有节点预算。
        """
        all_node_ids: Set[str] = set()
        all_edges: List[Dict[str, Any]] = []
        all_node_scores: Dict[str, float] = {}
        all_doc_refs: List[Dict[str, str]] = []
        all_candidates: List[Tuple[str, float]] = []
        edge_set: Set[Tuple[str, str, str]] = set()
        per_topic_max_nodes = max(40, 80 // len(topics))

        logger.info(
            "Multi-topic decomposition: %d topics %s, %d nodes/topic budget",
            len(topics), topics, per_topic_max_nodes,
        )

        for topic in topics:
            # 对每个主题做独立的候选检索
            vec_cands = self._vector_route_intent_multi(
                query=topic, client=client,
                embedding_model=embedding_model, top_k=top_k,
            )
            kw_cands = self._keyword_fallback_candidates(topic, top_k=top_k)
            cands = self._merge_vector_keyword_candidates(
                vec_cands, kw_cands, max_total=max(top_k, 4),
            )
            if not cands:
                continue

            # 收集该主题的独立子图（使用独立节点预算）
            node_ids, edges, scores = self._collect_multi_entity_subgraph(
                cands, max_nodes=per_topic_max_nodes,
            )
            all_node_ids |= node_ids
            for nid, s in scores.items():
                if nid not in all_node_scores or s > all_node_scores[nid]:
                    all_node_scores[nid] = s
            all_candidates.extend(cands)

            for e in edges:
                ekey = (e["source_id"], e["target_id"], e.get("relation_type", ""))
                if ekey not in edge_set:
                    edge_set.add(ekey)
                    all_edges.append(e)

            focus = {eid for eid, _ in cands}
            refs = self._collect_doc_directory_info(node_ids, focus_ids=focus)
            all_doc_refs.extend(refs)

        if not all_node_ids:
            return None

        # 候选实体去重
        seen_cid: Set[str] = set()
        deduped_candidates: List[Tuple[str, float]] = []
        for eid, d in all_candidates:
            if eid not in seen_cid:
                seen_cid.add(eid)
                deduped_candidates.append((eid, d))

        # doc_refs 去重
        seen_doc: Set[Tuple[str, str]] = set()
        deduped_refs: List[Dict[str, str]] = []
        for ref in all_doc_refs:
            key = (ref.get("concept", ""), ref.get("doc_path", ""))
            if key not in seen_doc:
                seen_doc.add(key)
                deduped_refs.append(ref)

        # 构建上下文
        context, sources = self._build_ranked_context(
            all_node_ids, all_edges, all_node_scores, doc_refs=deduped_refs,
        )
        confidence = self._compute_confidence(deduped_candidates, all_node_ids, all_edges)

        # 按问题相关度排序 doc_refs 并加载补充文档
        q_keywords = [w.lower() for w in _re.findall(
            r"[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*", question,
        ) if len(w) >= 3]
        if deduped_refs and q_keywords:
            def _rel(ref: Dict[str, str]) -> int:
                c = ref.get("concept", "").lower()
                p = ref.get("doc_path", "").lower()
                s = 0
                for kw in q_keywords:
                    if kw in c:
                        s += 10
                    if kw in p:
                        s += 5
                return -s
            deduped_refs.sort(key=_rel)

        supplementary = ""
        resolved = self._resolve_doc_paths(deduped_refs, sources)
        if resolved:
            supplementary = self._load_supplementary_content(
                resolved, max_files=min(len(topics) * 2, 6),
                focus_keywords=[t.lower() for t in topics],
            )
            if supplementary:
                logger.info(
                    "Multi-topic: loaded supplementary from %d doc files",
                    min(len(resolved), 6),
                )

        full_context = context + supplementary

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": LOCAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n图上下文：\n{full_context}"},
                ],
                temperature=0.2,
            )
            content_str = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Multi-topic LLM call failed: %s", exc, exc_info=True)
            return None

        answer = content_str.strip()
        if not answer:
            return None

        # 不确定检测 + 重试
        if UNCERTAIN_RE.search(answer):
            logger.info("Multi-topic: uncertain answer, attempting doc enrichment retry...")
            enriched = self._retry_with_doc_enrichment(
                question=question,
                original_context=full_context,
                candidates=deduped_candidates,
                node_ids=all_node_ids,
                sources=sources,
                client=client,
                model=model,
            )
            if enriched and not UNCERTAIN_RE.search(enriched):
                logger.info("Multi-topic: enrichment retry succeeded.")
                answer = enriched
            elif enriched:
                logger.info("Multi-topic: enrichment retry still uncertain, keeping enriched.")
                answer = enriched

        logger.info(
            "Multi-topic answer: %d nodes, %d edges across %d topics",
            len(all_node_ids), len(all_edges), len(topics),
        )

        return SearchResult(
            answer=answer,
            mode="local",
            sources=sources,
            confidence=confidence,
            matched_entities=deduped_candidates,
            doc_references=deduped_refs,
        )

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
        5. 当向量索引不可用时，自动回退到关键词匹配检索；
        6. 多主题查询自动拆分：涉及 2+ 实体时分别搜索再合并。
        """
        embedding_model = embedding_model or model

        # ── 多主题检测：当问题涉及 2+ 个实体时，使用拆分-搜索-合并策略 ──────
        topics = self._detect_query_topics(question)
        if len(topics) >= 2:
            multi_result = self._answer_local_multi_topic(
                client, model, question, topics, embedding_model, top_k,
            )
            if multi_result is not None:
                return multi_result
            logger.info("Multi-topic decomposition returned no result, falling back to normal path.")

        # Phase 1: 向量路由 —— 基于 embedding 相似度检索候选实体
        vector_candidates = self._vector_route_intent_multi(
            query=question,
            client=client,
            embedding_model=embedding_model,
            top_k=top_k,
        )

        # Phase 2: 关键词补充 —— 始终运行，确保查询中明确提到的实体不被遗漏
        # （解决多主题查询时 embedding 混合导致部分主题丢失的问题）
        keyword_candidates = self._keyword_fallback_candidates(question, top_k=top_k)

        # Phase 3: 合并去重，向量优先，关键词补充缺失项
        candidates = self._merge_vector_keyword_candidates(
            vector_candidates, keyword_candidates, max_total=max(top_k * 2, 8),
        )

        if not candidates:
            logger.info(
                "Local search: both vector and keyword found no candidates; "
                "will fall back to global mode if enabled."
            )
            return None

        node_ids, edges, node_scores = self._collect_multi_entity_subgraph(candidates)
        if not node_ids:
            logger.info("Local search: subgraph is empty for candidates: %s", candidates)
            return None

        # 收集文档目录信息（DOCUMENTED_AT 关系）
        candidate_focus_ids = {eid for eid, _ in candidates}
        doc_refs = self._collect_doc_directory_info(node_ids, focus_ids=candidate_focus_ids)
        if doc_refs:
            logger.info(
                "Local search: found %d document references via DOCUMENTED_AT",
                len(doc_refs),
            )

        context, sources = self._build_ranked_context(node_ids, edges, node_scores, doc_refs=doc_refs)
        confidence = self._compute_confidence(candidates, node_ids, edges)

        # 提取问题中的英文关键词，用于文档排序和关键词段落提取
        q_keywords = [w.lower() for w in _re.findall(r"[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*", question) if len(w) >= 3]

        # 按问题相关度排序 doc_refs，让最相关的文档优先加载
        if doc_refs:
            q_lower = question.lower()
            def _doc_ref_relevance(ref):
                concept = ref.get("concept", "").lower()
                doc_path = ref.get("doc_path", "").lower()
                score = 0
                for kw in q_keywords:
                    if kw in concept:
                        score += 10
                    if kw in doc_path:
                        score += 5
                return -score
            doc_refs.sort(key=_doc_ref_relevance)

        # 尝试加载补充文档内容（从本地 temp_repos 加载关联文档原文）
        supplementary = ""
        resolved_doc_paths = self._resolve_doc_paths(doc_refs, sources)
        if resolved_doc_paths:
            supplementary = self._load_supplementary_content(
                resolved_doc_paths, focus_keywords=q_keywords,
            )
            if supplementary:
                logger.info(
                    "Local search: loaded supplementary content from %d doc files",
                    min(len(resolved_doc_paths), 3),
                )

        full_context = context + supplementary

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": LOCAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n图上下文：\n{full_context}"},
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

        # 检测回答中的不确定/信息不足标记：当 LLM 因上下文不足无法回答时，
        # 主动扩大文档搜索范围并重试
        if UNCERTAIN_RE.search(answer):
            logger.info("Uncertain answer detected, attempting doc enrichment retry...")
            enriched = self._retry_with_doc_enrichment(
                question=question,
                original_context=full_context,
                candidates=candidates,
                node_ids=node_ids,
                sources=sources,
                client=client,
                model=model,
            )
            if enriched and not UNCERTAIN_RE.search(enriched):
                logger.info("Doc enrichment retry succeeded, replacing uncertain answer.")
                answer = enriched
            elif enriched:
                logger.info("Doc enrichment retry still uncertain, keeping enriched answer anyway.")
                answer = enriched

        return SearchResult(
            answer=answer,
            mode="local",
            sources=sources,
            confidence=confidence,
            matched_entities=candidates,
            doc_references=doc_refs,
        )

    def _retry_with_doc_enrichment(
        self,
        question: str,
        original_context: str,
        candidates: List[Tuple[str, float]],
        node_ids: Set[str],
        sources: List[Dict[str, Any]],
        client: Any,
        model: str,
    ) -> Optional[str]:
        """
        当初次回答包含"不确定"时，尝试通过扩大文档搜索范围来丰富上下文：

        1. 从问题中提取关键词；
        2. 在整个图谱中查找匹配这些关键词的所有实体（不限于当前子图）；
        3. 沿 BELONGS_TO 关系向上追溯到父概念/模块；
        4. 收集这些实体的 DOCUMENTED_AT 文档引用；
        5. 加载文档内容，用丰富的上下文重新调用 LLM。
        """
        import re

        g = self.builder.graph

        # 提取问题中的英文关键词
        keywords: List[str] = []
        for word in re.findall(r"[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*", question):
            if len(word) >= 3:
                keywords.append(word.lower())
        for token in re.findall(r"[A-Za-z]+\d+", question):
            keywords.append(token.lower())
        keywords = list(dict.fromkeys(keywords))

        if not keywords:
            return None

        # 在整个图谱中查找匹配关键词的实体（不限于子图）
        expanded_ids: Set[str] = set()
        for kw in keywords:
            for nid, data in g.nodes(data=True):
                name = (data.get("name") or "").lower()
                eid_lower = nid.lower()
                if kw in eid_lower or kw == name:
                    expanded_ids.add(nid)
                    # 沿 BELONGS_TO 向上追溯（2 层），找到父概念/模块
                    for _, target, edata in g.out_edges(nid, data=True):
                        if edata.get("relation_type") in ("BELONGS_TO",):
                            expanded_ids.add(target)
                            for _, t2, edata2 in g.out_edges(target, data=True):
                                if edata2.get("relation_type") in ("BELONGS_TO",):
                                    expanded_ids.add(t2)
                    # 也检查 CONTAINS 入边（父节点指向子节点）
                    for source, _, edata in g.in_edges(nid, data=True):
                        if edata.get("relation_type") in ("CONTAINS",):
                            expanded_ids.add(source)

        # 也从当前候选实体的 BELONGS_TO 父节点收集
        for eid, _ in candidates:
            if eid in g:
                for _, target, edata in g.out_edges(eid, data=True):
                    if edata.get("relation_type") in ("BELONGS_TO", "DOCUMENTED_AT"):
                        expanded_ids.add(target)

        # 从扩展的实体集合中收集 DOCUMENTED_AT 文档引用
        focus_ids = {eid for eid, _ in candidates}
        doc_refs = self._collect_doc_directory_info(expanded_ids | node_ids, focus_ids=focus_ids)
        if not doc_refs:
            logger.info(
                "Doc enrichment retry: no doc refs found from %d expanded entities",
                len(expanded_ids),
            )
            return None

        # 优先加载与查询关键词直接相关的文档（如 TimeZone 的 time_package_classes.md）
        def _doc_relevance(ref: Dict[str, str]) -> int:
            concept = ref.get("concept", "").lower()
            doc_path = ref.get("doc_path", "").lower()
            score = 0
            for kw in keywords:
                if kw in concept:
                    score += 10
                if kw in doc_path:
                    score += 5
            return -score  # 负数使得相关性高的排在前面

        doc_refs.sort(key=_doc_relevance)

        # 收集扩展实体的源元数据，用于解析文档路径
        extra_sources: List[Dict[str, Any]] = []
        for nid in expanded_ids:
            data = g.nodes.get(nid, {})
            for s in (data.get("sources") or []):
                if s and s not in extra_sources:
                    extra_sources.append(s)

        resolved = self._resolve_doc_paths(doc_refs, sources + extra_sources)
        if not resolved:
            logger.info("Doc enrichment retry: could not resolve any doc paths")
            return None

        supplementary = self._load_supplementary_content(
            resolved, max_files=5, max_chars_per_file=3000,
            focus_keywords=keywords,
        )
        if not supplementary:
            logger.info("Doc enrichment retry: no supplementary content loaded")
            return None

        logger.info(
            "Doc enrichment retry: loaded supplementary from %d files for: %s",
            min(len(resolved), 5),
            question[:60],
        )

        enriched_context = original_context + supplementary

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": LOCAL_ANSWER_PROMPT},
                    {"role": "user", "content": f"用户问题：{question}\n\n图上下文：\n{enriched_context}"},
                ],
                temperature=0.2,
            )
            content_str = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Doc enrichment retry LLM call failed: %s", exc)
            return None

        enriched_answer = content_str.strip()
        if not enriched_answer:
            return None

        return enriched_answer


    # ------------------------------------------------------------------
    # 全局 / 社区搜索相关辅助方法
    # ------------------------------------------------------------------

    def _detect_communities(self) -> List[Set[str]]:
        """
        基于图结构做“社区发现”，用于全局/宏观架构问答。

        当前实现策略：
        - 将内部 MultiDiGraph 投影为无向简单图（忽略边方向与多重边）；
        - 若节点数较多，优先使用 greedy_modularity_communities 做模块度最大化划分；
        - 若算法不可用或失败，则回退到 connected_components（弱连通分量）。

        返回：
            List[Set[str]]，每个集合是一簇社区中的节点 ID。
        """
        g = self.builder.graph
        if not g or g.number_of_nodes() == 0:
            logger.info("Community detection: graph is empty.")
            return []

        # 投影为无向图，便于使用社区发现算法
        undirected = nx.Graph()
        undirected.add_nodes_from(g.nodes())
        # 忽略多重边和方向，只要有边就视为连接
        for u, v in g.edges():
            undirected.add_edge(u, v)

        if undirected.number_of_edges() == 0:
            logger.info("Community detection: graph has no edges, using isolated nodes as trivial communities.")
            return [{n} for n in undirected.nodes()]

        communities: List[Set[str]] = []

        try:
            # 优先使用模块度最大化算法
            from networkx.algorithms.community import greedy_modularity_communities

            comms = greedy_modularity_communities(undirected)
            communities = [set(c) for c in comms]
            logger.info(
                "Community detection (greedy_modularity): found %d communities on %d nodes / %d edges.",
                len(communities),
                undirected.number_of_nodes(),
                undirected.number_of_edges(),
            )
        except Exception as exc:  # noqa: BLE001
            # 回退到简单的连通分量划分
            logger.warning(
                "Community detection via greedy_modularity failed (%s); "
                "falling back to connected components.",
                exc,
            )
            communities = [set(c) for c in nx.connected_components(undirected)]
            logger.info(
                "Community detection (connected_components): found %d components.",
                len(communities),
            )

        return communities

    def _summarize_community(
        self,
        client: Any,
        model: str,
        nodes: List[str],
        max_entities: int = 60,
    ) -> Optional[str]:
        """
        对单个社区生成高层次中文摘要。

        实现方式：
        - 从社区节点中采样最多 max_entities 个代表性实体；
        - 组织为结构化的文本上下文（包含 entity_id / type / name / content）；
        - 调用 LLM（GLOBAL_COMMUNITY_SUMMARY_PROMPT）生成“社区级”摘要。
        """
        g = self.builder.graph
        if not nodes:
            return None

        # 节点过多时做简单截断，避免上下文爆炸
        sampled_nodes = list(nodes)[:max_entities]
        lines: List[str] = []

        for nid in sampled_nodes:
            data = g.nodes.get(nid, {})
            entity_type = data.get("entity_type", "")
            name = data.get("name", "")
            content = (data.get("content") or "").strip()

            lines.append(f"- ID: {nid}  (type={entity_type}, name={name})")
            if content:
                # 为避免上下文过长，仅保留前若干字符
                snippet = content[:300]
                lines.append(f"  描述: {snippet}")

        context = "\n".join(lines)

        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=[
                    {"role": "system", "content": GLOBAL_COMMUNITY_SUMMARY_PROMPT},
                    {
                        "role": "user",
                        "content": f"以下是同一技术社区中的若干实体，请你为该社区生成一个高层次的架构/主题摘要：\n\n{context}",
                    },
                ],
                temperature=0.3,
            )
            content_str = response.choices[0].message.content or ""  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Community summary LLM call failed: %s", exc, exc_info=True)
            return None

        summary = content_str.strip()
        if not summary:
            return None
        return summary


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

        # 启发式判断是否为全局/宏观问题
        import re as _re
        lower_q = q.lower()
        _global_keywords = ("整体", "架构", "如何设计", "总体", "全局")
        # "原理/设计/机制" 等词在具体实体问题中也常出现（如 "HashMap 的原理"），
        # 仅当查询不含任何具体实体名称时才视为全局查询
        _soft_global_keywords = ("设计", "原理", "机制")
        has_hard_global = any(kw in q for kw in _global_keywords)
        has_soft_global = any(kw in q for kw in _soft_global_keywords)
        # 检测查询中是否包含具体的英文实体名称（首字母大写的词，如 HashMap、TreeSet）
        has_specific_entity = bool(
            _re.search(r"[A-Z][a-zA-Z0-9]{2,}", q)
        )
        is_global_like = (
            has_hard_global or (has_soft_global and not has_specific_entity)
        ) or (len(lower_q) > 80 and not has_specific_entity)

        local_result: Optional[SearchResult] = None
        global_result: Optional[SearchResult] = None

        # auto 模式：始终先尝试 local（除非纯全局问题且无具体实体）
        if mode in {"local", "auto"}:
            if not is_global_like or has_specific_entity:
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

