# GraphDistill 搜索优化测试报告

> 生成时间：2026-03-16 02:48:08

本报告涵盖两个核心数据源的知识检索测试：
- **Cangjie_StdLib**：`cangjie_runtime.git` (branch: release/1.0, subdir: std/doc/libs)
- **interface_sdk_cangjie**：`interface_sdk_cangjie.git` (branch: master, subdir: api)

## 1. 知识图谱概览

| 指标 | 值 |
|------|-----|
| 实体数量 | 12726 |
| 关系数量 | 19871 |
| 弱连通分量数 | 1435 |
| 向量索引 | ❌ 未构建（需运行 build_vector_index.py） |
| Embedding 模型 | Qwen/Qwen3-Embedding-8B |

## 2. 图结构验证

通过 9/9 项结构验证。

| 测试类型 | 通过 | 详情 |
|----------|------|------|
| entity_exists | ✅ | Entity 'concept:core' found in graph |
| entity_exists | ✅ | Entity 'concept:argopt' found in graph |
| entity_exists | ✅ | Entity 'concept:binary' found in graph |
| entity_exists | ✅ | Entity 'concept:ast' found in graph |
| entity_exists | ✅ | Entity 'concept:math' found in graph |
| entity_exists | ✅ | Entity 'concept:collection' found in graph |
| entity_type_distribution | ✅ | Entity types: {'Function': 6005, 'Concept': 1754, 'Property': 1206, 'Class': 1185, 'CodeSnippet': 996, 'Interface': 394, 'Enum': 321, 'Struct': 224, 'File': 203, 'Exception': 120} |
| relation_type_distribution | ✅ | Relation types: {'RETURNS': 5907, 'ACCEPTS_PARAM': 5060, 'BELONGS_TO': 2488, 'DOCUMENTED_AT': 1288, 'THROWS': 1248, 'IMPLEMENTS': 1002, 'HAS_SAMPLE_CODE': 931, 'MODIFIED_BY': 554, 'CONTAINS': 529, 'DEPENDS_ON': 305} |
| source_distribution | ✅ | Source presets: {'Cangjie_StdLib': 9883, 'interface_sdk_cangjie': 2843} |

## 3. 关键词回退检索测试（无 LLM）

验证在向量索引不可用时，关键词回退逻辑（`_keyword_fallback_candidates`）能否定位到正确的图谱实体。

**通过率**: 6/6

| ID | 问题 | 通过 | 期望关键词 | 命中 | Top-3候选实体 |
|----|------|------|-----------|------|--------------|
| kw_01 | 怎么将字符串中的浮点数转为Float64类型？ | ✅ | float64, parse | float64, parse | function:std_convert_float64_parse(d=0.01) \| function:std_convert_float64_tryparse(d=0.01) \| property:std_float64_inf(d=1.01) |
| kw_02 | IncompatiblePackageException 在什么场景下会被抛出？ | ✅ | incompatiblepackageexception | incompatiblepackageexception | function:incompatiblepackageexception_init(d=0.01) \| function:incompatiblepackageexception_init_string_(d=0.01) \| concept:incompatiblepackageexception(d=1.01) |
| kw_03 | 仓颉语言中如何使用 ArrayList 存储和遍历元素？ | ✅ | arraylist | arraylist | class:std_ast_arraylist(d=0.01) \| property:std_collection_arraylist_first(d=0.01) \| property:std_collection_arraylist_last(d=0.01) |
| kw_04 | Button 组件的 onClick 事件如何触发？ | ✅ | button, onclick | button, onclick | class:buttoninfo(d=0.01) \| class:alertdialogbuttonbaseoptions(d=0.01) \| class:buttonoptions(d=0.01) |
| kw_05 | 如何使用 Float64 类型的 parse 方法从字符串中解析浮点数？ | ✅ | float64, parse | float64, parse | function:std_convert_float64_parse(d=0.01) \| function:std_convert_float64_tryparse(d=0.01) \| function:std_reflect_parseparametertypes(d=1.01) |
| kw_06 | HashMap 如何存储和查找键值对？ | ✅ | hashmap | hashmap | function:std_collection_hashmap_init_elements(d=0.01) \| function:std_collection_hashmap_init_collection(d=0.01) \| function:std_collection_hashmap_add_collection(d=0.01) |

## 4. 搜索问答测试

> ⚠️ 搜索测试已跳过（未提供 SILICONFLOW_API_KEY 或使用了 --skip-llm）。
> 如需完整测试，请按以下步骤操作：
> 
> 1. 设置 API Key：`export SILICONFLOW_API_KEY=<your_key>`
> 2. 构建向量索引：`python build_vector_index.py`
> 3. 运行完整测试：`python test_search_report.py`

## 5. 搜索优化策略总结

本次对 `search_engine.py`、`main.py`、`test_search_report.py` 进行了以下优化：

| 优化点 | 实现方式 | 预期效果 |
|--------|----------|----------|
| 多候选实体检索 | `_vector_route_intent_multi(top_k=3)` | 避免只取 top-1 时遗漏相关实体，提升召回率 |
| 多实体子图融合 | `_collect_multi_entity_subgraph` | 合并多个候选实体的 1~2 跳邻居，丰富上下文 |
| 相似度 × 中心性重排序 | 综合得分 = sim_score × (1 + degree_centrality) | 让最相关且图中最重要的实体优先被 LLM 看到 |
| 置信度评分 | `_compute_confidence`（相似度+高置信奖励+子图密度） | 为答案提供可解释的置信度指标 |
| 上下文节点数量控制 | `max_nodes=80` 截断策略 | 防止 context 过长超出 LLM 窗口，保留高分节点 |
| 向后兼容 | `_vector_route_intent` 委托给多候选版本 | 不破坏现有调用代码，平滑升级 |
| 关键词回退检索（新增） | `_keyword_fallback_candidates`：名称命中权重3，内容命中权重1 | 向量索引不可用时自动降级，保证本地搜索不会空返回 |
