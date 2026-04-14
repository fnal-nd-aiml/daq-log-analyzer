"""
File: json_utils.py
Purpose: JSON extraction and repair utilities for LLM responses.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: extract_json, fix_json, parse_json_response, T
Complexity: Medium | Lines: 135
"""

import logging
import re
from typing import TypeVar
from pydantic import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def extract_json(response: str) -> str:
    response = response.strip()
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()
    json_match = re.search("(\\{[\\s\\S]*\\}|\\[[\\s\\S]*\\])", response)
    if json_match:
        return json_match.group(1)
    return response


def fix_json(json_str: str) -> str:
    fixed = json_str
    fixed = re.sub(",\\s*([}\\]])", "\\1", fixed)
    fixed = re.sub("(\\{|\\,)\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*:", '\\1"\\2":', fixed)
    fixed = _convert_single_quotes(fixed)
    fixed = _repair_truncation(fixed)
    fixed = _remove_comments(fixed)
    return fixed


def _convert_single_quotes(json_str: str) -> str:
    result = []
    i = 0
    in_double_string = False
    in_single_string = False
    while i < len(json_str):
        char = json_str[i]
        if char == "\\" and i + 1 < len(json_str):
            result.append(char)
            result.append(json_str[i + 1])
            i += 2
            continue
        if char == '"' and (not in_single_string):
            in_double_string = not in_double_string
            result.append(char)
        elif char == "'" and (not in_double_string):
            in_single_string = not in_single_string
            result.append('"')
        else:
            result.append(char)
        i += 1
    return "".join(result)


def _repair_truncation(json_str: str) -> str:
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False
    for char in json_str:
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            open_braces += 1
        elif char == "}":
            open_braces -= 1
        elif char == "[":
            open_brackets += 1
        elif char == "]":
            open_brackets -= 1
    result = json_str
    if open_braces > 0 or open_brackets > 0:
        result += "]" * max(0, open_brackets)
        result += "}" * max(0, open_braces)
    return result


def _remove_comments(json_str: str) -> str:
    result = re.sub("/\\*[\\s\\S]*?\\*/", "", json_str)
    lines = result.split("\n")
    cleaned_lines = []
    for line in lines:
        in_string = False
        escape_next = False
        comment_start = -1
        for i, char in enumerate(line):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string and char == "/" and (i + 1 < len(line)) and (line[i + 1] == "/"):
                comment_start = i
                break
        if comment_start >= 0:
            cleaned_lines.append(line[:comment_start].rstrip())
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def parse_json_response(response: str, model: type[T], fix_on_error: bool = True) -> T:
    json_str = extract_json(response)
    try:
        return model.model_validate_json(json_str)
    except Exception as e:
        if not fix_on_error:
            raise ValueError(f"Failed to parse JSON response: {e}") from e
        logger.warning(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response was: {response}")
        fixed_json = fix_json(json_str)
        try:
            return model.model_validate_json(fixed_json)
        except Exception as e2:
            raise ValueError(f"Failed to parse JSON response even after fixing: {e2}") from e2
