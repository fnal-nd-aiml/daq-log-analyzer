"""
File: question.py
Purpose: Question-answering data models for the panel of experts system.
Category: Data
Author: artdaq team
Depends: base, pydantic
Exports: QuestionType, SourceCitation, VotingResult, QuestionContext, PanelResponse, ...
Complexity: Medium | Lines: 89
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from .base import generate_id
if TYPE_CHECKING:
    from srcs.persona.base import Contribution, Critique, Discussion
    from .logs import Log

class QuestionType(str, Enum):
    HOW_TO = 'how_to'
    WHY = 'why'
    WHAT_IS = 'what_is'
    TROUBLESHOOT = 'troubleshoot'
    COMPARE = 'compare'
    BEST_PRACTICE = 'best_practice'

@dataclass
class SourceCitation:
    type: str
    reference: str
    excerpt: str
    relevance: float = 0.0
    line_range: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'SourceCitation':
        return cls(type=d.get('type', 'unknown'), reference=d.get('reference', ''), excerpt=d.get('excerpt', ''), relevance=d.get('relevance', 0.0), line_range=d.get('line_range'))

@dataclass
class VotingResult:
    endorsements: int
    critiques: list['Critique'] = field(default_factory=list)
    consensus_score: float = 0.0

@dataclass
class QuestionContext:
    question: str
    question_type: QuestionType
    question_id: str = field(default_factory=generate_id)
    related_logs: list['Log'] = field(default_factory=list)
    contributions: list['Contribution'] = field(default_factory=list)
    discussions: list['Discussion'] = field(default_factory=list)
    voting_results: dict[str, VotingResult] = field(default_factory=dict)

    def get_contributions_by_persona(self, persona_id: str) -> list['Contribution']:
        return [c for c in self.contributions if c.persona_id == persona_id]

    def add_contribution(self, contribution: 'Contribution') -> None:
        self.contributions.append(contribution)

    def get_prior_contributions_summary(self) -> str:
        if not self.contributions:
            return 'No prior contributions yet.'
        summaries = []
        for contrib in self.contributions:
            content_preview = str(contrib.content)[:200]
            summaries.append(f'- {contrib.persona_id.title()}: {content_preview}')
        return '\n'.join(summaries)

class PanelResponse(BaseModel):
    question_id: str = Field(..., description='ID of the question being answered')
    answer: str = Field(..., description='The synthesized answer')
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description='Overall confidence in the answer')
    key_points: list[str] = Field(default_factory=list, description='Main points from the answer')
    sources: list[str] = Field(default_factory=list, description='Sources consulted')
    caveats: list[str] = Field(default_factory=list, description='Important caveats or limitations')
    dissenting_views: list[str] = Field(default_factory=list, description='Alternative views not adopted')
    contributions_summary: dict[str, str] = Field(default_factory=dict, description="Summary of each persona's contribution")
    citations: list[dict[str, Any]] = Field(default_factory=list, description='Source citations as dicts')

    @classmethod
    def from_citations(cls, question_id: str, answer: str, confidence: float, citations: list[SourceCitation], **kwargs: Any) -> 'PanelResponse':
        citation_dicts = [{'type': c.type, 'reference': c.reference, 'excerpt': c.excerpt, 'relevance': c.relevance, 'line_range': c.line_range} for c in citations]
        return cls(question_id=question_id, answer=answer, confidence=confidence, citations=citation_dicts, **kwargs)

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description='The question to ask')
    related_logs: list[dict[str, Any]] = Field(default_factory=list, description='Optional related log entries')

class QuestionResponse(BaseModel):
    question: str = Field(..., description='The original question')
    question_type: str = Field(..., description='Classified question type')
    response: PanelResponse = Field(..., description="The panel's response")

class QAFeedbackRequest(BaseModel):
    qa_id: str = Field(..., description='Q&A session ID')
    helpful: bool = Field(..., description='Whether answer was helpful')
    feedback_text: str | None = Field(default=None, description='Optional feedback text')