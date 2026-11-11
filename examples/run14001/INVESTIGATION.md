# Run 14001 Crash Investigation: CAEN V1730 Hardware Failure and Cascade

## Summary

On 16-Jan-2026 at approximately 15:24:47 CST, CAEN V1730 digitizer board FragID 8194
(hosted on `icaruspmtwwtop03`) delivered a corrupted event containing 128,612 bytes instead
of the expected 160,016 bytes. This undersized read caused the CAEN library on the co-located
board reader `icaruspmtewbot01` to attempt writing 312,596 bytes into a 162,208-byte buffer,
overwriting the buffer's memory redzone and crashing the GetDataWorkerThread. The board then
became fully unresponsive (register read failures, `CAEN_DGTZ_ReadData` returning -1,
unphysical temperature readings). The failure cascaded to all other boards sharing the same
VME crate/optical link infrastructure, causing event counter resets to 1, sequence ID
discontinuities with unsigned integer wrapping, and timestamp causality violations across
six additional board readers. The event builder (`evb11`) recorded empty fragments for
FragIDs 8194, 8197, and 8207 across 153 events (74816 through 74969) over a 3.5-minute
window before the run was terminated.

---

## Timeline of Events

All times are CST, 16-Jan-2026. Run 14001, SubRun 1.

| Time | Host | Event |
|------|------|-------|
| 15:24:47.000 | icaruspmtwwtop03 | FragID 8194 returns corrupted event: 128,612 bytes vs expected 160,016 bytes (`CAENV1730Readout_generator.cc:1066`). Fragment dropped. |
| 15:24:47.000 | icaruspmtewbot01 | `CAENReadData()` attempts to write 312,596 bytes into 162,208-byte buffer (`CAENV1730Readout_generator.cc:1034`). Data dropped. |
| 15:24:47.000 | icaruspmtewbot01 | Redzone overwrite detected: `DataBlock.index=14, size=162208, data_size=160016, end - begin=162240, redzone size=8` (`PoolBuffer.hh:39`). |
| 15:24:47.000 | icaruspmtewbot01 | GetDataWorkerThread crashes after 883,098 checks (`workerThread.cpp:51-53`). |
| 15:24:47.000 | icaruspmtewbot02 | FragID 8208 event counter resets from 8,214,316 to 1 (gap=8,562,901). Causality violations begin (169-163 ms). |
| 15:24:47.000 | icaruspmtwwtop01 | FragID 8192 event counter resets from 8,127,715 to 1 (gap=8,649,502). |
| 15:24:47.000 | icaruspmtwwtop02 | FragID 8193 event counter resets from 8,127,715 to 1. Causality violations (289-286 ms). |
| 15:24:48.000 | icaruspmtewbot03 | FragID 8209 event counter resets from 8,214,306 to 1 (gap=8,562,911). |
| 15:24:50.000 | icaruspmtwwtop03 | Failed reading `CAEN_DGTZ_ACQ_STATUS_ADD` register for FragID 8194 (`CAENV1730Readout_generator.cc:1504`). |
| 15:24:53.000 | icaruspmtwwtop03 | `CAEN_DGTZ_ReadData` returns -1 (second occurrence) (`CAENV1730Readout_generator.cc:1020`). |
| 15:24:56.000 | icaruspmtwwtop03 | FragID 8194 channel 0 reads unphysical temperature (39C), `ReadTemperature` returns -18 (`CAENV1730Readout_generator.cc:1551`). |
| 15:24:59.000 | icaruspmtewbot01 | FragmentBuffer timeout (>10 s) waiting for data window close (`FragmentBuffer.cc:610`). |
| 15:24:59.000 | icaruspmtwwtop03 | FragmentBuffer timeout (>10 s) waiting for data window close (`FragmentBuffer.cc:610`). |
| 15:24:59.000 | icaruspmtwwtop03 | `CAEN_DGTZ_ReadData` returns -1 (third occurrence) (`CAENV1730Readout_generator.cc:1020`). |
| 15:25:02.000 | icaruspmtwwtop03 | Failed reading `CHANNEL_STATUS` register for FragID 8194, channel 0 (`CAENV1730Readout_generator.cc:1573`). |
| 15:25:11.000 | evb11 | Event 74816: 3 empty fragments detected (FragIDs 8194, 8197, 8207) out of 346 total (`FragmentWatcher_module.cc:226`). |
| 15:25:56.000 | evb11 | Event 74843: 2 empty fragments (FragIDs 8194, 8207). FragID 8197 partially recovers. |
| 15:28:38.000 | evb11 | Event 74969: 1 empty fragment (FragID 8207). Last recorded event before run termination. |

---

## Root Cause Analysis

### Primary Root Cause: CAEN V1730 Digitizer Hardware/Firmware Failure on FragID 8194

The board at FragID 8194 (hosted on `icaruspmtwwtop03`) suffered a hardware or firmware
failure that caused it to deliver a corrupted event readout. The evidence is unambiguous:

**Evidence 1 -- Wrong Event Size (wwtop03 log, line 2)**

```
%MSG-e CAENV1730Readout:  Early 16-Jan-2026 15:24:47 CST pre-events CAENV1730Readout_generator.cc:1066
(FragID=8194) Wrong event size; returned=128612, header=160016. PMT_EVENT_COUNTER=8127715, PMT_EVENT_SIZE=40004, PMT_TIME_TAG=15948090. DROPPING THIS FRAGMENT.
```

The CAEN V1730 event header reported `PMT_EVENT_SIZE=40004` (in units of 32-bit words, meaning
40004 x 4 = 160,016 bytes), but only 128,612 bytes were actually returned. This 31,404-byte
shortfall (19.6% data loss) indicates a mid-transfer failure where the board stopped delivering
data before the event was complete. The event counter (8,127,715) was still valid at this point,
confirming the board was operational immediately prior.

**Evidence 2 -- Board Becomes Fully Unresponsive**

Within seconds, the board became completely unreachable through multiple independent access paths:

- `15:24:50` -- ACQ_STATUS register read failure (`CAENV1730Readout_generator.cc:1504`)
- `15:24:53` -- `CAEN_DGTZ_ReadData` returns -1 (`CAENV1730Readout_generator.cc:1020`)
- `15:24:56` -- Unphysical temperature reading (39C, return code -18) on channel 0 (`CAENV1730Readout_generator.cc:1551`)
- `15:24:59` -- `CAEN_DGTZ_ReadData` returns -1 again
- `15:25:02` -- CHANNEL_STATUS register read failure for channel 0 (`CAENV1730Readout_generator.cc:1573`)

The progression from corrupted-but-readable to fully-unresponsive-across-all-registers is
characteristic of a firmware hang or bus-level lockup on the CAEN V1730 digitizer.

### Secondary Effect: Buffer Overflow on ewbot01

**Evidence 3 -- Buffer Overflow (ewbot01 log, lines 1-2)**

```
%MSG-e CAENV1730Readout:  Early 16-Jan-2026 15:24:47 CST pre-events CAENV1730Readout_generator.cc:1034
CAENReadData() tried to write 312596 bytes into a 162208-byte buffer; dropping.
```

The CAEN library reported that it attempted to write 312,596 bytes into a buffer allocated
for 162,208 bytes. The buffer size of 162,208 bytes is consistent with the expected single-event
payload of 160,016 bytes plus a small alignment/header overhead of 2,192 bytes
(160,016 + 2,192 = 162,208). The 312,596-byte write represents approximately 1.93x the buffer
capacity, indicating the CAEN library returned data from approximately two events merged into
one read cycle, or the board delivered garbled length metadata.

**Evidence 4 -- Memory Corruption Detected (ewbot01 log, lines 4-5)**

```
%MSG-e CAENV1730Readout:  Early 16-Jan-2026 15:24:47 CST pre-events PoolBuffer.hh:39
verify_redzone: Redzone was overwritten; DataBlock.index=14, size=162208, data_size=160016, end - begin=162240, redzone size=8
```

The pool buffer memory allocator detected that its 8-byte sentinel region (redzone) following
DataBlock index 14 was overwritten. This confirms the overflow physically corrupted adjacent
memory. The numbers are internally consistent:
- `size=162208` -- total allocated block
- `data_size=160016` -- expected payload capacity
- `end - begin=162240` -- actual span (162,208 + 32 bytes of metadata/alignment)
- `redzone size=8` -- sentinel bytes that were overwritten

**Evidence 5 -- Worker Thread Crash (ewbot01 log, lines 7-11)**

```
%MSG-e WorkerThread:  Early 16-Jan-2026 15:24:47 CST pre-events workerThread.cpp:51
Caught exception while running GetDataWorkerThread thread.
%MSG-i WorkerThread:  Early 16-Jan-2026 15:24:47 CST pre-events workerThread.cpp:53
Stopped GetDataWorkerThread thread after 883098 checks.
```

The redzone overwrite was detected as an exception, which propagated up to the worker thread
loop (`workerThread.cpp:51`). After running for 883,098 polling iterations, the thread terminated.
In the artdaq framework, the BoardReaderCore runs its fragment generator in a receiver thread
(see `BoardReaderCore.cc` line 361: `receiver_thread_active_ = generator_ptr_->getNext(frags)`).
When `getNext()` raises an exception, `generator_ptr_->exception()` returns true and the
application transitions to `InRunError` state (lines 370-372).

---

## Per-Board Analysis

### Board 1: icaruspmtewbot01 (FragIDs served from this host)

**Role:** Board reader that experienced the buffer overflow.

**Failure Mode:** The CAEN readout library wrote 312,596 bytes into a 162,208-byte buffer on
DataBlock index 14 of the PoolBuffer. The redzone sentinel was overwritten, the exception
propagated to `workerThread.cpp:51`, and the GetDataWorkerThread terminated after 883,098
iterations. With the data acquisition thread dead, the FragmentBuffer at line 610 of
`FragmentBuffer.cc` began issuing timeout warnings at 15:24:59 -- exactly 12 seconds after
the crash -- when the 10-second `window_close_timeout_us_` expired without new data arriving
to close the request windows.

The timeout code path is in `artdaq::FragmentBuffer::applyRequestsWindowMode_CheckAndFillDataBuffer`
(`FragmentBuffer.cc:597-718`). At line 611, the condition
`TimeUtils::GetElapsedTimeMicroseconds(requestBuffer_->GetRequestTime(seq)) > window_close_timeout_us_`
evaluates to true, triggering the warning at line 614. The two timeout messages show consecutive
request windows with timestamps `{1768598689227608136-1768598689230608136}` and
`{1768598689260608328-1768598689263608328}`, while the buffer data range was frozen at
`{1768598677121537664-1768598687094584432}` (no new data since crash).

**Log Messages:** 4 errors, 2 warnings.

### Board 2: icaruspmtewbot02 (FragID 8208)

**Role:** Board reader sharing infrastructure with the failed board.

**Failure Mode:** Event counter cascading reset. At 15:24:47, FragID 8208 reported its
event counter jumping from 8,214,316 to 1, with a gap of 8,562,901 events
(`CAENV1730Readout_generator.cc:1144`). This reset is characteristic of a CAEN V1730 board
re-initialization or firmware restart triggered by a shared bus/optical-link disruption.

The sequence ID also reset from 8,214,316 to 1, producing a gap value of
18,446,744,073,701,337,301 (`CAENV1730Readout_generator.cc:1411`). This enormous number is
the unsigned 64-bit interpretation of `1 - 8,214,316 = -8,214,315`, confirming unsigned integer
wrapping: `2^64 - 8,214,315 = 18,446,744,073,701,337,301`. The sequence ID out-of-order error
at line 1419 (`1 < 8214316`) confirmed the regression.

Additionally, five consecutive timestamp causality violations were detected
(`CAENV1730Readout_generator.cc:1379`), with fragments assigned timestamps 169 ms to 163 ms
ahead of the wall clock at creation time. This indicates the board's internal timestamp counter
was reset to a value inconsistent with the system time epoch.

**Log Messages:** 1 error (sequence ID out of order), 7 warnings (missing triggers, causality,
sequence gap).

### Board 3: icaruspmtewbot03 (FragID 8209)

**Role:** Board reader sharing infrastructure with the failed board.

**Failure Mode:** Identical cascading reset pattern to ewbot02. At 15:24:48 (one second after
the primary failure), FragID 8209 reported its event counter jumping from 8,214,306 to 1
(gap=8,562,911). The sequence ID gap is 18,446,744,073,701,337,311 (unsigned wrapping of
`1 - 8,214,306`). Sequence ID ordering error confirmed: `1 < 8214306`.

The slightly different starting event counter (8,214,306 vs ewbot02's 8,214,316) indicates
the two boards were 10 events apart at the time of the disruption, consistent with normal
readout pipeline jitter. The one-second delay compared to ewbot02 suggests the disruption
propagated through the shared infrastructure with a small delay.

No causality violations were logged for this board, suggesting its internal timestamp counter
reset was coincidentally close to the system time epoch, or the fragments were processed before
the timestamp divergence grew large enough to trigger the warning threshold.

**Log Messages:** 1 error (sequence ID out of order), 2 warnings (missing triggers, sequence gap).

### Board 4: icaruspmtwwtop01 (FragID 8192)

**Role:** Board reader on the wwtop crate.

**Failure Mode:** Event counter reset from 8,127,715 to 1 (gap=8,649,502) at 15:24:47.
The different starting count (8,127,715 vs 8,214,316 on ewbot boards) reflects different
accumulated event totals between the two crate groups. The sequence ID gap is
18,446,744,073,701,423,902 (unsigned wrapping of `1 - 8,127,715`). Sequence ID ordering
error confirmed: `1 < 8127715`.

No causality violations logged.

**Log Messages:** 1 error (sequence ID out of order), 2 warnings (missing triggers, sequence gap).

### Board 5: icaruspmtwwtop02 (FragID 8193)

**Role:** Board reader on the wwtop crate, same crate as the failed FragID 8194 board.

**Failure Mode:** Event counter reset from 8,127,715 to 1 (gap=8,649,502) at 15:24:47.
Starting count matches wwtop01 (8,127,715), confirming they share the same trigger
distribution. The sequence ID gap is 18,446,744,073,701,423,902.

Three causality violations were detected with deltas of 289 ms, 287 ms, and 286 ms
(`CAENV1730Readout_generator.cc:1379`). These are roughly double the causality violations
seen on ewbot02 (163-169 ms), consistent with the wwtop boards being in a different
physical location with a different clock synchronization path.

**Log Messages:** 1 error (sequence ID out of order), 5 warnings (missing triggers,
3x causality, sequence gap).

### Board 6: icaruspmtwwtop03 (FragID 8194 -- the failed board)

**Role:** Board reader hosting the primary failed digitizer.

**Failure Mode:** This is the origin of the incident. The CAEN V1730 board at FragID 8194
first delivered a corrupted event (128,612 vs 160,016 bytes expected) at 15:24:47, then
became progressively more unresponsive over the next 15 seconds:

1. **15:24:47** -- Corrupted event detected and dropped (line 1066)
2. **15:24:50** -- ACQ_STATUS register read failure (line 1504)
3. **15:24:53** -- `CAEN_DGTZ_ReadData` returns -1 (line 1020)
4. **15:24:56** -- Unphysical temperature (39C) with CAEN error -18 (line 1551)
5. **15:24:59** -- FragmentBuffer data timeout (10s exceeded)
6. **15:24:59** -- `CAEN_DGTZ_ReadData` returns -1 again (line 1020)
7. **15:25:02** -- CHANNEL_STATUS register read failure (line 1573)

The FragmentBuffer timeout at 15:24:59 shows the same pattern as ewbot01: the
`window_close_timeout_us_` of 10 seconds expired because no new data arrived from the
dead board. The buffer range `{1768598677155309344-1768598687127485424}` was frozen.

**Log Messages:** 3 errors (wrong event size, 2x CAEN_DGTZ_ReadData=-1), 4 warnings
(register failures, temperature, 2x FragmentBuffer timeout).

### Board 7: pmt_icarus-evb11-daq (Event Builder 5)

**Role:** Event builder receiving fragments from all board readers.

**Failure Mode:** The FragmentWatcher module (`FragmentWatcher_module.cc:226`) detected empty
fragments arriving in assembled events. The empty fragment detection logic (lines 162-188)
identifies fragments whose art product instance name contains "Empty", which corresponds to
`Fragment::EmptyFragmentType` (system type 231, defined in `RawFragmentHeader.hh:62`).

These empty fragments are generated by the `FragmentBuffer::sendEmptyFragment` method
(`FragmentBuffer.cc:916-924`) when a board reader has no data to contribute for a given
sequence ID. When the data acquisition thread crashes (as on ewbot01) or the board becomes
unresponsive (as on wwtop03), the FragmentBuffer eventually times out
(`applyRequestsWindowMode_CheckAndFillDataBuffer`, lines 611-619) and sends an empty
ContainerFragment or an EmptyFragmentType placeholder.

The progression of empty fragments tells the recovery story:
- **Event 74816 (15:25:11):** 3 empty fragments -- FragIDs 8194, 8197, 8207
- **Event 74843 (15:25:56):** 2 empty fragments -- FragIDs 8194, 8207 (8197 recovered)
- **Event 74969 (15:28:38):** 1 empty fragment -- FragID 8207 only (8194 presumably
  still dead but potentially handled differently by this point)

The 346 total fragments per event represents the full detector complement, meaning only 0.3-0.9%
of fragments were empty in any given event.

**Log Messages:** 3+ warnings (empty fragment reports; the `...` in the log suggests
additional intermediate events were elided).

---

## Causal Chain

```
CAEN V1730 Board (FragID 8194) Hardware/Firmware Failure
│
├─[1] Delivers corrupted event: 128,612 bytes vs 160,016 expected
│     (CAENV1730Readout_generator.cc:1066, wwtop03 log)
│
├─[2] CAEN library on ewbot01 writes 312,596 bytes into 162,208-byte buffer
│     (CAENV1730Readout_generator.cc:1034, ewbot01 log)
│     │
│     ├─[2a] PoolBuffer redzone sentinel overwritten (PoolBuffer.hh:39)
│     │       DataBlock.index=14, 8-byte redzone corrupted
│     │
│     ├─[2b] Exception propagates to GetDataWorkerThread (workerThread.cpp:51)
│     │       Thread terminates after 883,098 iterations
│     │
│     └─[2c] BoardReaderCore detects generator exception
│             (BoardReaderCore.cc:370-372) → InRunError state
│
├─[3] Board becomes fully unresponsive (progressive, 15:24:50 → 15:25:02)
│     ├─ ACQ_STATUS register read failure
│     ├─ CAEN_DGTZ_ReadData returns -1 (CAEN library error)
│     ├─ Temperature readout returns unphysical value (-18 error code)
│     └─ CHANNEL_STATUS register read failure
│
├─[4] Cascading board resets on shared infrastructure
│     │   (All at 15:24:47 to 15:24:48)
│     │
│     ├─ ewbot02 (FragID 8208): counter 8,214,316 → 1
│     ├─ ewbot03 (FragID 8209): counter 8,214,306 → 1
│     ├─ wwtop01 (FragID 8192): counter 8,127,715 → 1
│     └─ wwtop02 (FragID 8193): counter 8,127,715 → 1
│
│     Secondary effects of reset:
│     ├─ Sequence ID discontinuities (unsigned 64-bit wrapping)
│     ├─ Timestamp causality violations (163-289 ms)
│     └─ Sequence ID ordering errors (new ID 1 < previous ID ~8M)
│
├─[5] FragmentBuffer data starvation on ewbot01 and wwtop03
│     (FragmentBuffer.cc:610-619)
│     │
│     └─ window_close_timeout_us_ (10 seconds) expires
│        → Frozen buffer ranges, no new data arriving
│        → Sends EmptyFragmentType placeholders
│           (FragmentBuffer.cc:916-924)
│
└─[6] Event Builder (evb11) assembles events with empty fragments
      (FragmentWatcher_module.cc:162-228)
      │
      ├─ Event 74816: 3 empty (8194, 8197, 8207)
      ├─ Event 74843: 2 empty (8194, 8207)
      └─ Event 74969: 1 empty (8207)
```

---

## Correlation with artdaq Framework Code

### FragmentBuffer.cc (artdaq/DAQrate/FragmentBuffer.cc)

- **Lines 597-718** -- `applyRequestsWindowMode_CheckAndFillDataBuffer()`: This is the window-mode
  request processing method. When the worker thread dies, no new fragments enter the DataBuffer
  (via `AddFragmentsToBuffer`, line 143). The buffer timestamp range freezes, and requests
  targeting future timestamps can never be satisfied.

- **Line 610** -- `bool windowClosed = dataBuffer->DataBufferDepthFragments > 0 && dataBuffer->DataBuffer.back()->timestamp() >= max`:
  This condition stays false because the buffer's latest timestamp never advances past the
  request window's maximum. The subsequent timeout check at line 611
  (`TimeUtils::GetElapsedTimeMicroseconds(...) > window_close_timeout_us_`) eventually triggers.

- **Lines 614-619** -- The timeout warning message matches exactly what appears in the ewbot01
  and wwtop03 logs: the request window range, the frozen buffer range, and the elapsed time
  exceeding 10,000,000 microseconds.

- **Lines 640-646** -- When `!windowClosed` (timeout path), the code sets `cfl.set_missing_data(true)`
  on the ContainerFragment, marking it as having known data gaps.

- **Lines 916-924** -- `sendEmptyFragment()`: Creates an EmptyFragmentType placeholder with the
  appropriate sequence ID and fragment ID. This is what the event builder's FragmentWatcher
  later detects.

### FragmentWatcher_module.cc (artdaq/ArtModules/FragmentWatcher_module.cc)

- **Lines 162-188** -- The empty fragment detection loop iterates over fragment handles, checking
  if the product instance name contains "Empty" (line 168:
  `std::size_t found = instance_name.find("Empty")`). When found, it counts the fragments and
  tracks which fragment IDs are affected.

- **Lines 216-228** -- When `empty_fragmentID_list_this_event` is non-empty, the module logs a
  `TLVL_BAD_FRAGMENTS` (which maps to `TLVL_WARNING`, line 34) message listing the total
  fragment count and the specific fragment IDs with empty fragments. This matches the evb11
  log entries: `Event 74816: total_fragments=346, fragmentIDs for 3 empty_fragments: 8194, 8197, 8207`.

### BoardReaderCore.cc (artdaq/Application/BoardReaderCore.cc)

- **Line 361** -- `receiver_thread_active_ = generator_ptr_->getNext(frags)`: The main data
  acquisition loop. When `getNext()` throws (due to the buffer overflow exception from the
  CAEN generator), the catch block in the calling thread infrastructure (`workerThread.cpp:51`)
  terminates the thread.

- **Lines 370-372** -- `if (!receiver_thread_active_ && generator_ptr_ && generator_ptr_->exception()) { parent_application_.in_run_failure(); }`:
  When the generator signals an exception, the board reader transitions to InRunError state,
  preventing further normal operation.

- **Lines 380-384** -- `fragment_buffer_ptr_->AddFragmentsToBuffer(std::move(frags))`: In normal
  operation, fragments returned by `getNext()` are added to the FragmentBuffer. With the
  receiver thread dead, this call is never made again, causing the buffer starvation that
  leads to the 10-second timeouts.

### FragmentBuffer.hh (artdaq/DAQrate/FragmentBuffer.hh)

- **Lines 435-444** -- The `DataBuffer` struct definition: contains `DataBufferDepthFragments`
  (atomic int), `DataBufferDepthBytes` (atomic size_t), `WindowsSent` map, and the actual
  `FragmentPtrs DataBuffer` protected by `DataBufferMutex`. The frozen state of this structure
  after the worker thread crash is what causes all subsequent timeouts.

- **Line 425** -- `window_close_timeout_us_`: The 10-second timeout parameter that determines
  when a stale request window is closed and empty/partial data is sent downstream.

### RawFragmentHeader.hh (artdaq-core/Data/detail/RawFragmentHeader.hh)

- **Line 43** -- `typedef uint64_t sequence_id_t`: The 48-bit sequence ID field that wraps
  when computing gaps, producing the enormous gap values seen in the cascade boards
  (e.g., 18,446,744,073,701,337,301).

- **Line 62** -- `static constexpr type_t EmptyFragmentType = FIRST_SYSTEM_TYPE + 6`: The
  type marker (value 231) used for empty placeholder fragments sent when no data is available.

### ContainerFragment.hh (artdaq-core/Data/ContainerFragment.hh)

- **Line 43** -- `count_t missing_data : 1`: The 1-bit flag set by `FragmentBuffer.cc:646`
  when a container is built from a timed-out window, informing downstream consumers that
  the container is known to be incomplete.

---

## Recommended Mitigations

### 1. Buffer Size Validation in CAEN Readout (Critical)

The CAEN readout generator (`CAENV1730Readout_generator.cc:1034`) already detects the
oversized write and drops it, but the damage occurs before the check -- the CAEN library
has already written 312,596 bytes into the 162,208-byte buffer. The fix should allocate
a "landing zone" buffer that is significantly larger than the maximum expected event size
(e.g., 2x or 4x), copy data into it, validate the size, and only then copy valid data
into the pool buffer. This prevents the CAEN library's DMA transfer from corrupting
adjacent memory.

### 2. Pre-Read Buffer Sizing with Guard Pages (High Priority)

Replace or supplement the 8-byte redzone sentinel in `PoolBuffer.hh` with OS-level guard
pages (`mmap` with `PROT_NONE`) after each allocated block. This converts silent memory
corruption into an immediate segfault with a clear stack trace, rather than relying on
post-hoc redzone verification.

### 3. Board Health Monitoring with Proactive Isolation (High Priority)

When a board returns a wrong event size (as at line 1066), the readout generator should
immediately attempt a register health check. If the board is unresponsive (as observed
3 seconds later at line 1504), it should be proactively removed from the active readout
list rather than continuing to poll it for 15+ seconds. This reduces the cascade window.

### 4. Cascade Detection and Automatic Recovery (Medium Priority)

When multiple boards simultaneously reset their event counters to 1, this is a clear
signature of a shared-infrastructure disruption. The system should detect this pattern
(event counter gap > threshold on N boards within T seconds) and trigger an automatic
board re-synchronization procedure rather than continuing to generate data with
incorrect sequence IDs and timestamps.

### 5. VME/Optical Link Isolation (Medium Priority)

Investigate whether the cascading resets can be prevented by improving electrical isolation
between boards on the same VME crate or optical link chain. The fact that boards on both
ewbot (8208, 8209) and wwtop (8192, 8193) crates were affected simultaneously suggests
the disruption propagated through a shared trigger distribution path or clock fanout,
not just the local VME bus.

### 6. Graceful Worker Thread Recovery (Medium Priority)

The GetDataWorkerThread currently terminates permanently on any exception
(`workerThread.cpp:51`). For recoverable errors (such as a single corrupted readout),
the thread should log the error, discard the corrupted data, and attempt to continue
reading. Only persistent failures (e.g., 3 consecutive errors) should trigger thread
termination and InRunError state transition.

### 7. Enhanced Diagnostics for CAEN Errors (Low Priority)

Log the raw CAEN error codes alongside the application-level messages. The return code
of -1 from `CAEN_DGTZ_ReadData` and -18 from `ReadTemperature` correspond to specific
CAEN library error enumerations (`CAEN_DGTZ_CommError` and `CAEN_DGTZ_InvalidChannelNumber`
respectively) that would help diagnose whether the root cause is in the optical link,
the VME bridge, or the digitizer FPGA itself.

---

## Appendix: Numerical Verification

### Sequence ID Gap Wrapping

For ewbot02 (FragID 8208):
- Previous sequence ID: 8,214,316
- Current sequence ID: 1
- Reported gap: 18,446,744,073,701,337,301
- Verification: `2^64 - 8,214,315 = 18,446,744,073,709,551,616 - 8,214,315 = 18,446,744,073,701,337,301` (matches)

For wwtop01 (FragID 8192):
- Previous sequence ID: 8,127,715
- Current sequence ID: 1
- Reported gap: 18,446,744,073,701,423,902
- Verification: `2^64 - 8,127,714 = 18,446,744,073,709,551,616 - 8,127,714 = 18,446,744,073,701,423,902` (matches)

### Buffer Overflow Arithmetic

- Expected event size: 160,016 bytes (`PMT_EVENT_SIZE=40004` words x 4 bytes/word)
- Buffer allocation: 162,208 bytes (160,016 + 2,192 overhead)
- Actual write attempt: 312,596 bytes
- Overflow: 312,596 - 162,208 = 150,388 bytes beyond buffer boundary
- Ratio: 312,596 / 162,208 = 1.928x buffer capacity

### Corrupted Event Shortfall

- Expected: 160,016 bytes
- Received: 128,612 bytes
- Shortfall: 31,404 bytes (19.6% missing)
