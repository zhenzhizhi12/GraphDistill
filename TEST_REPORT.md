# GraphDistill 搜索优化测试报告

> 生成时间：2026-03-16 02:11:12

## 1. 知识图谱概览

| 指标 | 值 |
|------|-----|
| 实体数量 | 12726 |
| 关系数量 | 19871 |
| 弱连通分量数 | 1435 |
| 向量索引 | 未构建 |

## 2. 图结构验证

通过 8/8 项结构验证。

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

## 3. 搜索问答测试

> ⚠️ 搜索测试已跳过（未提供 SILICONFLOW_API_KEY 或使用了 --skip-llm）。
> 请设置 `SILICONFLOW_API_KEY` 环境变量后重新运行以获取完整测试结果。

## 4. 搜索优化策略总结

本次对 `search_engine.py` 进行了以下优化，旨在提升回答质量和覆盖度：

| 优化点 | 实现方式 | 预期效果 |
|--------|----------|----------|
| 多候选实体检索 | `_vector_route_intent_multi(top_k=3)` | 避免只取 top-1 时遗漏相关实体，提升召回率 |
| 多实体子图融合 | `_collect_multi_entity_subgraph` | 合并多个候选实体的 1~2 跳邻居，丰富上下文 |
| 相似度 × 中心性重排序 | 综合得分 = sim_score × (1 + degree_centrality) | 让最相关且图中最重要的实体优先被 LLM 看到 |
| 置信度评分 | `_compute_confidence`（相似度+高置信奖励+子图密度） | 为答案提供可解释的置信度指标 |
| 上下文节点数量控制 | `max_nodes=80` 截断策略 | 防止 context 过长超出 LLM 窗口，保留高分节点 |
| 向后兼容 | `_vector_route_intent` 委托给多候选版本 | 不破坏现有调用代码，平滑升级 |
