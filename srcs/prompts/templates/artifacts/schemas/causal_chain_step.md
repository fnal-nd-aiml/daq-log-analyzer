## Causal Chain Step Artifact

A step in the causal chain from root cause to observed error.

### Fields

- `claim` (string, required): The causal claim (A causes B)
- `mechanism` (string, required): How A actually causes B
- `evidence` (array of strings, required): Evidence IDs supporting this step (from provided list)
- `is_assumption` (boolean, required): True if no evidence supports this step

### JSON Format

```json
{
    "claim": "X causes Y",
    "mechanism": "How X leads to Y",
    "evidence": ["evidence_id_1", "evidence_id_2"],
    "is_assumption": false
}
```

### Notes

- You can ONLY cite evidence IDs from the provided list
- If a step lacks evidence, mark `is_assumption: true` and leave evidence empty
- The chain must end at the observed error
- Each link should explain the mechanism, not just assert causation
