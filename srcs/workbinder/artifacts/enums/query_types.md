## Evidence Query Types

Available query types for evidence gathering:

- **log_search**: Search log entries by text pattern (e.g., "timeout", "failed to connect")
- **log_source**: Find source code files containing log statements that produce this message
- **function_lookup**: Look up function definitions by name. Use `full_source: true` for complete body.
- **class_lookup**: Look up class definitions by name
- **code_search**: Search code for symbols/patterns
- **similar_cases**: Find similar past investigations
- **pattern_lookup**: Find known error patterns matching this error
- **component_logs**: Get logs from a specific component
- **time_window**: Get logs within a time window
- **accuracy_check**: Check historical accuracy of a pattern
