"""
File: observability.py
Purpose: Logging configuration and request correlation.
Category: Utility
Author: artdaq team
Depends: None
Exports: RequestIdFilter, JsonFormatter, LoggingWrapperBase, resolve_log_level, configure_logging, ...
Complexity: Medium | Lines: 73
"""

from __future__ import annotations
import logging
import os
import sys
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any
request_id_var: ContextVar[str] = ContextVar('request_id', default='')
_DEFAULT_FORMAT = '%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s'
_PLAIN_FORMAT = '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
_NOISY_LOGGERS = {'httpcore': logging.WARNING, 'httpx': logging.WARNING, 'chromadb': logging.WARNING, 'urllib3': logging.WARNING, 'asyncio': logging.WARNING}

class RequestIdFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or '-'
        return True

class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        import json
        payload: dict[str, Any] = {'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'), 'level': record.levelname, 'logger': record.name, 'message': record.getMessage(), 'request_id': getattr(record, 'request_id', '-')}
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)

def resolve_log_level(level: str | int | None=None, default: str='INFO') -> int:
    if isinstance(level, int):
        return level
    candidate = level or os.environ.get('ARTDAQ_LOG_LEVEL') or default
    resolved = logging.getLevelName(str(candidate).upper())
    return resolved if isinstance(resolved, int) else logging.INFO

def configure_logging(level: str | int | None=None, *, json_format: bool | None=None, force: bool=True) -> None:
    resolved_level = resolve_log_level(level)
    if json_format is None:
        json_format = os.environ.get('ARTDAQ_LOG_JSON', '').lower() in {'1', 'true', 'yes', 'on'}
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if json_format else logging.Formatter(_DEFAULT_FORMAT))
    root = logging.getLogger()
    if force:
        for existing in list(root.handlers):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved_level)
    for name, noisy_level in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(max(noisy_level, resolved_level))

def configure_plain_logging(level: str | int | None=None) -> None:
    resolved_level = resolve_log_level(level, default='WARNING')
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved_level)
    for name, noisy_level in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(max(noisy_level, resolved_level))

class LoggingWrapperBase:

    def __init__(self, callback: Callable[[Any], None]):
        self._callback = callback
        self._current_phase = 0

    def set_phase(self, phase: int) -> None:
        self._current_phase = phase

    def _emit_event(self, event: Any) -> None:
        self._callback(event)