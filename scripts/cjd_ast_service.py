from __future__ import annotations

"""
WSL / Linux 侧的 Cangjie AST 解析微服务。

设计目的：
  - 在 Linux/WSL 环境中使用 Cangjie 专用 Tree-sitter 语法（tree_sitter_cangjie）
  - 对外暴露 HTTP 接口，供 Windows 侧 GraphDistill 调用
  - 返回符合 pydantic_schema.DocumentGraph 结构的 JSON

依赖（在 WSL / Linux 环境中安装）：
  - pip install tree-sitter~=0.25
  - 安装 CangjieTreeSitter 的 Python 绑定（tree_sitter_cangjie）：
      git clone https://github.com/SunriseSummer/CangjieTreeSitter.git
      cd CangjieTreeSitter/bindings/python
      pip install .

运行示例（在 WSL 中，确保当前目录是 GraphDistill 项目根）：
  cd /path/to/GraphDistill
  python scripts/cjd_ast_service.py --host 0.0.0.0 --port 8001

接口：
  POST /parse_cjd
    body: {"cjd_text": "...", "source_metadata": {...}}
    resp: DocumentGraph 的 JSON 表示
"""

import argparse
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict

from pydantic import ValidationError

# 确保能导入项目根目录的模块（WSL 环境）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cjd_parser import parse_cjd_ast
from pydantic_schema import DocumentGraph

logger = logging.getLogger("cjd_ast_service")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


def init_cangjie_language():
    """
    在 WSL / Linux 中初始化 Cangjie Tree-sitter 语言对象。
    假设已正确安装 tree_sitter_cangjie（参考模块 docstring）。
    """

    try:
        import tree_sitter_cangjie  # type: ignore
        from tree_sitter import Language  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to import tree_sitter_cangjie / tree_sitter: %s", exc, exc_info=True)
        raise

    try:
        cj_lang = Language(tree_sitter_cangjie.language())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize Cangjie Language from tree_sitter_cangjie: %s", exc, exc_info=True)
        raise

    logger.info("Cangjie Tree-sitter language initialized successfully.")
    return cj_lang


class CjdAstHandler(BaseHTTPRequestHandler):
    server_version = "CjdAstService/0.1"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/parse_cjd":
            self._send_json(404, {"error": "not_found"})
            return

        length_str = self.headers.get("Content-Length")
        try:
            length = int(length_str or "0")
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return

        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return

        cjd_text = data.get("cjd_text", "")
        source_metadata = data.get("source_metadata") or {}
        if not isinstance(source_metadata, dict):
            source_metadata = {}

        try:
            graph: DocumentGraph = parse_cjd_ast(
                cjd_text=cjd_text,
                source_metadata=source_metadata,
                cangjie_lang=self.server.cangjie_lang,  # type: ignore[attr-defined]
            )
        except ValidationError as exc:
            logger.warning("DocumentGraph validation failed: %s", exc, exc_info=True)
            self._send_json(500, {"error": "validation_error", "detail": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("parse_cjd_ast failed: %s", exc, exc_info=True)
            self._send_json(500, {"error": "internal_error", "detail": str(exc)})
            return

        self._send_json(200, graph.model_dump())


def run_server(host: str, port: int) -> None:
    cj_lang = init_cangjie_language()

    httpd = HTTPServer((host, port), CjdAstHandler)
    # 将 language 挂在 server 对象上，方便 handler 访问
    setattr(httpd, "cangjie_lang", cj_lang)

    logger.info("CJD AST service listening on %s:%d", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("CJD AST service shutting down (KeyboardInterrupt).")
    finally:
        httpd.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cangjie .cj.d AST microservice based on Tree-sitter.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8001, help="监听端口（默认 8001）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()

