"""
File: config.py
Purpose: Shared configuration module.
Category: Utility
Author: artdaq team
Depends: agent, callbacks, knowledge, logging_wrapper, llm, ...
Exports: OutputConfig, AppConfig, CoordinatorFactory, load_config, load_source_config
Complexity: High | Lines: 182
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Callable
    from srcs.llm.logging_wrapper import LoggingLLMProvider
import yaml
from pydantic import BaseModel, ConfigDict, Field
from srcs.agent import InvestigationConfig, InvestigationCoordinator
from srcs.agent.callbacks import DataRetrievalEvent, LLMEvent
from srcs.knowledge import KnowledgeBase, StorageConfig
from srcs.llm import LLMConfig, RecordingLLMProvider, create_llm_provider
from srcs.msgspy.config import MsgSpyConfig
from srcs.output import MarkdownFormatter
from srcs.pipeline import PipelineConfig
from srcs.source import SourceConfig

logger = logging.getLogger(__name__)


class OutputConfig(BaseModel):
    verbose: bool = Field(default=False, description="Show detailed phase-by-phase progress during investigation")
    llm_logging: bool = Field(default=False, description="Show LLM requests and responses")
    full_output: bool = Field(default=False, description="Show complete LLM output without truncation")


class AppConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    llm: LLMConfig
    storage: StorageConfig
    investigation: InvestigationConfig
    output: OutputConfig = Field(default_factory=OutputConfig)
    source: SourceConfig | None = None
    pipeline: PipelineConfig | None = None
    msgspy: MsgSpyConfig | None = None


def load_config(config_file: Path | None = None) -> AppConfig:
    defaults = AppConfig(
        llm=LLMConfig(),
        storage=StorageConfig(),
        investigation=InvestigationConfig(),
        output=OutputConfig(),
        source=None,
        pipeline=None,
    )
    if config_file and config_file.exists():
        config_path = config_file
    elif Path("config.yaml").exists():
        config_path = Path("config.yaml")
    else:
        return defaults
    try:
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        llm = defaults.llm
        storage = defaults.storage
        investigation = defaults.investigation
        output = defaults.output
        source = defaults.source
        pipeline = defaults.pipeline
        msgspy = defaults.msgspy
        if "llm" in user_config:
            llm = LLMConfig(**user_config["llm"])
        if "storage" in user_config:
            storage = StorageConfig(**user_config["storage"])
        if "investigation" in user_config:
            investigation = InvestigationConfig(**user_config["investigation"])
        if "output" in user_config:
            output = OutputConfig(**user_config["output"])
        if "source" in user_config:
            source = SourceConfig(**user_config["source"])
        if "pipeline" in user_config:
            pipeline = PipelineConfig(**user_config["pipeline"])
        if "msgspy" in user_config:
            msgspy = MsgSpyConfig(**user_config["msgspy"])
        return AppConfig(
            llm=llm,
            storage=storage,
            investigation=investigation,
            output=output,
            source=source,
            pipeline=pipeline,
            msgspy=msgspy,
        )
    except Exception as e:
        logger.warning(f"Failed to load config file: {e}")
        return defaults


def load_source_config(config_path: Path | None = None) -> SourceConfig | None:
    if config_path is not None:
        if not config_path.exists():
            return None
        cfg_path = config_path
    elif Path("config.yaml").exists():
        cfg_path = Path("config.yaml")
    else:
        return None
    try:
        with open(cfg_path) as f:
            config = yaml.safe_load(f) or {}
        if "source" in config:
            return SourceConfig(**config["source"])
    except Exception as e:
        logger.warning(f"Could not load source config: {e}")
    return None


class CoordinatorFactory:

    @staticmethod
    def create(config: AppConfig) -> InvestigationCoordinator:
        llm = create_llm_provider(config.llm)
        kb = KnowledgeBase(config.storage, llm)
        coordinator = InvestigationCoordinator(kb, llm, config.investigation, source_config=config.source)
        if config.pipeline is None:
            raise ValueError("Pipeline configuration required. Please add a 'pipeline' section to config.yaml.")
        coordinator.configure_pipeline(config.pipeline)
        return coordinator

    @staticmethod
    def create_with_logging(
        config: AppConfig,
        enable_logging: bool = False,
        full_output: bool = False,
        llm_callback: "Callable[[LLMEvent], None] | None" = None,
        data_callback: "Callable[[DataRetrievalEvent], None] | None" = None,
        enable_llm_recording: bool = True,
    ) -> tuple[
        InvestigationCoordinator,
        MarkdownFormatter | None,
        list[LLMEvent | DataRetrievalEvent] | None,
        RecordingLLMProvider | None,
        "LoggingLLMProvider | None",
    ]:
        llm = create_llm_provider(config.llm)
        kb = KnowledgeBase(config.storage, llm)
        from srcs.llm import LLMProvider

        md_formatter: MarkdownFormatter | None = None
        collected_events: list[LLMEvent | DataRetrievalEvent] | None = None
        recording_llm: RecordingLLMProvider | None = None
        wrapped_llm: LLMProvider
        if enable_llm_recording:
            recording_llm = RecordingLLMProvider(llm)
            wrapped_llm = recording_llm
        else:
            wrapped_llm = llm
        if enable_logging:
            from srcs.knowledge.logging_wrapper import LoggingKnowledgeBase
            from srcs.llm.logging_wrapper import LoggingLLMProvider

            md_formatter = MarkdownFormatter(full_output=full_output)
            collected_events = []

            def on_llm_event(event: LLMEvent) -> None:
                if collected_events is not None:
                    collected_events.append(event)
                if llm_callback is not None:
                    llm_callback(event)

            def on_data_event(event: DataRetrievalEvent) -> None:
                if collected_events is not None:
                    collected_events.append(event)
                if data_callback is not None:
                    data_callback(event)

            logging_llm = LoggingLLMProvider(wrapped_llm, on_llm_event)
            logging_kb = LoggingKnowledgeBase(kb, on_data_event)
            coordinator = InvestigationCoordinator(
                cast(KnowledgeBase, logging_kb), logging_llm, config.investigation, source_config=config.source
            )
        else:
            logging_llm = None
            coordinator = InvestigationCoordinator(kb, wrapped_llm, config.investigation, source_config=config.source)
        if config.pipeline is None:
            raise ValueError("Pipeline configuration required. Please add a 'pipeline' section to config.yaml.")
        coordinator.configure_pipeline(config.pipeline)
        coordinator.recording_llm = recording_llm
        return (coordinator, md_formatter, collected_events, recording_llm, logging_llm)
