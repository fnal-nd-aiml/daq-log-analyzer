"""
File: hooks.py
Purpose: Pipeline hooks for side effects.
Category: Utility
Author: artdaq team
Depends: models, workbinder
Exports: HookRegistry, store_investigation_hook, store_binder_hook, log_metrics_hook, store_failed_investigation_hook
Complexity: Medium | Lines: 101
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine
if TYPE_CHECKING:
    from srcs.models import Investigation
logger = logging.getLogger(__name__)
HookFunction = Callable[[dict[str, Any], 'Investigation | None'], Coroutine[Any, Any, None]]

class HookRegistry:

    def __init__(self) -> None:
        self._hooks: dict[str, HookFunction] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register('store_investigation', store_investigation_hook)
        self.register('store_binder', store_binder_hook)
        self.register('log_metrics', log_metrics_hook)
        self.register('store_failed_investigation', store_failed_investigation_hook)

    def register(self, name: str, hook_fn: HookFunction) -> None:
        self._hooks[name] = hook_fn
        logger.debug(f'Registered hook: {name}')

    def get(self, name: str) -> HookFunction | None:
        return self._hooks.get(name)

    def list_hooks(self) -> list[str]:
        return list(self._hooks.keys())

    async def execute(self, action: str, context: dict[str, Any], investigation: 'Investigation | None'=None) -> None:
        hook_fn = self.get(action)
        if hook_fn is None:
            logger.warning(f'Unknown hook action: {action}')
            return
        try:
            await hook_fn(context, investigation)
        except Exception as e:
            logger.error(f"Hook '{action}' failed: {e}")

async def store_investigation_hook(context: dict[str, Any], investigation: 'Investigation | None') -> None:
    if investigation is None:
        logger.debug('store_investigation: No investigation to store')
        return
    kb = context.get('kb')
    if kb is None:
        logger.warning('store_investigation: No knowledge base in context')
        return
    try:
        await kb.store_investigation(investigation)
        logger.debug(f'Stored investigation {investigation.id}')
    except Exception as e:
        logger.warning(f'Failed to store investigation: {e}')

async def store_binder_hook(context: dict[str, Any], investigation: 'Investigation | None') -> None:
    if investigation is None or investigation.binder is None:
        logger.debug('store_binder: No binder to store')
        return
    binder_store = context.get('binder_store')
    if binder_store is None:
        kb = context.get('kb')
        if kb is not None and hasattr(kb, 'config'):
            try:
                from srcs.workbinder import BinderStore
                binder_store = BinderStore(kb.config.sqlite_path)
            except Exception as e:
                logger.warning(f'Failed to create binder store: {e}')
                return
        else:
            logger.debug('store_binder: No binder store available')
            return
    try:
        investigation.binder.status = 'completed'
        await binder_store.save_binder(investigation.binder)
        logger.debug(f'Stored work binder {investigation.binder.id}')
    except Exception as e:
        logger.warning(f'Failed to store work binder: {e}')

async def log_metrics_hook(context: dict[str, Any], investigation: 'Investigation | None') -> None:
    if investigation is None:
        return
    metrics: dict[str, str | int | float] = {'investigation_id': investigation.id, 'outcome': investigation.outcome.value if investigation.outcome else 'unknown', 'hypotheses_count': len(investigation.hypotheses) if investigation.hypotheses else 0, 'evidence_count': len(investigation.evidence.items) if investigation.evidence else 0, 'chains_count': len(investigation.causal_chains) if investigation.causal_chains else 0}
    if investigation.started_at and investigation.completed_at:
        metrics['duration_seconds'] = (investigation.completed_at - investigation.started_at).total_seconds()
    logger.info(f'Investigation metrics: {metrics}')

async def store_failed_investigation_hook(context: dict[str, Any], investigation: 'Investigation | None') -> None:
    if investigation is None:
        logger.debug('store_failed_investigation: No investigation to store')
        return
    kb = context.get('kb')
    if kb is None:
        logger.debug('store_failed_investigation: No knowledge base in context')
        return
    try:
        from srcs.models import InvestigationOutcome
        if investigation.outcome is None:
            investigation.outcome = InvestigationOutcome.INSUFFICIENT
        await kb.store_investigation(investigation)
        logger.debug(f'Stored failed investigation {investigation.id}')
    except Exception as e:
        logger.warning(f'Failed to store failed investigation: {e}')