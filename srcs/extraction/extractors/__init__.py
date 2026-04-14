"""
File: __init__.py
Purpose: Modular code extraction system with plugin architecture.
Category: Config
Author: artdaq team
Depends: None
Exports: ExtractorRegistry
Complexity: Medium | Lines: 118
"""

import logging
from pathlib import Path
from typing import Type
from .base import (
    ExtractedClass,
    ExtractedDependency,
    ExtractedFunction,
    ExtractionResult,
    ExtractionStrategy,
    LanguageExtractor,
)

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    _languages: dict[str, Type[LanguageExtractor]] = {}
    _strategies: dict[str, Type[ExtractionStrategy]] = {}
    _extension_map: dict[str, str] = {}

    @classmethod
    def register_language(cls, extractor_class: Type[LanguageExtractor]) -> None:
        instance = extractor_class()
        cls._languages[instance.language_id] = extractor_class
        for ext in instance.extensions:
            cls._extension_map[ext.lower()] = instance.language_id
        logger.debug(f"Registered {instance.language_id} extractor with extensions {instance.extensions}")

    @classmethod
    def register_strategy(cls, name: str, strategy_class: Type[ExtractionStrategy]) -> None:
        cls._strategies[name] = strategy_class
        logger.debug(f"Registered {name} strategy")

    @classmethod
    def get_extractor(cls, file_path: Path) -> LanguageExtractor | None:
        ext = file_path.suffix.lower()
        lang_id = cls._extension_map.get(ext)
        if lang_id and lang_id in cls._languages:
            return cls._languages[lang_id]()
        return None

    @classmethod
    def get_extractor_by_language(cls, language: str) -> LanguageExtractor | None:
        if language in cls._languages:
            return cls._languages[language]()
        return None

    @classmethod
    def get_strategy(cls, name: str = "tree_sitter") -> ExtractionStrategy | None:
        if name in cls._strategies:
            strategy = cls._strategies[name]()
            if strategy.is_available():
                return strategy
            logger.debug(f"Strategy {name} not available, trying fallback")
        if "regex" in cls._strategies and name != "regex":
            strategy = cls._strategies["regex"]()
            if strategy.is_available():
                logger.debug(f"Using regex fallback for {name}")
                return strategy
        return None

    @classmethod
    def get_available_strategies(cls) -> list[str]:
        available = []
        for name, strategy_class in cls._strategies.items():
            try:
                if strategy_class().is_available():
                    available.append(name)
            except Exception:
                pass
        return available

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        return list(cls._extension_map.keys())

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        return list(cls._languages.keys())


def _auto_register() -> None:
    try:
        from .strategies.tree_sitter import TreeSitterStrategy

        ExtractorRegistry.register_strategy("tree_sitter", TreeSitterStrategy)
    except ImportError as e:
        logger.debug(f"Could not register tree_sitter strategy: {e}")
    try:
        from .strategies.regex import RegexStrategy

        ExtractorRegistry.register_strategy("regex", RegexStrategy)
    except ImportError as e:
        logger.debug(f"Could not register regex strategy: {e}")
    try:
        from .cpp import CppExtractor

        ExtractorRegistry.register_language(CppExtractor)
    except ImportError as e:
        logger.debug(f"Could not register cpp extractor: {e}")
    try:
        from .python import PythonExtractor

        ExtractorRegistry.register_language(PythonExtractor)
    except ImportError as e:
        logger.debug(f"Could not register python extractor: {e}")


_auto_register()
__all__ = [
    "ExtractorRegistry",
    "LanguageExtractor",
    "ExtractionStrategy",
    "ExtractionResult",
    "ExtractedFunction",
    "ExtractedClass",
    "ExtractedDependency",
]
