"""
File: base.py
Purpose: Base classes for the modular code extraction system.
Category: Utility
Author: artdaq team
Depends: None
Exports: ExtractedFunction, ExtractedClass, ExtractedDependency, ExtractionResult, ExtractionStrategy, ...
Complexity: Medium | Lines: 99
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractedFunction:
    name: str
    file_path: Path
    start_line: int
    end_line: int
    signature: str
    body: str | None = None
    class_name: str | None = None
    parameters: list[tuple[str, str]] = field(default_factory=list)
    return_type: str | None = None
    docstring: str | None = None
    modifiers: list[str] = field(default_factory=list)
    calls: list[tuple[str, int, str]] = field(default_factory=list)


@dataclass
class ExtractedClass:
    name: str
    file_path: Path
    start_line: int
    end_line: int
    signature: str
    base_classes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    members: list[tuple[str, str]] = field(default_factory=list)
    nested_classes: list[str] = field(default_factory=list)


@dataclass
class ExtractedDependency:
    imported_path: str
    import_type: str
    is_system: bool
    line_number: int
    imported_names: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    functions: list[ExtractedFunction] = field(default_factory=list)
    classes: list[ExtractedClass] = field(default_factory=list)
    dependencies: list[ExtractedDependency] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ExtractionStrategy(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def parse(self, content: str, language: str) -> Any:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def supported_languages(self) -> list[str]:
        pass


class LanguageExtractor(ABC):

    @property
    @abstractmethod
    def language_id(self) -> str:
        pass

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        pass

    @abstractmethod
    def extract(self, content: str, file_path: Path, strategy: ExtractionStrategy) -> ExtractionResult:
        pass

    @abstractmethod
    def extract_calls_from_function(self, func_node: Any, strategy: ExtractionStrategy) -> list[tuple[str, int, str]]:
        pass

    def extract_function_body(self, func_node: Any, content: str) -> str | None:
        if hasattr(func_node, "start_line") and hasattr(func_node, "end_line"):
            lines = content.split("\n")
            start = max(0, func_node.start_line - 1)
            end = min(len(lines), func_node.end_line)
            return "\n".join(lines[start:end])
        return None
