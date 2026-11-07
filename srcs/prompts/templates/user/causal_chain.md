TASK: Build explicit causal chain from root cause to observed error.

HYPOTHESIS: {hypothesis}
EVIDENCE: {evidence}

Build a chain where each step:
1. States a claim (A causes B)
2. Explains the mechanism (how A causes B)
3. Cites supporting evidence
4. Notes if it's an assumption

Chain must end at the observed error.

{include:artifacts/schemas/causal_chain_step}

Respond with ONLY valid JSON (no markdown code blocks):
{{"steps": [...]}}
