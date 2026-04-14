"""
File: config.py
Purpose: Configuration model for MessageFacility UDP message spy.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: FieldFilter, ThrottleConfig, MsgSpyConfig, load_msgspy_config
Complexity: Medium | Lines: 62
"""

import logging
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FieldFilter(BaseModel):
    include: list[str] | None = Field(
        default=None, description="Glob allowlist — value must match at least one pattern"
    )
    exclude: list[str] | None = Field(default=None, description="Glob blocklist — value must NOT match any pattern")


class ThrottleConfig(BaseModel):
    enabled: bool = Field(default=False, description="Enable throttling")
    max_repeat: int = Field(default=5, description="Suppress after N consecutive identical messages")
    summary: bool = Field(default=True, description="Emit '... repeated N times' when streak ends")
    key_fields: list[str] = Field(
        default_factory=lambda: ["message"], description="MFMessage fields that define 'identical'"
    )


class MsgSpyConfig(BaseModel):
    bind_address: str = Field(default="0.0.0.0", description="UDP bind address")
    port: int = Field(default=30000, description="UDP listen port")
    multicast_group: str | None = Field(default=None, description="Multicast group to join (e.g. 227.128.12.27)")
    multicast_interface: str = Field(default="0.0.0.0", description="Interface for multicast join")
    socket_buffer_size: int = Field(default=1048576, description="SO_RCVBUF size in bytes (1MB default)")
    output_path: Path = Field(default=Path("msgspy_output.log"), description="Output file path")
    append: bool = Field(default=False, description="Append to output file instead of overwriting")
    queue_size: int = Field(default=50000, description="Maximum queue depth between receiver and writer")
    flush_interval_ms: int = Field(default=100, description="Flush period in milliseconds")
    batch_size: int = Field(default=200, description="Messages per write batch")
    poll_timeout_ms: int = Field(default=50, description="Socket poll timeout in milliseconds")
    write_raw: bool = Field(default=True, description="Write raw bytes (fast) vs parsed/cleaned reformat")
    filters: dict[str, FieldFilter] = Field(
        default_factory=dict, description="Field-based message filters keyed by MFMessage field name"
    )
    throttle: ThrottleConfig = Field(
        default_factory=ThrottleConfig, description="Duplicate message throttling configuration"
    )


def load_msgspy_config(config_path: Path | None = None) -> MsgSpyConfig:
    if config_path is not None:
        if not config_path.exists():
            return MsgSpyConfig()
        cfg_path = config_path
    elif Path("config.yaml").exists():
        cfg_path = Path("config.yaml")
    else:
        return MsgSpyConfig()
    try:
        with open(cfg_path) as f:
            config = yaml.safe_load(f) or {}
        if "msgspy" in config:
            return MsgSpyConfig(**config["msgspy"])
    except Exception as e:
        logger.warning(f"Could not load msgspy config: {e}")
    return MsgSpyConfig()
