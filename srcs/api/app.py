"""
File: app.py
Purpose: FastAPI application for artdaq investigation agent.
Category: Utility
Author: artdaq team
Depends: errors, admin_tools, code_tools, finding_tools, knowledge_tools, ...
Exports: RequestSizeLimitMiddleware, lifespan, create_app, MAX_REQUEST_BODY_BYTES
Complexity: Medium | Lines: 140
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
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
from srcs.source.errors import SourceError
from .dependencies import get_settings
from .errors import AgentAPIError, agent_error_response
from .routes import admin, agent, binders, calibration, health, investigations, metrics, patterns, questions
from .sessions import SessionStore
from .tools.router import router as tool_router

logger = logging.getLogger(__name__)
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": f"Request body exceeds maximum size of {MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MB",
                    }
                },
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.session_store = SessionStore()
    yield
    logger.info("Shutting down: cleaning up resources")
    if hasattr(app.state, "session_store"):
        del app.state.session_store


def create_app() -> FastAPI:
    app = FastAPI(
        title="artdaq Investigation Agent API",
        description="REST API for LLM-powered root cause analysis of artdaq DAQ software errors. Provides endpoints for running investigations, managing patterns, and tracking calibration.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestSizeLimitMiddleware)
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
    )
    app.include_router(health.router, tags=["Health"])
    app.include_router(investigations.router, prefix="/api/v1", tags=["Investigations"])
    app.include_router(patterns.router, prefix="/api/v1", tags=["Patterns"])
    app.include_router(calibration.router, prefix="/api/v1", tags=["Calibration"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["Metrics"])
    app.include_router(questions.router, prefix="/api/v1", tags=["Questions"])
    app.include_router(binders.router, prefix="/api/v1", tags=["Binders"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
    app.include_router(tool_router, prefix="/api/v1/agent", tags=["Agent Tools"])
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(AgentAPIError)
    async def agent_api_error_handler(request: Request, exc: AgentAPIError) -> JSONResponse:
        return agent_error_response(exc)

    @app.exception_handler(PatternNotFoundError)
    async def pattern_not_found_handler(request: Request, exc: PatternNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": {"code": "PATTERN_NOT_FOUND", "message": str(exc)}})

    @app.exception_handler(InvestigationNotFoundError)
    async def investigation_not_found_handler(request: Request, exc: InvestigationNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"error": {"code": "INVESTIGATION_NOT_FOUND", "message": str(exc)}}
        )

    @app.exception_handler(KnowledgeError)
    async def knowledge_error_handler(request: Request, exc: KnowledgeError) -> JSONResponse:
        logger.error("Knowledge error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500, content={"error": {"code": "KNOWLEDGE_ERROR", "message": "Knowledge operation failed"}}
        )

    @app.exception_handler(AgentError)
    async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
        logger.error("Agent error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500, content={"error": {"code": "AGENT_ERROR", "message": "Investigation agent error"}}
        )

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
        logger.error("LLM error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=503, content={"error": {"code": "LLM_ERROR", "message": "LLM service unavailable"}}
        )

    @app.exception_handler(ExtractionError)
    async def extraction_error_handler(request: Request, exc: ExtractionError) -> JSONResponse:
        logger.error("Extraction error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500, content={"error": {"code": "EXTRACTION_ERROR", "message": "Code extraction error"}}
        )

    @app.exception_handler(SourceError)
    async def source_error_handler(request: Request, exc: SourceError) -> JSONResponse:
        logger.error("Source error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500, content={"error": {"code": "SOURCE_ERROR", "message": "Source repository error"}}
        )


app = create_app()
