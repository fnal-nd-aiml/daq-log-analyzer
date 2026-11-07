Analyze this error message and extract structured information about the numeric
values and their relationships.

## Error Message
{error_message}

## Pre-extracted Numeric Values
{numeric_values}

## Analysis Tasks
1. Identify the function name where the error occurred
2. Classify the error type (timeout, buffer_overflow, data_gap, synchronization, etc.)
3. For each numeric value, determine what it represents (e.g., timeout_threshold,
   actual_wait_time, buffer_start, buffer_end, window_start, window_end)
4. If timestamps are present, calculate and explain any gaps or latency
5. If timeout values are present, explain the relationship between configured and
   actual values
6. Determine the most likely root cause based on the numeric analysis

Focus on the NUMERIC relationships. For example:
- If buffer timestamps don't reach window timestamps, calculate how far behind the
  buffer is
- If wait time exceeds timeout, calculate by how much
- Express gaps in human-readable form (e.g., "2.2 seconds behind")

Be specific and quantitative in your analysis.
