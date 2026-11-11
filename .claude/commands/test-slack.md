# Test Slack Bot Live

Automated workflow to start the Slack bot and run live tests with slacktesterbot.

## Workflow

Execute this workflow step by step:

### Step 1: Start the Slack Bot

Start the Slack bot in the background:

```bash
./slackbot.sh
```

Run this command in the background and wait for startup confirmation. Look for:
```
[INFO] Starting Slack bot in Socket Mode...
Starting Slack bot (Socket Mode)...
```

The bot must show "Starting Slack bot" before proceeding.

### Step 2: Run Live Tests

Run the slacktesterbot in live mode against the running bot:

```bash
./tools/slacktesterbot/slacktester.sh live
```

**Options:**
- `--test <name>` / `-t <name>` - Run specific test only
- `--timeout <seconds>` - Response timeout (default: 120)
- `--config <path>` / `-c <path>` - Path to config file
- `--last-investigation` / `-l` - Use most recent investigation for binder/artifact tests

### Step 3: Analyze Results

Review the test output. All 12 tests should pass:

| Test | Description | What It Tests |
|------|-------------|---------------|
| `help` | Help command | Shows available commands |
| `version` | Version command | Returns bot version |
| `config` | Config show | Displays current settings |
| `list` | List investigations | Shows recent investigations |
| `wb_list` | Workbinder list | Lists all binders |
| `wb_show` | Workbinder show | Shows binder details |
| `wb_artifacts` | Workbinder artifacts | Lists artifacts for a binder |
| `wb_artifact` | Single artifact | Shows single artifact content |
| `wb_artifact_all` | Export all artifacts | Exports all artifacts as markdown |
| `wb_search` | Workbinder search | Searches artifacts by query |
| `wb_history` | Workbinder history | Shows binder history |
| `wb_audit` | Workbinder audit | Shows audit trail |

**Total: 12 live tests**

### Step 4: Stop the Slack Bot

After testing, stop the background Slack bot process.

## Troubleshooting

### Connection Errors

**Error:** `Could not connect to Slack`
- **Cause:** Invalid Slack credentials or network issue
- **Fix:** Check `tools/slacktesterbot/config.yaml` for correct Slack tokens

**Error:** `missing_scope: channels:join`
- **Cause:** Bot token missing required OAuth scope
- **Fix:** This is a warning; bot can still work if already in channel

### Bot Startup Errors

**Error:** `ModuleNotFoundError: No module named 'X'`
- **Cause:** Missing dependency
- **Fix:** Run `./setup.sh` to install dependencies

**Error:** `SLACK_BOT_TOKEN not set`
- **Cause:** Missing environment variable
- **Fix:** Set token in environment or config file

### Test Failures

**Error:** `No investigation IDs found`
- **Cause:** No investigations in database
- **Fix:** Run an investigation first with `./run.sh investigate <logfile>`

**Error:** `Expected 'X' not found in response`
- **Cause:** Bot returned unexpected response format
- **Fix:** Check slackbot output for errors; may be data-dependent

**Error:** `Timeout waiting for response`
- **Cause:** Bot not responding or slow
- **Fix:** Increase timeout with `--timeout 180`

### Common Issues

**Issue:** `Unknown artifact type: ArtifactType.CONCLUSION`
- **Cause:** Historical investigation has artifact types not in current schema
- **Impact:** Warning only; tests may still pass
- **Fix:** Safe to ignore unless tests fail consistently

**Issue:** Tests pass individually but fail in batch
- **Cause:** Random investigation selection hit problematic data
- **Fix:** Re-run tests; they use random investigation IDs

**Issue:** `wb_artifact_all` intermittent failures
- **Cause:** Some investigations have artifacts that can't be loaded
- **Fix:** Re-run; different investigation will be selected

## Running Specific Tests

```bash
# Run only help test
./tools/slacktesterbot/slacktester.sh live --test help

# Run only workbinder tests
./tools/slacktesterbot/slacktester.sh live --test wb_list
./tools/slacktesterbot/slacktester.sh live --test wb_show
./tools/slacktesterbot/slacktester.sh live --test wb_artifact_all

# Run with longer timeout
./tools/slacktesterbot/slacktester.sh live --timeout 180

# Use specific investigation for binder tests
./tools/slacktesterbot/slacktester.sh live --last-investigation
```

## Running Mock Tests (No Slack Connection)

For testing command parsing without Slack:

```bash
# Run all mock scenarios
./tools/slacktesterbot/slacktester.sh run

# Run specific scenario
./tools/slacktesterbot/slacktester.sh run --scenario investigate

# List available scenarios
./tools/slacktesterbot/slacktester.sh list

# Verbose output
./tools/slacktesterbot/slacktester.sh run --verbose

# JSON output for CI/CD
./tools/slacktesterbot/slacktester.sh run --json
```

## Checking Bot Output

Monitor the Slack bot logs for errors during testing:

```bash
# Bot should show successful startup:
[INFO] Starting Slack bot in Socket Mode...
Starting Slack bot (Socket Mode)...

# Warnings about artifact types are normal:
WARNING: srcs.workbinder.persistence: Unknown artifact type: ArtifactType.CONCLUSION
```

## Quick Reference

| Task | Command |
|------|---------|
| Start Slack bot | `./slackbot.sh` |
| Run all live tests | `./tools/slacktesterbot/slacktester.sh live` |
| Run specific test | `./tools/slacktesterbot/slacktester.sh live --test <name>` |
| Run mock tests | `./tools/slacktesterbot/slacktester.sh run` |
| List mock scenarios | `./tools/slacktesterbot/slacktester.sh list` |
| Run specific scenario | `./tools/slacktesterbot/slacktester.sh run --scenario <name>` |

## Expected Success Output

```
Running 12 live tests against LogAnalyzer Bot...
Timeout: 120s per test

============================================================

[help] Test help command
  Command: help
  Status: PASS (4811ms)
  ...

[version] Test version command
  Command: version
  Status: PASS (4789ms)
  ...

... (10 more tests)

============================================================

Results: 12 passed, 0 failed
```
