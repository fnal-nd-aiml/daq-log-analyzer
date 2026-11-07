ARTDAQ DOMAIN KNOWLEDGE:

COMPONENTS:
- BoardReader: Reads data from hardware (digitizers, trigger boards)
- EventBuilder: Assembles fragments from BoardReaders into complete events
- DataLogger: Writes assembled events to disk storage
- Dispatcher: Routes events to online monitoring
- RoutingManager: Coordinates data flow between components

ERROR CATEGORIES:
- Hardware: Device communication failures, timeouts, data corruption
- Software: Memory issues, logic errors, race conditions
- Configuration: Mismatched settings, invalid parameters
- Timing: Synchronization issues, deadlines missed
- Resource: Out of memory, disk full, network congestion

CAEN DIGITIZER PATTERNS:
CAEN V1730 is a common VME digitizer in artdaq DAQ systems. Key patterns:
- PMT_EVENT_SIZE is in 32-bit words: multiply by 4 to get bytes (e.g., 40004 words = 160,016 bytes)
- "Wrong event size" with returned < header: mid-transfer hardware failure (device stopped mid-read)
- CAEN_DGTZ_ReadData returning -1: communication error (CAEN_DGTZ_CommError), device unreachable
- ReadTemperature returning negative error codes: device register access failure
- Event counter resetting from millions to 1: board re-initialization or firmware restart
- Multiple boards resetting counters simultaneously: shared VME crate/optical link disruption
- Sequence ID gap showing huge unsigned value: unsigned 64-bit wrapping of (1 - previous_value)
- Buffer overflow where write_size ~2x buffer_size: CAEN library returned merged/garbled events
- Progressive failure pattern (corrupted data → API errors → register failures → unphysical
  sensor readings) within seconds: hardware/firmware failure, NOT software or configuration

EVIDENCE PRINCIPLES:
- Every claim must cite evidence or be marked as assumption
- Supporting evidence strengthens hypotheses
- Contradicting evidence weakens hypotheses
- Strong > Moderate > Weak evidence

{include:artifacts/enums/evidence_strength}
