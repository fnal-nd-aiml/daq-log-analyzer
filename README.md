# artdaq Deep Investigation Agent

An AI-powered log analysis and investigation system for [artdaq](https://github.com/art-daq/artdaq) data acquisition systems. The agent uses a multi-persona pipeline of LLM-backed specialists to automatically diagnose errors, build causal chains, and learn from past investigations.

Built for the [SBN](https://sbn.fnal.gov/) and artdaq communities at [Fermilab](https://www.fnal.gov/), this tool turns raw DAQ log output into structured root-cause analyses with confidence-calibrated conclusions.

---

## Table of Contents

- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
  - [Investigation Pipeline](#investigation-pipeline)
  - [Persona System](#persona-system)
  - [Knowledge Base and Learning](#knowledge-base-and-learning)
  - [WorkBinder Artifact System](#workbinder-artifact-system)
- [Interfaces](#interfaces)
  - [CLI](#cli)
  - [REST API](#rest-api)
  - [MCP Server](#mcp-server)
  - [Slack Bot](#slack-bot)
- [MessageSpy (UDP Log Capture)](#messagespy-udp-log-capture)
- [Source Code Analysis](#source-code-analysis)
- [Configuration](#configuration)
- [Getting Started](#getting-started)
- [Documentation](#documentation)

---

## What It Does

Given a DAQ log file or error message, the agent:

1. **Parses and triages** log entries, identifying the trigger error and surrounding context across multiple log files.
2. **Searches prior knowledge** for matching error patterns and similar past investigations.
3. **Generates ranked hypotheses** about the root cause using LLM-driven reasoning.
4. **Gathers evidence** iteratively, querying logs, source code, and documentation to support or refute each hypothesis.
5. **Builds causal chains** linking the evidence to a root cause through logical steps.
6. **Challenges its own conclusions** via an adversarial review phase.
7. **Produces a calibrated result** with a confidence score, root cause explanation, causal narrative, code references, and recommended debugging steps.
8. **Learns from outcomes** by extracting reusable error patterns and incorporating user feedback to improve future analyses.

---

## How It Works

### Investigation Pipeline

The investigation is driven by a configurable, phase-based pipeline engine. Each phase is executed by a specialized persona and produces typed artifacts that flow into subsequent phases. The pipeline supports fast paths for early termination, conditional branching, and named variants (e.g., `quick`, `thorough`) that adjust iteration counts and enable/disable phases.

The default pipeline phases are:

| Phase | Executor | Purpose |
|-------|----------|---------|
| **Log Bundle Analysis** | Chronicler | Merge and triage multi-file logs, identify the trigger error and relevant context |
| **Prior Retrieval** | Archivist | Search the knowledge base for matching patterns and similar past investigations |
| **Hypothesis Generation** | Theorist | Generate ranked hypotheses from multiple reasoning tiers |
| **Evidence Seeking** | Detective | Iteratively gather supporting and contradicting evidence for each hypothesis |
| **Causal Chains** | Logician | Construct logical causal chains from evidence to root cause |
| **Adversarial Review** | Skeptic | Challenge conclusions, identify gaps, and test alternative explanations |
| **Outcome Assessment** | Judge | Assess whether the investigation reached a confident, probable, uncertain, or insufficient outcome |
| **Synthesis** | Synthesizer | Produce the final structured result with root cause, confidence, caveats, and recommendations |
| **Learning** | Learner | Extract reusable error patterns and store them for future investigations |

The pipeline is fully declarative -- phases can be added, removed, reordered, or customized entirely through `config.yaml`. See the [Pipeline Configuration Specification](docs/PIPELINE_CONFIGURATION.md) for the full YAML syntax.

### Persona System

Each pipeline phase is powered by a **persona** -- a specialized LLM-backed agent with a defined role, prompt architecture, and set of capabilities. Personas collaborate through a shared artifact store (the WorkBinder) and follow a structured investigation methodology.

The 10 personas are:

- **Chronicler** -- Log triage specialist. Merges multi-file logs chronologically and identifies the trigger error.
- **Archivist** -- Knowledge retrieval specialist. Searches the pattern database and vector store for prior knowledge.
- **Theorist** -- Hypothesis generator. Produces ranked hypotheses across multiple reasoning tiers (pattern match, structural, creative).
- **Detective** -- Evidence seeker. Iteratively queries logs, code, and documentation to build the evidence base.
- **Logician** -- Causal reasoning specialist. Constructs and validates causal chains linking evidence to root causes.
- **Skeptic** -- Adversarial reviewer. Challenges conclusions, identifies logical gaps, and proposes alternative explanations.
- **Judge** -- Outcome assessor. Determines investigation confidence level and identifies evidence gaps.
- **Synthesizer** -- Result compiler. Produces the final structured analysis with recommendations.
- **Learner** -- Pattern extractor. Identifies reusable error patterns from completed investigations.
- **Reviewer** -- Feedback integrator. Incorporates user feedback to update pattern confidence and correctness.

Beyond the pipeline, personas also participate in an **Expert Panel** for ad-hoc Q&A. The panel orchestrator classifies questions by type (how-to, why, troubleshooting, comparison, etc.) and assembles the most relevant subset of personas, who then vote, deliberate, and synthesize a consensus answer.

### Knowledge Base and Learning

The agent maintains a hybrid knowledge store:

- **SQLite or PostgreSQL** for structured data: error patterns, investigation records, calibration metrics, feedback history, and analytics.
- **ChromaDB** for vector embeddings: enables semantic similarity search across past investigations and error signatures.

The **pattern learning** system uses Wilson score intervals for confidence estimation and supports:

- Automatic pattern extraction from completed investigations.
- Pattern merging when similar signatures are detected.
- Confidence decay for patterns that prove inaccurate over time.
- User feedback integration (correct/incorrect/partial) to refine pattern accuracy.
- Calibration tracking to measure and improve the agent's confidence reliability.

### WorkBinder Artifact System

The **WorkBinder** is the central artifact store through which all personas communicate during an investigation. It tracks 24 artifact types across 5 categories (context, code, investigation, observation, infrastructure), enforces a permissions model controlling which personas can read/write which artifacts, and maintains a full audit trail of every artifact mutation and LLM exchange.

---

## Interfaces

The agent exposes four interfaces, all backed by the same investigation engine:

### CLI

The primary command-line interface (`artdaq-agent`):

```bash
# Investigate a log file
./run.sh investigate path/to/logfile.log

# Investigate a specific error line with context
./run.sh investigate path/to/logfile.log -e 150 -c 50

# Investigate an error message directly
./run.sh investigate -m "Fragment receiver timed out after 30s"

# Pipe logs from stdin
cat logfile.log | ./run.sh investigate -

# Initialize the knowledge base
./run.sh init

# Ask the expert panel a question
./run.sh cli ask "Why does the fragment receiver timeout?"

# Submit feedback on an investigation
./run.sh feedback <investigation-id> --correct
./run.sh feedback <investigation-id> --incorrect --comment "The real cause was..."
```

### REST API

A FastAPI server exposing the full investigation capabilities over HTTP:

```bash
# Start the API server
./run.sh api                    # Default port 8000
./run.sh api --port 8080        # Custom port
./run.sh api --port 8080 --reload  # With hot reload
```

Endpoints include:
- `POST /api/v1/investigations` -- Submit an investigation
- `GET /api/v1/investigations` -- List recent investigations
- `GET /api/v1/patterns` -- List learned error patterns
- `GET /api/v1/calibration` -- View confidence calibration metrics
- `POST /api/v1/questions` -- Ask the expert panel
- `GET /api/v1/binders` -- Access investigation artifacts
- `GET /api/v1/metrics` -- Quality and performance metrics
- `POST /api/v1/admin/init` -- Initialize knowledge base

### MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server exposing 100+ tools for integration with Claude and other MCP-compatible clients:

```bash
# Start MCP server (stdio transport, for Claude Desktop / Claude Code)
./run.sh mcp

# Start MCP server with SSE transport (for web clients)
./run.sh mcp --sse --port 8001
```

Tools are organized into groups: investigation, pattern management, knowledge retrieval, calibration, Q&A, code analysis, artifact access, meta-learning, and administration.

### Slack Bot

A Slack bot for team-based investigation directly from Slack channels:

```bash
./run.sh cli slack
```

Supports Socket Mode (WebSocket) and HTTP mode. Configure bot tokens and app tokens in `config.yaml` or via environment variables.

---

## MessageSpy (UDP Log Capture)

The built-in **MessageSpy** captures live [MessageFacility](https://cdcvs.fnal.gov/redmine/projects/messagefacility/wiki) UDP messages from running artdaq processes. It provides:

- UDP and multicast reception.
- Field-based filtering (severity, hostname, application, category) with glob patterns.
- Duplicate message throttling with configurable repeat limits.
- Batched asynchronous file writing with configurable flush intervals.

Configure MessageSpy in the `msgspy:` section of `config.yaml`.

---

## Source Code Analysis

The agent can clone and index artdaq source repositories to enhance investigations with code-level evidence:

- Automatic shallow cloning of configured GitHub repositories (artdaq, artdaq_core, sbndaq, etc.).
- Tree-sitter-based code parsing for C++ and Python.
- Function summarization, call graph extraction, and source location lookup.
- Code snippet retrieval for inclusion in investigation results.

Configure repositories in the `source:` section of `config.yaml`.

---

## Configuration

All configuration lives in `config.yaml`. Key sections:

| Section | Purpose |
|---------|---------|
| `llm` | LLM provider selection (Ollama, Anthropic, OpenRouter), model names, temperature, embedding config |
| `storage` | Knowledge store backend (SQLite or PostgreSQL), database paths |
| `investigation` | Max hypotheses, evidence iterations, chain depth, confidence bounds |
| `pipeline` | Phase definitions, fast paths, variants, conditional branches, hooks |
| `output` | Verbose mode, LLM logging, full output display |
| `slack` | Slack bot tokens, socket mode, queue depth |
| `msgspy` | UDP capture port, multicast, filtering, throttling |
| `source` | Git repositories to clone, authentication, auto-indexing |

LLM providers supported:
- **Ollama** -- Local models (default)
- **Anthropic** -- Claude API (direct or via custom vLLM endpoint)
- **OpenRouter** -- Multi-provider routing

---

## Getting Started

### Prerequisites

- Python 3.10+
- An LLM provider: [Ollama](https://ollama.ai/) running locally (default), or an Anthropic/OpenRouter API key

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd daq-log-analyzer2

# Run setup (creates virtual environment and installs dependencies)
./setup.sh

# Initialize the knowledge base
./run.sh init

# Run your first investigation
./run.sh investigate path/to/your/logfile.log
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (when using Anthropic provider) |
| `ARTDAQ_OPENROUTER_API_KEY` | OpenRouter API key |
| `ARTDAQ_POSTGRES_PASSWORD` | PostgreSQL password (when using PostgreSQL backend) |
| `ARTDAQ_GITHUB_TOKEN` | GitHub token for private repository access |
| `ARTDAQ_API_URL` | REST API base URL (for CLI to send results to API) |

---

## Documentation

### Pipeline Configuration

- [Pipeline Configuration Specification](docs/PIPELINE_CONFIGURATION.md) -- Full YAML syntax for defining pipeline phases, fast paths, variants, branches, and hooks.

### REST API Design

- [Agentic REST Service Design](docs/agentic-rest-service-design.md) -- Overview of the agentic REST API architecture.
  - [Ch 1: Architecture & Session Management](docs/agentic-rest-service-design-ch1-architecture.md)
  - [Ch 2: Log Analysis Tools](docs/agentic-rest-service-design-ch2-log-analysis-tools.md)
  - [Ch 3: Code Analysis Tools](docs/agentic-rest-service-design-ch3-code-analysis-tools.md)
  - [Ch 4: Knowledge & Finding Tools](docs/agentic-rest-service-design-ch4-knowledge-finding-tools.md)
  - [Ch 5: Pipeline, Expert & Admin Tools](docs/agentic-rest-service-design-ch5-pipeline-admin-tools.md)
  - [Ch 6: Client Refactoring Guide](docs/agentic-rest-service-design-ch6-client-refactoring.md)
  - [Ch 7: Testing Strategy](docs/agentic-rest-service-design-ch7-testing-strategy.md)

### WorkBinder Library

- [Agentic WorkBinder Library](docs/agentic-workbinder-library.md) -- Overview of the artifact store, permissions model, and audit system.
  - [Ch 1: Architecture](docs/agentic-workbinder-library-ch1-architecture.md)
  - [Ch 2: Context Artifacts](docs/agentic-workbinder-library-ch2-context-artifacts.md)
  - [Ch 3: Code Artifacts](docs/agentic-workbinder-library-ch3-code-artifacts.md)
  - [Ch 4: Investigation Artifacts](docs/agentic-workbinder-library-ch4-investigation-artifacts.md)
  - [Ch 5: Observation Artifacts](docs/agentic-workbinder-library-ch5-observation-artifacts.md)
  - [Ch 6: Infrastructure Artifacts](docs/agentic-workbinder-library-ch6-infrastructure-artifacts.md)
  - [Ch 7: Tools & Serialization](docs/agentic-workbinder-library-ch7-tools-serialization.md)
  - [Ch 8: API Integration](docs/agentic-workbinder-library-ch8-api-integration.md)

### Persona Library

- [Agentic Persona Library](docs/agentic-persona-library.md) -- Overview of the persona system, orchestration, and prompt architecture.
  - [Ch 1: Architecture](docs/agentic-persona-library-ch1-architecture.md)
  - [Ch 2: Pipeline Personas](docs/agentic-persona-library-ch2-pipeline-personas.md)
  - [Ch 3: Analysis Personas](docs/agentic-persona-library-ch3-analysis-personas.md)
  - [Ch 4: Learning Personas](docs/agentic-persona-library-ch4-learning-personas.md)
  - [Ch 5: Expert Panel](docs/agentic-persona-library-ch5-expert-panel.md)
  - [Ch 6: Prompt Architecture](docs/agentic-persona-library-ch6-prompt-architecture.md)
  - [Ch 7: Testing Strategy](docs/agentic-persona-library-ch7-testing-strategy.md)

### Permissions & Audit

- [Permissions Matrix Audit](docs/permissions-matrix-audit.md) -- Audit of the artifact permissions model against actual persona usage in LLM prompts.
