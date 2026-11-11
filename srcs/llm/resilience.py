"""
File: resilience.py
Purpose: Timeout and retry handling for LLM provider calls.
Category: Utility
Author: artdaq team
Depends: None
Exports: is_transient, backoff_delay, call_with_resilience, T, _RETRYABLE_STATUS, ...
Complexity: Low | Lines: 53
"""

from __future__ import annotations
import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar
from .errors import ProviderError
logger = logging.getLogger(__name__)
T = TypeVar('T')
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
_RETRYABLE_EXC_NAMES = frozenset({'APIConnectionError', 'APITimeoutError', 'ConnectError', 'ConnectTimeout', 'InternalServerError', 'PoolTimeout', 'RateLimitError', 'ReadTimeout', 'RemoteProtocolError', 'ServiceUnavailableError', 'TimeoutException', 'WriteTimeout'})

def _status_code(exc: BaseException) -> int | None:
    for attr in ('status_code', 'status', 'code'):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None)
    return status if isinstance(status, int) else None

def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    status = _status_code(exc)
    if status is not None:
        return status in _RETRYABLE_STATUS
    return any((cls.__name__ in _RETRYABLE_EXC_NAMES for cls in type(exc).__mro__))

def backoff_delay(attempt: int, base: float, maximum: float) -> float:
    capped = min(maximum, base * 2 ** attempt)
    return random.uniform(0, capped)

async def call_with_resilience(operation: Callable[[], Awaitable[T]], *, timeout: float, max_retries: int, retry_base_delay: float, retry_max_delay: float, provider: str, description: str) -> T:
    attempts = max(1, max_retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            if timeout > 0:
                return await asyncio.wait_for(operation(), timeout=timeout)
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not is_transient(exc):
                raise
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            delay = backoff_delay(attempt, retry_base_delay, retry_max_delay)
            logger.warning('%s %s failed (attempt %d/%d): %s: %s — retrying in %.1fs', provider, description, attempt + 1, attempts, type(exc).__name__, exc, delay)
            await asyncio.sleep(delay)
    raise ProviderError(provider, f'{description} failed after {attempts} attempt(s): {type(last_exc).__name__}: {last_exc}') from last_exc