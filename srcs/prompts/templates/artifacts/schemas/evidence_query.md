## Evidence Query Artifact

A query to gather evidence that discriminates between hypotheses.

### Fields

- `query_type` (string, required): Type of query (see query_types enum)
- `query` (string, required): The specific search query or parameter
- `targets_hypothesis` (string, required): Which hypothesis this tests
- `expected_if_true` (string, required): What we'd find if hypothesis is correct
- `expected_if_false` (string, required): What we'd find otherwise
- `full_source` (boolean, optional): For function_lookup, get complete function body

### JSON Format

```json
{
    "query_type": "log_search|log_source|function_lookup|class_lookup|code_search|similar_cases|pattern_lookup|component_logs|time_window|accuracy_check",
    "query": "specific query",
    "targets_hypothesis": "hypothesis_id",
    "expected_if_true": "what we'd find",
    "expected_if_false": "what we'd find otherwise",
    "full_source": false
}
```
