"""
File: callbacks.py
Purpose: Investigation callbacks for progress reporting.
Category: Data
Author: artdaq team
Depends: None
Exports: PhaseEvent, LLMEvent, DataRetrievalEvent
Complexity: Low | Lines: 43
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PhaseEvent:
    phase: int
    phase_name: str
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None


InvestigationCallback = Callable[[PhaseEvent], None]


@dataclass
class LLMEvent:
    phase: int
    event_type: str
    system_prompt: str | None
    user_prompt: str | None
    response: str | None
    response_model: str | None
    model_name: str
    parse_failed: bool = False
    parse_error: str | None = None
    expected_schema: str | None = None


@dataclass
class DataRetrievalEvent:
    phase: int
    event_type: str
    source: str
    operation: str
    query_params: dict[str, Any] = field(default_factory=dict)
    result_summary: str | None = None
    result_count: int | None = None


LLMCallback = Callable[[LLMEvent], None]
DataRetrievalCallback = Callable[[DataRetrievalEvent], None]
