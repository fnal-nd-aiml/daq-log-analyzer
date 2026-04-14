"""
File: regex.py
Purpose: Regex-based extraction strategy.
Category: Utility
Author: artdaq team
Depends: None
Exports: RegexMatch, RegexStrategy
Complexity: Medium | Lines: 182
"""

import logging
import re
from dataclasses import dataclass, field
from ..base import ExtractionStrategy

logger = logging.getLogger(__name__)


@dataclass
class RegexMatch:
    type: str
    text: str
    start_line: int
    end_line: int
    groups: dict[str, str] = field(default_factory=dict)
    children: list["RegexMatch"] = field(default_factory=list)

    def find_all(self, match_type: str) -> list["RegexMatch"]:
        results = []
        if self.type == match_type:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(match_type))
        return results


class RegexStrategy(ExtractionStrategy):
    CPP_FUNCTION_PATTERN = re.compile(
        "^(?P<modifiers>(?:static|virtual|inline|const|constexpr|explicit)\\s+)*(?P<return_type>[\\w:*&<>,\\s]+?)\\s+(?P<name>[\\w:]+)\\s*\\((?P<params>[^)]*)\\)\\s*(?P<const>const)?\\s*(?:override|final)?\\s*\\{",
        re.MULTILINE,
    )
    CPP_CLASS_PATTERN = re.compile(
        "^(?P<keyword>class|struct)\\s+(?P<name>\\w+)\\s*(?::\\s*(?P<bases>(?:public|private|protected)?\\s*[\\w:,\\s]+))?\\s*\\{",
        re.MULTILINE,
    )
    PYTHON_FUNCTION_PATTERN = re.compile(
        "^(?P<indent>\\s*)def\\s+(?P<name>\\w+)\\s*\\((?P<params>[^)]*)\\)\\s*(?:->\\s*(?P<return_type>[^:]+))?\\s*:",
        re.MULTILINE,
    )
    PYTHON_CLASS_PATTERN = re.compile(
        "^(?P<indent>\\s*)class\\s+(?P<name>\\w+)\\s*(?:\\((?P<bases>[^)]*)\\))?\\s*:", re.MULTILINE
    )
    CPP_INCLUDE_PATTERN = re.compile('^\\s*#\\s*include\\s+([<"])([^>"]+)[>"]', re.MULTILINE)
    PYTHON_IMPORT_PATTERN = re.compile("^\\s*(?:from\\s+([\\w.]+)\\s+)?import\\s+([\\w.,\\s]+)", re.MULTILINE)

    def __init__(self):
        self._supported = ["cpp", "c", "python"]

    @property
    def name(self) -> str:
        return "regex"

    def is_available(self) -> bool:
        return True

    def supported_languages(self) -> list[str]:
        return self._supported.copy()

    def parse(self, content: str, language: str) -> list[RegexMatch]:
        if language in ("cpp", "c"):
            return self._parse_cpp(content)
        elif language == "python":
            return self._parse_python(content)
        return []

    def _parse_cpp(self, content: str) -> list[RegexMatch]:
        matches = []
        lines = content.split("\n")
        for match in self.CPP_FUNCTION_PATTERN.finditer(content):
            start_line = content[: match.start()].count("\n") + 1
            end_line = self._find_block_end(lines, start_line - 1)
            matches.append(
                RegexMatch(
                    type="function_definition",
                    text="\n".join(lines[start_line - 1 : end_line]),
                    start_line=start_line,
                    end_line=end_line,
                    groups={
                        "name": match.group("name"),
                        "return_type": match.group("return_type").strip() if match.group("return_type") else "",
                        "params": match.group("params"),
                        "modifiers": match.group("modifiers") or "",
                    },
                )
            )
        for match in self.CPP_CLASS_PATTERN.finditer(content):
            start_line = content[: match.start()].count("\n") + 1
            end_line = self._find_block_end(lines, start_line - 1)
            matches.append(
                RegexMatch(
                    type="class_specifier" if match.group("keyword") == "class" else "struct_specifier",
                    text="\n".join(lines[start_line - 1 : end_line]),
                    start_line=start_line,
                    end_line=end_line,
                    groups={"name": match.group("name"), "bases": match.group("bases") or ""},
                )
            )
        for match in self.CPP_INCLUDE_PATTERN.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            is_system = match.group(1) == "<"
            matches.append(
                RegexMatch(
                    type="preproc_include",
                    text=match.group(0),
                    start_line=line_num,
                    end_line=line_num,
                    groups={"path": match.group(2), "is_system": str(is_system)},
                )
            )
        return matches

    def _parse_python(self, content: str) -> list[RegexMatch]:
        matches = []
        lines = content.split("\n")
        for match in self.PYTHON_FUNCTION_PATTERN.finditer(content):
            start_line = content[: match.start()].count("\n") + 1
            indent = len(match.group("indent"))
            end_line = self._find_python_block_end(lines, start_line - 1, indent)
            matches.append(
                RegexMatch(
                    type="function_definition",
                    text="\n".join(lines[start_line - 1 : end_line]),
                    start_line=start_line,
                    end_line=end_line,
                    groups={
                        "name": match.group("name"),
                        "params": match.group("params"),
                        "return_type": match.group("return_type") or "",
                    },
                )
            )
        for match in self.PYTHON_CLASS_PATTERN.finditer(content):
            start_line = content[: match.start()].count("\n") + 1
            indent = len(match.group("indent"))
            end_line = self._find_python_block_end(lines, start_line - 1, indent)
            matches.append(
                RegexMatch(
                    type="class_definition",
                    text="\n".join(lines[start_line - 1 : end_line]),
                    start_line=start_line,
                    end_line=end_line,
                    groups={"name": match.group("name"), "bases": match.group("bases") or ""},
                )
            )
        for match in self.PYTHON_IMPORT_PATTERN.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            module = match.group(1) or match.group(2).split(",")[0].strip()
            matches.append(
                RegexMatch(
                    type="import_statement",
                    text=match.group(0),
                    start_line=line_num,
                    end_line=line_num,
                    groups={"module": module, "from_module": match.group(1) or "", "imports": match.group(2)},
                )
            )
        return matches

    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        brace_count = 0
        started = False
        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    started = True
                elif char == "}":
                    brace_count -= 1
            if started and brace_count == 0:
                return i + 1
        return len(lines)

    def _find_python_block_end(self, lines: list[str], start_idx: int, base_indent: int) -> int:
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip():
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent and line.strip():
                return i
        return len(lines)
