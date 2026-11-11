"""
File: __init__.py
Purpose: Knowledge module - re-export public interface.
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 14
"""

from .base import DatabaseBackend, KnowledgeBase, PostgresConfig, StorageConfig
from .chroma_store import ChromaStore
from .doc_loader import DocStore, LLMDocExtractor, extract_names_from_message
from .errors import CalibrationError, InvestigationNotFoundError, KnowledgeError, PatternNotFoundError, StorageError
from .learning import LearningConfig, MetaLearner, PatternLearner
from .reporting import CalibrationHistoryTracker, CalibrationReport, CalibrationReporter, CalibrationTrend, export_calibration_json, export_trend_csv, format_calibration_report, format_trend_chart, generate_calibration_chart
from .sqlite_store import SQLiteStore
from .store_factory import create_structured_store, get_backend_info
from .store_interface import StructuredStore
try:
    from .postgres_store import PostgresStore
except ImportError:
    PostgresStore = None
__all__ = ['KnowledgeBase', 'StorageConfig', 'DatabaseBackend', 'PostgresConfig', 'StructuredStore', 'SQLiteStore', 'PostgresStore', 'ChromaStore', 'create_structured_store', 'get_backend_info', 'DocStore', 'LLMDocExtractor', 'extract_names_from_message', 'PatternLearner', 'LearningConfig', 'MetaLearner', 'CalibrationReporter', 'CalibrationReport', 'CalibrationHistoryTracker', 'CalibrationTrend', 'format_calibration_report', 'format_trend_chart', 'generate_calibration_chart', 'export_calibration_json', 'export_trend_csv', 'KnowledgeError', 'PatternNotFoundError', 'InvestigationNotFoundError', 'StorageError', 'CalibrationError']