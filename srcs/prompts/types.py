"""
File: types.py
Purpose: Type definitions for the prompts module.
Category: Utility
Author: artdaq team
Depends: None
Exports: SystemPromptType, UserPromptType, PromptMetadata, PromptTemplate
Complexity: Medium | Lines: 66
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class SystemPromptType(Enum):
    ARCHIVIST = 'archivist'
    THEORIST = 'theorist'
    DETECTIVE = 'detective'
    LOGICIAN = 'logician'
    SKEPTIC = 'skeptic'
    JUDGE = 'judge'
    SYNTHESIZER = 'synthesizer'
    LEARNER = 'learner'
    COORDINATOR = 'coordinator'
    CHRONICLER = 'chronicler'
    QA_THEORIST = 'qa/qa_theorist'
    QA_DETECTIVE = 'qa/qa_detective'
    QA_LOGICIAN = 'qa/qa_logician'
    QA_SKEPTIC = 'qa/qa_skeptic'
    ARTIFACT_EVALUATION = 'artifact_evaluation'
    BINDER_CODE_ANALYSIS = 'binder_code_analysis'
    HINT_INTERPRETATION = 'hint_interpretation'
    ERROR_CONTEXT_PARSING = 'error_context_parsing'

class UserPromptType(Enum):
    HYPOTHESIS_GENERATION = 'hypothesis_generation'
    EVIDENCE_QUERY = 'evidence_query'
    CAUSAL_CHAIN = 'causal_chain'
    CAUSAL_CHAIN_WITH_EVIDENCE = 'causal_chain_with_evidence'
    ADVERSARIAL_REVIEW = 'adversarial_review'
    OUTCOME_ASSESSMENT = 'outcome_assessment'
    FINAL_SYNTHESIS = 'final_synthesis'
    PRIOR_KNOWLEDGE_SUMMARY = 'prior_knowledge_summary'
    PATTERN_EXTRACTION = 'pattern_extraction'
    CALL_GRAPH_SUMMARY = 'call_graph_summary'
    LOG_BUNDLE_ANALYSIS = 'log_bundle_analysis'
    LOG_TIMELINE_EXTRACTION = 'log_timeline_extraction'
    BOARDREADER_IDENTIFICATION = 'boardreader_identification'
    PRIMARY_ERROR_SELECTION = 'primary_error_selection'
    DOCUMENTATION_SELECTION = 'documentation_selection'
    DOC_EXTRACTION = 'doc_extraction'
    ARTIFACT_EVALUATION = 'artifact_evaluation'
    BINDER_CODE_ANALYSIS = 'binder_code_analysis'
    HINT_INTERPRETATION = 'hint_interpretation'
    ERROR_CONTEXT_PARSING = 'error_context_parsing'

@dataclass(frozen=True)
class PromptMetadata:
    required_placeholders: frozenset[str] = field(default_factory=frozenset)
    optional_placeholders: frozenset[str] = field(default_factory=frozenset)

    @property
    def all_placeholders(self) -> frozenset[str]:
        return self.required_placeholders | self.optional_placeholders

@dataclass
class PromptTemplate:
    content: str
    prompt_type: UserPromptType | SystemPromptType
    metadata: PromptMetadata
    path: Path | None = None

    def format(self, **kwargs: object) -> str:
        from .formatters import safe_format
        return safe_format(self.content, self.prompt_type, self.metadata, **kwargs)
__all__ = ['SystemPromptType', 'UserPromptType', 'PromptMetadata', 'PromptTemplate']