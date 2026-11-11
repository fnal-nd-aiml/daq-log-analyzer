"""
File: __init__.py
Purpose: Output module - unified markdown formatting for CLI and Slack.
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 4
"""

from .markdown_formatter import MarkdownFormatter
from .phase_formatter import PhaseFormatter
from .renderer import ConsoleRenderer, SlackRenderer
__all__ = ['MarkdownFormatter', 'PhaseFormatter', 'ConsoleRenderer', 'SlackRenderer']