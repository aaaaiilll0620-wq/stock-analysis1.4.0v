# -*- coding: utf-8 -*-
"""Pre-2019 overlap reconciliation: official exchange PBR vs the admissible
`股價淨值比-TSE` lineage — READ-ONLY, VALUE LEVEL.

Coverage agreement is a weak test: two series can cover the same securities and
still be different numbers. This one compares the number itself, on the same
stock and the same trading session, for month-ends where BOTH sources exist.

Source admissibility, stated because it is the whole point:

  * the lineage side reads the yearly export for 2016-2018 ONLY. §2.8.3 fixes
    the canonical vintage boundary at `<= 2018 既有逐年匯出 / >= 2019 兩個 zip`,
    so pre-2019 yearly data is the admissible side of that boundary. The
    quarantined fingerprint `aeda65b9…ea49c1` is the 2019+ vintage, which this
    script never touches — it stops at 2018-12.
  * `股價淨值比-TEJ` is never read. B-09 freezes B/M on the TSE lineage, and a
    reconciliation that quietly swapped in the other column would be measuring
    the wrong thing.

Reported per board (TWSE 上市 / TPEx 上櫃), because the two exchanges are
separate publishers and an asymmetry between them is exactly what a lineage
continuation ruling has to see:

    exact equality rate            at published precision
    numeric difference distribution absolute and relative
    missingness mismatch           split into `-` vs not-on-that-board
    rounding / display precision    what share of disagreement is <= half a tick
    systematic semantic divergence  signed median, and whether it drifts

This is a lineage audit. No strategy quantity is computed from it, and it may
not be used to tune anything.

    python research/b0_valuation_lineage_audit/reconcile_pre2019_overlap.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from harvest_official_pbr import decision_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
CACHE = os.path.join(ART, "pre2019_lineage_month_ends.csv")
OUT = os.path.join(HERE, "pre2019_overlap_reconciliation.json")

YEARLY_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")
COL_ID, COL_DATE, COL_CLOSE = "代號", "年月日", "收盤價(元)"
COL_PBR_TSE = "股價淨值比-TSE"

OVERLAP_FROM, OVERLAP_TO = "2016-01", "2018-12"
YEARS = (2016, 2017, 2018)          # <= 2018 only: the admissible side of §2.8.3


def lineage_month_ends(sessions: list[str]):
    """(stock_id, session) -> {'pbr': float|None, 'close': float|None}."""
    import pandas as pd

    if os.path.exists(CACHE):
        df = pd.read_csv(CACHE, dtype={"stock_id": str})
    else:
        frames = []
        for y in YEARS:
            f = os.path.join(YEARLY_DIR, "%dDataExport.xlsx" % y)
            if not os.path.exists(f):
                raise SystemExit("abort: missing admissible yearly export %s" % f)
            d = pd.read_excel(f, engine="openpyxl",
                              usecols=[COL_ID, COL_DATE, COL_CLOSE, COL_PBR_TSE])
            d["session"] = pd.to_datetime(
                d[COL_DATE], errors="coerce").dt.strftime("%Y-%m-%d")
            d = d[d["session"].isin(sessions)]
            d["stock_id"] = d[COL_ID].astype(str).str.split().str[0].str.strip()
            d = d.rename(columns={COL_PBR_TSE: "pbr_tse", COL_CLOSE: "close"})
            frames.append(d[["stock_id", "session", "close", "pbr_tse"]])
            print("  read %d: %d rows on overlap sessions" % (y, len(d)),
                  flush=True)
        df = pd.concat(frames, ignore_index=True)
        df.to_csv(CACHE, index=False, encoding="utf-8")
    df["pbr_tse"] = df["pbr_tse"].astype(str).str.strip()
    out = {}
    def _f(v):
        # NaN must become None here. `float('nan') is not None` is True, so a
        # missing lineage value would otherwise count as a present one and turn
        # the whole missingness comparison inside out.
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if f != f else f

    for r in df.itertuples(index=False):
        pbr = _f(r.pbr_tse)
        close = _f(r.close)
        out[(str(r.stock_id), str(r.session))] = {"pbr": pbr, "close": close}
    return out


def load_norm(src: str, sess: str):
    p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def summarise(pairs, board: str) -> dict:
    """pairs: list of (session, sid, official_float, official_raw, lineage_float)"""
    diffs = [o - l for _, _, o, _, l in pairs]
    ad = sorted(abs(d) for d in diffs)
    rel = [abs(o - l) / abs(l) for _, _, o, _, l in pairs if l]
    n = len(pairs)

    def q(v, p):
        return round(v[int(p * (len(v) - 1))], 6) if v else None

    # "Exact" is judged at the coarser of the two published precisions: both
    # sources print two decimals, so equality below that is not a claim either
    # source makes.
    dec = [_decimals(r) for _, _, _, r, _ in pairs]
    tick = 10 ** -(min(dec) if dec else 2)
    exact = sum(1 for d in ad if d < 1e-9)
    within_half_tick = sum(1 for d in ad if d <= tick / 2 + 1e-12)
    disagreements = sorted(
        ({"session": s, "stock_id": sid, "official": o, "lineage": l,
          "diff": round(o - l, 6)}
         for s, sid, o, _, l in pairs if abs(o - l) >= 1e-9),
        key=lambda r: (r["session"], r["stock_id"]))
    return {
        "board": board,
        "compared": n,
        "exact_equal": exact,
        "exact_equal_rate": round(exact / n, 4) if n else None,
        "published_decimals_official_min": min(dec) if dec else None,
        "published_decimals_official_max": max(dec) if dec else None,
        "tick": tick,
        "within_half_tick": within_half_tick,
        "within_half_tick_rate": round(within_half_tick / n, 4) if n else None,
        "abs_diff_p50": q(ad, 0.50), "abs_diff_p90": q(ad, 0.90),
        "abs_diff_p99": q(ad, 0.99), "abs_diff_max": round(ad[-1], 6) if ad else None,
        "signed_diff_mean": round(statistics.fmean(diffs), 6) if diffs else None,
        "signed_diff_median": round(statistics.median(diffs), 6) if diffs else None,
        "rel_diff_p50": round(statistics.median(rel), 6) if rel else None,
        "rel_diff_gt_1pct": sum(1 for r in rel if r > 0.01),
        "rel_diff_gt_5pct": sum(1 for r in rel if r > 0.05),
        "abs_diff_gt_0_02": sum(1 for d in ad if d > 0.02),
        "disagreements": disagreements[:200],
        "disagreement_sessions": sorted({d["session"] for d in disagreements}),
    }


def main() -> None:
    months = decision_sessions(OVERLAP_FROM, OVERLAP_TO)
    sessions = [s for _, _, s in months]
    print("overlap month-end sessions: %d (%s .. %s)" % (
        len(sessions), sessions[0], sessions[-1]), flush=True)

    have = {s: {src: load_norm(src, s) for src in ("twse", "tpex")}
            for s in sessions}
    usable = [s for s in sessions
              if have[s]["twse"] is not None and have[s]["tpex"] is not None]
    print("sessions with both official payloads: %d" % len(usable), flush=True)
    if not usable:
        raise SystemExit("abort: no overlap session harvested yet")

    lineage = lineage_month_ends(usable)
    print("lineage rows loaded: %d" % len(lineage), flush=True)

    per_board = {"twse": [], "tpex": []}
    # Per board: rows the exchange published that session, cross-classified
    # against the lineage. `lineage_only_on_neither_board` is counted once per
    # session, not per board, because it is a statement about both.
    mismatch = {"twse": {"official_only": 0, "lineage_explicit_na_on_board": 0,
                         "both_missing": 0},
                "tpex": {"official_only": 0, "lineage_explicit_na_on_board": 0,
                         "both_missing": 0},
                "lineage_only_on_neither_board": 0}
    per_session = []
    close_checks = {"compared": 0, "equal": 0, "max_abs_diff": 0.0}

    # The comparison population is PRICED securities — the same definition the
    # 2019+ coverage audit uses for `required`. Comparing over the exchange's
    # row set instead would silently exclude every security the exchange does
    # not report, which is precisely the class a lineage switch would lose.
    priced_by_session: dict[str, set] = {}
    for (sid, sess), lin in lineage.items():
        if lin.get("close") and lin["close"] > 0:
            priced_by_session.setdefault(sess, set()).add(sid)

    for sess in usable:
        rec = {"session": sess}
        t, p = have[sess]["twse"], have[sess]["tpex"]
        board = {"twse": (t.get("values", {}), t.get("raw", {}), t.get("close", {})),
                 "tpex": (p.get("values", {}), p.get("raw", {}), p.get("close", {}))}
        published = set(board["twse"][1]) | set(board["tpex"][1])
        priced = priced_by_session.get(sess, set())
        comp = {"twse": 0, "tpex": 0}
        lin_only_off_board = 0

        for sid in priced:
            lin = lineage.get((sid, sess)) or {}
            lin_pbr = lin.get("pbr")
            src = ("twse" if sid in board["twse"][1] else
                   "tpex" if sid in board["tpex"][1] else None)
            if src is None:
                if lin_pbr is not None:
                    lin_only_off_board += 1
                continue
            vals, raws, closes = board[src]
            off = vals.get(sid)
            if off is not None and lin_pbr is not None:
                per_board[src].append((sess, sid, off, raws[sid], lin_pbr))
                comp[src] += 1
                if lin.get("close") is not None and closes.get(sid):
                    close_checks["compared"] += 1
                    d = abs(closes[sid] - lin["close"])
                    close_checks["max_abs_diff"] = max(
                        close_checks["max_abs_diff"], d)
                    if d < 1e-9:
                        close_checks["equal"] += 1
            elif off is not None and lin_pbr is None:
                mismatch[src]["official_only"] += 1
            elif off is None and lin_pbr is not None:
                mismatch[src]["lineage_explicit_na_on_board"] += 1
            else:
                mismatch[src]["both_missing"] += 1

        rec["priced"] = len(priced)
        rec["twse_compared"] = comp["twse"]
        rec["tpex_compared"] = comp["tpex"]
        rec["lineage_only_on_neither_board"] = lin_only_off_board
        rec["priced_on_no_board"] = len(priced - published)
        mismatch["lineage_only_on_neither_board"] += lin_only_off_board
        per_session.append(rec)

    report = {
        "audit": "pre2019_overlap_value_reconciliation",
        "overlap_window": {"from": OVERLAP_FROM, "to": OVERLAP_TO,
                           "sessions_requested": len(sessions),
                           "sessions_usable": len(usable)},
        "lineage_source": ("yearly export 2016-2018, column 股價淨值比-TSE "
                           "(<= 2018 side of the §2.8.3 vintage boundary)"),
        "used_pbr_tej": False,
        "used_quarantined_corpus": False,
        "b0_modified": False,
        "decision_or_performance_computed": False,
        "twse": summarise(per_board["twse"], "TWSE 上市"),
        "tpex": summarise(per_board["tpex"], "TPEx 上櫃"),
        "missingness_mismatch": mismatch,
        "close_price_cross_check": {
            **close_checks,
            "note": ("same-session alignment evidence: where both sources print a "
                     "close, they should agree; a systematic mismatch would mean "
                     "the two series are not keyed to the same session. A "
                     "published close of 0.00 means the security did not trade "
                     "that session — the exchange still publishes the ratio — so "
                     "those rows are excluded from this check rather than counted "
                     "as disagreement"),
        },
        "per_session_compared": per_session,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    for k in ("twse", "tpex"):
        s = report[k]
        print("%s: n=%s exact=%s (%s) |d|p50=%s p99=%s max=%s med_signed=%s" % (
            k.upper(), s["compared"], s["exact_equal"], s["exact_equal_rate"],
            s["abs_diff_p50"], s["abs_diff_p99"], s["abs_diff_max"],
            s["signed_diff_median"]))
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
