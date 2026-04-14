"""
File: config_store.py
Purpose: Per-channel and per-user settings storage.
Category: Utility
Author: artdaq team
Depends: None
Exports: ChannelConfig, ConfigStore
Complexity: Medium | Lines: 109
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    verbose: bool = False
    llm_logging: bool = False
    full_output: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"verbose": self.verbose, "llm_logging": self.llm_logging, "full_output": self.full_output}

    @classmethod
    def from_dict(cls, data: dict[str, Any], defaults: Any | None = None) -> ChannelConfig:
        if defaults:
            return cls(
                verbose=data.get("verbose", defaults.verbose),
                llm_logging=data.get("llm_logging", defaults.llm_logging),
                full_output=data.get("full_output", defaults.full_output),
            )
        return cls(
            verbose=data.get("verbose", False),
            llm_logging=data.get("llm_logging", False),
            full_output=data.get("full_output", False),
        )

    @classmethod
    def from_output_config(cls, output_config: Any) -> ChannelConfig:
        return cls(
            verbose=output_config.verbose, llm_logging=output_config.llm_logging, full_output=output_config.full_output
        )


@dataclass
class ConfigStore:
    data_dir: Path
    output_defaults: Any | None = None
    _configs: dict[str, ChannelConfig] = field(default_factory=dict)
    _loaded: bool = False

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)

    @property
    def _config_file(self) -> Path:
        return self.data_dir / "slack_config.json"

    def _load(self) -> None:
        if self._loaded:
            return
        if self._config_file.exists():
            try:
                data = json.loads(self._config_file.read_text())
                for key, value in data.items():
                    self._configs[key] = ChannelConfig.from_dict(value, self.output_defaults)
            except Exception as e:
                logger.warning(f"Failed to load slack config: {e}")
        self._loaded = True

    def _save(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {key: config.to_dict() for key, config in self._configs.items()}
            self._config_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save slack config: {e}")

    def get_config(self, channel_id: str) -> ChannelConfig:
        self._load()
        if channel_id not in self._configs:
            if self.output_defaults:
                self._configs[channel_id] = ChannelConfig.from_output_config(self.output_defaults)
            else:
                self._configs[channel_id] = ChannelConfig()
        return self._configs[channel_id]

    def set_setting(self, channel_id: str, setting: str, value: bool) -> bool:
        self._load()
        config = self.get_config(channel_id)
        setting = setting.lower().replace("-", "_")
        if setting == "verbose":
            config.verbose = value
        elif setting == "llm_logging":
            config.llm_logging = value
        elif setting == "full_output":
            config.full_output = value
        else:
            return False
        self._save()
        return True

    def format_config(self, channel_id: str) -> str:
        config = self.get_config(channel_id)
        lines = [
            "*Current Settings:*",
            f"• `verbose`: {('on' if config.verbose else 'off')} - Show detailed phase-by-phase progress",
            f"• `llm-logging`: {('on' if config.llm_logging else 'off')} - Show LLM requests and responses",
            f"• `full-output`: {('on' if config.full_output else 'off')} - Show complete LLM output without truncation",
            "",
            "_Defaults come from `output` section in config.yaml_",
        ]
        return "\n".join(lines)
