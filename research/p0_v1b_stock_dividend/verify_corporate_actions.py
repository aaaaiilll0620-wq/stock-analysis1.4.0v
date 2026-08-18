"""Corporate-action data-semantics probe (READ-ONLY, non-performance only).

W-3 rules every share-changing event into the B0 ledger. Before that can be
implemented, each event type has to be asked a different question than "how many
rows are there": *does the corpus carry enough semantics to reconstruct what
happens to OUR shares?*

For each event type this reports, in-window:
  - which accompanying ratio / effective-date / cash-date fields exist and are
    populated,
  - whether the row is on the side of the transaction that changes our holding,
  - the resulting three-state classification per event.

No return, IC, Sharpe, ranking or selection quantity is computed anywhere here.
"""

import glob
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "tej_exports", "DataExport0806", "配股相關2004-20260817")
OUT = os.path.join(HERE, "corporate_action_semantics.json")

WIN_START, WIN_END = "2014-07-31", "2026-03-31"
_D8 = re.compile(r"^\d{8}$")


def norm_date(v):
    s = str(v).strip()
    if not s or s == ".":
        return None
    if _D8.match(s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    s = s.replace("/", "-")
    p = s.split("-")
    if len(p) == 3 and all(x.isdigit() for x in p):
        return "%04d-%02d-%02d" % (int(p[0]), int(p[1]), int(p[2]))
    return None


def num(v):
    s = str(v).strip()
    if not s or s == ".":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_rows():
    rows = []
    hdr = None
    for z in sorted(glob.glob(os.path.join(SRC, "*.zip"))):
        zf = zipfile.ZipFile(z)
        for name in zf.namelist():
            txt = zf.read(name).decode("utf-16")
            lines = txt.split("\n")
            hdr = lines[0].rstrip("\r").split("\t")
            for line in lines[1:]:
                if not line.strip():
                    continue
                f = line.rstrip("\r").split("\t")
                if len(f) < len(hdr):
                    continue
                rows.append(dict(zip(hdr, f)))
    return rows, hdr


# Each entry: quantity column -> fields the ledger would need to apply it.
EVENT_SEMANTICS = {
    "stock_dividend": {
        "qty": ["盈餘增資(仟股)", "公積增資(仟股)"],
        "ratio": ["盈餘配股率 %", "公積配股率 %"],
        "effective": ["年月日"],
        "tradable": ["股票股利上市日", "股票股利發放日"],
        "cash": [],
    },
    "capital_reduction": {
        "qty": ["減資(仟股)"],
        "ratio": ["減資率 %"],
        "effective": ["除權減資基準日", "年月日"],
        "tradable": [],
        "cash": ["減資每股退還現金", "減資現金退款日"],
    },
    "merger": {
        "qty": ["合併(仟股)"],
        "ratio": [],
        "effective": ["年月日"],
        "tradable": [],
        "cash": [],
    },
    "share_conversion": {
        "qty": ["股份轉換(仟股"],
        "ratio": [],
        "effective": ["年月日"],
        "tradable": [],
        "cash": [],
    },
    "par_value_change": {
        "qty": ["變更股票面額股數(仟股)"],
        "ratio": ["面額"],
        "effective": ["年月日"],
        "tradable": [],
        "cash": [],
    },
    "cash_capital_increase": {
        "qty": ["現金增資(仟股)"],
        "ratio": ["現金認購率 %"],
        "effective": ["年月日"],
        "tradable": ["現增股票上市日", "現增股票發放日"],
        "cash": ["現金認購價（元）", "原股東繳款-迄"],
    },
}

# Events that only change the ISSUER's total share count, never ours.
DILUTION_ONLY = ["証券轉換_可轉債(仟股)", "庫藷股註銷(仟股)", "庫藏股註銷(仟股)",
                 "員工分紅(仟股)", "受讓(仟股)", "其它(仟股)"]


def in_window(r):
    d = norm_date(r.get("年月日"))
    return bool(d and WIN_START <= d <= WIN_END)


def main():
    rows, hdr = load_rows()
    print(f"loaded {len(rows):,} rows, {len(hdr)} columns")

    report = {}
    for ev, spec in EVENT_SEMANTICS.items():
        sel = [r for r in rows
               if any((num(r.get(c)) or 0.0) != 0.0 for c in spec["qty"]) and in_window(r)]
        n = len(sel)
        field_cov = {}
        for group in ("ratio", "effective", "tradable", "cash"):
            for c in spec[group]:
                present = sum(
                    1 for r in sel
                    if (norm_date(r.get(c)) is not None if ("日" in c and c != "年月日")
                        else (num(r.get(c)) is not None if "日" not in c
                              else norm_date(r.get(c)) is not None))
                )
                field_cov[c] = {"group": group, "present": present,
                                "pct": round(100.0 * present / n, 2) if n else None}

        # Does the row's own total share count move the way the event implies?
        # For a merger/share-conversion recorded on the ACQUIRER, total shares
        # rise and our holding is only diluted — a different event from ours.
        direction = Counter()
        for r in sel:
            tot = num(r.get("總股數(仟股)"))
            q = sum(num(r.get(c)) or 0.0 for c in spec["qty"])
            if tot is None:
                direction["no_total"] += 1
            elif q > 0:
                direction["issues_new_shares"] += 1
            else:
                direction["reduces_shares"] += 1

        by_year = Counter()
        for r in sel:
            d = norm_date(r.get("年月日"))
            if d:
                by_year[d[:4]] += 1

        report[ev] = {
            "events_in_window": n,
            "securities_in_window": len({str(r["證券代碼"]).split()[0] for r in sel}),
            "field_coverage": field_cov,
            "quantity_direction": dict(direction),
            "by_year": dict(sorted(by_year.items())),
        }
        print(f"\n{ev}: {n} events / {report[ev]['securities_in_window']} securities")
        for c, v in field_cov.items():
            print(f"    {v['group']:<10} {c:<24} {v['present']:>6} ({v['pct']}%)")

    # --- stock dividend: exact ordering split under the W-2 ruling -----------
    sd = [r for r in rows
          if str(r.get("配股(Y/N)", "")).strip() == "Y"
          and (num(r.get("盈餘增資(仟股)")) or 0.0) + (num(r.get("公積增資(仟股)")) or 0.0) > 0
          and in_window(r)]
    order = Counter()
    missing_years = Counter()
    for r in sd:
        ex = norm_date(r.get("年月日"))
        li = norm_date(r.get("股票股利上市日"))
        pa = norm_date(r.get("股票股利發放日"))
        tr = max([d for d in (li, pa) if d], default=None)
        if tr is None:
            order["missing_tradable"] += 1
            if ex:
                missing_years[ex[:4]] += 1
        elif tr > ex:
            order["after_ex"] += 1
        elif tr == ex:
            order["same_day"] += 1
        else:
            order["before_ex"] += 1
    report["stock_dividend_ordering"] = {"counts": dict(order),
                                         "missing_by_year": dict(sorted(missing_years.items()))}
    print("\nstock-dividend credit-date ordering in window:", dict(order))
    print("  missing by year:", dict(sorted(missing_years.items())))

    # --- capital reduction: does cash-back imply a cash date? ----------------
    cr = [r for r in rows if (num(r.get("減資(仟股)")) or 0.0) != 0.0 and in_window(r)]
    cash_back = [r for r in cr if (num(r.get("減資每股退還現金")) or 0.0) > 0]
    cash_no_date = [r for r in cash_back if norm_date(r.get("減資現金退款日")) is None]
    no_ratio = [r for r in cr if num(r.get("減資率 %")) is None]
    no_eff = [r for r in cr if norm_date(r.get("除權減資基準日")) is None]
    report["capital_reduction_detail"] = {
        "events": len(cr), "with_cash_back": len(cash_back),
        "cash_back_without_refund_date": len(cash_no_date),
        "without_reduction_rate": len(no_ratio),
        "without_effective_date": len(no_eff),
    }
    print("\ncapital reduction:", report["capital_reduction_detail"])

    # --- dilution-only events: confirm they carry no holder-side fields ------
    dil = {}
    for c in DILUTION_ONLY:
        if c not in hdr:
            continue
        sel = [r for r in rows if (num(r.get(c)) or 0.0) != 0.0 and in_window(r)]
        dil[c] = {"events_in_window": len(sel),
                  "securities": len({str(r["證券代碼"]).split()[0] for r in sel})}
    report["dilution_only_events"] = dil
    print("\ndilution-only (issuer total shares change, our shares do not):")
    for c, v in dil.items():
        if v["events_in_window"]:
            print(f"    {c:<26} {v['events_in_window']:>6} events / {v['securities']} securities")

    payload = {"study": "W-3 corporate-action data semantics",
               "read_only": True, "performance_computed": False,
               "source": os.path.relpath(SRC, REPO).replace("\\", "/"),
               "window": {"start": WIN_START, "end": WIN_END},
               "report": report}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
