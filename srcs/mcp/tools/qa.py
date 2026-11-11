"""
File: qa.py
Purpose: Expert-panel question answering.
Category: Utility
Author: artdaq team
Depends: log_parser, logs, question, orchestrator
Exports: register
Complexity: Medium | Lines: 109
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from mcp.server.fastmcp import Context, FastMCP
from ..context import _get_agent_client, _json_default, _qa_db_path, get_client_session_id
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def ask_experts(question: str, log_content: str | None=None, ctx: Context | None=None) -> str:
        import asyncio
        from srcs.models.logs import Log
        from srcs.persona.orchestrator import PanelOrchestrator, QAEvent

        async def _safe_progress(coro: Any) -> None:
            try:
                await coro
            except Exception:
                pass

        def on_event(event: QAEvent) -> None:
            if not ctx:
                return
            event_type = event.get('event', '')
            try:
                loop = asyncio.get_running_loop()
                if event_type == 'classification':
                    loop.create_task(_safe_progress(ctx.info(f"Question type: {event.get('question_type', 'unknown')}")))
                elif event_type == 'panel_selected':
                    personas = event.get('personas', [])
                    loop.create_task(_safe_progress(ctx.info(f"Panel assembled: {', '.join(personas)}")))
                    loop.create_task(_safe_progress(ctx.report_progress(progress=1, total=5)))
                elif event_type == 'contribution_start':
                    loop.create_task(_safe_progress(ctx.info(f"{event.get('persona', '')} is thinking...")))
                elif event_type == 'contribution_complete':
                    loop.create_task(_safe_progress(ctx.report_progress(progress=2, total=5)))
                elif event_type == 'voting_complete':
                    loop.create_task(_safe_progress(ctx.report_progress(progress=3, total=5)))
                elif event_type == 'deliberation_complete':
                    loop.create_task(_safe_progress(ctx.report_progress(progress=4, total=5)))
                elif event_type == 'synthesis_complete':
                    loop.create_task(_safe_progress(ctx.report_progress(progress=5, total=5)))
            except RuntimeError:
                pass
        try:
            agent = await _get_agent_client()
            session_id = get_client_session_id()
            if agent is not None and session_id is not None:
                result_data = await agent.ask_experts(session_id, question)
                return json.dumps(result_data, default=_json_default, indent=2)
            related_logs: list[Log] = []
            if log_content:
                from srcs.models.log_parser import parse_log_content
                related_logs = parse_log_content(log_content)
            orchestrator = PanelOrchestrator()
            response = await orchestrator.answer(question=question, related_logs=related_logs if related_logs else None, callback=on_event)
            result = {'question_id': response.question_id, 'answer': response.answer, 'confidence': response.confidence, 'key_points': response.key_points, 'caveats': response.caveats, 'contributions_summary': response.contributions_summary, 'dissenting_views': response.dissenting_views, 'sources': response.sources, 'citations': response.citations}
            return json.dumps(result, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Ask experts failed')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def list_question_types() -> str:
        from srcs.models.question import QuestionType
        return json.dumps([{'type': QuestionType.HOW_TO.value, 'description': 'How to do something', 'example': 'How do I configure fragment timeouts?'}, {'type': QuestionType.WHY.value, 'description': 'Why something happens', 'example': 'Why might EventBuilder timeout?'}, {'type': QuestionType.WHAT_IS.value, 'description': 'What something is', 'example': 'What is a BoardReader?'}, {'type': QuestionType.TROUBLESHOOT.value, 'description': 'Troubleshooting an issue', 'example': "I'm seeing timeout errors in the BoardReader"}, {'type': QuestionType.COMPARE.value, 'description': 'Comparing options', 'example': "What's the difference between push and pull mode?"}, {'type': QuestionType.BEST_PRACTICE.value, 'description': 'Best practices', 'example': "What's the best way to handle data rates?"}], indent=2)

    @mcp.tool()
    async def get_question(question_id: str) -> str:
        import aiosqlite
        try:
            db_path = _qa_db_path()
            async with aiosqlite.connect(db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('SELECT * FROM qa_sessions WHERE id = ?', (question_id,)) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return json.dumps({'error': f'Q&A session not found: {question_id}'})
            async with aiosqlite.connect(db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('SELECT * FROM qa_feedback WHERE qa_session_id = ? ORDER BY created_at', (question_id,)) as cursor:
                    fb_rows = await cursor.fetchall()
            feedback = [{'id': fb['id'], 'helpful': bool(fb['helpful']), 'feedback_text': fb['feedback_text'], 'created_at': fb['created_at']} for fb in fb_rows]
            result = {'question_id': row['id'], 'question': row['question'], 'question_type': row['question_type'], 'answer': row['answer'], 'confidence': row['confidence'], 'key_points': json.loads(row['key_points_json']) if row['key_points_json'] else [], 'caveats': json.loads(row['caveats_json']) if row['caveats_json'] else [], 'sources': json.loads(row['sources_json']) if row['sources_json'] else [], 'citations': json.loads(row['citations_json']) if row['citations_json'] else [], 'contributions_summary': json.loads(row['contributions_summary_json']) if row['contributions_summary_json'] else {}, 'related_logs': json.loads(row['related_logs_json']) if row['related_logs_json'] else None, 'created_at': row['created_at'], 'feedback': feedback}
            return json.dumps(result, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get question')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def submit_question_feedback(question_id: str, helpful: bool, feedback_text: str | None=None) -> str:
        import aiosqlite
        try:
            db_path = _qa_db_path()
            async with aiosqlite.connect(db_path) as conn:
                async with conn.execute('SELECT id FROM qa_sessions WHERE id = ?', (question_id,)) as cursor:
                    if not await cursor.fetchone():
                        return json.dumps({'error': f'Q&A session not found: {question_id}'})
                await conn.execute('INSERT INTO qa_feedback (qa_session_id, helpful, feedback_text, created_at) VALUES (?, ?, ?, ?)', (question_id, helpful, feedback_text, datetime.now().isoformat()))
                await conn.commit()
            return json.dumps({'message': 'Feedback recorded successfully', 'qa_id': question_id}, indent=2)
        except Exception as e:
            logger.exception('Failed to submit question feedback')
            return json.dumps({'error': str(e)}, indent=2)