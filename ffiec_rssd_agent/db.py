"""
SQLite query helpers for the FFIEC NIC database.

Provides typed search, lookup, and fuzzy-matching functions for agent
Python scripts and other callers.
"""

import math
import re
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "ffiec_nic.db"

# Full U.S. state / territory names -> 2-letter abbreviations (for normalizing input files)
_US_STATE_ABBR: dict[str, str] = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN",
    "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "AMERICAN SAMOA": "AS", "GUAM": "GU", "NORTHERN MARIANA ISLANDS": "MP",
    "PUERTO RICO": "PR", "VIRGIN ISLANDS": "VI",
}

_US_STATE_CODES = frozenset(_US_STATE_ABBR.values())

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
    """Execute a read-only SELECT/WITH against the NIC database (no extensions such as writefile)."""
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

def _aba_to_int(val: Any) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s == "0":
        return None
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return None
    v = int(digits)
    return v if v > 0 else None


def _scalar_is_missing(val: Any) -> bool:
    """True for None, float NaN, pandas NA/NaN (when pandas is installed)."""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    try:
        import pandas as pd

        if pd.isna(val):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    return False


def _norm_state_hint(raw: Any) -> str | None:
    if _scalar_is_missing(raw):
        return None
    t = str(raw).strip().upper()
    if not t or t == "NAN":
        return None
    if len(t) == 2 and t.isalpha():
        return t
    return _US_STATE_ABBR.get(t)


def _norm_city_hint(raw: Any) -> str | None:
    if _scalar_is_missing(raw):
        return None
    t = re.sub(r"\s+", " ", str(raw).strip().upper())
    if not t or t == "NAN":
        return None
    return t


def _build_state_row_pools(
    candidates: list[dict[str, Any]],
) -> dict[str, list[int]]:
    """
    Map normalized state abbreviation -> global candidate indices for fuzzy extract.

    U.S. / territory buckets also include candidates with a blank NIC state so
    nationally chartered entities are not dropped from the in-state pool.
    """
    buckets: dict[str, list[int]] = {}
    missing_state: list[int] = []
    for i, c in enumerate(candidates):
        sa = (c.get("STATE_ABBR_NM") or "").strip().upper()
        if not sa:
            missing_state.append(i)
        else:
            buckets.setdefault(sa, []).append(i)
    pools: dict[str, list[int]] = {}
    for key, idxs in buckets.items():
        if key in _US_STATE_CODES:
            pools[key] = idxs + missing_state
        else:
            pools[key] = list(idxs)
    return pools


def fuzzy_match_bank_rows(
    rows: list[dict[str, Any]],
    *,
    pool_active_only: bool = False,
    score_cutoff: int = 52,
    name_neighbor_limit: int = 45,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Fuzzy-match bank rows that may include secondary cues: city, state, ABA/RTN.

    Searches institutions_all by default (active + closed). Ranking:
      1. Composite score (name + cue bonuses)
      2. Currently active (DT_END = 99991231) before closed
      3. Among closed, most recently ended (highest DT_END)
      4. Most recent DT_START as a tie-breaker

    Each input row dict may contain: name (required), city, state, aba (routing).

    When ``state`` resolves to a U.S. / territory abbreviation present in the NIC
    data, name fuzzy-matching is restricted to that state's bucket (plus
    blank-state records for U.S. states) instead of the full national pool, which
    greatly speeds bulk jobs.
    """
    from rapidfuzz import fuzz, process

    if pool_active_only:
        sql = """
            SELECT ID_RSSD, NM_LGL, NM_LGL_UPPER, ENTITY_TYPE, STATE_ABBR_NM, CITY,
                   ID_ABA_PRIM, DT_START, DT_END, 'active' AS status
            FROM institutions_active
            WHERE NM_LGL_UPPER IS NOT NULL
        """
    else:
        sql = """
            SELECT ID_RSSD, NM_LGL, NM_LGL_UPPER, ENTITY_TYPE, STATE_ABBR_NM, CITY,
                   ID_ABA_PRIM, DT_START, DT_END, status
            FROM institutions_all
            WHERE NM_LGL_UPPER IS NOT NULL
        """

    with _get_conn() as conn:
        candidates = _rows_to_dicts(conn.execute(sql).fetchall())

    choice_names = [c["NM_LGL_UPPER"] for c in candidates]
    state_row_pools = _build_state_row_pools(candidates)

    # Pre-index ABA -> list of candidate indices (for routing disambiguation)
    aba_to_indices: dict[int, list[int]] = {}
    for i, c in enumerate(candidates):
        a = _aba_to_int(c.get("ID_ABA_PRIM"))
        if a is not None:
            aba_to_indices.setdefault(a, []).append(i)

    out: list[dict[str, Any]] = []
    for rec in rows:
        name = str(rec.get("name") or "").strip()
        if not name:
            out.append({"input": rec, "matches": [], "note": "empty name"})
            continue

        city_hint = _norm_city_hint(rec.get("city"))
        state_hint = _norm_state_hint(rec.get("state"))
        aba_hint = _aba_to_int(rec.get("aba"))

        idx_set: set[int] = set()

        pool_indices: list[int] | None = None
        if isinstance(state_hint, str) and state_hint:
            pool_indices = state_row_pools.get(state_hint.strip().upper())
        if pool_indices is not None and len(pool_indices) == 0:
            pool_indices = None

        if pool_indices is None:
            names_for_extract = choice_names
            local_to_global: list[int] | None = None
        else:
            names_for_extract = [choice_names[i] for i in pool_indices]
            local_to_global = pool_indices

        name_matches = process.extract(
            name.upper(),
            names_for_extract,
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff,
            limit=name_neighbor_limit,
        )
        for _, _, local_j in name_matches:
            gidx = local_j if local_to_global is None else local_to_global[local_j]
            idx_set.add(gidx)

        if aba_hint is not None and aba_hint in aba_to_indices:
            idx_set.update(aba_to_indices[aba_hint])

        scored: list[dict[str, Any]] = []
        for idx in idx_set:
            c = candidates[idx]
            name_score = float(
                fuzz.WRatio(name.upper(), c["NM_LGL_UPPER"] or ""),
            )

            cues: list[str] = []
            composite = name_score

            cand_state = _norm_state_hint(c.get("STATE_ABBR_NM"))
            if (
                isinstance(state_hint, str)
                and cand_state
                and state_hint == cand_state
            ):
                composite = min(100.0, composite + 14.0)
                cues.append("state")

            if city_hint and c.get("CITY"):
                city_cand = _norm_city_hint(c["CITY"])
                if city_cand:
                    cr = float(fuzz.WRatio(city_hint, city_cand))
                    bonus = min(18.0, cr * 0.18)
                    if bonus >= 8:
                        cues.append("city")
                    composite = min(100.0, composite + bonus)

            cand_aba = _aba_to_int(c.get("ID_ABA_PRIM"))
            if aba_hint is not None and cand_aba is not None and aba_hint == cand_aba:
                composite = min(100.0, composite + 38.0)
                cues.append("aba")

            dt_end = str(c.get("DT_END") or "0").strip()
            dt_start = str(c.get("DT_START") or "0").strip()
            is_current = dt_end == "99991231"
            try:
                dt_end_i = int(dt_end)
            except ValueError:
                dt_end_i = 0
            try:
                dt_start_i = int(dt_start)
            except ValueError:
                dt_start_i = 0

            scored.append({
                "rssd_id": c["ID_RSSD"],
                "legal_name": c["NM_LGL"],
                "composite_score": round(composite, 1),
                "name_score": round(name_score, 1),
                "cues_matched": cues,
                "entity_type": c["ENTITY_TYPE"],
                "state": c["STATE_ABBR_NM"],
                "city": c["CITY"],
                "id_aba_prim": c.get("ID_ABA_PRIM"),
                "dt_end": dt_end,
                "dt_start": dt_start,
                "status": c.get("status"),
                "is_current_record": is_current,
                "_sort": (-composite, -float(is_current), -dt_end_i, -dt_start_i),
            })

        scored.sort(key=lambda x: x["_sort"])
        for x in scored:
            del x["_sort"]

        out.append({
            "input": {
                "name": name,
                "city": rec.get("city"),
                "state": rec.get("state"),
                "aba": rec.get("aba"),
            },
            "matches": scored[:top_n],
        })

    return out


def fuzzy_match_names(
    names: list[str],
    *,
    active_only: bool = True,
    score_cutoff: int = 60,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Fuzzy-match a list of bank names (legacy helper; no secondary cues).

    Returns one dict per name with keys input_name and matches.
    """
    rows = [{"name": n} for n in names]
    raw = fuzzy_match_bank_rows(
        rows,
        pool_active_only=active_only,
        score_cutoff=score_cutoff,
        top_n=top_n,
    )
    legacy: list[dict[str, Any]] = []
    for item in raw:
        matches = []
        for m in item["matches"]:
            m2 = dict(m)
            m2["score"] = m2.get("composite_score", m2.get("name_score"))
            matches.append(m2)
        legacy.append({"input_name": item["input"]["name"], "matches": matches})
    return legacy
