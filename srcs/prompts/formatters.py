"""
File: formatters.py
Purpose: Safe formatting utilities for prompt templates.
Category: Utility
Author: artdaq team
Depends: None
Exports: safe_format
Complexity: Low | Lines: 27
"""

import logging
from .errors import MissingPlaceholderError
from .types import PromptMetadata, SystemPromptType, UserPromptType

logger = logging.getLogger(__name__)


def safe_format(
    content: str, prompt_type: UserPromptType | SystemPromptType, metadata: PromptMetadata, **kwargs: str
) -> str:
    provided = frozenset(kwargs.keys())
    missing = metadata.required_placeholders - provided
    if missing:
        raise MissingPlaceholderError(prompt_type.value, missing)
    known = metadata.all_placeholders
    unexpected = provided - known
    if unexpected:
        unexpected_str = ", ".join(sorted(unexpected))
        logger.warning("Unexpected placeholder(s) for %s: %s", prompt_type.value, unexpected_str)
    result = content
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, str(value))
    return result


__all__ = ["safe_format"]
