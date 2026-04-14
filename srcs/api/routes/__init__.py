"""
File: __init__.py
Purpose: API routes.
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 3
"""

from . import admin, agent, calibration, health, investigations, metrics, patterns

__all__ = ["admin", "agent", "calibration", "health", "investigations", "metrics", "patterns"]
