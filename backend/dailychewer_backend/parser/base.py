"""Base interface for all file parsers."""

from __future__ import annotations

from pathlib import Path


class BaseParser:
    """Abstract parser that turns a file into plain text."""

    def parse(self, file_path: Path) -> str:
        """Parse a source file and return plain text."""

        raise NotImplementedError

