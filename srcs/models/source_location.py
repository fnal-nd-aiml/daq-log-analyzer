"""
File: source_location.py
Purpose: Source location data models for error message tracing.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: SourceLocation, SourceLocationResult
Complexity: Low | Lines: 41
"""

from pydantic import BaseModel, Field
from .base import generate_id

class SourceLocation(BaseModel):
    id: str = Field(default_factory=generate_id)
    file_path: str
    line_number: int
    matched_line: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    function_name: str | None = None
    function_signature: str | None = None
    function_start_line: int | None = None
    function_end_line: int | None = None
    class_name: str | None = None
    callers: list[dict] | None = None
    callees: list[dict] | None = None
    function_summary: str | None = None
    function_body: str | None = None
    call_graph_diagram: str | None = None
    function_summaries: list[dict] = Field(default_factory=list)
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    search_pattern: str = ''
    is_log_statement: bool = False

class SourceLocationResult(BaseModel):
    original_message: str
    locations: list[SourceLocation] = Field(default_factory=list)
    patterns_tried: list[str] = Field(default_factory=list)
    files_searched: int = 0
    search_time_ms: float = 0.0

    @property
    def best_match(self) -> SourceLocation | None:
        if not self.locations:
            return None
        return max(self.locations, key=lambda loc: loc.match_score)

    @property
    def log_statement_matches(self) -> list[SourceLocation]:
        return [loc for loc in self.locations if loc.is_log_statement]