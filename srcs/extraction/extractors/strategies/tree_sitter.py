"""
File: tree_sitter.py
Purpose: Tree-sitter based extraction strategy.
Category: Utility
Author: artdaq team
Depends: None
Exports: ParsedNode, TreeSitterStrategy
Complexity: Medium | Lines: 98
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from ..base import ExtractionStrategy
logger = logging.getLogger(__name__)

@dataclass
class ParsedNode:
    type: str
    text: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    children: list['ParsedNode'] = field(default_factory=list)

    def find_all(self, node_type: str) -> list['ParsedNode']:
        results = []
        if self.type == node_type:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(node_type))
        return results

    def find_first(self, node_type: str) -> 'ParsedNode | None':
        if self.type == node_type:
            return self
        for child in self.children:
            result = child.find_first(node_type)
            if result:
                return result
        return None

class TreeSitterStrategy(ExtractionStrategy):
    LANGUAGE_GRAMMARS = {'cpp': 'tree_sitter_cpp', 'c': 'tree_sitter_cpp', 'python': 'tree_sitter_python', 'javascript': 'tree_sitter_javascript', 'typescript': 'tree_sitter_typescript', 'java': 'tree_sitter_java', 'go': 'tree_sitter_go', 'rust': 'tree_sitter_rust'}

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}
        self._available_languages: list[str] = []
        self._tree_sitter_available = False
        try:
            import tree_sitter
            self._tree_sitter = tree_sitter
            self._tree_sitter_available = True
            self._detect_available_languages()
        except ImportError:
            logger.debug('tree-sitter not available, strategy disabled')

    @property
    def name(self) -> str:
        return 'tree_sitter'

    def is_available(self) -> bool:
        return self._tree_sitter_available and len(self._available_languages) > 0

    def supported_languages(self) -> list[str]:
        return self._available_languages.copy()

    def _detect_available_languages(self) -> None:
        for lang, module_name in self.LANGUAGE_GRAMMARS.items():
            try:
                module = __import__(module_name)
                parser = self._tree_sitter.Parser(module.language())
                self._parsers[lang] = parser
                if lang not in self._available_languages:
                    self._available_languages.append(lang)
            except (ImportError, AttributeError, Exception) as e:
                logger.debug(f'Grammar for {lang} not available: {e}')

    def _get_parser(self, language: str) -> Any | None:
        if language in self._parsers:
            return self._parsers[language]
        module_name = self.LANGUAGE_GRAMMARS.get(language)
        if not module_name:
            return None
        try:
            module = __import__(module_name)
            parser = self._tree_sitter.Parser(module.language())
            self._parsers[language] = parser
            return parser
        except Exception as e:
            logger.debug(f'Failed to create parser for {language}: {e}')
            return None

    def parse(self, content: str, language: str) -> ParsedNode | None:
        parser = self._get_parser(language)
        if not parser:
            return None
        try:
            tree = parser.parse(content.encode('utf-8'))
            return self._convert_node(tree.root_node, content)
        except Exception as e:
            logger.debug(f'Failed to parse {language} content: {e}')
            return None

    def _convert_node(self, node: Any, content: str) -> ParsedNode:
        children = [self._convert_node(child, content) for child in node.children]
        return ParsedNode(type=node.type, text=content[node.start_byte:node.end_byte], start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1, start_byte=node.start_byte, end_byte=node.end_byte, children=children)