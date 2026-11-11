# artdaq Deep Investigation Agent

LLM-powered root cause analysis tool for artdaq DAQ (Data Acquisition) software.

This is the deployment build of `log-analyzer-agent`. `config.yaml`,
`tools/*/config.yaml`, `requirements.txt` and `constraints.txt` are kept identical
to the development repo; don't let them drift.

## 1. Environment setup

Prerequisites: Python 3.10+, `git`, `curl`, network access to GitHub (source
repos) and to the LLM gateway.

```bash
./setup.sh                # creates ./venv, installs requirements.txt + this package, creates ./data
source venv/bin/activate  # optional; the wrapper scripts activate it themselves
```

### Secrets: `.env`

The API server (and through it the Slack bot) reads LLM settings from `.env`
in the project root (gitignored; `slackbot.sh` and `run.sh` source it). Copy it
from the dev repo, or create it with:

```bash
ARTDAQ_LLM_PROVIDER=openrouter
ARTDAQ_OPENROUTER_BASE_URL=<FNAL LiteLLM gateway URL>
ARTDAQ_OPENROUTER_MODEL=<model>
ARTDAQ_OPENROUTER_REASONING_EFFORT=medium
ARTDAQ_LLM_MAX_TOKENS=50000          # match config.yaml llm.max_tokens
ARTDAQ_EMBEDDING_PROVIDER=openai
ARTDAQ_EMBEDDING_HOST=<gateway URL>
ARTDAQ_EMBEDDING_MODEL=<embedding model>
ARTDAQ_OPENROUTER_API_KEY=sk-...      # virtual key from https://llm-keys.fnal.gov/
```

Slack credentials are read from the `slack:` section of `config.yaml` (bot and
tester/monitor tokens in `tools/slacktesterbot/config.yaml` and
`tools/slackmonitorbot/config.yaml`). You can also set them with
`LOGANALYZER_SLACK_BOT_BOT_TOKEN`, `LOGANALYZER_SLACK_BOT_APP_TOKEN`, and
`LOGANALYZER_SLACK_BOT_SIGNING_SECRET` (HTTP mode only).

## 2. Initialize the knowledge base and source code index

`init` runs through the REST API, so start the API server first:

```bash
./run.sh api &                                   # API on :8000
until curl -s localhost:8000/health; do sleep 1; done

./run.sh init                                    # == artdaq-agent init
```

`init` does the following:

| Step | Result |
|------|--------|
| `create_directories` | `data/` |
| `init_database` | `data/knowledge.db` (SQLite knowledge base) |
| `sync_source` | clones/updates the repos listed under `source.repositories` in `config.yaml` into `data/repos/` |
| `build_index` | `data/code_index.db` (functions, classes, call graph), about 465 files / 3500 functions |

Useful variants:

```bash
artdaq-agent init --skip-source   # DB only, don't touch repos
artdaq-agent sync-source          # re-pull repos and rebuild the code index later
```

Stop the API when you're done (`kill %1`); `slackbot.sh` starts its own.

### Slack channel settings

`data/slack_config.json` holds per-channel output overrides (verbose /
llm_logging / full_output) that the bot reads at startup. Without it, the bot
falls back to the `output:` section of `config.yaml`. To match dev
behaviour in the test channel `C08827X3MSN`, use:

```json
{
  "C08827X3MSN": { "verbose": true, "llm_logging": false, "full_output": false }
}
```

## 3. Running the Slack bot

```bash
./slackbot.sh &> slack-out.txt &   # starts API server on :8000 + bot in Socket Mode
./slackbot.sh --status
./slackbot.sh --stop
```

Startup is good when `slack-out.txt` shows `API server ready` and
`Announced connection to C08827X3MSN`.

> **Only one bot per Slack app.** Dev (`~/work/log-analyzer-agent`) and this
> deployment use the same Slack app tokens. If both bots are connected,
> Socket Mode splits events between them, so tests become flaky. Also,
> `slackbot.sh` restarts any `uvicorn srcs.api` already on port 8000. Stop the
> other checkout's bot first (`<other-repo>/slackbot.sh --stop`).

## 4. Running tests

All Slack tests drive the real bot in the test channel through two helper
bots. Each helper creates its own venv on first run.

| Tool | Purpose |
|------|---------|
| `tools/slacktesterbot/slacktester.sh` | **Sends** messages to the bot and checks replies |
| `tools/slackmonitorbot/slackmonitor.sh` | **Watches** the channel and writes `slack-monitor.log` / `slack-monitor.status` |
| `tools/mcptester/mcptester.sh` | Tests the MCP server |

### 4.1 Mock tests (no Slack connection)

```bash
./tools/slacktesterbot/slacktester.sh list               # scenarios
./tools/slacktesterbot/slacktester.sh run [--verbose]    # all scenarios
./tools/slacktesterbot/slacktester.sh run --scenario investigate
```

### 4.2 Live command tests (12 tests)

With the bot running:

```bash
./tools/slacktesterbot/slacktester.sh live                  # help, version, config, list, wb_* ...
./tools/slacktesterbot/slacktester.sh live --test wb_list    # single test
./tools/slacktesterbot/slacktester.sh live --timeout 180 --last-investigation
```

Expected result: `Results: 12 passed, 0 failed`. The `wb_*` tests need at least one
investigation in `data/knowledge.db`. On a fresh install, run 4.3 first.

### 4.3 Live investigation test

```bash
./tools/slackmonitorbot/slackmonitor.sh start --timeout 300 &
./tools/slacktesterbot/slacktester.sh send "message applyRequestsWindowMode_CheckAndFillDataBuffer: A timeout occurred waiting for data to close the request window ({1768598689260608328-1768598689263608328}, buffer={1768598677121537664-1768598687094584432} ). Time waiting: 10001038 us (> 10000000 us)." --timeout 300
./tools/slackmonitorbot/slackmonitor.sh status
```

The investigation takes 2–5 minutes. Expected conclusion: **data pipeline latency**
at `FragmentBuffer.cc:612`. Incoming fragments are about 2.2 s behind the request
window. Follow progress in `slack-out.txt` and `slack-monitor.log`.

### 4.4 Run 14001 end-to-end (log file attachments)

Test fixtures are in `examples/run14001/`: seven board logs plus
`INVESTIGATION.md`, the reference root-cause analysis that results are graded
against. Submit them all in one message:

```bash
./tools/slacktesterbot/slacktester.sh send \
    "investigate Run 14001 CAEN V1730 failure cascade: 7 board logs from hardware failure on FragID 8194 (wwtop03). Analyze each log for root cause and cascade relationship." \
    --files "examples/run14001/*.log" --timeout 900
```

Or run them through the CLI without Slack:

```bash
./run.sh investigate examples/run14001/run14001-icaruspmtwwtop03.log -e 2
```

### 4.5 Claude Code skills

`.claude/commands/` contains the same test workflows as slash commands. Each one
starts the bot and monitor, runs the steps above, and analyzes the results:

| Command | What it runs |
|---------|--------------|
| `/test-slack` | 4.2, the 12 live command tests |
| `/test-slackbot [--message "..."]` | 4.3, plus a WorkBinder / pipeline-quality report |
| `/test-run14001-slack [board]` | 4.4 through Slack, compared against `INVESTIGATION.md` |
| `/submit-run14001` | 4.4 through the CLI/API |

### Cleanup

```bash
./slackbot.sh --stop
pkill -f "slackmonitor|slacktester"
```
