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
    """Best-effort extraction of one JSON object from model output."""

    def parse_candidate(candidate: str) -> dict[str, Any]:
        cleaned = candidate.strip().removeprefix("\ufeff").strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = json.loads(re.sub(r",\s*([}\]])", r"\1", cleaned))
        if not isinstance(payload, dict):
            raise ValueError("LLM JSON response must be an object.")
        return payload

    stripped = text.strip()
    for fenced_match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE):
        fenced_content = fenced_match.group(1)
        if "{" in fenced_content:
            try:
                return parse_candidate(_first_balanced_json_object(fenced_content))
            except Exception:
                continue

    if "{" in stripped:
        return parse_candidate(_first_balanced_json_object(stripped))

    return parse_candidate(stripped)


def _first_balanced_json_object(text: str) -> str:
    """Return the first balanced JSON object substring, respecting quoted braces."""

    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM response.")

    depth = 0
    in_string = False
    escape_next = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("No balanced JSON object found in LLM response.")


def ensure_non_empty_text(text: str) -> str:
    """Validate that parsed text still contains meaningful content."""

    if not text or not text.strip():
        raise ValueError("文件内容为空，无法继续处理。")
    return text.strip()
