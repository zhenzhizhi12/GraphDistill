from __future__ import annotations

from typing import Any, List, Literal

from pydantic import BaseModel, Field, model_validator


EntityType = Literal[
    # 代码结构相关
    "File",
    "Module",
    "Class",
    "Struct",
    "Interface",
    "Enum",
    "Macro",
    "Function",
    "Property",
    "Exception",
    # 抽象语义相关
    "Concept",
    "Keyword",
    # UI / 交互相关
    "UI_Component",
    "UI_Modifier",
    "Lifecycle_Hook",
    "Permission",
    # 运行与配置相关
    "CLI_Command",
    "Config_Option",
    # 代码片段相关
    "CodeSnippet",
]
"""
在“仓颉 / 鸿蒙”技术语境下的实体类型枚举。

- Module: 逻辑或物理上的模块边界，可对应 OpenHarmony/鸿蒙子系统或仓颉包（package）。
- Class: 面向对象类型定义，承载状态与行为，常用于 OpenHarmony 业务能力建模。
- Struct: 值语义的数据结构，一般用于跨进程 / NDK / FFI 结构体描述。
- Interface: 稳定抽象契约，例如系统服务接口、Ability/Service 的协议定义。
- Enum: 离散枚举类型，例如状态机状态、错误码、系统配置枚举值。
- Macro: 预处理或编译期宏，用于平台差异控制、特性开关等。
- Function: 具体可调用逻辑单元，既包括普通函数也包括静态/成员方法。
- Property: 可读写属性或字段，对应类/结构体中的成员，可能带有访问控制。
- Exception: 异常或错误类型，用于描述运行时失败语义。

- Concept: 抽象概念，例如“分布式软总线”“原子化服务”“Ability”等领域术语。
- Keyword: 语言关键字或框架保留字，例如仓颉语言关键字、配置 DSL 关键字。

- UI_Component: UI 组件，例如 ArkUI 组件、HarmonyOS 控件、自定义视图。
- UI_Modifier: UI 修饰器/装饰器，用于在不改变组件本体的情况下叠加行为或样式。
- Lifecycle_Hook: 生命周期钩子，如 Ability/Page/组件的 onStart/onActive/onDestroy 等。
- Permission: 鉴权权限点，例如系统能力（system ability）权限、应用运行时权限。

- CLI_Command: 命令行指令，如构建工具、调试工具、项目脚手架命令。
- Config_Option: 配置项/配置键，如 profile.json、module.json5 或系统配置中的 key。

- CodeSnippet: 代码片段或示例，用于承载文档中的示例代码或局部实现。
"""


RelationType = Literal[
    "BELONGS_TO",
    "DOCUMENTED_AT",
    "INHERITS",
    "IMPLEMENTS",
    "ACCEPTS_PARAM",
    "RETURNS",
    "THROWS",
    "CALLS",
    "CONTAINS",
    "MODIFIED_BY",
    "TRIGGERS_EVENT",
    "DEPENDS_ON",
    "CONFIGURES",
    "HAS_SAMPLE_CODE",
]
"""
图中关系类型的语义说明（有向边，均从 source 指向 target）。

- BELONGS_TO: 从“成员/子节点”指向“所属/父节点”，如 Function → Class、Module 中的文件。
- IMPLEMENTS: 实现关系，如 Class → Interface，或 Struct → 接口约定。
- ACCEPTS_PARAM: 参数依赖关系，如 Function → Type（参数类型）或 Function → Concept（语义参数）。
- RETURNS: 返回值关系，如 Function → Type / Concept，表示输出的数据或语义。
- THROWS: 异常抛出关系，如 Function → Exception。
- CALLS: 调用关系，如 Function → Function，表示在调用图中的直接调用。
- CONTAINS: 包含关系，如 Module → Class、Class → Property、文档 → CodeSnippet。
- MODIFIED_BY: 被修改/影响关系，如 Config_Option → Behavior，或 UI_Component → UI_Modifier。
- TRIGGERS_EVENT: 触发事件关系，如 UI_Component / Lifecycle_Hook → Event Handler。
- DEPENDS_ON: 依赖关系，通常表示编译期或运行期依赖，如 Module → Library、Service → Permission。
- CONFIGURES: 配置关系，如 Config_Option → Module / Service / Feature。
- HAS_SAMPLE_CODE: 文档或实体到代码示例的关系，如 Concept / Function → CodeSnippet。
"""


class Entity(BaseModel):
    """
    文档蒸馏后的原子实体节点。

    该模型作为 GraphDistill 的“最小语义单位”，每个实体必须是可独立指认的知识点，
    可以映射到仓颉/鸿蒙生态中的类、模块、配置项、权限点或抽象概念。
    """

    entity_id: str = Field(
        ...,
        description=(
            "实体的全局唯一标识符，用于在图结构中引用。"
            "建议使用稳定、可读且在跨文档场景中不易碰撞的 ID，例如：'类型:名称'（如 'UI_Component:Button'）。"
        ),
    )
    entity_type: EntityType = Field(
        ...,
        description="实体的类型标签，用于下游任务（如可视化、检索、推理）做语义区分。",
    )
    name: str = Field(
        ...,
        description="实体的人类可读名称，例如类名、配置项名或概念名。",
    )
    content: str = Field(
        ...,
        description="与实体关联的详细说明或正文，可包含简要描述、代码节选等。",
    )


class Relationship(BaseModel):
    """
    图中的有向边，用于表达两个实体之间的语义关系。

    注意：关系只在 `DocumentGraph` 中做一致性检查，孤立关系会被静默过滤。
    """

    source_id: str = Field(
        ...,
        description="关系起点实体的 ID，必须能在 `DocumentGraph.entities` 中找到对应实体。",
    )
    target_id: str = Field(
        ...,
        description="关系终点实体的 ID，必须能在 `DocumentGraph.entities` 中找到对应实体。",
    )
    relation_type: RelationType = Field(
        ...,
        description="关系的语义类型，详见 `RelationType` 的枚举说明。",
    )
    evidence: str = Field(
        ...,
        description=(
            "支持该关系的证据文本，例如原始文档片段、注释内容或代码位置描述；"
            "用于追溯与解释 LLM 抽取出的知识图谱边。"
        ),
    )


class DocumentGraph(BaseModel):
    """
    单个文档（或文档片段）对应的知识图谱视图。

    - `entities`: 该文档中被识别出的所有原子实体。
    - `relationships`: 实体之间的有向边，构成局部知识结构。

    该模型实现“静默过滤”策略：在构建阶段自动剔除引用不存在实体的孤儿关系，
    以提高对 LLM 局部错误的容错性，避免因为单条错误关系而导致整体文档蒸馏失败。
    """

    entities: List[Entity] = Field(
        default_factory=list,
        description="该文档中抽取出的所有实体节点。",
    )
    relationships: List[Relationship] = Field(
        default_factory=list,
        description="实体间的有向关系边，将在构建时自动过滤掉引用不存在实体的孤儿关系。",
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "文档溯源元数据，例如 {'file_path': '…', 'repo': '…', 'commit': '…'}，"
            "用于全局搜索与跨文件摘要时进行来源说明与可信度增强。"
        ),
    )

    @model_validator(mode="after")
    def _filter_orphan_relationships(self) -> "DocumentGraph":
        """
        在模型实例化后执行的校验逻辑。

        策略：静默过滤所有“孤儿关系”——即 source_id 或 target_id
        不在当前 `entities` 列表中的 `Relationship` 实例。

        这样可以：
        - 保留尽可能多的正确实体与关系；
        - 在 LLM 产生部分错误引用时自动降级，而不是让整个解析/校验过程失败；
        - 为后续图谱合并与推理提供更稳健的基础。
        """
        if not self.entities or not self.relationships:
            # 无实体或无关系时，无需处理
            return self

        valid_ids = {entity.entity_id for entity in self.entities}

        self.relationships = [
            rel
            for rel in self.relationships
            if rel.source_id in valid_ids and rel.target_id in valid_ids
        ]

        return self


__all__ = ["EntityType", "RelationType", "Entity", "Relationship", "DocumentGraph"]

