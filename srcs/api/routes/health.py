"""
File: health.py
Purpose: Health check endpoints.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: HealthResponse, RootResponse, health_check, root
Complexity: Low | Lines: 27
"""

from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class RootResponse(BaseModel):
    name: str
    version: str
    docs: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", version="0.1.0", timestamp=datetime.now())


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(name="artdaq Investigation Agent API", version="0.1.0", docs="/docs")
