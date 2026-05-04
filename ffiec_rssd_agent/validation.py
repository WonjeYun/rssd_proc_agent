"""
Validation helpers for fuzzy-match outputs.

This module classifies each matched row into:
  - accept
  - review
  - reject
and records concise reason codes for auditability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

_GENERIC_TOKENS = {
    "BANK",
    "BANCORP",
    "BANCORPORATION",
    "FINANCIAL",
    "HOLDINGS",
    "GROUP",
    "CORP",
    "CORPORATION",
    "COMPANY",
    "TRUST",
    "NATIONAL",
    "ASSOCIATION",
    "NA",
    "N",
    "A",
}


@dataclass(frozen=True)
class ValidationConfig:
    strong_name_score: float = 90.0
    moderate_name_score: float = 70.0
    strong_composite_score: float = 92.0


def _clean_tokenize(value: Any) -> list[str]:
    if value is None:
        return []
    s = str(value).upper()
    tokens = re.findall(r"[A-Z0-9]+", s)
    return [t for t in tokens if t]


def _is_generic_name(value: Any) -> bool:
    toks = _clean_tokenize(value)
    if not toks:
        return True
    non_generic = [t for t in toks if t not in _GENERIC_TOKENS]
    return len(non_generic) == 0


def _eq_norm(a: Any, b: Any) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return str(a).strip().upper() == str(b).strip().upper()


def _to_float(v: Any) -> float:
    try:
        if pd.isna(v):
            return 0.0
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return 0.0


def validate_matched_rows(
    df: pd.DataFrame,
    *,
    cfg: ValidationConfig | None = None,
) -> pd.DataFrame:
    """
    Add validation columns to a matched output DataFrame.

    Expected columns:
      input_name, input_city, input_state, rssd_id, matched_city, matched_state,
      composite_score, name_score, confidence
    """
    cfg = cfg or ValidationConfig()
    out = df.copy()

    verdicts: list[str] = []
    reasons: list[str] = []

    for _, row in out.iterrows():
        row_reasons: list[str] = []

        rssd_missing = pd.isna(row.get("rssd_id")) or str(row.get("rssd_id")).strip() == ""
        name_score = _to_float(row.get("name_score"))
        composite_score = _to_float(row.get("composite_score"))

        state_match = _eq_norm(row.get("input_state"), row.get("matched_state"))
        city_match = _eq_norm(row.get("input_city"), row.get("matched_city"))
        generic_name = _is_generic_name(row.get("input_name"))

        if rssd_missing:
            verdicts.append("reject")
            reasons.append("no_match")
            continue

        if name_score < cfg.moderate_name_score:
            row_reasons.append("low_name_score")
        elif name_score < cfg.strong_name_score:
            row_reasons.append("moderate_name_score")

        if not state_match and not pd.isna(row.get("input_state")):
            row_reasons.append("state_mismatch")
        if not city_match and not pd.isna(row.get("input_city")):
            row_reasons.append("city_mismatch")
        if generic_name:
            row_reasons.append("generic_input_name")
        if composite_score >= 100.0:
            row_reasons.append("composite_capped")

        if (
            name_score >= cfg.strong_name_score
            and composite_score >= cfg.strong_composite_score
            and (state_match or pd.isna(row.get("input_state")))
            and not generic_name
        ):
            verdict = "accept"
        elif name_score < cfg.moderate_name_score:
            verdict = "reject"
        else:
            verdict = "review"

        verdicts.append(verdict)
        reasons.append(",".join(row_reasons) if row_reasons else "clean_match")

    out["validation_verdict"] = verdicts
    out["validation_reason_codes"] = reasons
    return out
