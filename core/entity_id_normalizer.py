from __future__ import annotations

import re
from typing import List, Tuple

"""
统一的 entity_id 归一化模块，确保跨轨道合并。

核心问题：
1. 命名空间完整性问题：`stdx.net.http` vs `net.http` vs `http`
2. 泛型写法差异：`ArrayDeque<T>` vs `ArrayDeque` vs `ArrayDeque_t_`
3. 大小写差异：`HttpRequest` vs `httprequest`

策略：
- 保留命名空间前缀（不自动补全，但统一格式）
- 泛型统一处理（移除或标准化）
- 统一转小写
"""

ID_NORMALIZE_REGEX = re.compile(r"[^\w:]", re.UNICODE)


def _strip_generics(name: str) -> Tuple[str, bool]:
    """
    移除泛型参数，返回 (基础名称, 是否有泛型)。
    
    示例：
    - "ArrayDeque<T>" -> ("ArrayDeque", True)
    - "HashMap<K, V>" -> ("HashMap", True)
    - "String" -> ("String", False)
    """
    if "<" not in name:
        return name, False
    
    # 找到第一个 < 和匹配的 >
    depth = 0
    start = name.find("<")
    if start == -1:
        return name, False
    
    for i in range(start, len(name)):
        if name[i] == "<":
            depth += 1
        elif name[i] == ">":
            depth -= 1
            if depth == 0:
                return name[:start].strip(), True
    
    # 未闭合的泛型，返回去掉 < 之后的部分
    return name[:start].strip(), True


def _normalize_namespace(name: str) -> str:
    """
    归一化命名空间写法，但不自动补全（避免误合并不同命名空间的同名实体）。
    
    策略：
    - 统一点号分隔符（去除多余空格）
    - 不自动补全缺失的命名空间前缀（如 net.http 不会自动变成 stdx.net.http）
    - 保留相对路径信息（如 ./path/to/file.md）
    """
    # 去除多余空格，统一点号/斜杠分隔
    normalized = re.sub(r"\s*[./]\s*", lambda m: m.group(0).strip(), name)
    normalized = re.sub(r"\s+", "", normalized)  # 移除所有空格
    return normalized


def normalize_entity_id(raw_id: str) -> str:
    """
    对 entity_id 做标准化，确保跨轨道合并。
    
    规则：
    1. 统一转小写
    2. 移除泛型参数（`ArrayDeque<T>` -> `arraydeque`）
    3. 保留命名空间结构（`stdx.net.http` -> `stdx_net_http`，不自动补全）
    4. 非法字符替换为下划线
    
    注意：
    - 不处理命名空间简写问题（如 `net.http` vs `stdx.net.http` 会被视为不同实体）
    - 这是设计选择：避免误合并不同命名空间的同名实体
    - 如果需要在更高层做命名空间补全，应该在生成 entity_id 之前处理
    """
    if not raw_id:
        return ""
    
    # 分离类型前缀和名称部分
    if ":" not in raw_id:
        # 没有类型前缀，直接处理名称
        name_part = raw_id
    else:
        type_part, name_part = raw_id.split(":", 1)
        type_part = type_part.strip().lower()
        name_part = name_part.strip()
    
    # 移除泛型参数
    base_name, _ = _strip_generics(name_part)
    
    # 归一化命名空间（统一点号/斜杠，但不补全）
    normalized_name = _normalize_namespace(base_name)
    
    # 组合：类型前缀（如果有）+ 归一化后的名称
    if ":" in raw_id:
        full_id = f"{type_part}:{normalized_name}"
    else:
        full_id = normalized_name
    
    # 转小写并替换非法字符
    lowered = full_id.lower()
    return ID_NORMALIZE_REGEX.sub("_", lowered)


def normalize_entity_id_with_namespace_hint(raw_id: str, namespace_hints: List[str] | None = None) -> str:
    """
    带命名空间提示的归一化（实验性）。
    
    如果 raw_id 中的名称部分缺少命名空间前缀，且 namespace_hints 中有匹配的候选，
    则尝试补全。
    
    示例：
    - raw_id="Module:net.http", namespace_hints=["stdx.net.http", "ohos.net.http"]
    - 如果上下文明确指向 stdx，可以补全为 "Module:stdx.net.http"
    
    注意：这个功能需要上下文信息，目前仅作为预留接口。
    """
    # 基础归一化
    base_normalized = normalize_entity_id(raw_id)
    
    # TODO: 如果 namespace_hints 可用，尝试智能补全
    # 这需要更复杂的上下文推理，暂时不实现
    
    return base_normalized
