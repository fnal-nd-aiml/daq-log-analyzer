# Test Slack Bot Live (Debug)

Debug workflow for the Slack bot with focus on **pipeline quality assessment**, **WorkBinder artifact efficiency**, and **LLM-first processing verification**.

## Purpose

This skill goes beyond functional testing to evaluate:
1. **WorkBinder Efficiency** - Are artifacts stored and retrieved properly for investigation convergence?
2. **LLM-First Processing** - Is the pipeline using LLM-based parsing, or falling back to hardcoded regex?
3. **Archivist Precision** - Is source code analysis leveraging prior knowledge effectively?
4. **Cross-Phase Artifact Usage** - Do all phases use binder artifacts thoughtfully?

## Arguments

- `$ARGUMENTS` - Description of what needs debugging (context for you, NOT a message to send)
- Optional: `--message "text"` - Custom error message to send to the bot (overrides default)

**If no arguments are provided**, use this default analysis prompt:

> Run the test and carefully observe each message in the thread, as well as each attached file. Evaluate how the investigation is conducted using the WorkBinder Checklist and Pipeline Quality Rubric below. Give this the Gordon Ramsay treatment. Be surgical. What's wrong with artifact flow? Where is hardcoded parsing failing? What needs to be completely redone?

## MANDATORY: Send Error Message to Trigger Investigation

**YOU MUST ALWAYS send an error message to trigger an investigation.** This is the primary purpose of this skill.

1. Check if `$ARGUMENTS` contains `--message "text"` flag
2. If YES: Extract the text and use it as the error message
3. If NO: Use this default error message:

```
applyRequestsWindowMode_CheckAndFillDataBuffer: A timeout occurred waiting for data to close the request window ({1768598689260608328-1768598689263608328}, buffer={1768598677121537664-1768598687094584432} ). Time waiting: 10001038 us (> 10000000 us).
```

**DO NOT** substitute with "help", "version", or other simple commands. The goal is to test the investigation pipeline.

---

## Investigation Pipeline Phases

When an error message is sent, the bot runs through these phases (typically 2-4 minutes total):

| Phase | Persona | Description | Key Artifacts |
|-------|---------|-------------|---------------|
| 0 | **Archivist** | Retrieves prior knowledge: similar cases, patterns, code hints | SourceLocationArtifact, CodeSnippet, CallGraphNode |
| 1 | **Theorist** | Generates ranked root cause hypotheses | HypothesisArtifact (with prior scores) |
| 2 | **Detective** | Iteratively gathers discriminating evidence | EvidenceArtifact, EvidenceQueryArtifact |
| 3 | **Chain Builder** | Constructs causal chains with evidence citations | CausalChainArtifact |
| 4 | **Critic** | Adversarial review: challenges conclusions | ChallengeArtifact |
| 5 | **Insufficiency Check** | Determines outcome confidence level | - |
| 6 | **Synthesizer** | Generates final report with calibrated confidence | ConclusionArtifact |
| 7 | **Learner** | Extracts patterns for future investigations | - |

**Possible Outcomes:** `CONFIDENT`, `PROBABLE`, `UNCERTAIN`, `CONTRADICTORY`, `INSUFFICIENT`

---

## WorkBinder Quality Checklist

When analyzing investigation results, verify artifact creation and usage:

### Phase 0 (Archivist) Artifacts
- [ ] SourceLocationArtifact created with function body attached
- [ ] CodeSnippet artifacts stored for found functions
- [ ] CallGraphNode artifacts include caller/callee bodies
- [ ] Prior knowledge patterns stored as artifacts (not just returned)
- [ ] Error context with parsed numeric values stored

### Phase 1 (Theorist) Artifacts
- [ ] Hypotheses reference specific code locations from binder
- [ ] Numeric values from error are parsed and used in scoring
- [ ] Prior patterns are cited in hypothesis descriptions
- [ ] Initial scores reflect prior knowledge confidence

### Phase 2 (Detective) Artifacts
- [ ] Evidence queries are logged as artifacts
- [ ] Code lookups reference existing binder artifacts first
- [ ] New evidence is linked to hypotheses bidirectionally
- [ ] Score evolution is tracked (which evidence mattered)

### Phase 3-4 (Logician/Critic) Artifacts
- [ ] Causal chains cite evidence artifact IDs
- [ ] Challenges reference specific hypothesis artifacts
- [ ] Assumptions are explicitly marked

### Verification Commands

After investigation completes, check binder state:
```bash
# List all artifacts in binder
./tools/slacktesterbot/slacktester.sh send "workbinder list"

# Get specific artifact details
./tools/slacktesterbot/slacktester.sh send "workbinder get <artifact_id>"
```

---

## LLM-First Processing Verification

### What to Check in Logs

Look for these patterns in `slack-out.txt`:

**GOOD Signs (LLM-First):**
- `Using structured generation for hypothesis extraction`
- `LLM-based relevance scoring`
- `Semantic code hint extraction`
- `LLM JSON repair successful`

**BAD Signs (Regex Fallback):**
- `Falling back to regex extraction`
- `JSON parse failed, attempting regex repair`
- `Using pattern-based relevance scoring`
- `Bulleted list regex extraction`

### Known Hardcoded Regex Locations

These are the files where regex fallbacks may occur - watch for failures here:

| File | Lines | Current Issue | What Should Happen |
|------|-------|---------------|-------------------|
| `llm/anthropic.py` | 159-185 | JSON extraction/repair | LLM should fix malformed JSON |
| `llm/ollama.py` | 148-196 | Same JSON repair | Same - use LLM |
| `agent/hypotheses.py` | 309-339 | Bulleted list parsing | LLM structured extraction |
| `agent/evidence.py` | 1016-1133 | 30+ relevance patterns | LLM relevance scoring |
| `agent/dataflow.py` | 59-316 | Code hint extraction | LLM semantic hint extraction |
| `agent/chains.py` | 387-455 | Evidence-to-step linking | LLM semantic matching |

### Debug Log Patterns to Check

```bash
# Source location finding
grep "INFO: srcs.agent.prior_retrieval:" slack-out.txt

# JSON parsing fallbacks
grep "WARNING: srcs.llm:" slack-out.txt

# Artifact creation
grep "INFO: srcs.workbinder:" slack-out.txt

# Hypothesis scoring
grep "DEBUG: srcs.agent.hypotheses:" slack-out.txt
```

---

## Expected Artifact Flow

### Ideal Phase 0 Output
- 1x ErrorContextArtifact (with parsed timestamps, durations)
- N x SourceLocationArtifact (with match scores and function bodies)
- N x CodeSnippet (complete function implementations)
- N x CallGraphNode (with caller/callee bodies)
- 1x PatternMatchArtifact (if prior pattern matched)

### Ideal Phase 1 Output
- N x HypothesisArtifact (scores initialized from prior knowledge)
- References to Phase 0 artifacts in hypothesis descriptions

### Ideal Phase 2 Output
- N x EvidenceArtifact (bidirectionally linked to hypotheses)
- N x EvidenceQueryArtifact (record of what was asked)
- Updated hypothesis scores with audit trail

### Ideal Phase 3-6 Output
- N x CausalChainArtifact (with evidence citations)
- N x ChallengeArtifact (referencing specific hypotheses)
- 1x ConclusionArtifact (with confidence justification)

---

## Pipeline Quality Rubric

### Grade A: Excellent (Converges to CONFIDENT)
- Source code found in Phase 0 with correct function body
- Hypotheses cite specific code locations and numeric values
- Evidence directly supports/refutes hypotheses
- Causal chain is complete with artifact citations
- All relevant binder artifacts are used across phases

### Grade B: Good (Converges to PROBABLE)
- Source code found but not fully utilized
- Hypotheses are somewhat specific
- Some evidence gaps or missing citations
- Causal chain has minor gaps
- Some binder artifacts created but not referenced later

### Grade C: Poor (Returns UNCERTAIN/INSUFFICIENT)
- Source code not found or not used
- Hypotheses are generic (no code/number references)
- Evidence doesn't discriminate between hypotheses
- Causal chain has major gaps
- Binder artifacts isolated per phase (no cross-reference)

### Grade D: Failing (System Errors)
- LLM parsing failures (regex fallbacks logged)
- Binder artifacts missing entirely
- Phase failures or timeouts
- JSON extraction errors in logs

---

## Workflow

### Step 1: Start Slack Bot in Background

```bash
./slackbot.sh &> slack-out.txt &
```

Wait for startup confirmation:
```bash
sleep 3 && grep -q "Starting Slack bot" slack-out.txt && echo "Bot started"
```

### Step 2: Start Slack Monitor in Background

```bash
./tools/slackmonitorbot/slackmonitor.sh start --timeout 300 &
```

### Step 3: Verify Services Ready

```bash
sleep 5
./tools/slackmonitorbot/slackmonitor.sh status
```

### Step 4: Send Error Message to Bot (MANDATORY)

**THIS STEP IS REQUIRED.** Send an error message to trigger an investigation.

Parse `$ARGUMENTS` for `--message "text"` flag:

**If `--message` flag is present**, extract the text and run:
```bash
./tools/slacktesterbot/slacktester.sh send "message <EXTRACTED_TEXT>" --timeout 300
```

**If NO `--message` flag** (common case), run this exact command:
```bash
./tools/slacktesterbot/slacktester.sh send "message applyRequestsWindowMode_CheckAndFillDataBuffer: A timeout occurred waiting for data to close the request window ({1768598689260608328-1768598689263608328}, buffer={1768598677121537664-1768598687094584432} ). Time waiting: 10001038 us (> 10000000 us)." --timeout 300
```

**DO NOT skip this step or substitute with "help" or other commands.**

### Step 5: Wait for Investigation and Check Results

Wait for investigation to complete (30-120 seconds):
```bash
sleep 60
```

Check bot output for phase progression and artifacts:
```bash
cat slack-out.txt
```

Check monitor status:
```bash
./tools/slackmonitorbot/slackmonitor.sh status
```

### Step 6: Analyze Pipeline Quality

Use the **WorkBinder Checklist** and **Pipeline Quality Rubric** above to assess:

1. **Artifact Creation**: Are all expected artifacts present?
2. **Cross-Phase References**: Do later phases cite earlier artifacts?
3. **LLM Processing**: Any regex fallback warnings in logs?
4. **Final Outcome**: Does confidence level match evidence quality?

### Step 7: Check Binder State (Optional)

```bash
./tools/slacktesterbot/slacktester.sh send "workbinder list"
```

### Step 8: Cleanup

```bash
pkill -f "slackbot.sh|slackmonitor|artdaq-agent slack"
```

---

## Tool Responsibilities

**./slackbot.sh**
- The LogAnalyzer bot that receives and investigates error messages
- Start this FIRST before any testing

**./tools/slackmonitorbot/slackmonitor.sh**
- ONLY for MONITORING Slack channel communication
- Use `start` to begin monitoring, `status` to check
- DO NOT use `send` command - use slacktester.sh instead

**./tools/slacktesterbot/slacktester.sh**
- MUST be used for SENDING error messages to the bot
- Use `send "command"` to send any command to the bot
- Target bot ID: `U0ABYV0N545`

---

## Available Commands Reference

| Tool | Command | Description |
|------|---------|-------------|
| `slackbot.sh` | (no args) | Start the LogAnalyzer Slack bot |
| `slackmonitor.sh` | `start` | Start monitoring channel |
| `slackmonitor.sh` | `start --timeout N` | Monitor for N seconds |
| `slackmonitor.sh` | `status` | Check monitor status |
| `slacktester.sh` | `send "text"` | Send custom message to bot |
| `slacktester.sh` | `live` | Run all live tests |
| `slacktester.sh` | `run` | Run mock tests (no Slack) |

## Message Format Examples

| Intent | Command |
|--------|---------|
| Get help | `help` |
| Get version | `version` |
| Show config | `config` |
| Investigate error | `message <error text>` |
| List investigations | `list` |
| Show workbinder | `workbinder list` |
| Get artifact | `workbinder get <id>` |

---

## Troubleshooting

### Bot Not Starting
```bash
cat slack-out.txt | grep -i error
```

### No Response from Bot
1. Verify bot is running: `pgrep -f slackbot`
2. Check monitor status: `./tools/slackmonitorbot/slackmonitor.sh status`
3. Increase timeout: `--timeout 300`

### Connection Errors
Check config files for valid Slack tokens:
- `tools/slackmonitorbot/config.yaml`
- `tools/slacktesterbot/config.yaml`

---

## Known Issues to Watch For

1. **Binder tool instructions confusing the LLM** - If LLM outputs "We will use get_artifact..." instead of JSON, check if `include_tool_instructions=True` is being passed to `BinderSerializer.serialize_for_prompt()`. Should be `False` for structured generation.

2. **JSON parsing failures** - If `generate_structured()` fails:
   - Is the prompt too long/complex?
   - Are there conflicting instructions?
   - Check for regex fallback warnings

3. **Empty or invalid responses** - Consider two-step approach:
   - Step 1: LLM generates natural language analysis
   - Step 2: Second LLM call extracts structured data

4. **Artifacts not linked across phases** - Check if:
   - Phase 1 hypotheses reference Phase 0 code snippets
   - Phase 2 evidence links back to hypothesis IDs
   - Phase 3 chains cite evidence artifact IDs

---

## IMPORTANT: Expected Investigation Outcome

Given proper source code analysis, the correct conclusion would be:

**CONFIDENT: Data pipeline latency**

The applyRequestsWindowMode_CheckAndFillDataBuffer timeout at FragmentBuffer.cc:612 occurs because incoming data fragments are ~2.2 seconds behind the request window. The buffer's latest timestamp (1768598687094584432) never reaches the required window maximum (1768598689263608328).

**Root Cause:** Upstream data production is not keeping pace with data requests. Either:
- The data source (BoardReader) is slow/stalled
- Network latency is causing fragment delivery delays
- The window_close_timeout_us_ (10s) is insufficient for the data rate

**Actionable Fixes:**
1. Check upstream BoardReader processes for errors/backlog
2. Increase window_close_timeout_us_ if data source is legitimately slow
3. Investigate timestamp synchronization if sources use different clocks

**Key Verification:** The pipeline should identify FragmentBuffer.cc:612 as the source location and extract the numeric timestamp values to justify the "2.2 seconds behind" calculation.
