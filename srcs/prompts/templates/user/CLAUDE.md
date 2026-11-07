# User Prompts Directory

This directory contains user prompts (task templates) for each investigation phase.

## Contents

- **`hypothesis_generation.md`** - Phase 1: Generate hypotheses
- **`evidence_query.md`** - Phase 2: Generate evidence queries
- **`causal_chain.md`** - Phase 3: Build causal chains (basic)
- **`causal_chain_with_evidence.md`** - Phase 3: Build chains (with evidence list)
- **`adversarial_review.md`** - Phase 4: Generate challenges
- **`outcome_assessment.md`** - Phase 5: Assess outcome
- **`final_synthesis.md`** - Phase 6: Synthesize results
- **`prior_knowledge_summary.md`** - Phase 0: Summarize prior knowledge
- **`pattern_extraction.md`** - Phase 7: Extract patterns
- **`call_graph_summary.md`** - Phase 0: Summarize call graphs

## How It Works

User prompts are templates with `{placeholder}` values filled at runtime:

```python
template = loader.get_user_prompt("hypothesis_generation")
prompt = template.format(
    error_message="...",
    context_logs="...",
    prior_knowledge="..."
)
```

Prompts can include artifact schemas: `{include:artifacts/schemas/hypothesis}`

## Further Reading

For complete documentation including:
- All prompts with their placeholders
- Input/output specifications
- Writing effective user prompts

**Read: [PROMPTS.md](PROMPTS.md)**
