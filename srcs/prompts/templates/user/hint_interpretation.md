You are analyzing code hints extracted from a C++ function to generate root cause
hypotheses for a DAQ system error.

## Error Message
{error_message}

## Code Hints Extracted From Source
{hints_text}

## Your Task
For each hint, determine:
1. Is it diagnostically relevant to the error? Mark as NOT diagnostic if it is:
   - An implementation note about algorithm strategy (e.g., "iterate from the end")
   - A status/progress message (e.g., "Checking that data exists")
   - A description of what the code does rather than what could go wrong
   - An iteration or loop comment (e.g., "do more work to decide which...")
   - A TLOG or trace message describing normal operation (e.g., "windowClosed is false")
   - A variable state description without failure context (e.g., "the missing_data flag
     should be set", "sending N fragments")
   - An algorithm note explaining code strategy (e.g., "likely that we need to resend")
2. If diagnostic, rewrite it as a specific, testable hypothesis about what could cause
   the observed error. A good hypothesis states a concrete condition or failure mode,
   not just what a function does.

## Examples

REJECT these (not diagnostic):
- "windowClosed is false, and the missing_data flag should be set" → variable state, no failure
- "Do a little bit more work to decide which fragments to send" → algorithm note
- "Checking that data buffer exists" → status message
- "Iterate over remaining fragments" → implementation detail
- "likely that we have old data" → speculative code comment, not a failure condition

ACCEPT these (diagnostic):
- "Timeout exceeded: buffer timestamp trails request window" → specific failure condition
- "Data pipeline stall: no new fragments received in N seconds" → concrete failure mode
- "Buffer overflow when fragment count exceeds maximum" → error cause with mechanism
- "Timestamp gap causes window closure before data arrives" → causal failure chain

Be selective. Only mark hints as diagnostic if they describe a failure condition,
error cause, or abnormal state that could explain the error message.
