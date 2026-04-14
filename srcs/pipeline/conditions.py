"""
File: conditions.py
Purpose: Safe condition evaluation for pipeline branching.
Category: Utility
Author: artdaq team
Depends: None
Exports: VariableInterpolator, ConditionEvaluator
Complexity: Medium | Lines: 440
"""

import logging
import operator
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


class VariableInterpolator:
    PATTERN = re.compile("\\$\\{([^}]+)\\}")

    def __init__(self, investigation_config: Any = None):
        self._investigation_config = investigation_config

    def set_investigation_config(self, config: Any) -> None:
        self._investigation_config = config

    def interpolate(self, value: Any, context: dict[str, Any] | None = None) -> Any:
        if isinstance(value, str):
            return self._interpolate_string(value, context)
        elif isinstance(value, dict):
            return {k: self.interpolate(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.interpolate(v, context) for v in value]
        return value

    def _interpolate_string(self, value: str, context: dict[str, Any] | None) -> Any:
        match = self.PATTERN.fullmatch(value)
        if match:
            return self._resolve_variable(match.group(1), context)

        def replace(m: re.Match[str]) -> str:
            resolved = self._resolve_variable(m.group(1), context)
            return str(resolved) if resolved is not None else ""

        return self.PATTERN.sub(replace, value)

    def _resolve_variable(self, var_path: str, context: dict[str, Any] | None) -> Any:
        parts = var_path.split(".", 1)
        source = parts[0]
        path = parts[1] if len(parts) > 1 else None
        if source == "env":
            if path:
                return os.environ.get(path)
            return None
        if source == "investigation":
            if self._investigation_config and path:
                return getattr(self._investigation_config, path, None)
            return None
        if context and source in context:
            obj = context[source]
            if path:
                return self._get_nested_attr(obj, path)
            return obj
        logger.debug(f"Unknown variable source: {source}")
        return None

    def _get_nested_attr(self, obj: Any, path: str) -> Any:
        for attr in path.split("."):
            if obj is None:
                return None
            if hasattr(obj, attr):
                obj = getattr(obj, attr)
            elif isinstance(obj, dict):
                obj = obj.get(attr)
            else:
                return None
        return obj


class ConditionEvaluator:
    OPERATORS = {
        ">": operator.gt,
        "<": operator.lt,
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
    }
    ARITHMETIC_OPS = {
        "+": (operator.add, 1),
        "-": (operator.sub, 1),
        "*": (operator.mul, 2),
        "/": (operator.truediv, 2),
        "%": (operator.mod, 2),
    }
    COMPARISON_PATTERN = re.compile("(.+?)\\s*(>=|<=|==|!=|>|<)\\s*(.+)")
    LOGICAL_AND = re.compile("\\s+and\\s+", re.IGNORECASE)
    LOGICAL_OR = re.compile("\\s+or\\s+", re.IGNORECASE)
    INDEX_PATTERN = re.compile("^(.+?)\\[(\\d+)\\](.*)$")
    LEN_PATTERN = re.compile("^len\\((.+)\\)$")
    METHOD_PATTERN = re.compile("^(.+?)\\.([a-z_][a-z0-9_]*)\\(\\)$", re.IGNORECASE)
    STRING_METHOD_WITH_ARG_PATTERN = re.compile("^(.+?)\\.(contains|startswith|endswith)\\((['\\\"])(.+?)\\3\\)$")
    STRING_MATCHES_PATTERN = re.compile("^(.+?)\\.matches\\(([\\'\"])(.+?)\\2\\)$")
    AGGREGATE_PATTERNS = {
        "min": re.compile("^min\\((.+)\\)$"),
        "max": re.compile("^max\\((.+)\\)$"),
        "sum": re.compile("^sum\\((.+)\\)$"),
        "any": re.compile("^any\\((.+)\\)$"),
        "all": re.compile("^all\\((.+)\\)$"),
    }

    def __init__(self, context: dict[str, Any] | None = None):
        self._context = context or {}

    def set_context(self, context: dict[str, Any]) -> None:
        self._context = context

    def evaluate(self, expression: str, context: dict[str, Any] | None = None) -> bool:
        ctx = context if context is not None else self._context
        expression = expression.strip()
        if not expression:
            return True
        parts = self.LOGICAL_OR.split(expression)
        if len(parts) > 1:
            return any((self.evaluate(part.strip(), ctx) for part in parts))
        parts = self.LOGICAL_AND.split(expression)
        if len(parts) > 1:
            return all((self.evaluate(part.strip(), ctx) for part in parts))
        if expression.lower().startswith("not "):
            return not self.evaluate(expression[4:].strip(), ctx)
        match = self.COMPARISON_PATTERN.match(expression)
        if match:
            left_expr, op_str, right_expr = match.groups()
            left = self._resolve_value(left_expr.strip(), ctx)
            right = self._resolve_value(right_expr.strip(), ctx)
            if left is None or right is None:
                if op_str == "==":
                    return bool(left == right)
                elif op_str == "!=":
                    return bool(left != right)
                else:
                    return False
            op_func = self.OPERATORS[op_str]
            return bool(op_func(left, right))
        value = self._resolve_value(expression, ctx)
        return bool(value)

    def _resolve_value(self, expr: str, context: dict[str, Any]) -> Any:
        expr = expr.strip()
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False
        if expr.lower() == "none":
            return None
        try:
            if "." in expr and expr.replace(".", "", 1).lstrip("-").isdigit():
                return float(expr)
            if expr.lstrip("-").isdigit():
                return int(expr)
        except ValueError:
            pass
        if expr.startswith('"') and expr.endswith('"') or (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]
        len_match = self.LEN_PATTERN.match(expr)
        if len_match:
            inner = self._resolve_value(len_match.group(1), context)
            return len(inner) if inner is not None else 0
        for func_name, pattern in self.AGGREGATE_PATTERNS.items():
            agg_match = pattern.match(expr)
            if agg_match:
                return self._resolve_aggregate(func_name, agg_match.group(1), context)
        str_method_match = self.STRING_METHOD_WITH_ARG_PATTERN.match(expr)
        if str_method_match:
            obj_expr = str_method_match.group(1)
            method_name = str_method_match.group(2)
            arg_value = str_method_match.group(4)
            return self._resolve_string_method(obj_expr, method_name, arg_value, context)
        matches_match = self.STRING_MATCHES_PATTERN.match(expr)
        if matches_match:
            str_expr = matches_match.group(1)
            regex_pattern = matches_match.group(3)
            return self._resolve_regex_match(str_expr, regex_pattern, context)
        method_match = self.METHOD_PATTERN.match(expr)
        if method_match:
            obj_expr, method_name = method_match.groups()
            obj = self._resolve_value(obj_expr, context)
            if obj is not None:
                if isinstance(obj, str) and method_name in ("lower", "upper", "strip"):
                    return getattr(obj, method_name)()
                if hasattr(obj, method_name):
                    method = getattr(obj, method_name)
                    if callable(method):
                        return method()
            return None
        arithmetic_result = self._resolve_arithmetic(expr, context)
        if arithmetic_result is not None:
            return arithmetic_result
        return self._resolve_chain(expr, context)

    def _resolve_arithmetic(self, expr: str, context: dict[str, Any]) -> Any | None:
        tokens = self._tokenize_arithmetic(expr)
        if len(tokens) < 3:
            return None
        has_arithmetic = any((t in self.ARITHMETIC_OPS for t in tokens))
        if not has_arithmetic:
            return None
        resolved_tokens: list[Any] = []
        for token in tokens:
            if token in self.ARITHMETIC_OPS:
                resolved_tokens.append(token)
            else:
                value = self._resolve_value(token, context)
                if value is None:
                    return None
                resolved_tokens.append(value)
        i = 0
        while i < len(resolved_tokens):
            if isinstance(resolved_tokens[i], str) and resolved_tokens[i] in ("*", "/", "%"):
                op_func, _ = self.ARITHMETIC_OPS[resolved_tokens[i]]
                left = resolved_tokens[i - 1]
                right = resolved_tokens[i + 1]
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    return None
                result = op_func(left, right)
                resolved_tokens = resolved_tokens[: i - 1] + [result] + resolved_tokens[i + 2 :]
                i = i - 1
            else:
                i += 1
        i = 0
        while i < len(resolved_tokens):
            if isinstance(resolved_tokens[i], str) and resolved_tokens[i] in ("+", "-"):
                op_func, _ = self.ARITHMETIC_OPS[resolved_tokens[i]]
                left = resolved_tokens[i - 1]
                right = resolved_tokens[i + 1]
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    return None
                result = op_func(left, right)
                resolved_tokens = resolved_tokens[: i - 1] + [result] + resolved_tokens[i + 2 :]
                i = i - 1
            else:
                i += 1
        if len(resolved_tokens) == 1:
            return resolved_tokens[0]
        return None

    def _tokenize_arithmetic(self, expr: str) -> list[str]:
        tokens: list[str] = []
        current = ""
        i = 0
        while i < len(expr):
            char = expr[i]
            if char.isspace():
                if current:
                    tokens.append(current.strip())
                    current = ""
                i += 1
                continue
            if char in "+-*/%":
                if current:
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
                i += 1
                continue
            if char == "(":
                depth = 1
                start = i
                i += 1
                while i < len(expr) and depth > 0:
                    if expr[i] == "(":
                        depth += 1
                    elif expr[i] == ")":
                        depth -= 1
                    i += 1
                current += expr[start:i]
                continue
            if char in "\"'":
                quote = char
                start = i
                i += 1
                while i < len(expr) and expr[i] != quote:
                    i += 1
                i += 1
                current += expr[start:i]
                continue
            if char == ".":
                current += char
                i += 1
                continue
            if char == "[":
                depth = 1
                start = i
                i += 1
                while i < len(expr) and depth > 0:
                    if expr[i] == "[":
                        depth += 1
                    elif expr[i] == "]":
                        depth -= 1
                    i += 1
                current += expr[start:i]
                continue
            current += char
            i += 1
        if current:
            tokens.append(current.strip())
        return [t for t in tokens if t]

    def _resolve_string_method(self, obj_expr: str, method_name: str, arg: str, context: dict[str, Any]) -> bool:
        obj = self._resolve_value(obj_expr, context)
        if obj is None or not isinstance(obj, str):
            return False
        if method_name == "contains":
            return bool(arg in obj)
        elif method_name == "startswith":
            return bool(obj.startswith(arg))
        elif method_name == "endswith":
            return bool(obj.endswith(arg))
        return False

    def _resolve_regex_match(self, str_expr: str, pattern: str, context: dict[str, Any]) -> bool:
        string_val = self._resolve_value(str_expr, context)
        if string_val is None or not isinstance(string_val, str):
            return False
        try:
            return bool(re.search(pattern, string_val))
        except re.error:
            logger.warning(f"Invalid regex pattern: {pattern}")
            return False

    def _resolve_aggregate(self, func_name: str, inner_expr: str, context: dict[str, Any]) -> Any:
        if "." in inner_expr:
            parts = inner_expr.split(".", 1)
            list_expr = parts[0]
            attr_path = parts[1]
            items = self._resolve_value(list_expr, context)
            if items is None or not isinstance(items, (list, tuple)):
                return None
            values = []
            for item in items:
                val = self._resolve_attr_chain(item, attr_path)
                if val is not None:
                    values.append(val)
        else:
            values = self._resolve_value(inner_expr, context)
            if values is None:
                return None
            if not isinstance(values, (list, tuple)):
                values = [values]
        if not values:
            return None
        if func_name == "min":
            return min(values)
        elif func_name == "max":
            return max(values)
        elif func_name == "sum":
            return sum(values)
        elif func_name == "any":
            return any((bool(v) for v in values))
        elif func_name == "all":
            return all((bool(v) for v in values))
        return None

    def _resolve_chain(self, expr: str, context: dict[str, Any]) -> Any:
        index_match = self.INDEX_PATTERN.match(expr)
        if index_match:
            base_expr, index_str, remainder = index_match.groups()
            base = self._resolve_chain(base_expr, context)
            if base is None:
                return None
            try:
                index = int(index_str)
                if isinstance(base, (list, tuple)):
                    if 0 <= index < len(base):
                        value = base[index]
                    else:
                        return None
                elif isinstance(base, dict):
                    value = base.get(index)
                else:
                    return None
                if remainder:
                    if remainder.startswith("."):
                        remainder = remainder[1:]
                    return self._resolve_attr_chain(value, remainder)
                return value
            except (ValueError, IndexError, KeyError):
                return None
        parts = expr.split(".", 1)
        current_key = parts[0]
        if current_key == "." and "." in context:
            current = context["."]
            if len(parts) > 1:
                return self._resolve_attr_chain(current, parts[1])
            return current
        elif current_key in context:
            current = context[current_key]
        else:
            if "." in context:
                return self._resolve_attr_chain(context["."], expr)
            return None
        if current is None:
            return None
        if len(parts) > 1:
            return self._resolve_attr_chain(current, parts[1])
        return current

    def _resolve_attr_chain(self, obj: Any, attr_chain: str) -> Any:
        if obj is None:
            return None
        index_match = self.INDEX_PATTERN.match(attr_chain)
        if index_match:
            attr_name, index_str, after_index = index_match.groups()
            if attr_name:
                if hasattr(obj, attr_name):
                    obj = getattr(obj, attr_name)
                elif isinstance(obj, dict):
                    obj = obj.get(attr_name)
                else:
                    return None
            if obj is None:
                return None
            try:
                index = int(index_str)
                if isinstance(obj, (list, tuple)) and 0 <= index < len(obj):
                    obj = obj[index]
                elif isinstance(obj, dict):
                    obj = obj.get(index)
                else:
                    return None
                if after_index:
                    if after_index.startswith("."):
                        after_index = after_index[1:]
                    return self._resolve_attr_chain(obj, after_index)
                return obj
            except (ValueError, IndexError):
                return None
        parts = attr_chain.split(".", 1)
        attr_name = parts[0]
        if hasattr(obj, attr_name):
            value = getattr(obj, attr_name)
        elif isinstance(obj, dict):
            value = obj.get(attr_name)
        else:
            return None
        if len(parts) > 1:
            return self._resolve_attr_chain(value, parts[1])
        return value
