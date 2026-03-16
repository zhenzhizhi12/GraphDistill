from __future__ import annotations

"""
简单的 cjd_parser 评估脚本（不依赖 Tree-sitter 绑定，主要测试兜底解析质量）。
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cjd_parser import parse_cjd_ast
from pydantic_schema import DocumentGraph


SDK_API_DIR = ROOT / "temp_repos" / "interface_sdk_cangjie" / "api"


SAMPLES = [
    SDK_API_DIR / "NetworkKit" / "ohos.net.http.cj.d",
    SDK_API_DIR / "Cangjie" / "third_party" / "std" / "std.collection.cj.d",
]


def run_sample(path: Path) -> None:
    print("=" * 80)
    print(f"File: {path}")
    if not path.exists():
        print("  [WARN] file not found")
        return

    text = path.read_text(encoding="utf-8", errors="ignore")
    graph: DocumentGraph = parse_cjd_ast(
        cjd_text=text,
        source_metadata={"file_path": str(path)},
        cangjie_lang=None,  # 强制走兜底解析
    )

    print(f"  entities: {len(graph.entities)}")
    print(f"  relationships: {len(graph.relationships)}")

    if graph.entities:
        print("  sample entities:")
        for e in graph.entities[:8]:
            print(f"    - [{e.entity_type}] {e.entity_id} :: {e.name}")

    if graph.relationships:
        print("  sample relationships:")
        for r in graph.relationships[:12]:
            print(f"    - {r.relation_type}: {r.source_id} -> {r.target_id}")


def main() -> None:
    for p in SAMPLES:
        run_sample(p)


if __name__ == "__main__":
    main()

