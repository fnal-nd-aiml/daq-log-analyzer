Evaluate the following upstream investigation artifacts against the hypotheses below.
For each artifact that contains useful information, produce an evidence assessment.

## Hypotheses

{hypotheses}

## Upstream Artifacts

{artifact_text}

## Your Task

For each artifact that is relevant to any hypothesis, produce an evidence assessment.
Consider:
- Source code: control flow, conditions, bounds checks, error handling paths
- Call graphs: upstream data flow, error propagation paths
- Function summaries: purpose, mechanism, data flow, error paths
- Findings: numeric analysis, pattern observations
- Log bundles: cascade chain, affected boards, error timeline
- Error context: trigger error message, surrounding log lines

Respond with ONLY valid JSON (no markdown code blocks):
{{"assessments": [
  {{
    "artifact_id": "<id of the artifact being assessed>",
    "hypothesis_id": "<id of the hypothesis this assessment targets>",
    "relationship": "supports" | "contradicts" | "neutral",
    "strength": "STRONG" | "MODERATE" | "WEAK",
    "reasoning": "<2-4 sentences explaining the assessment with specific citations>"
  }}
]}}

Rules:
- Only include assessments where you have a clear reason to support or contradict
- Cite specific details: line numbers, variable names, conditions, numeric values
- An artifact can produce multiple assessments (one per relevant hypothesis)
- Prefer fewer, higher-quality assessments over many weak ones
- If an artifact is irrelevant to all hypotheses, skip it
