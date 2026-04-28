"""
SQLite query helpers for the FFIEC NIC database.

Provides typed search, lookup, and fuzzy-matching functions used by
the MCP tools layer.
"""

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "ffiec_nic.db"

_MAX_RESULTS = 50


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ── Institution Search ──────────────────────────────────────────────

def search_institution(
    *,
    name: str | None = None,
    rssd_id: int | None = None,
    state: str | None = None,
    city: str | None = None,
    fdic_cert: int | None = None,
    ncua_id: int | None = None,
    aba_routing: int | None = None,
    lei: str | None = None,
    active_only: bool = False,
    limit: int = _MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Search institutions by one or more criteria. Returns matching rows."""
    table = "institutions_active" if active_only else "institutions_all"
    conditions: list[str] = []
    params: list[Any] = []

    if rssd_id is not None:
        conditions.append("ID_RSSD = ?")
        params.append(str(rssd_id))
    if name is not None:
        conditions.append("NM_LGL_UPPER LIKE ?")
        params.append(f"%{name.upper()}%")
    if state is not None:
        conditions.append("UPPER(STATE_ABBR_NM) = ?")
        params.append(state.upper())
    if city is not None:
        conditions.append("UPPER(CITY) LIKE ?")
        params.append(f"%{city.upper()}%")
    if fdic_cert is not None:
        conditions.append("ID_FDIC_CERT = ?")
        params.append(str(fdic_cert))
    if ncua_id is not None:
        conditions.append("ID_NCUA = ?")
        params.append(str(ncua_id))
    if aba_routing is not None:
        conditions.append("ID_ABA_PRIM = ?")
        params.append(str(aba_routing))
    if lei is not None:
        conditions.append("UPPER(ID_LEI) = ?")
        params.append(lei.upper())

    if not conditions:
        return []

    where = " AND ".join(conditions)
    sql = f"""
        SELECT ID_RSSD, NM_LGL, NM_SHORT, ENTITY_TYPE, CITY,
               STATE_ABBR_NM, CHTR_TYPE_CD, BROAD_REG_CD, PRIM_FED_REG,
               ID_FDIC_CERT, ID_NCUA, ID_ABA_PRIM, ID_LEI,
               D_DT_EXIST_CMNC, D_DT_EXIST_TERM, DT_START, DT_END
        FROM {table}
        WHERE {where}
        ORDER BY NM_LGL
        LIMIT ?
    """
    params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


# ── Full Detail ─────────────────────────────────────────────────────

def get_institution(rssd_id: int) -> list[dict[str, Any]]:
    """Return all attribute rows for a given RSSD ID (may span date ranges)."""
    sql = """
        SELECT * FROM institutions_all
        WHERE ID_RSSD = ?
        ORDER BY DT_START DESC
    """
    with _get_conn() as conn:
        rows = conn.execute(sql, [str(rssd_id)]).fetchall()
    return _rows_to_dicts(rows)


# ── Relationships ───────────────────────────────────────────────────

def get_relationships(
    rssd_id: int,
    *,
    as_parent: bool = True,
    as_offspring: bool = True,
    active_only: bool = False,
    limit: int = _MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Get ownership/control relationships involving a given RSSD ID."""
    parts: list[str] = []
    params: list[Any] = []
    active_clause = " AND r.DT_END = '99991231'" if active_only else ""

    if as_parent:
        parts.append(f"""
            SELECT r.*, a.NM_LGL AS OFFSPRING_NAME, a.ENTITY_TYPE AS OFFSPRING_ENTITY_TYPE
            FROM relationships r
            LEFT JOIN institutions_all a ON r.ID_RSSD_OFFSPRING = a.ID_RSSD
                AND a.DT_END = '99991231'
            WHERE r.ID_RSSD_PARENT = ?{active_clause}
        """)
        params.append(str(rssd_id))

    if as_offspring:
        parts.append(f"""
            SELECT r.*, a.NM_LGL AS OFFSPRING_NAME, a.ENTITY_TYPE AS OFFSPRING_ENTITY_TYPE
            FROM relationships r
            LEFT JOIN institutions_all a ON r.ID_RSSD_PARENT = a.ID_RSSD
                AND a.DT_END = '99991231'
            WHERE r.ID_RSSD_OFFSPRING = ?{active_clause}
        """)
        params.append(str(rssd_id))

    if not parts:
        return []

    sql = " UNION ALL ".join(parts) + f" LIMIT {limit}"
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


# ── Transformations ─────────────────────────────────────────────────

def get_transformations(
    rssd_id: int,
    *,
    as_predecessor: bool = True,
    as_successor: bool = True,
    limit: int = _MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Get merger/failure/split events involving a given RSSD ID."""
    parts: list[str] = []
    params: list[Any] = []

    if as_predecessor:
        parts.append("""
            SELECT t.*, a.NM_LGL AS SUCCESSOR_NAME
            FROM transformations t
            LEFT JOIN institutions_all a ON t.ID_RSSD_SUCCESSOR = a.ID_RSSD
                AND a.DT_END = '99991231'
            WHERE t.ID_RSSD_PREDECESSOR = ?
        """)
        params.append(str(rssd_id))

    if as_successor:
        parts.append("""
            SELECT t.*, a.NM_LGL AS SUCCESSOR_NAME
            FROM transformations t
            LEFT JOIN institutions_all a ON t.ID_RSSD_PREDECESSOR = a.ID_RSSD
                AND a.DT_END = '99991231'
            WHERE t.ID_RSSD_SUCCESSOR = ?
        """)
        params.append(str(rssd_id))

    if not parts:
        return []

    sql = " UNION ALL ".join(parts) + f" ORDER BY DT_TRANS LIMIT {limit}"
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


# ── Branches ────────────────────────────────────────────────────────

def get_branches(
    head_office_rssd: int,
    *,
    active_only: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List branch offices for a given head-office RSSD ID."""
    active_clause = " AND DT_END = '99991231'" if active_only else ""
    sql = f"""
        SELECT ID_RSSD, NM_LGL, NM_SHORT, CITY, STATE_ABBR_NM,
               STREET_LINE1, ZIP_CD, EST_TYPE_CD, D_DT_OPEN, DT_START, DT_END
        FROM branches
        WHERE ID_RSSD_HD_OFF = ?{active_clause}
        ORDER BY STATE_ABBR_NM, CITY
        LIMIT ?
    """
    with _get_conn() as conn:
        rows = conn.execute(sql, [str(head_office_rssd), limit]).fetchall()
    return _rows_to_dicts(rows)


# ── Raw SQL ─────────────────────────────────────────────────────────

def run_sql(query: str, limit: int = _MAX_RESULTS) -> list[dict[str, Any]]:
    """Execute a read-only SQL query against the database."""
    q = query.strip().rstrip(";")
    q_upper = q.upper()
    if not q_upper.startswith("SELECT") and not q_upper.startswith("WITH"):
        raise ValueError("Only SELECT / WITH queries are allowed.")

    if "LIMIT" not in q_upper:
        q += f" LIMIT {limit}"

    with _get_conn() as conn:
        rows = conn.execute(q).fetchall()
    return _rows_to_dicts(rows)


# ── Fuzzy Name Matching ─────────────────────────────────────────────

def fuzzy_match_names(
    names: list[str],
    *,
    active_only: bool = True,
    score_cutoff: int = 60,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Fuzzy-match a list of bank names against the database.

    Returns a list of dicts, one per input name, each containing:
      - input_name
      - matches: list of {rssd_id, legal_name, score, entity_type, state}
    """
    from rapidfuzz import fuzz, process

    table = "institutions_active" if active_only else "institutions_all"
    sql = f"""
        SELECT ID_RSSD, NM_LGL, NM_LGL_UPPER, ENTITY_TYPE, STATE_ABBR_NM, CITY
        FROM {table}
        WHERE NM_LGL_UPPER IS NOT NULL
    """
    with _get_conn() as conn:
        rows = conn.execute(sql).fetchall()

    candidates = _rows_to_dicts(rows)
    choice_names = [c["NM_LGL_UPPER"] for c in candidates]

    results = []
    for name in names:
        matches = process.extract(
            name.upper(),
            choice_names,
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff,
            limit=top_n,
        )
        match_details = []
        for matched_name, score, idx in matches:
            c = candidates[idx]
            match_details.append({
                "rssd_id": c["ID_RSSD"],
                "legal_name": c["NM_LGL"],
                "score": round(score, 1),
                "entity_type": c["ENTITY_TYPE"],
                "state": c["STATE_ABBR_NM"],
                "city": c["CITY"],
            })
        results.append({"input_name": name, "matches": match_details})

    return results
