"""
File: sessions.py
Purpose: In-memory session management for the agentic API.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: ParsedLogSummary, SessionFinding, SessionHypothesis, ToolInvocation, SessionState, ...
Complexity: Medium | Lines: 151
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from typing import Any
from pydantic import BaseModel, Field, PrivateAttr
from .errors import session_closed, session_not_found
logger = logging.getLogger(__name__)
SESSION_TTL_SECONDS = 24 * 60 * 60
MAX_PARSED_LOGS_PER_SESSION = 5000
MAX_FINDINGS_PER_SESSION = 500
MAX_TOOL_HISTORY_PER_SESSION = 1000
MAX_SESSIONS = 1000

class ParsedLogSummary(BaseModel):
    total_entries: int = 0
    error_count: int = 0
    warning_count: int = 0
    components: list[str] = Field(default_factory=list)
    time_range_start: str | None = None
    time_range_end: str | None = None

class SessionFinding(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    category: str
    description: str
    severity: str = 'medium'
    evidence: list[str] = Field(default_factory=list)
    source_tool: str | None = None

class SessionHypothesis(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str
    confidence: float = 0.5
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    status: str = 'active'

class ToolInvocation(BaseModel):
    tool_name: str
    timestamp: float = Field(default_factory=time.time)
    duration_ms: float | None = None
    success: bool = True
    error: str | None = None
    summary: str | None = None

class SessionState(BaseModel):
    parsed_logs: list[dict[str, Any]] = Field(default_factory=list)
    log_summary: ParsedLogSummary | None = None
    findings: list[SessionFinding] = Field(default_factory=list)
    hypotheses: list[SessionHypothesis] = Field(default_factory=list)
    investigation_result: dict[str, Any] | None = None
    tool_history: list[ToolInvocation] = Field(default_factory=list)
    _search_cache: dict[str, Any] = PrivateAttr(default_factory=dict)

class SessionMetadata(BaseModel):
    session_id: str
    created_at: float
    last_accessed_at: float
    status: str = 'active'
    tool_invocation_count: int = 0

class Session(BaseModel):
    metadata: SessionMetadata
    state: SessionState = Field(default_factory=SessionState)

    def touch(self) -> None:
        self.metadata.last_accessed_at = time.time()

    def record_tool_invocation(self, invocation: ToolInvocation) -> None:
        if len(self.state.tool_history) >= MAX_TOOL_HISTORY_PER_SESSION:
            self.state.tool_history = self.state.tool_history[-MAX_TOOL_HISTORY_PER_SESSION // 2:]
        self.state.tool_history.append(invocation)
        self.metadata.tool_invocation_count += 1
        self.touch()

    def add_finding(self, finding: SessionFinding) -> None:
        if len(self.state.findings) < MAX_FINDINGS_PER_SESSION:
            self.state.findings.append(finding)

    @property
    def is_closed(self) -> bool:
        return self.metadata.status == 'closed'

    @property
    def is_expired(self) -> bool:
        return time.time() - self.metadata.last_accessed_at > SESSION_TTL_SECONDS

class SessionStore:

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> Session:
        session_id = uuid.uuid4().hex[:16]
        now = time.time()
        session = Session(metadata=SessionMetadata(session_id=session_id, created_at=now, last_accessed_at=now))
        async with self._lock:
            self._reap_expired()
            self._enforce_capacity()
            self._sessions[session_id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            self._reap_expired()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    async def get_or_raise(self, session_id: str) -> Session:
        session = await self.get(session_id)
        if session is None:
            raise session_not_found(session_id)
        if session.is_closed:
            raise session_closed(session_id)
        return session

    async def close(self, session_id: str) -> Session:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise session_not_found(session_id)
            session.metadata.status = 'closed'
            return session

    async def list_sessions(self) -> list[SessionMetadata]:
        async with self._lock:
            self._reap_expired()
            return [s.metadata for s in self._sessions.values() if not s.is_closed]

    def _reap_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]
            logger.debug('Reaped expired session %s', sid)

    def _enforce_capacity(self) -> None:
        if len(self._sessions) < MAX_SESSIONS:
            return
        closed = [sid for sid, s in self._sessions.items() if s.is_closed]
        for sid in closed:
            del self._sessions[sid]
            logger.info('Evicted closed session %s to make room', sid)
        while len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions.items(), key=lambda item: item[1].metadata.last_accessed_at)[0]
            del self._sessions[oldest]
            logger.warning('Session store at capacity (%d); evicted least-recently-used session %s', MAX_SESSIONS, oldest)