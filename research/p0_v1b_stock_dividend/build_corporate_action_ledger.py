"""Build the canonical B0 corporate-action ledger from the 配股相關 export.

This is the IMPORTER: all TEJ-specific column names and quirks live here, and it
emits normalised records that `core.b0_corporate_actions.classify` turns into
three-state events. The core module never sees a Chinese column name, and this
module never decides reconstructibility itself.

Rulings implemented:
  W-1  missing credit date -> per-event NOT_RECONSTRUCTIBLE (no interpolation,
       no missing-rate threshold anywhere in this file)
  W-2  credit == ex-right is a legal zero-day receivable
  W-3  every share-changing event type is emitted, each with its own verifier
  W-4  cash capital increases are emitted as NOT_APPLICABLE (never subscribed)

READ-ONLY with respect to Frozen A. No return, IC, Sharpe, ranking or selection
quantity is computed here.
"""

import csv
import glob
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_corporate_actions import (            # noqa: E402
    NOT_APPLICABLE, NOT_RECONSTRUCTIBLE, RECONSTRUCTIBLE,
    assert_every_holder_affecting_kind_has_a_handler, classify,
)

SRC = os.path.join(REPO, "tej_exports", "DataExport0806", "配股相關2004-20260817")
# B0.4: the second admitted lineage. security_status states, authoritatively,
# that a listed security ceased trading and why. It is the ONLY source in the
# corpus that establishes the disappearing side of a reorganization at all.
STATUS_SRC = os.path.join(REPO, "data", "b0", "security_status.csv")
REORGANIZATION_EXIT_REASONS = {
    "合併下市": "MERGER",
    "併入控股公司下市": "HOLDING_COMPANY_CONVERSION",
}
OUT_DIR = os.path.join(REPO, "data", "b0")
OUT_LEDGER = os.path.join(OUT_DIR, "corporate_actions_ledger.csv")
OUT_SD = os.path.join(OUT_DIR, "stock_dividend_pit.csv")
OUT_JSON = os.path.join(HERE, "corporate_action_ledger_summary.json")

WIN_START, WIN_END = "2014-07-31", "2026-03-31"
_D8 = re.compile(r"^\d{8}$")

# TEJ quantity column -> canonical event kind. Kinds that only move the issuer's
# total share count are emitted too, so the ledger states explicitly that they
# were seen and judged NOT_APPLICABLE.
KIND_BY_COLUMN = {
    "減資(仟股)": "capital_reduction",
    # B0.3 R2/R4: keyed on the SOURCE COLUMN, which is the immutable provenance.
    # This export is a per-security share-formation table, so 合併(仟股) on a row
    # is that security's OWN issuance -- issuer-side, never the holder leg.
    "合併(仟股)": "issuer_side_merger_share_issuance",
    "股份轉換(仟股": "issuer_side_share_conversion_issuance",
    "變更股票面額股數(仟股)": "par_value_change",
    "現金增資(仟股)": "cash_capital_increase",
    "証券轉換_可轉債(仟股)": "convertible_bond_conversion",
    "庫藏股註銷(仟股)": "treasury_cancellation",
    "員工分紅(仟股)": "employee_bonus",
    "受讓(仟股)": "transfer_in",
    "其它(仟股)": "other_share_change",
}
# Columns whose non-zero value on the same row would contaminate a share-count
# identity, so a reduction rate must not be derived from counts when present.
SHARE_MOVING_COLUMNS = tuple(KIND_BY_COLUMN) + ("盈餘增資(仟股)", "公積增資(仟股)")


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
    rows, hdr = [], None
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


def sid_of(r):
    return str(r["證券代碼"]).split()[0]


def build_records(rows):
    """Yield (kind, normalised record) for every share-changing row."""
    # previous known par value per security, for par-value-change events
    seq = defaultdict(list)
    for r in rows:
        d = norm_date(r.get("年月日"))
        if d:
            seq[sid_of(r)].append((d, r))
    for k in seq:
        seq[k].sort(key=lambda t: t[0])
    prev_par = {}
    for k, items in seq.items():
        running = None
        for d, r in items:
            prev_par[(k, d)] = running
            p = num(r.get("面額"))
            if p:
                running = p

    for r in rows:
        ex = norm_date(r.get("年月日"))
        sid = sid_of(r)
        tot = num(r.get("總股數(仟股)"))

        # --- stock dividend ---------------------------------------------------
        new_shares = (num(r.get("盈餘增資(仟股)")) or 0.0) + (num(r.get("公積增資(仟股)")) or 0.0)
        if new_shares != 0.0:
            li, pa = norm_date(r.get("股票股利上市日")), norm_date(r.get("股票股利發放日"))
            credit = max([d for d in (li, pa) if d], default=None)
            rate = (num(r.get("盈餘配股率 %")) or 0.0) + (num(r.get("公積配股率 %")) or 0.0)
            yield "stock_dividend", {
                "stock_id": sid, "ex_right_date": ex,
                "new_shares_thousands": new_shares,
                "distribution_ratio_pct": rate or None,
                "credit_tradable_date": credit,
                "is_ex_right_event": str(r.get("配股(Y/N)", "")).strip() == "Y",
            }

        # --- everything else --------------------------------------------------
        for col, kind in KIND_BY_COLUMN.items():
            q = num(r.get(col))
            if not q:
                continue
            rec = {"stock_id": sid, "ex_right_date": ex, "effective_date": ex,
                   "quantity_thousands": q, "total_shares_thousands": tot}
            if kind == "capital_reduction":
                rate = num(r.get("減資率 %"))
                if rate is None and tot:
                    # Arithmetic identity, not a model: reduction / pre-event
                    # shares. Only usable when nothing else moved the count on
                    # the same row, otherwise the identity is contaminated.
                    contaminated = any(
                        (num(r.get(c)) or 0.0) != 0.0
                        for c in SHARE_MOVING_COLUMNS if c != col)
                    if not contaminated:
                        pre = tot + q
                        if pre > 0:
                            rate = q / pre * 100.0
                            rec["reduction_rate_derived"] = True
                rec["reduction_rate_pct"] = rate
                rec["effective_date"] = norm_date(r.get("除權減資基準日")) or ex
                rec["cash_per_share"] = num(r.get("減資每股退還現金"))
                rec["cash_payment_date"] = norm_date(r.get("減資現金退款日"))
            elif kind == "par_value_change":
                rec["new_par"] = num(r.get("面額"))
                rec["old_par"] = prev_par.get((sid, ex))
                rec["changed_shares_thousands"] = q
            yield kind, rec


def main():
    assert_every_holder_affecting_kind_has_a_handler()
    rows, hdr = load_rows()
    print(f"loaded {len(rows):,} rows, {len(hdr)} columns")

    events = [classify(kind, rec) for kind, rec in build_records(rows)]

    # B0.4 · holder-side coverage. Materialized for EVERY status-defined
    # disappearance, with no filter on price-universe membership, window or
    # holdings -- the coverage invariant is about the corpus, not about what B0
    # happened to touch.
    exits = 0
    with open(STATUS_SRC, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["status"] != "delisted":
                continue
            if r["reason"] not in REORGANIZATION_EXIT_REASONS:
                continue
            events.append(classify("holder_side_reorganization_exit", {
                "stock_id": r["stock_id"],
                "effective_date": r["effective_from"],
                "status_reason": r["reason"]}))
            exits += 1
    print(f"holder-side reorganization exits materialized: {exits}")
    in_win = [e for e in events
              if e.ex_or_effective_date and WIN_START <= e.ex_or_effective_date <= WIN_END]
    print(f"classified {len(events):,} events, {len(in_win):,} in window")

    tally = Counter((e.kind, e.reconstructibility) for e in in_win)
    reasons = Counter(e.reason for e in in_win if e.reconstructibility == NOT_RECONSTRUCTIBLE)

    os.makedirs(OUT_DIR, exist_ok=True)
    cols = ["stock_id", "kind", "source_field", "ex_or_effective_date", "reconstructibility", "reason",
            "credit_tradable_date", "new_shares_thousands", "share_multiplier",
            "cash_per_share", "cash_payment_date", "zero_day_receivable"]
    with open(OUT_LEDGER, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # B0.3 R4: the source column travels with the event, so a later audit
        # can be run on PROVENANCE rather than on the canonical kind name --
        # which is precisely the shortcut that produced the conflation.
        from core.b0_corporate_actions import EVENT_KIND_BY_KEY
        for e in sorted(events, key=lambda x: (x.ex_or_effective_date, x.stock_id, x.kind)):
            row = {c: getattr(e, c) for c in cols if c != "source_field"}
            ek = EVENT_KIND_BY_KEY.get(e.kind)
            row["source_field"] = ek.source_column if ek else ""
            w.writerow(row)

    # The V-1b blocking requirement reads the stock-dividend view specifically.
    sd_cols = ["stock_id", "ex_right_date", "distribution_ratio_or_new_shares",
               "actual_credit_tradable_date", "reconstructibility", "reason",
               "zero_day_receivable"]
    with open(OUT_SD, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sd_cols)
        w.writeheader()
        for e in sorted((x for x in events if x.kind == "stock_dividend"),
                        key=lambda x: (x.ex_or_effective_date, x.stock_id)):
            w.writerow({
                "stock_id": e.stock_id,
                "ex_right_date": e.ex_or_effective_date,
                "distribution_ratio_or_new_shares": e.new_shares_thousands,
                "actual_credit_tradable_date": e.credit_tradable_date or "",
                "reconstructibility": e.reconstructibility,
                "reason": e.reason,
                "zero_day_receivable": e.zero_day_receivable,
            })

    print("\nin-window classification:")
    for (kind, state), n in sorted(tally.items()):
        print("   %-28s %-20s %6d" % (kind, state, n))
    print("\nNOT_RECONSTRUCTIBLE reasons (in window):")
    for reason, n in reasons.most_common():
        print("   %5d  %s" % (n, reason[:110]))

    summary = {
        "study": "W-1..W-4 corporate-action ledger",
        "read_only": True, "performance_computed": False,
        "source": os.path.relpath(SRC, REPO).replace("\\", "/"),
        "window": {"start": WIN_START, "end": WIN_END},
        "events_total": len(events), "events_in_window": len(in_win),
        "in_window_by_kind_state": {f"{k}|{s}": n for (k, s), n in sorted(tally.items())},
        "not_reconstructible_reasons": dict(reasons.most_common()),
        "ledger": os.path.relpath(OUT_LEDGER, REPO).replace("\\", "/"),
        "stock_dividend_view": os.path.relpath(OUT_SD, REPO).replace("\\", "/"),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("\nwrote", os.path.relpath(OUT_LEDGER, REPO))
    print("wrote", os.path.relpath(OUT_SD, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
