"""
File: context.py
Purpose: Shared context for the MCP tool modules.
Category: Utility
Author: artdaq team
Depends: agent, client, config
Exports: get_db_path, get_client_session_id, get_coordinator
Complexity: Low | Lines: 62
"""

from __future__ import annotations
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from srcs.agent import InvestigationCoordinator
    from srcs.api.client import AgentClient
logger = logging.getLogger(__name__)
_client: 'AgentClient | None' = None
_client_session_id: str | None = None

def _enum_or_str(value: Any) -> str:
    return str(getattr(value, 'value', value))

def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(mode='json')
    if hasattr(obj, 'value'):
        return obj.value
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')

def get_db_path() -> Path:
    data_dir = os.environ.get('ARTDAQ_DATA_DIR', './data')
    return Path(data_dir) / 'knowledge.db'

def _qa_db_path() -> Path:
    data_dir = os.environ.get('ARTDAQ_DATA_DIR', './data')
    return Path(data_dir) / 'qa_sessions.db'

def _get_api_url() -> str | None:
    return os.environ.get('ARTDAQ_API_URL')

async def _get_agent_client() -> 'AgentClient | None':
    global _client, _client_session_id
    api_url = _get_api_url()
    if not api_url:
        return None
    if _client is None:
        from srcs.api.client import AgentClient
        _client = AgentClient(api_url)
        await _client.__aenter__()
        session = await _client.create_session()
        _client_session_id = session['session_id']
        logger.info('Initialized AgentClient for MCP server at %s', api_url)
    return _client

def get_client_session_id() -> str | None:
    return _client_session_id
_coordinator: 'InvestigationCoordinator | None' = None

async def get_coordinator() -> 'InvestigationCoordinator':
    global _coordinator
    if _coordinator is None:
        from srcs.config import CoordinatorFactory, load_config
        config = load_config()
        _coordinator = CoordinatorFactory.create(config)
        logger.info('Initialized investigation coordinator for MCP server')
    return _coordinator