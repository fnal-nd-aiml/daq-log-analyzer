"""
File: base.py
Purpose: Shared imports and utilities for investigation tools.
Category: Utility
Author: artdaq team
Depends: extraction, source_locator, summarizer, knowledge, models, ...
Exports: validate_path, strength_from_log_level, strength_from_confidence, make_evidence, make_log_evidence
Complexity: Medium | Lines: 36
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from srcs.extraction import CodeExtractor, CodeIndex, CodeIndexConfig, CodeParser
from srcs.extraction.source_locator import SourceLocator
from srcs.extraction.summarizer import FunctionSummarizer
from srcs.knowledge import KnowledgeBase
from srcs.models import EvidenceItem, Log
from srcs.source import RepositoryManager, SourceConfig
logger = logging.getLogger(__name__)

def validate_path(path: Path, allowed_roots: list[Path]) -> Path:
    resolved = path.resolve()
    for root in allowed_roots:
        if resolved.is_relative_to(root.resolve()):
            return resolved
    raise ValueError(f'Path {path} is outside allowed source roots')

def strength_from_log_level(level: str) -> str:
    if level in ('ERROR', 'WARNING'):
        return 'MODERATE'
    return 'WEAK'

def strength_from_confidence(score: float) -> str:
    if score > 0.7:
        return 'STRONG'
    if score > 0.4:
        return 'MODERATE'
    return 'WEAK'

def make_evidence(evidence_type: str, content: str, source: str, strength: str='WEAK') -> EvidenceItem:
    return EvidenceItem(evidence_type=evidence_type, content=content, source=source, strength=strength)

def make_log_evidence(log: Log, source: str) -> EvidenceItem:
    return make_evidence(evidence_type='log', content=f'[{log.timestamp}] {log.level} {log.component}: {log.message}', source=source, strength=strength_from_log_level(log.level))
__all__ = ['CodeExtractor', 'CodeIndex', 'CodeIndexConfig', 'CodeParser', 'EvidenceItem', 'KnowledgeBase', 'Log', 'Path', 'RepositoryManager', 'SourceConfig', 'SourceLocator', 'FunctionSummarizer', 'logger', 'make_evidence', 'make_log_evidence', 'strength_from_confidence', 'strength_from_log_level', 'validate_path', 'TYPE_CHECKING']