"""JSON extraction and repair utilities for LLM responses.

Consolidates duplicated JSON handling logic from LLM providers
into a single, reusable module.
"""

import logging
import re
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def extract_json(response: str) -> str:
    """Extract JSON from LLM response text.

    Handles various formats including:
    - Markdown code blocks (```json ... ``` or ``` ... ```)
    - Raw JSON objects/arrays
    - JSON embedded in explanatory text

    Args:
        response: Raw LLM response text

    Returns:
        Extracted JSON string

    Example:
        >>> response = '''Here's the analysis:
        ... ```json
        ... {"result": "success"}
        ... ```
        ... '''
        >>> extract_json(response)
        '{"result": "success"}'
    """
    response = response.strip()

    # Try to find JSON in ```json code blocks
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()

    # Try to find JSON in generic ``` code blocks
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()

    # Try to find a JSON object or array in the response.
    extracted = _scan_balanced(response)
    if extracted is not None:
        return extracted

    # Return as-is if no JSON structure found
    return response


def _scan_balanced(text: str) -> str | None:
    """Return the first balanced {...} or [...] region in `text`.

    Replaces a greedy `r"(\\{[\\s\\S]*\\}|\\[[\\s\\S]*\\])"`, which matched from
    the first opening brace to the *last* closing one. Given two top-level
    objects, or prose that happens to contain a brace after the JSON, that
    produced a concatenation which is not valid JSON.

    Brace counting is skipped inside string literals so that braces in values
    (`{"msg": "unbalanced { here"}`) do not throw the depth off, and escaped
    quotes do not end a string early.

    Args:
        text: Text that may contain a JSON value.

    Returns:
        The first balanced region, or None if there is no complete one.
    """
    openers = {"{": "}", "[": "]"}

    for start, char in enumerate(text):
        if char not in openers:
            continue

        closer = openers[char]
        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            current = text[index]

            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current == char:
                depth += 1
            elif current == closer:
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        # Unbalanced from here on; fix_json()'s truncation repair is the
        # fallback, so hand back the remainder rather than nothing.
        return text[start:]

    return None


def fix_json(json_str: str) -> str:
    """Attempt to fix common JSON formatting issues using multi-pass repair.

    Handles:
    - Pass 1: Trailing commas before closing braces/brackets
    - Pass 1: Unquoted property names
    - Pass 2: Single quotes to double quotes
    - Pass 3: Truncation repair (unbalanced braces/brackets)
    - Pass 4: Comment removal (// and /* */ style)

    Args:
        json_str: Potentially malformed JSON string

    Returns:
        Fixed JSON string

    Example:
        >>> fix_json('{"items": [1, 2, 3,], name: "test"}')
        '{"items": [1, 2, 3], "name": "test"}'
        >>> fix_json("{'key': 'value'}")
        '{"key": "value"}'
    """
    fixed = json_str

    # === Pass 1: Basic fixes (original) ===
    # Remove trailing commas before closing braces/brackets
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)

    # Ensure property names are quoted
    # Matches: { key: or , key: and adds quotes around key
    fixed = re.sub(r"(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', fixed)

    # === Pass 2: Single quotes to double quotes ===
    # Replace single quotes with double quotes for property names and string values
    # Be careful not to replace apostrophes inside strings
    # Match single-quoted strings: 'value' -> "value"
    # This is a simplistic approach - handles common cases
    fixed = _convert_single_quotes(fixed)

    # === Pass 3: Truncation repair ===
    # Count unbalanced braces and brackets and append missing closers
    fixed = _repair_truncation(fixed)

    # === Pass 4: Comment removal ===
    # Remove // line comments and /* */ block comments
    fixed = _remove_comments(fixed)

    return fixed


def _convert_single_quotes(json_str: str) -> str:
    """Convert single quotes to double quotes in JSON string.

    Handles the common case where LLMs return JSON with single quotes
    instead of double quotes for strings.

    Args:
        json_str: JSON string potentially with single quotes

    Returns:
        JSON string with double quotes
    """
    result = []
    i = 0
    in_double_string = False
    in_single_string = False

    while i < len(json_str):
        char = json_str[i]

        # Handle escape sequences
        if char == '\\' and i + 1 < len(json_str):
            result.append(char)
            result.append(json_str[i + 1])
            i += 2
            continue

        # Track string state
        if char == '"' and not in_single_string:
            in_double_string = not in_double_string
            result.append(char)
        elif char == "'" and not in_double_string:
            # Convert single quote to double quote
            in_single_string = not in_single_string
            result.append('"')
        else:
            result.append(char)

        i += 1

    return ''.join(result)


def _repair_truncation(json_str: str) -> str:
    """Repair truncated JSON by appending missing closing characters.

    Counts unbalanced braces {} and brackets [] and appends the
    necessary closing characters to complete the JSON structure.

    Args:
        json_str: Potentially truncated JSON string

    Returns:
        JSON string with balanced braces/brackets
    """
    # Count braces and brackets (ignoring those inside strings)
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for char in json_str:
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == '{':
            open_braces += 1
        elif char == '}':
            open_braces -= 1
        elif char == '[':
            open_brackets += 1
        elif char == ']':
            open_brackets -= 1

    # Append missing closers. Close an unterminated string FIRST — otherwise the
    # appended braces/brackets land inside the open string and the result is
    # still invalid (e.g. '{"name": "buffer overflo' -> '{"name": "buffer overflo"}').
    result = json_str
    if in_string:
        result += '"'
    if open_braces > 0 or open_brackets > 0:
        # Append in reverse order of likely nesting
        result += ']' * max(0, open_brackets)
        result += '}' * max(0, open_braces)

    return result


def _remove_comments(json_str: str) -> str:
    """Remove JavaScript-style comments from JSON string.

    Removes:
    - Single-line comments: // comment
    - Block comments: /* comment */

    Args:
        json_str: JSON string potentially containing comments

    Returns:
        JSON string with comments removed
    """
    # Remove block comments first (they can span lines)
    result = re.sub(r'/\*[\s\S]*?\*/', '', json_str)

    # Remove single-line comments (but not inside strings)
    # This is a simplified approach - handles common cases
    lines = result.split('\n')
    cleaned_lines = []

    for line in lines:
        # Find // that's not inside a string
        in_string = False
        escape_next = False
        comment_start = -1

        for i, char in enumerate(line):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string and char == '/' and i + 1 < len(line) and line[i + 1] == '/':
                comment_start = i
                break

        if comment_start >= 0:
            cleaned_lines.append(line[:comment_start].rstrip())
        else:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def parse_json_response(
    response: str,
    model: type[T],
    fix_on_error: bool = True,
) -> T:
    """Parse LLM response text into a Pydantic model.

    Combines JSON extraction, validation, and optional repair
    into a single convenient function.

    Args:
        response: Raw LLM response text
        model: Pydantic model class to parse into
        fix_on_error: If True, attempt to fix JSON on parse failure

    Returns:
        Instance of the specified model

    Raises:
        ValueError: If JSON cannot be parsed even after fixing

    Example:
        >>> class Result(BaseModel):
        ...     items: list[str]
        >>> response = '```json\\n{"items": ["a", "b"]}\\n```'
        >>> result = parse_json_response(response, Result)
        >>> result.items
        ['a', 'b']
    """
    json_str = extract_json(response)

    try:
        return model.model_validate_json(json_str)
    except Exception as e:
        if not fix_on_error:
            raise ValueError(f"Failed to parse JSON response: {e}") from e

        logger.warning(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response was: {response}")

        # Try to fix common issues and retry
        fixed_json = fix_json(json_str)
        try:
            return model.model_validate_json(fixed_json)
        except Exception as e2:
            raise ValueError(
                f"Failed to parse JSON response even after fixing: {e2}"
            ) from e2
