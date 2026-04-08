# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP + Skills 销售分析 Agent — a Python-based AI Agent demonstrating how to build expert-level AI assistants using MCP (Model Context Protocol) tools + Skills packages. The project uses a client-server architecture where the AI Agent (client) communicates with the MCP Server via stdio protocol, featuring progressive skill loading, vector memory, conversation recording, and evolutionary user profiling.

## Commands

```bash
# Install dependencies
uv sync

# Initialize/reset database with 52 Q2 test records
uv run init_db.py

# Start Agent (interactive model selection, REPL mode)
uv run agent.py

# Run MCP Server standalone (for testing)
uv run server.py
```

**First run requires `.env` configuration**: Copy `.env.example` and fill in API keys.

## Architecture

```
User Terminal (Natural Language)
    ↓
agent.py (MCP Client + Skill Engine + LLM Backend + 4-Layer Memory System)
    ↓ stdio                                    ↕ ChromaDB          ↕ SQLite
server.py (MCP Server — 5 Sales Tools)       memory_db/ (Memory)   conversations.db (History)
    ↓                                                       ↕
sales.db (SQLite — 52 Q2 Records)               user_profile.db (User Profile + Hypotheses)
```

### Four-Layer Memory System

1. **Vector Memory (ChromaDB)**: Cross-session semantic retrieval, auto-summary storage
   - Location: `./object_db/memory_db/`
   - Auto-saves conversation summaries on exit
   - Auto-retrieves relevant memories before each turn

2. **Conversation Record (SQLite)**: Complete session history with tool call chain tracking
   - Location: `./object_db/conversations.db`
   - Tracks: user questions, agent responses, tool calls (name, params, result, duration_ms)

3. **Evolutionary Memory (User Profile)**: Agent self-evolution capability
   - Location: `./object_db/user_profile.db`
   - **UserProfileStore**: Persistent user profiling (preferences/constraints/workflows)
   - **HypothesisStore**: Manages pending hypothesis confirmation queue
   - **Observer**: Extracts user behavior signals from each conversation
   - **EvolutionEngine**: Coordinates observe→summarize→evolve workflow
   - `/evolve` command: Batch profile updates from session analysis

4. **Tool Cache (TTL + LRU)**: Same-query millisecond response with hit rate tracking

### Progressive Skill Loading

Three-stage loading strategy to minimize token cost:

```
Stage 1: Startup (~100 tokens)
    └── Load only SKILL.md YAML header (name + description + trigger_keywords)
    └── Purpose: Skill routing and fast matching

Stage 2: Match (<5000 tokens)
    └── Load complete SKILL.md instructions
    └── Purpose: Parse business SOP, execution flow, output specs

Stage 3: Execution (on-demand)
    └── Load scripts/ or references/ files
    └── Purpose: Code execution, template rendering (code not exposed to model)
```

### Core Components

**agent.py** - MCP Client entry: Model selection, AgentCore initialization, runtime model switching

**agent/core.py** - Agent coordinator: Conversation loop, tool calls, streaming output

**agent/skill_loader.py** - Three-stage progressive skill loader with path traversal protection

**agent/backends/** - LLM Backend abstraction
   - `base.py`: `BaseBackend` interface (check, build_tools, chat, chat_stream, make_tool_call_raw_message, make_tool_result_message)
   - `openai_compat.py`: OpenAI-compatible base class (shared by GLM and Ollama)
   - `qwen.py`: Alibaba DashScope API (qwen-max/qwen-plus/qwen-turbo)
   - `glm.py`: Zhipu BigModel API (GLM-4.5-Air/GLM-4-Flash)
   - `ollama.py`: Local model service

**agent/evolution/** - Evolutionary memory module
   - `engine.py`: EvolutionEngine coordinating observation→summary→evolve
   - `observer.py`: Extracts user behavior signals (preferences, missing_constraints, workflow_patterns)
   - `profile.py`: UserProfileStore for persistent user profiling
   - `hypothesis.py`: HypothesisStore managing pending confirmation queue

**agent/commands/** - Slash command handlers
   - `memory.py`: `/memory list/search/delete/clear/stats`
   - `history.py`: `/history show/resume/delete/clear/stats/search/export/tools`

**agent/cache.py** - Tool call cache with TTL expiration (default 300s) and LRU eviction (default 1000 entries)

**agent/retry.py** - MCP connection retry with exponential backoff (1s→2s→4s) and jitter

**server.py** - FastMCP Server with 5 sales data tools: `list_products`, `query_sales_by_product`, `query_sales_by_region`, `get_sales_overview`, `get_raw_sales_data`

**sales-analysis/** - Skill package structure
   - `SKILL.md`: Core instruction (YAML metadata + execution flow + output specs)
   - `scripts/`: Python scripts for calculations (metrics, anomaly detection)
   - `references/`: Output templates (report formats)

## Environment Variables

`.env` file:
- `DASHSCOPE_API_KEY` - Alibaba Qwen API Key
- `BIGMODEL_API_KEY` - Zhipu GLM API Key
- `OLLAMA_BASE_URL` (optional) - Default: http://localhost:11434
- `OLLAMA_MODEL` (optional) - Default: qwen2.5:7b

## Configuration

Copy `config.yaml.example` to `config.yaml` and configure:
- `cache.enabled/ttl_seconds/max_size` - Tool caching behavior
- `mcp_server.retry_max_attempts/retry_base_delay/timeout` - MCP connection retry
- `database.pool_size/pool_timeout` - SQLite connection pool
- `session.export_dir/max_history_display` - Session export settings

## Key Design Patterns

**Progressive Skill Loading**: Minimizes token cost with on-demand loading

**Backend Abstraction**: Unified `BaseBackend` interface supporting Qwen/GLM/Ollama with OpenAI-compatible layer reuse

**Skill-Tool Synergy**: SKILL.md defines business flow, scripts/ handles calculations, references/ provides templates

**MCP Connection Stability**: Exponential backoff retry with jitter, automatic retryable error detection

**Immutable Configuration**: `AgentConfig` dataclass with environment variable overrides, keyring-secured API key storage

## Slash Commands

| Command | Description |
|---------|-------------|
| `/new` | Create new session |
| `/evolve` | Deep analysis of user profile from session |
| `/profile` [clear] | View/clear user profile |
| `/hypothesis` [clear] | View/clear pending hypotheses |
| `/memory list/search/delete/clear/stats` | Memory management |
| `/history [show/resume/delete/clear/stats/search/export/tools]` | Session management |
| `/model` [qwen/glm/ollama] | Runtime model switching |
| `/help` | Show all commands |
| `/exit` | Exit program |

## Database Storage

All databases stored in `./object_db/`:
- `sales.db` - Sales business data
- `memory_db/` - ChromaDB vector memory persistence
- `conversations.db` - Session history with tool call chain
- `user_profile.db` - User profile and hypothesis constraints
