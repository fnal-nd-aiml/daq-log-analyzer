"""
File: patterns.py
Purpose: Pattern matching logic.
Category: Utility
Author: artdaq team
Depends: models
Exports: match_signature, normalize_message, extract_signature, calculate_pattern_confidence
Complexity: Medium | Lines: 74
"""

import re
from srcs.models import ErrorSignature


def match_signature(pattern: ErrorSignature, candidate: ErrorSignature) -> float:
    score = 0.0
    weights = {"function": 0.4, "message": 0.4, "level": 0.1, "component": 0.1}
    if pattern.function and candidate.function:
        if pattern.function == candidate.function:
            score += weights["function"]
    elif not pattern.function:
        score += weights["function"] * 0.5
    if pattern.message_pattern and candidate.message_pattern:
        if _message_matches(pattern.message_pattern, candidate.message_pattern):
            score += weights["message"]
    elif not pattern.message_pattern:
        score += weights["message"] * 0.5
    if pattern.level == candidate.level:
        score += weights["level"]
    if pattern.component and candidate.component:
        if pattern.component == candidate.component:
            score += weights["component"]
        elif _component_partial_match(pattern.component, candidate.component):
            score += weights["component"] * 0.5
    elif not pattern.component:
        score += weights["component"] * 0.5
    return score


def _message_matches(pattern: str, message: str) -> bool:
    regex = re.escape(pattern)
    regex = regex.replace("\\{N\\}", "\\d+")
    regex = regex.replace("\\{HEX\\}", "0x[0-9a-fA-F]+")
    regex = regex.replace("\\{FLOAT\\}", "\\d+\\.\\d+")
    regex = regex.replace("\\{ID\\}", "[a-zA-Z_][a-zA-Z0-9_]*")
    try:
        return bool(re.match(f"^{regex}$", message))
    except re.error:
        return pattern == message


def _component_partial_match(pattern: str, component: str) -> bool:
    pattern_base = re.sub("\\d+$", "", pattern)
    component_base = re.sub("\\d+$", "", component)
    return pattern_base.lower() == component_base.lower()


def normalize_message(message: str) -> str:
    pattern = message
    pattern = re.sub("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "{UUID}", pattern)
    pattern = re.sub("0x[0-9a-fA-F]+", "{HEX}", pattern)
    pattern = re.sub("\\d+\\.\\d+", "{FLOAT}", pattern)
    pattern = re.sub("\\b\\d+\\b", "{N}", pattern)
    pattern = re.sub(
        "\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?", "{TIMESTAMP}", pattern
    )
    return pattern


def extract_signature(
    function: str | None, message: str, level: str = "ERROR", component: str | None = None
) -> ErrorSignature:
    return ErrorSignature(
        function=function, message_pattern=normalize_message(message), level=level, component=component
    )


def calculate_pattern_confidence(times_correct: int, times_incorrect: int, base_confidence: float = 0.5) -> float:
    prior_alpha = base_confidence * 2
    prior_beta = (1 - base_confidence) * 2
    posterior_alpha = prior_alpha + times_correct
    posterior_beta = prior_beta + times_incorrect
    confidence = posterior_alpha / (posterior_alpha + posterior_beta)
    return confidence
