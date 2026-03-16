"""
build_vector_index.py
=====================
基于现有的知识图谱 JSON 文件，调用 SiliconFlow Embedding 接口构建 FAISS 向量索引，
并将结果（图谱数据 + 向量索引）保存到新的 JSON 文件，作为后续查询的数据源。

用法：
    # 必须先设置 API Key（或通过 --api-key 参数传入）
    export SILICONFLOW_API_KEY=sk-...
    python build_vector_index.py

    # 指定输入/输出文件与嵌入模型
    python build_vector_index.py \\
        --input test_core_extraction_unified_std_api.json \\
        --output test_graph_with_vectors.json \\
        --embedding-model Qwen/Qwen3-Embedding-8B

默认值：
    --input   : test_core_extraction_unified_std_api.json
    --output  : test_graph_with_vectors.json
    --embedding-model : Qwen/Qwen3-Embedding-8B（可通过环境变量 GRAPHDISTILL_EMBEDDING_MODEL 覆盖）
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from openai import OpenAI

from graph_builder import GraphBuilder
from main import BASE_URL, EMBEDDING_MODEL as DEFAULT_EMBEDDING_MODEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("graphdistill.build_vector_index")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="为已有知识图谱 JSON 构建 FAISS 向量索引，并保存为新的 JSON 文件。"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="test_core_extraction_unified_std_api.json",
        help="输入的知识图谱 JSON 文件路径（默认：test_core_extraction_unified_std_api.json）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_graph_with_vectors.json",
        help="输出的带向量索引的 JSON 文件路径（默认：test_graph_with_vectors.json）",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=os.getenv("GRAPHDISTILL_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help=(
            f"Embedding 模型名称（默认：环境变量 GRAPHDISTILL_EMBEDDING_MODEL 或 {DEFAULT_EMBEDDING_MODEL}）"
        ),
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("SILICONFLOW_API_KEY", ""),
        help="SiliconFlow API Key（默认从环境变量 SILICONFLOW_API_KEY 读取）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding 批处理大小（默认：32）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    embedding_model = args.embedding_model
    api_key = args.api_key

    # ── 检查输入文件 ──────────────────────────────────────────────────────────
    if not input_path.exists():
        logger.error("输入文件不存在：%s", input_path)
        sys.exit(1)

    # ── 检查 API Key ──────────────────────────────────────────────────────────
    if not api_key:
        logger.error(
            "未提供 API Key。请设置环境变量 SILICONFLOW_API_KEY 或使用 --api-key 参数。"
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("输入文件    : %s", input_path)
    logger.info("输出文件    : %s", output_path)
    logger.info("Embedding 模型: %s", embedding_model)
    logger.info("=" * 60)

    # ── 加载图谱 ──────────────────────────────────────────────────────────────
    logger.info("正在从 %s 加载知识图谱 ...", input_path)
    builder = GraphBuilder.load_json(input_path)
    stats = builder.stats_report()
    logger.info(
        "图谱加载完成：%d 个实体，%d 条关系，向量索引=%s",
        stats.get("num_entities", 0),
        stats.get("num_relationships", 0),
        builder.has_vector_index(),
    )

    if stats.get("num_entities", 0) == 0:
        logger.error("图谱中没有任何实体，无法构建向量索引。请检查输入文件。")
        sys.exit(1)

    # ── 构建 OpenAI 兼容客户端 ────────────────────────────────────────────────
    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    # ── 构建向量索引 ──────────────────────────────────────────────────────────
    logger.info("开始构建向量索引（模型：%s，批大小：%d）...", embedding_model, args.batch_size)
    try:
        builder.build_vector_index(
            client=client,
            embedding_model=embedding_model,
            batch_size=args.batch_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("构建向量索引失败：%s", exc, exc_info=True)
        sys.exit(1)

    if not builder.has_vector_index():
        logger.error("向量索引构建后仍不可用，请检查 API Key 和网络连接。")
        sys.exit(1)

    logger.info("✅ 向量索引构建成功！")

    # ── 保存输出文件 ──────────────────────────────────────────────────────────
    logger.info("正在保存带向量索引的图谱到 %s ...", output_path)
    builder.save_json(output_path)
    logger.info("✅ 输出文件已保存：%s", output_path)

    # ── 打印最终摘要 ──────────────────────────────────────────────────────────
    final_stats = builder.stats_report()
    print("\n" + "=" * 60)
    print("✅ 向量索引构建完成")
    print(f"   输入文件    : {input_path}")
    print(f"   输出文件    : {output_path}")
    print(f"   实体数量    : {final_stats.get('num_entities', 0)}")
    print(f"   关系数量    : {final_stats.get('num_relationships', 0)}")
    print(f"   Embedding 模型: {embedding_model}")
    print(f"   向量索引可用: {builder.has_vector_index()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
