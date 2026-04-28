# FFIEC RSSD Lookup Agent

A CLI agent powered by the Claude Agent SDK that helps you look up bank RSSD IDs,
explore ownership structures, trace merger histories, and fuzzy-match bank name
lists against the FFIEC National Information Center (NIC) database.

## Prerequisites

- **Python 3.10+**
- **Anthropic API key** — get one at https://console.anthropic.com/

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

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
python -m ffiec_rssd_agent.load_data
```

### 4. Start the agent

```bash
python -m ffiec_rssd_agent
```

## Example Queries

Once the agent is running, try:

| Query | What it does |
|-------|-------------|
| `What is the RSSD ID for JPMorgan Chase?` | Searches institutions by name |
| `Show me the ownership tree for RSSD 1039502` | Displays parent/subsidiary relationships |
| `What happened to Washington Mutual?` | Traces merger/failure history |
| `Match this file: bank_list.xlsx` | Fuzzy-matches a spreadsheet of bank names to RSSD IDs |
| `How many national banks are in Texas?` | Runs a custom SQL query under the hood |
| `What are all the branches of RSSD 480228?` | Lists branch locations for a head office |

## CLI Commands

| Command | Action |
|---------|--------|
| `/help` | Show help message |
| `/quit` | Exit the agent |

## Project Structure

```
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
3. Re-run `python -m ffiec_rssd_agent.load_data`
