"""
File: __init__.py
Purpose: Pipeline module - configurable dataflow system for investigation pi...
Category: Config
Author: artdaq team
Depends: None
Exports: None
Complexity: Medium | Lines: 62
"""

from .conditions import ConditionEvaluator, VariableInterpolator
from .config import (
    AggregationConfig,
    BranchConfig,
    CustomAggregatorConfig,
    ExecutorPluginConfig,
    FastPathAction,
    FastPathConfig,
    FilterConfig,
    HookConfig,
    PanelConfig,
    PerKeyAggregationConfig,
    PhaseConfig,
    PhaseOverrideConfig,
    PipelineConfig,
    VariantConfig,
    WeightedVoteConfig,
)
from .contracts import DataContractError, DataContracts
from .engine import PipelineEngine
from .executor import ExecutorRegistry, PhaseExecutor
from .hooks import HookRegistry
from .panel import AggregationStrategy, PanelExecutor
from .persona_executor import PersonaExecutor, UnifiedPersonaExecutor
from .plugins import ExecutorPluginLoader, PluginLoadError, PluginSecurityError
from .result_builders import ResultBuilderRegistry
from .router import DataRouter

__all__ = [
    "PhaseConfig",
    "PanelConfig",
    "FilterConfig",
    "BranchConfig",
    "FastPathConfig",
    "FastPathAction",
    "HookConfig",
    "VariantConfig",
    "PhaseOverrideConfig",
    "PipelineConfig",
    "ExecutorPluginConfig",
    "AggregationConfig",
    "WeightedVoteConfig",
    "CustomAggregatorConfig",
    "PerKeyAggregationConfig",
    "PipelineEngine",
    "PhaseExecutor",
    "ExecutorRegistry",
    "PanelExecutor",
    "PersonaExecutor",
    "UnifiedPersonaExecutor",
    "AggregationStrategy",
    "DataRouter",
    "ConditionEvaluator",
    "VariableInterpolator",
    "DataContracts",
    "DataContractError",
    "HookRegistry",
    "ResultBuilderRegistry",
    "ExecutorPluginLoader",
    "PluginLoadError",
    "PluginSecurityError",
]
