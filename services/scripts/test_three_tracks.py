#!/usr/bin/env python3
"""
三轨道集成测试脚本（低成本调试版）。

用途：
  - 只处理少量文件，验证三轨道路由和合并逻辑
  - 支持跳过 LLM 调用（轨道3），只测试轨道1和轨道2
  - 输出详细的轨道统计和样本实体/关系

使用方式：
  python scripts/test_three_tracks.py [--skip-llm] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 确保能导入项目根目录的模块（将项目根目录提前插入 sys.path）
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openai import OpenAI

from core.cjd_parser import parse_cjd_ast
from core.extractor import extract_graph_from_text
from core.graph_builder import GraphBuilder
from core.index_parser import parse_index_markdown
from main import BASE_URL, MODEL, try_init_cangjie_language

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("test_three_tracks")

# 测试用的少量文件样本（覆盖三轨道）
TEST_SAMPLES = {
    "track1": [
        # 轨道1：overview/index 文件
        Path("temp_repos/Cangjie_StdLib/std/doc/libs/std/collection/collection_package_overview.md"),
        Path("temp_repos/Cangjie_StdLib/std/doc/libs/std/ast/ast_package_overview.md"),
    ],
    "track2": [
        # 轨道2：.cj.d 声明文件
        Path("temp_repos/interface_sdk_cangjie/api/NetworkKit/ohos.net.http.cj.d"),
        Path("temp_repos/interface_sdk_cangjie/api/Cangjie/third_party/std/std.collection.cj.d"),
    ],
    "track3": [
        # 轨道3：普通 .md 文档（可选，如果 --skip-llm 则跳过）
        Path("temp_repos/Cangjie_StdLib/std/doc/libs/std/collection/collection_package_overview.md"),
    ],
}


def process_file_track1(file_path: Path, builder: GraphBuilder) -> bool:
    """处理轨道1：目录/overview 文件"""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        source_metadata = {
            "test": True,
            "file_path": str(file_path),
            "track": "track1",
        }
        doc_graph = parse_index_markdown(text, source_metadata)
        builder.merge_document_graph(doc_graph)
        logger.info(
            "Track1: %s -> %d entities, %d relationships",
            file_path.name,
            len(doc_graph.entities),
            len(doc_graph.relationships),
        )
        return True
    except Exception as exc:
        logger.error("Track1 failed for %s: %s", file_path, exc, exc_info=True)
        return False


def process_file_track2(file_path: Path, builder: GraphBuilder, cangjie_lang) -> bool:
    """处理轨道2：.cj.d 声明文件"""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        source_metadata = {
            "test": True,
            "file_path": str(file_path),
            "track": "track2",
        }
        doc_graph = parse_cjd_ast(text, source_metadata, cangjie_lang)
        builder.merge_document_graph(doc_graph)
        logger.info(
            "Track2: %s -> %d entities, %d relationships",
            file_path.name,
            len(doc_graph.entities),
            len(doc_graph.relationships),
        )
        return True
    except Exception as exc:
        logger.error("Track2 failed for %s: %s", file_path, exc, exc_info=True)
        return False


def process_file_track3(file_path: Path, builder: GraphBuilder, client: OpenAI, model: str) -> bool:
    """处理轨道3：普通 .md 文档（LLM 蒸馏）"""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        source_metadata = {
            "test": True,
            "file_path": str(file_path),
            "track": "track3",
        }
        doc_graph = extract_graph_from_text(
            client=client,
            model=model,
            markdown_text=text,
            source_metadata=source_metadata,
        )
        builder.merge_document_graph(doc_graph)
        logger.info(
            "Track3: %s -> %d entities, %d relationships",
            file_path.name,
            len(doc_graph.entities),
            len(doc_graph.relationships),
        )
        return True
    except Exception as exc:
        logger.error("Track3 failed for %s: %s", file_path, exc, exc_info=True)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="三轨道集成测试（低成本调试版）")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过轨道3（LLM 调用），只测试轨道1和轨道2",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制每个轨道处理的文件数量（默认：使用 TEST_SAMPLES 中的全部）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_three_tracks_output.json",
        help="输出 JSON 文件路径（默认：test_three_tracks_output.json）",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    builder = GraphBuilder()

    # 初始化轨道2的 AST 语言（尝试，失败不影响）
    cangjie_lang = try_init_cangjie_language()
    if cangjie_lang:
        logger.info("Track2: Cangjie Tree-sitter language initialized (local)")
    else:
        logger.info("Track2: Will use remote AST service or fallback parsing")

    # 初始化轨道3的 LLM 客户端（如果启用）
    client = None
    if not args.skip_llm:
        api_key = os.getenv("SILICONFLOW_API_KEY", "")
        if not api_key:
            logger.warning("SILICONFLOW_API_KEY not set; Track3 will be skipped")
            args.skip_llm = True
        else:
            client = OpenAI(base_url=BASE_URL, api_key=api_key)

    track1_count = 0
    track2_count = 0
    track3_count = 0
    track1_success = 0
    track2_success = 0
    track3_success = 0

    # 处理轨道1
    logger.info("=" * 80)
    logger.info("Track 1: Index/Overview Markdown files")
    logger.info("=" * 80)
    track1_files = TEST_SAMPLES["track1"]
    if args.limit:
        track1_files = track1_files[: args.limit]
    for file_path in track1_files:
        full_path = root / file_path
        if not full_path.exists():
            logger.warning("Track1 file not found: %s", full_path)
            continue
        track1_count += 1
        if process_file_track1(full_path, builder):
            track1_success += 1

    # 处理轨道2
    logger.info("=" * 80)
    logger.info("Track 2: Cangjie declaration files (.cj.d)")
    logger.info("=" * 80)
    track2_files = TEST_SAMPLES["track2"]
    if args.limit:
        track2_files = track2_files[: args.limit]
    for file_path in track2_files:
        full_path = root / file_path
        if not full_path.exists():
            logger.warning("Track2 file not found: %s", full_path)
            continue
        track2_count += 1
        if process_file_track2(full_path, builder, cangjie_lang):
            track2_success += 1

    # 处理轨道3（如果启用）
    if not args.skip_llm and client:
        logger.info("=" * 80)
        logger.info("Track 3: Regular Markdown files (LLM distillation)")
        logger.info("=" * 80)
        track3_files = TEST_SAMPLES["track3"]
        if args.limit:
            track3_files = track3_files[: args.limit]
        for file_path in track3_files:
            full_path = root / file_path
            if not full_path.exists():
                logger.warning("Track3 file not found: %s", full_path)
                continue
            track3_count += 1
            if process_file_track3(full_path, builder, client, MODEL):
                track3_success += 1
    else:
        logger.info("Track 3: Skipped (--skip-llm or no API key)")

    # 输出统计
    logger.info("=" * 80)
    logger.info("Test Summary")
    logger.info("=" * 80)
    logger.info("Track 1 (Index/Overview): %d/%d files processed", track1_success, track1_count)
    logger.info("Track 2 (CJD AST): %d/%d files processed", track2_success, track2_count)
    logger.info("Track 3 (LLM): %d/%d files processed", track3_success, track3_count)

    stats = builder.stats_report()
    logger.info("Final graph stats: %s", stats)

    # 显示样本实体和关系
    all_entities = list(builder._entities.values())
    all_rels = []
    for key, evidences in builder._relationship_evidence.items():
        source_id, target_id, rel_type = key
        all_rels.append((source_id, target_id, rel_type))

    logger.info("=" * 80)
    logger.info("Sample Entities (first 10):")
    for i, ent in enumerate(all_entities[:10], 1):
        logger.info("  %d. [%s] %s :: %s", i, ent.entity_type, ent.entity_id, ent.name[:60])

    logger.info("=" * 80)
    logger.info("Sample Relationships (first 15):")
    for i, (src, tgt, rel_type) in enumerate(all_rels[:15], 1):
        logger.info("  %d. %s: %s -> %s", i, rel_type, src[:50], tgt[:50])

    # 保存结果
    output_path = root / args.output
    builder.save_json(output_path)
    logger.info("=" * 80)
    logger.info("Graph saved to: %s", output_path.absolute())


if __name__ == "__main__":
    main()

