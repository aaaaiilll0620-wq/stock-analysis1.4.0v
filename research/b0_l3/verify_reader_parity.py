# -*- coding: utf-8 -*-
"""W6b-2 · the L3 readers must reproduce L2's answer from the same bytes.

P2-3 requires a field to mean ONE thing across both routes. A second
implementation of a parsing rule does not fail by crashing — it fails by
returning a slightly different number, and every guard downstream accepts it.
So the readers are not asserted correct; they are checked against the sealed
artefacts L2 built from the same upstream.

    prices             vs data/b0/price_panel.parquet
    valuation          vs data/b0/valuation_panel.parquet
    calendar           vs data/b0/trading_calendar.csv          PREFIX
    security_status    vs data/b0/security_status.csv           exact
    corporate_actions  vs data/b0/corporate_actions_ledger.csv  exact BYTES
    bonus_shares       vs data/b0/bonus_share_panel.parquet     frozen window
    financials         vs data/b0/financials_pit.parquet        <= window_end
    revenue            vs data/b0/monthly_revenue_pit.parquet   <= window_end
    industry           vs data/b0/industry_pit.parquet          exact

THREE COMPARISONS ARE RESTRICTED, AND FOR ONE REASON
-----------------------------------------------------
L2 is frozen and L3 is not. Its calendar stops at 2026-08-17 under R-W1-1; its
fundamentals panels drop anything announced after `window_end` (2026-03-31);
its bonus panel covers only the union the 141-period lookback reaches. An L3
reader that reproduced those bounds would be prospective in name only.

So equality is required exactly on the OVERLAP, and the shape of the restriction
is the same every time: everything L2 has, L3 has, unchanged. What that rules
out is the failure that matters — a past row that MOVED. A calendar that
re-dates a past session re-dates every decision that stood on it, and a restated
fundamental that quietly replaces an earlier one does the same to a holding.

READ-ONLY with respect to `data/b0/`. This compares against those files; it
never writes one.

    python research/b0_l3/verify_reader_parity.py <run_dir> [as_of]
"""
from __future__ import annotations

import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.b0_master_prereg import spec as frozen_spec              # noqa: E402
from l3_readers import (                                           # noqa: E402
    LEDGER_COLUMNS, STATUS_COLUMNS, read_bonus_shares, read_calendar,
    read_corporate_actions, read_financials, read_industry, read_prices,
    read_revenue, read_security_status, read_valuation,
)

L2_PRICES = os.path.join(REPO, "data", "b0", "price_panel.parquet")
L2_VALUATION = os.path.join(REPO, "data", "b0", "valuation_panel.parquet")
L2_CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
L2_STATUS = os.path.join(REPO, "data", "b0", "security_status.csv")
L2_LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
L2_BONUS = os.path.join(REPO, "data", "b0", "bonus_share_panel.parquet")
L2_FINANCIALS = os.path.join(REPO, "data", "b0", "financials_pit.parquet")
L2_REVENUE = os.path.join(REPO, "data", "b0", "monthly_revenue_pit.parquet")
L2_INDUSTRY = os.path.join(REPO, "data", "b0", "industry_pit.parquet")

# Both legs are now declared (§2.8.3 splits the lineage at 2019-01-01 and the
# halves live in different trees), so the comparison covers L2's whole panel
# rather than only its archive era. `None` means "from L2's first row".
PARITY_FROM = None

# L2's fundamentals panels stop here; L3's do not.
WINDOW_END = str(frozen_spec("window_end"))

# L2's bonus panel window: the union every 141-period momentum_12_1 / sigma20d
# lookback reaches. Passed in explicitly because it is L2's property, not a
# constant the reader may assume.
BONUS_WINDOW = ("2013-06-29", "2026-03-31")


class ParityError(SystemExit):
    """Fail-loud: the two routes disagree about the same bytes."""


def _frames_equal(a, b, key, columns, label: str) -> int:
    """Row-for-row equality on `columns`, keyed and sorted the same way."""
    import pandas as pd

    a = a.sort_values(key).reset_index(drop=True)
    b = b.sort_values(key).reset_index(drop=True)
    if len(a) != len(b):
        ka = set(map(tuple, a[key].astype(str).values))
        kb = set(map(tuple, b[key].astype(str).values))
        raise ParityError(
            "abort: %s row counts differ — L2 %d, L3 %d\n"
            "  only in L2: %s\n  only in L3: %s"
            % (label, len(a), len(b), sorted(ka - kb)[:5], sorted(kb - ka)[:5]))

    mism = {}
    for col in columns:
        x, y = a[col], b[col]
        if x.dtype == object or y.dtype == object:
            differ = ~((x.astype(str) == y.astype(str))
                       | (x.isna() & y.isna()))
        else:
            differ = ~((x == y) | (x.isna() & y.isna()))
        n = int(differ.sum())
        if n:
            mism[col] = {"rows": n,
                         "first": a.loc[differ, key].head(3).values.tolist(),
                         "l2": x[differ].head(3).tolist(),
                         "l3": y[differ].head(3).tolist()}
    if mism:
        raise ParityError(
            "abort: the two routes disagree on the same bytes (%s): %s\n"
            "A second parsing implementation does not fail by crashing."
            % (label, mism))
    return int(len(a))


# --- prices / valuation / calendar ----------------------------------------------

def verify_prices(run_dir: str, sample_to: str = "",
                  sample_from: str = "") -> dict:
    """Both legs against the whole sealed panel.

    The two legs disagree about what a volume number means — the archive leg
    publishes 成交量(千股) and the cache leg publishes shares — so a comparison
    that covered only one era would leave the other convention unchecked, and
    getting it wrong moves every security 1000x across §4.2's absolute NTD
    liquidity floor without raising.
    """
    import pandas as pd

    l2 = pd.read_parquet(L2_PRICES, columns=["stock_id", "date", "open",
                                             "close", "volume_shares"])
    l2["date"] = l2["date"].astype(str).str[:10]
    l2["stock_id"] = l2["stock_id"].astype(str)
    lo = sample_from or PARITY_FROM or str(l2["date"].min())
    hi = sample_to or str(l2["date"].max())
    l2 = l2[(l2["date"] >= lo) & (l2["date"] <= hi)]

    l3 = read_prices(run_dir, lo, hi)
    rows = _frames_equal(l2, l3, ["stock_id", "date"],
                         ["open", "close", "volume_shares"], "prices")
    eras = {"pre_2019": int((l2["date"] < "2019-01-01").sum()),
            "from_2019": int((l2["date"] >= "2019-01-01").sum())}
    return {"rows": rows, "range": [lo, hi], "rows_by_era": eras,
            "columns_checked": ["open", "close", "volume_shares"]}


def verify_valuation(run_dir: str, as_of: str) -> dict:
    import pandas as pd

    panel = pd.read_parquet(L2_VALUATION)
    panel = panel[panel["as_of"].astype(str) == as_of]
    if panel.empty:
        raise ParityError(
            "abort: L2's valuation panel has no rows for as_of %s, so there is "
            "nothing to check the reader against." % as_of)

    l3 = read_valuation(run_dir)

    checked = differ = 0
    examples = []
    for row in panel.itertuples(index=False):
        sid = str(row.stock_id)
        if sid not in l3:
            continue
        for col in ("per_tse", "pbr_tse"):
            want = getattr(row, col)
            got = l3[sid][col]
            want = None if pd.isna(want) else float(want)
            checked += 1
            if want != got:
                differ += 1
                if len(examples) < 5:
                    examples.append((sid, col, want, got))
    if differ:
        raise ParityError(
            "abort: %d of %d valuation values differ, e.g. %s"
            % (differ, checked, examples))
    if not checked:
        raise ParityError("abort: no overlapping securities to compare")
    return {"values_checked": checked, "as_of": as_of}


def verify_calendar(run_dir: str) -> dict:
    with open(L2_CALENDAR, encoding="utf-8") as fh:
        l2 = tuple(sorted(r["session"] for r in csv.DictReader(fh)))
    l3 = read_calendar(run_dir)

    # PREFIX, not equality: L2 is frozen at its own last session and L3's
    # declared series runs past it.
    if l3[:len(l2)] != l2:
        first = next((i for i in range(min(len(l2), len(l3)))
                      if l2[i] != l3[i]), None)
        raise ParityError(
            "abort: the declared calendar is not a suffix-extension of L2's.\n"
            "  first divergence at index %s: L2 %s / L3 %s\n"
            "A calendar that re-dates a past session re-dates every decision "
            "that stood on it."
            % (first, l2[first] if first is not None else "-",
               l3[first] if first is not None else "-"))
    return {"l2_sessions": len(l2), "l3_sessions": len(l3),
            "extension": list(l3[len(l2):])}


# --- security_status ------------------------------------------------------------

def verify_security_status(run_dir: str) -> dict:
    """Exact equality. This table is not window-bounded on either side.

    It is also the one whose divergence would be hardest to see downstream:
    B0.6 exists because `status_available_from` was absent from the state, and
    a reader that lost the resumption rows would not raise — it would leave
    every suspension explaining gaps forever.
    """
    with open(L2_STATUS, encoding="utf-8") as fh:
        l2 = list(csv.DictReader(fh))
    l3 = read_security_status(run_dir)

    if len(l2) != len(l3):
        raise ParityError(
            "abort: security_status row counts differ — L2 %d, L3 %d. A lost "
            "resumption row lets a suspension explain a gap forever; a lost "
            "delisting row makes an exit invisible." % (len(l2), len(l3)))
    for i, (a, b) in enumerate(zip(l2, l3)):
        for col in STATUS_COLUMNS:
            if str(a[col]) != str(b[col]):
                raise ParityError(
                    "abort: security_status row %d differs on %r\n"
                    "  L2: %s\n  L3: %s" % (i, col, a, b))
    statuses = sorted({r["status"] for r in l3})
    return {"records": len(l3),
            "securities": len({r["stock_id"] for r in l3}),
            "statuses": statuses}


# --- corporate_actions ----------------------------------------------------------

def _ledger_csv_text(rows) -> str:
    """Exactly what `csv.DictWriter` wrote, so the comparison is on bytes."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(LEDGER_COLUMNS))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def verify_corporate_actions(run_dir: str) -> dict:
    """Byte-for-byte against the sealed ledger.

    Byte equality rather than value equality is the right check here because
    this ledger is consumed as a CSV downstream — `build_bonus_share_panel`
    reads it with `csv.DictReader` and compares strings. A float that
    round-trips to a different repr is a real difference to that consumer even
    though it is the same number.
    """
    with open(L2_LEDGER, encoding="utf-8", newline="") as fh:
        want = fh.read()
    rows = read_corporate_actions(run_dir)
    got = _ledger_csv_text(rows)

    if got != want:
        a, b = want.splitlines(), got.splitlines()
        first = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]),
                     min(len(a), len(b)))
        raise ParityError(
            "abort: the corporate-action ledger differs.\n"
            "  L2 lines %d / L3 lines %d, first divergence at line %d\n"
            "  L2: %s\n  L3: %s"
            % (len(a), len(b), first,
               a[first] if first < len(a) else "<eof>",
               b[first] if first < len(b) else "<eof>"))

    kinds = sorted({r["kind"] for r in rows})
    exits = sum(1 for r in rows
                if r["kind"] == "holder_side_reorganization_exit")
    return {"events": len(rows), "kinds": len(kinds),
            "holder_side_reorganization_exits": exits,
            "not_reconstructible": sum(
                1 for r in rows
                if r["reconstructibility"] == "NOT_RECONSTRUCTIBLE")}


# --- bonus_shares ---------------------------------------------------------------

BONUS_COLUMNS = ("official_scheduled_ex_right_date", "market_effective_session",
                 "board", "source_endpoint", "payload_key", "payload_sha256",
                 "bonus_shares_per_1000", "holder_multiplier", "disposition",
                 "ledger_reconstructibility", "parser_version")


def verify_bonus_shares(run_dir: str) -> dict:
    """C-51's holder multiplier, over L2's frozen lookback union.

    The window is passed IN rather than read from the reader, because that is
    the whole point: L2's bounds are L2's, and an L3 run computes its own. What
    parity establishes is that over the shared span the multiplier is the same
    number — and it has to be, because it silently rescales the price series
    momentum reads.
    """
    import pandas as pd

    l2 = pd.read_parquet(L2_BONUS)
    l3 = read_bonus_shares(run_dir, *BONUS_WINDOW)
    rows = _frames_equal(l2, l3, ["stock_id", "market_effective_session"],
                         list(BONUS_COLUMNS), "bonus_shares")
    matched = int((l3["disposition"] == "OFFICIAL_BONUS_RATE").sum())
    return {"events": rows, "window": list(BONUS_WINDOW),
            "matched_official_bonus_rate": matched,
            "securities": int(l3["stock_id"].nunique())}


# --- financials / revenue / industry --------------------------------------------

def verify_financials(run_dir: str) -> dict:
    """Restricted to `release_date <= window_end`, which is L2's own bound."""
    import pandas as pd

    l2 = pd.read_parquet(L2_FINANCIALS)
    l3 = read_financials(run_dir)
    l3 = l3[l3["release_date"] <= pd.Timestamp(WINDOW_END)].copy()

    for f in (l2, l3):
        f["date"] = f["date"].astype(str).str[:10]
        f["release_date"] = f["release_date"].astype(str).str[:10]
        f["stock_id"] = f["stock_id"].astype(str)

    cols = [c for c in l2.columns if c not in ("stock_id", "date")]
    rows = _frames_equal(l2, l3, ["stock_id", "date"], cols, "financials")
    return {"rows": rows, "restricted_to": "release_date <= %s" % WINDOW_END,
            "columns_checked": len(cols),
            "securities": int(l3["stock_id"].nunique())}


def verify_revenue(run_dir: str) -> dict:
    """Restricted the same way, for the same reason."""
    import pandas as pd

    l2 = pd.read_parquet(L2_REVENUE)
    l3 = read_revenue(run_dir)
    l3 = l3[l3["release_date"] <= WINDOW_END].copy()

    for f in (l2, l3):
        f["date"] = f["date"].astype(str).str[:10]
        f["release_date"] = f["release_date"].astype(str).str[:10]
        f["stock_id"] = f["stock_id"].astype(str)

    rows = _frames_equal(l2, l3, ["stock_id", "date"],
                         ["release_date", "revenue"], "revenue")
    return {"rows": rows, "restricted_to": "release_date <= %s" % WINDOW_END,
            "first_real_release_date": str(l3["release_date"].min()),
            "securities": int(l3["stock_id"].nunique())}


def verify_industry(run_dir: str) -> dict:
    """Exact. §2.3's step function must have exactly ONE construction.

    L2's own builder already re-derives this timeline and aborts if it differs
    from the frozen artefact, for the same reason: a second construction that
    disagrees is a second definition of what a security's industry WAS.
    """
    import pandas as pd

    l2 = pd.read_parquet(L2_INDUSTRY)
    l3 = read_industry(run_dir)
    cols = ["stock_id", "effective_from", "tse_ind_code"]

    a = l2[cols].astype(str).sort_values(cols).reset_index(drop=True)
    b = l3[cols].astype(str).sort_values(cols).reset_index(drop=True)
    if len(a) != len(b) or not a.equals(b):
        raise ParityError(
            "abort: the PIT industry timeline differs (%d vs %d rows). §2.3's "
            "step function must have exactly one construction; investigate "
            "rather than pick one." % (len(a), len(b)))

    l2_unres = set(l2[l2["unresolved_from"].notna()]["stock_id"].astype(str))
    l3_unres = set(l3[l3["unresolved_from"].notna()]["stock_id"].astype(str))
    if l2_unres != l3_unres:
        raise ParityError(
            "abort: UNRESOLVED sets differ (L2 %d / L3 %d securities). "
            "UNRESOLVED means industry NA, which means Value NA, which means "
            "§4.1 drops the security — so this changes the universe."
            % (len(l2_unres), len(l3_unres)))
    return {"rows": int(len(b)),
            "securities": int(l3["stock_id"].nunique()),
            "unresolved_securities": len(l3_unres)}


# --- all ------------------------------------------------------------------------

VERIFIERS = {
    "calendar": lambda d, a: verify_calendar(d),
    "security_status": lambda d, a: verify_security_status(d),
    "industry": lambda d, a: verify_industry(d),
    "revenue": lambda d, a: verify_revenue(d),
    "financials": lambda d, a: verify_financials(d),
    "valuation": lambda d, a: verify_valuation(d, a),
    "corporate_actions": lambda d, a: verify_corporate_actions(d),
    "bonus_shares": lambda d, a: verify_bonus_shares(d),
    "prices": lambda d, a: verify_prices(d),
}


def verify_all(run_dir: str, as_of: str, only=()) -> dict:
    """Every family, cheapest first so a common mistake fails fast."""
    out = {}
    for name, fn in VERIFIERS.items():
        if only and name not in only:
            continue
        out[name] = fn(run_dir, as_of)
    return out


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: verify_reader_parity.py <run_dir> [as_of] [family ...]")
        return 2
    run_dir = argv[1]
    as_of = argv[2] if len(argv) > 2 else "2026-03-30"
    only = tuple(argv[3:])
    import json

    print(json.dumps(verify_all(run_dir, as_of, only), ensure_ascii=False,
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
