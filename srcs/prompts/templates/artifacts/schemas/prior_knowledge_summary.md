## Prior Knowledge Summary Artifact

Summary of prior knowledge retrieved for an investigation.

### Fields

- `relevance_assessment` (object, required): Relevance of each knowledge type
  - `patterns` (string): high/medium/low with explanation
  - `similar_cases` (string): high/medium/low with explanation
  - `source_locations` (string): high/medium/low with explanation
- `key_insights` (array of strings, required): Important insights from prior knowledge
- `recommended_focus_areas` (array of strings, required): Where investigation should focus
- `data_flow_summary` (string, required): Explanation of data flow around error
- `overall_confidence` (string, required): high, medium, or low
- `confidence_reasoning` (string, required): Why this confidence level

### JSON Format

```json
{
    "relevance_assessment": {
        "patterns": "high|medium|low with explanation",
        "similar_cases": "high|medium|low with explanation",
        "source_locations": "high|medium|low with explanation"
    },
    "key_insights": ["insight 1", "insight 2"],
    "recommended_focus_areas": ["focus area 1", "focus area 2"],
    "data_flow_summary": "explanation of data flow around error",
    "overall_confidence": "high|medium|low",
    "confidence_reasoning": "explanation"
}
```
