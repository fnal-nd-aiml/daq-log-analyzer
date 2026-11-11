"""
File: __init__.py
Purpose: MCP tool modules, grouped by domain.
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 5
"""

from collections.abc import Callable
from mcp.server.fastmcp import FastMCP
from . import admin, analytics, audit, binder, calibration, investigation, llm, patterns, qa
REGISTRARS: list[Callable[[FastMCP], None]] = [binder.register, audit.register, patterns.register, calibration.register, investigation.register, llm.register, qa.register, admin.register, analytics.register]
__all__ = ['REGISTRARS']