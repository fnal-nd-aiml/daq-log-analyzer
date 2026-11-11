# Test Run 14001 via Slack Pipeline

End-to-end Slack pipeline test: starts slackmonitorbot, starts the Slack bot, submits run 14001 log files via slacktesterbot, monitors messages, then analyzes whether the bot handled them correctly.

## Arguments

`$ARGUMENTS` - Optional: `[board-filter]`

- **Board filter**: substring to match file names (default: all 7 files)

Examples: `/test-run14001-slack`, `/test-run14001-slack wwtop03`, `/test-run14001-slack ewbot`

---

## Log File Registry

All files are in `examples/run14001/`. Submit in this order (primary failure first):

| # | File | Board | Error Line | Description |
|---|------|-------|-----------|-------------|
| 1 | `run14001-icaruspmtwwtop03.log` | wwtop03 | 2 | Primary: wrong event size (FragID 8194) |
| 2 | `run14001-icaruspmtewbot01.log` | ewbot01 | 2 | Buffer overflow (312K into 162K buffer) |
| 3 | `run14001-pmt_icarus-evb11.log` | evb11 | 2 | Empty fragments in event builder |
| 4 | `run14001-icaruspmtewbot02.log` | ewbot02 | 10 | Sequence ID out of order (counter reset) |
| 5 | `run14001-icaruspmtewbot03.log` | ewbot03 | 7 | Sequence ID out of order (counter reset) |
| 6 | `run14001-icaruspmtwwtop01.log` | wwtop01 | 7 | Sequence ID out of order (counter reset) |
| 7 | `run14001-icaruspmtwwtop02.log` | wwtop02 | 10 | Sequence ID out of order (counter reset) |

---

## Workflow

### Step 1: Start Services

1. Start the Slack bot in the background:
   ```bash
   ./slackbot.sh &> slack-out.txt &
   ```
   Wait for startup confirmation:
   ```bash
   sleep 5 && grep -q "Starting Slack bot" slack-out.txt && echo "Bot started"
   ```

2. Start the Slack monitor:
   ```bash
   ./tools/slackmonitorbot/slackmonitor.sh start --timeout 600 &
   ```

3. Verify both services are running:
   ```bash
   sleep 5
   ./tools/slackmonitorbot/slackmonitor.sh status
   ```
   Confirm the monitor shows `connected: true`.

### Step 2: Submit ALL Log Files in a Single Message

**CRITICAL: All files MUST be submitted together in ONE Slack message with ALL files attached.**
The bot will process each file as a separate investigation automatically. Do NOT submit files
individually.

Parse `$ARGUMENTS` for a board filter substring. If provided, use a glob pattern that matches
only the filtered files.

Submit all files at once using a glob pattern, with a descriptive message that clearly states
what needs to be investigated:

```bash
# Submit all 7 files in one message (default)
./tools/slacktesterbot/slacktester.sh send \
  "investigate Run 14001 CAEN V1730 failure cascade: 7 board logs from hardware failure on FragID 8194 (wwtop03). Analyze each log for root cause and cascade relationship." \
  --files "examples/run14001/*.log" --timeout 900

# Or with board filter (e.g., only ewbot boards)
./tools/slacktesterbot/slacktester.sh send \
  "investigate Run 14001 cascade boards: event counter resets and sequence ID errors" \
  --files "examples/run14001/*ewbot*.log" --timeout 600
```

**Important notes:**
- The `error=N` option is omitted because it applies globally to all files and each file has a
  different error line. The bot auto-detects the primary error in each file.
- The descriptive text after `investigate` is visible in the Slack channel as context.
- The bot iterates over all attached files and kicks off a separate investigation for each one.
- Use a long timeout (900s) since 7 concurrent investigations with Ollama will be slow.

After submission, print confirmation: "All files submitted in one message. Monitoring for results..."

### Step 3: Monitor Analysis

After all submissions complete:

1. Read `slack-monitor.log` -- shows all channel messages (file uploads + bot responses):
   ```bash
   cat slack-monitor.log
   ```

2. Read `slack-out.txt` -- shows bot internal logs (pipeline phases, errors):
   ```bash
   cat slack-out.txt
   ```

Check the monitor log for:
- File upload messages (one per file submitted)
- Bot acknowledgment messages ("Investigating...")
- Bot result messages (investigation outcomes)
- Any bot error messages

### Step 4: Verify Bot Correctness

Read `examples/run14001/INVESTIGATION.md` for the documented root cause analysis.

For each submitted file, verify the bot's response against the known analysis:

| Board | Expected Root Cause Keywords |
|-------|------------------------------|
| wwtop03 | "wrong event size", "FragID 8194", "CAEN", "hardware", "corrupted", "128612", "160016" |
| ewbot01 | "buffer overflow", "redzone", "worker thread", "memory corruption", "312596", "162208" |
| ewbot02 | "event counter reset", "sequence ID", "cascade", "counter.*1", "8214316" |
| ewbot03 | "event counter reset", "sequence ID", "cascade", "8214306" |
| wwtop01 | "event counter reset", "sequence ID", "cascade", "8127715" |
| wwtop02 | "event counter reset", "causality", "timestamp", "8127715" |
| evb11 | "empty fragment", "FragID 8194", "FragID 8207", "event builder", "74816" |

Check for each result:
- Did the bot return a result (not timeout)?
- Did the outcome include relevant keywords from the table above?
- Was the confidence level reasonable (CONFIDENT or PROBABLE for well-characterized failures)?
- Did the bot correctly identify the connection between cascade boards and the primary wwtop03 failure?

### Step 5: Pipeline Quality Assessment

Grade each investigation result:

| Grade | Criteria |
|-------|----------|
| **A** | CONFIDENT outcome with correct root cause identification. Keywords match. Cascade connection identified for secondary boards. |
| **B** | PROBABLE outcome with partially correct analysis. Some keywords match. General failure category correct. |
| **C** | UNCERTAIN or INSUFFICIENT outcome. Vague or generic analysis. Few keyword matches. |
| **D** | Error, timeout, or completely wrong analysis. No relevant keywords found. |

Print a summary table:

| File | Board | Grade | Outcome | Confidence | Keywords Match | Cascade Link |
|------|-------|-------|---------|------------|---------------|--------------|

Calculate overall pass rate: Grade A or B counts as pass.

### Step 6: Cleanup

1. Stop the Slack bot:
   ```bash
   pkill -f "slackbot.sh|artdaq-agent slack"
   ```

2. Stop the monitor (if still running):
   ```bash
   pkill -f "slackmonitor"
   ```

3. Print final summary:
   - Total files submitted
   - Pass/fail count (A/B = pass, C/D = fail)
   - Whether the primary failure (wwtop03) was correctly identified
   - Whether cascade relationship was detected across boards

---

## Expected Results

### Primary Failure (wwtop03)
The bot should identify this as a **CAEN V1730 hardware/firmware failure** on FragID 8194. The board returned 128,612 bytes instead of the expected 160,016 bytes, indicating a corrupted readout. This is the root cause of the entire cascade.

### Buffer Overflow (ewbot01)
The corrupted read from wwtop03 caused `CAENReadData()` to attempt writing 312,596 bytes into a 162,208-byte buffer, overwriting the memory redzone and crashing the `GetDataWorkerThread`.

### Event Builder (evb11)
Empty fragments appeared for FragIDs 8194, 8197, and 8207 across 153 events (74816-74969) over a 3.5-minute window.

### Cascade Boards (ewbot02, ewbot03, wwtop01, wwtop02)
All experienced event counter resets to 1 and sequence ID discontinuities caused by the primary failure propagating through the VME crate/optical link infrastructure. The bot should ideally reference the wwtop03 primary failure when analyzing these boards.

---

## Troubleshooting

### Bot Startup Failures
```bash
cat slack-out.txt | grep -i error
```
Common causes: missing Slack tokens, missing dependencies, port conflicts.

### Monitor Connection Errors
```bash
./tools/slackmonitorbot/slackmonitor.sh status
```
Check `tools/slackmonitorbot/config.yaml` for valid Slack credentials.

### File Upload Failures
If slacktesterbot cannot upload files:
1. Verify files exist: `ls examples/run14001/`
2. Check slacktesterbot config: `tools/slacktesterbot/config.yaml`
3. Ensure the bot has `files:write` scope

### Investigation Timeouts
If submissions time out (especially for the first file which seeds prior knowledge):
- Increase timeout: `--timeout 600`
- Check LLM provider connectivity
- Verify knowledge base is initialized: `./run.sh init`

### `missing_scope` Warnings
```
Warning: missing_scope: channels:join
```
Safe to ignore if the bot is already in the channel.

### No Response from Bot
1. Verify bot is running: `pgrep -f slackbot`
2. Check monitor status: `./tools/slackmonitorbot/slackmonitor.sh status`
3. Check bot logs: `cat slack-out.txt`

---

## Tool Responsibilities

| Tool | Purpose |
|------|---------|
| `./slackbot.sh` | The LogAnalyzer bot that receives and investigates error messages. Start FIRST. |
| `./tools/slackmonitorbot/slackmonitor.sh` | ONLY for MONITORING channel messages. Use `start` to begin, `status` to check. |
| `./tools/slacktesterbot/slacktester.sh` | MUST be used for SENDING messages and files to the bot. |

---

## Quick Reference

| Task | Command |
|------|---------|
| Test all 7 files | `/test-run14001-slack` |
| Test primary failure only | `/test-run14001-slack wwtop03` |
| Test cascade boards | `/test-run14001-slack ewbot` |
| Test event builder | `/test-run14001-slack evb11` |
