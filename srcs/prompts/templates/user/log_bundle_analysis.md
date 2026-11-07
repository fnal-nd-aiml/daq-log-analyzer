You are analyzing {file_count} DAQ log files from a single run.

## Source Files
{file_list}

## Total Errors Found
{total_errors} error-level entries across all files.

## Chronological Timeline
Each entry has: timestamp, source_file, board_name, level, component,
message, source_location.

{merged_timeline}

## Component Documentation Reference
{component_documentation}

## Your Task

Using the timeline entries and documentation reference above:

1. **Identify the primary error** — the FIRST error that CAUSED all others.
   Use the Error-to-Root-Cause Lookup Table in the documentation to determine
   the correct root cause classification.

2. **Analyze each affected board** — for every board_name in the timeline,
   determine its role (primary_failure, secondary_cascade, downstream_effect)
   and failure mode.

3. **Trace the cascade** — build explicit causal links showing how the
   primary failure propagated to each affected board. Use the Known Cascade
   Chains from the documentation to validate your analysis.

4. **Extract clues** for deeper investigation.

Produce a JSON response:

{include:artifacts/schemas/log_bundle_analysis}

## Guidelines

1. The PRIMARY error is the Tier 1 board that CAUSED all others — use the hierarchy above
2. Check the documentation Error-to-Root-Cause table to validate your primary error identification
3. Same-timestamp errors across boards = cascade from shared trigger; apply hierarchy to pick primary
4. Assign each board a role: primary_failure (1 board), secondary_cascade, or downstream_effect
5. Build cascade_chain links from primary board outward
6. Include specific numeric values in key_error_message and evidence fields
7. Extract source_location from the MSG header of each board's key error
8. Each clue should help the Archivist find relevant source code or patterns
