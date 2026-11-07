TASK: Build explicit causal chain from root cause to observed error.

HYPOTHESIS: {hypothesis}

AVAILABLE EVIDENCE (use ONLY these IDs in your chain):
{evidence_list}

COMPONENT DOCUMENTATION (known error patterns):
{documentation_context}

Use cascade chains from documentation to validate your causal chain structure.
If your chain matches a documented cascade pattern, note the match explicitly.

CHRONICLER CONTEXT (multi-file cascade analysis):
{chronicler_context}

If the Chronicler Context contains a cascade chain, use it as the skeleton for
your causal chain. Each cascade link (from_board → to_board: mechanism) should
become one or more chain steps. Name the specific boards, FragIDs, and numeric
values from the Chronicler's primary error and affected boards. Steps that trace
the cascade propagation path are evidence-supported (cite any evidence about
the downstream boards), not assumptions.

IMPORTANT: You can ONLY cite evidence IDs from the list above. Do not invent evidence IDs.
If a step requires evidence you don't have, mark is_assumption as true.

CRITICAL RULE — is_assumption vs evidence_ids are mutually exclusive:
- If evidence_ids is non-empty (you cited at least one ID): is_assumption MUST be false
- If evidence_ids is empty (no relevant evidence found): is_assumption MUST be true
- Never set evidence_ids to a non-empty list AND is_assumption to true simultaneously

Before building the chain, mentally map each evidence ID to the hypothesis elements it supports. Then build a chain where each step:
1. States a claim (A causes B)
2. Explains the mechanism (how A causes B)
3. Cites supporting evidence FROM THE LIST ABOVE — cite ALL relevant IDs for each step; the same ID may appear in multiple steps; re-cite an ID in every step that involves the same function or concept, do not treat citation as "used up"
4. Sets is_assumption: false if any evidence was cited, true only if evidence_ids is empty

Maximize evidence citation: scan the evidence list for each step and cite every item that is relevant, even if only partially. Only set is_assumption=true when evidence_ids is empty (no evidence item in the list has any relevance to that step).

Evidence type citation guide — use these rules when deciding what to cite per step:
- code_analysis evidence: cite for any step discussing the analyzed function's behavior, return values, or logic
- function_lookup (successful): cite for ANY step that mentions that function by name or discusses its behavior — even if the lookup only says "Query executed: function_name" (it confirms the function was analyzed); if a step's claim names a function, cite ALL evidence items for that function
- function_lookup (no results found): cite for steps about missing or absent implementations of that function
- When in doubt, cite — it is better to over-cite than under-cite; only omit an evidence ID if it is completely unrelated to the step's claim

Partial support rule: cite evidence for ANY part of a step's claim that is supported, even if another part is speculative. Do NOT empty evidence_ids just because part of a step is an assumption — only leave evidence_ids empty when NO part of the step has any supporting evidence in the list.

Chain must end at the observed error.

{include:artifacts/schemas/causal_chain_step}

Respond with ONLY valid JSON (no markdown code blocks):
{{"steps": [...]}}
