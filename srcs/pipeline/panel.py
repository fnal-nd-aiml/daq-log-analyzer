"""
File: panel.py
Purpose: Panel executor for multi-persona phases.
Category: Utility
Author: artdaq team
Depends: None
Exports: AggregationStrategy, PanelExecutor
Complexity: Medium | Lines: 288
"""

import asyncio
import importlib
import logging
from enum import Enum
from typing import Any
from .config import AggregationConfig, CustomAggregatorConfig, PanelConfig, PerKeyAggregationConfig, WeightedVoteConfig
from .executor import ExecutorRegistry, PhaseExecutor
logger = logging.getLogger(__name__)

class AggregationStrategy(str, Enum):
    MERGE = 'merge'
    VOTE = 'vote'
    BEST_SCORE = 'best_score'
    CONSENSUS = 'consensus'

class PanelExecutor:

    def __init__(self, registry: ExecutorRegistry, default_timeout: int=60):
        self._registry = registry
        self._default_timeout = default_timeout

    async def execute(self, panel_config: PanelConfig, inputs: dict[str, Any], phase_config: dict[str, Any] | None=None) -> dict[str, Any]:
        phase_config = phase_config or {}
        timeout = panel_config.timeout or self._default_timeout
        executors = []
        for persona_id in panel_config.personas:
            executor = self._registry.get(persona_id)
            if executor is None:
                logger.warning(f"Panel persona '{persona_id}' not found in registry")
                continue
            executors.append((persona_id, executor))
        if not executors:
            logger.error('No valid executors found for panel')
            return {}
        if panel_config.execution == 'parallel':
            results = await self._execute_parallel(executors, inputs, phase_config, timeout)
        else:
            results = await self._execute_sequential(executors, inputs, phase_config)
        aggregation = panel_config.aggregation
        if isinstance(aggregation, str):
            strategy = AggregationStrategy(aggregation)
            return self._aggregate(results, strategy)
        elif isinstance(aggregation, AggregationConfig):
            return self._aggregate_advanced(results, aggregation)
        else:
            return self._aggregate_merge(results)

    async def _execute_parallel(self, executors: list[tuple[str, PhaseExecutor]], inputs: dict[str, Any], phase_config: dict[str, Any], timeout: int) -> list[tuple[str, dict[str, Any]]]:

        async def run_executor(persona_id: str, executor: PhaseExecutor) -> tuple[str, dict[str, Any]]:
            try:
                outputs = await executor.execute(inputs, phase_config)
                return (persona_id, outputs)
            except Exception as e:
                logger.warning(f"Panel executor '{persona_id}' failed: {e}")
                return (persona_id, {})
        tasks = [asyncio.create_task(run_executor(pid, ex)) for pid, ex in executors]
        try:
            done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            for task in pending:
                task.cancel()
            results = []
            for task in done:
                try:
                    results.append(task.result())
                except Exception as e:
                    logger.warning(f'Task result retrieval failed: {e}')
            return results
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise

    async def _execute_sequential(self, executors: list[tuple[str, PhaseExecutor]], inputs: dict[str, Any], phase_config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        results = []
        for persona_id, executor in executors:
            try:
                outputs = await executor.execute(inputs, phase_config)
                results.append((persona_id, outputs))
            except Exception as e:
                logger.warning(f"Panel executor '{persona_id}' failed: {e}")
                results.append((persona_id, {}))
        return results

    def _aggregate(self, results: list[tuple[str, dict[str, Any]]], strategy: AggregationStrategy) -> dict[str, Any]:
        if not results:
            return {}
        if strategy == AggregationStrategy.MERGE:
            return self._aggregate_merge(results)
        elif strategy == AggregationStrategy.VOTE:
            return self._aggregate_vote(results)
        elif strategy == AggregationStrategy.BEST_SCORE:
            return self._aggregate_best_score(results)
        elif strategy == AggregationStrategy.CONSENSUS:
            return self._aggregate_consensus(results)
        else:
            return self._aggregate_merge(results)

    def _aggregate_merge(self, results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for persona_id, outputs in results:
            for key, value in outputs.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, list) and isinstance(merged[key], list):
                    merged[key] = merged[key] + value
                elif isinstance(value, dict) and isinstance(merged[key], dict):
                    merged[key] = {**merged[key], **value}
                elif merged[key] is None:
                    merged[key] = value
        return merged

    def _aggregate_vote(self, results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        from collections import Counter
        all_keys: set[str] = set()
        for _, outputs in results:
            all_keys.update(outputs.keys())
        voted: dict[str, Any] = {}
        for key in all_keys:
            values = []
            for _, outputs in results:
                if key in outputs:
                    val = outputs[key]
                    if isinstance(val, (str, int, float, bool, type(None))):
                        values.append(val)
                    elif hasattr(val, 'value'):
                        values.append(val)
            if values:
                counter = Counter(values)
                most_common = counter.most_common(1)
                if most_common:
                    voted[key] = most_common[0][0]
        return voted

    def _aggregate_best_score(self, results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        best_score = -float('inf')
        best_outputs: dict[str, Any] = {}
        for persona_id, outputs in results:
            score = outputs.get('score', outputs.get('confidence', 0))
            if isinstance(score, (int, float)) and score > best_score:
                best_score = score
                best_outputs = outputs
        return best_outputs

    def _aggregate_consensus(self, results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        if not results:
            return {}
        _, first_outputs = results[0]
        consensus: dict[str, Any] = {}
        for key, value in first_outputs.items():
            if isinstance(value, list):
                common_items = set((self._to_hashable(item) for item in value))
                for _, outputs in results[1:]:
                    if key in outputs and isinstance(outputs[key], list):
                        other_set = set((self._to_hashable(item) for item in outputs[key]))
                        common_items &= other_set
                    else:
                        common_items = set()
                        break
                if common_items:
                    consensus[key] = [item for item in value if self._to_hashable(item) in common_items]
            else:
                all_match = True
                for _, outputs in results[1:]:
                    if key not in outputs or outputs[key] != value:
                        all_match = False
                        break
                if all_match:
                    consensus[key] = value
        return consensus

    def _to_hashable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted(value.items()))
        elif isinstance(value, list):
            return tuple(value)
        elif hasattr(value, 'id'):
            return value.id
        elif hasattr(value, '__hash__') and value.__hash__ is not None:
            return value
        else:
            return str(value)

    def _aggregate_advanced(self, results: list[tuple[str, dict[str, Any]]], config: AggregationConfig) -> dict[str, Any]:
        if config.strategy is not None:
            strategy = AggregationStrategy(config.strategy)
            return self._aggregate(results, strategy)
        elif config.weighted is not None:
            return self._aggregate_weighted(results, config.weighted)
        elif config.custom is not None:
            return self._aggregate_custom(results, config.custom)
        elif config.per_key is not None:
            return self._aggregate_per_key(results, config.per_key)
        else:
            return self._aggregate_merge(results)

    def _aggregate_weighted(self, results: list[tuple[str, dict[str, Any]]], config: WeightedVoteConfig) -> dict[str, Any]:
        if not results:
            return {}
        weights = dict(config.weights)
        if config.normalize:
            total = sum((weights.get(pid, 0.0) for pid, _ in results))
            if total > 0:
                weights = {pid: weights.get(pid, 0.0) / total for pid in weights}
        all_keys: set[str] = set()
        for _, outputs in results:
            all_keys.update(outputs.keys())
        aggregated: dict[str, Any] = {}
        for key in all_keys:
            values_with_weights: list[tuple[Any, float]] = []
            for persona_id, outputs in results:
                if key in outputs:
                    weight = weights.get(persona_id, 0.0)
                    values_with_weights.append((outputs[key], weight))
            if not values_with_weights:
                continue
            sample_value = values_with_weights[0][0]
            if isinstance(sample_value, (int, float)):
                total_weight = sum((w for _, w in values_with_weights))
                if total_weight > 0:
                    weighted_sum = sum((v * w for v, w in values_with_weights))
                    aggregated[key] = weighted_sum / total_weight
            elif isinstance(sample_value, (str, bool, type(None))):
                from collections import defaultdict
                vote_weights: defaultdict[Any, float] = defaultdict(float)
                for value, weight in values_with_weights:
                    vote_weights[value] += weight
                if vote_weights:
                    aggregated[key] = max(vote_weights.keys(), key=lambda k: vote_weights[k])
            elif isinstance(sample_value, list):
                sorted_values = sorted(values_with_weights, key=lambda x: -x[1])
                merged_list: list[Any] = []
                seen: set[Any] = set()
                for lst, _ in sorted_values:
                    for item in lst:
                        item_hash = self._to_hashable(item)
                        if item_hash not in seen:
                            seen.add(item_hash)
                            merged_list.append(item)
                aggregated[key] = merged_list
            elif isinstance(sample_value, dict):
                sorted_values = sorted(values_with_weights, key=lambda x: x[1])
                merged_dict: dict[str, Any] = {}
                for d, _ in sorted_values:
                    merged_dict.update(d)
                aggregated[key] = merged_dict
            else:
                best_value, _ = max(values_with_weights, key=lambda x: x[1])
                aggregated[key] = best_value
        return aggregated

    def _aggregate_custom(self, results: list[tuple[str, dict[str, Any]]], config: CustomAggregatorConfig) -> dict[str, Any]:
        try:
            module = importlib.import_module(config.module)
            func = getattr(module, config.function)
            result: dict[str, Any] = func(results, **config.config)
            return result
        except ImportError as e:
            logger.error(f'Failed to import custom aggregator module: {e}')
            return self._aggregate_merge(results)
        except AttributeError as e:
            logger.error(f'Custom aggregator function not found: {e}')
            return self._aggregate_merge(results)
        except Exception as e:
            logger.error(f'Custom aggregator failed: {e}')
            return self._aggregate_merge(results)

    def _aggregate_per_key(self, results: list[tuple[str, dict[str, Any]]], config: PerKeyAggregationConfig) -> dict[str, Any]:
        if not results:
            return {}
        all_keys: set[str] = set()
        for _, outputs in results:
            all_keys.update(outputs.keys())
        aggregated: dict[str, Any] = {}
        for key in all_keys:
            strategy_name = config.overrides.get(key, config.default)
            key_results = [(persona_id, {key: outputs[key]} if key in outputs else {}) for persona_id, outputs in results]
            key_results = [(pid, out) for pid, out in key_results if out]
            if not key_results:
                continue
            try:
                strategy = AggregationStrategy(strategy_name)
                key_aggregated = self._aggregate(key_results, strategy)
            except ValueError:
                key_aggregated = self._aggregate_merge(key_results)
            if key in key_aggregated:
                aggregated[key] = key_aggregated[key]
        return aggregated