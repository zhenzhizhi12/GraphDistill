from __future__ import annotations

import argparse
import logging
import os

from openai import OpenAI

from graph_builder import GraphBuilder
from search_engine import SearchEngine
from main import BASE_URL, MODEL, GRAPH_JSON_PATH, EMBEDDING_MODEL


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("graphdistill.search_main")


def load_builder_for_search() -> GraphBuilder:
    """
    仅用于搜索测试：从本地 JSON 加载已有图谱。
    若文件不存在则返回空图谱，并给出警告。
    """
    p = GRAPH_JSON_PATH
    if not p.exists():
        logger.warning("Graph JSON not found at %s; search will run on an empty graph.", p)
        return GraphBuilder()

    logger.info("Loading existing graph from %s", p)
    return GraphBuilder.load_json(p)


def run_search_tests(
    client: OpenAI,
    model: str,
    builder: GraphBuilder,
) -> None:
    """
    使用 SearchEngine 运行预定义的多模搜索用例，输出答案与溯源信息。
    """
    engine = SearchEngine(builder)

    test_cases = [
        ("local", "IncompatiblePackageException 在什么场景下会被抛出？"),
        ("local", "Button 组件的 onClick 事件如何触发？"),
        ("global", "请总结仓颉语言二进制兼容性检查的设计规则。"),
    ]

    for mode, question in test_cases:
        logger.info("=== Running search case (mode=%s) ===", mode)
        result = engine.answer_question(
            client=client,
            model=model,
            question=question,
            mode=mode,
            embedding_model=EMBEDDING_MODEL,
        )

        print("\n" + "=" * 80)
        print(f"问题（mode={result.mode}）: {question}")
        print("-" * 80)
        print(result.answer)
        print("-" * 80)
        print("溯源文档：")
        if not result.sources:
            print("  （无溯源信息）")
        else:
            # 打印去重后的 sources 摘要
            for i, src in enumerate(result.sources[:10], start=1):
                preset = src.get("preset", "")
                file_path = src.get("file_path", "")
                branch = src.get("branch", "")
                repo_url = src.get("repo_url", "")
                print(f"  [{i}] preset={preset}, branch={branch}")
                print(f"      file={file_path}")
                print(f"      repo={repo_url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GraphDistill search-only runner.")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GRAPHDISTILL_MODEL", MODEL),
        help=(
            "LLM 模型名称，默认为环境变量 GRAPHDISTILL_MODEL 或内置模型 "
            f"{MODEL}（SiliconFlow OpenAI-兼容接口）。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 初始化 SiliconFlow OpenAI-兼容客户端（需环境变量 SILICONFLOW_API_KEY）
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    if not api_key:
        logger.warning("SILICONFLOW_API_KEY is not set; LLM calls will likely fail.")
    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    builder = load_builder_for_search()

    # 打印当前图谱概览，便于确认加载是否成功
    stats = builder.stats_report()
    logger.info("Graph stats (for search): %s", stats)

    run_search_tests(client=client, model=args.model, builder=builder)


if __name__ == "__main__":
    main()

