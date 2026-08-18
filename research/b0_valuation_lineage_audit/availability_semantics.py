# -*- coding: utf-8 -*-
"""Do the historical queries return the ratio AS PUBLISHED THEN? — READ-ONLY.

For the window under ruling (2019+) TWSE answers this itself: every row carries
財報年/季, the statement period behind the ratio, and the report page states the
figures are `計算當時公開資訊觀測站已公告申報格式化之資料，而非同期即時資訊`.

TPEx says no such thing before 2025. Its payload notes define the ratio
(`股價淨值比＝收盤價／每股淨值`) and stop there, so for the early 上櫃 years the
source does not name the statement period behind the denominator. Reading more
documentation does not fix that; the gap is in the source.

It can, however, be MEASURED, because the denominator is recoverable:

    BVPS(i, s) = close(i, s) / PBR(i, s)

If the exchange archived what it published on session s, the implied BVPS is
piecewise constant and steps only when a new statement is announced — four times
a year, on the statutory calendar. If instead the endpoint recomputes today's
ratio and back-dates it, the implied BVPS is ONE level across the whole history.
Those hypotheses are far apart, so a measurement separates them.

Rounding is carried exactly rather than by a fudge factor: a published PBR of
`p` at two decimals means the true ratio is in [p-0.005, p+0.005], so BVPS lies
in an interval. Two observations are consistent with the same book value
whenever their intervals intersect; a STEP is recorded only when they cannot.

Calibration comes first. The estimator is run on TWSE 2019+, where 財報年/季 is
ground truth, and its steps are cross-tabulated against the sessions where the
disclosed vintage actually changed. An estimator that reproduces the disclosed
vintage on 上市 is then applied to 上櫃, where nothing is disclosed.

Availability semantics only. No strategy quantity is computed, and this cannot
settle WHICH vintage TPEx used — only whether the series behaves like an
archived per-session record or a back-dated recomputation.

    python research/b0_valuation_lineage_audit/availability_semantics.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from harvest_official_pbr import decision_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
CLOSES = {
    "pre2019": os.path.join(ART, "pre2019_lineage_month_ends.csv"),
    "2019plus": os.path.join(ART, "closes_2019plus_month_ends.csv"),
}
OUT = os.path.join(HERE, "availability_semantics_report.json")

ERAS = {"pre2019": ("2016-01", "2018-12"), "2019plus": ("2019-01", "2026-03")}
HALF_TICK = 0.005                   # both exchanges publish the ratio at 2 dp
MIN_OBS = 8                         # a security needs a real span to be judged


def load_norm(src: str, sess: str):
    p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def load_closes(era: str) -> dict:
    import pandas as pd

    path = CLOSES[era]
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype={"stock_id": str})
    out = {}
    for r in df.itertuples(index=False):
        try:
            c = float(r.close)
        except (TypeError, ValueError):
            continue
        if c > 0:
            out[(str(r.stock_id), str(r.session))] = c
    return out


def bvps_interval(close: float, pbr: float):
    lo_ratio, hi_ratio = pbr - HALF_TICK, pbr + HALF_TICK
    if lo_ratio <= 0:
        return None
    return close / hi_ratio, close / lo_ratio      # (low BVPS, high BVPS)


def step_scan(obs):
    """obs: [(session, close, pbr)] in session order. Greedy interval sweep."""
    levels, steps, cur = 0, [], None
    for sess, close, pbr in obs:
        iv = bvps_interval(close, pbr)
        if iv is None:
            continue
        if cur is None:
            cur, levels = iv, 1
            continue
        lo, hi = max(cur[0], iv[0]), min(cur[1], iv[1])
        if lo <= hi:
            cur = (lo, hi)                          # still one book value
        else:
            steps.append(sess)
            cur, levels = iv, levels + 1
    return levels, steps


def analyse(src: str, sessions: list[str], ext_close: dict, label: str) -> dict:
    per_sec: dict[str, list] = {}
    vintage: dict[str, dict[str, str]] = {}
    payload_close_used = 0
    external_close_used = 0
    harvested = 0
    for sess in sessions:
        rec = load_norm(src, sess)
        if rec is None:
            continue
        harvested += 1
        closes = rec.get("close") or {}
        for sid, pbr in (rec.get("values") or {}).items():
            c = closes.get(sid)
            if c is not None:
                payload_close_used += 1
            else:
                c = ext_close.get((sid, sess))
                if c is not None:
                    external_close_used += 1
            if not c or c <= 0 or pbr <= 0:
                continue
            per_sec.setdefault(sid, []).append((sess, float(c), float(pbr)))
        for sid, v in (rec.get("vintage") or {}).items():
            vintage.setdefault(sid, {})[sess] = v

    # Years of data actually observed, not years requested: a partly harvested
    # era would otherwise report a steps-per-year that looks like a flat series.
    observed = sorted({s for obs in per_sec.values() for s, _, _ in obs})
    years = max(1, len(set(s[:4] for s in observed)))
    level_hist, step_months, agree = Counter(), Counter(), Counter()
    steps_total = obs_total = single = multi = 0
    for sid, obs in per_sec.items():
        obs.sort()
        if len(obs) < MIN_OBS:
            continue
        levels, steps = step_scan(obs)
        level_hist[min(levels, 20)] += 1
        steps_total += len(steps)
        obs_total += len(obs)
        for s in steps:
            step_months[s[5:7]] += 1
        if levels <= 1:
            single += 1
        else:
            multi += 1
        vs = vintage.get(sid, {})
        if vs:
            seq = [s for s, _, _ in obs]
            stepset = set(steps)
            for prev, cur in zip(seq, seq[1:]):
                if prev not in vs or cur not in vs:
                    continue
                vchg, sstep = vs[prev] != vs[cur], cur in stepset
                agree["vintage_changed_and_step" if vchg and sstep else
                      "vintage_changed_no_step" if vchg else
                      "no_change_but_step" if sstep else
                      "no_change_no_step"] += 1

    n = single + multi
    out = {
        "label": label,
        "source": src,
        "sessions_requested": len(sessions),
        "sessions_harvested": harvested,
        "close_from_payload_obs": payload_close_used,
        "close_from_admissible_corpus_obs": external_close_used,
        "securities_analysed": n,
        "observations": obs_total,
        "implied_bvps_levels_histogram": {str(k): v for k, v in
                                          sorted(level_hist.items())},
        "securities_with_one_level_only": single,
        "securities_with_multiple_levels": multi,
        "multi_level_share": round(multi / n, 4) if n else None,
        "steps_total": steps_total,
        "steps_per_security_year": round(steps_total / n / years, 3) if n else None,
        "step_month_histogram": dict(sorted(step_months.items())),
        "vintage_crosstab": dict(agree) or None,
    }
    if agree:
        tp = agree["vintage_changed_and_step"]
        fn = agree["vintage_changed_no_step"]
        fp = agree["no_change_but_step"]
        tn = agree["no_change_no_step"]
        tot = tp + fn + fp + tn
        out["vintage_agreement_rate"] = round((tp + tn) / tot, 4) if tot else None
        out["step_recall_on_vintage_change"] = round(
            tp / (tp + fn), 4) if (tp + fn) else None
        out["step_without_vintage_change_rate"] = round(
            fp / (fp + tn), 4) if (fp + tn) else None
    return out


def field_layout_changes(src: str) -> list:
    """When the source's disclosure changed, measured from the payloads."""
    seen, out = None, []
    for era in ("pre2019", "2019plus"):
        for _, _, sess in decision_sessions(*ERAS[era]):
            rec = load_norm(src, sess)
            if rec is None:
                continue
            f = tuple(rec.get("fields") or [])
            if f != seen:
                out.append({"first_session_with_layout": sess, "fields": list(f),
                            "discloses_vintage": "財報年/季" in f})
                seen = f
    return out


def main() -> None:
    runs = []
    for era, src in (("2019plus", "twse"), ("pre2019", "twse"),
                     ("2019plus", "tpex"), ("pre2019", "tpex")):
        sessions = [s for _, _, s in decision_sessions(*ERAS[era])]
        ext = load_closes(era)
        label = "%s_%s" % (src, era)
        runs.append(analyse(src, sessions, ext, label))
        print("%-16s sessions=%d/%d closes=%d" % (
            label, runs[-1]["sessions_harvested"], len(sessions), len(ext)),
            flush=True)

    report = {
        "audit": "official_pbr_availability_semantics",
        "method": ("implied BVPS = close / published PBR, with the published "
                   "two-decimal rounding carried as an interval; a step is "
                   "recorded only when two intervals cannot intersect"),
        "close_sources": {
            "twse_2019plus": "payload 收盤價 where present",
            "other": ("admissible corpus only — yearly export for <= 2018, the "
                      "two zips for >= 2019; no valuation column is read from "
                      "either, and the quarantined 2019+ xlsx vintage is not "
                      "opened"),
        },
        "runs": {r["label"]: r for r in runs},
        "disclosure_timeline": {
            "twse": field_layout_changes("twse"),
            "tpex": field_layout_changes("tpex"),
        },
        "documentation": {
            "twse": ("the report page states the figures are 計算當時公開資訊觀測站"
                     "已公告申報格式化之資料，而非同期即時資訊，且不作回溯計算 — no "
                     "retrospective recomputation — and that 股利年度及財報年/季資訊"
                     "自民國106年4月12日起提供 (2017-04-12); the payload carries "
                     "財報年/季 per row from that layout onward"),
            "tpex_pre_2025": ("payload notes define 股價淨值比＝收盤價／每股淨值 only; "
                              "no statement period is named and the response "
                              "carries no vintage column"),
            "tpex_from_2025": ("財報年/季 appears in the peQryDate response; measured "
                               "boundary: absent on 2024-12-31, present on "
                               "2025-01-02"),
            "tpex_openapi_current": ("/tpex_mainboard_peratio_analysis publishes "
                                     "seven fields and no vintage"),
        },
        "limitation": (
            "This measures behaviour, not documentation. It can show that a "
            "series behaves like an archived per-session record rather than a "
            "back-dated recomputation. It cannot show WHICH statement vintage "
            "stood behind each 上櫃 denominator before 2025, because the source "
            "does not say and no official document was found that says it."),
        "decision_or_performance_computed": False,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    for r in runs:
        print("%-16s n=%s multi=%s steps/sec/yr=%s agree=%s recall=%s" % (
            r["label"], r["securities_analysed"], r["multi_level_share"],
            r["steps_per_security_year"], r.get("vintage_agreement_rate"),
            r.get("step_recall_on_vintage_change")))
        print("%-16s step months: %s" % ("", r["step_month_histogram"]))
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
