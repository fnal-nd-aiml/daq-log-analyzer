"""
File: dependencies.py
Purpose: API dependencies and configuration.
Category: Utility
Author: artdaq team
Depends: agent, config, extraction, knowledge, llm, ...
Exports: Settings, get_settings, get_llm_config, get_storage_config, get_llm_provider, ...
Complexity: Medium | Lines: 168
"""

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
import yaml
from fastapi import Depends, Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from srcs.agent import InvestigationConfig, InvestigationCoordinator, QualityAnalyzer
from srcs.config import CONFIG_PATH_ENV_VAR, resolve_config_path
from srcs.knowledge import CalibrationReporter, KnowledgeBase, PatternLearner, StorageConfig
from srcs.llm import LLMConfig, LLMProvider, create_llm_provider
from srcs.pipeline import PipelineConfig
from srcs.source import SourceConfig
from srcs.workbinder import BinderStore
from .sessions import SessionStore
if TYPE_CHECKING:
    from srcs.extraction import CodeIndex
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    data_dir: str = Field(default='./data', description='Data directory path')
    source_repos_path: str = Field(default='./data/repos', description='Source repos path')
    llm_provider: str = Field(default='ollama', description='LLM provider')
    llm_model: str = Field(default='gpt-oss:120b', description='LLM model name')
    llm_max_tokens: int = Field(default=4096, ge=1, description='Default completion budget; personas give sub-calls fractions of it (e.g. //3, //10), and reasoning models spend part of it on reasoning')
    ollama_host: str = Field(default='http://localhost:11434', description='Ollama host URL')
    anthropic_api_key: str | None = Field(default=None, description='Anthropic API key')
    anthropic_base_url: str | None = Field(default=None, description='Custom Anthropic/vLLM endpoint')
    anthropic_auth_token: str | None = Field(default=None, description='vLLM auth token')
    anthropic_model: str | None = Field(default=None, description='Anthropic default model')
    anthropic_small_fast_model: str | None = Field(default=None, description='Fast model tier')
    anthropic_haiku_model: str | None = Field(default=None, description='Haiku equivalent model')
    anthropic_opus_model: str | None = Field(default=None, description='Opus equivalent model')
    openrouter_api_key: str | None = Field(default=None, description='OpenRouter API key')
    openrouter_base_url: str | None = Field(default=None, description='OpenAI-compatible endpoint (e.g. https://litellm.fnal.gov/v1)')
    openrouter_model: str | None = Field(default=None, description='OpenRouter default model')
    openrouter_reasoning_effort: str | None = Field(default=None, description='reasoning_effort for the openrouter provider (low/medium/high)')
    openrouter_small_fast_model: str | None = Field(default=None, description='Fast model tier')
    openrouter_haiku_model: str | None = Field(default=None, description='Haiku equivalent model')
    openrouter_opus_model: str | None = Field(default=None, description='Opus equivalent model')
    embedding_model: str = Field(default='nomic-embed-text', description='Embedding model name')
    embedding_host: str | None = Field(default=None, description='Embedding provider host')
    embedding_provider: str = Field(default='ollama', description="Embedding backend: 'ollama' or 'openai' (compatible)")
    embedding_api_key: str | None = Field(default=None, description="Key for an 'openai' embedding endpoint")
    max_hypotheses: int = Field(default=10, description='Maximum hypotheses')
    max_evidence_iterations: int = Field(default=10, description='Max evidence iterations')
    llm_timeout_seconds: float = Field(default=300.0, ge=0, description='Per-attempt LLM generation deadline')
    llm_embedding_timeout_seconds: float = Field(default=60.0, ge=0, description='Per-attempt embedding deadline')
    llm_max_retries: int = Field(default=2, ge=0, le=10, description='Retries after the first LLM attempt')
    max_concurrent_investigations: int = Field(default=4, ge=1, le=64, description='Concurrent investigation limit')
    investigation_timeout_seconds: float = Field(default=1800.0, ge=0, description='Wall-clock deadline for one investigation')
    api_key: str | None = Field(default=None, description='Shared secret required in the X-API-Key header')
    cors_origins: list[str] = Field(default=['http://localhost:3000', 'http://localhost:8000'], description='Allowed CORS origins')
    cors_allow_credentials: bool = Field(default=False, description='Allow credentials in CORS requests (only enable with specific origins)')
    model_config = SettingsConfigDict(env_prefix='ARTDAQ_', env_file='.env')

@lru_cache
def get_settings() -> Settings:
    return Settings()

def get_llm_config(settings: Annotated[Settings, Depends(get_settings)]) -> LLMConfig:
    from srcs.llm.provider import AnthropicModels, AnthropicProviderConfig, EmbeddingConfig, OllamaProviderConfig, OpenRouterModels, OpenRouterProviderConfig, ProvidersConfig
    anthropic_models = AnthropicModels(default=settings.anthropic_model or 'claude-3-5-sonnet-20241022', small_fast=settings.anthropic_small_fast_model, haiku=settings.anthropic_haiku_model, opus=settings.anthropic_opus_model)
    anthropic_config = AnthropicProviderConfig(base_url=settings.anthropic_base_url, auth_token=settings.anthropic_auth_token, api_key=settings.anthropic_api_key, models=anthropic_models)
    openrouter_models = OpenRouterModels(default=settings.openrouter_model or 'anthropic/claude-3.5-sonnet', small_fast=settings.openrouter_small_fast_model, haiku=settings.openrouter_haiku_model, opus=settings.openrouter_opus_model)
    openrouter_config = OpenRouterProviderConfig(api_key=settings.openrouter_api_key, models=openrouter_models, reasoning_effort=settings.openrouter_reasoning_effort)
    if settings.openrouter_base_url:
        openrouter_config.base_url = settings.openrouter_base_url
    ollama_config = OllamaProviderConfig(host=settings.ollama_host, model=settings.llm_model)
    embedding_config = EmbeddingConfig(provider=settings.embedding_provider, model=settings.embedding_model, host=settings.embedding_host or settings.ollama_host, api_key=settings.embedding_api_key)
    return LLMConfig(provider=settings.llm_provider, providers=ProvidersConfig(ollama=ollama_config, anthropic=anthropic_config, openrouter=openrouter_config), embedding=embedding_config, max_tokens=settings.llm_max_tokens, timeout_seconds=settings.llm_timeout_seconds, embedding_timeout_seconds=settings.llm_embedding_timeout_seconds, max_retries=settings.llm_max_retries, model=settings.llm_model, ollama_host=settings.ollama_host, anthropic_api_key=settings.anthropic_api_key)

def get_storage_config(settings: Annotated[Settings, Depends(get_settings)]) -> StorageConfig:
    data_dir = Path(settings.data_dir)
    return StorageConfig(sqlite_path=str(data_dir / 'knowledge.db'), chroma_path=str(data_dir / 'chroma'))

async def get_llm_provider(config: Annotated[LLMConfig, Depends(get_llm_config)]) -> LLMProvider:
    return create_llm_provider(config)
_knowledge_bases: dict[tuple[str, str], KnowledgeBase] = {}
_knowledge_base_lock = asyncio.Lock()

async def get_knowledge_base(storage_config: Annotated[StorageConfig, Depends(get_storage_config)], llm: Annotated[LLMProvider, Depends(get_llm_provider)]) -> KnowledgeBase:
    key = (storage_config.sqlite_path, storage_config.chroma_path)
    existing = _knowledge_bases.get(key)
    if existing is not None:
        return existing
    async with _knowledge_base_lock:
        existing = _knowledge_bases.get(key)
        if existing is not None:
            return existing
        kb = KnowledgeBase(storage_config, llm)
        await kb.initialize()
        _knowledge_bases[key] = kb
        return kb

async def close_cached_knowledge_bases() -> None:
    async with _knowledge_base_lock:
        for key, kb in list(_knowledge_bases.items()):
            try:
                await kb.close()
            except Exception:
                logger.exception('Error closing knowledge base %s', key[0])
        _knowledge_bases.clear()

def get_source_config(settings: Annotated[Settings, Depends(get_settings)]) -> SourceConfig | None:
    repos_path = Path(settings.source_repos_path)
    if repos_path.exists():
        return SourceConfig(repos_path=str(repos_path))
    return None

@lru_cache
def get_pipeline_config() -> PipelineConfig:
    config_path = resolve_config_path()
    if config_path is None:
        raise ValueError(f'Pipeline configuration required, but no config.yaml was found. Searched ${CONFIG_PATH_ENV_VAR}, the working directory ({Path.cwd()}), and the package directory.')
    try:
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f'Failed to load {config_path}: {e}') from e
    if 'pipeline' not in config_data:
        raise ValueError("Pipeline configuration required. Please add a 'pipeline' section to config.yaml. See docs/PIPELINE_CONFIGURATION.md for syntax.")
    return PipelineConfig(**config_data['pipeline'])

def get_code_index(settings: Annotated[Settings, Depends(get_settings)]) -> 'CodeIndex | None':
    from srcs.extraction import CodeIndex, CodeIndexConfig
    data_dir = Path(settings.data_dir)
    index_path = data_dir / 'code_index.db'
    if not index_path.exists():
        return None
    repos_path = Path(settings.source_repos_path)
    source_roots = [p for p in repos_path.iterdir() if p.is_dir()] if repos_path.exists() else []
    if not source_roots:
        return None
    config = CodeIndexConfig(source_roots=source_roots, index_path=index_path)
    return CodeIndex(config)

async def get_investigation_coordinator(kb: Annotated[KnowledgeBase, Depends(get_knowledge_base)], llm: Annotated[LLMProvider, Depends(get_llm_provider)], settings: Annotated[Settings, Depends(get_settings)], source_config: Annotated[SourceConfig | None, Depends(get_source_config)], code_index: Annotated['CodeIndex | None', Depends(get_code_index)]) -> InvestigationCoordinator:
    config = InvestigationConfig(max_hypotheses=settings.max_hypotheses, max_evidence_iterations=settings.max_evidence_iterations)
    coordinator = InvestigationCoordinator(kb, llm, config, source_config=source_config, code_index=code_index)
    pipeline_config = get_pipeline_config()
    coordinator.configure_pipeline(pipeline_config)
    return coordinator

async def get_pattern_learner(storage_config: Annotated[StorageConfig, Depends(get_storage_config)]) -> PatternLearner:
    return PatternLearner(storage_config.sqlite_path)

async def get_calibration_reporter(storage_config: Annotated[StorageConfig, Depends(get_storage_config)]) -> CalibrationReporter:
    return CalibrationReporter(storage_config.sqlite_path)

def get_quality_analyzer() -> QualityAnalyzer:
    return QualityAnalyzer()

def get_binder_store(settings: Annotated[Settings, Depends(get_settings)]) -> BinderStore:
    data_dir = Path(settings.data_dir)
    return BinderStore(data_dir / 'knowledge.db')
_fallback_session_store: SessionStore | None = None

def get_session_store(request: Request) -> SessionStore:
    store: SessionStore | None = getattr(request.app.state, 'session_store', None)
    if store is not None:
        return store
    global _fallback_session_store
    if _fallback_session_store is None:
        _fallback_session_store = SessionStore()
    return _fallback_session_store