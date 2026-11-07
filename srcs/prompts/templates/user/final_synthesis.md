# Final Investigation Synthesis

Synthesize the complete investigation into a clear, actionable report.

## Investigation Overview

Investigation ID: {investigation_id}
Trigger Error: {error_message}
Component: {error_component}
Started: {started_at}
Duration: {duration}

## Outcome

{outcome}
Confidence: {confidence}

## Candidate Root Causes (ranked by score)

{hypotheses_ranked}

## Evidence Summary

{evidence_summary}

## Causal Chain

{causal_chain}

## Challenges and Responses

{challenges_summary}

## Source Code Locations

{source_locations}

## Numeric Analysis (from Phase 0)

{numeric_context}

## Code Context (from Phase 0)

{code_context}

## Evidence Gaps (from Judge)

{judge_evidence_gaps}

## Unmet Criteria (from Judge)

{judge_criteria_not_met}

## Component Documentation (from data/docs/)

{documentation_context}

## Chronicler Context (multi-file analysis)

{chronicler_context}

## Task

Create the final investigation report that includes:

1. **Executive Summary**: 2-3 sentence overview for quick understanding

2. **Root Cause Explanation**: Clear, technical explanation of what went wrong and why
   Do NOT simply accept the highest-ranked hypothesis. Cross-reference each candidate
   against the evidence summary, numeric analysis, and code context. A lower-ranked
   hypothesis with stronger evidence alignment should be preferred over a higher-ranked
   hypothesis whose score comes from unverified similar cases.
   You MUST base this on the evidence provided above. Do NOT infer or fabricate
   code-level behavior not present in the evidence. If numeric analysis is available,
   reference the specific values. If code context is available, cross-reference
   control flow conditions against numeric values to verify the root cause.

   **SPECIFICITY REQUIREMENTS** (do NOT produce vague descriptions):
   - The root cause MUST reference specific numeric values from the Trigger Error
     above (e.g., returned=128612, header=160016) and the Numeric Analysis section
   - The root cause MUST name the specific device, board, or FragID from the trigger
     error and Chronicler Context when available
   - The root cause MUST name the specific code mechanism (variable names, conditions,
     function names) from the Code Context and Evidence sections
   - The root cause MUST state the specific data flow problem (e.g., "upstream data
     arrived 500us after the 100us request window closed") rather than vague phrases
     like "a stall in the pipeline" or "a delay in processing"
   - If the error involves a timeout or buffer, state the exact timeout value and
     what exceeded it

   **CASCADE SYNTHESIS** (when Chronicler Context contains a cascade chain):
   - The root cause MUST name the primary failure device from the Chronicler's
     primary_error (board name, FragID, host)
   - The root cause description MUST include the cascade propagation path: how the
     primary failure caused downstream effects on other boards
   - Hypotheses that name only a generic category ("data corruption", "size mismatch")
     without identifying the primary device and cascade mechanism are INSUFFICIENT —
     prefer hypotheses that name the specific device and failure mode even if they
     have a lower score
   - The causal narrative MUST trace the cascade from origin through each affected
     board, not just describe the primary error in isolation

   **TRIGGER ERROR ANALYSIS**: Parse the Trigger Error message above and extract:
   - Device/board identifiers (FragID, component name)
   - Numeric values (sizes, counters, timestamps) and their relationships
   - The specific comparison that failed (e.g., returned vs header)
   These MUST appear in the root cause description with their exact values.

3. **Causal Narrative**: Step-by-step explanation of how the root cause led to the observed error

4. **Evidence Highlight**: The most important evidence that supports the conclusion

5. **Debugging Steps**: Specific, actionable steps the user should take to:
   - Verify the diagnosis
   - Fix the issue
   - Prevent recurrence

   **DEBUGGING STEP REQUIREMENTS** (do NOT produce generic checklists):
   - Each step MUST reference specific code locations, variable names, or function
     calls from the evidence and code context sections
   - Steps like "check the logs" or "review configuration" are NOT acceptable without
     specifying WHICH logs, WHICH configuration parameters, and WHERE in the code
   - Include the specific file paths and line numbers from the Source Code Locations
     section when available

6. **Caveats**: Any limitations, uncertainties, or alternative explanations

7. **Confidence Assessment**: Final confidence level with explanation

   **CONFIDENCE ALIGNMENT**: The Judge has already determined the investigation
   outcome as {outcome}. Your confidence assessment MUST be consistent with this
   outcome. CONFIDENT outcomes should have confidence level "high". PROBABLE
   should be "medium". UNCERTAIN should be "low". Do NOT contradict the Judge's
   outcome with an inconsistent confidence level.

**IMPORTANT — UNCERTAIN outcome handling**: If the outcome is UNCERTAIN, the response
JSON format is different (see schema below). You MUST output `discrimination_needed`
(not `root_cause` or `debugging_steps`). Each `discrimination_needed` entry must name
the two competing hypotheses AND the specific test/evidence that would distinguish them.
Example: `"Need evidence to distinguish: buffer misconfiguration vs optical link corruption
— check hardware status return codes and review error messages from the
board reader logs"`.

## Response Format

{include:artifacts/schemas/synthesis_response}
