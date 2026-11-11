"""
File: config_paths.py
Purpose: Locating the application config file.
Category: Utility
Author: artdaq team
Depends: None
Exports: resolve_config_path, CONFIG_PATH_ENV_VAR, _PROJECT_ROOT
Complexity: Low | Lines: 21
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
logger = logging.getLogger(__name__)
CONFIG_PATH_ENV_VAR = 'ARTDAQ_CONFIG'
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def resolve_config_path(config_file: Path | None=None) -> Path | None:
    if config_file is not None:
        return config_file if config_file.exists() else None
    env_path = os.environ.get(CONFIG_PATH_ENV_VAR)
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
        logger.warning('%s is set to %s but that file does not exist; falling back to search', CONFIG_PATH_ENV_VAR, env_path)
    for candidate in (Path('config.yaml'), _PROJECT_ROOT / 'config.yaml'):
        if candidate.exists():
            return candidate
    return None