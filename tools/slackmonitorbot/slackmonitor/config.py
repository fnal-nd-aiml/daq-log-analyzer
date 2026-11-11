import os
from pathlib import Path
from typing import Any
import yaml


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

def get_default_config_path() -> Path:
    return Path(__file__).parent.parent / 'config.yaml'

def load_config(config_path: Path | None=None) -> dict[str, Any] | None:
    if config_path is None:
        config_path = get_default_config_path()
    if not config_path.exists():
        return None
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None
    slack_config: dict[str, Any] | None = config.get('slack')
    if slack_config is not None:
        slack_config['bot_token'] = slack_config.get('bot_token') or _env_token('SLACK_MONITOR_BOT_TOKEN')
        slack_config['app_token'] = slack_config.get('app_token') or _env_token('SLACK_MONITOR_APP_TOKEN')
    return slack_config

def load_output_config(config_path: Path | None=None) -> dict[str, Any]:
    if config_path is None:
        config_path = get_default_config_path()
    defaults = {'file': 'slack-monitor.log', 'status_file': 'slack-monitor.status'}
    if not config_path.exists():
        return defaults
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return defaults
    output_config = config.get('output', {})
    return {**defaults, **output_config}