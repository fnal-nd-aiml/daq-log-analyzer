"""
File: engine.py
Purpose: Pipeline engine orchestrator.
Category: Utility
Author: artdaq team
Depends: callbacks, extraction, knowledge, llm, models, ...
Exports: PipelineEngine
Complexity: High | Lines: 494
"""

import logging
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any
from srcs.models import Investigation, InvestigationOutcome, InvestigationResult, Log
from .conditions import ConditionEvaluator, VariableInterpolator
from .config import FastPathAction, PhaseConfig, PipelineConfig
from .executor import ExecutorRegistry
from .hooks import HookRegistry
from .panel import PanelExecutor
from .result_builders import ResultBuilderRegistry
from .router import DataRouter

if TYPE_CHECKING:
    from srcs.agent.callbacks import InvestigationCallback
    from srcs.extraction import CodeIndex, SourceLocator
    from srcs.knowledge import KnowledgeBase
    from srcs.llm import LLMProvider, RecordingLLMProvider
logger = logging.getLogger(__name__)


class PipelineEngine:

    def __init__(
        self,
        config: PipelineConfig,
        executor_registry: ExecutorRegistry,
        validate_contracts: bool = True,
        kb: "KnowledgeBase | None" = None,
        investigation_config: Any = None,
        plugin_allowed_prefixes: list[str] | None = None,
        recording_llm: "RecordingLLMProvider | None" = None,
        llm: "LLMProvider | None" = None,
        code_index: "CodeIndex | None" = None,
        source_locator: "SourceLocator | None" = None,
        snapshot_callback: Any = None,
    ):
        self._config = config
        self._base_config = deepcopy(config)
        self._registry = executor_registry
        self._router = DataRouter(config, validate_contracts)
        self._evaluator = ConditionEvaluator()
        self._interpolator = VariableInterpolator(investigation_config)
        self._panel_executor = PanelExecutor(executor_registry)
        self._hook_registry = HookRegistry()
        self._result_builder_registry = ResultBuilderRegistry(kb)
        self._kb = kb
        self._active_variant: str | None = None
        self._recording_llm = recording_llm
        self._llm = llm
        self._code_index = code_index
        self._source_locator = source_locator
        self._investigation_config = investigation_config
        self._snapshot_callback = snapshot_callback
        if config.executors:
            from .plugins import load_plugin_executors

            plugin_executors = load_plugin_executors(config.executors, plugin_allowed_prefixes)
            for executor in plugin_executors.values():
                self._registry.register(executor)

    def _resolve_phase_number(self, phase: PhaseConfig, phase_idx: int) -> int:
        if phase.executor is not None:
            executor = self._registry.get(phase.executor)
            if executor is not None and hasattr(executor, "_phase"):
                return executor._phase
        return phase_idx

    async def execute(
        self,
        trigger_error: Log,
        context_logs: list[Log],
        callback: "InvestigationCallback | None" = None,
        investigation: Investigation | None = None,
        source_files: list[Any] | None = None,
    ) -> InvestigationResult:
        if investigation is None:
            investigation = Investigation(
                trigger_error=trigger_error, context_logs=context_logs, started_at=datetime.now()
            )
        from srcs.workbinder import WorkBinder

        if investigation.binder is None:
            investigation.binder = WorkBinder(investigation_id=investigation.id)
            investigation.binder.add_error_context(trigger_error, context_logs, "Pipeline")
        if self._recording_llm is not None:
            self._recording_llm.set_binder(investigation.binder)
        binder_store = None
        if self._kb is not None and hasattr(self._kb, "config"):
            try:
                from srcs.workbinder import BinderStore

                binder_store = BinderStore(self._kb.config.sqlite_path)
            except Exception as e:
                logger.warning(f"Failed to create binder store: {e}")
        context: dict[str, Any] = {
            "trigger_error": trigger_error,
            "context_logs": context_logs,
            "investigation": investigation,
            "kb": self._kb,
            "llm": self._llm,
            "code_index": self._code_index,
            "source_locator": self._source_locator,
            "config": self._investigation_config,
            "binder": investigation.binder,
            "binder_store": binder_store,
            "source_files": source_files,
        }
        logger.info(f"Starting pipeline execution for investigation {investigation.id}")
        try:
            if self._config.start_at:
                current_phase_idx = self._config.get_phase_index(self._config.start_at)
                if current_phase_idx is None:
                    current_phase_idx = 0
            else:
                current_phase_idx = 0
            self._active_variant = None
            self._config = deepcopy(self._base_config)
            while current_phase_idx < len(self._config.phases):
                phase = self._config.phases[current_phase_idx]
                if phase.id in self._config.skip_phases:
                    logger.debug(f"Phase '{phase.id}' in skip_phases, skipping")
                    current_phase_idx += 1
                    continue
                if not self._is_phase_enabled(phase, context):
                    logger.debug(f"Phase '{phase.id}' is disabled, skipping")
                    current_phase_idx += 1
                    continue
                if not self._check_requires(phase, context):
                    logger.debug(f"Phase '{phase.id}' requires condition not met, skipping")
                    current_phase_idx += 1
                    continue
                await self._execute_hooks("before", phase.id, context, investigation)
                phase_num = self._resolve_phase_number(phase, current_phase_idx)
                if hasattr(self._llm, "set_phase"):
                    self._llm.set_phase(phase_num)
                if hasattr(self._kb, "set_phase"):
                    self._kb.set_phase(phase_num)
                if hasattr(self._recording_llm, "set_phase"):
                    self._recording_llm.set_phase(phase_num)
                self._emit_phase_start(callback, phase, phase_num, investigation.id)
                outputs: dict[str, Any] = {}
                pre_context = dict(context) if self._snapshot_callback else None
                try:
                    outputs = await self._execute_phase(phase, context)
                    context = self._router.merge_outputs(phase, context, outputs)
                    if self._snapshot_callback is not None:
                        self._snapshot_callback(phase.id, phase_num, pre_context, context, outputs)
                    self._update_investigation(investigation, phase, outputs)
                except Exception as e:
                    logger.warning(f"Phase '{phase.id}' failed: {e}")
                    self._emit_phase_error(callback, phase, phase_num, e)
                self._emit_item_events(callback, phase, phase_num, outputs)
                self._emit_phase_complete(callback, phase, phase_num, outputs)
                await self._execute_hooks("after", phase.id, context, investigation)
                fast_path_result = await self._check_fast_paths(phase, context, current_phase_idx, investigation)
                if fast_path_result is not None:
                    if isinstance(fast_path_result, InvestigationResult):
                        await self._execute_completion_hooks(context, investigation)
                        return fast_path_result
                    elif isinstance(fast_path_result, int):
                        current_phase_idx = fast_path_result
                        continue
                next_phase_idx = self._check_branches(phase, context, current_phase_idx)
                if next_phase_idx is not None:
                    current_phase_idx = next_phase_idx
                else:
                    current_phase_idx += 1
            investigation.completed_at = datetime.now()
            await self._execute_completion_hooks(context, investigation)
            if "result" in context and isinstance(context["result"], InvestigationResult):
                return context["result"]
            else:
                return self._create_fallback_result(investigation, context)
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            investigation.completed_at = datetime.now()
            investigation.outcome = InvestigationOutcome.INSUFFICIENT
            await self._execute_error_hooks(context, investigation)
            return InvestigationResult(
                investigation_id=investigation.id,
                outcome=InvestigationOutcome.INSUFFICIENT,
                insufficient_reason=f"Pipeline execution failed: {str(e)}",
                missing_evidence=["Pipeline encountered an error"],
                duration_seconds=(investigation.completed_at - investigation.started_at).total_seconds(),
            )

    async def _execute_phase(self, phase: PhaseConfig, context: dict[str, Any]) -> dict[str, Any]:
        inputs = self._router.get_inputs(phase, context)
        interpolated_config = self._interpolator.interpolate(phase.config, context)
        logger.debug(f"Executing phase '{phase.id}' with inputs: {list(inputs.keys())}")
        if phase.panel is not None:
            outputs = await self._panel_executor.execute(phase.panel, inputs, interpolated_config)
        else:
            if phase.executor is None:
                raise ValueError(f"Phase '{phase.id}' has no executor")
            executor = self._registry.get(phase.executor)
            if executor is None:
                raise ValueError(f"Executor '{phase.executor}' not found for phase '{phase.id}'")
            outputs = await executor.execute(inputs, interpolated_config)
        logger.debug(f"Phase '{phase.id}' produced outputs: {list(outputs.keys())}")
        return outputs

    def _is_phase_enabled(self, phase: PhaseConfig, context: dict[str, Any]) -> bool:
        enabled = phase.enabled
        if isinstance(enabled, bool):
            return enabled
        if isinstance(enabled, str):
            enabled = self._interpolator.interpolate(enabled, context)
            if isinstance(enabled, bool):
                return enabled
            if enabled.startswith("${") and enabled.endswith("}"):
                enabled = enabled[2:-1]
            return self._evaluator.evaluate(enabled, context)
        return True

    def _check_requires(self, phase: PhaseConfig, context: dict[str, Any]) -> bool:
        if phase.requires is None:
            return True
        return self._evaluator.evaluate(phase.requires, context)

    def _check_branches(self, phase: PhaseConfig, context: dict[str, Any], current_idx: int) -> int | None:
        for branch in self._config.branches:
            if branch.after != phase.id:
                continue
            if self._evaluator.evaluate(branch.condition, context):
                target_idx = self._config.get_phase_index(branch.skip_to)
                if target_idx is not None:
                    logger.info(f"Branch condition met after '{phase.id}', skipping to '{branch.skip_to}'")
                    return target_idx
        return None

    async def _check_fast_paths(
        self, phase: PhaseConfig, context: dict[str, Any], current_idx: int, investigation: Investigation
    ) -> int | InvestigationResult | None:
        for fast_path in self._config.fast_paths:
            if fast_path.after is not None and fast_path.after != phase.id:
                continue
            if not self._evaluator.evaluate(fast_path.condition, context):
                continue
            logger.info(f"Fast path '{fast_path.name}' triggered")
            if fast_path.action == FastPathAction.SKIP_TO:
                if fast_path.skip_to:
                    target_idx = self._config.get_phase_index(fast_path.skip_to)
                    if target_idx is not None and target_idx > current_idx:
                        logger.info(f"Skipping to '{fast_path.skip_to}'")
                        return target_idx
            elif fast_path.action == FastPathAction.EARLY_RETURN:
                if not fast_path.result_builder:
                    continue
                result = await self._result_builder_registry.build(fast_path.result_builder, context, investigation)
                if result is not None:
                    logger.info(f"Early return via builder '{fast_path.result_builder}'")
                    return result
            elif fast_path.action == FastPathAction.USE_VARIANT:
                self._apply_variant(fast_path.variant)
                logger.info(f"Applied variant '{fast_path.variant}'")
                return None
        return None

    def _apply_variant(self, variant_name: str | None) -> None:
        if variant_name is None:
            return
        variant = self._config.variants.get(variant_name)
        if variant is None:
            logger.warning(f"Variant '{variant_name}' not found")
            return
        self._active_variant = variant_name
        for phase_id, override in variant.phase_overrides.items():
            phase = self._config.get_phase(phase_id)
            if phase is None:
                continue
            if override.config is not None:
                phase.config = {**phase.config, **override.config}
            if override.enabled is not None:
                phase.enabled = override.enabled
        logger.debug(f"Applied variant '{variant_name}'")

    async def _execute_hooks(
        self, trigger: str, phase_id: str, context: dict[str, Any], investigation: Investigation
    ) -> None:
        for hook in self._config.hooks:
            if trigger == "before" and hook.before == phase_id:
                await self._hook_registry.execute(hook.action, context, investigation)
            elif trigger == "after" and hook.after == phase_id:
                await self._hook_registry.execute(hook.action, context, investigation)

    async def _execute_completion_hooks(self, context: dict[str, Any], investigation: Investigation) -> None:
        for hook in self._config.hooks:
            if hook.on_complete:
                await self._hook_registry.execute(hook.action, context, investigation)

    async def _execute_error_hooks(self, context: dict[str, Any], investigation: Investigation) -> None:
        for hook in self._config.hooks:
            if hook.on_error:
                await self._hook_registry.execute(hook.action, context, investigation)

    def _update_investigation(self, investigation: Investigation, phase: PhaseConfig, outputs: dict[str, Any]) -> None:
        if "hypotheses" in outputs:
            new_hyps = outputs["hypotheses"]
            if investigation.hypotheses and new_hyps:
                existing = {h.id: h for h in investigation.hypotheses}
                for nh in new_hyps:
                    if nh.id in existing:
                        eh = existing[nh.id]
                        eh.score = nh.score
                        eh.status = nh.status
                        eh.supporting_evidence_ids = nh.supporting_evidence_ids
                        eh.contradicting_evidence_ids = nh.contradicting_evidence_ids
                    else:
                        investigation.hypotheses.append(nh)
            else:
                investigation.hypotheses = new_hyps
        if "evidence" in outputs:
            investigation.evidence = outputs["evidence"]
        if "causal_chains" in outputs:
            investigation.causal_chains = outputs["causal_chains"]
        if "challenges" in outputs:
            investigation.challenges = outputs["challenges"]
        if "outcome" in outputs:
            investigation.outcome = outputs["outcome"]
        if "prior_knowledge" in outputs:
            prior = outputs["prior_knowledge"]
            if prior.matched_patterns:
                investigation.matched_pattern_id = prior.matched_patterns[0].pattern.id
            investigation.similar_investigation_ids = [s.investigation_id for s in prior.similar_investigations]
        if "trigger_error" in outputs and outputs["trigger_error"] is not None:
            investigation.trigger_error = outputs["trigger_error"]
        if "context_logs" in outputs and outputs["context_logs"]:
            investigation.context_logs = outputs["context_logs"]

    def _create_fallback_result(self, investigation: Investigation, context: dict[str, Any]) -> InvestigationResult:
        outcome = context.get("outcome", InvestigationOutcome.INSUFFICIENT)
        return InvestigationResult(
            investigation_id=investigation.id,
            outcome=outcome,
            insufficient_reason="Pipeline completed without synthesis phase",
            duration_seconds=(
                (investigation.completed_at - investigation.started_at).total_seconds()
                if investigation.completed_at
                else 0.0
            ),
        )

    def _emit_phase_start(
        self,
        callback: "InvestigationCallback | None",
        phase: PhaseConfig,
        phase_idx: int,
        investigation_id: str | None = None,
    ) -> None:
        if callback is None:
            return
        from srcs.agent.callbacks import PHASE_NAMES, PhaseEvent

        data: dict[str, Any] = {"phase_id": phase.id}
        if investigation_id:
            data["investigation_id"] = investigation_id
        event = PhaseEvent(
            phase=phase_idx, phase_name=PHASE_NAMES.get(phase_idx, phase.id), event_type="start", data=data
        )
        callback(event)

    def _emit_item_events(
        self, callback: "InvestigationCallback | None", phase: PhaseConfig, phase_idx: int, outputs: dict[str, Any]
    ) -> None:
        if callback is None:
            return
        from srcs.agent.callbacks import PHASE_NAMES, PhaseEvent

        output_to_item_type = {
            "hypotheses": "hypothesis",
            "evidence": "evidence",
            "causal_chains": "causal_chain",
            "challenges": "challenge",
            "matched_patterns": "pattern",
            "similar_investigations": "similar_case",
            "source_locations": "source_location",
        }
        for key, item_type in output_to_item_type.items():
            items = outputs.get(key)
            if not items:
                continue
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if hasattr(item, "model_dump"):
                    item_data = item.model_dump()
                elif hasattr(item, "__dict__"):
                    item_data = dict(item.__dict__)
                else:
                    item_data = {"value": item}
                item_data["type"] = item_type
                event = PhaseEvent(
                    phase=phase_idx, phase_name=PHASE_NAMES.get(phase_idx, phase.id), event_type="item", data=item_data
                )
                callback(event)
        if phase_idx == 0 and "prior_knowledge" in outputs:
            pk = outputs["prior_knowledge"]
            if hasattr(pk, "matched_patterns") and pk.matched_patterns:
                for pattern_match in pk.matched_patterns:
                    if hasattr(pattern_match, "model_dump"):
                        item_data = pattern_match.model_dump()
                    elif hasattr(pattern_match, "__dict__"):
                        item_data = dict(pattern_match.__dict__)
                    else:
                        item_data = {"value": pattern_match}
                    item_data["type"] = "pattern"
                    event = PhaseEvent(
                        phase=phase_idx,
                        phase_name=PHASE_NAMES.get(phase_idx, phase.id),
                        event_type="item",
                        data=item_data,
                    )
                    callback(event)
            if hasattr(pk, "similar_investigations") and pk.similar_investigations:
                for similar in pk.similar_investigations:
                    if hasattr(similar, "model_dump"):
                        item_data = similar.model_dump()
                    elif hasattr(similar, "__dict__"):
                        item_data = dict(similar.__dict__)
                    else:
                        item_data = {"value": similar}
                    item_data["type"] = "similar_case"
                    event = PhaseEvent(
                        phase=phase_idx,
                        phase_name=PHASE_NAMES.get(phase_idx, phase.id),
                        event_type="item",
                        data=item_data,
                    )
                    callback(event)
            if hasattr(pk, "source_locations") and pk.source_locations:
                for location in pk.source_locations:
                    if hasattr(location, "model_dump"):
                        item_data = location.model_dump()
                    elif hasattr(location, "__dict__"):
                        item_data = dict(location.__dict__)
                    else:
                        item_data = {"value": location}
                    item_data["type"] = "source_location"
                    event = PhaseEvent(
                        phase=phase_idx,
                        phase_name=PHASE_NAMES.get(phase_idx, phase.id),
                        event_type="item",
                        data=item_data,
                    )
                    callback(event)

    def _emit_phase_complete(
        self, callback: "InvestigationCallback | None", phase: PhaseConfig, phase_idx: int, outputs: dict[str, Any]
    ) -> None:
        if callback is None:
            return
        from srcs.agent.callbacks import PHASE_NAMES, PhaseEvent

        data: dict[str, Any] = {"phase_id": phase.id}
        for key, value in outputs.items():
            if isinstance(value, list):
                data[f"{key}_count"] = len(value)
            elif hasattr(value, "items") and isinstance(getattr(value, "items", None), dict):
                data[f"{key}_count"] = len(value.items)
            elif hasattr(value, "value"):
                data[key] = value.value
        if phase_idx == 0 and "prior_knowledge" in outputs:
            pk = outputs["prior_knowledge"]
            if hasattr(pk, "matched_patterns"):
                data["patterns_found"] = len(pk.matched_patterns)
            if hasattr(pk, "similar_investigations"):
                data["similar_cases"] = len(pk.similar_investigations)
            if hasattr(pk, "source_locations"):
                data["source_locations"] = len(pk.source_locations)
            data["prior_knowledge_count"] = (
                data.get("patterns_found", 0) + data.get("similar_cases", 0) + data.get("source_locations", 0)
            )
        event = PhaseEvent(
            phase=phase_idx, phase_name=PHASE_NAMES.get(phase_idx, phase.id), event_type="complete", data=data
        )
        callback(event)

    def _emit_phase_error(
        self, callback: "InvestigationCallback | None", phase: PhaseConfig, phase_idx: int, error: Exception
    ) -> None:
        if callback is None:
            return
        from srcs.agent.callbacks import PHASE_NAMES, PhaseEvent

        event = PhaseEvent(
            phase=phase_idx,
            phase_name=PHASE_NAMES.get(phase_idx, phase.id),
            event_type="error",
            data={"phase_id": phase.id, "error": str(error)},
            message=f"Phase failed: {error}",
        )
        callback(event)
