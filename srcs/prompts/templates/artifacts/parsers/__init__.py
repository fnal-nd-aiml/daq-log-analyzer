"""LLM response parsers for artifact creation.

This module provides parsers for converting LLM responses into
domain models and WorkBinder artifacts. Each parser handles a
specific artifact type with two-stage conversion:

1. LLM Response -> Domain Model (for investigation pipeline)
2. Domain Model -> WorkBinder Artifact (for persistence)

Parsers:
- MergedTimelineParser: Parse timeline extraction responses (Phase -1)
- HypothesisParser: Parse hypothesis generation responses (Phase 1)
- EvidenceQueryParser: Parse evidence query responses (Phase 2)
- CausalChainParser: Parse causal chain construction responses (Phase 3)
- ChallengeParser: Parse adversarial review responses (Phase 4)
- ConclusionParser: Parse synthesis responses (Phase 6)

JSON Utilities:
- extract_json: Extract JSON from LLM responses
- fix_json: Repair common JSON formatting issues
- parse_json_response: Parse and validate JSON against a model
"""

from .base import BaseParser
from .boardreader_identification import (
    BoardReaderIdentificationParser,
    BoardReaderIdentificationResponse,
)
from .causal_chain import CausalChainParser, ChainResponse, ChainStepItem
from .challenge import ChallengeItem, ChallengeParser, ChallengeResponse
from .conclusion import (
    ConclusionItem,
    ConclusionParser,
    ConclusionResponse,
    KeyFileItem,
    SubCauseItem,
)
from .evidence import EvidenceQueryParser, QueryItem, QueryResponse
from .hypothesis import HypothesisItem, HypothesisParser, HypothesisResponse
from .json_utils import extract_json, fix_json, parse_json_response
from .log_bundle import LogBundleParser, LogBundleResponse
from .merged_timeline import MergedTimelineParser, TimelineResponse

__all__ = [
    # Base
    "BaseParser",
    # Boardreader identification parser (Phase -1)
    "BoardReaderIdentificationParser",
    "BoardReaderIdentificationResponse",
    # JSON utilities
    "extract_json",
    "fix_json",
    "parse_json_response",
    # Merged timeline parser (Phase -1)
    "MergedTimelineParser",
    "TimelineResponse",
    # Hypothesis parser (Phase 1)
    "HypothesisParser",
    "HypothesisItem",
    "HypothesisResponse",
    # Evidence parser (Phase 2)
    "EvidenceQueryParser",
    "QueryItem",
    "QueryResponse",
    # Causal chain parser (Phase 3)
    "CausalChainParser",
    "ChainStepItem",
    "ChainResponse",
    # Challenge parser (Phase 4)
    "ChallengeParser",
    "ChallengeItem",
    "ChallengeResponse",
    # Conclusion parser (Phase 6)
    "ConclusionParser",
    "ConclusionItem",
    "ConclusionResponse",
    "SubCauseItem",
    "KeyFileItem",
    # Log bundle parser (Phase -1)
    "LogBundleParser",
    "LogBundleResponse",
]
