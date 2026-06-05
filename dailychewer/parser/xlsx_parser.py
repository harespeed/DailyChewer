"""XLSX report parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dailychewer.parser.base import BaseParser
from dailychewer.utils.text_utils import dataframe_to_markdown_table, ensure_non_empty_text


class XlsxParser(BaseParser):
    """Read every sheet from an XLSX file and render them as text."""

    def parse(self, file_path: Path) -> str:
        """Parse all worksheets and prefix each block with its sheet name."""

        try:
            workbook = pd.ExcelFile(file_path, engine="openpyxl")
        except ValueError as exc:
            raise ValueError(f"无法解析 xlsx 文件：{file_path}") from exc

        blocks: list[str] = []
        for sheet_name in workbook.sheet_names:
            dataframe = workbook.parse(sheet_name=sheet_name)
            table_text = dataframe_to_markdown_table(dataframe)
            blocks.append(f"# Sheet: {sheet_name}\n\n{table_text}")
        return ensure_non_empty_text("\n\n".join(blocks))

