"""
Custom MCP tools for the FFIEC RSSD Lookup Agent.

Each tool wraps a db.py function and returns structured text results
for Claude to interpret and present to the user.
"""

import json
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import db

SERVER_NAME = "ffiec"
SERVER_VERSION = "1.0.0"

_CITY_ALIASES = (
    "city",
    "hq_city",
    "bank_city",
    "institution_city",
    "hq city",
    "bank city",
)
_STATE_ALIASES = (
    "state",
    "st",
    "state_abbr",
    "state abbr",
    "state_code",
)
_ROUTING_ALIASES = (
    "aba",
    "rtn",
    "routing",
    "routing_number",
    "routing_no",
    "routing number",
    "id_aba",
    "id_aba_prim",
    "aba_routing",
    "fed_ach",
)


def _resolve_column(df: pd.DataFrame, explicit: str, aliases: tuple[str, ...]) -> str | None:
    """Pick a column: use explicit name if valid, else first case-insensitive alias match."""
    cols = list(df.columns)
    if explicit and explicit.strip():
        e = explicit.strip()
        if e in cols:
            return e
        el = e.lower()
        for c in cols:
            if str(c).strip().lower() == el:
                return c
    lower_to_orig = {str(c).strip().lower(): c for c in cols}
    for a in aliases:
        if a.lower() in lower_to_orig:
            return lower_to_orig[a.lower()]
    return None


def _fmt_rows(rows: list[dict], max_rows: int = 30) -> str:
    if not rows:
        return "No results found."
    truncated = rows[:max_rows]
    text = json.dumps(truncated, indent=2, default=str)
    if len(rows) > max_rows:
        text += f"\n\n... and {len(rows) - max_rows} more rows (total {len(rows)})"
    return text


# ── Tools ───────────────────────────────────────────────────────────

@tool(
    "search_institution",
    "Search FFIEC NIC institutions by name, RSSD ID, state, city, FDIC cert, NCUA charter, ABA routing number, or LEI. "
    "All text searches are case-insensitive partial matches. "
    "Provide at least one search parameter. Set active_only to 'true' to exclude closed institutions.",
    {
        "name": str,
        "rssd_id": str,
        "state": str,
        "city": str,
        "fdic_cert": str,
        "ncua_id": str,
        "aba_routing": str,
        "lei": str,
        "active_only": str,
    },
)
async def search_institution(args: dict[str, Any]) -> dict[str, Any]:
    try:
        kwargs: dict[str, Any] = {}
        if args.get("name"):
            kwargs["name"] = args["name"]
        if args.get("rssd_id"):
            kwargs["rssd_id"] = int(args["rssd_id"])
        if args.get("state"):
            kwargs["state"] = args["state"]
        if args.get("city"):
            kwargs["city"] = args["city"]
        if args.get("fdic_cert"):
            kwargs["fdic_cert"] = int(args["fdic_cert"])
        if args.get("ncua_id"):
            kwargs["ncua_id"] = int(args["ncua_id"])
        if args.get("aba_routing"):
            kwargs["aba_routing"] = int(args["aba_routing"])
        if args.get("lei"):
            kwargs["lei"] = args["lei"]
        if args.get("active_only", "").lower() == "true":
            kwargs["active_only"] = True

        rows = db.search_institution(**kwargs)
        return {"content": [{"type": "text", "text": _fmt_rows(rows)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "get_institution_details",
    "Get the full attribute record for a given RSSD ID, including all date ranges. "
    "Returns charter type, regulator, address, identifiers, and status history.",
    {"rssd_id": str},
)
async def get_institution_details(args: dict[str, Any]) -> dict[str, Any]:
    try:
        rssd_id = int(args["rssd_id"])
        rows = db.get_institution(rssd_id)
        return {"content": [{"type": "text", "text": _fmt_rows(rows)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "get_ownership_tree",
    "Get parent/subsidiary ownership and control relationships for a given RSSD ID. "
    "Set direction to 'parent' (entities this RSSD owns), 'offspring' (entities that own this RSSD), or 'both'. "
    "Set active_only to 'true' to see only current relationships.",
    {"rssd_id": str, "direction": str, "active_only": str},
)
async def get_ownership_tree(args: dict[str, Any]) -> dict[str, Any]:
    try:
        rssd_id = int(args["rssd_id"])
        direction = args.get("direction", "both").lower()
        active_only = args.get("active_only", "").lower() == "true"
        rows = db.get_relationships(
            rssd_id,
            as_parent=(direction in ("parent", "both")),
            as_offspring=(direction in ("offspring", "both")),
            active_only=active_only,
        )
        return {"content": [{"type": "text", "text": _fmt_rows(rows)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "get_merger_history",
    "Get the transformation (merger, acquisition, failure, split) history for a given RSSD ID. "
    "Set direction to 'predecessor' (what this entity was absorbed into), "
    "'successor' (what entities were absorbed by this one), or 'both'.",
    {"rssd_id": str, "direction": str},
)
async def get_merger_history(args: dict[str, Any]) -> dict[str, Any]:
    try:
        rssd_id = int(args["rssd_id"])
        direction = args.get("direction", "both").lower()
        rows = db.get_transformations(
            rssd_id,
            as_predecessor=(direction in ("predecessor", "both")),
            as_successor=(direction in ("successor", "both")),
        )
        return {"content": [{"type": "text", "text": _fmt_rows(rows)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "get_branches",
    "List branch office locations for a given head-office RSSD ID. "
    "Set active_only to 'true' (default) to see only currently open branches.",
    {"rssd_id": str, "active_only": str},
)
async def get_branches(args: dict[str, Any]) -> dict[str, Any]:
    try:
        rssd_id = int(args["rssd_id"])
        active_only = args.get("active_only", "true").lower() != "false"
        rows = db.get_branches(rssd_id, active_only=active_only)
        return {"content": [{"type": "text", "text": _fmt_rows(rows, max_rows=100)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "match_bank_list",
    "Fuzzy-match banks from a CSV or Excel file against the FFIEC NIC database. "
    "Required: file_path. Use name_column for the institution name (defaults to the first column). "
    "Optional columns disambiguate duplicate names: city_column, state_column (2-letter or full state name), "
    "routing_column (ABA/RTN). If those parameters are empty, common header names are auto-detected "
    "(e.g. CITY, STATE, ABA, RTN, ROUTING_NUMBER). "
    "By default searches active AND closed institutions but ranks currently active (DT_END=99991231) first, "
    "then the most recently ended institutions. Set active_only to 'true' to restrict the search pool "
    "to institutions_active only (legacy behavior).",
    {
        "file_path": str,
        "name_column": str,
        "city_column": str,
        "state_column": str,
        "routing_column": str,
        "active_only": str,
    },
)
async def match_bank_list(args: dict[str, Any]) -> dict[str, Any]:
    try:
        file_path = Path(args["file_path"]).expanduser().resolve()
        if not file_path.exists():
            return {
                "content": [{"type": "text", "text": f"File not found: {file_path}"}],
                "is_error": True,
            }

        suffix = file_path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, dtype=str)
        elif suffix == ".csv":
            df = pd.read_csv(file_path, dtype=str)
        else:
            return {
                "content": [{"type": "text", "text": f"Unsupported file type: {suffix}. Use .csv or .xlsx"}],
                "is_error": True,
            }

        name_explicit = (args.get("name_column") or "").strip()
        if name_explicit:
            name_col = _resolve_column(df, name_explicit, ())
        else:
            name_col = str(df.columns[0])
        if not name_col or name_col not in df.columns:
            return {
                "content": [{"type": "text", "text": f"Name column not found. Available: {list(df.columns)}"}],
                "is_error": True,
            }

        city_col = _resolve_column(df, (args.get("city_column") or "").strip(), _CITY_ALIASES)
        state_col = _resolve_column(df, (args.get("state_column") or "").strip(), _STATE_ALIASES)
        routing_col = _resolve_column(df, (args.get("routing_column") or "").strip(), _ROUTING_ALIASES)

        hint_lines = [
            f"Using columns: name={name_col!r}",
        ]
        if city_col:
            hint_lines.append(f"city={city_col!r}")
        if state_col:
            hint_lines.append(f"state={state_col!r}")
        if routing_col:
            hint_lines.append(f"routing/ABA={routing_col!r}")

        bank_rows: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            raw_name = row.get(name_col)
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
                continue
            name = str(raw_name).strip()
            if not name:
                continue
            rec: dict[str, Any] = {"name": name}
            if city_col:
                v = row.get(city_col)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    rec["city"] = str(v).strip()
            if state_col:
                v = row.get(state_col)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    rec["state"] = str(v).strip()
            if routing_col:
                v = row.get(routing_col)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    rec["aba"] = str(v).strip()
            bank_rows.append(rec)

        if not bank_rows:
            return {
                "content": [{"type": "text", "text": "No non-empty bank names found in the file."}],
                "is_error": True,
            }

        pool_active_only = (args.get("active_only") or "").strip().lower() == "true"
        results = db.fuzzy_match_bank_rows(
            bank_rows,
            pool_active_only=pool_active_only,
        )
        header = "\n".join(hint_lines) + "\n\n"
        return {"content": [{"type": "text", "text": header + _fmt_rows(results, max_rows=500)}]}

    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {e}\n{traceback.format_exc()}"}],
            "is_error": True,
        }


@tool(
    "run_sql_query",
    "Execute a read-only SELECT (or WITH) against the FFIEC NIC SQLite database ONLY. "
    "No DDL, no writes, no ATTACH/import of external CSVs, and no SQLite optional extensions "
    "(there is NO writefile() or similar file-export in this engine). "
    "To save query output to disk, format the rows yourself and use the Claude **Write** tool. "
    "Tables: institutions_active, institutions_closed, branches, relationships, "
    "transformations, institutions_all.",
    {"query": str},
)
async def run_sql_query(args: dict[str, Any]) -> dict[str, Any]:
    try:
        rows = db.run_sql(args["query"])
        return {"content": [{"type": "text", "text": _fmt_rows(rows)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


# ── Server Factory ──────────────────────────────────────────────────

ALL_TOOLS = [
    search_institution,
    get_institution_details,
    get_ownership_tree,
    get_merger_history,
    get_branches,
    match_bank_list,
    run_sql_query,
]

ALLOWED_TOOL_NAMES = [f"mcp__{SERVER_NAME}__{t.name}" for t in ALL_TOOLS]


def create_ffiec_server():
    """Create the in-process MCP server with all FFIEC tools."""
    return create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=ALL_TOOLS,
    )
