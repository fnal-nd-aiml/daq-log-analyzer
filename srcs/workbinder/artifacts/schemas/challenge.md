## Challenge Artifact

A challenge raised during adversarial review.

### Fields

- `type` (string, required): One of logical_flaw, weak_evidence, alternative, missing
- `content` (string, required): Specific challenge description
- `severity` (string, required): One of HIGH, MEDIUM, LOW

### JSON Format

```json
{
    "type": "logical_flaw|weak_evidence|alternative|missing",
    "content": "Specific description of the challenge",
    "severity": "HIGH|MEDIUM|LOW"
}
```

### Challenge Types

- **logical_flaw**: Problems with the causal reasoning chain
- **weak_evidence**: Evidence doesn't actually support claims
- **alternative**: Alternative explanations for the evidence
- **missing**: Evidence that should be gathered

### Severity Guide

- **HIGH**: Conclusion likely wrong (evidence contradicts, chain impossible, alternative more likely)
- **MEDIUM**: Conclusion needs strengthening (evidence circumstantial, gaps fillable)
- **LOW**: Minor improvement possible (interpretation varies, non-critical assumptions)
