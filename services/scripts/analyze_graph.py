#!/usr/bin/env python3
"""分析生成的图谱JSON文件"""

import json
from collections import Counter
from pathlib import Path

def analyze_graph(json_path: str):
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
    
    entities = data.get('entities', [])
    relationships = data.get('relationships', [])
    
    print("=" * 80)
    print("图谱统计")
    print("=" * 80)
    print(f"总实体数: {len(entities)}")
    print(f"总关系数: {len(relationships)}")
    
    # 实体类型统计
    entity_types = Counter(e.get('entity_type', 'Unknown') for e in entities)
    print("\n实体类型分布:")
    for etype, count in entity_types.most_common():
        print(f"  {etype}: {count}")
    
    # 关系类型统计
    rel_types = Counter(r.get('relation_type', 'Unknown') for r in relationships)
    print("\n关系类型分布:")
    for rtype, count in rel_types.most_common():
        print(f"  {rtype}: {count}")
    
    # 检查轨道2的实体（Class, Interface, Function）
    track2_entities = [e for e in entities if e.get('entity_type') in ('Class', 'Interface', 'Function')]
    print(f"\n轨道2实体数（Class/Interface/Function）: {len(track2_entities)}")
    
    # 检查轨道2的关系（INHERITS, IMPLEMENTS, RETURNS, ACCEPTS_PARAM）
    track2_rels = [r for r in relationships if r.get('relation_type') in ('INHERITS', 'IMPLEMENTS', 'RETURNS', 'ACCEPTS_PARAM')]
    print(f"轨道2关系数（INHERITS/IMPLEMENTS/RETURNS/ACCEPTS_PARAM）: {len(track2_rels)}")
    
    # 检查轨道1的实体（Concept, File）
    track1_entities = [e for e in entities if e.get('entity_type') in ('Concept', 'File')]
    print(f"\n轨道1实体数（Concept/File）: {len(track1_entities)}")
    
    # 检查轨道1的关系（DOCUMENTED_AT）
    track1_rels = [r for r in relationships if r.get('relation_type') == 'DOCUMENTED_AT']
    print(f"轨道1关系数（DOCUMENTED_AT）: {len(track1_rels)}")
    
    # 检查轨道3的实体（其他类型）
    track3_types = {'Module', 'Struct', 'Enum', 'Macro', 'Property', 'Exception', 'Keyword',
                    'UI_Component', 'UI_Modifier', 'Lifecycle_Hook', 'Permission', 'CLI_Command',
                    'Config_Option', 'CodeSnippet'}
    track3_entities = [e for e in entities if e.get('entity_type') in track3_types]
    print(f"\n轨道3实体数（LLM提取的其他类型）: {len(track3_entities)}")
    
    # 检查轨道2的样本实体
    if track2_entities:
        print("\n轨道2样本实体（前5个）:")
        for e in track2_entities[:5]:
            print(f"  [{e.get('entity_type')}] {e.get('entity_id')} - {e.get('name', '')[:50]}")
            content = e.get('content', '')
            if content:
                print(f"    content预览: {content[:100]}...")
    
    # 检查轨道2的样本关系
    if track2_rels:
        print("\n轨道2样本关系（前10个）:")
        for r in track2_rels[:10]:
            print(f"  {r.get('relation_type')}: {r.get('source_id', '')[:40]} -> {r.get('target_id', '')[:40]}")
    
    # 检查是否有空content的实体
    empty_content = [e for e in entities if not e.get('content', '').strip()]
    print(f"\n空content的实体数: {len(empty_content)}")
    if empty_content:
        empty_by_type = Counter(e.get('entity_type', 'Unknown') for e in empty_content)
        print("空content实体类型分布:")
        for etype, count in empty_by_type.most_common():
            print(f"  {etype}: {count}")
    
    # 检查sources分布
    presets = Counter()
    for e in entities:
        for src in e.get('sources', []):
            presets[src.get('preset', 'Unknown')] += 1
    print("\n实体来源Preset分布:")
    for preset, count in presets.most_common():
        print(f"  {preset}: {count}")

if __name__ == '__main__':
    import sys
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'test_graph.json'
    analyze_graph(json_path)
