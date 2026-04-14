"""
File: filter.py
Purpose: Message filtering and duplicate throttling for MessageFacility mess...
Category: Utility
Author: artdaq team
Depends: None
Exports: MessageFilter, _PREFIX_RE
Complexity: Low | Lines: 87
"""

import logging
import re
from fnmatch import fnmatch
from .config import FieldFilter, ThrottleConfig
from .errors import ParseError
from .parser import parse

logger = logging.getLogger(__name__)
_PREFIX_RE = re.compile(b"^UDPMFMESSAGE\\d+\\|")


class MessageFilter:

    def __init__(self, filters: dict[str, FieldFilter], throttle: ThrottleConfig, write_raw: bool = True) -> None:
        self._filters = filters
        self._throttle = throttle
        self._write_raw = write_raw
        self._messages_filtered: int = 0
        self._messages_throttled: int = 0
        self._last_key: str | None = None
        self._repeat_count: int = 0
        self._suppressed_count: int = 0

    @property
    def messages_filtered(self) -> int:
        return self._messages_filtered

    @property
    def messages_throttled(self) -> int:
        return self._messages_throttled

    def process(self, data: bytes) -> list[bytes]:
        try:
            msg = parse(data)
        except ParseError:
            return [self._format(data)]
        for field_name, field_filter in self._filters.items():
            value = getattr(msg, field_name, None)
            if value is None:
                continue
            value_str = str(value)
            if field_filter.include is not None:
                if not any((fnmatch(value_str, pat) for pat in field_filter.include)):
                    self._messages_filtered += 1
                    return []
            if field_filter.exclude is not None:
                if any((fnmatch(value_str, pat) for pat in field_filter.exclude)):
                    self._messages_filtered += 1
                    return []
        if self._throttle.enabled:
            key = "|".join((str(getattr(msg, f, "")) for f in self._throttle.key_fields))
            return self._apply_throttle(key, data)
        return [self._format(data)]

    def flush_throttle(self) -> bytes | None:
        if self._throttle.enabled and self._throttle.summary and (self._suppressed_count > 0):
            summary = self._build_summary(self._suppressed_count)
            self._suppressed_count = 0
            return summary
        return None

    def _apply_throttle(self, key: str, data: bytes) -> list[bytes]:
        formatted = self._format(data)
        if key == self._last_key:
            self._repeat_count += 1
            if self._repeat_count >= self._throttle.max_repeat:
                self._suppressed_count += 1
                self._messages_throttled += 1
                return []
            return [formatted]
        result: list[bytes] = []
        if self._throttle.summary and self._suppressed_count > 0:
            result.append(self._build_summary(self._suppressed_count))
        self._last_key = key
        self._repeat_count = 1
        self._suppressed_count = 0
        result.append(formatted)
        return result

    def _build_summary(self, suppressed: int) -> bytes:
        return f"  ... repeated {suppressed} more times".encode("utf-8")

    def _format(self, data: bytes) -> bytes:
        if self._write_raw:
            return data
        cleaned = _PREFIX_RE.sub(b"", data)
        return cleaned
