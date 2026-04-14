# Pipeline Configuration Specification

Version: 1.0

## Overview

This document defines the YAML configuration syntax for the artdaq Investigation Pipeline. The pipeline is **always driven by configuration** - there is no hardcoded pipeline logic. All investigation flow, phase execution, conditional branching, and runtime behavior is controlled through the `pipeline` section in `config.yaml`.

### Key Principles

1. **Config-First**: The pipeline section in `config.yaml` is required and defines all behavior
2. **Declarative**: Pipeline flow is expressed as data, not code
3. **Flexible**: Phases can be added, removed, reordered, or customized
4. **Extensible**: Custom executors, hooks, and result builders can be registered

---

## Top-Level Structure

```yaml
pipeline:
  # Entry point configuration
  start_at: <phase_id>           # Optional: Phase to start execution (default: first phase)
  skip_phases: [<phase_id>, ...] # Optional: Phases to always skip

  # Phase definitions (required)
  phases:
    - <PhaseConfig>
    - ...

  # Flow control (optional)
  branches: [<BranchConfig>, ...]
  fast_paths: [<FastPathConfig>, ...]

  # Runtime variants (optional)
  variants:
    <variant_name>: <VariantConfig>
    ...

  # Side effect hooks (optional)
  hooks: [<HookConfig>, ...]
```

---

## PhaseConfig

Defines a single phase in the pipeline.

```yaml
- id: <string>                    # Required: Unique phase identifier
  executor: <string>              # Required*: Executor ID (mutually exclusive with panel)
  panel: <PanelConfig>            # Required*: Panel config (mutually exclusive with executor)
  inputs: [<string>, ...]         # Required: Data keys consumed by this phase
  outputs: [<string>, ...]        # Required: Data keys produced by this phase
  config: <object>                # Optional: Executor-specific configuration
  filter: <FilterMap>             # Optional: Input filtering rules
  enabled: <bool | expression>    # Optional: Static or dynamic enable flag (default: true)
  requires: <expression>          # Optional: Runtime guard condition
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | - | Unique identifier for the phase |
| `executor` | string | Yes* | - | Registered executor ID |
| `panel` | PanelConfig | Yes* | - | Multi-executor panel configuration |
| `inputs` | string[] | Yes | - | Data keys required as input |
| `outputs` | string[] | Yes | - | Data keys produced as output |
| `config` | object | No | `{}` | Key-value config passed to executor |
| `filter` | FilterMap | No | - | Input filtering rules |
| `enabled` | bool \| string | No | `true` | Enable/disable phase |
| `requires` | string | No | - | Runtime guard expression |

*Note: Exactly one of `executor` or `panel` must be specified.

### Example

```yaml
- id: evidence_seeking
  executor: detective
  inputs: [hypotheses, prior_knowledge]
  outputs: [evidence, hypotheses]
  config:
    max_iterations: 10
  filter:
    hypotheses:
      condition: "score > 0.2"
      limit: 5
  enabled: true
  requires: "len(hypotheses) > 0"
```

---

## PanelConfig

Configures multi-executor (panel of experts) execution for a phase.

```yaml
panel:
  personas: [<string>, ...]       # Required: List of executor IDs
  execution: <string>             # Optional: "parallel" | "sequential" (default: "sequential")
  aggregation: <string>           # Optional: Result merge strategy (default: "merge")
  timeout: <integer>              # Optional: Timeout in seconds (default: 60)
```

### Aggregation Strategies

| Strategy | Description |
|----------|-------------|
| `merge` | Concatenate lists, merge dicts, first non-None scalar |
| `vote` | Majority voting for categorical outputs |
| `best_score` | Take output from highest-scoring executor |
| `consensus` | Only include items all executors agree on |

### Example

```yaml
- id: hypothesis_generation
  panel:
    personas: [theorist, pattern_matcher, code_analyzer]
    execution: parallel
    aggregation: merge
    timeout: 120
  inputs: [trigger_error, context_logs, prior_knowledge]
  outputs: [hypotheses]
```

---

## FilterConfig

Defines filtering rules for phase inputs.

```yaml
filter:
  <input_key>:
    field: <string>               # Optional: Field name (defaults to input_key)
    condition: <expression>       # Optional: Item-level filter condition
    limit: <integer>              # Optional: Maximum items to pass through
```

### Example

```yaml
filter:
  hypotheses:
    condition: "score > 0.3"
    limit: 3
  evidence:
    condition: "strength == 'STRONG'"
```

---

## BranchConfig

Defines conditional branching after a phase.

```yaml
branches:
  - after: <phase_id>             # Required: Phase after which to evaluate
    condition: <expression>       # Required: Condition to evaluate
    skip_to: <phase_id>           # Required: Target phase if condition is true
```

### Example

```yaml
branches:
  - after: prior_retrieval
    condition: "prior_knowledge.has_high_confidence_pattern()"
    skip_to: synthesis
```

---

## FastPathConfig

Defines fast path conditions for early termination or flow modification.

```yaml
fast_paths:
  - name: <string>                # Required: Human-readable identifier
    after: <phase_id>             # Optional: Phase after which to check (null = always check)
    condition: <expression>       # Required: Trigger condition
    action: <string>              # Required: Action type (see below)
    skip_to: <phase_id>           # Required for action=skip_to
    result_builder: <string>      # Required for action=early_return
    variant: <string>             # Required for action=use_variant
```

### Actions

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `skip_to` | Jump to a later phase | `skip_to` |
| `early_return` | Exit pipeline immediately with built result | `result_builder` |
| `use_variant` | Apply variant config and continue | `variant` |

### Example

```yaml
fast_paths:
  # Pattern match fast path - exit early with cached result
  - name: tier1_pattern_match
    after: prior_retrieval
    condition: "prior_knowledge.has_tier1_pattern()"
    action: early_return
    result_builder: pattern_fast_path

  # Code hint fast path - continue with reduced iterations
  - name: code_hint_fast_path
    after: prior_retrieval
    condition: "prior_knowledge.has_authoritative_code_hint()"
    action: use_variant
    variant: reduced_evidence

  # High confidence skip - jump to synthesis
  - name: high_confidence_skip
    after: hypothesis_generation
    condition: "hypotheses[0].score > 0.9"
    action: skip_to
    skip_to: synthesis
```

---

## VariantConfig

Defines named configuration variants that can be activated by fast paths.

```yaml
variants:
  <variant_name>:
    phase_overrides:
      <phase_id>:
        config:
          <key>: <value>
        enabled: <bool>
        # Other PhaseConfig fields can be overridden
```

### Example

```yaml
variants:
  reduced_evidence:
    phase_overrides:
      evidence_seeking:
        config:
          max_iterations: 3

  thorough:
    phase_overrides:
      evidence_seeking:
        config:
          max_iterations: 20
      adversarial_review:
        enabled: true

  quick:
    phase_overrides:
      causal_chains:
        enabled: false
      adversarial_review:
        enabled: false
      learning:
        enabled: false
```

---

## HookConfig

Defines side-effect actions executed at specific points in the pipeline.

```yaml
hooks:
  - after: <phase_id>             # Execute after phase completes
    action: <string>              # Registered hook action name

  - before: <phase_id>            # Execute before phase starts
    action: <string>

  - on_error: true                # Execute on pipeline error
    action: <string>

  - on_complete: true             # Execute on pipeline completion
    action: <string>
```

### Built-in Hook Actions

| Action | Description |
|--------|-------------|
| `store_investigation` | Persist investigation record to database |
| `store_binder` | Persist work binder artifacts |
| `log_metrics` | Log phase execution metrics |
| `store_failed_investigation` | Store failed investigation for debugging |

### Example

```yaml
hooks:
  - after: synthesis
    action: store_investigation
  - after: synthesis
    action: store_binder
  - on_error: true
    action: store_failed_investigation
```

---

## Expression Syntax

Expressions are used in `condition`, `requires`, and `enabled` fields.

### Supported Operations

| Category | Syntax | Example |
|----------|--------|---------|
| Attribute access | `obj.attr` | `prior_knowledge.matched_patterns` |
| Index access | `list[n]` | `hypotheses[0].score` |
| Comparisons | `>`, `<`, `>=`, `<=`, `==`, `!=` | `score > 0.7` |
| Logical | `and`, `or`, `not` | `a > 0 and b < 10` |
| Boolean literals | `true`, `false` | `enabled == true` |
| Numeric literals | integers, floats | `0.9`, `20` |
| String literals | `"str"` or `'str'` | `source == "pattern"` |
| Length function | `len(x)` | `len(hypotheses) > 0` |
| Method calls | `obj.method()` | `prior.has_tier1_pattern()` |

### Examples

```yaml
# Simple comparison
condition: "score > 0.7"

# Nested attribute access
condition: "hypotheses[0].score > 0.5"

# Logical combination
condition: "len(hypotheses) > 0 and hypotheses[0].score > 0.7"

# Method call
condition: "prior_knowledge.has_authoritative_code_hint()"

# Negation
enabled: "not investigation.skip_learning"
```

---

## Variable Interpolation

Config values can reference external configuration using `${...}` syntax.

### Syntax

```yaml
config:
  key: "${<source>.<path>}"
```

### Sources

| Source | Description |
|--------|-------------|
| `investigation` | InvestigationConfig fields |
| `env` | Environment variables |

### Examples

```yaml
config:
  max_hypotheses: "${investigation.max_hypotheses}"
  max_iterations: "${investigation.max_evidence_iterations}"
  api_key: "${env.ANTHROPIC_API_KEY}"

enabled: "${investigation.enable_auto_learning}"
```

---

## Data Keys Reference

Standard data keys available in the pipeline context.

| Key | Type | Produced By | Description |
|-----|------|-------------|-------------|
| `trigger_error` | Log | Input | The error being investigated |
| `context_logs` | list[Log] | Input | Context logs around error |
| `investigation` | Investigation | Engine | Investigation record |
| `prior_knowledge` | PriorKnowledge | prior_retrieval | Retrieved patterns and similar cases |
| `hypotheses` | list[Hypothesis] | hypothesis_generation | Root cause hypotheses |
| `evidence` | Evidence | evidence_seeking | Gathered evidence |
| `causal_chains` | list[CausalChain] | causal_chains | Reasoning chains |
| `challenges` | list[Challenge] | adversarial_review | Adversarial challenges |
| `outcome` | InvestigationOutcome | outcome_assessment | Assessment result |
| `result` | InvestigationResult | synthesis | Final investigation result |
| `patterns` | list[ErrorPattern] | learning | Learned patterns |

---

## Built-in Executors

| Executor ID | Phase | Description |
|-------------|-------|-------------|
| `archivist` | prior_retrieval | Retrieves patterns, similar cases, source locations |
| `theorist` | hypothesis_generation | Generates root cause hypotheses |
| `detective` | evidence_seeking | Iteratively seeks discriminating evidence |
| `logician` | causal_chains | Builds causal reasoning chains |
| `skeptic` | adversarial_review | Challenges conclusions |
| `judge` | outcome_assessment | Assesses investigation outcome |
| `synthesizer` | synthesis | Synthesizes final result |
| `learner` | learning | Extracts patterns for future use |

---

## Complete Example

```yaml
pipeline:
  # Fast paths for early termination
  fast_paths:
    - name: tier1_pattern_match
      after: prior_retrieval
      condition: "prior_knowledge.has_tier1_pattern()"
      action: early_return
      result_builder: pattern_fast_path

    - name: code_hint_fast_path
      after: prior_retrieval
      condition: "prior_knowledge.has_authoritative_code_hint()"
      action: use_variant
      variant: reduced_evidence

  # Named variants
  variants:
    reduced_evidence:
      phase_overrides:
        evidence_seeking:
          config:
            max_iterations: 3

  # Phase definitions
  phases:
    - id: prior_retrieval
      executor: archivist
      inputs: [trigger_error, context_logs]
      outputs: [prior_knowledge]

    - id: hypothesis_generation
      executor: theorist
      inputs: [trigger_error, context_logs, prior_knowledge]
      outputs: [hypotheses]
      config:
        max_hypotheses: 10

    - id: evidence_seeking
      executor: detective
      inputs: [hypotheses, prior_knowledge]
      outputs: [evidence, hypotheses]
      config:
        max_iterations: 10

    - id: causal_chains
      executor: logician
      inputs: [hypotheses, evidence]
      outputs: [causal_chains]
      filter:
        hypotheses:
          condition: "score > 0.2"
          limit: 3

    - id: adversarial_review
      executor: skeptic
      inputs: [hypotheses, causal_chains, evidence, prior_knowledge]
      outputs: [challenges]
      requires: "len(causal_chains) > 0 and len(hypotheses) > 0"

    - id: outcome_assessment
      executor: judge
      inputs: [hypotheses, evidence, challenges]
      outputs: [outcome]

    - id: synthesis
      executor: synthesizer
      inputs: [investigation, outcome, hypotheses, causal_chains, evidence, prior_knowledge]
      outputs: [result]

    - id: learning
      executor: learner
      inputs: [investigation]
      outputs: [patterns]
      enabled: "${investigation.enable_auto_learning}"

  # Side effect hooks
  hooks:
    - after: synthesis
      action: store_investigation
    - after: synthesis
      action: store_binder

  # Conditional branches (optional)
  branches: []
```

---

## Validation Rules

1. **Phase IDs must be unique** within the pipeline
2. **Exactly one of `executor` or `panel`** must be specified per phase
3. **Branch/fast_path targets** must reference existing phase IDs
4. **Variant names** referenced in fast_paths must exist in variants section
5. **Hook actions** must be registered in the HookRegistry
6. **Result builders** must be registered in the ResultBuilderRegistry
7. **Circular branches** are not allowed (no backward jumps in branches)
8. **Fast path skip_to** must target a phase after the current position
9. **Pipeline section is required** - config.yaml must contain a valid `pipeline:` section

---

## Error Messages

### Missing Pipeline Configuration

If `config.yaml` is missing the `pipeline` section:

```
Error: Pipeline configuration required.
Please add a 'pipeline' section to config.yaml.
See documentation for pipeline configuration syntax.
```

### Invalid Phase Reference

```
ValueError: Fast path 'my_fast_path' skip_to references unknown phase 'nonexistent'
```

### Missing Required Field

```
ValueError: Fast path 'my_fast_path' with action=early_return requires 'result_builder'
```
