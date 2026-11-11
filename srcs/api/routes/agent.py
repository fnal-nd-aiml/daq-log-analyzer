"""
File: agent.py
Purpose: Agent session management endpoints.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: CreateSessionResponse, SessionStateResponse, DeleteSessionResponse, create_session, get_session, ...
Complexity: Low | Lines: 43
"""

from __future__ import annotations
import logging
from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..dependencies import get_session_store
from ..sessions import Session, SessionMetadata, SessionStore
logger = logging.getLogger(__name__)
router = APIRouter()

class CreateSessionResponse(BaseModel):
    session_id: str
    status: str

class SessionStateResponse(BaseModel):
    metadata: SessionMetadata
    findings_count: int
    hypotheses_count: int
    parsed_logs_count: int
    tool_invocation_count: int
    has_investigation_result: bool

class DeleteSessionResponse(BaseModel):
    session_id: str
    status: str

def _session_to_state_response(session: Session) -> SessionStateResponse:
    return SessionStateResponse(metadata=session.metadata, findings_count=len(session.state.findings), hypotheses_count=len(session.state.hypotheses), parsed_logs_count=len(session.state.parsed_logs), tool_invocation_count=session.metadata.tool_invocation_count, has_investigation_result=session.state.investigation_result is not None)

@router.post('/sessions', status_code=201, response_model=CreateSessionResponse)
async def create_session(store: Annotated[SessionStore, Depends(get_session_store)]) -> CreateSessionResponse:
    session = await store.create()
    return CreateSessionResponse(session_id=session.metadata.session_id, status=session.metadata.status)

@router.get('/sessions/{session_id}', response_model=SessionStateResponse)
async def get_session(session_id: str, store: Annotated[SessionStore, Depends(get_session_store)]) -> SessionStateResponse:
    session = await store.get_or_raise(session_id)
    return _session_to_state_response(session)

@router.delete('/sessions/{session_id}', response_model=DeleteSessionResponse)
async def delete_session(session_id: str, store: Annotated[SessionStore, Depends(get_session_store)]) -> DeleteSessionResponse:
    session = await store.close(session_id)
    return DeleteSessionResponse(session_id=session.metadata.session_id, status='closed')