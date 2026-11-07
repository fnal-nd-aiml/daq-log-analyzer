TASK: Generate root cause hypotheses for this error.

ERROR:
- Message: {error_message}
- Component: {error_component}
- Function: {error_function}
- Time: {error_timestamp}

## ISSUE DESCRIPTION (HIGHEST WEIGHT — use this as primary context)
{chronicler_context}

## PRIOR CASE INTELLIGENCE
{prior_case_intelligence}

## Code Analysis Context
{code_context}

## CONTEXT LOGS (before error)
{context_logs}

## Supporting Prior Knowledge
{prior_knowledge}

## CODE HINT PRIORITY (CRITICAL)

The PRIOR_KNOWLEDGE section may include CODE HINTS extracted from source code.
These are developer-written diagnostic comments that explain error causes, such as:
- "This is most likely caused by X"
- "This error occurs when Y happens"
- "Check Z first - it's the most common cause"

**Developer comments are AUTHORITATIVE evidence.** They represent the knowledge of
engineers who wrote and debugged this code. Code hints should be STRONGLY PRIORITIZED
over LLM speculation because:
1. Developers have direct knowledge of common failure modes
2. Comments often capture hard-won debugging experience
3. They reflect understanding of system-specific behavior
4. They are placed at the exact location where the error occurs

## EXPLICIT CAUSAL STATEMENTS (HIGHEST PRIORITY)

When you see explicit developer explanations like:
- "This is most likely caused by..."
- "This happens when..."
- "The problem is..."
- "Check X first..."

**DO NOT generate competing fresh hypotheses.** Instead:
1. Assign the explicit cause a prior of **0.90-0.95** (near-definitive)
2. Generate at most 1-2 alternative hypotheses with lower priors (0.1-0.2)
3. Focus your alternatives on DIFFERENT failure modes, not variations of the same cause

Example: If code says "This is most likely caused by a problem with the Fragment Generator":
- CORRECT: Assign "Fragment Generator problem" prior=0.92, add one alternative like "timing issue" prior=0.15
- WRONG: Generate 5 variations like "FragmentGenerator null", "Fragment creation failed", "Generator error"

**If a code hint directly explains the error cause, assign it a prior of 0.90+ for explicit
causal statements, or 0.7-0.85 for general diagnostic comments.**

When generating hypotheses from code:
1. Look for error handling patterns that match the error message
2. Trace data flow from callers to the error point
3. Identify conditions that could make pointer/data invalid
4. Consider what state changes in callers affect this code
5. Check for missing validation, null checks, or bounds checks
6. **TREAT developer causal comments as AUTHORITATIVE - do not dilute with similar hypotheses**

IMPORTANT: If multiple SOURCE LOCATIONS are listed above, this error message appears in
multiple places in the codebase. You MUST consider ALL candidate locations when generating
hypotheses - the error could originate from any of them. Generate hypotheses that cover
the different code paths where this message is logged. Use the function signatures and
call graph information to understand the context of each location.

Generate hypotheses as JSON array.

{include:artifacts/schemas/hypothesis}

Respond with ONLY valid JSON (no markdown code blocks):
{{"hypotheses": [...]}}
