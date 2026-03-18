from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("graphdistill.old_compare")


ROOT = Path(__file__).parent
OLD_SEARCH_DIR = ROOT / "old-search-l1"
DEFAULT_CURRENT_REPORT = ROOT / "TEST_REPORT.md"
DEFAULT_OUTPUT = ROOT / "OLD_SEARCH_COMPARE_REPORT.md"
JUDGE_NAME = "GPT-5.4"

if str(OLD_SEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(OLD_SEARCH_DIR))

from cangjie_retriever import CangjieRetriever, map_source_file_to_local  # type: ignore  # noqa: E402


def _normalize_text(text: str) -> str:
    return (text or "").lower()


def _strip_markdown_quotes(text: str) -> str:
    lines: List[str] = []
    for line in (text or "").splitlines():
        if line.startswith("> "):
            lines.append(line[2:])
        elif line == ">":
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _clip_text(text: str, limit: int = 700) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "…（截断）"


def _extract_question_tokens(question: str, expected_keywords: List[str]) -> List[str]:
    tokens: List[str] = []
    tokens.extend(expected_keywords)
    tokens.extend(re.findall(r"[A-Za-z][A-Za-z0-9_<>.:-]{1,}", question))
    tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", question))

    cleaned: List[str] = []
    seen = set()
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        lower = token.lower()
        if lower in seen:
            continue
        seen.add(lower)
        cleaned.append(token)
    return cleaned


def parse_current_report(report_path: Path) -> List[Dict[str, Any]]:
    if not report_path.exists():
        return []

    text = report_path.read_text(encoding="utf-8")
    section_pattern = re.compile(
        r"^#### \[(?P<id>[^\]]+)\] (?P<status>[✅❌] (?:PASS|FAIL))\n(?P<body>.*?)(?=^#### \[|\Z)",
        re.M | re.S,
    )

    parsed: List[Dict[str, Any]] = []
    for match in section_pattern.finditer(text):
        body = match.group("body")
        question_match = re.search(r"\*\*问题\*\*：(.+)", body)
        mode_match = re.search(r"\*\*数据源\*\*：.+?\| \*\*搜索模式\*\*：(.+)", body)
        answer_match = re.search(r"\*\*回答\*\*：\n\n(?P<answer>(?:>.*\n?)*)", body)
        kw_match = re.search(r"\*\*命中关键词\*\*：(.+)", body)
        expected_keywords = []
        if kw_match:
            expected_keywords = [item.strip() for item in kw_match.group(1).split(",") if item.strip()]

        question = question_match.group(1).strip() if question_match else ""
        parsed.append(
            {
                "id": match.group("id"),
                "status": match.group("status"),
                "question": question,
                "mode": mode_match.group(1).strip() if mode_match else "",
                "answer": _strip_markdown_quotes(answer_match.group("answer")) if answer_match else "",
                "expected_keywords": expected_keywords,
                "question_tokens": _extract_question_tokens(question, expected_keywords),
            }
        )
    return parsed


def _vector_search(retriever: CangjieRetriever, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
    if not getattr(retriever, "vector_enabled", False) or getattr(retriever, "chroma", None) is None:
        return []

    try:
        collection = retriever.chroma._collection
        if collection.count() <= 0:
            return []
    except Exception:  # noqa: BLE001
        collection = None

    results: List[Dict[str, Any]] = []
    try:
        embedding = retriever.chroma._embedding_function.embed_query(question)
        raw = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )
        metadatas = (raw.get("metadatas") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        for meta, content, distance in zip(metadatas, documents, distances):
            meta = meta or {}
            source_file = meta.get("source_file", "")
            results.append(
                {
                    "knowledge_point": meta.get("knowledge_point", ""),
                    "source_file": source_file,
                    "local_path": map_source_file_to_local(source_file) if source_file else "",
                    "score": round(float(distance), 4),
                    "content": content or "",
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector-only search failed for '%s': %s", question[:60], exc)
    return results


def run_old_search_cases(report_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    retriever = CangjieRetriever(
        chroma_db_dir=str(OLD_SEARCH_DIR / "chroma_db"),
        bm25_docs_path=str(OLD_SEARCH_DIR / "chroma_db" / "bm25_documents.pkl"),
    )
    vector_collection_count = 0
    if getattr(retriever, "vector_enabled", False) and getattr(retriever, "chroma", None) is not None:
        try:
            vector_collection_count = retriever.chroma._collection.count()
        except Exception:  # noqa: BLE001
            vector_collection_count = 0

    results: List[Dict[str, Any]] = []
    for case in report_cases:
        t0 = time.time()
        question = case["question"]
        logger.info("Running old-search case %s: %s", case["id"], question[:80])

        try:
            vector_hits = _vector_search(retriever, question, top_k=3)
            docs = retriever.query(question, top_k=6)
            formatted = retriever.format_for_llm(docs)
            elapsed = round(time.time() - t0, 2)

            top_doc = docs[0] if docs else None
            top_meta = top_doc.metadata if top_doc else {}
            top_source = top_meta.get("source_file", "")
            results.append(
                {
                    "id": case["id"],
                    "question": question,
                    "has_result": bool(docs),
                    "elapsed_seconds": elapsed,
                    "doc_count": len(docs),
                    "top_knowledge_point": top_meta.get("knowledge_point", ""),
                    "top_source_file": top_source,
                    "top_local_path": map_source_file_to_local(top_source) if top_source else "",
                    "preview": formatted[:1500],
                    "vector_hits": vector_hits,
                    "vector_collection_count": vector_collection_count,
                    "vector_enabled": bool(getattr(retriever, "vector_enabled", False)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = round(time.time() - t0, 2)
            logger.warning("Old-search case %s failed: %s", case["id"], exc, exc_info=True)
            results.append(
                {
                    "id": case["id"],
                    "question": question,
                    "has_result": False,
                    "elapsed_seconds": elapsed,
                    "doc_count": 0,
                    "top_knowledge_point": "",
                    "top_source_file": "",
                    "top_local_path": "",
                    "preview": f"ERROR: {exc}",
                    "vector_hits": [],
                    "vector_collection_count": vector_collection_count,
                    "vector_enabled": bool(getattr(retriever, "vector_enabled", False)),
                }
            )

    return results


def score_response(
    question: str,
    expected_keywords: List[str],
    response: str,
    top_hint: str = "",
) -> Dict[str, Any]:
    text = _normalize_text(response)
    if not text.strip():
        return {"score": 0, "reason": "没有可评估内容。"}

    tokens = _extract_question_tokens(question, expected_keywords)
    token_hits = [token for token in tokens if token.lower() in text]
    keyword_hits = [kw for kw in expected_keywords if kw.lower() in text]
    top_hint_lower = _normalize_text(top_hint)
    top_hint_hits = [token for token in tokens if token.lower() in top_hint_lower]

    score = 1
    positives: List[str] = []
    negatives: List[str] = []

    if keyword_hits:
        kw_score = min(4, round(len(keyword_hits) / max(len(expected_keywords), 1) * 4))
        score += kw_score
        positives.append(f"命中预期关键词 {len(keyword_hits)}/{max(len(expected_keywords), 1)}")

    if token_hits:
        token_score = min(3, round(len(token_hits) / max(len(tokens), 1) * 3))
        score += token_score
        positives.append(f"覆盖题目关键术语 {len(token_hits)}/{max(len(tokens), 1)}")

    if len(response) >= 120:
        score += 1
        positives.append("回答有一定展开")
    if len(response) >= 260:
        score += 1
        positives.append("回答信息较完整")

    if top_hint:
        if top_hint_hits:
            score += 1
            positives.append("Top-1 结果与题目主题相关")
        else:
            score -= 2
            negatives.append("Top-1 结果与题目主题不一致")

    off_topic_signals = ["buttonrole", "mock", "spy", "arkui", "picker"]
    if any(signal in text for signal in off_topic_signals) and not keyword_hits:
        score -= 3
        negatives.append("内容存在明显跑题信号")

    score = max(0, min(10, score))

    reason_parts: List[str] = []
    if positives:
        reason_parts.append("覆盖到：" + "；".join(positives))
    if negatives:
        reason_parts.append("扣分点：" + "；".join(negatives))
    if not reason_parts:
        reason_parts.append("几乎没有覆盖题目要求的信息。")

    return {"score": score, "reason": "；".join(reason_parts)}


def generate_compare_report(
    current_report_data: List[Dict[str, Any]],
    old_results: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old_result_by_id = {item["id"]: item for item in old_results}
    current_by_id = {item["id"]: item for item in current_report_data}

    lines: List[str] = []
    lines.append("# 新旧检索全量对比评分报告")
    lines.append("")
    lines.append(f"> 生成时间：{timestamp}")
    lines.append(f"> 评审者：{JUDGE_NAME}")
    lines.append("")

    lines.append("## 老方案使用向量检索的证据")
    lines.append("")
    vector_enabled = any(item.get("vector_enabled") for item in old_results)
    vector_collection_count = old_results[0].get("vector_collection_count", 0) if old_results else 0
    lines.append(
        f"- 代码层面：old-search-l1 在当前环境中 vector_enabled={vector_enabled}，会初始化 OpenAIEmbeddings、Chroma，并与 BM25 组成混合检索。"
    )
    lines.append(
        f"- 向量库状态：当前 Chroma collection 文档数为 {vector_collection_count}。这意味着运行时会发 embedding 请求，但如果库为空，就不会产生有效向量命中。"
    )
    lines.append("- 运行层面：下表单独列出每道题的向量-only Top-1 结果与分数，用来区分‘已启用向量链路’和‘实际命中到向量文档’这两件事。")
    lines.append("")
    lines.append("| ID | 向量 Top-1 知识点 | 向量分数 | 向量来源文件 |")
    lines.append("|----|------------------|----------|--------------|")
    for item in old_results:
        top_vector = item.get("vector_hits", [])[:1]
        if top_vector:
            hit = top_vector[0]
            knowledge = (hit.get("knowledge_point", "") or "").replace("|", "\\|")[:60]
            source_file = (hit.get("source_file", "") or "").replace("|", "\\|")[:80]
            lines.append(f"| {item['id']} | {knowledge} | {hit.get('score', '')} | {source_file} |")
        else:
            lines.append(f"| {item['id']} | (none) | (none) | (none) |")
    lines.append("")

    lines.append("## 逐题对比")
    lines.append("")

    for current in current_report_data:
        case_id = current["id"]
        old = old_result_by_id.get(case_id, {})
        new_answer = current.get("answer", "")
        old_answer = old.get("preview", "")

        new_score = score_response(
            current.get("question", ""),
            current.get("expected_keywords", []),
            new_answer,
        )
        old_score = score_response(
            current.get("question", ""),
            current.get("expected_keywords", []),
            old_answer,
            top_hint=old.get("top_knowledge_point", ""),
        )
        winner = "新方案" if new_score["score"] >= old_score["score"] else "老方案"

        lines.append(f"## [{case_id}] {current.get('question', '')}")
        lines.append("")
        lines.append("### 新方案结果")
        lines.append("")
        for line in _clip_text(new_answer, limit=500).splitlines():
            lines.append(f"> {line}" if line.strip() else ">")
        lines.append("")
        lines.append(f"分数：{new_score['score']}/10")
        lines.append(f"理由：{new_score['reason']}")
        lines.append("")

        vector_hits = old.get("vector_hits", []) or []
        lines.append("### 老方案向量检索 Top-3")
        lines.append("")
        if vector_hits:
            for idx, hit in enumerate(vector_hits[:3], 1):
                lines.append(
                    f"- Top {idx}: {hit.get('knowledge_point', '')} | score={hit.get('score', '')} | {hit.get('source_file', '')}"
                )
        else:
            lines.append("- 无向量结果")
        lines.append("")

        lines.append("### 老方案结果")
        lines.append("")
        for line in _clip_text(old_answer, limit=500).splitlines():
            lines.append(f"> {line}" if line.strip() else ">")
        lines.append("")
        lines.append(f"分数：{old_score['score']}/10")
        lines.append(f"理由：{old_score['reason']}")
        lines.append("")
        lines.append(f"结论：{winner}更优。")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Old-search scored comparison report written to %s", output_path)


def main() -> None:
    current_report_data = parse_current_report(DEFAULT_CURRENT_REPORT)
    old_results = run_old_search_cases(current_report_data)
    generate_compare_report(current_report_data, old_results, DEFAULT_OUTPUT)
    print(f"[OK] 对比报告已写入：{DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()

