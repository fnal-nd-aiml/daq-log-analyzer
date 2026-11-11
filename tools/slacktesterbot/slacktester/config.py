import os
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field


def _env_token(name: str) -> str | None:
    """Read a token from the environment, falling back to the repo-root .env.slack file."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = Path(__file__).resolve().parents[3] / '.env.slack'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key.strip() == name:
                return value.strip().strip('"\'') or None
    return None

class ScenariosConfig(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: ['investigate', 'message', 'feedback', 'ask', 'list', 'config', 'workbinder', 'admin', 'help', 'version'])

class MockConfig(BaseModel):
    simulate_delays: bool = False
    mock_llm_responses: bool = True

class OutputConfig(BaseModel):
    format: Literal['terminal', 'json'] = 'terminal'
    verbose: bool = True

class SlackConfig(BaseModel):
    bot_token: str | None = None
    app_token: str | None = None
    channel: str | None = None
    target_bot: str | None = None
    target_bot_id: str | None = None

class TesterConfig(BaseModel):
    scenarios: ScenariosConfig = Field(default_factory=ScenariosConfig)
    mock: MockConfig = Field(default_factory=MockConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)

def load_config(config_path: Path | None=None) -> TesterConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        config = TesterConfig.model_validate(data)
    else:
        config = TesterConfig()
    config.slack.bot_token = config.slack.bot_token or _env_token('SLACK_TESTER_BOT_TOKEN')
    config.slack.app_token = config.slack.app_token or _env_token('SLACK_TESTER_APP_TOKEN')
    return config