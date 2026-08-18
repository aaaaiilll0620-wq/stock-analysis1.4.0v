# -*- coding: utf-8 -*-
"""Align the official exchange bonus-share disclosure to the canonical events.

READ-ONLY. Nothing here decides anything; it produces the coverage table the
`stock_dividend_holder_multiplier_source` ruling needs, and the TWSE detail
work list the harvester consumes.

Board attribution is CONTEMPORANEOUS by construction: a security is attributed
to TWSE for an ex-date because the TWSE payload FOR THAT DATE carries it, and to
TPEx for the same reason. No current 上市別 column is read anywhere.

Columns are resolved by NAME, never by position: TPEx served a 22-column schema
through 2015 (it carried 員工紅利轉增資, which C-50/R2 classifies ineligible in
any case) and a 21-column one from 2016, so an index would silently shift.

    python research/b0_stock_dividend_multiplier_audit/align_official_bonus_rate.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or os.path.join(REPO, "artifacts"),
                   "stock_dividend_multiplier_audit")
RAW = os.path.join(ART, "raw")
LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")

WINDOW_FROM = "2013-06-29"      # see harvest_official_bonus_rate.WINDOW_FROM
WINDOW_TO = "2026-03-31"

TWSE_ID, TWSE_DATE, TWSE_FLAG = "股票代號", "資料日期", "權/息"
TWSE_DETAIL_KEY = "詳細資料"
TPEX_ID, TPEX_DATE, TPEX_FLAG = "代號", "除權息日期", "權/息"
TPEX_BONUS = "每仟股無償配股"


def roc_cn_to_iso(s: str) -> str | None:
    """'113年06月03日' -> '2024-06-03'."""
    s = str(s).strip()
    if "年" in s and "月" in s and "日" in s:
        y = int(s.split("年")[0]) + 1911
        m = int(s.split("年")[1].split("月")[0])
        d = int(s.split("月")[1].split("日")[0])
        return "%04d-%02d-%02d" % (y, m, d)
    return None


def roc_slash_to_iso(s: str) -> str | None:
    """'113/06/04' -> '2024-06-04'."""
    p = str(s).strip().split("/")
    if len(p) == 3 and p[0].isdigit():
        return "%04d-%02d-%02d" % (int(p[0]) + 1911, int(p[1]), int(p[2]))
    return None


def num(v) -> float | None:
    s = str(v).replace(",", "").strip()
    for tail in ("股", "元/股", "元／股", "元"):
        if s.endswith(tail):
            s = s[: -len(tail)].strip()
    if s in ("", "-", "--", ".", "nan", "None", "N/A"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if f != f else f


def load_twse() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(glob.glob(os.path.join(RAW, "twse_range_*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        pay = rec["payload"]
        fields = pay.get("fields") or []
        if not fields:
            continue
        ix = {f: i for i, f in enumerate(fields)}
        for row in pay.get("data") or []:
            date = roc_cn_to_iso(row[ix[TWSE_DATE]])
            sid = str(row[ix[TWSE_ID]]).strip()
            if not date:
                continue
            key = (sid, date)
            detail = str(row[ix[TWSE_DETAIL_KEY]]).strip()
            out[key] = {"board": "TWSE", "flag": str(row[ix[TWSE_FLAG]]).strip(),
                        "detail": detail, "src": os.path.basename(path)}
    return out


def load_tpex() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(glob.glob(os.path.join(RAW, "tpex_range_*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        for tb in rec["payload"].get("tables") or []:
            fields = tb.get("fields") or []
            if not fields:
                continue
            ix = {f: i for i, f in enumerate(fields)}
            if TPEX_BONUS not in ix:
                raise SystemExit(
                    "TPEx schema in %s has no %r column; the disclosure changed "
                    "and this alignment must not guess which column replaced it"
                    % (os.path.basename(path), TPEX_BONUS))
            for row in tb.get("data") or []:
                date = roc_slash_to_iso(row[ix[TPEX_DATE]])
                sid = str(row[ix[TPEX_ID]]).strip()
                if not date:
                    continue
                out[(sid, date)] = {
                    "board": "TPEX", "flag": str(row[ix[TPEX_FLAG]]).strip(),
                    "bonus_per_1000": num(row[ix[TPEX_BONUS]]),
                    "src": os.path.basename(path)}
    return out


def load_events() -> list[dict]:
    with open(LEDGER, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows
            if r["kind"] == "stock_dividend"
            and WINDOW_FROM <= r["ex_or_effective_date"] <= WINDOW_TO]


def main() -> int:
    twse, tpex = load_twse(), load_tpex()
    events = load_events()
    print("official rows: TWSE %d keys, TPEx %d keys" % (len(twse), len(tpex)))
    print("canonical stock_dividend events in window: %d" % len(events))

    both = set(twse) & set(tpex)
    if both:
        print("WARNING: %d keys appear on BOTH boards, e.g. %s"
              % (len(both), sorted(both)[:5]))

    todo, rows = [], []
    for ev in events:
        key = (ev["stock_id"], ev["ex_or_effective_date"])
        t, p = twse.get(key), tpex.get(key)
        board = "TWSE" if t else ("TPEX" if p else "ABSENT")
        rows.append({"stock_id": key[0], "ex_date": key[1], "board": board,
                     "flag": (t or p or {}).get("flag", ""),
                     "bonus_per_1000": (p or {}).get("bonus_per_1000"),
                     "reconstructibility": ev["reconstructibility"],
                     "new_shares_thousands": ev["new_shares_thousands"]})
        if t:
            todo.append([key[0], key[1].replace("-", "")])

    with open(os.path.join(ART, "twse_detail_todo.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(todo, fh, ensure_ascii=False)
    with open(os.path.join(ART, "alignment.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    import collections
    c = collections.Counter(r["board"] for r in rows)
    print("board attribution (contemporaneous):", dict(c))
    print("TWSE detail requests queued:", len(todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
