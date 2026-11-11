"""
File: app.py
Purpose: FastAPI application for artdaq investigation agent.
Category: Utility
Author: artdaq team
Depends: errors, admin_tools, code_tools, finding_tools, knowledge_tools, ...
Exports: lifespan, create_app, API_VERSION
Complexity: Medium | Lines: 103
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import AsyncGenerator
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import srcs.api.tools.admin_tools
import srcs.api.tools.code_tools
import srcs.api.tools.finding_tools
import srcs.api.tools.knowledge_tools
import srcs.api.tools.log_tools
import srcs.api.tools.pipeline_tools
from srcs.agent.errors import AgentError
from srcs.extraction.errors import ExtractionError
from srcs.knowledge.errors import InvestigationNotFoundError, KnowledgeError, PatternNotFoundError
from srcs.llm.errors import LLMError
from srcs.observability import configure_logging
from srcs.source.errors import SourceError
from .auth import log_auth_status, require_api_key
from .dependencies import close_cached_knowledge_bases, get_pipeline_config, get_settings
from .errors import AgentAPIError, agent_error_response
from .middleware import REQUEST_ID_HEADER, RequestContextMiddleware, RequestSizeLimitMiddleware
from .routes import admin, agent, binders, calibration, health, investigations, metrics, patterns, questions
from .sessions import SessionStore
from .tools.router import router as tool_router
logger = logging.getLogger(__name__)
API_VERSION = version('artdaq-agent')

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    settings = get_settings()
    app.state.settings = settings
    app.state.session_store = SessionStore()
    app.state.investigation_semaphore = asyncio.Semaphore(settings.max_concurrent_investigations)
    try:
        get_pipeline_config()
    except ValueError as e:
        logger.error('Pipeline configuration unavailable: %s', e)
    log_auth_status(settings)
    logger.info('artdaq Investigation Agent API %s started (provider=%s, data_dir=%s, max_concurrent_investigations=%d)', API_VERSION, settings.llm_provider, settings.data_dir, settings.max_concurrent_investigations)
    yield
    logger.info('Shutting down: cleaning up resources')
    await close_cached_knowledge_bases()
    if hasattr(app.state, 'session_store'):
        del app.state.session_store

def create_app() -> FastAPI:
    app = FastAPI(title='artdaq Investigation Agent API', description='REST API for LLM-powered root cause analysis of artdaq DAQ software errors. Provides endpoints for running investigations, managing patterns, and tracking calibration.', version=API_VERSION, lifespan=lifespan)
    app.add_middleware(RequestSizeLimitMiddleware)
    settings = get_settings()
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=settings.cors_allow_credentials, allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization', 'Accept', REQUEST_ID_HEADER], expose_headers=[REQUEST_ID_HEADER])
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router, tags=['Health'])
    protected = [Depends(require_api_key)]
    app.include_router(investigations.router, prefix='/api/v1', tags=['Investigations'], dependencies=protected)
    app.include_router(patterns.router, prefix='/api/v1', tags=['Patterns'], dependencies=protected)
    app.include_router(calibration.router, prefix='/api/v1', tags=['Calibration'], dependencies=protected)
    app.include_router(metrics.router, prefix='/api/v1', tags=['Metrics'], dependencies=protected)
    app.include_router(questions.router, prefix='/api/v1', tags=['Questions'], dependencies=protected)
    app.include_router(binders.router, prefix='/api/v1', tags=['Binders'], dependencies=protected)
    app.include_router(admin.router, prefix='/api/v1/admin', tags=['Admin'], dependencies=protected)
    app.include_router(agent.router, prefix='/api/v1/agent', tags=['Agent'], dependencies=protected)
    app.include_router(tool_router, prefix='/api/v1/agent', tags=['Agent Tools'], dependencies=protected)
    _register_exception_handlers(app)
    return app

def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', '')
    body: dict[str, object] = {'error': {'code': code, 'message': message}}
    if request_id:
        body['request_id'] = request_id
    response = JSONResponse(status_code=status_code, content=body)
    if request_id:
        response.headers[REQUEST_ID_HEADER] = request_id
    return response
_INTERNAL_ERRORS: tuple[tuple[type[Exception], int, str, str], ...] = ((KnowledgeError, 500, 'KNOWLEDGE_ERROR', 'Knowledge operation failed'), (AgentError, 500, 'AGENT_ERROR', 'Investigation agent error'), (LLMError, 503, 'LLM_ERROR', 'LLM service unavailable'), (ExtractionError, 500, 'EXTRACTION_ERROR', 'Code extraction error'), (SourceError, 500, 'SOURCE_ERROR', 'Source repository error'))

def _register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(AgentAPIError)
    async def agent_api_error_handler(request: Request, exc: AgentAPIError) -> JSONResponse:
        return agent_error_response(exc)

    @app.exception_handler(PatternNotFoundError)
    async def pattern_not_found_handler(request: Request, exc: PatternNotFoundError) -> JSONResponse:
        return _error_response(request, 404, 'PATTERN_NOT_FOUND', str(exc))

    @app.exception_handler(InvestigationNotFoundError)
    async def investigation_not_found_handler(request: Request, exc: InvestigationNotFoundError) -> JSONResponse:
        return _error_response(request, 404, 'INVESTIGATION_NOT_FOUND', str(exc))

    def register_internal(exc_type: type[Exception], status: int, code: str, message: str) -> None:

        async def handler(request: Request, exc: Exception) -> JSONResponse:
            logger.error('%s on %s %s: %s', code, request.method, request.url.path, exc, exc_info=exc)
            return _error_response(request, status, code, message)
        app.add_exception_handler(exc_type, handler)
    for exc_type, status, code, message in _INTERNAL_ERRORS:
        register_internal(exc_type, status, code, message)
app = create_app()