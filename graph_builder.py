from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Optional

import networkx as nx
import numpy as np

from pydantic_schema import DocumentGraph, Entity

try:
    import faiss  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    faiss = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class MergedEntity:
    """
    全局图谱中的实体聚合表示。

    - 以 entity_id 为主键进行去重；
    - content 采取“语义合并”策略：
      - 若新内容与旧内容不同，保留较长版本，短版本可追加到 long_content_notes 中；
    - sources 用来记录该实体在不同文档中的 source_metadata，便于跨文档溯源。
    """

    entity_id: str
    entity_type: str
    name: str
    content: str
    sources: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_entity(cls, entity: Entity, source_metadata: Dict[str, Any]) -> "MergedEntity":
        return cls(
            entity_id=entity.entity_id,
            entity_type=entity.entity_type,
            name=entity.name,
            content=entity.content,
            sources=[source_metadata] if source_metadata else [],
        )

    def merge_from(self, entity: Entity, source_metadata: Dict[str, Any]) -> None:
        """
        与新抽取的同 ID 实体进行合并。

        - 若 content 长度不同，保留较长的那一个；
        - sources 中追加新的 source_metadata（避免完全重复）。
        """
        # 内容合并：保留信息量更大的版本
        new_content = entity.content or ""
        if len(new_content) > len(self.content):
            self.content = new_content

        # 源信息合并：简单去重（基于 dict 比较）
        if source_metadata and source_metadata not in self.sources:
            self.sources.append(source_metadata)


class GraphBuilder:
    """
    负责将多个 DocumentGraph 合并为一个全局统一的知识网络。

    - 内部维护一个 networkx.MultiDiGraph 作为图论引擎；
    - 支持增量合并、去重与持久化；
    - 为“社会搜索”准备统计与导出能力。
    """

    def __init__(self) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        # 映射：entity_id -> MergedEntity
        self._entities: Dict[str, MergedEntity] = {}
        # 映射：(source_id, target_id, relation_type) -> 聚合 evidence 列表
        self._relationship_evidence: Dict[Tuple[str, str, str], List[str]] = {}
        # ---------------- 向量索引相关（Vector + Graph 双路检索） ----------------
        # FAISS 向量索引（IndexFlatL2），仅在 faiss 可用且已构建时非空
        self._vector_index: Optional["faiss.IndexFlatL2"] = None  # type: ignore[name-defined]
        # 索引位置 -> entity_id 的映射，用于从检索结果回到图节点
        self._index_to_entity_id: List[str] = []
        # entity_id -> 索引位置 的反向映射，便于增量更新（目前主要用于一次性构建）
        self._entity_id_to_index: Dict[str, int] = {}
        # 向量维度（由首次构建时的 embedding 决定）
        self._embedding_dim: Optional[int] = None
        # 采用的 embedding 模型名称（便于调试与持久化）
        self._embedding_model_name: Optional[str] = None
        # 将所有向量也以 Python 列表形式持久化，便于从 JSON 快速恢复 FAISS 索引
        self._embeddings_matrix: List[List[float]] = []

    # ---------------------------------------------------------------------
    # 增量合并逻辑
    # ---------------------------------------------------------------------

    def merge_document_graph(self, doc: DocumentGraph) -> None:
        """
        将单个 DocumentGraph 增量合并到全局图谱中。

        具备防御性：
        - 若 doc 为空或无实体/关系，安全返回；
        - 对实体与关系均做去重与内容合并。
        """
        if not doc or (not doc.entities and not doc.relationships):
            logger.info("merge_document_graph: received empty DocumentGraph; skip.")
            return

        source_meta = doc.source_metadata or {}

        # 1) 合并实体
        for entity in doc.entities:
            merged = self._entities.get(entity.entity_id)
            if merged is None:
                merged = MergedEntity.from_entity(entity, source_meta)
                self._entities[entity.entity_id] = merged

                # 在图中添加节点
                self.graph.add_node(
                    entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    content=entity.content,
                    sources=[source_meta] if source_meta else [],
                )
            else:
                # 已存在节点，执行内容与溯源合并
                merged.merge_from(entity, source_meta)
                # 同步更新图中的节点属性
                data = self.graph.nodes[entity.entity_id]
                data["content"] = merged.content
                data.setdefault("sources", [])
                if source_meta and source_meta not in data["sources"]:
                    data["sources"].append(source_meta)

        # 2) 合并关系
        for rel in doc.relationships:
            key = (rel.source_id, rel.target_id, rel.relation_type)

            # 聚合 evidence
            evidences = self._relationship_evidence.setdefault(key, [])
            if rel.evidence and rel.evidence not in evidences:
                evidences.append(rel.evidence)

            # 在图中添加/更新边（MultiDiGraph 允许多条边，但我们在属性层做去重）
            self.graph.add_edge(
                rel.source_id,
                rel.target_id,
                relation_type=rel.relation_type,
                evidences=list(evidences),
            )

    def merge_many(self, docs: Iterable[DocumentGraph]) -> None:
        """
        批量合并多个 DocumentGraph。
        """
        for doc in docs:
            self.merge_document_graph(doc)

    # ---------------------------------------------------------------------
    # 导出 / 持久化
    # ---------------------------------------------------------------------

    def to_json_dict(self) -> Dict[str, Any]:
        """
        将当前全局图谱导出为标准 JSON 友好的 dict 结构，便于持久化或下游消费。

        结构大致为：
        {
          "entities": [...],
          "relationships": [...]
        }
        """
        entities_payload: List[Dict[str, Any]] = []
        for entity_id, merged in self._entities.items():
            node_data = self.graph.nodes.get(entity_id, {})
            entities_payload.append(
                {
                    "entity_id": merged.entity_id,
                    "entity_type": merged.entity_type,
                    "name": merged.name,
                    "content": merged.content,
                    "sources": list(node_data.get("sources", merged.sources)),
                }
            )

        relationships_payload: List[Dict[str, Any]] = []
        for (src, tgt, rel_type), evidences in self._relationship_evidence.items():
            relationships_payload.append(
                {
                    "source_id": src,
                    "target_id": tgt,
                    "relation_type": rel_type,
                    "evidences": list(evidences),
                }
            )

        payload: Dict[str, Any] = {
            "entities": entities_payload,
            "relationships": relationships_payload,
        }

        # 持久化向量索引的必要元数据与原始向量
        if self._embeddings_matrix and self._index_to_entity_id and self._embedding_dim:
            payload["vector_index"] = {
                "embedding_model": self._embedding_model_name or "",
                "dimension": int(self._embedding_dim),
                "index_to_entity_id": list(self._index_to_entity_id),
                "embeddings": self._embeddings_matrix,
            }

        return payload

    def save_json(self, path: str | Path) -> None:
        """
        将当前全局图谱保存为 JSON 文件（UTF-8，ensure_ascii=False，避免中文乱码）。
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_json_dict()
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("GraphBuilder state saved to JSON: %s", p)

    def save_graphml(self, path: str | Path) -> None:
        """
        将当前 MultiDiGraph 导出为 GraphML，用于 Gephi 等工具可视化。
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # networkx 的 write_graphml 默认就是 UTF-8 编码
        nx.write_graphml(self.graph, p)
        logger.info("GraphBuilder graph saved to GraphML: %s", p)

    @classmethod
    def load_json(cls, path: str | Path) -> "GraphBuilder":
        """
        从 JSON 文件中恢复 GraphBuilder 状态，用于断点续传。

        若文件不存在或数据格式异常，则返回一个空的 GraphBuilder。
        """
        p = Path(path)
        builder = cls()

        if not p.exists():
            logger.warning("load_json: file not found, return empty GraphBuilder: %s", p)
            return builder

        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("load_json: failed to read JSON, return empty builder: %s", exc, exc_info=True)
            return builder

        entities = data.get("entities") or []
        relationships = data.get("relationships") or []

        # 恢复实体
        for item in entities:
            try:
                entity_id = item["entity_id"]
                merged = MergedEntity(
                    entity_id=entity_id,
                    entity_type=item.get("entity_type", ""),
                    name=item.get("name", ""),
                    content=item.get("content", ""),
                    sources=item.get("sources", []) or [],
                )
                builder._entities[entity_id] = merged

                builder.graph.add_node(
                    entity_id,
                    entity_type=merged.entity_type,
                    name=merged.name,
                    content=merged.content,
                    sources=list(merged.sources),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("load_json: skip invalid entity entry: %s", exc, exc_info=True)

        # 恢复关系
        for item in relationships:
            try:
                src = item["source_id"]
                tgt = item["target_id"]
                rel_type = item["relation_type"]
                evidences = item.get("evidences", []) or []

                key = (src, tgt, rel_type)
                builder._relationship_evidence[key] = list(evidences)

                builder.graph.add_edge(
                    src,
                    tgt,
                    relation_type=rel_type,
                    evidences=list(evidences),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("load_json: skip invalid relationship entry: %s", exc, exc_info=True)

        # 恢复向量索引（若存在）
        vector_blob = data.get("vector_index") or {}
        try:
            embeddings: List[List[float]] = vector_blob.get("embeddings") or []
            index_to_entity_id: List[str] = vector_blob.get("index_to_entity_id") or []
            dim: Optional[int] = vector_blob.get("dimension")
            model_name: str = vector_blob.get("embedding_model") or ""

            if embeddings and index_to_entity_id and dim and faiss is not None:
                mat = np.asarray(embeddings, dtype="float32")
                if mat.ndim == 2 and mat.shape[0] == len(index_to_entity_id) and mat.shape[1] == dim:
                    builder._embedding_dim = dim
                    builder._embedding_model_name = model_name or None
                    builder._embeddings_matrix = embeddings
                    builder._index_to_entity_id = list(index_to_entity_id)
                    builder._entity_id_to_index = {
                        eid: idx for idx, eid in enumerate(builder._index_to_entity_id)
                    }
                    index = faiss.IndexFlatL2(dim)  # type: ignore[call-arg]
                    index.add(mat)
                    builder._vector_index = index
                    logger.info(
                        "Reconstructed FAISS index from JSON: %d vectors (dim=%d, model=%s)",
                        mat.shape[0],
                        dim,
                        model_name or "<unknown>",
                    )
                else:
                    logger.warning("vector_index payload shape mismatch, skip FAISS reconstruction.")
            elif vector_blob and faiss is None:
                logger.warning(
                    "vector_index payload found but faiss is not installed; "
                    "Vector routing will be disabled until faiss-cpu is available."
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to restore vector_index from JSON: %s", exc, exc_info=True)

        logger.info(
            "GraphBuilder state loaded from %s: %d entities, %d relationships",
            p,
            len(builder._entities),
            len(builder._relationship_evidence),
        )
        return builder

    # ---------------------------------------------------------------------
    # 向量索引构建与检索接口
    # ---------------------------------------------------------------------

    def has_vector_index(self) -> bool:
        """
        判断当前是否已经成功构建了向量索引。
        """
        return self._vector_index is not None and bool(self._index_to_entity_id)

    def build_vector_index(
        self,
        client: Any,
        embedding_model: str,
        batch_size: int = 32,
        max_content_chars: int = 256,
    ) -> None:
        """
        基于当前图谱中的所有实体节点，构建 FAISS 向量索引。

        - 文本拼接规则：[Type] Name(or entity_id): content_摘要
        - 使用 SiliconFlow OpenAI-兼容接口的 embeddings.create 生成向量；
        - 采用简单的 IndexFlatL2 作为向量检索后端；
        - 支持多次调用：后一次会重建索引并覆盖旧索引。
        """
        if faiss is None:
            logger.warning(
                "faiss is not available; please install faiss-cpu to enable vector index "
                "(`pip install faiss-cpu`)."
            )
            return

        texts: List[str] = []
        entity_ids: List[str] = []

        for entity_id, merged in self._entities.items():
            node = self.graph.nodes.get(entity_id, {})
            entity_type = node.get("entity_type", merged.entity_type)
            name = node.get("name", merged.name) or merged.name or entity_id
            content = (node.get("content") or merged.content or "").strip()
            if max_content_chars and len(content) > max_content_chars:
                content = content[:max_content_chars] + "..."
            text = f"[{entity_type}] {name}: {content}"
            texts.append(text)
            entity_ids.append(entity_id)

        if not texts:
            logger.warning("build_vector_index: no entities to index; skip.")
            return

        def _embed_batch(batch_texts: List[str]) -> Optional[np.ndarray]:
            """
            带简单重试的 embedding 调用。
            """
            import time

            last_exc: Optional[Exception] = None
            for attempt in range(3):
                try:
                    resp = client.embeddings.create(  # type: ignore[call-arg]
                        model=embedding_model,
                        input=batch_texts,
                    )
                    # OpenAI-兼容接口：resp.data[i].embedding
                    vectors = [item.embedding for item in resp.data]  # type: ignore[attr-defined]
                    return np.asarray(vectors, dtype="float32")
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    wait = 1.5 * (2 ** attempt)
                    logger.warning(
                        "Embedding batch failed on attempt %d: %s; retry in %.1fs",
                        attempt + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
            logger.error("Embedding batch permanently failed after retries: %s", last_exc)
            return None

        all_vecs: List[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vecs = _embed_batch(batch)
            if vecs is None:
                # 某个 batch 失败时，直接中止整个构建流程，避免索引不完整
                logger.error("build_vector_index aborted due to embedding failures.")
                return
            all_vecs.append(vecs)

        mat = np.vstack(all_vecs)
        if mat.ndim != 2 or mat.shape[0] != len(entity_ids):
            logger.error(
                "build_vector_index: embedding matrix shape mismatch, got %s for %d entities.",
                mat.shape,
                len(entity_ids),
            )
            return

        dim = int(mat.shape[1])
        index = faiss.IndexFlatL2(dim)  # type: ignore[call-arg]
        index.add(mat)

        self._vector_index = index
        self._embedding_dim = dim
        self._embedding_model_name = embedding_model
        self._index_to_entity_id = list(entity_ids)
        self._entity_id_to_index = {eid: idx for idx, eid in enumerate(entity_ids)}
        self._embeddings_matrix = mat.astype("float32").tolist()

        logger.info(
            "Vector index built successfully: %d entities indexed (dim=%d, model=%s).",
            len(entity_ids),
            dim,
            embedding_model,
        )

    def search_by_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int = 1,
    ) -> List[Tuple[str, float]]:
        """
        使用已构建的向量索引，根据查询向量检索最相似的实体。

        返回 (entity_id, distance) 的列表，距离越小说明越相似。
        若尚未构建索引，则返回空列表。
        """
        if not self.has_vector_index():
            return []

        if query_embedding.ndim == 1:
            query_embedding = query_embedding[None, :]

        if self._embedding_dim is not None and query_embedding.shape[1] != self._embedding_dim:
            logger.warning(
                "search_by_embedding: query dimension %d != index dimension %d; "
                "skip vector search.",
                query_embedding.shape[1],
                self._embedding_dim,
            )
            return []

        k = min(top_k, len(self._index_to_entity_id))
        if k <= 0:
            return []

        assert self._vector_index is not None  # for type checkers
        distances, indices = self._vector_index.search(query_embedding.astype("float32"), k)  # type: ignore[arg-type]
        results: List[Tuple[str, float]] = []
        for dist, idx in zip(distances[0].tolist(), indices[0].tolist()):
            if idx < 0 or idx >= len(self._index_to_entity_id):
                continue
            eid = self._index_to_entity_id[idx]
            results.append((eid, float(dist)))
        return results

    # ---------------------------------------------------------------------
    # 社会搜索准备：统计与剪枝辅助
    # ---------------------------------------------------------------------

    def stats_report(self) -> Dict[str, Any]:
        """
        生成当前图谱的“密度”报告。

        返回结构示例：
        {
          "num_entities": 123,
          "num_relationships": 456,
          "num_weakly_connected_components": 7,
          "top_hub_entities": [
            {
              "entity_id": "UI_Component:Button",
              "degree": 42
            },
            ...
          ]
        }
        """
        num_entities = self.graph.number_of_nodes()
        num_relationships = self.graph.number_of_edges()

        if num_entities == 0:
            return {
                "num_entities": 0,
                "num_relationships": 0,
                "num_weakly_connected_components": 0,
                "top_hub_entities": [],
            }

        # 使用弱连通分量统计“孤立社区”数量
        undirected_view = self.graph.to_undirected(as_view=True)
        num_components = nx.number_connected_components(undirected_view)

        # 连接度最高的 Top 10 实体（基于总度数：入度+出度）
        degree_view = self.graph.degree()
        top_hubs = sorted(degree_view, key=lambda x: x[1], reverse=True)[:10]
        top_hub_entities = [
            {
                "entity_id": node_id,
                "degree": int(deg),
                "entity_type": self.graph.nodes[node_id].get("entity_type", ""),
                "name": self.graph.nodes[node_id].get("name", ""),
            }
            for node_id, deg in top_hubs
        ]

        return {
            "num_entities": int(num_entities),
            "num_relationships": int(num_relationships),
            "num_weakly_connected_components": int(num_components),
            "top_hub_entities": top_hub_entities,
        }


__all__ = ["MergedEntity", "GraphBuilder"]

