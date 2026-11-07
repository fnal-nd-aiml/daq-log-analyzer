## Log Bundle Analysis

Analysis of a multi-file DAQ log bundle identifying the primary error, per-board analysis,
cascade chain, and clues for deeper investigation.

### Fields

- `annotated_narrative` (string, required): 2-4 paragraph narrative interpreting the merged timeline
- `primary_error_file` (string, required): Filename containing the primary/root error
- `primary_error_message` (string, required): The exact error message with numeric details
- `primary_error_line` (integer or null): Line number of the primary error if known
- `affected_boards` (array of objects, required): Per-board structured analysis
  - `board_name` (string): Short board identifier (e.g., "wwtop03")
  - `filename` (string): Source log filename
  - `role` (string): One of primary_failure, secondary_cascade, downstream_effect
  - `failure_mode` (string): One-sentence failure description
  - `key_error_message` (string): Most significant error message with numeric values
  - `source_location` (string): Source code location from MSG header (e.g., "CAENV1730Readout_generator.cc:1066")
  - `error_count` (integer): Number of errors for this board
  - `warning_count` (integer): Number of warnings for this board
- `cascade_chain` (array of objects, required): Causal links showing failure propagation
  - `from_board` (string): Board where cause originated
  - `to_board` (string): Board that was affected
  - `mechanism` (string): How failure propagated
  - `evidence` (string): Key numeric evidence for the link
- `cascade_description` (string, required): How the primary error cascaded to other boards
- `clues` (array of objects, required): Clues for deeper investigation
  - `clue_type` (string): One of error_pattern, component_interaction, timing, configuration
  - `description` (string): What to investigate
  - `source_file` (string): Filename where clue was found
  - `relevance` (string): One of HIGH, MEDIUM, LOW
  - `suggested_search` (string): Function or pattern to search for

### JSON Format

```json
{
  "annotated_narrative": "2-4 paragraph narrative...",
  "primary_error_file": "filename",
  "primary_error_message": "exact error with numeric details",
  "primary_error_line": null,
  "affected_boards": [
    {
      "board_name": "wwtop03",
      "filename": "run14001-icaruspmtwwtop03.log",
      "role": "primary_failure",
      "failure_mode": "CAEN V1730 returned corrupted event",
      "key_error_message": "Wrong event size; returned=128612...",
      "source_location": "CAENV1730Readout_generator.cc:1066",
      "error_count": 3,
      "warning_count": 4
    }
  ],
  "cascade_chain": [
    {
      "from_board": "wwtop03",
      "to_board": "ewbot01",
      "mechanism": "corrupted event data on shared VME bus",
      "evidence": "312596 bytes written into 162208 buffer"
    }
  ],
  "cascade_description": "How the primary error cascaded...",
  "clues": [
    {
      "clue_type": "error_pattern",
      "description": "What to investigate",
      "source_file": "filename",
      "relevance": "HIGH",
      "suggested_search": "function or pattern"
    }
  ]
}
```

### Cascade Hierarchy for Primary Error Identification

When multiple boards show errors at the same timestamp, use this strict hierarchy
to identify the PRIMARY error — the board that caused all others to fail:

**TIER 1 — PRIMARY (hardware/readout failure at source). Always prefer these:**
- `"Wrong event size; returned=N, header=N"` — hardware returned fewer bytes than its
  own header declared (CAENV1730). This is the root cause.
- `"CAEN_DGTZ_ReadData returned non zero return code"` — hardware became unresponsive
  at the API level (CAENV1730).
- `"Too many times (10) with zero data size in TileHeader. Exit."` — hardware stopped
  responding to readout requests (PhysCrateData).
- `"Could not connect to board on link %d, node %d. Bail."` — hardware link failure
  during initialization (PhysCrateData).
- `"Failed to initialise febdrv on interface"` — FEB driver initialization failure
  (BernCRTData).
- `"List of N FEBs declared in the FHiCL file... doesn't match list of M detected FEBs"`
  — hardware configuration mismatch (BernCRTData).
- `"Critical error in getData_(); stopping boardreader process...."` — fatal readout
  error (SPECTDCTimestampReader).
- `"fmctdc_init() returned error"` — hardware initialization failure
  (SPECTDCTimestampReader).
- `"Was not able to initialize SPEXI"` — trigger hardware initialization failure
  (ICARUSTriggerV3).
- `"Parameters not communicated successfully communicated, failing"` — trigger
  configuration failure (ICARUSTriggerV3).
- `"XMITReader %s: *** *** DMA timed out. DMAed %d bytes"` — DMA transfer timeout
  (NevisTPC2StreamNUandSNXMIT).
- `"Two internal trigger sources (CALIB and Controller) are enabled simultaneously.`
  `Exit..."` — conflicting trigger configuration (NevisTPC2StreamNUandSNXMIT).

**TIER 2 — SECONDARY (consequence of primary). Do NOT select as primary:**
- `"CAENReadData() tried to write N bytes into a N-byte buffer; dropping."` — buffer
  overflow caused by corrupted data from a Tier 1 board flowing downstream.
- `"Redzone was overwritten; DataBlock.index=N"` — memory corruption detected after
  overflow.
- `"Not enough space; DataRange.size=N is larger than DataBlock.size=M"` — buffer
  allocation insufficient for corrupted payload.
- `"PoolBuffer is empty; last received trigger eventCounter=N"` / `"PoolBuffer is full"`
  — buffer exhaustion from upstream stall or flood.
- `"Cannot stop <name> thread."` / `"Caught exception while running <name> thread."` —
  worker thread crash following upstream failure.
- `"Inconsistent event numbers in one fragment"` — event numbering corruption
  (PhysCrateData).
- `"Header out of sync: %X"` — stream desynchronization (NevisTPC).
- `"Circular buffer is not linear"` — buffer state corruption (PhysCrateData).
- `"Caught exception in processFragments: <what>"` — preprocessor crash
  (SPECTDCTimestampReader).

**TIER 3 — TERTIARY (downstream cascade effects). Do NOT select as primary:**
- `"FragmentBuffer timeout"` — timeout waiting for data that will never arrive because
  the upstream board is dead.
- `"event counter reset"` / sequence ID out-of-order / unsigned integer wrap errors.
- `"Causality problem"` / timestamp violations on cascade boards.
- `"Fragment assigned timestamp is after timestamp from fragment creation!"` — timestamp
  ordering violation from delayed or reordered fragments.
- `"There is no data for %d seconds"` — prolonged data absence (NevisTPC).
- `"Missing triggers; current trigger eventCounter=N, previous ... / gap = N"` — trigger
  gap from upstream failure.
- `"Detected a gap in the channel N sample sequence"` — sample sequence discontinuity
  (SPECTDCTimestampReader).
- `"Detected a time gap > N in the channel M"` — timing discontinuity
  (SPECTDCTimestampReader).
- Empty fragment detections in the event builder.

**Rule**: When a Tier 1 error and a Tier 2 error appear at the same timestamp, the Tier 1
board is ALWAYS the primary_failure. The Tier 2 board received bad data FROM the Tier 1 board
over the shared VME bus/optical link — it is a victim, not the cause.
