from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Sequence, Tuple

from pydantic import ValidationError

from pydantic_schema import DocumentGraph, Entity, Relationship
from index_parser import parse_index_markdown

logger = logging.getLogger(__name__)


# === 1. 鲁棒的 JSON 提取逻辑 ==================================================

JSON_OBJECT_REGEX = re.compile(r"\{.*\}", re.DOTALL)
JSON_CODE_BLOCK_REGEX = re.compile(r"```json(.*?)```", re.DOTALL | re.IGNORECASE)


def safe_json_loads(raw_text: str) -> Dict[str, Any] | None:
    """
    从 LLM 原始输出中“捞取”最外层 JSON，并尽量解析为 dict。

    优先级：
    1. 通过正则 r'\\{.*\\}' (DOTALL) 抓取从首个 '{' 到最后一个 '}' 的片段；
    2. 若失败，再尝试抓取 ```json ... ``` 代码块中的内容进行解析；
    3. 若仍失败，返回 None，由上层决定是否做递归重试或放弃当前片段。

    该函数本身不抛异常，只记录日志。
    """
    text = raw_text or ""

    # 尝试方案 1：整段里找最外围花括号
    try:
        m = JSON_OBJECT_REGEX.search(text)
        if m:
            candidate = m.group(0)
            return json.loads(candidate)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to parse JSON from outer braces: %s", exc, exc_info=True)

    # 尝试方案 2：从 ```json ... ``` 代码块中抓取
    try:
        m2 = JSON_CODE_BLOCK_REGEX.search(text)
        if m2:
            candidate = m2.group(1).strip()
            # 代码块里可能依然包了一层 {}，也可能就是对象本身
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                m3 = JSON_OBJECT_REGEX.search(candidate)
                if m3:
                    return json.loads(m3.group(0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to parse JSON from ```json``` block: %s", exc, exc_info=True)

    logger.warning("safe_json_loads: unable to parse JSON from LLM output; returning None.")
    return None


# === 2. 精准的系统提示词 =======================================================

GRAPH_EXTRACTION_PROMPT = """你是一个架构知识图谱抽取器。从 Markdown 技术文档中提取架构层面的实体与关系，输出 JSON。

输出格式：
{
  "entities": [{"entity_id": "类型:完整名称", "entity_type": "EntityType枚举值", "name": "显示名称", "content": "描述"}],
  "relationships": [{"source_id": "实体ID", "target_id": "实体ID", "relation_type": "RelationType枚举值", "evidence": "原文摘录"}]
}

实体类型（entity_type，区分大小写）：
Module, Class, Struct, Interface, Enum, Macro, Function, Property, Exception, Concept, Keyword,
UI_Component, UI_Modifier, Lifecycle_Hook, Permission, CLI_Command, Config_Option, CodeSnippet

关系类型（relation_type，区分大小写）：
BELONGS_TO, IMPLEMENTS, ACCEPTS_PARAM, RETURNS, THROWS, CALLS, CONTAINS, MODIFIED_BY,
TRIGGERS_EVENT, DEPENDS_ON, CONFIGURES, HAS_SAMPLE_CODE

【entity_id 生成规则 - 关键】
entity_id 格式：`类型:完整限定名称`，必须包含完整的命名空间路径。

命名空间处理规则（重要）：
1. **必须保留完整的命名空间前缀**，区分不同库/包的实体：
   - 标准库模块：`Module:std.xxx`（如 `Module:std.io`）
   - stdx 扩展库：`Module:stdx.xxx`（如 `Module:stdx.net.http`）
   - ohos 系统库：`Module:ohos.xxx`（如 `Module:ohos.net.http`）
   - 其他命名空间：`Module:命名空间.子模块`（如 `Module:cangjie.runtime`）

2. **禁止省略命名空间前缀**：
   - ❌ 错误：`Module:net.http`（缺少命名空间）
   - ✅ 正确：`Module:stdx.net.http`（完整命名空间）
   - ❌ 错误：`Module:http`（缺少命名空间和父模块）
   - ✅ 正确：`Module:stdx.net.http`（完整路径）

3. **相同语义的实体必须使用相同的 entity_id**（跨文档一致性）：
   - 如果文档 A 提到 `stdx.net.http`，entity_id 应为 `Module:stdx.net.http`
   - 如果文档 B 也提到 `stdx.net.http`，必须使用相同的 `Module:stdx.net.http`
   - 这样系统会自动合并为同一个节点

4. **不同命名空间的同名实体必须区分**：
   - `Module:stdx.net.http` 和 `Module:ohos.net.http` 是不同的实体，不能合并
   - `Module:stdx.log` 和 `Module:std.log` 是不同的实体，不能合并

5. **示例**：
   - 标准库：`Module:std.io`, `Module:std.string`, `Class:std.String`
   - stdx 库：`Module:stdx.net.http`, `Module:stdx.log`, `Class:stdx.log.Logger`
   - ohos 库：`Module:ohos.net.http`, `UI_Component:ohos.Button`
   - 配置项：`Config_Option:router_mode`, `Config_Option:app.name`
   - CLI 命令：`CLI_Command:cjc`, `CLI_Command:cjdb`

【name 字段规则】
- name 字段填写实体的显示名称（人类可读），可以包含命名空间：
  - entity_id: `Module:stdx.net.http` → name: `stdx.net.http`
  - entity_id: `Class:stdx.log.Logger` → name: `Logger` 或 `stdx.log.Logger`
- name 主要用于显示，entity_id 用于唯一标识和合并

【语义选择规则】
- 只提取架构定义层面的内容（模块、接口、类、UI组件、配置项、核心概念等）
- 禁止提取：运行日志、示例输入输出、临时变量名（foo/bar/temp）、纯URL/目录链接

【字段填写要求】
- 所有字段必需，不能省略。content 字段必需，不能为空。
- content 填写：Module/Class→功能描述；Function→功能/参数/返回值；Property/Config_Option→类型/默认值/用途；Concept/Keyword→定义/语义；UI_Component→功能/用法；CLI_Command→功能/参数；CodeSnippet→代码本身（必须与原文一致）。
- 如果找不到描述，至少填写实体名称或简短说明。

【证据溯源要求】
- evidence 必须是原文精准摘录，不能改写或总结，必须是原文子串。
- 找不到证据就不要创建关系。

【输出格式要求】
- 只输出纯 JSON 对象，不要代码块标记、注释或多余文字。

请抽取文档片段并返回 JSON。"""


# === 3. 自适应分块逻辑 ========================================================

def sliding_window_chunks(
    text: str,
    max_chunk_size: int,
    overlap_size: int = 300,
) -> List[str]:
    """
    将长文本按字符数做滑动窗口切分，保持 overlap_size 的重叠。

    参数:
        text: 原始 Markdown 文本。
        max_chunk_size: 单个片段的最大长度（字符数）。
        overlap_size: 邻接片段之间的重叠长度，默认 300 字符。
    """
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")

    n = len(text)
    if n == 0:
        return []

    chunks: List[str] = []
    start = 0
    while start < n:
        end = min(start + max_chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        # 下一个窗口的起点为本窗口末尾减去 overlap
        next_start = end - overlap_size
        if next_start <= start:
            # 防止死循环，至少前进 1
            next_start = start + 1
        start = next_start

    return chunks


# === 4. 实体标准化与清洗 =======================================================

WHITESPACE_REGEX = re.compile(r"\s+", re.UNICODE)

# 统一使用 entity_id_normalizer 模块的归一化函数
from entity_id_normalizer import normalize_entity_id


def _normalize_whitespace(s: str) -> str:
    return WHITESPACE_REGEX.sub(" ", s).strip()


def is_valid_code_snippet(snippet: str, original_text: str) -> bool:
    """
    快速字符串对齐检查：
    1. 若 snippet 作为子串直接出现在原文中，则认为有效；
    2. 否则，对 snippet 与原文都做空白折叠（collapse whitespace）后再尝试子串匹配；
    3. 若仍失败，则认为该 CodeSnippet 摘录缺乏直接证据，视为无效。
    """
    if not snippet:
        return False

    if snippet in original_text:
        return True

    normalized_snippet = _normalize_whitespace(snippet)
    if not normalized_snippet:
        return False

    normalized_original = _normalize_whitespace(original_text)
    return normalized_snippet in normalized_original


def _build_entities_and_relationships(
    raw_entities: Sequence[Dict[str, Any]],
    raw_relationships: Sequence[Dict[str, Any]],
    original_text: str,
) -> Tuple[List[Entity], List[Relationship]]:
    """
    将 LLM 产出的原始 dict 列表转为 Pydantic 模型，并做 ID 归一化与 CodeSnippet 过滤。
    """
    entities: Dict[str, Entity] = {}
    relationships: List[Relationship] = []

    # 1) 先处理实体
    for item in raw_entities:
        if not isinstance(item, dict):
            logger.debug("Skip non-dict entity item: %r", item)
            continue

        raw_id = str(item.get("entity_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not raw_id and not name:
            # 完全无法识别的实体，跳过
            logger.debug("Skip entity without id and name: %r", item)
            continue

        normalized_id = normalize_entity_id(raw_id or name)
        item["entity_id"] = normalized_id

        # CodeSnippet 物理防伪：内容若无法在原文中对齐，则丢弃该实体
        if item.get("entity_type") == "CodeSnippet":
            content = str(item.get("content") or "")
            if not is_valid_code_snippet(content, original_text):
                logger.info(
                    "Drop invalid CodeSnippet entity (content not found in text): id=%s",
                    normalized_id,
                )
                continue

        try:
            entity = Entity(**item)
        except ValidationError as exc:
            logger.info("Drop invalid entity due to validation error: %s", exc)
            continue

        # 去重：同一 ID 多次出现时，保留第一份（你也可以按需选择覆盖）
        if normalized_id not in entities:
            entities[normalized_id] = entity

    # 2) 再处理关系（使用已经归一化的 ID）
    for item in raw_relationships:
        if not isinstance(item, dict):
            logger.debug("Skip non-dict relationship item: %r", item)
            continue

        src = str(item.get("source_id") or "").strip()
        tgt = str(item.get("target_id") or "").strip()
        if not src or not tgt:
            logger.debug("Skip relationship without source/target: %r", item)
            continue

        item["source_id"] = normalize_entity_id(src)
        item["target_id"] = normalize_entity_id(tgt)

        try:
            rel = Relationship(**item)
        except ValidationError as exc:
            logger.info("Drop invalid relationship due to validation error: %s", exc)
            continue

        relationships.append(rel)

    return list(entities.values()), relationships


# === 5. 核心抽取流程 (Main API) ===============================================


def _call_llm_for_chunk(
    client: Any,
    model: str,
    chunk_text: str,
) -> Dict[str, Any] | None:
    """
    对单个文本片段调用 LLM，并做安全的 JSON 解析。

    若解析失败，返回 None，由上层决定是否递归重试。
    """
    # 根因治理 1：优先使用“结构化输出 / JSON 模式”强制模型只返回 JSON（如果服务端支持）。
    # 这样可以显著降低“格式跑偏/夹带解释/代码块/多段文本”导致的解析失败。
    #
    # 兼容性：部分 OpenAI-兼容服务不支持 response_format，会报错；此时自动回退到普通模式。
    messages = [
        {"role": "system", "content": GRAPH_EXTRACTION_PROMPT},
        {"role": "user", "content": chunk_text},
    ]

    try:
        response = client.chat.completions.create(  # type: ignore[call-arg]
            model=model,
            messages=messages,
            temperature=0.1,  # 结构化输出优先稳定性
            max_tokens=8192,  # 提高输出限制，降低 JSON 被截断概率
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Structured JSON mode not available or failed, fallback to plain mode: %s", exc)
        try:
            response = client.chat.completions.create(  # type: ignore[call-arg]
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=8192,
            )
        except Exception as exc2:  # noqa: BLE001
            logger.warning("LLM API call failed: %s", exc2, exc_info=True)
            return None

    try:
        content = response.choices[0].message.content or ""  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected LLM response structure: %s", exc, exc_info=True)
        return None

    data = safe_json_loads(content)
    return data


def _extract_from_chunk_with_retry(
    client: Any,
    model: str,
    chunk_text: str,
    depth: int,
    max_depth: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    针对单个片段进行抽取，支持在解析失败时按“二分”策略递归重试。

    若在最大递归深度内仍无法解析，则返回空列表，保证主流程不中断。
    """
    data = _call_llm_for_chunk(client, model, chunk_text)

    if data is None or not isinstance(data, dict):
        # 解析失败，考虑递归切分
        # 注意：输入上下文有 200k，足够大；问题可能是输出 JSON 太大被截断
        # 所以拆分是为了让每个 chunk 产生的输出更小，避免截断
        
        # 降低最小拆分阈值：从 512 降到 200，让更多 chunk 有机会拆分
        # 但完全放弃的阈值设为 100，避免对极小片段浪费 API 调用
        min_split_size = 200  # 最小拆分大小
        min_retry_size = 100  # 最小重试大小（小于这个才真正放弃）
        
        if len(chunk_text) > min_split_size and depth < max_depth:
            mid = len(chunk_text) // 2
            left = chunk_text[:mid]
            right = chunk_text[mid:]
            logger.info(
                "Chunk parse failed, recursively splitting at depth %s (len=%s).",
                depth,
                len(chunk_text),
            )
            e1, r1 = _extract_from_chunk_with_retry(client, model, left, depth + 1, max_depth)
            e2, r2 = _extract_from_chunk_with_retry(client, model, right, depth + 1, max_depth)
            return e1 + e2, r1 + r2
        
        # 即使达到最大深度，如果 chunk 还比较大（>min_retry_size），再尝试一次
        # 因为可能是 LLM 返回格式问题，而不是内容太长
        # 信息密度大的 chunk 应该更积极尝试，而不是轻易放弃
        if len(chunk_text) > min_retry_size:
            if depth >= max_depth:
                logger.info(
                    "Reached max depth %s but chunk still substantial (%s chars), retrying once more...",
                    max_depth,
                    len(chunk_text),
                )
            else:
                logger.info(
                    "Chunk small (%s chars) but retrying once more before giving up...",
                    len(chunk_text),
                )
            retry_data = _call_llm_for_chunk(client, model, chunk_text)
            if retry_data and isinstance(retry_data, dict):
                raw_entities = retry_data.get("entities") or []
                raw_relationships = retry_data.get("relationships") or []
                if isinstance(raw_entities, list) and isinstance(raw_relationships, list):
                    logger.info("Retry succeeded!")
                    return raw_entities, raw_relationships

        # 只有 chunk 非常小（<=min_retry_size）时才真正放弃
        logger.warning(
            "Failed to parse chunk at depth %s (len=%s); giving up on this chunk.",
            depth,
            len(chunk_text),
        )

        # 将失败的 chunk 追加写入日志文件，便于后续人工排查
        try:
            from pathlib import Path

            fail_log_path = Path("failed_chunks.log")
            with fail_log_path.open("a", encoding="utf-8") as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"depth={depth}, len={len(chunk_text)}\n")
                f.write("-" * 80 + "\n")
                # 只截断极端长文本，防止日志文件爆炸
                preview = chunk_text if len(chunk_text) <= 5000 else chunk_text[:5000] + "\n...[truncated]...\n"
                f.write(preview)
                f.write("\n")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to dump failed chunk: %s", exc, exc_info=True)

        return [], []

    raw_entities = data.get("entities") or []
    raw_relationships = data.get("relationships") or []

    if not isinstance(raw_entities, list) or not isinstance(raw_relationships, list):
        logger.warning("LLM JSON does not contain list 'entities'/'relationships'.")
        return [], []

    return raw_entities, raw_relationships


def extract_graph_from_text(
    client: Any,
    model: str,
    markdown_text: str,
    source_metadata: Dict[str, Any] | None = None,
    *,
    max_chunk_size: int = 4000,
    overlap_size: int = 300,
    max_retry_depth: int = 2,
) -> DocumentGraph:
    """
    将非结构化 Markdown 技术文档转化为符合 Pydantic 契约的 DocumentGraph。

    参数:
        client: OpenAI 客户端实例（需支持 chat.completions.create 接口）。
        model: 使用的模型名称。
        markdown_text: 原始 Markdown 文本。
        source_metadata: 溯源元数据，将写入 DocumentGraph.source_metadata。
        max_chunk_size: 滑动窗口的单片最大字符数。
        overlap_size: 邻接片段之间的重叠字符数。
        max_retry_depth: JSON 解析失败时“二分”递归的最大深度。

    返回:
        已完成 ID 清洗、并经过 DocumentGraph 内部“孤儿关系”过滤的图对象。
        若整体解析过程失败，返回一个包含给定 source_metadata 的空图谱。
    """
    if not markdown_text:
        return DocumentGraph(
            entities=[],
            relationships=[],
            source_metadata=source_metadata or {},
        )

    # 快速检测：如果文档主要是链接列表（目录型文档），优先走“目录专线”正则抽取（轨道 1），
    # 而不是直接返回空图谱，避免误杀像 *_function.md 这类 API 汇总页。
    # 启发式：链接数量 / 总行数 > 0.5，且平均行长度较短
    lines = markdown_text.split('\n')
    if len(lines) > 10:  # 只对较长的文档做检测
        link_count = markdown_text.count("[") + markdown_text.count("](")  # 粗略统计链接
        avg_line_length = len(markdown_text) / len(lines)
        link_ratio = link_count / len(lines) if lines else 0

        # 如果链接比例高且平均行长度短，极可能是目录/索引/API 一览页 → 走 parse_index_markdown
        if link_ratio > 0.5 and avg_line_length < 100:
            logger.info(
                "Treating as directory/index-like page; route to parse_index_markdown "
                "(link_ratio=%.2f, avg_line_len=%.1f)",
                link_ratio,
                avg_line_length,
            )
            return parse_index_markdown(md_text=markdown_text, source_metadata=source_metadata or {})

    chunks = sliding_window_chunks(markdown_text, max_chunk_size=max_chunk_size, overlap_size=overlap_size)

    all_raw_entities: List[Dict[str, Any]] = []
    all_raw_relationships: List[Dict[str, Any]] = []

    for chunk in chunks:
        e_list, r_list = _extract_from_chunk_with_retry(
            client=client,
            model=model,
            chunk_text=chunk,
            depth=0,
            max_depth=max_retry_depth,
        )
        all_raw_entities.extend(e_list)
        all_raw_relationships.extend(r_list)

    # 若完全没有解析出任何内容，返回空图谱
    if not all_raw_entities and not all_raw_relationships:
        logger.info("No entities or relationships extracted; returning empty DocumentGraph.")
        return DocumentGraph(
            entities=[],
            relationships=[],
            source_metadata=source_metadata or {},
        )

    entities, relationships = _build_entities_and_relationships(
        raw_entities=all_raw_entities,
        raw_relationships=all_raw_relationships,
        original_text=markdown_text,
    )

    # DocumentGraph 自身会再做一次“孤儿关系”过滤
    graph = DocumentGraph(
        entities=entities,
        relationships=relationships,
        source_metadata=source_metadata or {},
    )

    return graph


__all__ = [
    "GRAPH_EXTRACTION_PROMPT",
    "safe_json_loads",
    "sliding_window_chunks",
    "normalize_entity_id",
    "is_valid_code_snippet",
    "extract_graph_from_text",
]

