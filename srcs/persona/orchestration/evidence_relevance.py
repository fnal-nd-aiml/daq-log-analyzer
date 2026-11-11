"""
File: evidence_relevance.py
Purpose: LLM-powered relevance assessment for evidence scoring.
Category: Utility
Author: artdaq team
Depends: llm, investigation, workbinder, pydantic
Exports: RelevanceAssessment, LLMRelevanceAssessor
Complexity: Medium | Lines: 118
"""

import logging
import re
from typing import TYPE_CHECKING
from pydantic import BaseModel
if TYPE_CHECKING:
    from srcs.llm import LLMProvider
    from srcs.models.investigation import EvidenceItem, Hypothesis
    from srcs.workbinder import WorkBinder
logger = logging.getLogger(__name__)

class RelevanceAssessment(BaseModel):
    relevance_score: float
    reasoning: str
    supports: bool
    contradicts: bool
    key_terms_matched: list[str]

class LLMRelevanceAssessor:
    ASSESSMENT_PROMPT = '''Assess how relevant this evidence is to the given hypothesis.

Hypothesis: {hypothesis}

Evidence Type: {evidence_type}
Evidence Content: {evidence}

Consider:
1. Does the evidence directly support or contradict the hypothesis?
2. Are there key terms or concepts that link them?
3. Is the relationship causal or circumstantial?

Respond with JSON:
{{
    "relevance_score": <float from -1.0 (contradicts) to 1.0 (supports)>,
    "reasoning": "<brief explanation>",
    "supports": <true if evidence supports hypothesis>,
    "contradicts": <true if evidence contradicts hypothesis>,
    "key_terms_matched": ["<term1>", "<term2>", ...]
}}
'''

    def __init__(self, llm: 'LLMProvider | None'=None, use_llm: bool | None=None):
        self._llm = llm
        if use_llm is not None:
            self._use_llm = use_llm
        else:
            self._use_llm = llm is not None

    async def assess(self, evidence: 'EvidenceItem', hypothesis: 'Hypothesis', binder: 'WorkBinder | None'=None) -> float:
        if self._use_llm and self._llm is not None:
            try:
                return await self._llm_assess(evidence, hypothesis, binder)
            except Exception as e:
                logger.debug(f'LLM relevance assessment failed: {e}')
        return self._regex_assess(evidence, hypothesis)

    async def _llm_assess(self, evidence: 'EvidenceItem', hypothesis: 'Hypothesis', binder: 'WorkBinder | None'=None) -> float:
        prompt = self.ASSESSMENT_PROMPT.format(hypothesis=hypothesis.description, evidence_type=evidence.evidence_type, evidence=evidence.content[:1000])
        request_id = None
        if binder is not None:
            request_id = binder.record_llm_request(persona='Detective', prompt_key='relevance_assessment', system_prompt='You are an evidence analysis expert.', user_prompt=prompt, model=getattr(self._llm, 'model', 'unknown'), phase=2)
        try:
            if self._llm is None:
                raise RuntimeError('LLM provider is None')
            response = await self._llm.generate_structured(prompt, RelevanceAssessment, system_prompt='You are an evidence analysis expert. Respond with JSON only.')
            if binder is not None and request_id is not None:
                binder.record_llm_response(request_id=request_id, raw_response=str(response.model_dump()), parsed_content=response.model_dump(), tokens_used=0, latency_ms=0, parse_success=True, phase=2)
            return response.relevance_score
        except Exception as e:
            if binder is not None and request_id is not None:
                binder.record_llm_response(request_id=request_id, raw_response=str(e), parsed_content=None, tokens_used=0, latency_ms=0, parse_success=False, parse_errors=[str(e)], phase=2)
            raise

    def _regex_assess(self, evidence: 'EvidenceItem', hypothesis: 'Hypothesis') -> float:
        desc_lower = hypothesis.description.lower()
        content_lower = evidence.content.lower()
        relevance = 0.0
        if any((term in desc_lower for term in ['race condition', 'concurrency', 'thread', 'synchronization', 'deadlock', 'mutex'])):
            if any((s in content_lower for s in ['mutex', 'lock_guard', 'unique_lock', 'atomic', 'synchronized', 'critical_section'])):
                relevance -= 0.25
            if re.search('std::thread|pthread|boost::thread', content_lower):
                if not any((s in content_lower for s in ['mutex', 'lock', 'atomic'])):
                    relevance += 0.2
        if any((term in desc_lower for term in ['configuration', 'config', 'parameter', 'setting', 'fhicl', 'fcl'])):
            if re.search('config|param|fhicl|pset|getenv|get_if_present', content_lower):
                relevance += 0.2
            if re.search('default|fallback|missing.*param', content_lower):
                relevance += 0.15
        if any((term in desc_lower for term in ['resource', 'memory', 'allocation', 'exhaustion', 'leak', 'buffer'])):
            if re.search('alloc|malloc|new\\s+|make_unique|make_shared|buffer|capacity', content_lower):
                relevance += 0.2
            if re.search('delete|free|release|reset\\(\\)', content_lower):
                relevance += 0.1
        if any((term in desc_lower for term in ['timeout', 'network', 'connection', 'socket', 'tcp', 'udp'])):
            if re.search('timeout|connect|socket|recv|send|bind|listen', content_lower):
                relevance += 0.2
            if re.search('retry|reconnect|backoff', content_lower):
                relevance += 0.1
        if any((term in desc_lower for term in ['null', 'nullptr', 'pointer', 'dereference', 'validation'])):
            if re.search('nullptr|NULL|!.*\\)|==.*null|\\.empty\\(\\)', content_lower):
                relevance += 0.15
            if re.search('throw|exception|assert|abort', content_lower):
                relevance -= 0.1
        if any((term in desc_lower for term in ['exception', 'error handling', 'catch', 'throw'])):
            if re.search('try\\s*\\{|catch\\s*\\(|throw\\s+|exception', content_lower):
                relevance += 0.2
            if re.search('noexcept|nothrow', content_lower):
                relevance -= 0.1
        if relevance == 0.0:
            categories = ['hardware', 'software', 'configuration', 'timing', 'resource']
            for cat in categories:
                if cat in desc_lower and cat in content_lower:
                    relevance = 0.15
                    break
            if relevance == 0.0:
                significant_words = [w for w in desc_lower.split() if len(w) > 4 and w not in ('error', 'issue', 'problem', 'cause', 'might', 'could')]
                if any((word in content_lower for word in significant_words[:5])):
                    relevance = 0.05
        return max(-1.0, min(1.0, relevance))