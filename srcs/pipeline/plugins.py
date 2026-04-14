"""
File: plugins.py
Purpose: Plugin executor loading with security controls.
Category: Utility
Author: artdaq team
Depends: None
Exports: PluginLoadError, PluginSecurityError, ExecutorPluginLoader, load_plugin_executors
Complexity: Medium | Lines: 78
"""

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ExecutorPluginConfig
    from .executor import PhaseExecutor
logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    pass


class PluginSecurityError(PluginLoadError):
    pass


class ExecutorPluginLoader:
    DEFAULT_ALLOWED_PREFIXES = ["srcs.", "artdaq_plugins."]

    def __init__(self, allowed_prefixes: list[str] | None = None):
        self._allowed_prefixes = allowed_prefixes or self.DEFAULT_ALLOWED_PREFIXES

    def _is_allowed_module(self, module_path: str) -> bool:
        return any(
            (module_path.startswith(prefix) or module_path == prefix.rstrip(".") for prefix in self._allowed_prefixes)
        )

    def load(self, plugin_config: "ExecutorPluginConfig") -> "PhaseExecutor":
        from .executor import PhaseExecutor

        if not self._is_allowed_module(plugin_config.module):
            allowed = ", ".join(self._allowed_prefixes)
            raise PluginSecurityError(
                f"Plugin '{plugin_config.id}' module '{plugin_config.module}' is not in allowed prefixes: {allowed}"
            )
        try:
            module = importlib.import_module(plugin_config.module)
        except ImportError as e:
            raise PluginLoadError(
                f"Plugin '{plugin_config.id}' failed to import module '{plugin_config.module}': {e}"
            ) from e
        try:
            cls = getattr(module, plugin_config.class_name)
        except AttributeError as e:
            raise PluginLoadError(
                f"Plugin '{plugin_config.id}' class '{plugin_config.class_name}' not found in module '{plugin_config.module}'"
            ) from e
        if not isinstance(cls, type) or not issubclass(cls, PhaseExecutor):
            raise PluginLoadError(
                f"Plugin '{plugin_config.id}' class '{plugin_config.class_name}' must be a subclass of PhaseExecutor"
            )
        try:
            if plugin_config.config:
                instance = cls(**plugin_config.config)
            else:
                instance = cls()
        except Exception as e:
            raise PluginLoadError(f"Plugin '{plugin_config.id}' failed to instantiate: {e}") from e
        logger.info(
            f"Loaded plugin executor '{plugin_config.id}' from {plugin_config.module}.{plugin_config.class_name}"
        )
        return instance


def load_plugin_executors(
    plugin_configs: list["ExecutorPluginConfig"], allowed_prefixes: list[str] | None = None
) -> dict[str, "PhaseExecutor"]:
    loader = ExecutorPluginLoader(allowed_prefixes)
    executors: dict[str, "PhaseExecutor"] = {}
    for config in plugin_configs:
        try:
            executor = loader.load(config)
            executors[config.id] = executor
        except PluginLoadError as e:
            logger.error(f"Failed to load plugin: {e}")
    return executors
