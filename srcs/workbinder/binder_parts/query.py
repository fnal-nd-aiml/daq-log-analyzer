"""
File: query.py
Purpose: The BinderQuery filter object.
Category: Utility
Author: artdaq team
Depends: None
Exports: BinderQuery
Complexity: Low | Lines: 15
"""

from __future__ import annotations
from dataclasses import dataclass
from ..artifacts import ArtifactType, Priority

@dataclass
class BinderQuery:
    artifact_type: ArtifactType | None = None
    created_by: str | None = None
    tags: list[str] | None = None
    phase: int | None = None
    function_name: str | None = None
    priority: Priority | None = None
    include_deleted: bool = False
    limit: int = 100
    offset: int = 0