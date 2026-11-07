Parse these {file_count} DAQ log files and produce a merged chronological timeline.

**Files**: {file_list}

{raw_file_contents}

**Instructions**: Parse every `%MSG` block in the files above. Extract timestamp, source file, board name (from filename), level (e/s=error, w=warning, i=info, d=debug), component, source_location (source file:line from header, e.g., "BoardReader_generator.cc:345"), and full message content (all body lines joined with newline). Sort all entries by timestamp across files.

Return JSON:

{include:artifacts/schemas/merged_timeline_entry}

Preserve ALL message content including numeric details (buffer sizes, byte counts, fragment IDs). Do not skip any entries.
