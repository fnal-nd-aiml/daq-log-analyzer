"""
File: __init__.py
Purpose: REST API module for artdaq investigation agent.
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 2
"""

from .app import app, create_app
__all__ = ['create_app', 'app']