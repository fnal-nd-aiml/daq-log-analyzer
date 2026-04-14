"""
File: token_utils.py
Purpose: Centralized token estimation and content truncation utilities.
Category: Utility
Author: artdaq team
Depends: None
Exports: estimate_tokens, truncate_if_needed, truncate_middle_if_needed, CHARS_PER_TOKEN
Complexity: Low | Lines: 35
"""

import logging

logger = logging.getLogger(__name__)
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_if_needed(text: str, max_tokens: int, label: str = "") -> str:
    if max_tokens <= 0 or not text:
        return text
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    tag = f" ({label})" if label else ""
    original_tokens = estimate_tokens(text)
    logger.warning("Truncating content%s from ~%d tokens to ~%d tokens", tag, original_tokens, max_tokens)
    return text[: max_chars - 20] + "\n... [truncated]"


def truncate_middle_if_needed(text: str, max_tokens: int, label: str = "") -> str:
    if max_tokens <= 0 or not text:
        return text
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    tag = f" ({label})" if label else ""
    original_tokens = estimate_tokens(text)
    logger.warning("Truncating middle of content%s from ~%d tokens to ~%d tokens", tag, original_tokens, max_tokens)
    half = max_chars // 2
    return text[:half] + "\n\n... [truncated] ...\n\n" + text[-half:]
