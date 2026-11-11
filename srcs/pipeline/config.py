"""
File: config.py
Purpose: Pipeline configuration models.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: FastPathAction, FilterConfig, WeightedVoteConfig, CustomAggregatorConfig, PerKeyAggregationConfig, ...
Complexity: High | Lines: 212
"""

from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

class FastPathAction(str, Enum):
    SKIP_TO = 'skip_to'
    EARLY_RETURN = 'early_return'
    USE_VARIANT = 'use_variant'

class FilterConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    condition: str | None = None
    limit: int | None = None

class WeightedVoteConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    weights: dict[str, float]
    normalize: bool = True

    @model_validator(mode='after')
    def validate_weights(self) -> WeightedVoteConfig:
        for persona_id, weight in self.weights.items():
            if weight < 0.0:
                raise ValueError(f"Weight for persona '{persona_id}' must be >= 0.0, got {weight}")
        return self

class CustomAggregatorConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module: str
    function: str
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_module_path(self) -> CustomAggregatorConfig:
        parts = self.module.split('.')
        for part in parts:
            if not part.isidentifier():
                raise ValueError(f"Invalid module path: '{self.module}'")
        if not self.function.isidentifier():
            raise ValueError(f"Invalid function name: '{self.function}'")
        return self

class PerKeyAggregationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    default: str = 'merge'
    overrides: dict[str, str] = Field(default_factory=dict)

class AggregationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str | None = None
    weighted: WeightedVoteConfig | None = None
    custom: CustomAggregatorConfig | None = None
    per_key: PerKeyAggregationConfig | None = None

    @model_validator(mode='after')
    def validate_single_mode(self) -> AggregationConfig:
        modes = sum([self.strategy is not None, self.weighted is not None, self.custom is not None, self.per_key is not None])
        if modes != 1:
            raise ValueError('AggregationConfig must specify exactly one of: strategy, weighted, custom, or per_key')
        return self

class PanelConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    personas: list[str]
    execution: str = 'sequential'
    aggregation: str | AggregationConfig = 'merge'
    timeout: int = 60

class PhaseConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    executor: str | None = None
    panel: PanelConfig | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    filter: dict[str, FilterConfig] | None = None
    enabled: str | bool = True
    requires: str | None = None

    @model_validator(mode='after')
    def validate_executor_or_panel(self) -> 'PhaseConfig':
        if self.executor is None and self.panel is None:
            raise ValueError(f"Phase '{self.id}' must specify either 'executor' or 'panel'")
        if self.executor is not None and self.panel is not None:
            raise ValueError(f"Phase '{self.id}' cannot specify both 'executor' and 'panel'")
        return self

class BranchConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    after: str
    condition: str
    skip_to: str

class FastPathConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    after: str | None = None
    condition: str
    action: FastPathAction = FastPathAction.SKIP_TO
    skip_to: str | None = None
    result_builder: str | None = None
    variant: str | None = None

    @model_validator(mode='after')
    def validate_action_fields(self) -> 'FastPathConfig':
        if self.action == FastPathAction.SKIP_TO and (not self.skip_to):
            raise ValueError(f"Fast path '{self.name}' with action=skip_to requires 'skip_to' field")
        if self.action == FastPathAction.EARLY_RETURN and (not self.result_builder):
            raise ValueError(f"Fast path '{self.name}' with action=early_return requires 'result_builder'")
        if self.action == FastPathAction.USE_VARIANT and (not self.variant):
            raise ValueError(f"Fast path '{self.name}' with action=use_variant requires 'variant' field")
        return self

class PhaseOverrideConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    config: dict[str, Any] | None = None
    enabled: bool | None = None

class VariantConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    phase_overrides: dict[str, PhaseOverrideConfig] = Field(default_factory=dict)

class HookConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    after: str | None = None
    before: str | None = None
    on_error: bool = False
    on_complete: bool = False
    action: str

    @model_validator(mode='after')
    def validate_trigger(self) -> 'HookConfig':
        triggers = sum([self.after is not None, self.before is not None, self.on_error, self.on_complete])
        if triggers != 1:
            raise ValueError('Hook must specify exactly one of: after, before, on_error, on_complete')
        return self

class ExecutorPluginConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    id: str
    module: str
    class_name: str = Field(alias='class')
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_module_path(self) -> ExecutorPluginConfig:
        if not self.module:
            raise ValueError(f"Plugin '{self.id}' requires a module path")
        if not self.class_name:
            raise ValueError(f"Plugin '{self.id}' requires a class name")
        parts = self.module.split('.')
        for part in parts:
            if not part.isidentifier():
                raise ValueError(f"Plugin '{self.id}' has invalid module path: '{self.module}'")
        return self

class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_at: str | None = None
    skip_phases: list[str] = Field(default_factory=list)
    phases: list[PhaseConfig]
    branches: list[BranchConfig] = Field(default_factory=list)
    fast_paths: list[FastPathConfig] = Field(default_factory=list)
    variants: dict[str, VariantConfig] = Field(default_factory=dict)
    hooks: list[HookConfig] = Field(default_factory=list)
    executors: list[ExecutorPluginConfig] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_phase_references(self) -> 'PipelineConfig':
        phase_ids = {p.id for p in self.phases}
        if self.start_at and self.start_at not in phase_ids:
            raise ValueError(f"start_at references unknown phase '{self.start_at}'")
        for phase_id in self.skip_phases:
            if phase_id not in phase_ids:
                raise ValueError(f"skip_phases references unknown phase '{phase_id}'")
        for branch in self.branches:
            if branch.after not in phase_ids:
                raise ValueError(f"Branch references unknown phase '{branch.after}'")
            if branch.skip_to not in phase_ids:
                raise ValueError(f"Branch skip_to references unknown phase '{branch.skip_to}'")
        for fast_path in self.fast_paths:
            if fast_path.after and fast_path.after not in phase_ids:
                raise ValueError(f"Fast path '{fast_path.name}' after references unknown phase '{fast_path.after}'")
            if fast_path.skip_to and fast_path.skip_to not in phase_ids:
                raise ValueError(f"Fast path '{fast_path.name}' skip_to references unknown phase '{fast_path.skip_to}'")
            if fast_path.variant and fast_path.variant not in self.variants:
                raise ValueError(f"Fast path '{fast_path.name}' references unknown variant '{fast_path.variant}'")
        for hook in self.hooks:
            if hook.after and hook.after not in phase_ids:
                raise ValueError(f"Hook action='{hook.action}' after references unknown phase '{hook.after}'")
            if hook.before and hook.before not in phase_ids:
                raise ValueError(f"Hook action='{hook.action}' before references unknown phase '{hook.before}'")
        for variant_name, variant in self.variants.items():
            for phase_id in variant.phase_overrides:
                if phase_id not in phase_ids:
                    raise ValueError(f"Variant '{variant_name}' references unknown phase '{phase_id}'")
        return self

    def get_phase(self, phase_id: str) -> PhaseConfig | None:
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        return None

    def get_phase_index(self, phase_id: str) -> int | None:
        for i, phase in enumerate(self.phases):
            if phase.id == phase_id:
                return i
        return None