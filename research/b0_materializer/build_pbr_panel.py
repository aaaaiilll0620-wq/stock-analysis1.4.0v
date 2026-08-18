# -*- coding: utf-8 -*-
"""C-48 / R5 · the sealed `pbr_tse` panel the route replays against.

One field, two eras, one boundary — the same boundary §2.8.3 already fixed for
prices, reused rather than re-decided:

    <= 2018-12-31   股價淨值比-TSE from the admissible yearly export
    >= 2019-01-01   official exchange PBR: TWSE for 上市, TPEx for 上櫃

Three things this builder is careful about, each because getting it wrong is
silent rather than loud:

  1. **It keys on the ROUTE's session, not the month end.** `b0_route.resolve_as_of`
     (§6.6) takes the last completed session STRICTLY BEFORE the decision date.
     The lineage audit measured coverage on the last session on or before the
     month end, which is one session later whenever the month end is itself a
     session — 85 of the 141 decision months. A panel built on the audit's set
     would be keyed to a session the route never asks for, and every number in it
     would still look entirely reasonable.
  2. **Board attribution is point-in-time by construction** (R4). A security is
     上市 on session s because TWSE published it on s, 上櫃 because TPEx did. The
     current 上市別 label is never read; §2.3 shows it is rewritten on delisting.
  3. **A gap stays a gap** (R3). No TEJ fallback, no imputation, no cross-board
     backfill, no book-equity-over-shares derivation. Missing means missing, and
     §4.1 complete-case is what acts on it.

`股價淨值比-TEJ` is never read, from either vintage. The quarantined 2019+ corpus
(`aeda65b9…ea49c1`) is never opened; the pre-2019 leg reads only years <= 2018,
which is the admissible side of the vintage boundary.

Emits `data/b0/pbr_panel.parquet` plus a receipt carrying two
`ValuationSourceContract`s — one per era — each of which must pass
`assert_valuation_source_admissible` before anything is written.

READ-ONLY with respect to strategy: no feature, score, ranking, portfolio or
performance quantity is computed here.

    python research/b0_materializer/build_pbr_panel.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_valuation_lineage_audit"))

from harvest_official_pbr import route_as_of_sessions          # noqa: E402
from core.b0_master_prereg import spec as frozen_spec           # noqa: E402
from core.b0_valuation_source import (                          # noqa: E402
    MISSING_VALUE_POLICY,
    VALUATION_PARSER_VERSION,
    ValuationSourceContract,
    assert_valuation_source_admissible,
    lineage_for,
)

IMPORTER_VERSION = "pbr_panel_importer_v1"

ART = os.path.join(REPO, "artifacts", "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
YEARLY_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")
CLOSES_2019PLUS = os.path.join(ART, "closes_2019plus_route.csv")

OUT_PARQUET = os.path.join(REPO, "data", "b0", "pbr_panel.parquet")
OUT_RECEIPT = os.path.join(HERE, "pbr_panel_receipt.json")
PRE2019_CACHE = os.path.join(ART, "pre2019_pbr_route_sessions.csv")

COL_ID, COL_DATE, COL_CLOSE = "代號", "年月日", "收盤價(元)"
COL_PBR_TSE = "股價淨值比-TSE"
# Present in the same sheet and deliberately never read — B-09 freezes the TSE
# lineage, and a builder that touched the TEJ column would make substituting it
# a one-word edit.
EXCLUDED_BY_LINEAGE = ("股價淨值比-TEJ", "本益比-TEJ")


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def periods() -> list[tuple[str, str, str]]:
    """(decision_month, decision_date, as_of) for all 141 frozen periods."""
    first = str(frozen_spec("first_eligible_decision_month"))
    last = str(frozen_spec("window_end"))[:7]
    out = route_as_of_sessions(first, last)
    expected = int(frozen_spec("window_months"))
    if len(out) != expected:
        raise SystemExit(
            "abort: resolved %d decision periods, the frozen window is %d"
            % (len(out), expected))
    return out


# --- era 1 · <= 2018, admissible yearly export --------------------------------

def pre2019_leg(sessions: list[str]) -> tuple[dict, dict]:
    """{(stock_id, session): {'pbr','close'}}, plus upstream file hashes."""
    import pandas as pd

    years = sorted({s[:4] for s in sessions})
    upstream = {}
    if os.path.exists(PRE2019_CACHE):
        df = pd.read_csv(PRE2019_CACHE, dtype={"stock_id": str})
        for y in years:
            f = os.path.join(YEARLY_DIR, "%sDataExport.xlsx" % y)
            upstream["%sDataExport.xlsx" % y] = _file_sha(f)
    else:
        frames = []
        for y in years:
            f = os.path.join(YEARLY_DIR, "%sDataExport.xlsx" % y)
            if not os.path.exists(f):
                raise SystemExit("abort: missing admissible yearly export %s" % f)
            if int(y) >= 2019:
                raise SystemExit(
                    "abort: %s is the quarantined 2019+ vintage; the pre-2019 leg "
                    "must stop at 2018 (§2.8.3)" % f)
            upstream["%sDataExport.xlsx" % y] = _file_sha(f)
            d = pd.read_excel(f, engine="openpyxl",
                              usecols=[COL_ID, COL_DATE, COL_CLOSE, COL_PBR_TSE])
            d["session"] = pd.to_datetime(
                d[COL_DATE], errors="coerce").dt.strftime("%Y-%m-%d")
            d = d[d["session"].isin(sessions)]
            d["stock_id"] = d[COL_ID].astype(str).str.split().str[0].str.strip()
            d = d.rename(columns={COL_PBR_TSE: "pbr", COL_CLOSE: "close"})
            frames.append(d[["stock_id", "session", "close", "pbr"]])
            print("  %s: %d rows on as-of sessions" % (y, len(d)), flush=True)
        df = pd.concat(frames, ignore_index=True)
        df.to_csv(PRE2019_CACHE, index=False, encoding="utf-8", lineterminator="\n")

    out = {}
    for r in df.itertuples(index=False):
        out[(str(r.stock_id), str(r.session))] = {
            "pbr": _num(r.pbr), "close": _num(r.close)}
    return out, upstream


# --- era 2 · >= 2019, official exchanges --------------------------------------

def official_leg(sessions: list[str]) -> tuple[dict, dict]:
    """{(stock_id, session): {'pbr','board'}}, plus raw payload hashes."""
    out, upstream = {}, {}
    for sess in sessions:
        for src, board in (("twse", "TWSE"), ("tpex", "TPEx")):
            p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
            if not os.path.exists(p):
                raise SystemExit(
                    "abort: %s has no harvested %s payload. A sealed panel may "
                    "not be built over a session whose source was never "
                    "obtained — that is the transport-failure-as-history "
                    "confusion the harvester exists to prevent." % (sess, board))
            rec = json.load(open(p, encoding="utf-8"))
            if rec.get("state") != "OK":
                raise SystemExit("abort: %s %s state=%s" % (sess, board,
                                                            rec.get("state")))
            upstream["%s_%s" % (src, sess)] = rec["sha256"]
            for sid, pbr in (rec.get("values") or {}).items():
                key = (str(sid), sess)
                if key in out:
                    # R4 / PIT board membership: the two reports partitioned
                    # cleanly across the whole audit. If that ever stops holding,
                    # "which board" becomes a choice, and a choice needs a rule.
                    raise SystemExit(
                        "abort: %s appears on BOTH boards on %s. Board "
                        "attribution would become an unspecified tie-break."
                        % (sid, sess))
                v = _num(pbr)
                if v is not None and v > 0:
                    out[key] = {"pbr": v, "board": board}
    return out, upstream


def main() -> None:
    import pandas as pd

    per = periods()
    pre = [(m, d, s) for m, d, s in per if s < "2019-01-01"]
    post = [(m, d, s) for m, d, s in per if s >= "2019-01-01"]
    print("frozen periods: %d (pre-2019 %d, official %d)" % (
        len(per), len(pre), len(post)), flush=True)

    pre_rows, pre_upstream = pre2019_leg([s for _, _, s in pre])
    post_rows, post_upstream = official_leg([s for _, _, s in post])

    if not os.path.exists(CLOSES_2019PLUS):
        raise SystemExit(
            "abort: %s not built. Coverage needs the priced universe from the "
            "admissible 2019+ zips." % os.path.relpath(CLOSES_2019PLUS, REPO))
    closes = pd.read_csv(CLOSES_2019PLUS, dtype={"stock_id": str})
    priced_post = {}
    for r in closes.itertuples(index=False):
        c = _num(r.close)
        if c and c > 0:
            priced_post.setdefault(str(r.session), set()).add(str(r.stock_id))
    priced_pre: dict[str, set] = {}
    for (sid, sess), v in pre_rows.items():
        if v["close"] and v["close"] > 0:
            priced_pre.setdefault(sess, set()).add(sid)

    records, per_session = [], []
    for month, ddate, sess in per:
        lineage = lineage_for(sess)
        if lineage == "yearly_export_pbr_tse":
            vals = {sid: (v["pbr"], None) for (sid, s), v in pre_rows.items()
                    if s == sess and v["pbr"] is not None and v["pbr"] > 0}
            priced = priced_pre.get(sess, set())
        else:
            vals = {sid: (v["pbr"], v["board"]) for (sid, s), v in post_rows.items()
                    if s == sess}
            priced = priced_post.get(sess, set())
        for sid, (pbr, board) in sorted(vals.items()):
            records.append({"decision_month": month, "decision_date": ddate,
                            "as_of": sess, "stock_id": sid, "pbr": pbr,
                            "board": board, "lineage": lineage})
        covered = len(set(vals) & priced) if priced else 0
        per_session.append({
            "decision_month": month, "decision_date": ddate, "as_of": sess,
            "lineage": lineage, "priced": len(priced), "with_pbr": len(vals),
            "covered": covered,
            "coverage_rate": round(covered / len(priced), 4) if priced else None,
        })
        if not priced:
            raise SystemExit(
                "abort: no priced universe for %s (%s); coverage would be "
                "unmeasurable and the receipt would claim otherwise"
                % (month, sess))

    panel = pd.DataFrame.from_records(records)
    panel = panel.sort_values(["as_of", "stock_id"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    panel.to_parquet(OUT_PARQUET, index=False)

    schema = json.dumps({c: str(panel[c].dtype) for c in panel.columns},
                        sort_keys=True).encode("utf-8")
    cov_pre = [r["coverage_rate"] for r in per_session
               if r["lineage"] == "yearly_export_pbr_tse"]
    cov_post = [r["coverage_rate"] for r in per_session
                if r["lineage"] == "official_exchange_pbr"]

    contracts = [
        ValuationSourceContract(
            name="pbr_panel_pre2019", era="<= 2018-12-31",
            lineage="yearly_export_pbr_tse",
            importer_version=IMPORTER_VERSION,
            parser_version=VALUATION_PARSER_VERSION,
            content_sha256=_file_sha(OUT_PARQUET),
            schema_sha256=hashlib.sha256(schema).hexdigest(),
            date_min=pre[0][2], date_max=pre[-1][2], sessions=len(pre),
            securities=int(panel[panel["lineage"] == "yearly_export_pbr_tse"]
                           ["stock_id"].nunique()),
            coverage_rate_min=min(cov_pre), coverage_rate_max=max(cov_pre),
            na_policy=MISSING_VALUE_POLICY, live_fetch=False,
            upstream_sha256=pre_upstream),
        ValuationSourceContract(
            name="pbr_panel_official_2019plus", era=">= 2019-01-01",
            lineage="official_exchange_pbr",
            importer_version=IMPORTER_VERSION,
            parser_version=VALUATION_PARSER_VERSION,
            content_sha256=_file_sha(OUT_PARQUET),
            schema_sha256=hashlib.sha256(schema).hexdigest(),
            date_min=post[0][2], date_max=post[-1][2], sessions=len(post),
            securities=int(panel[panel["lineage"] == "official_exchange_pbr"]
                           ["stock_id"].nunique()),
            coverage_rate_min=min(cov_post), coverage_rate_max=max(cov_post),
            na_policy=MISSING_VALUE_POLICY, live_fetch=False,
            upstream_sha256=post_upstream),
    ]
    for c in contracts:
        assert_valuation_source_admissible(c)

    receipt = {
        "artefact": "data/b0/pbr_panel.parquet",
        "builder": "research/b0_materializer/build_pbr_panel.py",
        "ruling": "C-48 (R1-R7)",
        "session_rule": ("§6.6 / b0_route.resolve_as_of — last completed session "
                         "STRICTLY BEFORE the decision date; this is NOT the "
                         "month-end session the coverage audit used"),
        "periods": len(per),
        "rows": int(len(panel)),
        "bytes": os.path.getsize(OUT_PARQUET),
        "content_sha256": _file_sha(OUT_PARQUET),
        "schema_sha256": hashlib.sha256(schema).hexdigest(),
        "carried_columns": list(panel.columns),
        "excluded_by_frozen_lineage": list(EXCLUDED_BY_LINEAGE),
        "quarantined_corpus_opened": False,
        "board_attribution": "contemporaneous exchange payload (R4)",
        "na_policy": MISSING_VALUE_POLICY,
        "coverage_pre2019": {"min": min(cov_pre), "max": max(cov_pre)},
        "coverage_official": {"min": min(cov_post), "max": max(cov_post)},
        "contracts": [
            {k: (dict(v) if k == "upstream_sha256" else v)
             for k, v in c.__dict__.items()} for c in contracts],
        "per_session": per_session,
        "performance_computed": False,
    }
    with open(OUT_RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("rows=%d periods=%d securities=%d" % (
        len(panel), len(per), panel["stock_id"].nunique()))
    print("coverage pre-2019 : %.4f .. %.4f" % (min(cov_pre), max(cov_pre)))
    print("coverage official : %.4f .. %.4f" % (min(cov_post), max(cov_post)))
    print("wrote", os.path.relpath(OUT_PARQUET, REPO),
          "and", os.path.relpath(OUT_RECEIPT, REPO))


if __name__ == "__main__":
    main()
