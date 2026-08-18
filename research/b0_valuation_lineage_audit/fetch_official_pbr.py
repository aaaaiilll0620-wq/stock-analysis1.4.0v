# -*- coding: utf-8 -*-
"""Official Exchange Valuation Lineage Audit — fetch step (READ-ONLY).

Asks one question and nothing else: can the OFFICIAL exchanges supply a
point-in-time 股價淨值比 (PBR) for every B0 decision month from 2019-01 to
2026-03, for both boards?

    TWSE  上市  /rwd/zh/afterTrading/BWIBBU_d   個股日本益比、殖利率及股價淨值比
    TPEx  上櫃  /www/zh-tw/afterTrading/peQryDate  同名報表（ROC 日期）

Both publish the ratio as of a TRADING SESSION, so the query date must be a real
session. Querying a month-end that was not a session returns an empty payload
that looks exactly like "no history" — 2019-01-31 is such a date (the last
session before Lunar New Year 2019 was 2019-01-30). The session per decision
month is therefore resolved from the FROZEN trading calendar, never assumed.

This script does not decide anything. It fetches, caches the raw payloads for
provenance, and records coverage. Whether an official source may replace the
2019+ TSE lineage is a ruling, and `value_pbr_lineage_2019plus` stays open until
one is made.

Explicitly NOT done here: no PBR_TEJ is read, no quarantined corpus is opened,
no B0 module is modified, no decision/selection/performance quantity is computed.

    python research/b0_valuation_lineage_audit/fetch_official_pbr.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_master_prereg import spec as frozen_spec        # noqa: E402

RAW_DIR = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                       os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TWSE = ("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
        "?date={ymd}&selectType=ALL&response=json")
TPEX = ("https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"
        "?date={roc}&response=json")

# TWSE throttles hard and then refuses TCP entirely (curl reports HTTP 000), so
# the two sources are harvested separately and at different rates. Pacing is
# environment-controlled rather than hard-coded, because the polite rate is a
# property of the host on the day, not of this audit.
PAUSE = float(os.environ.get("B0_AUDIT_PAUSE", "4"))
RETRIES = int(os.environ.get("B0_AUDIT_RETRIES", "3"))
BACKOFF = float(os.environ.get("B0_AUDIT_BACKOFF", "10"))
# "twse", "tpex", or "both"
ONLY = os.environ.get("B0_AUDIT_SOURCE", "both").lower()


def sessions_for_decision_months() -> list[tuple[str, str, str]]:
    """(decision_month, decision_date, as_of_session) for the 2019+ window."""
    import pandas as pd

    with open(CALENDAR, encoding="utf-8") as fh:
        sess = sorted(r["session"] for r in csv.DictReader(fh))
    s = pd.Series(pd.to_datetime(sess))
    months = pd.date_range(frozen_spec("window_start"), frozen_spec("window_end"),
                           freq="ME")
    out = []
    for m in months:
        if m.strftime("%Y-%m") < "2019-01":
            continue
        prior = s[s <= m]
        if not len(prior):
            raise SystemExit(f"abort: no session on or before {m.date()}")
        out.append((m.strftime("%Y-%m"), m.strftime("%Y-%m-%d"),
                    prior.iloc[-1].strftime("%Y-%m-%d")))
    return out


def _get(url: str) -> bytes | None:
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as resp:
                body = resp.read()
            if body.strip():
                return body
        except Exception:
            pass
        time.sleep(BACKOFF * (attempt + 1))
    return None


def to_roc(ymd: str) -> str:
    y, m, d = ymd.split("-")
    return f"{int(y) - 1911}%2F{m}%2F{d}"


def parse_twse(body: bytes) -> dict:
    d = json.loads(body.decode("utf-8"))
    fields = d.get("fields") or []
    rows = d.get("data") or []
    idx_id = fields.index("證券代號") if "證券代號" in fields else 0
    idx_pbr = fields.index("股價淨值比") if "股價淨值比" in fields else None
    ids, with_pbr = set(), set()
    for r in rows:
        sid = str(r[idx_id]).strip()
        ids.add(sid)
        if idx_pbr is not None:
            v = str(r[idx_pbr]).strip()
            if v not in ("", "-", "NA", "N/A", "0.00"):
                with_pbr.add(sid)
    return {"stat": d.get("stat"), "rows": len(rows), "ids": ids, "with_pbr": with_pbr,
            "fields": fields, "reported_date": d.get("date")}


def parse_tpex(body: bytes) -> dict:
    d = json.loads(body.decode("utf-8"))
    t = (d.get("tables") or [{}])[0]
    fields = t.get("fields") or []
    rows = t.get("data") or []
    idx_id = fields.index("股票代號") if "股票代號" in fields else 0
    idx_pbr = fields.index("股價淨值比") if "股價淨值比" in fields else None
    ids, with_pbr = set(), set()
    for r in rows:
        sid = str(r[idx_id]).strip()
        ids.add(sid)
        if idx_pbr is not None:
            v = str(r[idx_pbr]).strip()
            if v not in ("", "-", "NA", "N/A", "0.00"):
                with_pbr.add(sid)
    return {"stat": "OK" if rows else "EMPTY", "rows": len(rows), "ids": ids,
            "with_pbr": with_pbr, "fields": fields,
            "reported_date": t.get("date"), "total_count": t.get("totalCount")}


def main() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    months = sessions_for_decision_months()
    print(f"decision months to audit: {len(months)} "
          f"({months[0][0]} .. {months[-1][0]})", flush=True)

    results = []
    for i, (ym, ddate, sess) in enumerate(months, 1):
        rec = {"decision_month": ym, "decision_date": ddate, "as_of_session": sess}

        raw_t = os.path.join(RAW_DIR, f"twse_{sess}.json")
        if ONLY not in ("both", "twse"):
            body = open(raw_t, "rb").read() if os.path.exists(raw_t) else None
        elif os.path.exists(raw_t):
            body = open(raw_t, "rb").read()
        else:
            body = _get(TWSE.format(ymd=sess.replace("-", "")))
            if body:
                open(raw_t, "wb").write(body)
            time.sleep(PAUSE)
        if body:
            try:
                p = parse_twse(body)
                rec.update(twse_stat=p["stat"], twse_rows=p["rows"],
                           twse_with_pbr=len(p["with_pbr"]),
                           twse_reported_date=p["reported_date"],
                           twse_sha256=hashlib.sha256(body).hexdigest())
                json.dump(sorted(p["with_pbr"]),
                          open(os.path.join(RAW_DIR, f"twse_ids_{sess}.json"), "w"))
            except Exception as e:
                rec.update(twse_stat=f"PARSE_FAIL:{e}", twse_rows=0, twse_with_pbr=0)
        else:
            rec.update(twse_stat="NO_RESPONSE", twse_rows=0, twse_with_pbr=0)

        raw_p = os.path.join(RAW_DIR, f"tpex_{sess}.json")
        if ONLY not in ("both", "tpex"):
            body = open(raw_p, "rb").read() if os.path.exists(raw_p) else None
        elif os.path.exists(raw_p):
            body = open(raw_p, "rb").read()
        else:
            body = _get(TPEX.format(roc=to_roc(sess)))
            if body:
                open(raw_p, "wb").write(body)
            time.sleep(PAUSE)
        if body:
            try:
                p = parse_tpex(body)
                rec.update(tpex_stat=p["stat"], tpex_rows=p["rows"],
                           tpex_with_pbr=len(p["with_pbr"]),
                           tpex_reported_date=p["reported_date"],
                           tpex_sha256=hashlib.sha256(body).hexdigest())
                json.dump(sorted(p["with_pbr"]),
                          open(os.path.join(RAW_DIR, f"tpex_ids_{sess}.json"), "w"))
            except Exception as e:
                rec.update(tpex_stat=f"PARSE_FAIL:{e}", tpex_rows=0, tpex_with_pbr=0)
        else:
            rec.update(tpex_stat="NO_RESPONSE", tpex_rows=0, tpex_with_pbr=0)

        results.append(rec)
        print(f"  [{i:3d}/{len(months)}] {ym} sess={sess} "
              f"TWSE {rec.get('twse_stat')}/{rec.get('twse_with_pbr')} "
              f"TPEx {rec.get('tpex_stat')}/{rec.get('tpex_with_pbr')}", flush=True)

    out = os.path.join(HERE, "official_pbr_coverage_raw.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"sources": {"twse": TWSE, "tpex": TPEX},
                   "raw_payload_dir": os.path.relpath(RAW_DIR, REPO),
                   "months": results, "performance_computed": False}, fh,
                  ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print("wrote", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
