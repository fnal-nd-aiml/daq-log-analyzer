# Investigation Outcome Assessment

Evaluate the evidence and determine the investigation outcome.

## Error Being Investigated

```
{error_message}
```

## Hypotheses Summary

{hypotheses_summary}

Top Hypothesis: {top_hypothesis}
Top Score: {top_score}

## Evidence Summary

Total Evidence Items: {evidence_count}
Strong Evidence: {strong_evidence_count}
Moderate Evidence: {moderate_evidence_count}
Weak Evidence: {weak_evidence_count}

Evidence Details:
{evidence_details}

## Causal Chains

{causal_chains_summary}

## Challenges from Adversarial Review

{challenges_summary}

Unresolved HIGH Challenges: {unresolved_high_count}
Unresolved MEDIUM Challenges: {unresolved_medium_count}

NOTE: If there are 3 or more unresolved MEDIUM challenges, this should normally
prevent a CONFIDENT outcome. Multiple unresolved concerns indicate insufficient
rigor even if no single HIGH-severity challenge exists.

## Context Availability

Log files provided: {has_context_logs}
Evidence collection mode: {evidence_mode}

NOTE: For LIMITED-INPUT investigations, adjust thresholds accordingly.
Single strong code/numeric evidence with high hypothesis score can support CONFIDENT.

## Self-Describing Error Recognition

IMPORTANT: Check if the error message is SELF-DESCRIBING. Self-describing errors contain:
- Explicit units (e.g., "10001038 us" = microseconds, "10s" = seconds)
- Mathematical relationships ("X > Y" where both values are given)
- Buffer/window ranges with timestamps
- Function names identifying the failure point

For self-describing errors:
1. The error message itself is STRONG EVIDENCE of the stated facts
2. Challenges about "missing timing evidence" are RESOLVED if times are in the message
3. Timestamp unit concerns are RESOLVED if units are explicit (us, ms, ns)
4. No separate "log trace" is needed to confirm what the error message states

Example: "Time waiting: 10001038 us (> 10000000 us)"
- Unit is EXPLICIT: microseconds (us)
- Relationship is EXPLICIT: actual > threshold
- This IS the timing evidence - no separate trace needed

## Evidence Quality Assessment

Quality Score: {evidence_quality_score}
- Strength: {quality_strength_score}
- Diversity: {quality_diversity_score}
- Coverage: {quality_coverage_score}
- Discrimination: {quality_discrimination_score}

Evidence Types Present: {evidence_types_present}
Evidence Types Missing: {evidence_types_missing}

## Evidence Gap Analysis

{evidence_gap_analysis}

Total Gaps Identified: {evidence_gap_count}
Most Critical Gap: {most_critical_gap}

## Recommended Next Steps (if INSUFFICIENT)

{alternative_paths}

## Task

Apply the decision framework to determine the investigation outcome:

{include:artifacts/enums/outcome_types}

## Response Format

{include:artifacts/schemas/outcome_assessment}
