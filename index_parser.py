from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from entity_id_normalizer import normalize_entity_id
from pydantic_schema import DocumentGraph, Entity, Relationship


_MD_LINK_RE = re.compile(
    r"""
    \[
        (?P<text>[^\]\n]+?)
    \]
    \(
        (?P<href>
            (?:
                \./|\.\./
            )
            [^) \t\r\n]+?
            \.md
            (?:\#[^) \t\r\n]+)?
        )
    \)
    """,
    re.VERBOSE,
)


def _unescape_cangjie_generics(text: str) -> str:
    """
    兼容仓颉/文档里对泛型尖括号的转义写法，例如 "\\<T>"、"\\<K, V\\>"。
    这里仅做最小必要的反转义，避免破坏其它 Markdown 转义语义。
    """

    return text.replace(r"\<", "<").replace(r"\>", ">")


def _strip_anchor(href: str) -> Tuple[str, str]:
    if "#" in href:
        path, anchor = href.split("#", 1)
        return path, f"#{anchor}"
    return href, ""


def parse_index_markdown(md_text: str, source_metadata: dict) -> DocumentGraph:
    """
    解析目录/索引 Markdown（表格或列表）中的超链接，抽取“概念 -> 文档文件”的关联图谱。

    目标链接格式示例：
    - [实体名称](./path/to/doc.md#anchor)
    - [Map\\<T>](../collection/map.md)
    """

    matches = list(_MD_LINK_RE.finditer(md_text or ""))
    if not matches:
        return DocumentGraph(source_metadata=source_metadata or {})

    entities: List[Entity] = []
    relationships: List[Relationship] = []

    seen_entity_ids: Set[str] = set()
    seen_relationship_keys: Set[Tuple[str, str, str]] = set()

    for m in matches:
        raw_name = (m.group("text") or "").strip()
        href = (m.group("href") or "").strip()
        if not raw_name or not href:
            continue

        name = _unescape_cangjie_generics(raw_name)
        doc_path, anchor = _strip_anchor(href)

        # 使用统一的 entity_id 归一化，确保跨轨道合并
        concept_id = normalize_entity_id(f"Concept:{name}")
        file_id = normalize_entity_id(f"File:{doc_path}")

        if concept_id not in seen_entity_ids:
            entities.append(
                Entity(
                    entity_id=concept_id,
                    entity_type="Concept",
                    name=name,
                    content="",
                )
            )
            seen_entity_ids.add(concept_id)

        if file_id not in seen_entity_ids:
            entities.append(
                Entity(
                    entity_id=file_id,
                    entity_type="File",
                    name=doc_path,
                    content="",
                )
            )
            seen_entity_ids.add(file_id)

        rel_key = (concept_id, file_id, "DOCUMENTED_AT")
        if rel_key not in seen_relationship_keys:
            relationships.append(
                Relationship(
                    source_id=concept_id,
                    target_id=file_id,
                    relation_type="DOCUMENTED_AT",
                    # href 原样保留（含 #anchor），作为证据更可追溯；不要重复拼接 anchor
                    evidence=f"index_link: [{raw_name}]({href})",
                )
            )
            seen_relationship_keys.add(rel_key)

    # 允许“无有效项”时返回空图，但必须带上 source_metadata
    if not entities:
        return DocumentGraph(source_metadata=source_metadata or {})

    return DocumentGraph(
        entities=entities,
        relationships=relationships,
        source_metadata=source_metadata or {},
    )

