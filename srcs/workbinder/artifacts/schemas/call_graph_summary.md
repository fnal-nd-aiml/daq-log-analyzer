## Call Graph Function Summary

Detailed structured summary of a function in a call graph relative to an error location.

### Fields

The response is a JSON object with structured per-function analysis sections.
Each section should be a substantial paragraph (minimum 50 words) so the total
analysis reaches approximately 300 words or more.

### JSON Format

```json
{
    "function_name": "The fully qualified function name",
    "purpose": "What the function does and why it exists in the codebase. Describe its role in the system and what problem it solves.",
    "mechanism": "How it works - key logic, algorithms, data transformations, state changes, and control flow. Be specific about the implementation.",
    "data_flow": "How data enters and exits the function - parameters, return values, key variables, buffers, shared state, and side effects.",
    "error_paths": "Error handling, failure modes, exception paths, edge cases, and what happens when things go wrong.",
    "error_line_relevance": "How this function specifically relates to the error emission line under investigation - what path leads from this function to the error, or what data it provides/consumes that is relevant."
}
```

### Focus Areas

When analyzing functions, focus on:
- Data transformations and validation that could corrupt or lose data
- Error handling paths and what conditions trigger failures
- Resource management (memory, connections, buffers)
- State changes that could affect downstream code
- Timing and synchronization concerns
- The specific relationship to the error under investigation
