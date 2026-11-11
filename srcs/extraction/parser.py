"""
File: parser.py
Purpose: Tree-sitter based code parser for C++ and other languages.
Category: Utility
Author: artdaq team
Depends: None
Exports: ParsedNode, ParsedFile, CodeParser
Complexity: Medium | Lines: 137
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
logger = logging.getLogger(__name__)

@dataclass
class ParsedNode:
    type: str
    text: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    children: list['ParsedNode'] = field(default_factory=list)

    def find_all(self, node_type: str) -> list['ParsedNode']:
        results = []
        if self.type == node_type:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(node_type))
        return results

@dataclass
class ParsedFile:
    path: Path
    language: str
    content: str
    root: ParsedNode | None
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def get_line(self, line_num: int) -> str:
        lines = self.content.split('\n')
        if 1 <= line_num <= len(lines):
            return lines[line_num - 1]
        return ''

    def get_lines(self, start: int, end: int) -> list[str]:
        lines = self.content.split('\n')
        return lines[max(0, start - 1):min(len(lines), end)]

class CodeParser:
    LANGUAGE_EXTENSIONS = {'.cpp': 'cpp', '.cxx': 'cpp', '.cc': 'cpp', '.c': 'c', '.h': 'cpp', '.hpp': 'cpp', '.hxx': 'cpp', '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.java': 'java', '.go': 'go', '.rs': 'rust'}

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}
        self._tree_sitter_available = self._check_tree_sitter()

    def _check_tree_sitter(self) -> bool:
        import importlib.util
        if importlib.util.find_spec('tree_sitter_cpp') is not None:
            return True
        logger.warning('tree-sitter-cpp not available, using fallback parser')
        return False

    def _get_parser(self, language: str) -> Any:
        if language in self._parsers:
            return self._parsers[language]
        if not self._tree_sitter_available:
            return None
        try:
            import tree_sitter as ts
            if language == 'cpp' or language == 'c':
                import tree_sitter_cpp
                parser = ts.Parser(ts.Language(tree_sitter_cpp.language()))
            elif language == 'python':
                import tree_sitter_python
                parser = ts.Parser(ts.Language(tree_sitter_python.language()))
            else:
                return None
            self._parsers[language] = parser
            return parser
        except Exception as e:
            logger.warning(f'Failed to create parser for {language}: {e}')
            return None

    def parse_file(self, path: Path) -> ParsedFile:
        if not path.exists():
            return ParsedFile(path=path, language='unknown', content='', root=None, errors=[f'File not found: {path}'])
        language = self.LANGUAGE_EXTENSIONS.get(path.suffix.lower(), 'unknown')
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return ParsedFile(path=path, language=language, content='', root=None, errors=[f'Failed to read file: {e}'])
        return self.parse_string(content, language, path)

    def parse_string(self, content: str, language: str, path: Path | None=None) -> ParsedFile:
        parser = self._get_parser(language)
        if parser is None:
            root = self._fallback_parse(content, language)
            return ParsedFile(path=path or Path('<string>'), language=language, content=content, root=root, errors=[] if root else ['Fallback parser failed'])
        try:
            tree = parser.parse(content.encode('utf-8'))
            root = self._convert_node(tree.root_node, content)
            errors = []
            if tree.root_node.has_error:
                errors.append('Source contains syntax errors')
            return ParsedFile(path=path or Path('<string>'), language=language, content=content, root=root, errors=errors)
        except Exception as e:
            logger.error(f'Tree-sitter parsing failed: {e}')
            root = self._fallback_parse(content, language)
            return ParsedFile(path=path or Path('<string>'), language=language, content=content, root=root, errors=[f'Parsing error: {e}'])

    def _convert_node(self, node: Any, content: str) -> ParsedNode:
        children = [self._convert_node(child, content) for child in node.children]
        return ParsedNode(type=node.type, text=content[node.start_byte:node.end_byte], start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1, start_col=node.start_point[1], end_col=node.end_point[1], children=children)

    def _fallback_parse(self, content: str, language: str) -> ParsedNode | None:
        import re
        lines = content.split('\n')
        children = []
        if language in ('cpp', 'c'):
            func_pattern = re.compile('^\\s*(?:[\\w:*&<>]+\\s+)+(\\w+)\\s*\\([^)]*\\)\\s*(?:const)?\\s*\\{?\\s*$')
            class_pattern = re.compile('^\\s*class\\s+(\\w+)')
            for i, line in enumerate(lines):
                func_match = func_pattern.match(line)
                if func_match:
                    children.append(ParsedNode(type='function_definition', text=line, start_line=i + 1, end_line=i + 1, start_col=0, end_col=len(line), children=[ParsedNode(type='identifier', text=func_match.group(1), start_line=i + 1, end_line=i + 1, start_col=line.find(func_match.group(1)), end_col=line.find(func_match.group(1)) + len(func_match.group(1)))]))
                class_match = class_pattern.match(line)
                if class_match:
                    children.append(ParsedNode(type='class_specifier', text=line, start_line=i + 1, end_line=i + 1, start_col=0, end_col=len(line), children=[ParsedNode(type='type_identifier', text=class_match.group(1), start_line=i + 1, end_line=i + 1, start_col=line.find(class_match.group(1)), end_col=line.find(class_match.group(1)) + len(class_match.group(1)))]))
        elif language == 'python':
            func_pattern = re.compile('^\\s*def\\s+(\\w+)\\s*\\(')
            class_pattern = re.compile('^\\s*class\\s+(\\w+)')
            for i, line in enumerate(lines):
                func_match = func_pattern.match(line)
                if func_match:
                    children.append(ParsedNode(type='function_definition', text=line, start_line=i + 1, end_line=i + 1, start_col=0, end_col=len(line), children=[ParsedNode(type='identifier', text=func_match.group(1), start_line=i + 1, end_line=i + 1, start_col=line.find(func_match.group(1)), end_col=line.find(func_match.group(1)) + len(func_match.group(1)))]))
                class_match = class_pattern.match(line)
                if class_match:
                    children.append(ParsedNode(type='class_definition', text=line, start_line=i + 1, end_line=i + 1, start_col=0, end_col=len(line), children=[ParsedNode(type='identifier', text=class_match.group(1), start_line=i + 1, end_line=i + 1, start_col=line.find(class_match.group(1)), end_col=line.find(class_match.group(1)) + len(class_match.group(1)))]))
        return ParsedNode(type='translation_unit', text=content, start_line=1, end_line=len(lines), start_col=0, end_col=len(lines[-1]) if lines else 0, children=children)