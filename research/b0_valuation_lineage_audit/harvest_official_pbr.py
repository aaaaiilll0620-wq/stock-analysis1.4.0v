# -*- coding: utf-8 -*-
"""Official exchange PBR harvest — full enumeration, READ-ONLY.

Supersedes the probe in `fetch_official_pbr.py` for three reasons the probe
cannot satisfy:

  1. **A transport failure must never look like history.** The probe returned
     `None` both when the host refused the connection and when the host answered
     "no data for this date". Those are opposite facts. Here every session ends
     in exactly one of three terminal states — `OK`, `NO_DATA` (the host
     answered, and the answer was that it has nothing), or `TRANSPORT_FAIL` (we
     never got an answer) — and only the first two are ever cached.
  2. **Values, not just identifiers.** Coverage counting needs the id set; the
     pre-2019 lineage reconciliation needs the number, the closing price and,
     where the source discloses it, the statement vintage. All three are kept.
  3. **NA has to be split by kind.** A security the exchange publishes with `-`
     is a different fact from a security the exchange does not list at all. The
     first is the NA class the frozen lineage already carries; the second is a
     board-membership statement.

Idempotent and resumable: a session whose payload is already normalised on disk
is never re-requested, and a failed request writes nothing, so re-running the
script converges. Nothing here decides anything — `value_pbr_lineage_2019plus`
stays OPEN.

    python research/b0_valuation_lineage_audit/harvest_official_pbr.py

Env:
    B0_AUDIT_SOURCE    twse | tpex | both        (default both)
    B0_AUDIT_SESSIONS  window | overlap | all    (default window = the 87 months)
    B0_AUDIT_PAUSE     seconds between requests to one host (default 3)
    B0_AUDIT_RETRIES   attempts per session      (default 4)
    B0_AUDIT_BACKOFF   linear backoff base       (default 15)
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
RAW_DIR = ART
NORM_DIR = os.path.join(ART, "norm")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TWSE = ("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
        "?date={ymd}&selectType=ALL&response=json")
TPEX = ("https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"
        "?date={roc}&response=json")

PAUSE = float(os.environ.get("B0_AUDIT_PAUSE", "3"))
RETRIES = int(os.environ.get("B0_AUDIT_RETRIES", "4"))
BACKOFF = float(os.environ.get("B0_AUDIT_BACKOFF", "15"))
TIMEOUT = float(os.environ.get("B0_AUDIT_TIMEOUT", "45"))
# Sliding-window rate limit, measured rather than guessed. TWSE serves a short
# burst in ~0.1s each and then refuses TCP outright for about 70 seconds, so a
# fixed inter-request pause either wastes the burst or trips the block; a window
# limiter spends the allowance and then waits exactly as long as it must.
# 0 disables it (TPEx never refused a request at a 4s pause).
BURST = int(os.environ.get("B0_AUDIT_BURST", "0"))
WINDOW = float(os.environ.get("B0_AUDIT_WINDOW", "70"))
ONLY = os.environ.get("B0_AUDIT_SOURCE", "both").lower()
WHICH = os.environ.get("B0_AUDIT_SESSIONS", "window").lower()

# The frozen window's 2019+ decision months. Overlap sessions are pre-2019
# month-ends, where the admissible yearly export still carries 股價淨值比-TSE.
WINDOW_FROM, WINDOW_TO = "2019-01", "2026-03"
OVERLAP_FROM, OVERLAP_TO = "2016-01", "2018-12"


def _sessions() -> list[str]:
    with open(CALENDAR, encoding="utf-8") as fh:
        return sorted(r["session"] for r in csv.DictReader(fh))


def decision_sessions(first_ym: str, last_ym: str) -> list[tuple[str, str, str]]:
    """(decision_month, decision_date, as_of_session), calendar-resolved."""
    import pandas as pd

    sess = pd.Series(pd.to_datetime(_sessions()))
    # `last_ym` is inclusive: range on its month END, or pandas stops one month
    # short and the window silently loses its final decision month.
    months = pd.date_range(pd.Period(first_ym, freq="M").start_time,
                           pd.Period(last_ym, freq="M").end_time.normalize(),
                           freq="ME")
    out = []
    for m in months:
        prior = sess[sess <= m]
        if not len(prior):
            raise SystemExit(f"abort: no session on or before {m.date()}")
        out.append((m.strftime("%Y-%m"), m.strftime("%Y-%m-%d"),
                    prior.iloc[-1].strftime("%Y-%m-%d")))
    return out


def to_roc(ymd: str) -> str:
    y, m, d = ymd.split("-")
    return f"{int(y) - 1911}%2F{m}%2F{d}"


# --- transport ---------------------------------------------------------------

class Transport:
    """Returns (body, state, detail). state in {HTTP_OK, TRANSPORT_FAIL}."""

    def __init__(self) -> None:
        self._stamps: list[float] = []

    def _throttle(self) -> None:
        if BURST <= 0:
            return
        now = time.monotonic()
        self._stamps = [t for t in self._stamps if now - t < WINDOW]
        if len(self._stamps) >= BURST:
            time.sleep(max(0.0, WINDOW - (now - self._stamps[0]) + 1.0))
            now = time.monotonic()
            self._stamps = [t for t in self._stamps if now - t < WINDOW]
        self._stamps.append(time.monotonic())

    def get(self, url: str) -> tuple[bytes | None, str, str]:
        last = ""
        for attempt in range(RETRIES):
            self._throttle()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    code = resp.getcode()
                    body = resp.read()
                if code == 200 and body.strip():
                    return body, "HTTP_OK", ""
                last = "http %s len %d" % (code, len(body))
            except urllib.error.HTTPError as e:
                last = "http %s" % e.code
            except Exception as e:                       # URLError, timeout, TCP
                last = "%s: %s" % (type(e).__name__, e)
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
        return None, "TRANSPORT_FAIL", last


# --- parsing -----------------------------------------------------------------

NA_TOKENS = {"", "-", "--", "NA", "N/A", "null", "None"}


def _num(v) -> float | None:
    s = str(v).replace(",", "").strip()
    if s in NA_TOKENS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_twse(body: bytes) -> dict:
    d = json.loads(body.decode("utf-8"))
    stat = str(d.get("stat") or "")
    fields = d.get("fields") or []
    rows = d.get("data") or []
    if not rows:
        return {"state": "NO_DATA", "stat": stat, "rows": 0, "values": {},
                "raw": {}, "close": {}, "vintage": {}, "fields": fields,
                "reported_date": d.get("date")}

    def idx(name, default=None):
        return fields.index(name) if name in fields else default

    i_id = idx("證券代號", 0)
    i_pbr = idx("股價淨值比")
    i_close = idx("收盤價")
    i_vint = idx("財報年/季")
    values, raw, close, vintage = {}, {}, {}, {}
    for r in rows:
        sid = str(r[i_id]).strip()
        if i_pbr is not None:
            raw[sid] = str(r[i_pbr]).strip()
            v = _num(r[i_pbr])
            if v is not None:
                values[sid] = v
        if i_close is not None:
            c = _num(r[i_close])
            if c is not None:
                close[sid] = c
        if i_vint is not None:
            vintage[sid] = str(r[i_vint]).strip()
    return {"state": "OK", "stat": stat, "rows": len(rows), "values": values,
            "raw": raw, "close": close, "vintage": vintage, "fields": fields,
            "reported_date": d.get("date")}


def parse_tpex(body: bytes) -> dict:
    d = json.loads(body.decode("utf-8"))
    tables = d.get("tables") or [{}]
    t = tables[0]
    fields = t.get("fields") or []
    rows = t.get("data") or []
    if not rows:
        return {"state": "NO_DATA", "stat": str(d.get("stat") or ""), "rows": 0,
                "values": {}, "raw": {}, "close": {}, "vintage": {},
                "fields": fields, "reported_date": t.get("date") or d.get("date")}

    def idx(*names):
        for n in names:
            if n in fields:
                return fields.index(n)
        return None

    i_id = idx("股票代號", "代號", "證券代號")
    i_id = 0 if i_id is None else i_id
    i_pbr = idx("股價淨值比")
    i_close = idx("收盤價", "收盤")
    i_vint = idx("財報年/季", "財報年度/季別")
    values, raw, close, vintage = {}, {}, {}, {}
    for r in rows:
        sid = str(r[i_id]).strip()
        if i_pbr is not None:
            raw[sid] = str(r[i_pbr]).strip()
            v = _num(r[i_pbr])
            if v is not None:
                values[sid] = v
        if i_close is not None:
            c = _num(r[i_close])
            if c is not None:
                close[sid] = c
        if i_vint is not None:
            vintage[sid] = str(r[i_vint]).strip()
    return {"state": "OK", "stat": str(d.get("stat") or ""), "rows": len(rows),
            "values": values, "raw": raw, "close": close, "vintage": vintage,
            "fields": fields, "reported_date": t.get("date") or d.get("date")}


PARSERS = {"twse": parse_twse, "tpex": parse_tpex}


def url_for(src: str, sess: str) -> str:
    return (TWSE.format(ymd=sess.replace("-", "")) if src == "twse"
            else TPEX.format(roc=to_roc(sess)))


def harvest_one(src: str, sess: str, transport: Transport) -> dict:
    """One (source, session). Cached payloads are never re-requested."""
    raw_path = os.path.join(RAW_DIR, "%s_%s.json" % (src, sess))
    norm_path = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
    if os.path.exists(norm_path):
        rec = json.load(open(norm_path, encoding="utf-8"))
        rec["from_cache"] = True
        rec["fetched"] = False
        return rec

    fetched = False
    if os.path.exists(raw_path):
        body = open(raw_path, "rb").read()
        detail = ""
    else:
        body, _state, detail = transport.get(url_for(src, sess))
        fetched = True
        if body is not None:
            with open(raw_path, "wb") as fh:
                fh.write(body)

    if body is None:
        return {"source": src, "session": sess, "state": "TRANSPORT_FAIL",
                "detail": detail, "rows": 0, "n_values": 0,
                "from_cache": False, "fetched": fetched}

    try:
        p = PARSERS[src](body)
    except Exception as e:
        return {"source": src, "session": sess, "state": "PARSE_FAIL:%s" % e,
                "rows": 0, "n_values": 0, "from_cache": False, "fetched": fetched}

    rec = {
        "source": src, "session": sess, "state": p["state"], "stat": p["stat"],
        "rows": p["rows"], "reported_date": p["reported_date"],
        "fields": p["fields"],
        "sha256": hashlib.sha256(body).hexdigest(),
        "n_values": len(p["values"]),
        "n_explicit_na": sum(1 for v in p["raw"].values() if v in NA_TOKENS),
        "has_vintage_field": bool(p["vintage"]),
        "values": p["values"], "raw": p["raw"], "close": p["close"],
        "vintage": p["vintage"],
    }
    # Only a real answer is memoised. A transport failure leaves no trace, which
    # is what makes a re-run converge instead of freezing a refusal as history.
    os.makedirs(NORM_DIR, exist_ok=True)
    with open(norm_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    rec["fetched"] = fetched
    rec["from_cache"] = False
    return rec


def main() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(NORM_DIR, exist_ok=True)

    months: list[tuple[str, str, str]] = []
    if WHICH in ("window", "all"):
        months += decision_sessions(WINDOW_FROM, WINDOW_TO)
    if WHICH in ("overlap", "all"):
        months += decision_sessions(OVERLAP_FROM, OVERLAP_TO)
    months.sort()

    srcs = ["twse", "tpex"] if ONLY == "both" else [ONLY]
    transport = Transport()
    print("sessions=%d sources=%s pause=%ss" % (len(months), srcs, PAUSE),
          flush=True)

    ledger = []
    for i, (ym, ddate, sess) in enumerate(months, 1):
        line = {"decision_month": ym, "decision_date": ddate, "as_of_session": sess}
        for src in srcs:
            rec = harvest_one(src, sess, transport)
            line["%s_state" % src] = rec["state"]
            line["%s_rows" % src] = rec.get("rows", 0)
            line["%s_values" % src] = rec.get("n_values", 0)
            if rec.get("detail"):
                line["%s_detail" % src] = rec["detail"]
            if rec.get("fetched"):
                time.sleep(PAUSE)
        ledger.append(line)
        print("  [%3d/%d] %s %s %s" % (
            i, len(months), ym, sess,
            " ".join("%s=%s/%s" % (s.upper(), line["%s_state" % s],
                                   line["%s_values" % s]) for s in srcs)),
            flush=True)

    out = os.path.join(HERE, "harvest_ledger_%s_%s.json" % (WHICH, ONLY))
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"sessions": ledger, "sources": srcs,
                   "performance_computed": False}, fh,
                  ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    fails = [l for l in ledger
             if any(l.get("%s_state" % s) == "TRANSPORT_FAIL" for s in srcs)]
    print("unresolved transport failures: %d" % len(fails))
    print("wrote", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
