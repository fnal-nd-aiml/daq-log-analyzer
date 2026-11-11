"""
File: binder.py
Purpose: Work Binder - Interactive Investigation Container.
Category: Utility
Author: artdaq team
Depends: base
Exports: WorkBinder
Complexity: Low | Lines: 33
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from srcs.models.base import generate_id
from .artifacts import Artifact, ArtifactHistory, AuditLogEntry
from .binder_parts.accessors import TypedAccessorsMixin
from .binder_parts.audit import AuditMixin
from .binder_parts.code_artifacts import CodeArtifactsMixin
from .binder_parts.crud import ArtifactCrudMixin
from .binder_parts.investigation_artifacts import InvestigationArtifactsMixin
from .binder_parts.llm_tracking import LlmTrackingMixin
from .binder_parts.phases import PhaseStateMixin
from .binder_parts.query import BinderQuery
from .binder_parts.serialization import SerializationMixin
__all__ = ['BinderQuery', 'WorkBinder']
logger = logging.getLogger(__name__)

@dataclass
class WorkBinder(AuditMixin, ArtifactCrudMixin, CodeArtifactsMixin, SerializationMixin, PhaseStateMixin, LlmTrackingMixin, InvestigationArtifactsMixin, TypedAccessorsMixin):
    id: str = field(default_factory=generate_id)
    investigation_id: str = ''
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: str = 'active'
    _artifacts: dict[str, Artifact] = field(default_factory=dict)
    _history: list[ArtifactHistory] = field(default_factory=list)
    _tags_index: dict[str, set[str]] = field(default_factory=dict)
    _function_index: dict[str, set[str]] = field(default_factory=dict)
    _audit_log: list[AuditLogEntry] = field(default_factory=list)
    _access_sequence: int = 0
    _audit_persona: str | None = None
    _audit_phase: int | None = None