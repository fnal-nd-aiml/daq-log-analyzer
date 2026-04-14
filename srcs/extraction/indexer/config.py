"""
File: config.py
Purpose: Configuration for code indexing.
Category: Utility
Author: artdaq team
Depends: None
Exports: CodeIndexConfig
Complexity: Low | Lines: 22
"""

from dataclasses import dataclass, field
from pathlib import Path


def _default_extensions() -> list[str]:
    return [".cpp", ".cxx", ".cc", ".c", ".h", ".hpp", ".py"]


def _default_exclude_patterns() -> list[str]:
    return ["**/build/**", "**/test/**", "**/.git/**"]


def _default_index_path() -> Path:
    return Path("./data/code_index.db")


@dataclass
class CodeIndexConfig:
    source_roots: list[Path]
    extensions: list[str] = field(default_factory=_default_extensions)
    exclude_patterns: list[str] = field(default_factory=_default_exclude_patterns)
    index_path: Path = field(default_factory=_default_index_path)
