from __future__ import annotations

"""
解析 Cangjie 声明文件 (.cj.d)，构建实体与关系。

支持的运行模式：
  1) 本地 Tree-sitter AST（cangjie_lang 非 None）：
       - 由调用方传入已初始化好的 Cangjie Language（通常在 WSL / Linux 环境）。
  2) 远程 AST 微服务（推荐在 Windows 环境使用）：
       - 通过 HTTP 调用运行在 WSL / Linux 的 `scripts/cjd_ast_service.py`，
         由该服务使用专用 Tree-sitter 语法完成 AST 解析。
       - 通过环境变量 CJD_REMOTE_SERVICE_URL 配置服务地址（默认 http://127.0.0.1:8001/parse_cjd）。
  3) 纯文本兜底解析（无 AST 时自动退回）：
       - 不依赖 Tree-sitter，仅基于 .cj.d 文本的正则/启发式抽取 class/interface/function 以及
         INHERITS / IMPLEMENTS / RETURNS / ACCEPTS_PARAM 四类关系。
"""

import json
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from entity_id_normalizer import normalize_entity_id
from pydantic_schema import DocumentGraph, Entity, Relationship

logger = logging.getLogger(__name__)


def _safe_decode(src_bytes: bytes) -> str:
    try:
        return src_bytes.decode("utf-8", errors="replace")
    except Exception:
        # 极端情况下兜底
        return "".join(chr(b) if 32 <= b < 127 else "�" for b in src_bytes)


def _node_text(src_bytes: bytes, node: Any) -> str:
    """
    从 tree-sitter Node 提取 raw text（使用字节范围 slice，确保泛型/符号不丢失）。
    """
    try:
        return _safe_decode(src_bytes[node.start_byte : node.end_byte])
    except Exception:
        return ""


def _find_first_child_by_type(node: Any, type_name: str) -> Optional[Any]:
    try:
        for ch in node.children:
            if getattr(ch, "type", None) == type_name:
                return ch
    except Exception:
        return None
    return None


def _iter_descendants(node: Any) -> Iterable[Any]:
    """
    迭代 node 的所有后代节点。容错：任何异常都直接停止该分支。
    """
    stack = []
    try:
        stack.append(node)
    except Exception:
        return

    while stack:
        cur = stack.pop()
        yield cur
        try:
            children = list(cur.children or [])
        except Exception:
            continue
        # 深度优先
        for ch in reversed(children):
            stack.append(ch)


def _guess_identifier_text(src_bytes: bytes, decl_node: Any) -> str:
    """
    尝试从声明节点中猜测标识符（类名/接口名/函数名）。
    由于语法可能变化，这里用几种保守策略：
      - 优先找 type == "identifier"
      - 其次找 type == "type_identifier" / "scoped_identifier" 等常见命名
      - 最后用正则从 raw text 中提取关键字后的第一个 token
    """

    preferred_types = {
        "identifier",
        "type_identifier",
        "scoped_identifier",
        "qualified_identifier",
        "simple_identifier",
        # 针对 CangjieTreeSitter 的声明节点：
        "funcName",
        "className",
        "interfaceName",
    }
    try:
        for ch in decl_node.children:
            if getattr(ch, "type", None) in preferred_types:
                name = _node_text(src_bytes, ch).strip()
                if name:
                    return name
    except Exception:
        pass

    raw = _node_text(src_bytes, decl_node)
    # 兜底：class Foo / interface Bar / func baz
    m = re.search(r"\b(class|interface|func|function)\s+([A-Za-z_][\w]*)", raw)
    if m:
        return m.group(2)
    return ""


def _mk_entity(entity_type: str, name: str, content: str) -> Entity:
    # 使用统一的 entity_id 归一化，确保跨轨道合并（与 extractor.py 的 normalize_entity_id 一致）
    raw_id = f"{entity_type}:{name}" if entity_type != "Function" else f"Function:{name}"
    return Entity(
        entity_id=normalize_entity_id(raw_id),
        entity_type=entity_type,  # type: ignore[arg-type]
        name=name,
        content=content,
    )


def _add_entity(entities: Dict[str, Entity], entity: Entity) -> None:
    # 去重：同 ID 以第一次为准，避免后续覆盖（更保守）
    if entity.entity_id not in entities:
        entities[entity.entity_id] = entity


def _add_rel(
    rels: Dict[Tuple[str, str, str], Relationship],
    source_id: str,
    target_id: str,
    relation_type: str,
    evidence: str,
) -> None:
    key = (source_id, target_id, relation_type)
    if key not in rels:
        rels[key] = Relationship(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,  # type: ignore[arg-type]
            evidence=evidence or "",
        )


def _collect_decl_nodes(root: Any) -> List[Any]:
    """
    捕获 class_declaration, interface_declaration, function_declaration。
    若语法节点命名稍有差异，也会尽量兼容常见别名（例如 class_decl/function_decl）。

    注意：CangjieTreeSitter 实际使用的节点名多为驼峰式 Definition，
    例如：
      - classDefinition
      - interfaceDefinition
      - functionDefinition
      - mainDefinition
    为了“最大程度利用 Tree-sitter”，这里同时兼容这两套命名。
    """

    targets = {
        "class_declaration",
        "interface_declaration",
        "function_declaration",
        # 兼容可能的别名
        "class_decl",
        "interface_decl",
        "function_decl",
        # 兼容 CangjieTreeSitter 中广泛使用的 Definition 命名
        "classDefinition",
        "interfaceDefinition",
        "functionDefinition",
        "mainDefinition",
    }
    out: List[Any] = []
    for n in _iter_descendants(root):
        try:
            t = getattr(n, "type", None)
            if not t:
                continue
            if t in targets:
                out.append(n)
                continue

            # 额外的启发式兜底：
            # - 任何以 "Definition" 结尾且包含 class/interface/function/main 关键词的节点，
            #   也视为潜在的声明节点（适配未来语法演进）。
            if t.endswith("Definition") and any(
                kw in t for kw in ("class", "interface", "function", "func", "main")
            ):
                out.append(n)
        except Exception:
            continue
    return out


def _extract_relation_targets_from_node_text(text: str) -> List[str]:
    """
    非侵入式兜底策略：从节点 raw text 中抽取潜在的类型名（含泛型），用于关系目标。
    注意：这只是兜底；更准确的方式应依赖具体 AST node 类型。
    """

    # 抽取像 Foo, Foo<T>, pkg.Foo<K,V> 这类 token（非常保守）
    candidates = re.findall(r"[A-Za-z_][\w.]*\s*(?:<[^>\n]+>)?", text)
    cleaned = []
    for c in candidates:
        c2 = c.strip()
        if not c2:
            continue
        # 排除关键字
        if c2 in {"class", "interface", "func", "function", "extends", "implements", "return"}:
            continue
        cleaned.append(c2)
    # 去重但保持顺序
    seen = set()
    out = []
    for x in cleaned:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _split_decl_head(raw_decl: str) -> str:
    """
    取声明节点的“头部”区域，用于做轻量语法解析：
    - 截断到第一个 '{' 或换行前（避免把函数体/大段注释纳入）
    - 去掉 where 约束（例如 where T <: Foo & Bar），避免误判为继承/实现
    """

    head = (raw_decl or "").strip()
    if not head:
        return ""
    # 截断到 '{' 或首个换行
    brace_idx = head.find("{")
    nl_idx = head.find("\n")
    cut_points = [i for i in (brace_idx, nl_idx) if i != -1]
    if cut_points:
        head = head[: min(cut_points)]
    # 去掉 where 约束（保守：where 后全部丢弃）
    where_idx = head.find(" where ")
    if where_idx != -1:
        head = head[:where_idx]
    return head.strip()


def _parse_subtypes_from_colon_syntax(raw_decl: str) -> List[str]:
    """
    解析 Cangjie 声明中的 subtype 语法：`<:`
    典型样例：
      - public class ArrayDeque<T> <: Deque<T> {
      - public open class Decl <: Node {
      - extend HttpRequestEvent <: Equatable<HttpRequestEvent> {
    """

    head = _split_decl_head(raw_decl)
    if "<:" not in head:
        return []
    _, rhs = head.split("<:", 1)
    rhs = rhs.strip()
    if not rhs:
        return []

    # 允许 `A & B` / `A, B` 这类组合（以常见分隔符拆分）
    parts = re.split(r"\s*&\s*|\s*,\s*", rhs)
    out: List[str] = []
    for p in parts:
        p2 = p.strip()
        if not p2:
            continue
        out.append(p2)
    return out


def _extract_param_types_from_signature(raw_decl: str) -> List[str]:
    """
    从函数签名 raw text 中提取参数类型（只取 `name: Type` 里的 Type，避免把 name 当成类型）。
    兼容：`cacheSize!: UInt32 = MAX_CACHE_SIZE`
    """

    head = _split_decl_head(raw_decl)
    m = re.search(r"\((.*?)\)", head, flags=re.S)
    if not m:
        return []
    params = m.group(1)
    if not params.strip():
        return []

    # 提取冒号后的类型片段，直到 , ) = 或换行
    # 支持 ?T / Array<T> / HashMap<K, V> 等
    type_hits = re.findall(r":\s*([?A-Za-z_][^,)=\n\r;]*)", params)
    out: List[str] = []
    for t in type_hits:
        tt = t.strip()
        if not tt:
            continue
        out.append(tt)
    # 去重保序
    seen = set()
    dedup: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


def _fallback_parse_cjd_text(cjd_text: str, source_metadata: dict) -> DocumentGraph:
    """
    纯文本兜底解析：在无法使用 Tree-sitter 语法树时，从 .cj.d 文本中尽量抽取
    class/interface/function 及其核心关系。

    目标：
      - 实体：Class / Interface / Function
      - 关系：
          - INHERITS / IMPLEMENTS：来自 `<:` 语法（以及 extend/implements 关键字的简单场景）
          - RETURNS：函数返回类型
          - ACCEPTS_PARAM：函数参数类型
    """

    text = cjd_text or ""
    entities: Dict[str, Entity] = {}
    rels: Dict[Tuple[str, str, str], Relationship] = {}

    # --- 1) class / interface 声明 ---
    # 兼容：
    #   public class Foo<T> <: Bar<T> {
    #   public open class Decl <: Node {
    #   public interface Arbitrary<T> {
    class_iface_pattern = re.compile(
        r"""
        ^\s*
        (?P<prefix>public|open|sealed|abstract)\s+
        (?:(?:open|sealed|abstract)\s+)?   # 冗余修饰词，容错
        (?P<kind>class|interface)\s+
        (?P<name>[A-Za-z_]\w*(?:\s*<[^>{\n]+>)?)   # 名称 + 泛型
        (?P<rest>[^\n]*)
        """,
        re.MULTILINE | re.VERBOSE,
    )

    for m in class_iface_pattern.finditer(text):
        kind = m.group("kind")
        name = (m.group("name") or "").strip()
        if not name:
            continue

        raw_decl = m.group(0).rstrip()

        ent = _mk_entity("Class" if kind == "class" else "Interface", name, raw_decl)
        _add_entity(entities, ent)

        # 继承/实现：使用 `<:` 启发式
        colon_supers = _parse_subtypes_from_colon_syntax(raw_decl)
        if colon_supers:
            if kind == "class":
                # class: 第一个视为 INHERITS，其余视为 IMPLEMENTS
                for idx, t in enumerate(colon_supers):
                    rel_type = "INHERITS" if idx == 0 else "IMPLEMENTS"
                    target_kind = "Class" if rel_type == "INHERITS" else "Interface"
                    target = _mk_entity(target_kind, t, "")
                    _add_entity(entities, target)
                    _add_rel(
                        rels,
                        ent.entity_id,
                        target.entity_id,
                        rel_type,
                        evidence=_split_decl_head(raw_decl),
                    )
            else:
                # interface: 全部视为 INHERITS
                for t in colon_supers:
                    target = _mk_entity("Interface", t, "")
                    _add_entity(entities, target)
                    _add_rel(
                        rels,
                        ent.entity_id,
                        target.entity_id,
                        "INHERITS",
                        evidence=_split_decl_head(raw_decl),
                    )

    # --- 2) function 声明 ---
    # 兼容：
    #   public func createHttp(): HttpRequest
    #   public func foo(a: T, b: Map<K, V>): Unit
    func_pattern = re.compile(
        r"""
        ^\s*
        (?P<prefix>public)\s+
        func\s+
        (?P<name>[A-Za-z_]\w*)   # 函数名
        \s*
        \(
            (?P<params>[^\)]*)
        \)
        \s*
        (?::\s*(?P<rettype>[^\s{;]+(?:\s*<[^>\n]+>)?))?
        """,
        re.MULTILINE | re.VERBOSE,
    )

    for m in func_pattern.finditer(text):
        fname = (m.group("name") or "").strip()
        if not fname:
            continue

        raw_decl = m.group(0).rstrip()
        ent = _mk_entity("Function", fname, raw_decl)
        _add_entity(entities, ent)

        # RETURNS：使用显式返回类型或兜底正则
        rettype = (m.group("rettype") or "").strip()
        if rettype:
            for t in _extract_relation_targets_from_node_text(rettype):
                target = _mk_entity("Concept", t, "")
                _add_entity(entities, target)
                _add_rel(
                    rels,
                    ent.entity_id,
                    target.entity_id,
                    "RETURNS",
                    evidence=raw_decl,
                )
        else:
            # 兜底：在整行中尝试匹配 `): RetType`
            tail_types = _extract_relation_targets_from_node_text(raw_decl)
            # 避免把函数名本身当成返回类型
            tail_types = [t for t in tail_types if t != fname]
            for t in tail_types:
                target = _mk_entity("Concept", t, "")
                _add_entity(entities, target)
                _add_rel(
                    rels,
                    ent.entity_id,
                    target.entity_id,
                    "RETURNS",
                    evidence=raw_decl,
                )

        # ACCEPTS_PARAM：基于 `name: Type` 抽取类型
        param_types = _extract_param_types_from_signature(raw_decl)
        for t in param_types:
            target = _mk_entity("Concept", t, "")
            _add_entity(entities, target)
            _add_rel(
                rels,
                ent.entity_id,
                target.entity_id,
                "ACCEPTS_PARAM",
                evidence=raw_decl,
            )

    try:
        graph = DocumentGraph(
            entities=list(entities.values()),
            relationships=list(rels.values()),
            source_metadata=source_metadata or {},
        )
        logger.info(
            "Fallback CJD text parser produced entities=%d, relationships=%d for %s",
            len(graph.entities),
            len(graph.relationships),
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return graph
    except Exception:
        logger.warning(
            "Fallback CJD text parser failed to build DocumentGraph; return empty graph for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return DocumentGraph(source_metadata=source_metadata or {})


def _try_parse_via_remote_service(
    cjd_text: str,
    source_metadata: dict,
) -> Optional[DocumentGraph]:
    """
    尝试调用远程 CJD AST 微服务（通常部署在 WSL / Linux 中，运行 scripts/cjd_ast_service.py）。

    配置：
      - 环境变量 CJD_REMOTE_SERVICE_URL
        默认为 "http://127.0.0.1:8001/parse_cjd"
    """

    url = os.getenv("CJD_REMOTE_SERVICE_URL", "http://127.0.0.1:8001/parse_cjd")

    payload = {
        "cjd_text": cjd_text or "",
        "source_metadata": source_metadata or {},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urlopen(req, timeout=8) as resp:
            if resp.status != 200:
                logger.debug("Remote CJD service returned non-200: %s", resp.status)
                return None
            body = resp.read()
    except URLError as exc:
        logger.debug("Remote CJD service unreachable at %s: %s", url, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Remote CJD service call failed: %s", exc, exc_info=True)
        return None

    try:
        obj = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        logger.debug("Remote CJD service returned invalid JSON.")
        return None

    try:
        return DocumentGraph.model_validate(obj)
    except ValidationError as exc:
        logger.debug("Remote CJD service JSON failed DocumentGraph validation: %s", exc, exc_info=True)
        return None


def parse_cjd_ast(cjd_text: str, source_metadata: dict, cangjie_lang) -> DocumentGraph:
    """
    使用 Tree-sitter 解析仓颉声明文件 (.cj.d)，抽取 class/interface/function，并构建关系：
      - INHERITS: 类继承
      - IMPLEMENTS: 接口实现
      - RETURNS: 函数返回值类型
      - ACCEPTS_PARAM: 函数参数类型

    要求：Entity.content 必须保存对应 AST 节点的完整原始代码字符串（Raw Text），不丢泛型。
    说明：由于 tree-sitter-cangjie 的节点命名可能演进，本实现采取“优先结构化节点、失败则兜底正则”
    的策略，并做强容错，确保任何异常都不会导致整体失败。
    """

    # 若未提供 Cangjie 语言对象（或未安装 tree_sitter），优先尝试远程 AST 微服务，其次退回纯文本兜底解析。
    if cangjie_lang is None:
        logger.info(
            "parse_cjd_ast: no local Cangjie Language; trying remote AST service then fallback text parser "
            "for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        remote_graph = _try_parse_via_remote_service(cjd_text, source_metadata)
        if remote_graph is not None:
            logger.info(
                "parse_cjd_ast: remote AST service succeeded (entities=%d, relationships=%d) for %s",
                len(remote_graph.entities),
                len(remote_graph.relationships),
                (source_metadata or {}).get("file_path", "<unknown>"),
            )
            return remote_graph
        logger.info(
            "parse_cjd_ast: remote AST service unavailable/empty; using fallback text parser for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return _fallback_parse_cjd_text(cjd_text, source_metadata)

    try:
        from tree_sitter import Parser  # type: ignore
    except Exception:
        # 环境缺少 tree_sitter 时，优先尝试远程 AST 微服务，其次退回兜底解析
        logger.info(
            "parse_cjd_ast: tree_sitter not available in this process; trying remote AST service for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        remote_graph = _try_parse_via_remote_service(cjd_text, source_metadata)
        if remote_graph is not None:
            logger.info(
                "parse_cjd_ast: remote AST service succeeded (entities=%d, relationships=%d) for %s",
                len(remote_graph.entities),
                len(remote_graph.relationships),
                (source_metadata or {}).get("file_path", "<unknown>"),
            )
            return remote_graph
        logger.info(
            "parse_cjd_ast: remote AST service unavailable/empty; using fallback text parser for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return _fallback_parse_cjd_text(cjd_text, source_metadata)

    src_bytes = (cjd_text or "").encode("utf-8", errors="replace")
    entities: Dict[str, Entity] = {}
    rels: Dict[Tuple[str, str, str], Relationship] = {}

    try:
        parser = Parser()
        # 兼容不同版本 API
        if hasattr(parser, "set_language"):
            parser.set_language(cangjie_lang)
        else:
            parser.language = cangjie_lang  # type: ignore[attr-defined]

        tree = parser.parse(src_bytes)
        root = tree.root_node
        logger.info(
            "parse_cjd_ast: using local Tree-sitter AST for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
    except Exception as exc:
        logger.warning(
            "parse_cjd_ast: local Tree-sitter AST failed (%s); trying remote service for %s",
            exc,
            (source_metadata or {}).get("file_path", "<unknown>"),
            exc_info=True,
        )
        remote_graph = _try_parse_via_remote_service(cjd_text, source_metadata)
        if remote_graph is not None:
            logger.info(
                "parse_cjd_ast: remote AST service succeeded (entities=%d, relationships=%d) for %s",
                len(remote_graph.entities),
                len(remote_graph.relationships),
                (source_metadata or {}).get("file_path", "<unknown>"),
            )
            return remote_graph
        logger.info(
            "parse_cjd_ast: remote AST service unavailable/empty; using fallback text parser for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return _fallback_parse_cjd_text(cjd_text, source_metadata)

    decl_nodes = []
    try:
        decl_nodes = _collect_decl_nodes(root)
    except Exception as exc:
        logger.warning(
            "parse_cjd_ast: _collect_decl_nodes failed for %s: %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
            exc,
            exc_info=True,
        )
        decl_nodes = []

    for decl in decl_nodes:
        try:
            decl_type = getattr(decl, "type", "")
            raw_decl = _node_text(src_bytes, decl)
            name = _guess_identifier_text(src_bytes, decl).strip()
            if not name:
                # 无法识别名称就跳过（仍然不抛异常）
                continue

            if "class" in decl_type:
                ent = _mk_entity("Class", name, raw_decl)
                _add_entity(entities, ent)

                # 继承/实现：优先找常见子节点，找不到用 raw text 兜底
                # 结构化节点名可能包括：superclass、extends_clause、implements_clause、type_list
                extends_node = _find_first_child_by_type(decl, "extends_clause") or _find_first_child_by_type(
                    decl, "superclass"
                )
                implements_node = _find_first_child_by_type(decl, "implements_clause")

                if extends_node is not None:
                    for t in _extract_relation_targets_from_node_text(_node_text(src_bytes, extends_node)):
                        target = _mk_entity("Class", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "INHERITS",
                            evidence=_node_text(src_bytes, extends_node),
                        )
                else:
                    # raw 兜底：extends X
                    m = re.search(r"\bextends\s+([^({\n]+)", raw_decl)
                    if m:
                        for t in _extract_relation_targets_from_node_text(m.group(1)):
                            target = _mk_entity("Class", t, "")
                            _add_entity(entities, target)
                            _add_rel(
                                rels,
                                ent.entity_id,
                                target.entity_id,
                                "INHERITS",
                                evidence=m.group(0),
                            )

                if implements_node is not None:
                    for t in _extract_relation_targets_from_node_text(_node_text(src_bytes, implements_node)):
                        target = _mk_entity("Interface", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "IMPLEMENTS",
                            evidence=_node_text(src_bytes, implements_node),
                        )
                else:
                    m = re.search(r"\bimplements\s+([^({\n]+)", raw_decl)
                    if m:
                        for t in _extract_relation_targets_from_node_text(m.group(1)):
                            target = _mk_entity("Interface", t, "")
                            _add_entity(entities, target)
                            _add_rel(
                                rels,
                                ent.entity_id,
                                target.entity_id,
                                "IMPLEMENTS",
                                evidence=m.group(0),
                            )

                # 额外适配真实 .cj.d 中的 `<:` subtype 语法（OpenHarmony interface_sdk_cangjie 大量使用）
                # 约定：class 的 `<:` 列表第一个视为 INHERITS，其余视为 IMPLEMENTS（启发式）
                colon_supers = _parse_subtypes_from_colon_syntax(raw_decl)
                if colon_supers:
                    for idx, t in enumerate(colon_supers):
                        rel_type = "INHERITS" if idx == 0 else "IMPLEMENTS"
                        target_kind = "Class" if rel_type == "INHERITS" else "Interface"
                        target = _mk_entity(target_kind, t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            rel_type,
                            evidence=_split_decl_head(raw_decl),
                        )

            elif "interface" in decl_type:
                ent = _mk_entity("Interface", name, raw_decl)
                _add_entity(entities, ent)

                # interface 可能也支持继承（extends）
                extends_node = _find_first_child_by_type(decl, "extends_clause")
                if extends_node is not None:
                    for t in _extract_relation_targets_from_node_text(_node_text(src_bytes, extends_node)):
                        target = _mk_entity("Interface", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "INHERITS",
                            evidence=_node_text(src_bytes, extends_node),
                        )
                else:
                    m = re.search(r"\bextends\s+([^({\n]+)", raw_decl)
                    if m:
                        for t in _extract_relation_targets_from_node_text(m.group(1)):
                            target = _mk_entity("Interface", t, "")
                            _add_entity(entities, target)
                            _add_rel(
                                rels,
                                ent.entity_id,
                                target.entity_id,
                                "INHERITS",
                                evidence=m.group(0),
                            )

                # interface 的 `<:` 一般表示继承接口（全部记为 INHERITS）
                colon_supers = _parse_subtypes_from_colon_syntax(raw_decl)
                if colon_supers:
                    for t in colon_supers:
                        target = _mk_entity("Interface", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "INHERITS",
                            evidence=_split_decl_head(raw_decl),
                        )

            elif "function" in decl_type:
                ent = _mk_entity("Function", name, raw_decl)
                _add_entity(entities, ent)

                # RETURNS：优先找 return_type / type_annotation 等节点
                ret_node = _find_first_child_by_type(decl, "return_type") or _find_first_child_by_type(
                    decl, "type_annotation"
                )
                if ret_node is not None:
                    for t in _extract_relation_targets_from_node_text(_node_text(src_bytes, ret_node)):
                        target = _mk_entity("Concept", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "RETURNS",
                            evidence=_node_text(src_bytes, ret_node),
                        )
                else:
                    # 兜底：func f(...): RetType
                    m = re.search(r"\)\s*:\s*([^\s{;\n]+(?:\s*<[^>\n]+>)?)", raw_decl)
                    if m:
                        for t in _extract_relation_targets_from_node_text(m.group(1)):
                            target = _mk_entity("Concept", t, "")
                            _add_entity(entities, target)
                            _add_rel(
                                rels,
                                ent.entity_id,
                                target.entity_id,
                                "RETURNS",
                                evidence=m.group(0),
                            )

                # ACCEPTS_PARAM：优先找 parameter_list / parameters
                params_node = _find_first_child_by_type(decl, "parameter_list") or _find_first_child_by_type(
                    decl, "parameters"
                )
                if params_node is not None:
                    params_text = _node_text(src_bytes, params_node)
                    # 优先只抽取 `name: Type` 的 Type（避免把参数名当类型）
                    for t in _extract_param_types_from_signature(f"func {name}({params_text})"):
                        target = _mk_entity("Concept", t, "")
                        _add_entity(entities, target)
                        _add_rel(
                            rels,
                            ent.entity_id,
                            target.entity_id,
                            "ACCEPTS_PARAM",
                            evidence=params_text,
                        )
                else:
                    # 兜底：func f(a: T, b: Map<K,V>)
                    params_types = _extract_param_types_from_signature(raw_decl)
                    if params_types:
                        for t in params_types:
                            target = _mk_entity("Concept", t, "")
                            _add_entity(entities, target)
                            _add_rel(
                                rels,
                                ent.entity_id,
                                target.entity_id,
                                "ACCEPTS_PARAM",
                                evidence=_split_decl_head(raw_decl),
                            )

        except Exception as exc:
            # 单个声明节点失败不影响整体
            logger.debug(
                "parse_cjd_ast: failed to process decl node type=%s in %s: %s",
                getattr(decl, "type", "<unknown>"),
                (source_metadata or {}).get("file_path", "<unknown>"),
                exc,
                exc_info=True,
            )
            continue

    # 若使用 AST 遍历后仍然完全没有抽取到实体/关系，则退回纯文本兜底解析，避免轨道 2“哑火”。
    # 这样可以在保持 Tree-sitter 优先的前提下，最大化保证 .cj.d 至少产出一定的结构化信息。
    if not entities and not rels:
        logger.info(
            "parse_cjd_ast: AST traversal produced no entities/relationships; using fallback text parser for %s",
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return _fallback_parse_cjd_text(cjd_text, source_metadata)

    # 组装 DocumentGraph；孤儿关系静默过滤由 pydantic_schema.DocumentGraph 负责
    try:
        graph = DocumentGraph(
            entities=list(entities.values()),
            relationships=list(rels.values()),
            source_metadata=source_metadata or {},
        )
        logger.info(
            "parse_cjd_ast: AST traversal succeeded (entities=%d, relationships=%d) for %s",
            len(graph.entities),
            len(graph.relationships),
            (source_metadata or {}).get("file_path", "<unknown>"),
        )
        return graph
    except Exception as exc:
        logger.warning(
            "parse_cjd_ast: failed to build DocumentGraph from AST result for %s: %s; return empty graph",
            (source_metadata or {}).get("file_path", "<unknown>"),
            exc,
            exc_info=True,
        )
        return DocumentGraph(source_metadata=source_metadata or {})

