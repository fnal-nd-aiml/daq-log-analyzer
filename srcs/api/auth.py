"""
File: auth.py
Purpose: API key authentication.
Category: Utility
Author: artdaq team
Depends: None
Exports: missing_api_key, invalid_api_key, require_api_key, log_auth_status
Complexity: Low | Lines: 33
"""

from __future__ import annotations
import logging
import secrets
from typing import Annotated
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from .constants import API_KEY_HEADER as API_KEY_HEADER_NAME
from .dependencies import Settings, get_settings
from .errors import AgentAPIError
logger = logging.getLogger(__name__)
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

def missing_api_key() -> AgentAPIError:
    return AgentAPIError(code='UNAUTHENTICATED', message=f'Missing {API_KEY_HEADER_NAME} header.', status_code=401, recovery_hint=f'Send the API key in the {API_KEY_HEADER_NAME} header.')

def invalid_api_key() -> AgentAPIError:
    return AgentAPIError(code='UNAUTHENTICATED', message='Invalid API key.', status_code=401, recovery_hint=f'Check the value of the {API_KEY_HEADER_NAME} header.')

def require_api_key(settings: Annotated[Settings, Depends(get_settings)], presented: Annotated[str | None, Security(_api_key_header)]=None) -> None:
    expected = settings.api_key
    if not expected:
        return
    if not presented:
        raise missing_api_key()
    if not secrets.compare_digest(presented, expected):
        logger.warning('Rejected request with invalid API key')
        raise invalid_api_key()

def log_auth_status(settings: Settings) -> None:
    if settings.api_key:
        logger.info('API key authentication enabled (%s header)', API_KEY_HEADER_NAME)
    else:
        logger.warning('API key authentication is DISABLED - every /api/v1 endpoint is open, including admin operations. Set ARTDAQ_API_KEY to enable it.')