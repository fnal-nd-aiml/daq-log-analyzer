"""
File: python.py
Purpose: Python language extractor.
Category: Utility
Author: artdaq team
Depends: None
Exports: PythonExtractor, PYTHON_STDLIB_MODULES
Complexity: Medium | Lines: 411
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
PYTHON_STDLIB_MODULES = {
    "os",
    "sys",
    "re",
    "json",
    "logging",
    "pathlib",
    "typing",
    "collections",
    "itertools",
    "functools",
    "datetime",
    "time",
    "threading",
    "multiprocessing",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "email",
    "html",
    "xml",
    "sqlite3",
    "pickle",
    "hashlib",
    "io",
    "abc",
    "copy",
    "pprint",
    "traceback",
    "inspect",
    "ast",
    "dataclasses",
    "enum",
    "contextlib",
    "asyncio",
    "concurrent",
    "unittest",
    "pytest",
    "argparse",
    "configparser",
    "tempfile",
    "shutil",
    "glob",
    "fnmatch",
    "string",
    "textwrap",
    "struct",
    "codecs",
    "base64",
    "binascii",
    "random",
    "secrets",
    "math",
    "statistics",
    "decimal",
    "fractions",
    "numbers",
    "operator",
    "functools",
    "itertools",
    "bisect",
    "heapq",
    "array",
    "weakref",
}


class PythonExtractor(LanguageExtractor):

    @property
    def language_id(self) -> str:
        return "python"

    @property
    def extensions(self) -> list[str]:
        return [".py"]

    def extract(self, content: str, file_path: Path, strategy: ExtractionStrategy) -> ExtractionResult:
        result = ExtractionResult()
        parsed = strategy.parse(content, "python")
        if not parsed:
            result.errors.append(f"Failed to parse {file_path}")
            return result
        if hasattr(parsed, "find_all"):
            result.functions = self._extract_functions_from_tree(parsed, file_path, content, strategy)
            result.classes = self._extract_classes_from_tree(parsed, file_path, content)
            result.dependencies = self._extract_imports_from_tree(parsed, file_path)
        else:
            result.functions = self._extract_functions_from_regex(parsed, file_path, content)
            result.classes = self._extract_classes_from_regex(parsed, file_path, content)
            result.dependencies = self._extract_imports_from_regex(parsed, file_path)
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
        for child in node.children:
            if child.type == "identifier":
                name = child.text
                break
        if not name:
            match = re.search("def\\s+(\\w+)", node.text)
            if match:
                name = match.group(1)
            else:
                return None
        parameters = []
        params_node = node.find_first("parameters")
        if params_node:
            parameters = self._extract_parameters_from_node(params_node)
        else:
            parameters = self._extract_parameters_regex(node.text)
        return_type = None
        for child in node.children:
            if child.type == "type":
                return_type = child.text
                break
        docstring = self._extract_docstring(node)
        calls = self.extract_calls_from_function(node, strategy)
        sig_end = node.text.find(":")
        signature = node.text[: sig_end + 1].strip() if sig_end > 0 else f"def {name}():"
        return ExtractedFunction(
            name=name,
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=signature,
            body=node.text,
            return_type=return_type,
            parameters=parameters,
            docstring=docstring,
            calls=calls,
        )

    def _extract_parameters_from_node(self, params_node: Any) -> list[tuple[str, str]]:
        params = []
        for child in params_node.children:
            if child.type == "identifier":
                params.append((child.text, ""))
            elif child.type == "typed_parameter":
                param_name = ""
                param_type = ""
                for subchild in child.children:
                    if subchild.type == "identifier":
                        param_name = subchild.text
                    elif subchild.type == "type":
                        param_type = subchild.text
                if param_name:
                    params.append((param_name, param_type))
            elif child.type == "typed_default_parameter":
                param_name = ""
                param_type = ""
                for subchild in child.children:
                    if subchild.type == "identifier":
                        param_name = subchild.text
                    elif subchild.type == "type":
                        param_type = subchild.text
                if param_name:
                    params.append((param_name, param_type))
            elif child.type == "default_parameter":
                identifier = child.find_first("identifier")
                if identifier:
                    params.append((identifier.text, ""))
        return params

    def _extract_parameters_regex(self, text: str) -> list[tuple[str, str]]:
        params = []
        match = re.search("def\\s+\\w+\\s*\\(([^)]*)\\)", text)
        if match:
            params_str = match.group(1)
            for param in params_str.split(","):
                param = param.strip()
                if not param or param in ("self", "cls"):
                    continue
                if ":" in param:
                    parts = param.split(":")
                    name = parts[0].strip()
                    type_hint = parts[1].split("=")[0].strip() if len(parts) > 1 else ""
                    params.append((name, type_hint))
                else:
                    name = param.split("=")[0].strip()
                    if name:
                        params.append((name, ""))
        return params

    def _extract_docstring(self, node: Any) -> str | None:
        lines = node.text.split("\n")
        for line in lines[1:5]:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote = '"""' if stripped.startswith('"""') else "'''"
                doc_match = re.search(f"{quote}(.+?){quote}", node.text, re.DOTALL)
                if doc_match:
                    return doc_match.group(1).strip()
                break
        return None

    def _extract_functions_from_regex(self, matches: list, file_path: Path, content: str) -> list[ExtractedFunction]:
        functions = []
        for match in matches:
            if match.type != "function_definition":
                continue
            name = match.groups.get("name", "")
            if not name:
                continue
            params_str = match.groups.get("params", "")
            parameters = self._extract_parameters_regex(f"def {name}({params_str}):")
            functions.append(
                ExtractedFunction(
                    name=name,
                    file_path=file_path,
                    start_line=match.start_line,
                    end_line=match.end_line,
                    signature=f"def {name}({params_str}):",
                    body=match.text,
                    return_type=match.groups.get("return_type", None),
                    parameters=parameters,
                    calls=[],
                )
            )
        return functions

    def _extract_classes_from_tree(self, root: Any, file_path: Path, content: str) -> list[ExtractedClass]:
        classes = []
        for node in root.find_all("class_definition"):
            cls = self._extract_class_from_node(node, file_path)
            if cls:
                classes.append(cls)
        return classes

    def _extract_class_from_node(self, node: Any, file_path: Path) -> ExtractedClass | None:
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = child.text
                break
        if not name:
            match = re.search("class\\s+(\\w+)", node.text)
            if match:
                name = match.group(1)
            else:
                return None
        base_classes = []
        arg_list = node.find_first("argument_list")
        if arg_list:
            for child in arg_list.children:
                if child.type == "identifier":
                    base_classes.append(child.text)
        methods = []
        for func_node in node.find_all("function_definition"):
            for child in func_node.children:
                if child.type == "identifier":
                    methods.append(child.text)
                    break
        signature = f"class {name}"
        if base_classes:
            signature += f"({', '.join(base_classes)})"
        return ExtractedClass(
            name=name,
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=signature,
            base_classes=base_classes,
            methods=methods,
        )

    def _extract_classes_from_regex(self, matches: list, file_path: Path, content: str) -> list[ExtractedClass]:
        classes = []
        for match in matches:
            if match.type != "class_definition":
                continue
            name = match.groups.get("name", "")
            if not name:
                continue
            bases_str = match.groups.get("bases", "")
            base_classes = [b.strip() for b in bases_str.split(",") if b.strip()] if bases_str else []
            signature = f"class {name}"
            if base_classes:
                signature += f"({', '.join(base_classes)})"
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

    def _extract_imports_from_tree(self, root: Any, file_path: Path) -> list[ExtractedDependency]:
        imports = []
        for node in root.find_all("import_statement"):
            for child in node.children:
                if child.type == "dotted_name":
                    module_name = child.text
                    imports.append(
                        ExtractedDependency(
                            imported_path=module_name,
                            import_type="import",
                            is_system=self._is_stdlib(module_name),
                            line_number=node.start_line,
                        )
                    )
        for node in root.find_all("import_from_statement"):
            module_name = ""
            imported_names = []
            for child in node.children:
                if child.type == "dotted_name" and (not module_name):
                    module_name = child.text
                elif child.type == "identifier" and module_name:
                    imported_names.append(child.text)
                elif child.type == "aliased_import":
                    identifier = child.find_first("identifier")
                    if identifier:
                        imported_names.append(identifier.text)
            if module_name:
                imports.append(
                    ExtractedDependency(
                        imported_path=module_name,
                        import_type="from_import",
                        is_system=self._is_stdlib(module_name),
                        line_number=node.start_line,
                        imported_names=imported_names,
                    )
                )
        return imports

    def _extract_imports_from_regex(self, matches: list, file_path: Path) -> list[ExtractedDependency]:
        imports = []
        for match in matches:
            if match.type != "import_statement":
                continue
            module = match.groups.get("module", "")
            from_module = match.groups.get("from_module", "")
            imports_str = match.groups.get("imports", "")
            if from_module:
                imported_names = [n.strip() for n in imports_str.split(",") if n.strip()]
                imports.append(
                    ExtractedDependency(
                        imported_path=from_module,
                        import_type="from_import",
                        is_system=self._is_stdlib(from_module),
                        line_number=match.start_line,
                        imported_names=imported_names,
                    )
                )
            elif module:
                imports.append(
                    ExtractedDependency(
                        imported_path=module,
                        import_type="import",
                        is_system=self._is_stdlib(module),
                        line_number=match.start_line,
                    )
                )
        return imports

    def _is_stdlib(self, module_name: str) -> bool:
        root_module = module_name.split(".")[0]
        return root_module in PYTHON_STDLIB_MODULES

    def extract_calls_from_function(self, func_node: Any, strategy: ExtractionStrategy) -> list[tuple[str, int, str]]:
        calls = []
        if not hasattr(func_node, "find_all"):
            return calls
        for call_node in func_node.find_all("call"):
            callee_name = None
            call_type = "direct"
            for child in call_node.children:
                if child.type == "identifier":
                    callee_name = child.text
                    call_type = "direct"
                    break
                elif child.type == "attribute":
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            callee_name = subchild.text
                    call_type = "method"
                    break
            if callee_name:
                calls.append((callee_name, call_node.start_line, call_type))
        return calls
