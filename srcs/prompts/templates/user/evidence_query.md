TASK: Identify queries to discriminate between hypotheses.

## Investigation Mode: {investigation_mode}
{mode_specific_guidance}

## Already Analyzed (DO NOT REQUEST AGAIN):
{analyzed_functions}

## Query Type Effectiveness:
{query_effectiveness}

HYPOTHESES:
{hypotheses}

CURRENT EVIDENCE:
{evidence}

## Code Hint Validation Priority

If hypotheses include code_hint sources (e.g., source starts with "code_hint:"),
these represent developer-written diagnostic explanations. Generate queries specifically to:

1. **Validate the mechanism** described in the code hint - look up the functions/classes
   mentioned to confirm the causal pathway exists
2. **Check code path execution** - verify the code path containing the hint is actually
   executed in this error scenario (call graph, callers)
3. **Find confirming evidence** - look for code patterns that support the hint's explanation
4. **Test alternatives** - only if the code hint seems incomplete, check alternatives

Code hints should be validated with 2-3 targeted queries before moving to other hypotheses.

## Upstream Tracing for Data Flow Errors

When investigating timeout, buffer, or data flow errors:
1. **Trace upstream callers** - Use function_lookup to find functions that CALL the error function
2. **Trace data producers** - Look for functions that produce/send the data being waited on
3. **Check configuration sources** - Look up timeout/window configuration variables
4. **Examine the data path** - If the error involves waiting for data, trace where data originates

Do NOT stop at the error function. The root cause of timeouts is usually UPSTREAM
in the data production or delivery chain.

## Multi-Board Cascade Validation

If the Chronicler Context below contains a cascade chain, validate each link.

**CRITICAL — Cascade Origin vs Symptom Discrimination:**
Boards marked `secondary_cascade` in the Affected Boards list are cascade *effects*, not root
causes. Evidence from these boards validates the cascade mechanism but CANNOT establish a
competing root cause hypothesis. Only the `primary_failure` board should be investigated as
the potential root cause origin. If a hypothesis names a secondary board's error as the root
cause (e.g., buffer overflow on a downstream board), that hypothesis describes a *symptom*
and must be scored lower than hypotheses targeting the primary_failure board.

**IMPORTANT — ERROR_CONTEXT may differ from primary_failure:**
The ERROR_CONTEXT artifact captures the *trigger* error from the submitted file, which may
be a downstream symptom on a secondary_cascade board. When the Chronicler's primary_error
names a different board than ERROR_CONTEXT, prioritize the Chronicler's primary_failure
board as the root cause origin. Investigate that board first.

Cascade validation steps:

1. **Start with the PRIMARY error board** — the board identified as the cascade origin.
   Generate queries targeting its specific failure mode and key error message.
2. **Validate each cascade link** — for each from_board → to_board link, generate a query
   that confirms the mechanism (e.g., corrupted data from board A causing buffer overflow
   in board B). Use component_logs for each board in the chain.
3. **Check per-board failure modes** — if boards share the same failure mode, this suggests
   a common cause (e.g., shared hardware). If failure modes differ along the chain, this
   supports cascade propagation rather than independent failures.
4. **Discriminate hardware vs software** — when the cascade originates from a hardware board
   (e.g., CAEN digitizer errors, wrong event size, read returns -1), generate queries that
   specifically test whether the failure is hardware/firmware (device-level errors) vs
   software (configuration, buffer management, race conditions).
5. **Detect hardware failure progression** — when the primary failure board shows a
   progression of worsening errors over time (e.g., corrupted data → driver read errors →
   register read failures → unphysical sensor readings), this strongly indicates
   hardware/firmware failure rather than software/configuration. Generate time_window
   queries around the primary board to trace this progression and confirm the board became
   unresponsive after the initial error.
6. **Use investigation clues directly** — if the Chronicler provided investigation clues
   with `suggested_search` values, use those exact search terms as query targets for
   log_source or code_search queries.

If no cascade chain is present in the Chronicler Context, skip this section.

## Cascade Synthesis

After validating cascade links, synthesize findings into a unified root cause:
- The root cause is the **primary failure board's specific failure**, not a generic category
- Name the board, FragID, failure type, and key numeric values
- Downstream effects (buffer overflows, counter resets, empty fragments) are symptoms
- Generate queries that confirm the primary board's failure mechanism rather than
  investigating symptoms as independent root causes

## Hypothesis Quality Filter

Before generating queries, assess hypothesis quality. **Skip** hypotheses that:
- Contain the full error message text verbatim (just restates the symptom)
- Use generic categories without a specific mechanism ("timing issue causing: <error>")
- Do not name a testable component or failure mode

Focus your queries on hypotheses that propose specific, falsifiable mechanisms.

## Confidence Escalation Signals

Flag these patterns as strong convergence signals (supporting CONFIDENT outcome):
- Hardware failure progression (2+ stages) on the primary board
- Cascade chain where all links validated with matching timestamps
- Numeric evidence consistent across boards (same counter values, same timestamps)
- Code analysis confirms the error path matches the observed log sequence
- Multiple independent evidence types (log + code + numeric) all converge

When you observe 3+ of these, note "EVIDENCE CONVERGENCE: HIGH" in your assessment.

## Component Documentation (from data/docs/)

{documentation_context}

## Upstream Investigation Context

{upstream_context}

## Chronicler Context (multi-file analysis)

{chronicler_context}

## Upstream Artifact Bodies

The following are full verbatim artifacts from upstream investigation phases.
Use these to inform your evidence queries — target specific functions, error paths,
and hypotheses mentioned in these artifacts.

{artifact_context}

What queries would help discriminate between hypotheses?
- Focus on queries that would confirm one hypothesis while refuting another
- Prioritize queries with high discriminating power
- **PRIORITIZE validating code_hint hypotheses first**
- DO NOT request functions listed in "Already Analyzed" above
- SKIP query types marked as ineffective above

{include:artifacts/enums/query_types}

TIPS FOR EFFECTIVE QUERIES:
- For error messages, use log_source with the static text portion (before dynamic values like numbers)
- For C++ errors with "ClassName::functionName()", use function_lookup with the function name
- If error mentions a component, use component_logs to see related activity
- When investigating memory issues, race conditions, or control flow bugs, use
  "full_source": true with function_lookup to see the complete implementation

Generate evidence_queries as JSON array.

{include:artifacts/schemas/evidence_query}

Respond with ONLY valid JSON (no markdown code blocks):
{{"queries": [...]}}
