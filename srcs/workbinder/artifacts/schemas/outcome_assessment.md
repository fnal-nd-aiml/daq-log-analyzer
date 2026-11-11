## Outcome Assessment Artifact

Assessment of investigation outcome and sufficiency.

### Fields

- `outcome` (string, required): CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, or INSUFFICIENT
- `confidence_score` (float, required): Numeric confidence 0.0-1.0
- `reasoning` (string, required): Detailed explanation of decision
- `criteria_met` (array of strings, required): Criteria that were met
- `criteria_not_met` (array of strings, required): Criteria that were not met
- `evidence_gaps` (array of strings, required): Gaps in evidence collection
- `unresolved_concerns` (array of strings, required): Concerns not addressed
- `recommendation` (string, required): What to do next based on outcome

### JSON Format

```json
{
    "outcome": "CONFIDENT|PROBABLE|UNCERTAIN|CONTRADICTORY|INSUFFICIENT",
    "confidence_score": 0.0,
    "reasoning": "detailed explanation of decision",
    "criteria_met": ["criterion 1", "criterion 2"],
    "criteria_not_met": ["criterion that was not met"],
    "evidence_gaps": ["gap 1", "gap 2"],
    "unresolved_concerns": ["concern 1"],
    "recommendation": "what to do next based on outcome"
}
```
