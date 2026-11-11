"""
File: middleware.py
Purpose: HTTP middleware: request correlation, access logging, and body size...
Category: Utility
Author: artdaq team
Depends: observability
Exports: RequestContextMiddleware, RequestSizeLimitMiddleware, MAX_REQUEST_BODY_BYTES, _QUIET_PATHS
Complexity: Medium | Lines: 76
"""

from __future__ import annotations
import logging
import time
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from srcs.observability import request_id_var
from .constants import REQUEST_ID_HEADER
logger = logging.getLogger(__name__)
__all__ = ['REQUEST_ID_HEADER', 'RequestContextMiddleware', 'RequestSizeLimitMiddleware']
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
_QUIET_PATHS = frozenset({'/health', '/ready', '/'})

class RequestContextMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, '').strip()
        request_id = incoming[:64] if incoming else uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - started) * 1000
            logger.exception('%s %s failed after %.1fms', request.method, request.url.path, duration_ms)
            raise
        finally:
            request_id_var.reset(token)
        duration_ms = (time.monotonic() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path not in _QUIET_PATHS:
            log = logger.warning if response.status_code >= 500 else logger.info
            log('%s %s -> %d in %.1fms', request.method, request.url.path, response.status_code, duration_ms)
        return response

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                return _too_large_response('Malformed Content-Length header', status_code=400)
            if declared > MAX_REQUEST_BODY_BYTES:
                return _too_large_response(f'Request body exceeds maximum size of {MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MB')
        elif _has_body(request):
            return await _call_with_metered_body(request, call_next)
        return await call_next(request)

def _has_body(request: Request) -> bool:
    if request.method in {'GET', 'HEAD', 'DELETE', 'OPTIONS'}:
        return False
    return 'chunked' in request.headers.get('transfer-encoding', '').lower()

async def _call_with_metered_body(request: Request, call_next: RequestResponseEndpoint) -> Response:
    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_REQUEST_BODY_BYTES:
            return _too_large_response(f'Request body exceeds maximum size of {MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MB')
        chunks.append(chunk)
    body = b''.join(chunks)

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': body, 'more_body': False}
    request._receive = receive
    return await call_next(request)

def _too_large_response(message: str, status_code: int=413) -> JSONResponse:
    code = 'REQUEST_TOO_LARGE' if status_code == 413 else 'INVALID_REQUEST'
    return JSONResponse(status_code=status_code, content={'error': {'code': code, 'message': message}})