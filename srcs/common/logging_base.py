"""
File: logging_base.py
Purpose: Base class for logging wrappers.
Category: Utility
Author: artdaq team
Depends: None
Exports: LoggingWrapperBase, T
Complexity: Low | Lines: 16
"""

from typing import Any, Callable, TypeVar

T = TypeVar("T")


class LoggingWrapperBase:

    def __init__(self, callback: Callable[[Any], None]):
        self._callback = callback
        self._current_phase = 0

    def set_phase(self, phase: int) -> None:
        self._current_phase = phase

    def _emit_event(self, event: Any) -> None:
        self._callback(event)
