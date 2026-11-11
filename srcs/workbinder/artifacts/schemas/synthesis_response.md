## Synthesis Response Artifact

Final investigation synthesis and report.

### Fields (CONFIDENT or PROBABLE outcome)

- `executive_summary` (string, required): 2-3 sentence summary
- `root_cause` (object, required): Root cause details
  - `description` (string): Clear description
  - `code_location` (string): File:line if known
  - `mechanism` (string): How it causes the error
- `causal_narrative` (array of strings, required): Step-by-step explanation
- `key_evidence` (array of objects, required): Important evidence items
  - `type` (string): log, code, or config
  - `content` (string): Evidence content
  - `significance` (string): Why this matters
- `debugging_steps` (array of objects, required): Actionable debugging steps
  - `action` (string): What to do
  - `purpose` (string): Why this helps
  - `expected_result` (string): What to look for
- `caveats` (array of strings, required): Limitations and uncertainties
- `confidence` (object, required): Confidence assessment
  - `level` (string): high, medium, or low
  - `raw_score` (float): Uncalibrated score
  - `calibrated_score` (float): Calibrated score
  - `reasoning` (string): Why this confidence level

### Fields (UNCERTAIN outcome)

For UNCERTAIN outcomes, include these fields **instead of** `root_cause`, `causal_narrative`,
`debugging_steps`:

- `executive_summary` (string, required): 2-3 sentence summary explaining why the investigation
  is uncertain and what competing hypotheses remain
- `discrimination_needed` (array of strings, **required**): Each element describes a pair of
  competing hypotheses and the specific evidence needed to distinguish between them.
  Must contain at least one entry when outcome is UNCERTAIN.
  Example: `"Need evidence to distinguish: buffer too small (128KB limit) vs optical link
  corruption — check CAENReadData return code and link status registers"`
- `key_evidence` (array of objects, required): Evidence gathered so far
- `caveats` (array of strings, required): Why the investigation could not reach a definitive conclusion
- `confidence` (object, required): Confidence assessment (level must be "low" for UNCERTAIN)

### JSON Format (CONFIDENT or PROBABLE)

```json
{
    "executive_summary": "2-3 sentence summary",
    "root_cause": {
        "description": "clear description of root cause",
        "code_location": "file:line if known",
        "mechanism": "how it causes the error"
    },
    "causal_narrative": ["Step 1: ...", "Step 2: ..."],
    "key_evidence": [
        {
            "type": "log|code|config",
            "content": "evidence content",
            "significance": "why this matters"
        }
    ],
    "debugging_steps": [
        {
            "action": "what to do",
            "purpose": "why this helps",
            "expected_result": "what to look for"
        }
    ],
    "caveats": ["caveat 1", "caveat 2"],
    "confidence": {
        "level": "high|medium|low",
        "raw_score": 0.0,
        "calibrated_score": 0.0,
        "reasoning": "why this confidence level"
    }
}
```

### JSON Format (UNCERTAIN)

```json
{
    "executive_summary": "2-3 sentence summary explaining uncertainty and competing hypotheses",
    "discrimination_needed": [
        "Need evidence to distinguish: <hypothesis A> vs <hypothesis B> — <what to check>",
        "Need evidence to distinguish: <hypothesis B> vs <hypothesis C> — <what to check>"
    ],
    "key_evidence": [
        {
            "type": "log|code|config",
            "content": "evidence content",
            "significance": "why this matters"
        }
    ],
    "caveats": ["why conclusion is uncertain", "what is still unknown"],
    "confidence": {
        "level": "low",
        "raw_score": 0.0,
        "calibrated_score": 0.0,
        "reasoning": "why this confidence level"
    }
}
```
