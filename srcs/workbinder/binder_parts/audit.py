"""
File: audit.py
Purpose: Audit logging: access recording and audit-log queries.
Category: Utility
Author: artdaq team
Depends: None
Exports: AuditMixin
Complexity: Low | Lines: 42
"""

from __future__ import annotations
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Generator
from ..artifacts import AuditLogEntry
from ._state import BinderState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class AuditMixin(BinderState):

    @contextmanager
    def audit_context(self, persona_name: str, phase: int | None=None) -> Generator[None, None, None]:
        old_persona = self._audit_persona
        old_phase = self._audit_phase
        self._audit_persona = persona_name
        self._audit_phase = phase
        try:
            yield
        finally:
            self._audit_persona = old_persona
            self._audit_phase = old_phase

    def _get_audit_context(self) -> tuple[str, int | None]:
        return (self._audit_persona or 'Unknown', self._audit_phase)

    def _log_access(self, persona_name: str, phase_number: int | None, operation_type: str, artifact_type: str, method_name: str, artifact_id: str | None=None, result_count: int=1, success: bool=True) -> None:
        self._access_sequence += 1
        entry = AuditLogEntry(persona_name=persona_name, phase_number=phase_number, timestamp=datetime.now(), access_sequence=self._access_sequence, operation_type=operation_type, artifact_type=artifact_type, artifact_id=artifact_id, method_name=method_name, result_count=result_count, success=success)
        self._audit_log.append(entry)

    def get_audit_log(self, persona_name: str | None=None, phase_number: int | None=None, operation_type: str | None=None) -> list[AuditLogEntry]:
        entries = self._audit_log
        if persona_name:
            entries = [e for e in entries if e.persona_name == persona_name]
        if phase_number is not None:
            entries = [e for e in entries if e.phase_number == phase_number]
        if operation_type:
            entries = [e for e in entries if e.operation_type == operation_type]
        return entries