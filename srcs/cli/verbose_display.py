"""
File: verbose_display.py
Purpose: Verbose display with personas for investigation progress.
Category: Utility
Author: artdaq team
Depends: callbacks, phase_formatter, persona, rich
Exports: VerboseDisplay, create_verbose_callback
Complexity: Low | Lines: 27
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from srcs.models.callbacks import PhaseEvent
from srcs.output.phase_formatter import PhaseFormatter
from srcs.persona import PERSONAS

class VerboseDisplay:

    def __init__(self, console: Console | None=None):
        self.console = console or Console()
        self.formatter = PhaseFormatter()

    def on_phase_event(self, event: PhaseEvent) -> None:
        md_text = self.formatter.format_event(event)
        if not md_text:
            return
        persona = PERSONAS.get(event.phase)
        color = persona.color if persona else 'white'
        if event.event_type == 'start':
            self.console.print()
            self.console.print(Panel(Markdown(md_text), border_style=color, padding=(0, 1)))
        else:
            self.console.print(Markdown(md_text), style=color)

def create_verbose_callback(console: Console | None=None) -> 'VerboseDisplay':
    return VerboseDisplay(console)