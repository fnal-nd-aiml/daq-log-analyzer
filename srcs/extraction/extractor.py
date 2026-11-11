"""
File: extractor.py
Purpose: Code element extraction from parsed source files.
Category: Utility
Author: artdaq team
Depends: code_relationships
Exports: CodeElement, FunctionInfo, ClassInfo, VariableInfo, CodeExtractor
Complexity: High | Lines: 456
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from srcs.models.code_relationships import FileImport
from .parser import CodeParser, ParsedFile, ParsedNode
logger = logging.getLogger(__name__)

@dataclass
class CodeElement:
    name: str
    file_path: Path
    start_line: int
    end_line: int
    signature: str
    docstring: str | None = None
    raw_text: str = ''

@dataclass
class FunctionInfo(CodeElement):
    return_type: str = ''
    parameters: list[tuple[str, str]] = field(default_factory=list)
    is_method: bool = False
    class_name: str | None = None
    modifiers: list[str] = field(default_factory=list)
    called_functions: list[str] = field(default_factory=list)
    thrown_exceptions: list[str] = field(default_factory=list)

@dataclass
class ClassInfo(CodeElement):
    base_classes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    members: list[tuple[str, str]] = field(default_factory=list)
    nested_classes: list[str] = field(default_factory=list)

@dataclass
class VariableInfo(CodeElement):
    var_type: str = ''
    is_const: bool = False
    initial_value: str | None = None

class CodeExtractor:

    def __init__(self, parser: CodeParser | None=None):
        self.parser = parser or CodeParser()

    def extract_from_file(self, path: Path) -> dict:
        parsed = self.parser.parse_file(path)
        return self.extract_from_parsed(parsed)

    def extract_from_parsed(self, parsed: ParsedFile) -> dict:
        if parsed.root is None:
            return {'functions': [], 'classes': [], 'variables': [], 'dependencies': [], 'errors': parsed.errors}
        if parsed.language in ('cpp', 'c'):
            return self._extract_cpp(parsed)
        elif parsed.language == 'python':
            return self._extract_python(parsed)
        else:
            return self._extract_generic(parsed)

    def extract_function(self, path: Path, function_name: str) -> FunctionInfo | None:
        result = self.extract_from_file(path)
        functions: list[FunctionInfo] = result.get('functions', [])
        for func in functions:
            if func.name == function_name:
                return func
        return None

    def extract_class(self, path: Path, class_name: str) -> ClassInfo | None:
        result = self.extract_from_file(path)
        classes: list[ClassInfo] = result.get('classes', [])
        for cls in classes:
            if cls.name == class_name:
                return cls
        return None

    def find_function_calls(self, parsed: ParsedFile, function_name: str) -> list[int]:
        if parsed.root is None:
            return []
        call_lines = []
        pattern = re.compile(f'\\b{re.escape(function_name)}\\s*\\(')
        for i, line in enumerate(parsed.content.split('\n'), 1):
            if pattern.search(line):
                call_lines.append(i)
        return call_lines

    def get_context_around_line(self, parsed: ParsedFile, line_num: int, context: int=5) -> tuple[list[str], FunctionInfo | None]:
        lines = parsed.get_lines(line_num - context, line_num + context)
        enclosing = None
        result = self.extract_from_parsed(parsed)
        for func in result.get('functions', []):
            if func.start_line <= line_num <= func.end_line:
                enclosing = func
                break
        return (lines, enclosing)

    def extract_dependencies(self, parsed: ParsedFile) -> list[FileImport]:
        if parsed.root is None:
            return []
        if parsed.language in ('cpp', 'c'):
            return self._extract_cpp_includes(parsed)
        elif parsed.language == 'python':
            return self._extract_python_imports(parsed)
        return []

    def _extract_cpp_includes(self, parsed: ParsedFile) -> list[FileImport]:
        imports: list[FileImport] = []
        source_file = str(parsed.path)
        if parsed.root is None:
            return imports
        for node in parsed.root.find_all('preproc_include'):
            include_path = ''
            is_system = False
            for child in node.children:
                if child.type == 'system_lib_string':
                    include_path = child.text.strip('<>')
                    is_system = True
                elif child.type == 'string_literal':
                    include_path = child.text.strip('"')
                    is_system = False
            if include_path:
                imports.append(FileImport(source_file=source_file, imported_path=include_path, import_type='include', is_system=is_system, line_number=node.start_line))
        if not imports:
            imports = self._extract_cpp_includes_regex(parsed)
        return imports

    def _extract_cpp_includes_regex(self, parsed: ParsedFile) -> list[FileImport]:
        imports = []
        source_file = str(parsed.path)
        include_pattern = re.compile('^\\s*#\\s*include\\s+([<"])([^>"]+)[>"]', re.MULTILINE)
        for match in include_pattern.finditer(parsed.content):
            bracket = match.group(1)
            include_path = match.group(2)
            is_system = bracket == '<'
            line_number = parsed.content[:match.start()].count('\n') + 1
            imports.append(FileImport(source_file=source_file, imported_path=include_path, import_type='include', is_system=is_system, line_number=line_number))
        return imports

    def _extract_python_imports(self, parsed: ParsedFile) -> list[FileImport]:
        imports: list[FileImport] = []
        source_file = str(parsed.path)
        if parsed.root is None:
            return imports
        for node in parsed.root.find_all('import_statement'):
            for child in node.children:
                if child.type == 'dotted_name':
                    imports.append(FileImport(source_file=source_file, imported_path=child.text, import_type='import', is_system=self._is_python_stdlib(child.text), line_number=node.start_line))
        for node in parsed.root.find_all('import_from_statement'):
            module_name = ''
            imported_names = []
            for child in node.children:
                if child.type == 'dotted_name' and (not module_name):
                    module_name = child.text
                elif child.type == 'identifier' and module_name:
                    imported_names.append(child.text)
                elif child.type == 'aliased_import':
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            imported_names.append(subchild.text)
                            break
            if module_name:
                imports.append(FileImport(source_file=source_file, imported_path=module_name, import_type='from_import', is_system=self._is_python_stdlib(module_name), line_number=node.start_line, imported_names=imported_names))
        if not imports:
            imports = self._extract_python_imports_regex(parsed)
        return imports

    def _extract_python_imports_regex(self, parsed: ParsedFile) -> list[FileImport]:
        imports = []
        source_file = str(parsed.path)
        import_pattern = re.compile('^\\s*import\\s+([\\w.]+)', re.MULTILINE)
        for match in import_pattern.finditer(parsed.content):
            module_name = match.group(1)
            line_number = parsed.content[:match.start()].count('\n') + 1
            imports.append(FileImport(source_file=source_file, imported_path=module_name, import_type='import', is_system=self._is_python_stdlib(module_name), line_number=line_number))
        from_pattern = re.compile('^\\s*from\\s+([\\w.]+)\\s+import\\s+([^#\\n]+)', re.MULTILINE)
        for match in from_pattern.finditer(parsed.content):
            module_name = match.group(1)
            imports_str = match.group(2)
            line_number = parsed.content[:match.start()].count('\n') + 1
            imported_names = []
            for name in imports_str.split(','):
                name = name.strip()
                if ' as ' in name:
                    name = name.split(' as ')[0].strip()
                if name and name != '(':
                    imported_names.append(name)
            imports.append(FileImport(source_file=source_file, imported_path=module_name, import_type='from_import', is_system=self._is_python_stdlib(module_name), line_number=line_number, imported_names=imported_names))
        return imports

    def _is_python_stdlib(self, module_name: str) -> bool:
        stdlib_modules = {'os', 'sys', 're', 'json', 'logging', 'pathlib', 'typing', 'collections', 'itertools', 'functools', 'datetime', 'time', 'threading', 'multiprocessing', 'subprocess', 'socket', 'http', 'urllib', 'email', 'html', 'xml', 'sqlite3', 'pickle', 'hashlib', 'io', 'abc', 'copy', 'pprint', 'traceback', 'inspect', 'ast', 'dataclasses', 'enum', 'contextlib', 'asyncio', 'concurrent'}
        root_module = module_name.split('.')[0]
        return root_module in stdlib_modules

    def _extract_calls_from_node(self, node: ParsedNode, language: str) -> list[tuple[str, int, str]]:
        calls = []
        if language in ('cpp', 'c'):
            calls = self._extract_cpp_calls(node)
        elif language == 'python':
            calls = self._extract_python_calls(node)
        return calls

    def _extract_cpp_calls(self, node: ParsedNode) -> list[tuple[str, int, str]]:
        calls = []
        for call_node in node.find_all('call_expression'):
            callee_name = None
            call_type = 'direct'
            for child in call_node.children:
                if child.type == 'identifier':
                    callee_name = child.text
                    call_type = 'direct'
                    break
                elif child.type == 'qualified_identifier':
                    callee_name = child.text
                    call_type = 'direct'
                    break
                elif child.type == 'field_expression':
                    for subchild in child.children:
                        if subchild.type == 'field_identifier':
                            callee_name = subchild.text
                            call_type = 'method'
                            break
                    break
                elif child.type == 'template_function':
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            callee_name = subchild.text
                            call_type = 'direct'
                            break
                    break
            if callee_name:
                calls.append((callee_name, call_node.start_line, call_type))
        for new_node in node.find_all('new_expression'):
            for child in new_node.children:
                if child.type == 'type_identifier':
                    calls.append((child.text, new_node.start_line, 'constructor'))
                    break
        for ptr_node in node.find_all('pointer_expression'):
            for child in ptr_node.children:
                if child.type == 'qualified_identifier':
                    calls.append((child.text, ptr_node.start_line, 'pointer'))
                    break
        ptr_pattern = re.compile('&([\\w:]+::[\\w]+)')
        for match in ptr_pattern.finditer(node.text):
            qualified_name = match.group(1)
            line_offset = node.text[:match.start()].count('\n')
            line_num = node.start_line + line_offset
            if not any((c[0] == qualified_name and c[2] == 'pointer' for c in calls)):
                calls.append((qualified_name, line_num, 'pointer'))
        return calls

    def _extract_python_calls(self, node: ParsedNode) -> list[tuple[str, int, str]]:
        calls = []
        for call_node in node.find_all('call'):
            callee_name = None
            call_type = 'direct'
            for child in call_node.children:
                if child.type == 'identifier':
                    callee_name = child.text
                    call_type = 'direct'
                    break
                elif child.type == 'attribute':
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            callee_name = subchild.text
                    call_type = 'method'
                    break
            if callee_name:
                calls.append((callee_name, call_node.start_line, call_type))
        return calls

    def _extract_cpp(self, parsed: ParsedFile) -> dict:
        functions = []
        classes: list[ClassInfo] = []
        variables: list[VariableInfo] = []
        if parsed.root is None:
            return {'functions': [], 'classes': [], 'variables': [], 'dependencies': []}
        for node in parsed.root.find_all('function_definition'):
            func = self._extract_cpp_function(node, parsed)
            if func:
                functions.append(func)
        for node in parsed.root.find_all('class_specifier'):
            cls = self._extract_cpp_class(node, parsed)
            if cls:
                classes.append(cls)
        for node in parsed.root.find_all('struct_specifier'):
            cls = self._extract_cpp_class(node, parsed, is_struct=True)
            if cls:
                classes.append(cls)
        dependencies = self.extract_dependencies(parsed)
        return {'functions': functions, 'classes': classes, 'variables': variables, 'dependencies': dependencies, 'errors': parsed.errors}

    def _extract_cpp_function(self, node: ParsedNode, parsed: ParsedFile) -> FunctionInfo | None:
        name = None
        for child in node.children:
            if child.type == 'function_declarator':
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        name = subchild.text
                        break
                    elif subchild.type == 'qualified_identifier':
                        name = subchild.text
                        break
            elif child.type == 'identifier':
                name = child.text
        if not name:
            match = re.search('(\\w+)\\s*\\(', node.text)
            if match:
                name = match.group(1)
            else:
                return None
        return_type = ''
        for child in node.children:
            if child.type in ('type_identifier', 'primitive_type'):
                return_type = child.text
                break
        parameters = []
        param_match = re.search('\\(([^)]*)\\)', node.text)
        if param_match:
            params_str = param_match.group(1)
            for param in params_str.split(','):
                param = param.strip()
                if param:
                    parts = param.rsplit(' ', 1)
                    if len(parts) == 2:
                        parameters.append((parts[1].strip('&*'), parts[0]))
                    else:
                        parameters.append((parts[0], ''))
        modifiers = []
        if 'const' in node.text:
            modifiers.append('const')
        if 'static' in node.text:
            modifiers.append('static')
        if 'virtual' in node.text:
            modifiers.append('virtual')
        calls = self._extract_calls_from_node(node, parsed.language)
        called_functions = [call[0] for call in calls]
        return FunctionInfo(name=name, file_path=parsed.path, start_line=node.start_line, end_line=node.end_line, signature=node.text.split('{')[0].strip() if '{' in node.text else node.text, return_type=return_type, parameters=parameters, modifiers=modifiers, called_functions=called_functions, raw_text=node.text)

    def _extract_cpp_class(self, node: ParsedNode, parsed: ParsedFile, is_struct: bool=False) -> ClassInfo | None:
        name = None
        for child in node.children:
            if child.type == 'type_identifier':
                name = child.text
                break
        if not name:
            keyword = 'struct' if is_struct else 'class'
            match = re.search(f'{keyword}\\s+(\\w+)', node.text)
            if match:
                name = match.group(1)
            else:
                return None
        base_classes = []
        for child in node.children:
            if child.type == 'base_class_clause':
                for subchild in child.find_all('type_identifier'):
                    base_classes.append(subchild.text)
        signature = f"{('struct' if is_struct else 'class')} {name}"
        if base_classes:
            signature += f" : {', '.join(base_classes)}"
        return ClassInfo(name=name, file_path=parsed.path, start_line=node.start_line, end_line=node.end_line, signature=signature, base_classes=base_classes, raw_text=node.text)

    def _extract_python(self, parsed: ParsedFile) -> dict:
        functions = []
        classes: list[ClassInfo] = []
        variables: list[VariableInfo] = []
        if parsed.root is None:
            return {'functions': [], 'classes': [], 'variables': [], 'dependencies': []}
        for node in parsed.root.find_all('function_definition'):
            func = self._extract_python_function(node, parsed)
            if func:
                functions.append(func)
        for node in parsed.root.find_all('class_definition'):
            cls = self._extract_python_class(node, parsed)
            if cls:
                classes.append(cls)
        dependencies = self.extract_dependencies(parsed)
        return {'functions': functions, 'classes': classes, 'variables': variables, 'dependencies': dependencies, 'errors': parsed.errors}

    def _extract_python_function(self, node: ParsedNode, parsed: ParsedFile) -> FunctionInfo | None:
        name = None
        for child in node.children:
            if child.type == 'identifier':
                name = child.text
                break
        if not name:
            match = re.search('def\\s+(\\w+)', node.text)
            if match:
                name = match.group(1)
            else:
                return None
        parameters = []
        for child in node.children:
            if child.type == 'parameters':
                for param in child.children:
                    if param.type == 'identifier':
                        parameters.append((param.text, ''))
                    elif param.type == 'typed_parameter':
                        param_name = ''
                        param_type = ''
                        for subchild in param.children:
                            if subchild.type == 'identifier':
                                param_name = subchild.text
                            elif subchild.type == 'type':
                                param_type = subchild.text
                        if param_name:
                            parameters.append((param_name, param_type))
        docstring = None
        lines = node.text.split('\n')
        for line in lines[1:5]:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                doc_match = re.search('["\\\']["\\\']["\\\'](.+?)["\\\']["\\\']["\\\']', node.text, re.DOTALL)
                if doc_match:
                    docstring = doc_match.group(1).strip()
                break
        calls = self._extract_calls_from_node(node, parsed.language)
        called_functions = [call[0] for call in calls]
        return FunctionInfo(name=name, file_path=parsed.path, start_line=node.start_line, end_line=node.end_line, signature=node.text.split(':')[0].strip() + ':', parameters=parameters, docstring=docstring, called_functions=called_functions, raw_text=node.text)

    def _extract_python_class(self, node: ParsedNode, parsed: ParsedFile) -> ClassInfo | None:
        name = None
        for child in node.children:
            if child.type == 'identifier':
                name = child.text
                break
        if not name:
            match = re.search('class\\s+(\\w+)', node.text)
            if match:
                name = match.group(1)
            else:
                return None
        base_classes = []
        for child in node.children:
            if child.type == 'argument_list':
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        base_classes.append(subchild.text)
        signature = f'class {name}'
        if base_classes:
            signature += f"({', '.join(base_classes)})"
        return ClassInfo(name=name, file_path=parsed.path, start_line=node.start_line, end_line=node.end_line, signature=signature, base_classes=base_classes, raw_text=node.text)

    def _extract_generic(self, parsed: ParsedFile) -> dict:
        functions = []
        classes: list[ClassInfo] = []
        if parsed.root:
            for node in parsed.root.find_all('function_definition'):
                name = None
                for child in node.children:
                    if child.type == 'identifier':
                        name = child.text
                        break
                if name:
                    functions.append(FunctionInfo(name=name, file_path=parsed.path, start_line=node.start_line, end_line=node.end_line, signature=node.text.split('{')[0].strip(), raw_text=node.text))
        return {'functions': functions, 'classes': classes, 'variables': [], 'dependencies': [], 'errors': parsed.errors}