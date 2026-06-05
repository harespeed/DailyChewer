"""Parser registry for supported daily report file formats."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.config import SUPPORTED_INPUT_FORMATS
from dailychewer_backend.parser.base import BaseParser


def get_parser(file_path: Path) -> BaseParser:
    """Return the parser instance matching the file extension."""

    suffix = file_path.suffix.lower()
    file_format = SUPPORTED_INPUT_FORMATS.get(suffix)
    if file_format == "csv":
        from dailychewer_backend.parser.csv_parser import CSVParser

        return CSVParser()
    if file_format == "xlsx":
        from dailychewer_backend.parser.xlsx_parser import XlsxParser

        return XlsxParser()
    if file_format == "markdown":
        from dailychewer_backend.parser.markdown_parser import MarkdownParser

        return MarkdownParser()
    if file_format == "docx":
        from dailychewer_backend.parser.docx_parser import DocxParser

        return DocxParser()
    raise ValueError(f"不支持的文件格式：{suffix or 'unknown'}")
