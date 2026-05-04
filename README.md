# FFIEC RSSD Lookup Agent

A CLI agent powered by the Claude Agent SDK that helps you look up bank RSSD IDs,
explore ownership structures, trace merger histories, and fuzzy-match bank name
lists against the FFIEC National Information Center (NIC) database.

## How it works

The agent loads a domain-expert system prompt ([`system_prompt.py`](ffiec_rssd_agent/system_prompt.py)) and exposes **Read**, **Write**, and **Bash** to Claude. **FFIEC data is not accessed through MCP tools** in the default setup: the prompt instructs the model to answer questions by **running Python** from the repository (for example `uv run python …`) that:

- **`import ffiec_rssd_agent.db as db`** and call typed helpers (`search_institution`, `get_institution`, `get_relationships`, `get_transformations`, `get_branches`, `fuzzy_match_bank_rows`, `run_sql`, …), and/or  
- Open **`ffiec_rssd_agent/ffiec_nic.db`** with **`sqlite3`** or **pandas** for custom read-only SQL.

That keeps large workloads (especially big spreadsheet matches) in **one local process**, avoiding repeated MCP/tool round-trips and artificial batching.

The SQLite database is still produced by **`load_data`** from the NIC CSVs; nothing changes there.

For reference or custom wiring, the **previous MCP tool implementations** (same logic as `db.py`) live in [`legacy_tools.py`](ffiec_rssd_agent/legacy_tools.py); the stock CLI does not register them.

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

You can also put the key in a repo-root `.env` file:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

`ffiec_rssd_agent.agent` loads `.env` automatically at startup.

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

Once the agent is running, try asking in natural language. The assistant should use **Bash**
to run **Python** that calls **`ffiec_rssd_agent.db`** (or SQL against `ffiec_nic.db`), not a separate FFIEC MCP layer.

| Query | What it does (via `db` / SQLite) |
|-------|--------------------------------|
| `What is the RSSD ID for JPMorgan Chase?` | `db.search_institution` (name / filters) |
| `Show me the ownership tree for RSSD 1039502` | `db.get_relationships` (and recursion in Python if needed) |
| `What happened to Washington Mutual?` | Resolve RSSD with search, then `db.get_transformations` |
| `Match this file: bank_list.xlsx` | pandas reads the file → row dicts → `db.fuzzy_match_bank_rows` in one script |
| `How many national banks are in Texas?` | Read-only `SELECT` / `WITH` on NIC tables (via `db.run_sql` or `sqlite3`) |
| `What are all the branches of RSSD 480228?` | `db.get_branches` |

## Matching bank lists (CSV / Excel)

Use Python (run through **`uv run python`** from the repo root so `ffiec_rssd_agent` imports resolve):

1. Load the sheet with **pandas** (`read_csv` / `read_excel`).
2. Build a list of dicts with at least **`name`** per row; include **`city`**, **`state`**, and **`aba`** when columns exist—those cues align with NIC fields and reduce ambiguity when names collide.
3. Call **`db.fuzzy_match_bank_rows(rows, pool_active_only=…)`** once for the whole table.

Header names like `CITY`, `STATE`, `ABA`, `RTN`, `ROUTING_NUMBER` are conventional; map them in code to the keys `db` expects.

By default both active and closed institutions are in the candidate pool; pass
**`pool_active_only=True`** to restrict to **`institutions_active`**.

Important matching behavior in current `db.fuzzy_match_bank_rows`:

- Uses **state-indexed candidate pools** when `state` is present (faster on large files).
- Falls back to the full national pool when state is missing/unknown.
- Ranks by **uncapped** composite (name + cue bonuses) so city/ABA evidence is not lost when display score reaches 100.
- Returns `composite_score` capped at 100 for readability.

## Validation workflow (stage 1 + stage 2)

When validating an already-matched output file:

1. **Stage 1 (deterministic)** — run `ffiec_rssd_agent.validation.validate_matched_rows(df)` on the full file.
   - Adds `validation_verdict` (`accept` / `review` / `reject`)
   - Adds `validation_reason_codes`
   - Write `*_validated.csv`
2. **Stage 2 (agent-assisted)** — review only rows where `validation_verdict == "review"` in chunks.
   - Write `*_review.csv` (review subset + model decisions)
   - Merge back and write `*_final.csv`

This keeps token costs low by sending only suspicious rows to model review.

Example Stage-1 command (run from repo root):

```bash
uv run python -c "import pandas as pd; from ffiec_rssd_agent.validation import validate_matched_rows; p='example/us_posting_unique_company_taxonomy_sftp_matched.csv'; out='example/us_posting_unique_company_taxonomy_sftp_validated.csv'; df=pd.read_csv(p, low_memory=False); validate_matched_rows(df).to_csv(out, index=False); print(f'saved -> {out}')"
```

Example inspect command (after Stage 1):

```bash
uv run python -c "import pandas as pd; p='example/us_posting_unique_company_taxonomy_sftp_validated.csv'; df=pd.read_csv(p, low_memory=False); print(df['validation_verdict'].value_counts(dropna=False).to_string())"
```

## CLI Commands

| Command | Action |
|---------|--------|
| `/help` | Show help message |
| `/quit` | Exit the agent |

## Project Structure

When editing this repository with Cursor, Claude Code, or similar tools, see **[`CLAUDE.md`](CLAUDE.md)** for behavioral guidelines (small diffs, clarify assumptions, simplicity-first). Those guidelines are adapted from **[forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)** (a single `CLAUDE.md` template for Claude Code and similar tools, from Andrej Karpathy’s notes on common LLM coding pitfalls). `CLAUDE.md` is **not** loaded by the FFIEC CLI agent at runtime; the shipped assistant uses [`system_prompt.py`](ffiec_rssd_agent/system_prompt.py) instead.

```
CLAUDE.md              # Guidelines for AI-assisted development on this repo
agent_scripts/         # Timestamped temporary runner scripts (agent-generated)
pyproject.toml         # Dependencies and project metadata (source of truth for uv)
uv.lock                # Produced by `uv lock`; commit it for reproducible installs
requirements.txt       # Legacy pip list (optional mirror; uv uses pyproject.toml)
data/                  # FFIEC NIC bulk CSV downloads (5 files)
ffiec_rssd_agent/
  __init__.py          # Package init
  __main__.py          # Entry point for python -m
  load_data.py         # CSV → SQLite ETL
  db.py                # SQLite query helpers + fuzzy matching (what scripts should import)
  validation.py        # Stage-1 deterministic validator for matched outputs
  tools.py             # Placeholder constants (no FFIEC MCP server in default agent)
  legacy_tools.py      # Former MCP tool definitions; optional for custom agents
  system_prompt.py     # Domain-expert system prompt with full data dictionary
  agent.py             # Interactive CLI agent (Read / Write / Bash only)
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

## Troubleshooting

### Claude Code permission dialogs (Read, Bash, Write, …)

The agent enables **`Read`**, **`Write`**, and **`Bash`** and lists them in **`allowed_tools`** so they are **pre‑approved** without interactive confirmation. Other built-ins (e.g. **Edit**, **Glob**) stay disabled to limit scope—see [`agent.py`](ffiec_rssd_agent/agent.py). If prompts still appear (e.g. a different tool name on your CLI/OS), add that tool to both **`tools=[...]`** and **`allowed_tools`** or set **`permission_mode`** as needed.

---

## Updating the Data

To refresh with newer CSV files:

1. Download updated CSVs from the FFIEC NIC website
2. Place them in the `data/` directory (replacing the old files)
3. Re-run `uv run python -m ffiec_rssd_agent.load_data`
