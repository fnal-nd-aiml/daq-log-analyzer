You are analyzing component documentation for an artdaq DAQ system to extract information relevant to specific error messages observed during a run.

## Documentation: {doc_name}

{doc_content}

## Observed Error Messages

{error_messages}

## Task

Extract all information from the documentation above that is relevant to diagnosing the observed error messages. Return a structured extraction with:

1. **error_diagnoses**: For each error message that matches or relates to documented errors, extract:
   - `error_pattern`: The error message pattern from the documentation
   - `root_cause`: The documented root cause
   - `resolution`: The documented fix or resolution
   - `confidence`: How well the doc matches — "exact" (error message directly documented), "likely" (closely related pattern), or "related" (tangentially relevant)

2. **cascade_chains**: Any documented error cascade sequences that could explain how the observed errors propagate (e.g., "hardware timeout → buffer overflow → fragment timeout")

3. **configuration_hints**: Any FHiCL parameters, configuration settings, or tuning knobs mentioned in the documentation that relate to the observed errors

4. **relevant_context**: Any background information from the documentation that would help diagnose the errors (component architecture, data flow, known limitations)

5. **reasoning**: Brief explanation of why you selected these sections and how they relate to the observed errors

## Guidelines

- Focus on ACTIONABLE information: root causes, fixes, and diagnostic procedures
- Prefer EXACT matches over tangential references
- Include cascade chain information even if only partially matching — understanding error propagation is critical
- For configuration hints, include the parameter name, its purpose, and recommended values if documented
- If no relevant information is found for a category, return an empty list/string
- Do NOT fabricate information not present in the documentation

Return your response as a JSON object matching the DocExtraction schema.
