# GraphDistill

**GraphDistill** 是一个面向技术文档的知识图谱蒸馏与智能问答系统，专为仓颉（Cangjie）语言生态设计。它将分散在多个代码仓库中的文档、源码和 API 说明，提炼成结构化的知识图谱，并通过语义检索与 LLM 推理实现高质量问答。
<img width="1908" height="947" alt="微信图片_20260320095725_394_63" src="https://github.com/user-attachments/assets/43426119-b27b-4d33-b889-c2b603abe9da" />


---

## 目录

1. [系统架构概览](#系统架构概览)
2. [知识图谱构建方法](#知识图谱构建方法)
   - [三轨提取流水线](#三轨提取流水线)
   - [图谱合并与去重](#图谱合并与去重)
   - [向量索引构建](#向量索引构建)
3. [图搜索方法](#图搜索方法)
   - [本地图搜索（Local Graph Search）](#本地图搜索)
   - [社会搜索（Global Community Search）](#社会搜索)
   - [自动路由（Auto Mode）](#自动路由)
4. [搜索优化策略](#搜索优化策略)
5. [数据源配置](#数据源配置)
6. [快速开始](#快速开始)
7. [文件结构说明](#文件结构说明)

---

## 系统架构概览

```
GraphDistill 系统架构
│
├─ 【数据采集层】
│   ├─ clone_or_get_repo()     克隆/复用远端 Git 仓库（去重优化）
│   └─ iter_source_files()     扫描文件并按类型路由
│
├─ 【三轨提取层】
│   ├─ 轨道1：index_parser.py  解析索引/总览 Markdown → 概念-文件关系
│   ├─ 轨道2：cjd_parser.py    解析 .cj/.cj.d 源码 → 类/函数继承实现关系
│   └─ 轨道3：extractor.py     LLM 提取 Markdown → 全类型实体与关系
│
├─ 【图谱构建层】
│   ├─ pydantic_schema.py      实体/关系类型定义与验证
│   ├─ entity_id_normalizer.py 统一实体 ID 规范化（跨轨道去重）
│   └─ graph_builder.py        NetworkX MultiDiGraph + FAISS 向量索引
│
└─ 【搜索与问答层】
    ├─ search_engine.py         双模搜索引擎（本地图搜索 + 社会搜索）
    ├─ search_main.py           搜索测试入口
    └─ serve.py                 服务入口
```

---

## 知识图谱构建方法

### 三轨提取流水线

GraphDistill 将文档分为三类，采用不同的提取策略：

#### 轨道1：索引解析（`index_parser.py`）

- **适用文件**：`*_overview.md`、`index.md` 等目录/总览页
- **解析逻辑**：提取页面中的超链接 `[名称](./路径.md#锚点)`，建立 `Concept → DOCUMENTED_AT → File` 关系
- **优点**：零 LLM 调用，高吞吐，精确覆盖模块结构
- **产出实体类型**：`Concept`、`File`

#### 轨道2：源码 AST 解析（`cjd_parser.py`）

- **适用文件**：`.cj`、`.cj.d` 仓颉源码及声明文件
- **解析策略**（瀑布式回退）：
  1. 本地 Tree-sitter AST（优先）
  2. 远端 AST 微服务（HTTP）
  3. 正则文本解析（兜底）
- **提取关系**：`INHERITS`、`IMPLEMENTS`、`RETURNS`、`ACCEPTS_PARAM`
- **产出实体类型**：`Class`、`Interface`、`Function`、`Struct`

#### 轨道3：LLM 深度提取（`extractor.py`）

- **适用文件**：常规技术文档 `.md`
- **提取逻辑**：
  - 滑动窗口分块（最大 4000 字符，300 字符重叠）
  - 调用 LLM 将每个 chunk 解析为结构化实体和关系
  - Pydantic 验证 + 代码片段物理核验
  - 解析失败时二叉递归拆分（最大深度 2）
- **产出实体类型**：全部 33 种（包括 `CodeSnippet`、`Concept`、`Permission` 等）

### 图谱合并与去重

- 每个文件产生一个 `DocumentGraph`，通过 `GraphBuilder.merge_document_graph()` 合并
- 合并规则：以 `entity_id`（规范化后的字符串）为主键去重
- `entity_id` 规范化（`entity_id_normalizer.py`）：
  - 移除泛型参数：`ArrayList<T>` → `arraylist`
  - 保留命名空间结构：`std.core.String` → `std_core_string`
  - 小写 + 非法字符替换为下划线
  - 格式：`type:normalized_name`（如 `class:std_core_string`）
- 内容合并：保留信息量更大（更长）的版本；`sources` 列表追加，保留全溯源链

### 向量索引构建

- 使用 `FAISS IndexFlatL2` 构建 L2 距离向量索引
- Embedding 模型：`BAAI/bge-m3`（通过 SiliconFlow OpenAI 兼容接口）
- 索引内容：所有实体节点的 `name + content`（截断至 256 字符）
- 持久化：向量矩阵与映射关系随图谱 JSON 一同序列化存储

---

## 图搜索方法

### 本地图搜索

**适用场景**：具体技术细节问题（函数用法、类的继承关系、异常触发条件等）

**搜索流程**（优化后）：

```
用户问题
    │
    ▼
① 向量编码（embedding_model）
    │
    ▼
② 多候选实体检索（FAISS top_k=3，过滤 distance > 1.5）
    │
    ▼
③ 多实体子图融合（每个候选实体做 1~2 跳 BFS）
    │  ├─ 综合得分 = sim_score × (1 + degree_centrality)
    │  └─ 节点过多时按得分截断（max_nodes=80）
    │
    ▼
④ 上下文构建（按综合得分排序，高分实体优先呈现给 LLM）
    │
    ▼
⑤ LLM 生成答案（基于排序后的图上下文）
    │
    ▼
⑥ 置信度评分（sim_score 50% + 高置信奖励 30% + 子图密度 20%）
```

**关键方法**：
- `_vector_route_intent_multi(top_k=3)` — 多候选向量路由
- `_collect_multi_entity_subgraph()` — 子图融合 + 重排序
- `_build_ranked_context()` — 按分排序的上下文构建
- `_compute_confidence()` — 置信度评分

### 社会搜索

**适用场景**：宏观架构问题（整体设计、模块间关系、技术选型原理等）

**搜索流程**：

```
用户问题
    │
    ▼
① 社区发现（Louvain / greedy_modularity_communities）
    │
    ▼
② 选取最大的 N 个社区（默认 max_communities=8）
    │
    ▼
③ 每个社区生成架构摘要（LLM）
    │
    ▼
④ 综合社区摘要回答宏观问题（LLM）
```

### 自动路由

`mode="auto"` 时根据以下启发式规则路由：

| 条件                                         | 路由目标                     |
| -------------------------------------------- | ---------------------------- |
| 问题包含"整体/架构/设计/原理/机制/总体/全局" | 优先全局搜索                 |
| 问题长度 > 80 字                             | 优先全局搜索                 |
| 其他情况                                     | 优先本地搜索，失败则回退全局 |
| 两者均成功                                   | Hybrid 模式（拼接两段答案）  |

---

## 搜索优化策略

相较于初始版本（`top_k=1` 单候选），本次引入以下优化：

| 优化维度         | 优化前              | 优化后                                      |
| ---------------- | ------------------- | ------------------------------------------- |
| **候选实体数量** | top_k=1，单一最近邻 | top_k=3，多候选融合                         |
| **上下文覆盖**   | 单实体子图          | 多实体子图合并（去重边）                    |
| **节点排序**     | 按 BFS 层次顺序     | 相似度 × 图中心性综合得分排序               |
| **结果可解释性** | 无置信度信息        | 0~1 置信度评分                              |
| **匹配溯源**     | 无                  | `matched_entities` 字段记录命中实体与距离   |
| **上下文提示**   | 无排序提示          | 告知 LLM 节点按相关性排序，优先引用高分实体 |

### 置信度计算公式

```
confidence = avg_sim × 0.5
           + (0.3 if any_distance < 0.5 else 0.0)
           + min(edge_count / node_count / 3.0, 1.0) × 0.2

其中 avg_sim = mean(1 / (1 + distance_i) for each candidate)
```

### 待进一步探索的方向

- **结果验证**：调用 LLM 对答案做一致性核查（答案是否与图谱矛盾）
- **动态 max_hops**：根据问题复杂度自动调整跳数（1~3 跳）
- **LLM 重排序**：对候选实体列表进行 LLM 二次打分
- **混合检索**：结合关键词 BM25 与向量检索的混合召回
- **增量更新**：支持图谱增量更新而不重建全量向量索引

---

## 数据源配置

系统内置 6 个数据源预设（`main.py` 中的 `DOC_PRESETS`）：

| 预设名称                | 仓库                  | 子目录                  | 说明                |
| ----------------------- | --------------------- | ----------------------- | ------------------- |
| `Cangjie_Guide`         | cangjie_docs          | `docs/dev-guide`        | 仓颉语言开发指南    |
| `Cangjie_Tools`         | cangjie_docs          | `docs/tools`            | 仓颉工具链文档      |
| `Cangjie_StdLib`        | cangjie_runtime       | `std/doc/libs`          | 仓颉标准库 API 文档 |
| `Cangjie_StdX`          | cangjie_stdx          | `doc`                   | 仓颉扩展库文档      |
| `HarmonyOS_Cangjie`     | docs_cangjie          | `zh-cn/application-dev` | HarmonyOS 应用开发  |
| `interface_sdk_cangjie` | interface_sdk_cangjie | `api`                   | HarmonyOS SDK API   |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# Linux/macOS
export SILICONFLOW_API_KEY="your_api_key_here"

# Windows PowerShell
$env:SILICONFLOW_API_KEY = "your_api_key_here"
```

### 3. 构建知识图谱（调试模式，每个源最多 5 个文件）

```bash
python main.py --debug 0
```

### 4. 运行搜索测试

```bash
# 使用内置测试用例
python search_main.py

# 生成完整测试报告（含 Cangjie 标准库相关问题）
python test_search_report.py

# 仅测试图结构（无需 API Key）
python test_search_report.py --skip-llm
```

### 5. 可视化图谱

用浏览器打开 `visualizer.html`，加载导出的 GraphML 文件。

---

## 文件结构说明

```
GraphDistill/
│
├─ main.py                  主流水线入口（克隆仓库 + 三轨提取 + 构建图谱）
├─ graph_builder.py         知识图谱构建引擎（NetworkX + FAISS）
├─ search_engine.py         双模搜索引擎（本地图搜索 + 社会搜索）
├─ search_main.py           搜索测试入口
├─ extractor.py             LLM 知识提取器（轨道3）
├─ cjd_parser.py            仓颉源码 AST 解析器（轨道2）
├─ index_parser.py          Markdown 索引解析器（轨道1）
├─ entity_id_normalizer.py  实体 ID 规范化
├─ pydantic_schema.py       实体/关系 Pydantic 模型定义
├─ serve.py                 HTTP 服务入口
│
├─ test_search_report.py    搜索优化测试脚本（生成 TEST_REPORT.md）
├─ test_core_extraction.py  核心提取测试脚本
├─ test_core_extraction_unified_std_api.json  测试提取结果样例
│
├─ scripts/
│   ├─ cjd_ast_service.py   WSL/Linux AST 微服务（HTTP）
│   ├─ test_three_tracks.py 三轨集成测试脚本
│   ├─ test_cjd_parser.py   CJD 解析器测试
│   ├─ debug_cjd_ast.py     AST 调试工具
│   └─ analyze_graph.py     图谱分析脚本
│
├─ visualizer.html          图谱可视化前端
├─ requirements.txt         Python 依赖
└─ SETUP_GUIDE.md           详细配置指南
```

A. 最快跑起来（不依赖 API Key）

安装 Python 3.10+ 与 Git。
在项目根目录创建虚拟环境并安装依赖：
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
启动可视化服务：
python serve.py
浏览器打开：
http://localhost:8000/visualizer.html

B. 跑完整 LLM 能力（需要 API Key）

先完成 A 的环境安装。
设置环境变量（PowerShell）：
$env:SILICONFLOW_API_KEY="你的Key"
直接体验问答：
python query.py
若要从头重建图谱（可选）：
python main.py --debug 0
然后按需构建向量版输出：
python build_vector_index.py --input test_graph.json --output test_graph_with_vectors.json