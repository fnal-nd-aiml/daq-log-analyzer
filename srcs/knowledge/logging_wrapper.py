"""
File: logging_wrapper.py
Purpose: Logging wrappers for knowledge stores.
Category: Utility
Author: artdaq team
Depends: provider, models, callbacks, observability
Exports: LoggingChromaStore, LoggingKnowledgeBase
Complexity: High | Lines: 155
"""

from typing import TYPE_CHECKING, Any, cast
from srcs.models import ErrorSignature, Log, PatternMatch, PriorKnowledge, RootCausePattern, SimilarInvestigation
from srcs.models.callbacks import DataRetrievalCallback, DataRetrievalEvent
from srcs.observability import LoggingWrapperBase
from .chroma_store import ChromaStore
if TYPE_CHECKING:
    from srcs.llm.provider import LLMProvider
    from .base import KnowledgeBase, StorageConfig
    from .store_interface import StructuredStore

class LoggingChromaStore(LoggingWrapperBase):

    def __init__(self, chroma: ChromaStore, callback: DataRetrievalCallback):
        super().__init__(callback)
        self._chroma = chroma

    async def find_similar_investigations(self, description: str, n: int=5) -> list[SimilarInvestigation]:
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='chromadb', operation='find_similar_investigations', query_params={'description': description, 'collection': 'investigations', 'n_results': n}))
        results = await self._chroma.find_similar_investigations(description, n)
        result_summary = None
        if results:
            summaries = []
            for inv in results[:3]:
                score_pct = int(inv.similarity_score * 100)
                cause = (inv.root_cause or 'Unknown')[:50]
                correct = 'Correct' if inv.was_correct else 'Wrong' if inv.was_correct is False else '?'
                summaries.append(f'{score_pct}%: {cause}... ({correct})')
            result_summary = '\n'.join(summaries)
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='chromadb', operation='find_similar_investigations', query_params={}, result_summary=result_summary, result_count=len(results)))
        return results

    async def find_similar_errors(self, error_description: str, n: int=5) -> list[dict]:
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='chromadb', operation='find_similar_errors', query_params={'description': error_description, 'collection': 'error_explanations', 'n_results': n}))
        results = await self._chroma.find_similar_errors(error_description, n)
        result_summary = None
        if results:
            summaries = []
            for err in results[:3]:
                score_pct = int(err.get('similarity', 0) * 100)
                pattern = err.get('pattern_id', 'Unknown')[:30]
                summaries.append(f'{score_pct}%: {pattern}')
            result_summary = '\n'.join(summaries)
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='chromadb', operation='find_similar_errors', query_params={}, result_summary=result_summary, result_count=len(results)))
        return results

    async def find_similar_functions(self, description: str, n: int=10, file_filter: str | None=None) -> list[dict]:
        query_params: dict[str, Any] = {'description': description, 'collection': 'function_summaries', 'n_results': n}
        if file_filter:
            query_params['file_filter'] = file_filter
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='chromadb', operation='find_similar_functions', query_params=query_params))
        results = await self._chroma.find_similar_functions(description, n, file_filter)
        result_summary = None
        if results:
            summaries = []
            for func in results[:3]:
                score_pct = int(func.get('similarity', 0) * 100)
                func_id = func.get('function_id', 'Unknown')
                file_path = func.get('file_path', '')
                if file_path:
                    summaries.append(f'{score_pct}%: {func_id} at {file_path}')
                else:
                    summaries.append(f'{score_pct}%: {func_id}')
            result_summary = '\n'.join(summaries)
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='chromadb', operation='find_similar_functions', query_params={}, result_summary=result_summary, result_count=len(results)))
        return results

    async def find_similar_mechanisms(self, situation_description: str, n: int=5, category: str | None=None) -> list[dict]:
        query_params: dict[str, Any] = {'description': situation_description, 'collection': 'causal_mechanisms', 'n_results': n}
        if category:
            query_params['category'] = category
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='chromadb', operation='find_similar_mechanisms', query_params=query_params))
        results = await self._chroma.find_similar_mechanisms(situation_description, n, category)
        result_summary = None
        if results:
            summaries = []
            for mech in results[:3]:
                score_pct = int(mech.get('similarity', 0) * 100)
                mech_cat = mech.get('category', 'general')
                desc = (mech.get('description', 'Unknown') or 'Unknown')[:40]
                summaries.append(f'{score_pct}%: [{mech_cat}] {desc}...')
            result_summary = '\n'.join(summaries)
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='chromadb', operation='find_similar_mechanisms', query_params={}, result_summary=result_summary, result_count=len(results)))
        return results

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chroma, name)

class LoggingKnowledgeBase(LoggingWrapperBase):

    def __init__(self, kb: 'KnowledgeBase', callback: DataRetrievalCallback):
        super().__init__(callback)
        self._kb = kb
        self._logging_chroma = LoggingChromaStore(kb.chroma, callback)

    @property
    def chroma(self) -> LoggingChromaStore:
        return self._logging_chroma

    @property
    def sqlite(self) -> 'StructuredStore':
        return self._kb.sqlite

    @property
    def config(self) -> 'StorageConfig':
        return self._kb.config

    @property
    def llm(self) -> 'LLMProvider':
        from srcs.llm.provider import LLMProvider
        return cast(LLMProvider, self._kb.llm)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._kb, name)

    def set_phase(self, phase: int) -> None:
        super().set_phase(phase)
        self._logging_chroma.set_phase(phase)

    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='sqlite', operation='find_pattern', query_params={'function': signature.function, 'message_pattern': signature.message_pattern[:100] if signature.message_pattern else None, 'level': signature.level, 'component': signature.component}))
        result = await self._kb.find_pattern(signature)
        result_summary = None
        if result:
            pattern = result.pattern
            result_summary = f"Pattern: {pattern.signature_function or pattern.name or 'Unknown'}\nTimes seen: {pattern.times_seen}\nConfidence: {result.confidence:.0%}"
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='sqlite', operation='find_pattern', query_params={}, result_summary=result_summary, result_count=1 if result else 0))
        return result

    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]:
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='sqlite', operation='get_pattern_root_causes', query_params={'pattern_id': pattern_id[:20] + '...'}))
        results = await self._kb.get_pattern_root_causes(pattern_id)
        result_summary = None
        if results:
            summaries = []
            for rc in results[:3]:
                freq_pct = int(rc.frequency * 100)
                desc = (rc.description or 'Unknown')[:40]
                summaries.append(f'{freq_pct}%: {desc}...')
            result_summary = '\n'.join(summaries)
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='sqlite', operation='get_pattern_root_causes', query_params={}, result_summary=result_summary, result_count=len(results)))
        return results

    async def get_prior_knowledge(self, error: Log, context: list[Log]) -> PriorKnowledge:
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='query', source='combined', operation='get_prior_knowledge', query_params={'error_message': error.message[:80] + '...' if len(error.message) > 80 else error.message, 'component': error.component, 'function': error.function, 'context_count': len(context)}))
        result = await self._kb.get_prior_knowledge(error, context)
        result_summary = f'Matched patterns: {len(result.matched_patterns)}\nSimilar cases: {len(result.similar_investigations)}\nRecommended hypotheses: {len(result.recommended_hypotheses)}\nRecommended queries: {len(result.recommended_queries)}'
        self._callback(DataRetrievalEvent(phase=self._current_phase, event_type='result', source='combined', operation='get_prior_knowledge', query_params={}, result_summary=result_summary, result_count=len(result.matched_patterns) + len(result.similar_investigations)))
        return result

    async def find_similar_investigations(self, error: Log, context: list[Log], n: int=5) -> list[SimilarInvestigation]:
        description = self._kb._create_description(error, context)
        return await self._logging_chroma.find_similar_investigations(description, n)

    async def find_similar_functions(self, description: str, n: int=10, file_filter: str | None=None) -> list[dict]:
        return await self._logging_chroma.find_similar_functions(description, n, file_filter)