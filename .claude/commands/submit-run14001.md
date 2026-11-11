# Submit Run 14001 Log Files for Analysis

Submit the 7 log files from the CAEN V1730 digitizer hardware failure cascade (run 14001) via CLI, REST API, or Slack.

## Arguments

`$ARGUMENTS` - Optional: `[cli|api|slack|all] [board-filter]`

- **Interface**: `cli` (default), `api`, `slack`, or `all`
- **Board filter**: substring to match file names (e.g., `wwtop03`, `ewbot`)

Examples: `/submit-run14001`, `/submit-run14001 cli wwtop03`, `/submit-run14001 api`, `/submit-run14001 all ewbot`

---

## Log File Registry

All files are in `examples/run14001/`. Submit in this order (primary failure first to seed prior knowledge):

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

### Step 1: Parse Arguments and Show Plan

Parse `$ARGUMENTS` for the interface mode and optional board filter:

1. Split `$ARGUMENTS` into tokens
2. First token matching `cli|api|slack|all` sets the interface mode (default: `cli`)
3. Remaining tokens are the board filter substring
4. Filter the file list: only include files whose name contains the filter substring (if provided)

Print a table showing which files will be submitted and via which interface(s). Confirm with the user before proceeding.

### Step 2A: CLI Submission (mode `cli` or `all`)

For each file in submission order, run sequentially:

```bash
./run.sh investigate examples/run14001/<file> -e <error_line>
```

After each command:
- Capture the investigation ID from the output
- Note the outcome (CONFIDENT, PROBABLE, UNCERTAIN, etc.) and confidence score
- Print a one-line summary before proceeding to the next file

### Step 2B: REST API Submission (mode `api` or `all`)

1. Start the API server in the background:
   ```bash
   ./run.sh api --port 8000 &
   ```

2. Wait for server ready by polling the health endpoint:
   ```bash
   curl -s http://localhost:8000/api/v1/health
   ```
   Retry up to 30 times with 1-second sleep between attempts.

3. For each file in submission order, read the file content and POST:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/investigations/from-content \
     -H "Content-Type: application/json" \
     -d '{"content": "<file-content>", "error_line": <N>, "context_lines": 60}'
   ```
   Capture the investigation ID and status from the JSON response.

4. Stop the API server:
   ```bash
   pkill -f "run.sh api"
   ```

### Step 2C: Slack Bot Submission (mode `slack` or `all`)

1. Start the Slack bot in the background:
   ```bash
   ./slackbot.sh &> slack-out.txt &
   ```

2. Wait for startup confirmation:
   ```bash
   sleep 5 && grep -q "Starting Slack bot" slack-out.txt && echo "Bot started"
   ```

3. **Submit ALL files in a single message** with all files attached at once:
   ```bash
   ./tools/slacktesterbot/slacktester.sh send \
     "investigate Run 14001 CAEN V1730 failure cascade: 7 board logs from hardware failure on FragID 8194 (wwtop03). Analyze each log for root cause and cascade relationship." \
     --files "examples/run14001/*.log" --timeout 900
   ```

   Each file appears as a separate attachment in the Slack message. The bot processes each
   file as an independent investigation. The `error=N` option is omitted because it applies
   globally and each file has a different error line -- the bot auto-detects the primary error.

   If using a board filter, use a matching glob pattern:
   ```bash
   ./tools/slacktesterbot/slacktester.sh send \
     "investigate Run 14001 cascade boards: event counter resets" \
     --files "examples/run14001/*ewbot*.log" --timeout 600
   ```

   After submission, monitor `slack-out.txt` for all investigations to complete.

4. Stop the Slack bot:
   ```bash
   pkill -f "slackbot.sh|artdaq-agent slack"
   ```

### Step 3: Results Summary

Print a summary table with columns:

| File | Interface | Investigation ID | Outcome | Confidence |
|------|-----------|-----------------|---------|------------|

Note any failures or timeouts.

### Step 4: Cross-Reference with Known Analysis

Read `examples/run14001/INVESTIGATION.md` and compare automated results against the documented root cause analysis:

| Board | Expected Root Cause |
|-------|---------------------|
| wwtop03 | CAEN V1730 hardware/firmware failure, wrong event size, FragID 8194 corrupted readout |
| ewbot01 | Buffer overflow from corrupted read, redzone overwrite, worker thread crash |
| evb11 | Empty fragments for FragIDs 8194/8197/8207, event builder data loss |
| ewbot02 | Event counter reset to 1, sequence ID discontinuity from cascade |
| ewbot03 | Event counter reset to 1, cascade from primary failure |
| wwtop01 | Event counter reset to 1, cascade from primary failure |
| wwtop02 | Event counter reset to 1, causality violations, cascade |

For each result, note whether the automated analysis:
- Identified the correct root cause category
- Referenced the primary failure on wwtop03 (for cascade boards)
- Achieved appropriate confidence level

---

## Troubleshooting

### LLM Provider Not Configured
```
Error: No LLM provider configured
```
Set up the provider in `config.yaml` or via environment variables:
```bash
export ARTDAQ_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=your-key-here
```

### Ollama Not Running
```
Error: Connection refused to localhost:11434
```
Start Ollama: `ollama serve`

### API Server Won't Start
Check if port 8000 is already in use:
```bash
lsof -i :8000
```

### Slack Token Errors
```
Error: SLACK_BOT_TOKEN not set
```
Ensure tokens are configured in the Slack bot config file or environment.

### Investigation Timeouts
For Slack submissions, increase the timeout:
```bash
./tools/slacktesterbot/slacktester.sh send "investigate error=<N>" \
  --files examples/run14001/<file> --timeout 600
```

### Empty Results
If investigations return no hypotheses or evidence:
1. Verify the knowledge base is initialized: `./run.sh init`
2. Check that source repositories are synced: `./run.sh cli sync-source --status`
3. Ensure the error line number is correct for the file

---

## Quick Reference

| Task | Command |
|------|---------|
| Submit all via CLI | `/submit-run14001` or `/submit-run14001 cli` |
| Submit one file via CLI | `/submit-run14001 cli wwtop03` |
| Submit all via API | `/submit-run14001 api` |
| Submit cascade boards via Slack | `/submit-run14001 slack ewbot` |
| Submit all via all interfaces | `/submit-run14001 all` |
