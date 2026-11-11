"""
File: questions.py
Purpose: Question answering endpoints.
Category: Utility
Author: artdaq team
Depends: logs, question, orchestrator, pydantic
Exports: QAStore, QuestionRequestBody, QuestionResponseBody, QuestionDetailResponse, FeedbackResponseBody, ...
Complexity: High | Lines: 183
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from srcs.models.logs import Log
from srcs.models.question import QAFeedbackRequest, QuestionType
from srcs.persona.orchestrator import PanelOrchestrator
from ..dependencies import Settings, get_settings
logger = logging.getLogger(__name__)
router = APIRouter()

class QAStore:
    SCHEMA = '''
    CREATE TABLE IF NOT EXISTS qa_sessions (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        question_type TEXT NOT NULL,
        answer TEXT NOT NULL,
        confidence REAL NOT NULL,
        key_points_json TEXT,
        caveats_json TEXT,
        sources_json TEXT,
        citations_json TEXT,
        contributions_summary_json TEXT,
        related_logs_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qa_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qa_session_id TEXT NOT NULL REFERENCES qa_sessions(id),
        helpful BOOLEAN NOT NULL,
        feedback_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_qa_sessions_created
        ON qa_sessions(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_qa_feedback_session
        ON qa_feedback(qa_session_id);
    '''

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.executescript(self.SCHEMA)
                await conn.commit()
            self._initialized = True

    async def store_session(self, session_id: str, question: str, question_type: str, answer: str, confidence: float, key_points: list[str], caveats: list[str], sources: list[str], citations: list[dict], contributions_summary: dict[str, str], related_logs: list[dict] | None=None) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute('''
                INSERT INTO qa_sessions (
                    id, question, question_type, answer, confidence,
                    key_points_json, caveats_json, sources_json,
                    citations_json, contributions_summary_json,
                    related_logs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, question, question_type, answer, confidence, json.dumps(key_points), json.dumps(caveats), json.dumps(sources), json.dumps(citations), json.dumps(contributions_summary), json.dumps(related_logs) if related_logs else None, datetime.now().isoformat()))
            await conn.commit()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM qa_sessions WHERE id = ?', (session_id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return {'question_id': row['id'], 'question': row['question'], 'question_type': row['question_type'], 'answer': row['answer'], 'confidence': row['confidence'], 'key_points': json.loads(row['key_points_json']) if row['key_points_json'] else [], 'caveats': json.loads(row['caveats_json']) if row['caveats_json'] else [], 'sources': json.loads(row['sources_json']) if row['sources_json'] else [], 'citations': json.loads(row['citations_json']) if row['citations_json'] else [], 'contributions_summary': json.loads(row['contributions_summary_json']) if row['contributions_summary_json'] else {}, 'related_logs': json.loads(row['related_logs_json']) if row['related_logs_json'] else None, 'created_at': row['created_at']}

    async def store_feedback(self, session_id: str, helpful: bool, feedback_text: str | None=None) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute('SELECT id FROM qa_sessions WHERE id = ?', (session_id,)) as cursor:
                if not await cursor.fetchone():
                    return False
            await conn.execute('''
                INSERT INTO qa_feedback (qa_session_id, helpful, feedback_text, created_at)
                VALUES (?, ?, ?, ?)
                ''', (session_id, helpful, feedback_text, datetime.now().isoformat()))
            await conn.commit()
            return True

    async def get_feedback(self, session_id: str) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM qa_feedback WHERE qa_session_id = ? ORDER BY created_at', (session_id,)) as cursor:
                rows = await cursor.fetchall()
        return [{'id': row['id'], 'helpful': bool(row['helpful']), 'feedback_text': row['feedback_text'], 'created_at': row['created_at']} for row in rows]

class QuestionRequestBody(BaseModel):
    question: str = Field(..., min_length=1, description='The question to ask')
    related_logs: list[dict] = Field(default_factory=list, description='Optional related log entries for context')

class QuestionResponseBody(BaseModel):
    question: str = Field(..., description='The original question')
    question_type: str = Field(..., description='Classified question type')
    question_id: str = Field(..., description='Unique ID for this Q&A session')
    answer: str = Field(..., description='The synthesized answer')
    confidence: float = Field(..., description='Confidence in the answer (0.0-1.0)')
    key_points: list[str] = Field(default_factory=list, description='Key points')
    caveats: list[str] = Field(default_factory=list, description='Important caveats')
    sources: list[str] = Field(default_factory=list, description='Sources consulted')
    citations: list[dict] = Field(default_factory=list, description='Source citations')
    contributions_summary: dict[str, str] = Field(default_factory=dict, description="Summary of each persona's contribution")

class QuestionDetailResponse(BaseModel):
    question_id: str
    question: str
    question_type: str
    answer: str
    confidence: float
    key_points: list[str]
    caveats: list[str]
    sources: list[str]
    citations: list[dict]
    contributions_summary: dict[str, str]
    related_logs: list[dict] | None
    created_at: str
    feedback: list[dict]

class FeedbackResponseBody(BaseModel):
    message: str = Field(..., description='Feedback confirmation message')
    qa_id: str = Field(..., description='Q&A session ID')

def get_orchestrator() -> PanelOrchestrator:
    return PanelOrchestrator()

def get_qa_store(settings: Annotated[Settings, Depends(get_settings)]) -> QAStore:
    data_dir = Path(settings.data_dir)
    return QAStore(data_dir / 'qa_sessions.db')

@router.get('/questions/types', response_model=list[dict])
async def list_question_types() -> list[dict]:
    return [{'type': QuestionType.HOW_TO.value, 'description': "How to do something (e.g., 'How do I configure X?')", 'example': 'How do I configure fragment timeouts?'}, {'type': QuestionType.WHY.value, 'description': "Why something happens (e.g., 'Why does X occur?')", 'example': 'Why might EventBuilder timeout?'}, {'type': QuestionType.WHAT_IS.value, 'description': "What something is (e.g., 'What is X?')", 'example': 'What is a BoardReader?'}, {'type': QuestionType.TROUBLESHOOT.value, 'description': "Troubleshooting an issue (e.g., 'I'm seeing error X')", 'example': "I'm seeing timeout errors in the BoardReader"}, {'type': QuestionType.COMPARE.value, 'description': "Comparing options (e.g., 'Difference between X and Y?')", 'example': "What's the difference between push and pull mode?"}, {'type': QuestionType.BEST_PRACTICE.value, 'description': "Best practices (e.g., 'What's the best way to do X?')", 'example': "What's the best way to handle data rates?"}]

@router.post('/questions', response_model=QuestionResponseBody)
async def ask_question(request: QuestionRequestBody, orchestrator: Annotated[PanelOrchestrator, Depends(get_orchestrator)], qa_store: Annotated[QAStore, Depends(get_qa_store)]) -> QuestionResponseBody:
    related_logs: list[Log] = []
    for log_dict in request.related_logs:
        try:
            related_logs.append(Log(timestamp=log_dict.get('timestamp', datetime.now()), level=log_dict.get('level', 'INFO'), component=log_dict.get('component', 'unknown'), function=log_dict.get('function'), message=log_dict.get('message', '')))
        except Exception as e:
            logger.warning(f'Failed to parse log entry: {e}')
    try:
        response = await orchestrator.answer(question=request.question, related_logs=related_logs if related_logs else None)
    except Exception as e:
        logger.error(f'Question answering failed: {e}')
        raise HTTPException(status_code=500, detail=f'Failed to answer question: {str(e)}')
    question_type = orchestrator._classify_question(request.question)
    try:
        await qa_store.store_session(session_id=response.question_id, question=request.question, question_type=question_type.value, answer=response.answer, confidence=response.confidence, key_points=response.key_points, caveats=response.caveats, sources=response.sources, citations=response.citations, contributions_summary=response.contributions_summary, related_logs=request.related_logs if request.related_logs else None)
    except Exception as e:
        logger.warning(f'Failed to store Q&A session: {e}')
    return QuestionResponseBody(question=request.question, question_type=question_type.value, question_id=response.question_id, answer=response.answer, confidence=response.confidence, key_points=response.key_points, caveats=response.caveats, sources=response.sources, citations=response.citations, contributions_summary=response.contributions_summary)

@router.get('/questions/{question_id}', response_model=QuestionDetailResponse)
async def get_question(question_id: str, qa_store: Annotated[QAStore, Depends(get_qa_store)]) -> QuestionDetailResponse:
    session = await qa_store.get_session(question_id)
    if not session:
        raise HTTPException(status_code=404, detail=f'Q&A session not found: {question_id}')
    feedback = await qa_store.get_feedback(question_id)
    return QuestionDetailResponse(question_id=session['question_id'], question=session['question'], question_type=session['question_type'], answer=session['answer'], confidence=session['confidence'], key_points=session['key_points'], caveats=session['caveats'], sources=session['sources'], citations=session['citations'], contributions_summary=session['contributions_summary'], related_logs=session['related_logs'], created_at=session['created_at'], feedback=feedback)

@router.post('/questions/{question_id}/feedback', response_model=FeedbackResponseBody)
async def submit_question_feedback(question_id: str, request: QAFeedbackRequest, qa_store: Annotated[QAStore, Depends(get_qa_store)]) -> FeedbackResponseBody:
    stored = await qa_store.store_feedback(session_id=question_id, helpful=request.helpful, feedback_text=request.feedback_text)
    if not stored:
        raise HTTPException(status_code=404, detail=f'Q&A session not found: {question_id}')
    logger.info(f'Feedback stored for Q&A {question_id}: helpful={request.helpful}, text={request.feedback_text}')
    return FeedbackResponseBody(message='Feedback recorded successfully', qa_id=question_id)