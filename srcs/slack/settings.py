"""
File: settings.py
Purpose: Slack bot configuration settings.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: YamlConfigSettingsSource, SlackSettings
Complexity: Medium | Lines: 42
"""

from pathlib import Path
from typing import Any
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

class YamlConfigSettingsSource(PydanticBaseSettingsSource):

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        config_path = Path('config.yaml')
        if not config_path.exists():
            return (None, field_name, False)
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        slack_config = config.get('slack', {})
        if field_name in slack_config:
            return (slack_config[field_name], field_name, False)
        return (None, field_name, False)

    def __call__(self) -> dict[str, Any]:
        config_path = Path('config.yaml')
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        section: dict[str, Any] = config.get('slack', {})
        return section

class SlackSettings(BaseSettings):
    socket_mode: bool = Field(default=True, description='Use Socket Mode (True) or HTTP mode (False)')
    http_port: int = Field(default=3000, description='Port for HTTP mode')
    bot_token: str = Field(description='Bot token (xoxb-...)')
    app_token: str | None = Field(default=None, description='App-level token (xapp-... for socket mode)')
    signing_secret: str | None = Field(default=None, description='Request signing secret (HTTP mode)')
    api_url: str | None = Field(default=None, description='AgentClient API URL (use REST API instead of direct coordinator)')
    max_queue_depth: int = Field(default=3, description='Maximum queued tasks')
    announce_channel: str | None = Field(default=None, description='Channel to announce connect/disconnect (channel ID or name)')
    model_config = SettingsConfigDict(env_prefix='LOGANALYZER_SLACK_BOT_')

    @classmethod
    def settings_customise_sources(cls, settings_cls: type[BaseSettings], init_settings: PydanticBaseSettingsSource, env_settings: PydanticBaseSettingsSource, dotenv_settings: PydanticBaseSettingsSource, file_secret_settings: PydanticBaseSettingsSource) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls))