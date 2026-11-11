"""
File: router.py
Purpose: Data router for pipeline input/output management.
Category: Utility
Author: artdaq team
Depends: None
Exports: DataRouter
Complexity: Medium | Lines: 86
"""

import logging
from typing import Any
from .conditions import ConditionEvaluator
from .config import FilterConfig, PhaseConfig, PipelineConfig
from .contracts import DataContracts
logger = logging.getLogger(__name__)

class DataRouter:

    def __init__(self, config: PipelineConfig, validate_contracts: bool=True):
        self._config = config
        self._validate_contracts = validate_contracts
        self._evaluator = ConditionEvaluator()
    GLOBAL_CONTEXT_KEYS = ['investigation', 'kb', 'llm', 'code_index', 'source_locator', 'config', 'binder']

    def get_inputs(self, phase: PhaseConfig, context: dict[str, Any]) -> dict[str, Any]:
        inputs = {}
        for key in phase.inputs:
            if key in context:
                value = context[key]
                if phase.filter and key in phase.filter:
                    value = self._apply_filter(value, phase.filter[key])
                inputs[key] = value
            else:
                logger.debug(f"Phase '{phase.id}' input '{key}' not in context")
                inputs[key] = None
        for key in self.GLOBAL_CONTEXT_KEYS:
            if key in context and key not in inputs:
                inputs[key] = context[key]
        return inputs

    def merge_outputs(self, phase: PhaseConfig, context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        new_context = dict(context)
        for key in phase.outputs:
            if key in outputs:
                value = outputs[key]
                if self._validate_contracts:
                    try:
                        DataContracts.validate(key, value)
                    except Exception as e:
                        logger.warning(f"Contract validation failed for '{key}': {e}")
                new_context[key] = value
            else:
                logger.debug(f"Phase '{phase.id}' declared output '{key}' not in outputs")
        return new_context

    def _apply_filter(self, value: Any, filter_config: FilterConfig) -> Any:
        if not isinstance(value, list):
            return value
        result = list(value)
        if filter_config.condition:
            result = self._filter_by_condition(result, filter_config.condition)
        if filter_config.limit is not None and filter_config.limit > 0:
            result = result[:filter_config.limit]
        return result

    def _filter_by_condition(self, items: list, condition: str) -> list:
        result = []
        for item in items:
            item_context = {'item': item}
            if hasattr(item, '__dict__'):
                for attr, val in vars(item).items():
                    if not attr.startswith('_'):
                        item_context[attr] = val
            elif hasattr(item, 'model_dump'):
                item_context.update(item.model_dump())
            try:
                if self._evaluator.evaluate(condition, item_context):
                    result.append(item)
            except Exception as e:
                logger.debug(f"Filter condition '{condition}' failed for item: {e}")
                result.append(item)
        return result

    def validate_phase_inputs(self, phase: PhaseConfig, context: dict[str, Any]) -> list[str]:
        missing = []
        for key in phase.inputs:
            if key not in context or context[key] is None:
                missing.append(key)
        return missing

    def create_initial_context(self, trigger_error: Any, context_logs: list) -> dict[str, Any]:
        context = {'trigger_error': trigger_error, 'context_logs': context_logs}
        if self._validate_contracts:
            DataContracts.validate_context(context)
        return context