# FFIEC RSSD Lookup Agent

A CLI agent powered by the Claude Agent SDK that helps you look up bank RSSD IDs,
explore ownership structures, trace merger histories, and fuzzy-match bank name
lists against the FFIEC National Information Center (NIC) database.

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — installs Python (if needed) and project dependencies from `pyproject.toml`
- **Python** — version must satisfy `requires-python` in `pyproject.toml` (currently **3.13+**)
- **Anthropic API key** — get one at https://console.anthropic.com/

## Setup

### 1. Clone and sync dependencies

From the repository root:

```bash
uv sync
```

This creates a virtual environment and installs packages declared in [`pyproject.toml`](pyproject.toml). Use **`uv run …`** below so commands use that environment automatically.

<details>
<summary>Alternative: pip and <code>requirements.txt</code></summary>

If you are not using uv:

```bash
pip install -r requirements.txt
```

Then replace `uv run python` with `python` in the steps below, using the interpreter where you installed the packages.

</details>

### 2. Set your API key

```bash
# Linux / macOS
export ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Windows (cmd)
set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Build the database

This reads the 5 FFIEC NIC CSV files from the `data/` directory and loads them
into a local SQLite database. You only need to run this once (or again when the
CSVs are updated).

```bash
uv run python -m ffiec_rssd_agent.load_data
```

### 4. Start the agent

```bash
uv run python -m ffiec_rssd_agent
```

Adding or upgrading dependencies (edit `pyproject.toml` first):

```bash
uv add <package>
# or after manual edits:
uv lock && uv sync
```

## Example Queries

Once the agent is running, try:

| Query | What it does |
|-------|-------------|
| `What is the RSSD ID for JPMorgan Chase?` | Searches institutions by name |
| `Show me the ownership tree for RSSD 1039502` | Displays parent/subsidiary relationships |
| `What happened to Washington Mutual?` | Traces merger/failure history |
| `Match this file: bank_list.xlsx` | Fuzzy-matches names to RSSD IDs; city/state/ABA columns disambiguate duplicates |
| `How many national banks are in Texas?` | Runs a custom SQL query under the hood |
| `What are all the branches of RSSD 480228?` | Lists branch locations for a head office |

## Matching bank lists (CSV / Excel)

The `match_bank_list` tool reads each row with the institution name plus optional **city**,
**state** (2-letter or full name), and **routing / ABA / RTN** columns. Those cues are
matched against NIC fields and strongly reduce ambiguity when many banks share a name.
If you do not pass column names, common headers (`CITY`, `STATE`, `ABA`, `RTN`,
`ROUTING_NUMBER`, etc.) are detected automatically.

By default both active and closed institutions are considered; **currently active** records
are ranked first, then the **most recently ended** (by `DT_END`). Pass `active_only='true'`
to limit the search to active institutions only.

## CLI Commands

| Command | Action |
|---------|--------|
| `/help` | Show help message |
| `/quit` | Exit the agent |

## Project Structure

```
pyproject.toml         # Dependencies and project metadata (source of truth for uv)
uv.lock                # Produced by `uv lock`; commit it for reproducible installs
requirements.txt       # Legacy pip list (optional mirror; uv uses pyproject.toml)
data/                  # FFIEC NIC bulk CSV downloads (5 files)
ffiec_rssd_agent/
  __init__.py          # Package init
  __main__.py          # Entry point for python -m
  load_data.py         # CSV → SQLite ETL
  db.py                # SQLite query helpers + fuzzy matching
  tools.py             # Custom MCP tools for Claude
  system_prompt.py     # Domain-expert system prompt with full data dictionary
  agent.py             # Interactive CLI agent
  ffiec_nic.db         # Generated SQLite database (after load_data)
```

## Data Source

The CSV files live in `data/` and come from the
[FFIEC NIC Bulk Data Download](https://www.ffiec.gov/NPW):

- `data/CSV_ATTRIBUTES_ACTIVE.CSV` — Active institutions
- `data/CSV_ATTRIBUTES_CLOSED.CSV` — Closed institutions
- `data/CSV_ATTRIBUTES_BRANCHES.CSV` — Branch offices
- `data/CSV_RELATIONSHIPS.CSV` — Ownership/control relationships
- `data/CSV_TRANSFORMATIONS.CSV` — Mergers, failures, splits

## Updating the Data

To refresh with newer CSV files:

1. Download updated CSVs from the FFIEC NIC website
2. Place them in the `data/` directory (replacing the old files)
3. Re-run `uv run python -m ffiec_rssd_agent.load_data`
