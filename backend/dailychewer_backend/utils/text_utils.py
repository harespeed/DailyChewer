"""Text processing helpers shared by parsers, storage, and LLM code."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any


def read_text_with_fallback(file_path: Path, encodings: list[str] | None = None) -> str:
    """Read text with multiple candidate encodings."""

    tried = encodings or ["utf-8", "gbk", "utf-8-sig"]
    last_error: UnicodeDecodeError | None = None
    for encoding in tried:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return file_path.read_text()


def _normalize_cell(value: Any) -> str:
    """Convert a cell value into stable plain text."""

    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def rows_to_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render headers and rows into a lightweight markdown table string."""

    normalized_headers = [_normalize_cell(header) or "Column" for header in headers]
    normalized_rows = [[_normalize_cell(cell) for cell in row] for row in rows]
    header_line = "| " + " | ".join(normalized_headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(normalized_headers)) + " |"
    body_lines = [
        "| " + " | ".join(row + [""] * (len(normalized_headers) - len(row))) + " |"
        for row in normalized_rows
    ]
    return "\n".join([header_line, separator_line, *body_lines]).strip()


def dataframe_to_markdown_table(dataframe: Any) -> str:
    """Convert a pandas DataFrame into markdown without extra dependencies."""

    if dataframe.empty:
        return "（空表）"
    filled = dataframe.fillna("")
    headers = [str(column) for column in filled.columns]
    rows = filled.astype(str).values.tolist()
    return rows_to_markdown_table(headers, rows)


def extract_json_payload(text: str) -> dict[str, Any]:
    """Best-effort extraction of the first JSON object from model output."""

    fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    direct_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if direct_match:
        return json.loads(direct_match.group(1))

    return json.loads(text)


def ensure_non_empty_text(text: str) -> str:
    """Validate that parsed text still contains meaningful content."""

    if not text or not text.strip():
        raise ValueError("文件内容为空，无法继续处理。")
    return text.strip()

