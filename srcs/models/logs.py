"""
File: logs.py
Purpose: Log-related data models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: Log, ErrorSignature, LogContext, SourceFile
Complexity: Medium | Lines: 60
"""

from datetime import datetime
from pydantic import BaseModel, Field


class Log(BaseModel):
    timestamp: datetime
    level: str
    component: str
    function: str | None = None
    file: str | None = None
    line: int | None = None
    message: str
    raw_line: str | None = None


class ErrorSignature(BaseModel):
    function: str | None = None
    message_pattern: str
    level: str = "ERROR"
    component: str | None = None

    def matches(self, other: "ErrorSignature") -> bool:
        if self.level != other.level:
            return False
        if not self._message_matches(self.message_pattern, other.message_pattern):
            return False
        if self.function and other.function:
            if self.function != other.function:
                return False
        if self.component and other.component:
            if self.component != other.component:
                return False
        return True

    def _message_matches(self, pattern1: str, pattern2: str) -> bool:
        import re

        def to_regex(pattern: str) -> str:
            escaped = re.escape(pattern)
            escaped = escaped.replace("\\{N\\}", "\\d+")
            escaped = escaped.replace("\\{HEX\\}", "0x[0-9a-fA-F]+")
            return f"^{escaped}$"

        regex1 = to_regex(pattern1)
        try:
            return bool(re.match(regex1, pattern2)) or pattern1 == pattern2
        except re.error:
            return pattern1 == pattern2


class LogContext(BaseModel):
    trigger_error: Log
    context_logs: list[Log] = Field(default_factory=list)
    time_window_seconds: float = 60.0


class SourceFile(BaseModel):
    filename: str
    content: str
    error_line: int | None = None
