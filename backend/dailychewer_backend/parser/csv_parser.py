"""CSV report parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dailychewer_backend.parser.base import BaseParser
from dailychewer_backend.utils.text_utils import dataframe_to_markdown_table, ensure_non_empty_text


class CSVParser(BaseParser):
    """Read CSV files and flatten them into markdown-table text."""

    def parse(self, file_path: Path) -> str:
        """Parse CSV with UTF-8 first and fall back to GBK."""

        last_error: Exception | None = None
        for encoding in ("utf-8", "utf-8-sig", "gbk"):
            try:
                dataframe = pd.read_csv(file_path, encoding=encoding)
                return ensure_non_empty_text(dataframe_to_markdown_table(dataframe))
            except UnicodeDecodeError as exc:
                last_error = exc
            except pd.errors.EmptyDataError as exc:
                raise ValueError("文件内容为空，无法继续处理。") from exc
        if last_error:
            raise ValueError(f"CSV 文件编码无法识别：{file_path}") from last_error
        raise ValueError(f"无法解析 CSV 文件：{file_path}")

