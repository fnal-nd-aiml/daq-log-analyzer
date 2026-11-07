# Parsers Module

## Overview

The parsers module provides a unified library for parsing LLM responses into domain models and WorkBinder artifacts. It consolidates scattered parsing logic from agent modules and LLM providers into a single, reusable location.

## Module Structure

| File | Purpose |
|------|---------|
| `__init__.py` | Export all parsers and utilities |
| `base.py` | BaseParser abstract base class |
| `json_utils.py` | JSON extraction and repair utilities |
| `merged_timeline.py` | MergedTimelineParser for Phase -1 |
| `hypothesis.py` | HypothesisParser for Phase 1 |
| `evidence.py` | EvidenceQueryParser for Phase 2 |
| `causal_chain.py` | CausalChainParser for Phase 3 |
| `challenge.py` | ChallengeParser for Phase 4 |
| `conclusion.py` | ConclusionParser for Phase 6 |

## Two-Stage Conversion Pattern

All parsers implement a two-stage conversion pattern:

```
LLM Response JSON
       │
       ▼ parse_llm_response()
LLM Response Model (HypothesisResponse, QueryResponse, etc.)
       │
       ▼ to_domain_model()
Domain Model (Hypothesis, EvidenceItem, CausalChain, Challenge)
       │
       ▼ to_artifact()
WorkBinder Artifact (HypothesisArtifact, EvidenceArtifact, etc.)
```

This separation:
1. Maintains backward compatibility with existing agent code
2. Preserves fields that were previously discarded (category, confirming/refuting evidence)
3. Handles field name mapping (type → challenge_type, evidence → evidence_ids)
4. Enables artifact storage without changing agent logic

## Key Classes

### JSON Utilities

```python
from srcs.workbinder.artifacts.parsers import extract_json, fix_json, parse_json_response

# Extract JSON from LLM response (handles markdown blocks)
json_str = extract_json(llm_response)

# Fix common JSON issues (trailing commas, unquoted keys)
fixed = fix_json(malformed_json)

# Parse directly to Pydantic model
result = parse_json_response(llm_response, ResponseModel)
```

### MergedTimelineParser

Parses timeline extraction responses from Phase -1 (Chronicler). Handles resilient
parsing of LLM output including bare JSON arrays, wrong field names (mapped via aliases),
and backward compatibility for old message_header/message_body split.

```python
from srcs.workbinder.artifacts.parsers import MergedTimelineParser, TimelineResponse

parser = MergedTimelineParser()

# Parse LLM response (never raises, returns empty TimelineResponse on failure)
response = parser.parse_llm_response(raw_json)

# Convert entries to domain models
entries = [parser.to_domain_model(e) for e in response.entries]

# Convert to artifact
artifact = parser.to_artifact(entries, "Chronicler", phase=-1)

# Static helpers for direct use
normalized = MergedTimelineParser.normalize_entry(raw_entry_dict)
formatted = MergedTimelineParser.format_timeline(response.entries)

# Convenience method
response, entries = parser.parse_and_store(raw_json)
```

Note: Unlike other parsers, `to_artifact()` takes a **list** of `MergedTimelineEntry`
(the full collection) since the artifact wraps the collection with summary stats.

### HypothesisParser

Parses hypothesis generation responses from Phase 1.

```python
from srcs.workbinder.artifacts.parsers import HypothesisParser, HypothesisItem, HypothesisResponse

parser = HypothesisParser()

# Parse LLM response
response = parser.parse_llm_response(raw_json)

# Convert items to domain models
for item in response.hypotheses:
    hypothesis = parser.to_domain_model(item, source_prefix="fresh", max_prior=0.3)

    # Convert to artifact for storage
    artifact = parser.to_artifact(hypothesis, "Theorist", phase=1, rank=0)

# Convenience method
hypotheses = parser.parse_and_convert(raw_json, exclude_descriptions=seen)
```

### EvidenceQueryParser

Parses evidence query responses from Phase 2.

```python
from srcs.workbinder.artifacts.parsers import EvidenceQueryParser, QueryItem, QueryResponse

parser = EvidenceQueryParser()

# Parse to query dictionaries for execution
queries = parser.parse_to_queries(raw_json)

# After query execution, convert results to artifacts
artifact = parser.to_artifact(evidence_item, "Detective", phase=2)
```

### CausalChainParser

Parses causal chain responses from Phase 3. Handles field mapping:
- `evidence` (LLM) → `evidence_ids` (domain model)

```python
from srcs.workbinder.artifacts.parsers import CausalChainParser, ChainResponse, ChainStepItem

parser = CausalChainParser()

response = parser.parse_llm_response(raw_json)
chain = parser.to_domain_model(response, hypothesis_id="hyp-001")
artifact = parser.to_artifact(chain, "Logician", phase=3)
```

### ChallengeParser

Parses adversarial review responses from Phase 4. Handles field mapping:
- `type` (LLM) → `challenge_type` (domain model)
- `missing` → `missing_evidence` (normalization)

```python
from srcs.workbinder.artifacts.parsers import ChallengeParser, ChallengeItem, ChallengeResponse

parser = ChallengeParser()

challenges = parser.parse_and_convert(raw_json)
for challenge in challenges:
    artifact = parser.to_artifact(
        challenge, "Skeptic", phase=4, target_hypothesis_id="hyp-001"
    )
```

### ConclusionParser

Parses synthesis responses from Phase 6. Converts LLM conclusion output to `InvestigationConclusion` domain model and `ConclusionArtifact`.

```python
from srcs.workbinder.artifacts.parsers import (
    ConclusionParser,
    ConclusionItem,
    ConclusionResponse,
    SubCauseItem,
    KeyFileItem,
)

parser = ConclusionParser()

# Parse LLM response
response = parser.parse_llm_response(raw_json)

# Convert to domain model (with optional calibrated confidence)
conclusion = parser.to_domain_model(
    response.conclusion,
    calibrated_confidence=0.85,
)

# Convert to artifact for storage
artifact = parser.to_artifact(
    conclusion,
    "Synthesizer",
    phase=6,
    outcome="CONFIDENT",
    llm_request_id="req-123",
)
```

The `ConclusionItem` model includes:
- `root_cause`: Final root cause determination
- `confidence`: Confidence level (0.0-1.0)
- `caveats`: List of caveats and limitations
- `code_snippet`: Relevant code at error location
- `code_location`: File:line of error
- `sub_causes`: Ranked breakdown of sub-causes (`SubCauseItem`)
- `data_flow`: ASCII visualization of call chain
- `key_files`: Key files to examine (`KeyFileItem`)
- `debugging_steps`: Specific debugging steps

## Field Preservation

The parsers preserve fields that were previously discarded during parsing:

### HypothesisItem Fields
| Field | Description |
|-------|-------------|
| `description` | Hypothesis text |
| `category` | Classification (timing, configuration, etc.) |
| `prior` | Prior probability estimate |
| `confirming_evidence` | Evidence design that would confirm |
| `refuting_evidence` | Evidence design that would refute |

The `category` is incorporated into the source field as `source_prefix:category`.
The `confirming_evidence` and `refuting_evidence` are stored in the domain model
and artifact for use by downstream phases.

## Field Mapping

### MergedTimelineParser
| LLM Field | Domain Field |
|-----------|--------------|
| `type`, `severity` | `level` |
| `msg`, `summary`, `details`, `body` | `message` |
| `file`, `filename` | `source_file` |
| `board` | `board_name` |
| `name`, `source`, `category` | `component` |
| `time`, `ts` | `timestamp` |
| `src_location`, `location` | `source_location` |
| `message_header` + `message_body` | `message` (merged) |

### ChallengeParser
| LLM Field | Domain Field |
|-----------|--------------|
| `type` | `challenge_type` |
| `"missing"` | `"missing_evidence"` |

### CausalChainParser
| LLM Field | Domain Field |
|-----------|--------------|
| `evidence` | `evidence_ids` |

## Usage in Agent Modules

Agent and persona modules import response models from parsers:

```python
# In srcs/persona/chronicler.py
from srcs.workbinder.artifacts.parsers import MergedTimelineParser, TimelineResponse

# In srcs/persona/theorist.py
from srcs.workbinder.artifacts.parsers import HypothesisItem, HypothesisResponse

# In srcs/persona/detective.py
from srcs.workbinder.artifacts.parsers import QueryItem, QueryResponse

# In srcs/persona/logician.py
from srcs.workbinder.artifacts.parsers import ChainStepItem, ChainResponse

# In srcs/persona/skeptic.py
from srcs.workbinder.artifacts.parsers import ChallengeItem, ChallengeResponse

# In srcs/persona/synthesizer.py
from srcs.workbinder.artifacts.parsers import ConclusionItem, ConclusionResponse
```

## Usage in LLM Providers

LLM providers import JSON utilities from parsers:

```python
# In srcs/llm/anthropic.py, ollama.py, openrouter.py
from srcs.workbinder.artifacts.parsers import extract_json, fix_json
```

## Artifact Parser Coverage

### Artifacts with Parsers

These artifacts are created from LLM responses and have dedicated parsers:

| Artifact Type | Parser | Phase | Description |
|---------------|--------|-------|-------------|
| `MergedTimelineArtifact` | `MergedTimelineParser` | -1 | Chronologically merged timeline from multi-file logs |
| `HypothesisArtifact` | `HypothesisParser` | 1 | Root cause hypotheses from LLM |
| `EvidenceArtifact` | `EvidenceQueryParser` | 2 | Evidence queries and results |
| `CausalChainArtifact` | `CausalChainParser` | 3 | Causal chain reasoning |
| `ChallengeArtifact` | `ChallengeParser` | 4 | Adversarial challenges |
| `ConclusionArtifact` | `ConclusionParser` | 6 | Final synthesis output |

**Note on ConclusionParser:** The `ConclusionParser` is designed for parsing LLM responses
with a specific `ConclusionItem` schema (sub_causes, key_files, debugging_steps). The
`SynthesizerPersona` in `srcs/persona/synthesizer.py` has its own `SynthesisResponse` model
with a different structure (executive_summary, root_cause object, etc.). These serve
different use cases - `ConclusionParser` is for pipeline-based conclusion generation,
while `SynthesizerPersona` handles persona-based LLM synthesis.

### Infrastructure Artifacts (No Parser Needed)

These artifacts are created programmatically during investigation, not from LLM responses:

| Artifact Type | Created By | Purpose |
|---------------|------------|---------|
| `InvestigationStateArtifact` | Coordinator | Track investigation lifecycle |
| `PhaseStateArtifact` | Coordinator | Track phase execution state |
| `FlowConfigArtifact` | Coordinator | Store configuration snapshot |
| `LLMRequestArtifact` | LLM providers | Record LLM requests |
| `LLMResponseArtifact` | LLM providers | Record LLM responses |
| `ErrorContextArtifact` | Archivist | Store triggering error details |
| `SourceLocationArtifact` | Archivist | Error source locations |
| `CallGraphNode` | Archivist/Tools | Call graph data |
| `CodeSnippet` | Archivist/Tools | Source code fragments |
| `Finding` | Any persona | Observations and notes |
| `Annotation` | Any persona | Notes on other artifacts |
| `PersonaContributionArtifact` | Any persona | Persona contributions |

## Dependencies

- `pydantic`: BaseModel for response models
- `srcs.models`: Domain models (Hypothesis, Evidence, etc.)
- `srcs.workbinder.artifacts`: Artifact types for persistence
