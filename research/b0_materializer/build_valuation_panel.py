# -*- coding: utf-8 -*-
"""C-48 / C-49 · the sealed valuation panel the route replays against.

Two ratios, two eras, one boundary — the boundary §2.8.3 already fixed for
prices, reused rather than re-decided:

    <= 2018-12-31   股價淨值比-TSE / 本益比-TSE from the admissible yearly export
    >= 2019-01-01   official exchange 股價淨值比 / 本益比: TWSE for 上市,
                    TPEx for 上櫃, both read from the SAME published row

Both ratios land in ONE panel on purpose. They are two columns of one published
row, they share a session, a board attribution and an NA semantics, and building
them separately would create two artefacts that could disagree about which
securities an exchange listed on a given day.

Four things this builder is careful about, each because getting it wrong is
silent rather than loud:

  1. **It keys on the ROUTE's session.** `b0_route.resolve_as_of` (§6.6) takes
     the last completed session STRICTLY BEFORE the decision date. The lineage
     audit measured coverage on the last session on or before the month end,
     which is one session later whenever the month end is itself a session —
     85 of the 141 decision months. A panel on the audit's set would be keyed to
     sessions the route never asks for, and every number in it would still look
     entirely reasonable. `assert_panel_sessions_match_route` re-derives the
     answer through `resolve_as_of` itself rather than trusting this file.
  2. **The 0.0 sentinel is not a number.** The yearly export writes exactly 0.0
     where a ratio is undefined — measured, 4,927 PE rows and 7 PBR rows in the
     overlap window, never negative, always coinciding with the exchange printing
     `-`. Read as data it would make PEG = 0/g, the cheapest possible rank, out
     of a security with no PE at all. It becomes NA here, which is what the
     frozen domains (C-17 PE > 0, §3.2 PBR > 0) do with it anyway.
  3. **Board attribution is point-in-time by construction** (R4). A security is
     上市 on session s because TWSE published it on s. The current 上市別 label is
     never read; §2.3 shows it is rewritten on delisting.
  4. **A gap stays a gap** (R3). No TEJ fallback, no imputation, no cross-board
     backfill, no derived book-to-market or self-computed PE.

`股價淨值比-TEJ` / `本益比-TEJ` are never read, from either vintage, and the
quarantined 2019+ corpus (`aeda65b9…ea49c1`) is never opened.

    python research/b0_materializer/build_valuation_panel.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_valuation_lineage_audit"))

from harvest_official_pbr import route_as_of_sessions          # noqa: E402
from core.b0_market_state import SourceContract, TradingCalendar   # noqa: E402
from core.b0_master_prereg import spec as frozen_spec           # noqa: E402
from core.b0_route import resolve_as_of                         # noqa: E402
from core.b0_valuation_source import (                          # noqa: E402
    MISSING_VALUE_POLICY,
    VALUATION_PARSER_VERSION,
    ValuationSourceContract,
    assert_valuation_source_admissible,
    lineage_for,
)

IMPORTER_VERSION = "valuation_panel_importer_v1"

ART = os.path.join(REPO, "artifacts", "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
PRE2019_ROUTE = os.path.join(ART, "pre2019_valuation_route.csv")
CLOSES_2019PLUS = os.path.join(ART, "closes_2019plus_route.csv")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
YEARLY_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")

OUT_PARQUET = os.path.join(REPO, "data", "b0", "valuation_panel.parquet")
OUT_RECEIPT = os.path.join(HERE, "valuation_panel_receipt.json")

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


def _ratio(v):
    """Source value -> frozen semantics. 0.0 is the undefined sentinel, not 0."""
    f = _num(v)
    if f is None or f <= 0:
        return None
    return f


def periods() -> list[tuple[str, str, str]]:
    first = str(frozen_spec("first_eligible_decision_month"))
    last = str(frozen_spec("window_end"))[:7]
    out = route_as_of_sessions(first, last)
    expected = int(frozen_spec("window_months"))
    if len(out) != expected:
        raise SystemExit(
            "abort: resolved %d decision periods, the frozen window is %d"
            % (len(out), expected))
    return out


def assert_panel_sessions_match_route(per: list[tuple[str, str, str]]) -> None:
    """The session rule, re-derived through the route rather than restated.

    This is the check that would have caught the month-end convention before it
    reached a sealed artefact, so it runs at build time and not only in a test.
    """
    with open(CALENDAR, encoding="utf-8") as fh:
        sessions = tuple(sorted(r["session"] for r in csv.DictReader(fh)))
    contract = SourceContract(
        name="b0_trading_calendar", kind="trading_calendar",
        importer_version="frozen", content_sha256=_file_sha(CALENDAR),
        schema_sha256=hashlib.sha256(b"session").hexdigest(),
        date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    cal = TradingCalendar(sessions, contract)
    for month, ddate, as_of in per:
        expected = resolve_as_of(ddate, cal)
        if expected != as_of:
            raise SystemExit(
                "abort: %s resolves to %s through b0_route.resolve_as_of, but the "
                "panel would key it to %s. A month-end trading day must never "
                "silently substitute for the strictly-prior as-of session."
                % (month, expected, as_of))


def pre2019_leg(sessions: set[str]) -> tuple[dict, dict]:
    """{(stock_id, session): {'pbr','per','close'}} plus upstream file hashes."""
    import pandas as pd

    if not os.path.exists(PRE2019_ROUTE):
        raise SystemExit(
            "abort: %s not built. Run extract_pre2019_valuation.py with "
            "B0_SESSION_MODE=route." % os.path.relpath(PRE2019_ROUTE, REPO))
    df = pd.read_csv(PRE2019_ROUTE, dtype={"stock_id": str})
    have = set(df["session"].astype(str))
    missing = sessions - have
    if missing:
        raise SystemExit("abort: pre-2019 extract lacks %d as-of sessions: %s"
                         % (len(missing), sorted(missing)[:5]))
    upstream = {}
    for y in sorted({s[:4] for s in sessions}):
        if int(y) >= 2019:
            raise SystemExit("abort: %s is the quarantined vintage era" % y)
        f = os.path.join(YEARLY_DIR, "%sDataExport.xlsx" % y)
        upstream["%sDataExport.xlsx" % y] = _file_sha(f)

    out = {}
    for r in df.itertuples(index=False):
        if str(r.session) not in sessions:
            continue
        out[(str(r.stock_id), str(r.session))] = {
            "pbr": _ratio(r.pbr_tse), "per": _ratio(r.per_tse),
            "close": _num(r.close)}
    return out, upstream


def official_leg(sessions: list[str]) -> tuple[dict, dict]:
    """{(stock_id, session): {'pbr','per','board'}} plus raw payload hashes."""
    out, upstream = {}, {}
    for sess in sessions:
        for src, board in (("twse", "TWSE"), ("tpex", "TPEx")):
            p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
            if not os.path.exists(p):
                raise SystemExit(
                    "abort: %s has no harvested %s payload. A sealed panel may "
                    "not be built over a session whose source was never "
                    "obtained." % (sess, board))
            rec = json.load(open(p, encoding="utf-8"))
            if rec.get("state") != "OK":
                raise SystemExit("abort: %s %s state=%s"
                                 % (sess, board, rec.get("state")))
            if rec.get("parser_version") != VALUATION_PARSER_VERSION:
                raise SystemExit(
                    "abort: %s %s was normalised by parser %r, this build "
                    "declares %r. A panel assembled from two normalisations is a "
                    "mixture nobody declared."
                    % (sess, board, rec.get("parser_version"),
                       VALUATION_PARSER_VERSION))
            upstream["%s_%s" % (src, sess)] = rec["sha256"]
            pbrs = rec.get("values") or {}
            pes = rec.get("pe_values") or {}
            for sid in set(rec.get("raw") or {}) | set(rec.get("pe_raw") or {}):
                key = (str(sid), sess)
                if key in out:
                    raise SystemExit(
                        "abort: %s appears on BOTH boards on %s; board "
                        "attribution would become an unspecified tie-break."
                        % (sid, sess))
                pbr, per = _ratio(pbrs.get(sid)), _ratio(pes.get(sid))
                if pbr is None and per is None:
                    continue
                out[key] = {"pbr": pbr, "per": per, "board": board}
    return out, upstream


def _priced(path: str, sessions: set[str]) -> dict:
    import pandas as pd

    df = pd.read_csv(path, dtype={"stock_id": str})
    out: dict[str, set] = {}
    for r in df.itertuples(index=False):
        s = str(r.session)
        if s not in sessions:
            continue
        c = _num(r.close)
        if c and c > 0:
            out.setdefault(s, set()).add(str(r.stock_id))
    return out


def main() -> None:
    import pandas as pd

    per = periods()
    assert_panel_sessions_match_route(per)
    pre = [(m, d, s) for m, d, s in per if s < "2019-01-01"]
    post = [(m, d, s) for m, d, s in per if s >= "2019-01-01"]
    print("frozen periods: %d (pre-2019 %d, official %d); as-of rule verified "
          "against b0_route.resolve_as_of" % (len(per), len(pre), len(post)),
          flush=True)

    pre_rows, pre_upstream = pre2019_leg({s for _, _, s in pre})
    post_rows, post_upstream = official_leg([s for _, _, s in post])

    if not os.path.exists(CLOSES_2019PLUS):
        raise SystemExit("abort: %s not built"
                         % os.path.relpath(CLOSES_2019PLUS, REPO))
    priced_post = _priced(CLOSES_2019PLUS, {s for _, _, s in post})
    priced_pre: dict[str, set] = {}
    for (sid, sess), v in pre_rows.items():
        if v["close"] and v["close"] > 0:
            priced_pre.setdefault(sess, set()).add(sid)

    records, per_session = [], []
    for month, ddate, sess in per:
        if sess < "2019-01-01":
            rows = {sid: (v["pbr"], v["per"], None)
                    for (sid, s), v in pre_rows.items() if s == sess}
            priced = priced_pre.get(sess, set())
        else:
            rows = {sid: (v["pbr"], v["per"], v["board"])
                    for (sid, s), v in post_rows.items() if s == sess}
            priced = priced_post.get(sess, set())
        if not priced:
            raise SystemExit("abort: no priced universe for %s (%s)"
                             % (month, sess))
        n_pbr = n_per = 0
        for sid, (pbr, pe, board) in sorted(rows.items()):
            if pbr is None and pe is None:
                continue
            n_pbr += int(pbr is not None and sid in priced)
            n_per += int(pe is not None and sid in priced)
            records.append({
                "decision_month": month, "decision_date": ddate, "as_of": sess,
                "stock_id": sid, "pbr_tse": pbr, "per_tse": pe, "board": board,
                "pbr_lineage": lineage_for(sess, "pbr_tse"),
                "per_lineage": lineage_for(sess, "per_tse")})
        per_session.append({
            "decision_month": month, "decision_date": ddate, "as_of": sess,
            "priced": len(priced), "pbr_covered": n_pbr, "per_covered": n_per,
            "pbr_coverage": round(n_pbr / len(priced), 4),
            "per_coverage": round(n_per / len(priced), 4)})

    panel = pd.DataFrame.from_records(records)
    panel = panel.sort_values(["as_of", "stock_id"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    panel.to_parquet(OUT_PARQUET, index=False)

    schema = json.dumps({c: str(panel[c].dtype) for c in panel.columns},
                        sort_keys=True).encode("utf-8")
    schema_sha = hashlib.sha256(schema).hexdigest()
    content_sha = _file_sha(OUT_PARQUET)

    def cov(key: str, era_rows) -> tuple[float, float]:
        vals = [r[key] for r in era_rows]
        return min(vals), max(vals)

    pre_sess = {s for _, _, s in pre}
    era_pre = [r for r in per_session if r["as_of"] in pre_sess]
    era_post = [r for r in per_session if r["as_of"] not in pre_sess]

    contracts = []
    for ratio, covkey in (("pbr_tse", "pbr_coverage"), ("per_tse", "per_coverage")):
        for era_name, era_rows, era_periods, upstream in (
                ("<= 2018-12-31", era_pre, pre, pre_upstream),
                (">= 2019-01-01", era_post, post, post_upstream)):
            lo, hi = cov(covkey, era_rows)
            col = panel[panel["as_of"].isin({s for _, _, s in era_periods})]
            contracts.append(ValuationSourceContract(
                name="valuation_panel_%s_%s" % (
                    ratio, "pre2019" if era_name.startswith("<=") else "official"),
                era=era_name, ratio=ratio,
                lineage=lineage_for(era_periods[0][2], ratio),
                importer_version=IMPORTER_VERSION,
                parser_version=VALUATION_PARSER_VERSION,
                content_sha256=content_sha, schema_sha256=schema_sha,
                date_min=era_periods[0][2], date_max=era_periods[-1][2],
                sessions=len(era_periods),
                securities=int(col[col[ratio].notna()]["stock_id"].nunique()),
                coverage_rate_min=lo, coverage_rate_max=hi,
                na_policy=MISSING_VALUE_POLICY, live_fetch=False,
                upstream_sha256=upstream))
    for c in contracts:
        assert_valuation_source_admissible(c)

    receipt = {
        "artefact": "data/b0/valuation_panel.parquet",
        "builder": "research/b0_materializer/build_valuation_panel.py",
        "ruling": "C-48 (pbr_tse) + C-49 (per_tse)",
        "session_rule": ("b0_route.resolve_as_of — last completed session "
                         "STRICTLY BEFORE the decision date; verified at build "
                         "time against the route for all %d periods" % len(per)),
        "periods": len(per),
        "rows": int(len(panel)),
        "bytes": os.path.getsize(OUT_PARQUET),
        "content_sha256": content_sha,
        "schema_sha256": schema_sha,
        "carried_columns": list(panel.columns),
        "excluded_by_frozen_lineage": list(EXCLUDED_BY_LINEAGE),
        "quarantined_corpus_opened": False,
        "board_attribution": "contemporaneous exchange payload (R4)",
        "na_semantics": {
            "policy": MISSING_VALUE_POLICY,
            "sentinel_zero": ("the yearly export writes 0.0 for an undefined "
                              "ratio; normalised to NA here, which is what the "
                              "frozen PE > 0 / PBR > 0 domains do with it"),
            "official_na_tokens": ["-", "N/A", "null", "<absent row>"],
        },
        "coverage": {
            "pbr_pre2019": cov("pbr_coverage", era_pre),
            "pbr_official": cov("pbr_coverage", era_post),
            "per_pre2019": cov("per_coverage", era_pre),
            "per_official": cov("per_coverage", era_post),
        },
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
    for k, v in receipt["coverage"].items():
        print("coverage %-14s %.4f .. %.4f" % (k, v[0], v[1]))
    print("wrote", os.path.relpath(OUT_PARQUET, REPO),
          "and", os.path.relpath(OUT_RECEIPT, REPO))


if __name__ == "__main__":
    main()
