# -*- coding: utf-8 -*-
"""PE-specific lineage reconciliation — READ-ONLY, VALUE LEVEL.

Same window, same securities, same sessions as the PBR reconciliation: the 36
month-ends 2016-2018, official `本益比` against the admissible `本益比-TSE`
lineage. Uses only payloads already on disk; no request is made to either
exchange.

PE is NOT PBR with a different numerator, and this script is built around the
difference rather than around the similarity:

  * **PE has a domain.** A security with non-positive trailing earnings has no
    meaningful ratio, so both sides carry a large legitimate NA class that has no
    analogue in B/M. Roughly a fifth to a quarter of published rows. A
    reconciliation that counted those as disagreement would report a failure that
    is really a definition.
  * **The two sides can be NA for different reasons.** The exchange prints `-`
    (or omits the value); the vendor lineage leaves the cell empty. Being NA in
    both is agreement about the domain; being NA on one side only is the thing
    worth counting, and it is counted separately here.
  * **Ratio magnitudes are unbounded.** A PE of 400 and a PE of 401 differ by 1.0
    in absolute terms and by 0.25% in relative terms; a PE of 4.0 and 5.0 differ
    by 1.0 and by 25%. Absolute-difference statistics alone would be dominated by
    expensive securities, so relative differences are reported alongside.

The admissibility rule was fixed BEFORE these numbers were computed (see the
ruling): agreement except for explainable display/rounding effects, missingness
differences attributable to the PE domain or the official NA representation, no
systematic level or sign divergence, and no evidence of a retrospectively
recomputed series. No numerical pass threshold is invented here.

    python research/b0_valuation_lineage_audit/reconcile_pre2019_pe.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from harvest_official_pbr import NA_TOKENS, decision_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
LINEAGE = os.path.join(ART, "pre2019_valuation_overlap.csv")
OUT = os.path.join(HERE, "pre2019_pe_reconciliation.json")

OVERLAP_FROM, OVERLAP_TO = "2016-01", "2018-12"


def load_norm(src: str, sess: str):
    p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def summarise(pairs, board: str) -> dict:
    """pairs: [(session, sid, official, official_raw, lineage)]"""
    n = len(pairs)
    diffs = [o - l for _, _, o, _, l in pairs]
    ad = sorted(abs(d) for d in diffs)
    rel = sorted(abs(o - l) / abs(l) for _, _, o, _, l in pairs if l)
    dec = [_decimals(r) for _, _, _, r, _ in pairs]
    tick = 10 ** -(min(dec) if dec else 2)

    def q(v, p):
        return round(v[int(p * (len(v) - 1))], 6) if v else None

    exact = sum(1 for d in ad if d < 1e-9)
    half_tick = sum(1 for d in ad if d <= tick / 2 + 1e-12)
    disagreements = sorted(
        ({"session": s, "stock_id": sid, "official": o, "lineage": l,
          "diff": round(o - l, 6),
          "rel": round(abs(o - l) / abs(l), 6) if l else None}
         for s, sid, o, _, l in pairs if abs(o - l) >= 1e-9),
        key=lambda r: -(r["rel"] or 0))
    return {
        "board": board,
        "compared": n,
        "exact_equal": exact,
        "exact_equal_rate": round(exact / n, 6) if n else None,
        "published_decimals_min": min(dec) if dec else None,
        "published_decimals_max": max(dec) if dec else None,
        "tick": tick,
        "within_half_tick": half_tick,
        "within_half_tick_rate": round(half_tick / n, 6) if n else None,
        "abs_diff_p50": q(ad, 0.50), "abs_diff_p90": q(ad, 0.90),
        "abs_diff_p99": q(ad, 0.99),
        "abs_diff_max": round(ad[-1], 6) if ad else None,
        "signed_diff_mean": round(statistics.fmean(diffs), 8) if diffs else None,
        "signed_diff_median": round(statistics.median(diffs), 8) if diffs else None,
        "signed_positive": sum(1 for d in diffs if d > 1e-9),
        "signed_negative": sum(1 for d in diffs if d < -1e-9),
        "rel_diff_p50": q(rel, 0.50), "rel_diff_p99": q(rel, 0.99),
        "rel_diff_max": round(rel[-1], 6) if rel else None,
        "rel_diff_gt_1pct": sum(1 for r in rel if r > 0.01),
        "rel_diff_gt_5pct": sum(1 for r in rel if r > 0.05),
        "disagreements_top20": disagreements[:20],
        "disagreement_sessions": sorted({d["session"] for d in disagreements}),
    }


def main() -> None:
    import pandas as pd

    sessions = [s for _, _, s in decision_sessions(OVERLAP_FROM, OVERLAP_TO)]
    if not os.path.exists(LINEAGE):
        raise SystemExit("abort: %s not built" % os.path.relpath(LINEAGE, REPO))
    df = pd.read_csv(LINEAGE, dtype={"stock_id": str})

    # MEASURED, not assumed: the yearly export encodes "no meaningful ratio" as
    # exactly 0.0 rather than as an empty cell — 4,927 rows in this window, every
    # one of them exactly 0.0 and not one of them negative, against 7 for PBR.
    # A 0.0 read as a number would make PEG = 0/g, i.e. the CHEAPEST possible
    # rank, out of a security that has no PE at all. The frozen domain (C-17:
    # PE > 0 and eps_growth > 0, else NA) already rejects it downstream; here it
    # is classified as the absence it is, so the missingness comparison measures
    # domain agreement instead of an encoding difference.
    sentinel_zero = 0
    lineage, priced = {}, {}
    for r in df.itertuples(index=False):
        key = (str(r.stock_id), str(r.session))
        per = _f(r.per_tse)
        if per is not None and per == 0.0:
            per = None
            sentinel_zero += 1
        lineage[key] = {"per": per, "close": _f(r.close)}
        c = _f(r.close)
        if c and c > 0:
            priced.setdefault(str(r.session), set()).add(str(r.stock_id))

    usable = [s for s in sessions
              if load_norm("twse", s) is not None and load_norm("tpex", s) is not None]
    print("overlap sessions usable: %d of %d" % (len(usable), len(sessions)),
          flush=True)

    per_board = {"twse": [], "tpex": []}
    miss = {"twse": Counter(), "tpex": Counter()}
    na_tokens = {"twse": Counter(), "tpex": Counter()}
    off_board_total = 0
    per_session = []

    for sess in usable:
        recs = {"twse": load_norm("twse", sess), "tpex": load_norm("tpex", sess)}
        published = {src: set(recs[src].get("pe_raw") or {}) for src in recs}
        row = {"session": sess, "priced": len(priced.get(sess, set()))}
        for src in ("twse", "tpex"):
            vals = recs[src].get("pe_values") or {}
            raws = recs[src].get("pe_raw") or {}
            for sid in priced.get(sess, set()) & published[src]:
                lin = lineage.get((sid, sess)) or {}
                off, lin_pe = vals.get(sid), lin.get("per")
                raw = raws.get(sid, "")
                if raw in NA_TOKENS:
                    na_tokens[src][raw or "<empty>"] += 1
                if off is not None and lin_pe is not None:
                    per_board[src].append((sess, sid, off, raw, lin_pe))
                    miss[src]["both_present"] += 1
                elif off is not None and lin_pe is None:
                    miss[src]["official_only"] += 1
                    miss[src]["official_only_negative_pe"] += int(off <= 0)
                elif off is None and lin_pe is not None:
                    # Rule 2 turns on WHY the two sides disagree about the
                    # domain. After the 0.0 sentinel is read as absence, anything
                    # left here is the vendor holding an ordinary positive PE the
                    # exchange does not publish — which would NOT be a definition
                    # difference, and is the case worth counting.
                    miss[src]["lineage_only_official_na"] += 1
                    miss[src]["lineage_only_positive_pe"] += int(lin_pe > 0)
                else:
                    miss[src]["both_na_domain_agreement"] += 1
            row["%s_compared" % src] = len(
                [1 for s, _, _, _, _ in per_board[src] if s == sess])
        off = priced.get(sess, set()) - (published["twse"] | published["tpex"])
        off_board_total += len(off)
        row["priced_on_no_board"] = len(off)
        per_session.append(row)

    report = {
        "audit": "pre2019_pe_lineage_reconciliation",
        "question": ("does official exchange 本益比 reproduce the admissible "
                     "本益比-TSE lineage on the same stock and session?"),
        "window": {"from": OVERLAP_FROM, "to": OVERLAP_TO,
                   "sessions_requested": len(sessions),
                   "sessions_usable": len(usable)},
        "lineage_source": ("yearly export 2016-2018, column 本益比-TSE "
                           "(<= 2018 side of the §2.8.3 vintage boundary)"),
        "new_exchange_requests": 0,
        "used_per_tej": False,
        "used_quarantined_corpus": False,
        "b0_modified": False,
        "decision_or_performance_computed": False,
        "twse": summarise(per_board["twse"], "TWSE 上市"),
        "tpex": summarise(per_board["tpex"], "TPEx 上櫃"),
        "missingness": {k: dict(v) for k, v in miss.items()},
        "official_na_tokens": {k: dict(v) for k, v in na_tokens.items()},
        "lineage_sentinel_zero_rows": sentinel_zero,
        "lineage_sentinel_note": (
            "the yearly export writes 0.0, never a negative and never an empty "
            "cell, where the ratio is undefined; read as absence here, and "
            "rejected downstream anyway by the frozen PE > 0 domain (C-17)"),
        "priced_on_no_board_total": off_board_total,
        "per_session": per_session,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    for k in ("twse", "tpex"):
        s = report[k]
        print("%s n=%s exact=%s (%s) |d|p99=%s max=%s rel_p99=%s med_signed=%s"
              % (k.upper(), s["compared"], s["exact_equal"],
                 s["exact_equal_rate"], s["abs_diff_p99"], s["abs_diff_max"],
                 s["rel_diff_p99"], s["signed_diff_median"]))
        print("   missingness:", dict(miss[k]))
        print("   official NA tokens:", dict(na_tokens[k]))
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
