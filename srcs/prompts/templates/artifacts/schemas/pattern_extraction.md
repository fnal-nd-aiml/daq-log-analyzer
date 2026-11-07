## Pattern Extraction Artifact

Patterns extracted from a completed investigation for future learning.

### Fields

- `error_pattern` (object, required): Generalizable error template
  - `signature` (string): Component:function pattern
  - `message_template` (string): Error message with {placeholders}
  - `contextual_indicators` (array): Context clues
  - `false_positive_risk` (string): low, medium, or high
- `root_cause_pattern` (object, required): Root cause template
  - `description_template` (string): Description with {placeholders}
  - `category` (string): configuration, hardware, timing, resource, or software
  - `confirming_evidence` (array): Evidence types that confirm
  - `refuting_evidence` (array): Evidence that would contradict
- `evidence_patterns` (array, required): Useful evidence patterns
  - `type` (string): log, code, config, or dataflow
  - `query_template` (string): How to find this evidence
  - `strength` (string): STRONG, MODERATE, or WEAK
  - `usefulness_score` (float): 0.0-1.0
- `strategy_recommendations` (object, required): Investigation strategy
  - `preferred_approach` (string): code-centric, log-centric, or hybrid
  - `key_queries` (array): Important queries
  - `shortcuts` (array): Useful shortcuts
  - `pitfalls` (array): Pitfalls to avoid
- `calibration` (object, required): Confidence calibration data
  - `stated_confidence` (float): Original confidence
  - `actual_accuracy` (string): correct, incorrect, or unknown
  - `calibration_adjustment` (string): increase, decrease, or maintain
  - `sample_size_note` (string): Generalizability note
- `lessons_learned` (array of strings, required): Key takeaways

### JSON Format

```json
{
    "error_pattern": {
        "signature": "component:function pattern",
        "message_template": "error message with {placeholders}",
        "contextual_indicators": ["indicator 1", "indicator 2"],
        "false_positive_risk": "low|medium|high"
    },
    "root_cause_pattern": {
        "description_template": "description with {placeholders}",
        "category": "configuration|hardware|timing|resource|software",
        "confirming_evidence": ["evidence type 1"],
        "refuting_evidence": ["evidence that would contradict"]
    },
    "evidence_patterns": [
        {
            "type": "log|code|config|dataflow",
            "query_template": "how to find this evidence",
            "strength": "STRONG|MODERATE|WEAK",
            "usefulness_score": 0.0
        }
    ],
    "strategy_recommendations": {
        "preferred_approach": "code-centric|log-centric|hybrid",
        "key_queries": ["query 1", "query 2"],
        "shortcuts": ["shortcut 1"],
        "pitfalls": ["pitfall to avoid"]
    },
    "calibration": {
        "stated_confidence": 0.0,
        "actual_accuracy": "correct|incorrect|unknown",
        "calibration_adjustment": "increase|decrease|maintain",
        "sample_size_note": "note about generalizability"
    },
    "lessons_learned": ["lesson 1", "lesson 2"]
}
```
