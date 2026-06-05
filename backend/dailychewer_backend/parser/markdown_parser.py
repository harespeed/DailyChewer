"""Markdown report parser."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.parser.base import BaseParser
from dailychewer_backend.utils.text_utils import ensure_non_empty_text, read_text_with_fallback


class MarkdownParser(BaseParser):
    """Read markdown files as-is."""

    def parse(self, file_path: Path) -> str:
        """Load markdown text using common encodings."""

        content = read_text_with_fallback(file_path)
        return ensure_non_empty_text(content)

