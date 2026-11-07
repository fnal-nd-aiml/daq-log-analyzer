# System Prompts Directory

This directory contains system prompts that define persona identities for each investigation phase.

## Contents

- **`base.md`** - Shared domain knowledge (artdaq components, error categories, evidence principles)
- **`archivist.md`** - Phase 0: Prior knowledge retrieval
- **`theorist.md`** - Phase 1: Hypothesis generation
- **`detective.md`** - Phase 2: Evidence seeking
- **`logician.md`** - Phase 3: Causal chain construction
- **`skeptic.md`** - Phase 4: Adversarial review
- **`judge.md`** - Phase 5: Outcome assessment
- **`synthesizer.md`** - Phase 6: Final synthesis
- **`learner.md`** - Phase 7: Pattern extraction
- **`coordinator.md`** - Panel orchestration (for Q&A mode)
- **`qa/`** - Q&A mode variants

## How It Works

Each persona prompt contains `{base_knowledge}` placeholder, which is replaced with `base.md` content at load time.

```python
loader = PromptLoader()
system_prompt = loader.get_system_prompt("theorist")
# Returns theorist.md with {base_knowledge} expanded
```

## Further Reading

For complete documentation including:
- All persona definitions with responsibilities
- Writing effective system prompts
- Common patterns and examples

**Read: [PROMPTS.md](PROMPTS.md)**
