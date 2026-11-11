## Hypothesis Artifact

A root cause hypothesis with probability estimate.

### Fields

- `description` (string, required): Clear description of the root cause
- `category` (string, required): One of hardware, software, configuration, timing, resource, unknown
- `prior` (float, required): Probability estimate 0.0-1.0 based on evidence strength
- `confirming_evidence` (string, required): What would confirm this hypothesis
- `refuting_evidence` (string, required): What would refute this hypothesis

### JSON Format

```json
{
    "description": "Clear description of the root cause",
    "category": "hardware|software|configuration|timing|resource|unknown",
    "prior": 0.0,
    "confirming_evidence": "What would confirm this hypothesis",
    "refuting_evidence": "What would refute this hypothesis"
}
```
