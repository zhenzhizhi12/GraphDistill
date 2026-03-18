from __future__ import annotations

"""
调试脚本：直接用 tree_sitter_cangjie 打印 .cj.d 文件的 AST 结构（使用 Python 绑定，不依赖 CLI）。

用途：
  - 观察 interface_sdk_cangjie/api/*.cj.d 的真实 AST 形状；
  - 为 cjd_parser.py 中基于 AST 的实体/关系抽取逻辑提供依据。

使用方式（在 WSL 中，已激活 .venv_cjd 且安装 tree-sitter / tree_sitter_cangjie）：

  cd /mnt/c/Users/zqw/Desktop/GraphDistill
  python scripts/debug_cjd_ast.py --file temp_repos/interface_sdk_cangjie/api/NetworkKit/ohos.net.http.cj.d

  或：
  python scripts/debug_cjd_ast.py --file temp_repos/interface_sdk_cangjie/api/Cangjie/third_party/std/std.collection.cj.d
"""

import argparse
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser  # type: ignore[import-not-found]
import tree_sitter_cangjie  # type: ignore[import-not-found]


def init_cangjie_language() -> Language:
    """
    使用已安装的 tree_sitter_cangjie Python 绑定初始化 Language。
    """
    return Language(tree_sitter_cangjie.language())


def print_top_level_structure(root: Any, max_children: int = 30) -> None:
    """
    打印顶层 translationUnit 的直接子节点类型，便于快速了解 .cj.d 的结构组成。
    """
    print("Top-level children (type, start_point, end_point):")
    for idx, child in enumerate(root.children[:max_children]):
        print(
            f"  [{idx}] type={child.type}, "
            f"start={child.start_point}, end={child.end_point}"
        )


def print_sexp_for_first_decls(root: Any, max_nodes: int = 5) -> None:
    """
    打印前若干个声明节点（classDefinition / interfaceDefinition / functionDefinition）的 sexp。
    """
    target_types = {
        "classDefinition",
        "interfaceDefinition",
        "functionDefinition",
        "foreignDeclaration",  # .cj.d 中可能会包一层声明
    }

    found = 0

    def _walk(node: Any) -> None:
        nonlocal found
        if found >= max_nodes:
            return
        if node.type in target_types:
            print("=" * 80)
            print(f"S-expression for node type={node.type}:")
            print(node.sexp())
            found += 1
        for ch in getattr(node, "children", []) or []:
            _walk(ch)

    _walk(root)
    if found == 0:
        print("No declaration nodes (classDefinition/interfaceDefinition/functionDefinition/foreignDeclaration) found.")


def debug_cjd_file(path: Path) -> None:
    if not path.exists():
        print(f"[WARN] file not found: {path}")
        return

    text = path.read_text(encoding="utf-8", errors="ignore")
    src_bytes = text.encode("utf-8")

    lang = init_cangjie_language()
    parser = Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(lang)
    else:
        parser.language = lang  # type: ignore[attr-defined]

    tree = parser.parse(src_bytes)
    root = tree.root_node

    print(f"Parsed file: {path}")
    print(f"Root type: {root.type}, start={root.start_point}, end={root.end_point}")
    print()

    print_top_level_structure(root)
    print()
    print_sexp_for_first_decls(root)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Debug Cangjie .cj.d AST using tree_sitter_cangjie.")
    p.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to .cj.d file (relative or absolute).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.file)
    debug_cjd_file(path)


if __name__ == "__main__":
    main()


