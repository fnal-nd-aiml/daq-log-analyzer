"""
File: cpp.py
Purpose: C++ language extractor.
Category: Utility
Author: artdaq team
Depends: None
Exports: CppExtractor
Complexity: Medium | Lines: 283
"""

import logging
import re
from pathlib import Path
from typing import Any
from .base import (
    ExtractedClass,
    ExtractedDependency,
    ExtractedFunction,
    ExtractionResult,
    ExtractionStrategy,
    LanguageExtractor,
)

logger = logging.getLogger(__name__)


class CppExtractor(LanguageExtractor):

    @property
    def language_id(self) -> str:
        return "cpp"

    @property
    def extensions(self) -> list[str]:
        return [".cpp", ".cxx", ".cc", ".c", ".h", ".hpp", ".hxx"]

    def extract(self, content: str, file_path: Path, strategy: ExtractionStrategy) -> ExtractionResult:
        result = ExtractionResult()
        lang = "cpp" if file_path.suffix.lower() in (".cpp", ".cxx", ".cc", ".hpp", ".hxx") else "c"
        parsed = strategy.parse(content, lang)
        if not parsed:
            result.errors.append(f"Failed to parse {file_path}")
            return result
        if hasattr(parsed, "find_all"):
            result.functions = self._extract_functions_from_tree(parsed, file_path, content, strategy)
            result.classes = self._extract_classes_from_tree(parsed, file_path, content)
            result.dependencies = self._extract_includes_from_tree(parsed, file_path)
        else:
            result.functions = self._extract_functions_from_regex(parsed, file_path, content)
            result.classes = self._extract_classes_from_regex(parsed, file_path, content)
            result.dependencies = self._extract_includes_from_regex(parsed, file_path)
        return result

    def _extract_functions_from_tree(
        self, root: Any, file_path: Path, content: str, strategy: ExtractionStrategy
    ) -> list[ExtractedFunction]:
        functions = []
        for node in root.find_all("function_definition"):
            func = self._extract_function_from_node(node, file_path, content, strategy)
            if func:
                functions.append(func)
        return functions

    def _extract_function_from_node(
        self, node: Any, file_path: Path, content: str, strategy: ExtractionStrategy
    ) -> ExtractedFunction | None:
        name = None
        declarator = node.find_first("function_declarator")
        if declarator:
            identifier = declarator.find_first("identifier")
            if identifier:
                name = identifier.text
            else:
                qualified = declarator.find_first("qualified_identifier")
                if qualified:
                    name = qualified.text
        if not name:
            match = re.search("(\\w+)\\s*\\(", node.text)
            if match:
                name = match.group(1)
            else:
                return None
        return_type = ""
        for child in node.children:
            if child.type in ("type_identifier", "primitive_type"):
                return_type = child.text
                break
        parameters = self._extract_parameters(node.text)
        modifiers = []
        if "const" in node.text:
            modifiers.append("const")
        if "static" in node.text:
            modifiers.append("static")
        if "virtual" in node.text:
            modifiers.append("virtual")
        if "inline" in node.text:
            modifiers.append("inline")
        calls = self.extract_calls_from_function(node, strategy)
        sig_end = node.text.find("{")
        signature = node.text[:sig_end].strip() if sig_end > 0 else node.text.split("\n")[0]
        return ExtractedFunction(
            name=name,
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=signature,
            body=node.text,
            return_type=return_type,
            parameters=parameters,
            modifiers=modifiers,
            calls=calls,
        )

    def _extract_functions_from_regex(self, matches: list, file_path: Path, content: str) -> list[ExtractedFunction]:
        functions = []
        for match in matches:
            if match.type != "function_definition":
                continue
            name = match.groups.get("name", "")
            if not name:
                continue
            functions.append(
                ExtractedFunction(
                    name=name,
                    file_path=file_path,
                    start_line=match.start_line,
                    end_line=match.end_line,
                    signature=match.text.split("{")[0].strip(),
                    body=match.text,
                    return_type=match.groups.get("return_type", ""),
                    parameters=self._extract_parameters(match.groups.get("params", "")),
                    modifiers=match.groups.get("modifiers", "").split(),
                    calls=[],
                )
            )
        return functions

    def _extract_parameters(self, text: str) -> list[tuple[str, str]]:
        params = []
        param_match = re.search("\\(([^)]*)\\)", text)
        if param_match:
            params_str = param_match.group(1)
            for param in params_str.split(","):
                param = param.strip()
                if param:
                    parts = param.rsplit(" ", 1)
                    if len(parts) == 2:
                        params.append((parts[1].strip("&*"), parts[0]))
                    elif parts[0]:
                        params.append((parts[0], ""))
        return params

    def _extract_classes_from_tree(self, root: Any, file_path: Path, content: str) -> list[ExtractedClass]:
        classes = []
        for node_type in ("class_specifier", "struct_specifier"):
            for node in root.find_all(node_type):
                cls = self._extract_class_from_node(node, file_path, is_struct=node_type == "struct_specifier")
                if cls:
                    classes.append(cls)
        return classes

    def _extract_class_from_node(self, node: Any, file_path: Path, is_struct: bool = False) -> ExtractedClass | None:
        name = None
        type_id = node.find_first("type_identifier")
        if type_id:
            name = type_id.text
        if not name:
            keyword = "struct" if is_struct else "class"
            match = re.search(f"{keyword}\\s+(\\w+)", node.text)
            if match:
                name = match.group(1)
            else:
                return None
        base_classes = []
        base_clause = node.find_first("base_class_clause")
        if base_clause:
            for type_id in base_clause.find_all("type_identifier"):
                base_classes.append(type_id.text)
        keyword = "struct" if is_struct else "class"
        signature = f"{keyword} {name}"
        if base_classes:
            signature += f" : {', '.join(base_classes)}"
        return ExtractedClass(
            name=name,
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=signature,
            base_classes=base_classes,
        )

    def _extract_classes_from_regex(self, matches: list, file_path: Path, content: str) -> list[ExtractedClass]:
        classes = []
        for match in matches:
            if match.type not in ("class_specifier", "struct_specifier"):
                continue
            name = match.groups.get("name", "")
            if not name:
                continue
            bases_str = match.groups.get("bases", "")
            base_classes = [b.strip() for b in bases_str.split(",") if b.strip()] if bases_str else []
            keyword = "struct" if match.type == "struct_specifier" else "class"
            signature = f"{keyword} {name}"
            if base_classes:
                signature += f" : {', '.join(base_classes)}"
            classes.append(
                ExtractedClass(
                    name=name,
                    file_path=file_path,
                    start_line=match.start_line,
                    end_line=match.end_line,
                    signature=signature,
                    base_classes=base_classes,
                )
            )
        return classes

    def _extract_includes_from_tree(self, root: Any, file_path: Path) -> list[ExtractedDependency]:
        includes = []
        for node in root.find_all("preproc_include"):
            include_path = ""
            is_system = False
            for child in node.children:
                if child.type == "system_lib_string":
                    include_path = child.text.strip("<>")
                    is_system = True
                elif child.type == "string_literal":
                    include_path = child.text.strip('"')
                    is_system = False
            if include_path:
                includes.append(
                    ExtractedDependency(
                        imported_path=include_path,
                        import_type="include",
                        is_system=is_system,
                        line_number=node.start_line,
                    )
                )
        return includes

    def _extract_includes_from_regex(self, matches: list, file_path: Path) -> list[ExtractedDependency]:
        includes = []
        for match in matches:
            if match.type != "preproc_include":
                continue
            include_path = match.groups.get("path", "")
            is_system = match.groups.get("is_system", "False") == "True"
            if include_path:
                includes.append(
                    ExtractedDependency(
                        imported_path=include_path,
                        import_type="include",
                        is_system=is_system,
                        line_number=match.start_line,
                    )
                )
        return includes

    def extract_calls_from_function(self, func_node: Any, strategy: ExtractionStrategy) -> list[tuple[str, int, str]]:
        calls = []
        if not hasattr(func_node, "find_all"):
            return calls
        for call_node in func_node.find_all("call_expression"):
            callee_name = None
            call_type = "direct"
            for child in call_node.children:
                if child.type == "identifier":
                    callee_name = child.text
                    call_type = "direct"
                    break
                elif child.type == "qualified_identifier":
                    callee_name = child.text
                    call_type = "direct"
                    break
                elif child.type == "field_expression":
                    field_id = child.find_first("field_identifier")
                    if field_id:
                        callee_name = field_id.text
                        call_type = "method"
                    break
                elif child.type == "template_function":
                    identifier = child.find_first("identifier")
                    if identifier:
                        callee_name = identifier.text
                        call_type = "direct"
                    break
            if callee_name:
                calls.append((callee_name, call_node.start_line, call_type))
        for new_node in func_node.find_all("new_expression"):
            type_id = new_node.find_first("type_identifier")
            if type_id:
                calls.append((type_id.text, new_node.start_line, "constructor"))
        return calls
