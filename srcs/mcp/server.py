"""
File: server.py
Purpose: MCP Server for Workbinder Artifacts, Access Logs, and Investigation...
Category: Utility
Author: artdaq team
Depends: None
Exports: create_mcp_server, run_mcp_server
Complexity: Low | Lines: 24
"""

from __future__ import annotations
import logging
from mcp.server.fastmcp import FastMCP
from .context import _enum_or_str, _get_agent_client, _get_api_url, _json_default, _qa_db_path, get_client_session_id, get_coordinator, get_db_path
from .tools import REGISTRARS
logger = logging.getLogger(__name__)
__all__ = ['_enum_or_str', '_get_agent_client', '_get_api_url', '_json_default', '_qa_db_path', 'create_mcp_server', 'get_client_session_id', 'get_coordinator', 'get_db_path', 'run_mcp_server']

def create_mcp_server(port: int=8001) -> FastMCP:
    mcp = FastMCP('artdaq-binder', port=port)
    for register in REGISTRARS:
        register(mcp)
    return mcp

def run_mcp_server(transport: str='stdio', port: int=8001) -> None:
    mcp = create_mcp_server(port=port)
    if transport == 'sse':
        mcp.run(transport='sse')
    elif transport == 'streamable-http':
        mcp.run(transport='streamable-http')
    else:
        mcp.run(transport='stdio')
if __name__ == '__main__':
    run_mcp_server()