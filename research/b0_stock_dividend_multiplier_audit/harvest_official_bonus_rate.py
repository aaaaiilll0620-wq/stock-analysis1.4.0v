# -*- coding: utf-8 -*-
"""Official exchange bonus-share-ratio harvest — READ-ONLY audit transport.

Three terminal states per request, and only two of them are ever cached:

    OK             the host answered and the answer carries a payload
    NO_DATA        the host answered, and the answer is that it has nothing
    TRANSPORT_FAIL we never got an answer

A transport failure cached as absence is how "the exchange has no history" gets
manufactured, so a failed request writes nothing and re-running converges.

Three layers, because the two exchanges disclose the ratio at different depths:

  twse_range   TWT49U over a date range. One row per ex-right/ex-dividend event
               with the rights/dividend classifier and the detail key. No ratio.
  twse_detail  TWT49UDetail?STK_NO=&T1=. Carries field A, the holder-level
               bonus allotment per 1,000 shares held. One request per event.
  tpex_range   exDailyQ?startDate=&endDate= in ROC dates. Carries the per-1,000
               bonus allotment in the RANGE table itself, so OTC needs no
               second layer.

Nothing here decides anything. `stock_dividend_holder_multiplier_source` stays
OPEN.

    python research/b0_stock_dividend_multiplier_audit/harvest_official_bonus_rate.py

Env:
    B0_SDM_LAYER    twse_range | tpex_range | twse_detail | all   (default all)
    B0_SDM_BURST    requests per window per host    (default 8, 0 disables)
    B0_SDM_WINDOW   window seconds                  (default 70)
    B0_SDM_PAUSE    minimum seconds between requests to one host (default 3)
    B0_SDM_RETRIES  attempts per request            (default 4)
"""
from __future__ import annotations

import datetime
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

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or os.path.join(REPO, "artifacts"),
                   "stock_dividend_multiplier_audit")
RAW = os.path.join(ART, "raw")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TWSE_RANGE = ("https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
              "?startDate=%s&endDate=%s&response=json")
TWSE_DETAIL = ("https://www.twse.com.tw/rwd/zh/exRight/TWT49UDetail"
               "?STK_NO=%s&T1=%s&response=json")
TPEX_RANGE = ("https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ"
              "?startDate=%s&endDate=%s&response=json")
REFERER = {"twse": "https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html",
           "tpex": "https://www.tpex.org.tw/zh-tw/bulletin/exDaily.html"}

BURST = int(os.environ.get("B0_SDM_BURST", "8"))
WINDOW = float(os.environ.get("B0_SDM_WINDOW", "70"))
PAUSE = float(os.environ.get("B0_SDM_PAUSE", "3"))
RETRIES = int(os.environ.get("B0_SDM_RETRIES", "4"))
TIMEOUT = float(os.environ.get("B0_SDM_TIMEOUT", "45"))
LAYER = os.environ.get("B0_SDM_LAYER", "all").lower()

# The window every 141-period momentum_12_1 / sigma20d lookback can reach.
# P_{t-13} for the first decision month 2014-07 is the 2013-06 month-end session
# (2013-06-28), and an event ON or BEFORE that session divides both momentum
# anchors alike, so it cannot change the ratio. Hence the open lower bound.
WINDOW_FROM = "2013-06-29"
WINDOW_TO = "2026-03-31"


class TransportFail(RuntimeError):
    """We never got an answer. Never cached, never counted as absence."""


class Transport:
    """One sliding-window limiter per host.

    TWSE serves a short burst and then refuses outright for about a minute; a
    fixed pause either wastes the burst or trips the block, so the allowance is
    spent and then waited out exactly.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._last: dict[str, float] = {}

    def _throttle(self, host: str) -> None:
        gap = time.time() - self._last.get(host, 0.0)
        if gap < PAUSE:
            time.sleep(PAUSE - gap)
        if BURST:
            hits = [t for t in self._hits.get(host, []) if time.time() - t < WINDOW]
            if len(hits) >= BURST:
                time.sleep(max(0.0, WINDOW - (time.time() - hits[0])) + 1.0)
                hits = [t for t in hits if time.time() - t < WINDOW]
            self._hits[host] = hits
        self._hits.setdefault(host, []).append(time.time())
        self._last[host] = time.time()

    def get(self, host: str, url: str) -> bytes:
        last = None
        for attempt in range(RETRIES):
            self._throttle(host)
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA, "Referer": REFERER[host],
                                  "Accept": "application/json, text/plain, */*"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
                    return fh.read()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(15.0 * (attempt + 1))
        raise TransportFail("%s: %s: %s" % (url, type(last).__name__, last))


def cache_path(key: str) -> str:
    return os.path.join(RAW, key + ".json")


def fetch(tr: Transport, host: str, url: str, key: str) -> dict:
    """Return the cached-or-fetched payload. Only OK/NO_DATA reach the disk."""
    path = cache_path(key)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    body = tr.get(host, url)                       # raises TransportFail
    text = body.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        # A non-JSON body from a host that answered is not "no data"; it is an
        # answer we cannot read, and guessing which it meant is the whole bug
        # this harvest exists to avoid.
        raise TransportFail("%s: non-JSON body (%d bytes)" % (url, len(body)))
    rec = {"key": key, "url": url, "sha256": hashlib.sha256(body).hexdigest(),
           "bytes": len(body), "payload": payload}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, ensure_ascii=False)
    return rec


def quarters(first: str, last: str):
    y, q = int(first[:4]), (int(first[5:7]) - 1) // 3
    while True:
        s = "%04d-%02d-01" % (y, q * 3 + 1)
        em = q * 3 + 3
        ey, em2 = (y + 1, 1) if em == 12 else (y, em + 1)
        e = (datetime.date(ey, em2, 1) - datetime.timedelta(days=1)).isoformat()
        if s > last:
            return
        yield max(s, first), min(e, last)
        q += 1
        if q == 4:
            q, y = 0, y + 1


def roc(iso: str) -> str:
    return "%d/%s/%s" % (int(iso[:4]) - 1911, iso[5:7], iso[8:10])


def main() -> int:
    os.makedirs(RAW, exist_ok=True)
    tr = Transport()
    qs = list(quarters(WINDOW_FROM, WINDOW_TO))
    fails: list[str] = []

    if LAYER in ("all", "twse_range"):
        for s, e in qs:
            key = "twse_range_%s_%s" % (s.replace("-", ""), e.replace("-", ""))
            try:
                url = TWSE_RANGE % (s.replace("-", ""), e.replace("-", ""))
                rec = fetch(tr, "twse", url, key)
                n = len(rec["payload"].get("data") or [])
                print("twse_range %s..%s  rows=%d" % (s, e, n), flush=True)
            except TransportFail as exc:
                fails.append(str(exc))
                print("twse_range %s..%s  TRANSPORT_FAIL" % (s, e), flush=True)

    if LAYER in ("all", "tpex_range"):
        for s, e in qs:
            key = "tpex_range_%s_%s" % (s.replace("-", ""), e.replace("-", ""))
            try:
                rec = fetch(tr, "tpex", TPEX_RANGE % (roc(s), roc(e)), key)
                tables = rec["payload"].get("tables") or [{}]
                n = len(tables[0].get("data") or [])
                print("tpex_range %s..%s  rows=%d" % (s, e, n), flush=True)
            except TransportFail as exc:
                fails.append(str(exc))
                print("tpex_range %s..%s  TRANSPORT_FAIL" % (s, e), flush=True)

    if LAYER in ("all", "twse_detail"):
        todo = json.load(open(os.path.join(ART, "twse_detail_todo.json"), encoding="utf-8"))
        # B0_SDM_SLICE=i/n runs every n-th entry. The detail endpoint answers in
        # ~6s, so a single worker spends most of an hour waiting on latency
        # rather than on the rate limit; disjoint slices let a few workers share
        # the wait without any of them raising the request rate per host beyond
        # what one worker already survived. Slices are disjoint by construction
        # and the cache check makes an overlap idempotent anyway.
        slice_spec = os.environ.get("B0_SDM_SLICE", "")
        if slice_spec:
            i, n = (int(x) for x in slice_spec.split("/"))
            todo = [t for k, t in enumerate(todo) if k % n == i]
            print("slice %s: %d of the work list" % (slice_spec, len(todo)), flush=True)
        ok = 0
        for i, (stk, ymd) in enumerate(todo, 1):
            key = "twse_detail_%s_%s" % (stk, ymd)
            try:
                fetch(tr, "twse", TWSE_DETAIL % (stk, ymd), key)
                ok += 1
            except TransportFail as exc:
                fails.append(str(exc))
            if i % 50 == 0:
                print("twse_detail %d/%d  ok=%d fails=%d"
                      % (i, len(todo), ok, len(fails)), flush=True)

    print("")
    print("unresolved transport failures:", len(fails))
    for f in fails[:20]:
        print("  ", f)
    with open(os.path.join(ART, "transport_failures_%s.json" % LAYER), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(fails, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
