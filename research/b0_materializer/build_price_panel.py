# -*- coding: utf-8 -*-
"""§2.8.3 · the canonical daily price panel, from the SEALED composed source.

The previous version of this file read `~/tej_cache/price_valuation` wholesale
and carried `PBR_TSE` / `PER_TSE` out of it. That was wrong in one specific way
worth stating precisely, because the fix is not "stop touching that path":

    the composed canonical source IS
        <= 2018   ~/tej_cache/price_valuation, restricted to date < 2019-01-01
        >= 2019   股價 2019-2022.zip + 股價2023-20260817.zip
    and the D-1 quarantine is on the 2019+ ERA of that cache, not on the cache
    as an object. `research/d1_price_universe/register_price_source.py` composes
    exactly these two legs and fingerprints them as `b0_price_universe_20260817`.

So the cutoff is the whole point, and it is enforced mechanically here rather
than trusted: every row from the cache leg is asserted to be pre-2019, every row
from the zip leg to be 2019+, and the composed coverage manifest is recomputed
and asserted EQUAL to the sealed contract's `content_sha256`. If this panel ever
stops reading the sealed source, the build aborts before writing anything.

Valuation is NOT read here. `pbr_tse` / `per_tse` come from the sealed valuation
panel under C-48 / C-49; a price panel that also carried a ratio would be a
second, unruled valuation lineage sitting one import away.

**Units.** C-25 pins adv20 to the legacy producer, `dollar_vol = close *
Trading_Volume` with `Trading_Volume` in SHARES. The cache leg is already in
shares; the zip leg publishes 成交量(千股), so it is multiplied by 1,000. That is
a unit conversion required for the frozen comparison to be dimensionally
correct, not a choice — and because a silent factor-of-1,000 break at the era
boundary would corrupt the §4.2 ADV gate for exactly the 87 months under ruling,
the boundary is checked numerically instead of being reasoned about.

adv20 and sigma20d are deliberately NOT computed here. They are frozen formulas
in `core.b0_state` (C-25 / C-26); this panel supplies the series they consume.

    python research/b0_materializer/build_price_panel.py
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "d1_price_universe"))

from core.b0_master_prereg import spec as frozen_spec          # noqa: E402
from core.b0_price_universe import (                            # noqa: E402
    CONTAMINATED_CORPUS_SHA256,
    PriceSourceContract,
    assert_price_source_admissible,
)

IMPORTER_VERSION = "price_panel_importer_v1"
VINTAGE_BOUNDARY = "2019-01-01"

OLD_CACHE = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
ZIP_DIR = os.path.join(REPO, "tej_exports", "DataExport0806",
                       "個股股價、本益比2004-20260817")
CONTRACT_JSON = os.path.join(REPO, "research", "d1_price_universe",
                             "price_source_contract.json")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")

OUT_PARQUET = os.path.join(REPO, "data", "b0", "price_panel.parquet")
OUT_RECEIPT = os.path.join(HERE, "price_panel_receipt.json")

CARRY = ("stock_id", "date", "open", "close", "volume_shares", "traded_value")
# Present in one leg or the other and deliberately never carried: the valuation
# columns belong to the sealed valuation panel (C-48 / C-49).
EXCLUDED_BY_LINEAGE = ("PER_TSE", "PER_TEJ", "PBR_TSE", "PBR_TEJ",
                       "dividend_yield_TSE", "本益比-TEJ", "股價淨值比-TEJ")


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sealed_contract() -> PriceSourceContract:
    """The already-registered D1-7 contract. Not re-invented here."""
    if not os.path.exists(CONTRACT_JSON):
        raise SystemExit("abort: %s missing; the price source must be registered "
                         "before a panel can claim it"
                         % os.path.relpath(CONTRACT_JSON, REPO))
    payload = json.load(open(CONTRACT_JSON, encoding="utf-8"))
    contract = PriceSourceContract(**payload["contract"])
    assert_price_source_admissible(contract)
    if contract.content_sha256 == CONTAMINATED_CORPUS_SHA256:
        raise SystemExit("abort: the registered contract carries the quarantined "
                         "fingerprint")
    return contract


def assert_reads_the_sealed_source(contract: PriceSourceContract) -> str:
    """Recompute the composed manifest and require the sealed fingerprint.

    This is the gate. Everything else in this file is bookkeeping: if the
    manifest matches, the panel is being built over the same composition D-1
    verified and B-21 sealed; if it does not, no amount of downstream care makes
    the panel the right one.
    """
    from rebuild_audit_new_source import coverage

    years, first, last = coverage("new")
    manifest = "\n".join(sorted(
        f"{s}:{first[s]}:{last[s]}:{len(years[s])}" for s in first))
    sha = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
    if sha != contract.content_sha256:
        raise SystemExit(
            "abort: composed source manifest is %s but the sealed contract "
            "declares %s. The panel would not be built over the sealed source."
            % (sha[:16], contract.content_sha256[:16]))
    if sha == CONTAMINATED_CORPUS_SHA256:
        raise SystemExit("abort: composed manifest equals the quarantined corpus")
    return sha


def panel_span() -> tuple[str, str]:
    """Derived from the frozen window, never chosen.

    Start: the calendar year of `window_start` minus `lookback_L_months`, so the
    12-1 momentum window and the 20-session liquidity/volatility windows of the
    FIRST decision month are inside the panel.
    End: the first session strictly after `window_end` — §6.5 executes at the
    OPEN of the session following the decision date, and nothing beyond it is
    reachable by B0.
    """
    import csv

    import pandas as pd

    start = pd.Timestamp(str(frozen_spec("window_start")))
    lookback = int(frozen_spec("lookback_L_months"))
    first_year = (start - pd.DateOffset(months=lookback)).year
    with open(CALENDAR, encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    end = str(frozen_spec("window_end"))
    after = [s for s in sessions if s > end]
    if not after:
        raise SystemExit(
            "abort: the calendar has no session after window_end %s, so the §6.5 "
            "execution session of the final decision month does not exist" % end)
    return "%d-01-01" % first_year, after[0]


def cache_leg(date_min: str, date_max: str):
    """<= 2018 leg. Every row asserted pre-2019 before it can be used."""
    import pandas as pd

    files = sorted(glob.glob(os.path.join(OLD_CACHE, "*.parquet")))
    if not files:
        raise SystemExit("abort: no per-security parquet under %s" % OLD_CACHE)
    frames, leaked = [], 0
    for f in files:
        d = pd.read_parquet(f, columns=["stock_id", "date", "open", "close",
                                        "Trading_Volume"])
        if d.empty:
            continue
        d["date"] = d["date"].astype(str)
        post = d["date"] >= VINTAGE_BOUNDARY
        leaked += int(post.sum())
        d = d[~post]
        d = d[(d["date"] >= date_min) & (d["date"] <= date_max)]
        if d.empty:
            continue
        d["stock_id"] = d["stock_id"].astype(str)
        d["volume_shares"] = pd.to_numeric(d["Trading_Volume"], errors="coerce")
        frames.append(d[["stock_id", "date", "open", "close", "volume_shares"]])
    out = pd.concat(frames, ignore_index=True)
    bad = out[out["date"] >= VINTAGE_BOUNDARY]
    if len(bad):
        raise SystemExit(
            "abort: %d rows from the cache leg are dated %s or later. That era of "
            "this cache is the D-1 quarantined vintage." % (len(bad),
                                                            VINTAGE_BOUNDARY))
    print("  cache leg: %d rows from %d securities (dropped %d rows >= %s, the "
          "quarantined era)" % (len(out), out["stock_id"].nunique(), leaked,
                                VINTAGE_BOUNDARY), flush=True)
    return out


def zip_leg(date_min: str, date_max: str):
    """>= 2019 leg. 成交量(千股) -> shares, to match the frozen adv20 lineage."""
    import pandas as pd

    zips = sorted(glob.glob(os.path.join(ZIP_DIR, "*.zip")))
    if len(zips) != 2:
        raise SystemExit("abort: expected the two D-1 replacement zips, found %d"
                         % len(zips))
    frames, upstream = [], {}
    for z in zips:
        upstream[os.path.basename(z)] = _file_sha(z)
        with zipfile.ZipFile(z) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as fh:
                txt = fh.read().decode("utf-16")
        d = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str,
                        usecols=["證券代碼", "年月日", "開盤價(元)", "收盤價(元)",
                                 "成交量(千股)"])
        d["date"] = pd.to_datetime(d["年月日"], errors="coerce").dt.strftime(
            "%Y-%m-%d")
        d = d[d["date"].notna()]
        d = d[(d["date"] >= date_min) & (d["date"] <= date_max)]
        d["stock_id"] = d["證券代碼"].astype(str).str.split().str[0].str.strip()
        d["open"] = pd.to_numeric(d["開盤價(元)"], errors="coerce")
        d["close"] = pd.to_numeric(d["收盤價(元)"], errors="coerce")
        d["volume_shares"] = pd.to_numeric(
            d["成交量(千股)"], errors="coerce") * 1000.0
        frames.append(d[["stock_id", "date", "open", "close", "volume_shares"]])
        print("  %s: %d rows" % (os.path.basename(z), len(d)), flush=True)
    out = pd.concat(frames, ignore_index=True)
    bad = out[out["date"] < VINTAGE_BOUNDARY]
    if len(bad):
        raise SystemExit(
            "abort: %d rows from the zip leg are dated before %s; the pre-2019 "
            "era belongs to the yearly-export leg" % (len(bad), VINTAGE_BOUNDARY))
    return out, upstream


def assert_unit_continuity(panel) -> dict:
    """A factor-of-1,000 break at the boundary would be invisible downstream.

    adv20 feeds the §4.2 ADV floor, which is an absolute NTD threshold, so a unit
    discontinuity would not look like an error — it would look like every
    security suddenly becoming liquid, or none of them.
    """
    import pandas as pd

    before = panel[(panel["date"] >= "2018-11-01") & (panel["date"] < "2019-01-01")]
    after = panel[(panel["date"] >= "2019-01-01") & (panel["date"] < "2019-03-01")]
    if before.empty or after.empty:
        raise SystemExit("abort: cannot check unit continuity across the boundary")
    med_before = float(before["traded_value"].median())
    med_after = float(after["traded_value"].median())
    ratio = med_after / med_before if med_before else float("inf")
    if not (0.2 <= ratio <= 5.0):
        raise SystemExit(
            "abort: median traded value moves %.1fx across the vintage boundary "
            "(%.3g -> %.3g). That is a unit break, not a market move."
            % (ratio, med_before, med_after))
    return {"median_traded_value_2018Q4": med_before,
            "median_traded_value_2019JanFeb": med_after,
            "ratio": round(ratio, 4),
            "unit": "NTD = close(元) * volume(shares), C-25 legacy lineage"}


def main() -> None:
    import pandas as pd

    contract = sealed_contract()
    print("sealed price source: %s (%s)" % (contract.name,
                                            contract.content_sha256[:16]),
          flush=True)
    manifest_sha = assert_reads_the_sealed_source(contract)
    print("composed manifest reproduces the sealed fingerprint", flush=True)

    date_min, date_max = panel_span()
    print("panel span %s .. %s (derived: window_start - lookback_L_months, "
          "through the §6.5 execution session)" % (date_min, date_max), flush=True)

    pre = cache_leg(date_min, date_max)
    post, zip_upstream = zip_leg(date_min, date_max)
    panel = pd.concat([pre, post], ignore_index=True)
    panel["open"] = pd.to_numeric(panel["open"], errors="coerce")
    panel["close"] = pd.to_numeric(panel["close"], errors="coerce")
    panel["traded_value"] = panel["close"] * panel["volume_shares"]
    panel = panel[list(CARRY)].sort_values(["stock_id", "date"]).reset_index(
        drop=True)

    dupes = int(panel.duplicated(["stock_id", "date"]).sum())
    if dupes:
        raise SystemExit(
            "abort: %d duplicate (stock_id, date) rows. The two legs must abut at "
            "%s, not overlap." % (dupes, VINTAGE_BOUNDARY))
    units = assert_unit_continuity(panel)

    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    panel.to_parquet(OUT_PARQUET, index=False)

    schema = json.dumps({c: str(panel[c].dtype) for c in panel.columns},
                        sort_keys=True).encode("utf-8")
    receipt = {
        "artefact": "data/b0/price_panel.parquet",
        "builder": "research/b0_materializer/build_price_panel.py",
        "clause": "§2.8.3 canonical price source, D1-6/D1-7 admissibility",
        "importer_version": IMPORTER_VERSION,
        "price_source": {
            "name": contract.name,
            "importer_version": contract.importer_version,
            "content_sha256": contract.content_sha256,
            "manifest_recomputed_sha256": manifest_sha,
            "reproduces_sealed_fingerprint": manifest_sha == contract.content_sha256,
            "includes_delisted": contract.includes_delisted,
            "lineage": contract.lineage,
        },
        "composition": {
            "pre_2019": "~/tej_cache/price_valuation, date < %s" % VINTAGE_BOUNDARY,
            "from_2019": sorted(zip_upstream),
            "boundary_enforced_mechanically": True,
        },
        "upstream_zip_sha256": zip_upstream,
        "quarantined_corpus_sha256": CONTAMINATED_CORPUS_SHA256,
        "quarantined_era_rows_dropped": True,
        "content_sha256": _file_sha(OUT_PARQUET),
        "schema_sha256": hashlib.sha256(schema).hexdigest(),
        "bytes": os.path.getsize(OUT_PARQUET),
        "rows": int(len(panel)),
        "securities": int(panel["stock_id"].nunique()),
        "date_min": str(panel["date"].min()),
        "date_max": str(panel["date"].max()),
        "carried_columns": list(CARRY),
        "excluded_by_frozen_lineage": list(EXCLUDED_BY_LINEAGE),
        "adv20_sigma20d_computed_here": False,
        "adv20_sigma20d_owner": "core.b0_state (C-25 / C-26)",
        "unit_continuity": units,
        "close_na_rows": int(panel["close"].isna().sum()),
        "performance_computed": False,
    }
    with open(OUT_RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("rows=%d securities=%d span=%s..%s" % (
        len(panel), panel["stock_id"].nunique(), panel["date"].min(),
        panel["date"].max()))
    print("unit continuity ratio across boundary: %.4f" % units["ratio"])
    print("wrote", os.path.relpath(OUT_PARQUET, REPO), "and",
          os.path.relpath(OUT_RECEIPT, REPO))


if __name__ == "__main__":
    main()
