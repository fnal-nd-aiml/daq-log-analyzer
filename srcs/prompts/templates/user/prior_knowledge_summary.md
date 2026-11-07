# Prior Knowledge Summary

Analyze and summarize the prior knowledge retrieved for this investigation.

## Error Being Investigated

```
{error_message}
```

Component: {error_component}
Function: {error_function}
Timestamp: {error_timestamp}

## Chronicler Multi-File Analysis
{chronicler_analysis}

## Retrieved Prior Knowledge

### Matched Patterns
{matched_patterns}

### Similar Past Investigations
{similar_investigations}

### Source Code Locations
{source_locations}

### Call Graph Context
{call_graph_context}

## Task

Use the Chronicler's analysis as the primary frame of reference when ranking relevance.
Patterns and similar cases that relate to the Chronicler's identified primary error and
cascade chain should be ranked highest.

Provide a concise summary of the prior knowledge that includes:

1. **Relevance Assessment**: How relevant is each piece of prior knowledge to the current error?

2. **Key Insights**: What important insights do the patterns and similar cases provide?

3. **Recommended Focus Areas**: Based on prior knowledge, what should the investigation focus on?

4. **Data Flow Summary**: Explain the data flow around the error location based on call graph analysis.

5. **Confidence Notes**: Rate your confidence in the prior knowledge applicability (high/medium/low) and explain why.

## Response Format

{include:artifacts/schemas/prior_knowledge_summary}
