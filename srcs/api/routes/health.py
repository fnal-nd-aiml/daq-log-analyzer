"""
File: health.py
Purpose: Health check endpoints.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: HealthResponse, ComponentStatus, ReadinessResponse, RootResponse, health_check, ...
Complexity: Medium | Lines: 81
"""

import asyncio
import logging
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from ..dependencies import Settings, get_pipeline_config, get_settings
logger = logging.getLogger(__name__)
router = APIRouter()
API_VERSION = version('artdaq-agent')
READINESS_CHECK_TIMEOUT_SECONDS = 5.0

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime

class ComponentStatus(BaseModel):
    name: str
    ready: bool
    detail: str | None = None

class ReadinessResponse(BaseModel):
    status: str = Field(description="'ready' or 'not_ready'")
    version: str
    timestamp: datetime
    checks: list[ComponentStatus]

class RootResponse(BaseModel):
    name: str
    version: str
    docs: str

@router.get('/health', response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status='healthy', version=API_VERSION, timestamp=datetime.now(timezone.utc))

@router.get('/ready', response_model=ReadinessResponse)
async def readiness_check(response: Response, settings: Annotated[Settings, Depends(get_settings)]) -> ReadinessResponse:
    checks = await asyncio.gather(_check_data_dir(settings), _check_pipeline_config())
    ready = all((check.ready for check in checks))
    if not ready:
        response.status_code = 503
        logger.warning('Readiness check failed: %s', ', '.join((f'{c.name}={c.detail}' for c in checks if not c.ready)))
    return ReadinessResponse(status='ready' if ready else 'not_ready', version=API_VERSION, timestamp=datetime.now(timezone.utc), checks=list(checks))

async def _check_data_dir(settings: Settings) -> ComponentStatus:

    def probe() -> ComponentStatus:
        data_dir = Path(settings.data_dir)
        if not data_dir.is_dir():
            return ComponentStatus(name='data_dir', ready=False, detail=f'{data_dir} does not exist')
        probe_file = data_dir / '.readiness'
        try:
            probe_file.touch()
            probe_file.unlink()
        except OSError as e:
            return ComponentStatus(name='data_dir', ready=False, detail=f'not writable: {e}')
        return ComponentStatus(name='data_dir', ready=True, detail=str(data_dir))
    return await _guarded(probe, 'data_dir')

async def _check_pipeline_config() -> ComponentStatus:

    def probe() -> ComponentStatus:
        config = get_pipeline_config()
        return ComponentStatus(name='pipeline_config', ready=True, detail=f'{len(config.phases)} phases')
    return await _guarded(probe, 'pipeline_config')

async def _guarded(probe: object, name: str) -> ComponentStatus:
    try:
        return await asyncio.wait_for(asyncio.to_thread(probe), timeout=READINESS_CHECK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return ComponentStatus(name=name, ready=False, detail=f'timed out after {READINESS_CHECK_TIMEOUT_SECONDS}s')
    except Exception as e:
        return ComponentStatus(name=name, ready=False, detail=f'{type(e).__name__}: {e}')

@router.get('/', response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(name='artdaq Investigation Agent API', version=API_VERSION, docs='/docs')