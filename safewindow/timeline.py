"""Per-village timeline outputs (Step 7).

From the per-date village status table this computes, for each village:
  * isolation range  (last date seen connected, first date seen isolated]
  * safe exit date   the last date seen connected before isolation
  * aid deadline     earliest possible isolation day + supply days
  * reconnected date first date seen connected again after isolation
and an urgency rank (earliest aid deadline first, then largest population).

Satellite dates have gaps, so isolation is a range, never a single day.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from . import config


def summarise(status: pd.DataFrame, villages: pd.DataFrame,
              supply_days: int = config.DEFAULT_SUPPLY_DAYS) -> pd.DataFrame:
    """status: village_id, date, status (one threshold only).
    villages: village_id, name, population, boat_dependent."""
    status = status.assign(date=pd.to_datetime(status["date"])).sort_values("date")
    rows = []
    for vid, grp in status.groupby("village_id", sort=False):
        dates, st = grp["date"].tolist(), grp["status"].tolist()
        row = {"village_id": vid, "outcome": "never_isolated",
               "last_connected": pd.NaT, "first_isolated": pd.NaT,
               "isolated_from_earliest": pd.NaT, "reconnected": pd.NaT,
               "safe_exit_date": pd.NaT, "n_dates_isolated": st.count("isolated")}
        if "boat_dependent" in st:
            row["outcome"] = "boat_dependent"
        elif "isolated" in st:
            i = st.index("isolated")
            before = [d for d, s in zip(dates[:i], st[:i]) if s == "connected"]
            after = [d for d, s in zip(dates[i:], st[i:]) if s == "connected"]
            row.update(outcome="isolated", first_isolated=dates[i],
                       last_connected=before[-1] if before else pd.NaT,
                       safe_exit_date=before[-1] if before else pd.NaT,
                       reconnected=after[0] if after else pd.NaT)
            # Earliest day isolation could have started. With no connected
            # observation before it, all we know is "on or before" this date.
            row["isolated_from_earliest"] = (before[-1] + timedelta(days=1)) if before else dates[i]
        elif "uncertain" in st:
            row["outcome"] = "uncertain"
        rows.append(row)

    out = villages[["village_id", "name", "population"]].merge(pd.DataFrame(rows), on="village_id", how="right")
    return add_deadlines(out, supply_days)


def add_deadlines(summary: pd.DataFrame, supply_days: int) -> pd.DataFrame:
    s = summary.copy()
    s["aid_deadline"] = pd.to_datetime(s["isolated_from_earliest"]) + pd.to_timedelta(supply_days, unit="D")
    ranked = s[s["outcome"] == "isolated"].sort_values(["aid_deadline", "population"], ascending=[True, False])
    s["urgency_rank"] = pd.Series(range(1, len(ranked) + 1), index=ranked.index).astype("Int64")
    return s.sort_values(["urgency_rank", "name"], na_position="last").reset_index(drop=True)


def isolation_range_text(row, fmt: str = "%d %b") -> str:
    """'isolated between 14 Jun and 18 Jun' style text (English)."""
    if row["outcome"] != "isolated":
        return ""
    first = pd.Timestamp(row["first_isolated"]).strftime(fmt)
    if pd.isna(row["last_connected"]):
        return f"isolated on or before {first}"
    lower = pd.Timestamp(row["isolated_from_earliest"]).strftime(fmt)
    return f"isolated between {lower} and {first}"
