#!/usr/bin/env python3
"""测试特定目录下的文档提取"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from cjd_parser import parse_cjd_ast
from extractor import extract_graph_from_text
from graph_builder import GraphBuilder
from index_parser import parse_index_markdown
from main import BASE_URL, MODEL, iter_source_files, try_init_cangjie_language

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("test_core_extraction")

# 测试目录
TEST_DIR = Path(r"C:\Users\zqw\Desktop\GraphDistill\temp_repos\Cangjie_StdLib\std\doc\libs\std")


def _run_three_tracks_on_root(
    builder: GraphBuilder,
    client: OpenAI,
    test_dir: Path,
    limit: int | None = None,
) -> None:
    """
    针对“单个根目录”做三轨道知识图谱提取，逻辑尽量对齐 main.distill_docs：
      - 轨道 1：目录/索引页（overview/index 的 .md）
      - 轨道 2：.cj.d / .cj（Cangjie AST + 兜底）
      - 轨道 3：其他 .md（LLM 蒸馏）

    参数:
        builder: 复用的 GraphBuilder（允许多个根目录汇聚成一个统一图）
        client: 复用的 LLM 客户端（轨道 3 使用）
        test_dir: 要测试的根目录路径（相当于 main 里的 repo_root/subdir）
        limit: 限制处理的源文件数量（None 表示处理所有文件）
    """
    # 检查目录是否存在
    if not test_dir.exists():
        logger.error("Directory not found: %s", test_dir)
        return
    
    if not test_dir.is_dir():
        logger.error("Path is not a directory: %s", test_dir)
        return
    
    # 用与 main.iter_source_files 一致的扫描逻辑，拿到三轨道混合的“源文件列表”
    src_files: List[Path] = iter_source_files(test_dir, subdir=".", limit=limit)
    
    logger.info("=" * 80)
    logger.info("测试目录: %s", test_dir)
    logger.info("找到源文件总数(.md/.cj/.cj.d): %d", len(src_files))
    logger.info("=" * 80)
    
    # 统计信息
    total_entities = 0
    total_relationships = 0
    failed_files = []
    track1_count = 0
    track2_count = 0
    track3_count = 0

    # Tree-sitter Cangjie Language 初始化（可选，本地 AST 优先；否则走远程微服务 + 兜底）
    try:
        cangjie_lang = try_init_cangjie_language()
    except Exception:
        cangjie_lang = None
    
    # 处理每个源文件（可能是 .md / .cj / .cj.d）
    for i, src_file in enumerate(src_files, 1):
        logger.info("\n" + "-" * 80)
        logger.info("[%d/%d] 处理文件: %s", i, len(src_files), src_file)
        logger.info("-" * 80)
        
        try:
            # 读取文件内容
            text = src_file.read_text(encoding="utf-8", errors="ignore")
            logger.info("文件大小: %d 字符", len(text))
            
            # 提取图谱
            source_metadata: Dict[str, Any] = {
                "test": True,
                "file_path": str(src_file),
                "test_dir": str(test_dir),
            }

            lower_name = src_file.name.lower()

            # Track 1：索引/概览页（overview/index.md）
            if src_file.suffix.lower() == ".md" and ("overview" in lower_name or "index" in lower_name):
                doc_graph = parse_index_markdown(md_text=text, source_metadata=source_metadata)
                track1_count += 1

            # Track 2：Cangjie AST（.cj.d / .cj）
            elif lower_name.endswith(".cj.d") or src_file.suffix.lower() == ".cj":
                # 这里不再“直接空图跳过”，而是交给 parse_cjd_ast 自己决定：
                # - 若 cangjie_lang 非 None：本地 Tree-sitter AST
                # - 若 None：优先远程微服务，其次兜底正则解析
                doc_graph = parse_cjd_ast(
                    cjd_text=text,
                    source_metadata=source_metadata,
                    cangjie_lang=cangjie_lang,
                )
                track2_count += 1

            # Track 3：常规 Markdown（其他 .md）
            elif src_file.suffix.lower() == ".md":
                doc_graph = extract_graph_from_text(
                    client=client,
                    model=MODEL,
                    markdown_text=text,
                    source_metadata=source_metadata,
                )
                track3_count += 1
            else:
                # 其他文件类型（理应不会出现），直接跳过
                logger.info("Skipping unsupported file type: %s", src_file)
                continue
            
            # 合并到全局图谱
            builder.merge_document_graph(doc_graph)
            
            # 统计结果
            entities_count = len(doc_graph.entities)
            relationships_count = len(doc_graph.relationships)
            total_entities += entities_count
            total_relationships += relationships_count
            
            logger.info("提取结果:")
            logger.info("  实体数: %d", entities_count)
            logger.info("  关系数: %d", relationships_count)
            
            # 显示前几个实体
            if doc_graph.entities:
                logger.info("\n  前5个实体:")
                for entity in doc_graph.entities[:5]:
                    logger.info("    - %s (%s): %s", entity.entity_id, entity.entity_type, entity.name[:50])
            
            # 显示前几个关系
            if doc_graph.relationships:
                logger.info("\n  前5个关系:")
                for rel in doc_graph.relationships[:5]:
                    logger.info("    - %s -> %s (%s)", rel.source_id, rel.target_id, rel.relation_type)
            
        except Exception as exc:
            logger.error("处理文件失败: %s", exc, exc_info=True)
            failed_files.append((src_file, str(exc)))
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("提取总结")
    logger.info("=" * 80)
    logger.info("处理文件数: %d", len(src_files))
    logger.info("成功: %d", len(src_files) - len(failed_files))
    logger.info("失败: %d", len(failed_files))
    logger.info("总实体数: %d", total_entities)
    logger.info("总关系数: %d", total_relationships)
    logger.info(
        "轨道计数: track1(index/overview)= %d, track2(.cj/.cj.d)= %d, track3(other .md)= %d",
        track1_count,
        track2_count,
        track3_count,
    )
    
    if failed_files:
        logger.info("\n失败的文件:")
        for md_file, error in failed_files:
            logger.info("  - %s: %s", md_file.name, error)
    

def test_directory_extraction(test_dir: Path, limit: int | None = None) -> None:
    """
    针对“单个根目录”做三轨道知识图谱提取（保持向后兼容的原有入口）。
    """
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    if not api_key:
        logger.error("SILICONFLOW_API_KEY is not set!")
        return

    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    builder = GraphBuilder()

    _run_three_tracks_on_root(builder=builder, client=client, test_dir=test_dir, limit=limit)

    # 单目录模式下，仍然为该目录各自输出一个 JSON
    output_path = Path(f"test_core_extraction_{test_dir.name}.json")
    logger.info("\n" + "=" * 80)
    logger.info("保存结果到: %s", output_path)
    logger.info("=" * 80)
    try:
        builder.save_json(output_path)
        logger.info("结果已保存到: %s", output_path.absolute())
        final_stats = builder.stats_report()
        logger.info("最终图谱统计: %s", final_stats)
    except Exception as exc:
        logger.error("保存结果失败: %s", exc, exc_info=True)


def test_std_and_api_unified(limit: int | None = None) -> None:
    """
    针对两个关键根目录构建“统一图谱”：
      1) temp_repos/Cangjie_StdLib/std/doc/libs/std
      2) temp_repos/interface_sdk_cangjie/api

    二者共用同一个 GraphBuilder 和同一个 LLM 客户端。
    """
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    if not api_key:
        logger.error("SILICONFLOW_API_KEY is not set!")
        return

    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    builder = GraphBuilder()

    std_root = Path(r"C:\Users\zqw\Desktop\GraphDistill\temp_repos\Cangjie_StdLib\std\doc\libs\std")
    api_root = Path(r"C:\Users\zqw\Desktop\GraphDistill\temp_repos\interface_sdk_cangjie\api")

    _run_three_tracks_on_root(builder=builder, client=client, test_dir=std_root, limit=limit)
    _run_three_tracks_on_root(builder=builder, client=client, test_dir=api_root, limit=limit)

    # 统一图谱输出为一个 JSON
    output_path = Path("test_core_extraction_unified_std_api.json")
    logger.info("\n" + "=" * 80)
    logger.info("保存统一图谱结果到: %s", output_path)
    logger.info("=" * 80)
    try:
        builder.save_json(output_path)
        logger.info("统一图谱结果已保存到: %s", output_path.absolute())
        final_stats = builder.stats_report()
        logger.info("统一图谱最终统计: %s", final_stats)
    except Exception as exc:
        logger.error("保存统一结果失败: %s", exc, exc_info=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试特定目录或统一 std+api 图谱的文档提取")
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help=(
            "要测试的目录路径；"
            "若省略该参数，则默认对 Cangjie_StdLib/std/doc/libs/std 和 interface_sdk_cangjie/api "
            "两个目录构建统一图谱"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理的文件数量（默认: 处理所有文件）",
    )
    
    args = parser.parse_args()

    if args.dir:
        test_directory_extraction(Path(args.dir), limit=args.limit)
    else:
        # 不传 --dir 时，默认跑“std 文档 + interface_sdk_cangjie API”的统一三轨道图谱
        test_std_and_api_unified(limit=args.limit)
