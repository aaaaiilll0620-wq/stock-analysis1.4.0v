# -*- coding: utf-8 -*-
"""Unit semantics + coverage of the official bonus-share ratio. READ-ONLY.

Two questions, kept apart on purpose:

  UNITS   Is the published number a decimal ratio, a percentage, or shares per
          1,000 shares held? Settled by reproducing the exchange's OWN published
          ex-reference price from its OWN published components. This does not
          DERIVE the multiplier from a price — the multiplier is published; the
          price is only the exchange's arithmetic identity, and only one reading
          of the units satisfies it.

  COVER   Of the canonical stock_dividend events the 141-period lookback can
          reach, how many carry an official holder-level ratio, and what exactly
          is left over?

Nothing here decides anything. `stock_dividend_holder_multiplier_source` stays
OPEN.

    python research/b0_stock_dividend_multiplier_audit/analyse_official_bonus_rate.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or os.path.join(REPO, "artifacts"),
                   "stock_dividend_multiplier_audit")
RAW = os.path.join(ART, "raw")

# Resolved by NAME with a fail-loud guard, never by position: a column that
# silently moves is how a present field gets read as a different one. TWSE writes
# the per-thousand unit as 千 in this report and 仟 in the TPEx one, so the two
# name sets are kept separate rather than normalised into one guess.
TWSE_A = "A. 按普通股股東持股比例每千股無償配股"
TWSE_CASH = "(每股配發現金股利)除息"
TWSE_SUBS = "按股東持股比例每千股認購"
TWSE_PRICE = "每股認購金額"


def num(v):
    s = str(v).replace(",", "").strip()
    for tail in ("元／股", "元/股", "股", "元"):
        if s.endswith(tail):
            s = s[: -len(tail)].strip()
    if s in ("", "-", "--", ".", "N/A", "nan", "None"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if f != f else f


def twse_range_rows():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "twse_range_*.json"))):
        with open(path, encoding="utf-8") as fh:
            pay = json.load(fh)["payload"]
        fields = pay.get("fields") or []
        if not fields:
            continue
        ix = {c: i for i, c in enumerate(fields)}
        for r in pay.get("data") or []:
            s = str(r[ix["資料日期"]])
            d = "%04d-%02d-%02d" % (int(s.split("年")[0]) + 1911,
                                    int(s.split("年")[1].split("月")[0]),
                                    int(s.split("月")[1].split("日")[0]))
            out[(str(r[ix["股票代號"]]).strip(), d)] = {
                "prev": num(r[ix["除權息前收盤價"]]),
                "ref": num(r[ix["除權息參考價"]]),
                "flag": str(r[ix["權/息"]]).strip()}
    return out


def twse_details():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "twse_detail_*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        pay = rec["payload"]
        key = rec["key"].split("twse_detail_")[1]
        stk, ymd = key.rsplit("_", 1)
        iso = "%s-%s-%s" % (ymd[:4], ymd[4:6], ymd[6:8])
        fields, data = pay.get("fields") or [], pay.get("data") or []
        if not fields or not data:
            out[(stk, iso)] = {"stat": str(pay.get("stat", "")), "row": None}
            continue
        r = data[0]

        def pick(name):
            hits = [i for i, c in enumerate(fields) if c.strip() == name.strip()]
            if len(hits) != 1:
                raise SystemExit(
                    "detail schema in %s resolves %r to %d columns; the report "
                    "changed and this analysis must not guess which one it meant"
                    % (os.path.basename(path), name, len(hits)))
            return num(r[hits[0]])

        out[(stk, iso)] = {
            "stat": str(pay.get("stat", "")),
            "bonus_per_1000": pick(TWSE_A),
            "cash": pick(TWSE_CASH),
            "subs_per_1000": pick(TWSE_SUBS),
            "subs_price": pick(TWSE_PRICE),
            "sha256": rec["sha256"], "row": r}
    return out


def unit_test(samples, label):
    """samples: (prev, ref, cash, bonus, subs, subs_price). One reading survives."""
    print("\n== %s — which reading of the published number satisfies the" % label)
    print("   exchange's own reference-price identity?")
    print("   %-38s %12s %12s %14s" % ("reading", "max|err|", "median|err|", "within 0.01"))
    for name, scale in [("shares per 1,000 held (m = 1 + b/1000)", 1000.0),
                        ("decimal ratio         (m = 1 + b)", 1.0),
                        ("percent               (m = 1 + b/100)", 100.0)]:
        errs = []
        for prev, ref, cash, bonus, subs, sp in samples:
            num_ = prev - cash + (subs / 1000.0) * sp
            den = 1.0 + bonus / scale + subs / 1000.0
            errs.append(abs(num_ / den - ref))
        ok = sum(1 for e in errs if e <= 0.01)
        print("   %-38s %12.4f %12.6f %10d/%d" %
              (name, max(errs), statistics.median(errs), ok, len(errs)))
    return len(samples)


def main() -> int:
    rng, det = twse_range_rows(), twse_details()
    print("TWSE range keys: %d   TWSE detail payloads on disk: %d" % (len(rng), len(det)))

    answered = {k: v for k, v in det.items() if v.get("row")}
    refused = {k: v for k, v in det.items() if not v.get("row")}
    print("detail answered with a row : %d" % len(answered))
    print("detail answered 'no data'  : %d  %s" %
          (len(refused), sorted({v["stat"] for v in refused.values()})))

    samples = []
    for k, v in answered.items():
        r = rng.get(k)
        if not r or r["prev"] is None or r["ref"] is None:
            continue
        b, c = v["bonus_per_1000"], v["cash"]
        s, sp = v["subs_per_1000"], v["subs_price"]
        if None in (b, c, s, sp) or b <= 0:
            continue
        samples.append((r["prev"], r["ref"], c, b, s, sp))
    unit_test(samples, "TWSE  " + TWSE_A)

    pos = [v["bonus_per_1000"] for v in answered.values()
           if v["bonus_per_1000"] is not None and v["bonus_per_1000"] > 0]
    zero = [v for v in answered.values() if v["bonus_per_1000"] == 0]
    print("\nTWSE matched events with a POSITIVE bonus allotment: %d" % len(pos))
    print("TWSE matched events with a ZERO bonus allotment     : %d" % len(zero))
    if pos:
        p = sorted(pos)
        print("   per-1,000 allotment  min=%.4f p50=%.4f p95=%.4f max=%.4f"
              % (p[0], statistics.median(p), p[int(.95 * len(p)) - 1], p[-1]))
        print("   implied multiplier   min=%.6f p50=%.6f max=%.6f"
              % (1 + p[0] / 1000, 1 + statistics.median(p) / 1000, 1 + p[-1] / 1000))

    with open(os.path.join(ART, "twse_bonus_rate.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["stock_id", "ex_date", "bonus_per_1000", "cash_per_share",
                    "subs_per_1000", "subs_price", "stat", "sha256"])
        for (stk, iso), v in sorted(det.items()):
            w.writerow([stk, iso, v.get("bonus_per_1000"), v.get("cash"),
                        v.get("subs_per_1000"), v.get("subs_price"),
                        v.get("stat"), v.get("sha256", "")])
    print("\nwrote", os.path.relpath(os.path.join(ART, "twse_bonus_rate.csv"), REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
