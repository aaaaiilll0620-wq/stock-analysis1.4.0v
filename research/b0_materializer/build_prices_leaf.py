# -*- coding: utf-8 -*-
"""W4 · the prices leaf producer for an L3 run.

The hardest of the nine families, for three reasons W1 measured rather than
guessed.

1 · AN ARCHIVE IS NOT A FILE
    `build_price_panel.py:195` globs `ZIP_DIR/*.zip`. That is the O-H defect
    inverted and worse: O-H was "the file that should have been read was not",
    this is "a file that should NOT be read silently is". The same directory
    also holds 24 workbooks that are deliberately excluded, so "everything in
    the directory" is not the rule either. Both zips and both exclusions are
    therefore DECLARED, and each archive carries its full member inventory
    (name, size, crc32) — a member added to or removed from a declared zip
    changes nothing the zip's own path can show.

2 · TWO SOURCE FAMILIES, AND TEJ IS AUTHORITATIVE (R-W1-2)
    On the 25-session overlap W1 measured 48,079 shared (stock_id, date) rows:

        close disagreements            1  (a sentinel zero, see 3)
        volume disagreements      47,047  (97.9%, all < 1,000 shares)
        TEJ-only securities          781  (22-47 per session)
        LIVE-only securities         722  (27-31 per session)

    The volume gap is not a disagreement about a fact: TEJ publishes 成交量(千股)
    and the importer multiplies by 1,000, so TEJ share counts are ALWAYS
    multiples of 1,000 while the live feed gives actual shares. It is rounding —
    but C-25 pins adv20 to `close × Trading_Volume` and §4.2 applies an absolute
    NTD floor to it, so at NT$100 a 999-share rounding is ~NT$100k of adv per
    day, and a name sitting on the floor can be judged differently by each leg.
    So authority is declared per entry and covers UNITS AND PRECISION, not only
    values.

    The population gap is the real conflict axis: under TEJ-authoritative, ~30
    securities per session that the live feed lists are excluded. That is a
    population being cut, and a cut population has to be a declared fact.

3 · THE SENTINEL ZERO IS THE EXPENSIVE ONE
    2026-07-14, 5906 台南-KY: TEJ open/close 37.0, live feed 0.0. The live feed
    uses 0.0 for "did not trade today". One row in 62,445 — and a held position
    marked at 0.0 zeroes its NAV contribution silently, without raising. This
    repository has already ruled the same shape for valuation ratios
    (`valuation_sentinel_zero_is_undefined`). The price leg must match: a live
    zero is UNDEFINED and must fail loud, never be used as a price.

    `SENTINEL_ZERO_POLICY` records that ruling next to the source it constrains,
    so the consumer cannot read the leaf without meeting it.

    python research/b0_materializer/build_prices_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError, build_leaf, write_leaf,
)

DATASET = "prices"

LANDING_DIRECTORY = os.path.join(
    "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")

# Every extension the directory actually holds. Unlike financials this is not a
# filter — it is the enumeration surface, and each entry is then declared
# consumed or not_consumed by name.
ENUMERATED_EXTENSIONS = (".zip", ".xlsx")

SENTINEL_ZERO_POLICY = {
    "rule": "LIVE_ZERO_PRICE_IS_UNDEFINED_AND_MUST_FAIL_LOUD",
    "applies_to_family": "LIVE",
    "fields": ["open", "close"],
    "rationale": (
        "the live feed encodes 'did not trade today' as 0.0; a held position "
        "marked at 0.0 zeroes its NAV contribution without raising. Same shape "
        "as the frozen `valuation_sentinel_zero_is_undefined` ruling."),
    "measured": "1 row in 62,445 (2026-07-14, 5906 台南-KY, TEJ 37.0 vs live 0.0)",
}

UNIT_AUTHORITY = {
    "rule": "TEJ_AUTHORITATIVE_COVERS_UNITS_AND_PRECISION",
    "detail": (
        "TEJ publishes 成交量(千股); the importer restores shares by x1000, so "
        "TEJ share counts are always multiples of 1,000 and the live feed's are "
        "not. adv20 = close x Trading_Volume (C-25) feeds an absolute NTD floor "
        "(§4.2), so mixing the two legs' units can put a name on opposite sides "
        "of the same threshold."),
    "measured": "47,047 of 48,079 overlapping rows differ, every one by < 1,000 shares",
}

POPULATION_AUTHORITY = {
    "rule": "TEJ_DEFINES_THE_POPULATION",
    "detail": (
        "securities the live feed lists and TEJ does not are EXCLUDED. This is "
        "a population being cut, so it is declared rather than discovered."),
    "measured": "722 live-only rows over 25 sessions (27-31 securities per session)",
}

# --- the declaration -----------------------------------------------------------
#
# TWO LEGS, TWO LANDING SURFACES, TWO UNIT CONVENTIONS.
#
# §2.8.3 splits the price lineage at 2019-01-01, and the two halves do not even
# live in the same tree:
#
#     <= 2018   ~/tej_cache/price_valuation, one parquet per security
#     >= 2019   the two archives in this export directory
#
# An earlier version of this file declared only the 2019+ leg while its docstring
# claimed a `PRE_2019_LEG` that did not exist. That was not cosmetic: with only
# the 2019+ leg declared, every listing spell for a security already listed in
# 2018 opens at the first covered session instead of its real start, and O-G's
# `opened_by` has no admissible value for "the corpus does not reach back far
# enough to say". Measured on the 2026-03 state: 1,706 of 1,958 securities got a
# fabricated spell start of 2019-01-02.

CONSUMED_ARCHIVES = ("股價 2019-2022.zip", "股價2023-20260817.zip")

NOT_CONSUMED_REASON = (
    "yearly/period workbook superseded by the two 2019+ archives and the "
    "pre-2019 cache leg; present in the export directory, deliberately not read "
    "by build_price_panel (§2.8.3 lineage)")

# The <= 2018 leg. A per-security parquet store, declared file by file for the
# same reason the archives are: `build_price_panel.py:159` reaches it with
# `glob("*.parquet")`, and a security appearing or disappearing from that
# directory changes the universe without changing any path.
PRE_2019_LEG = {
    "landing": os.path.join(os.path.expanduser("~"), "tej_cache",
                            "price_valuation"),
    "extensions": (".parquet",),
    "leg": "pre-2019",
    "columns": ("stock_id", "date", "open", "close", "Trading_Volume"),
}

# ⚠ THE CACHE IS PARTLY QUARANTINED, AND THE LINE IS A DATE, NOT A FILE.
#
# D-1 quarantined the 2019+ ERA of this cache, not the cache. The same parquet
# holds admissible pre-2019 rows and quarantined 2019+ rows, so the restriction
# cannot be expressed by which files are declared — it has to travel with them
# and be enforced at read time.
QUARANTINED_ERA_POLICY = {
    "rule": "PRE_2019_CACHE_ROWS_ONLY_THE_2019_ERA_IS_D1_QUARANTINED",
    "boundary": "2019-01-01",
    "applies_to_leg": "pre-2019",
    "detail": (
        "rows dated on or after the boundary must be dropped by the reader and "
        "the 2019+ archives used instead. The quarantine is on an era of this "
        "cache, so declaring the files does not admit their later rows."),
}

# The two legs disagree about what a volume number MEANS, which is exactly the
# kind of difference that does not raise.
LEG_UNIT_CONVENTIONS = {
    "rule": "VOLUME_UNITS_DIFFER_BY_LEG",
    "pre-2019": "Trading_Volume is ALREADY shares; no scaling",
    "2019+": "成交量(千股) is thousands; the reader restores shares by x1000",
    "detail": (
        "C-25 pins adv20 to close x Trading_Volume against an ABSOLUTE NTD "
        "floor (§4.2). Applying either leg's convention to the other does not "
        "raise — it moves every security across the liquidity floor by 1000x."),
}


def _members(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        return [{"name": i.filename, "size": int(i.file_size),
                 "crc32": "%08x" % i.CRC} for i in sorted(
                     z.infolist(), key=lambda i: i.filename)]


def build(run_id: str, as_of: str, landing_dir: str = "") -> dict:
    landing = landing_dir or os.path.join(REPO, LANDING_DIRECTORY)
    if not os.path.isdir(landing):
        raise ManifestError("abort: prices landing directory not found: %s"
                            % landing)
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    # Enumerate FIRST, then decide. Every entry is named, none is skipped.
    present, unknown = [], []
    for name in sorted(os.listdir(landing)):
        p = os.path.join(landing, name)
        if not os.path.isfile(p) or os.path.islink(p):
            unknown.append(name)
        elif os.path.splitext(name)[1].lower() in ENUMERATED_EXTENSIONS:
            present.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise ManifestError(
            "abort: %d entr(y/ies) in the prices landing directory are neither "
            "an archive nor a workbook:\n%s\n  directory: %s\n"
            "Every entry must be named accepted or rejected; this one is "
            "neither." % (len(unknown), "\n".join("    %s" % n for n in unknown),
                          landing))

    missing = [z for z in CONSUMED_ARCHIVES if z not in present]
    if missing:
        raise ManifestError(
            "abort: declared price archive(s) %s are not present under %s"
            % (missing, landing))

    entries = []
    for name in present:
        p = os.path.join(landing, name)
        consumed = name in CONSUMED_ARCHIVES
        entry = {
            "locator": name,
            "format": "zip" if name.lower().endswith(".zip") else "xlsx",
            "raw_sha256": file_sha256(p),
            # The export directory is dated 0806 but the archives were repacked
            # 2026-08-18; taken from the member timestamps, not the folder name.
            "export_vintage": "2026-08-18" if consumed else "2026-08-06",
            "observed_at": observed_at,
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed" if consumed else "not_consumed",
            "leg": "2019+" if consumed else None,
        }
        if not consumed:
            entry["not_consumed_reason"] = NOT_CONSUMED_REASON
        if entry["format"] == "zip":
            entry["members"] = _members(p)
        entries.append(entry)

    entries += _pre_2019_entries(observed_at)

    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=LANDING_DIRECTORY.replace("\\", "/"),
        accepted_extensions=ENUMERATED_EXTENSIONS,
        policies={
            "sentinel_zero": SENTINEL_ZERO_POLICY,
            "unit_authority": UNIT_AUTHORITY,
            "population_authority": POPULATION_AUTHORITY,
            "quarantined_era": QUARANTINED_ERA_POLICY,
            "leg_unit_conventions": LEG_UNIT_CONVENTIONS,
        })


def _pre_2019_entries(observed_at: str, payload_dir: str = "") -> list:
    """One entry per security parquet in the <= 2018 cache.

    Each carries its own `landing_directory` because this leg does not live in
    the leaf's landing surface at all. The reader prefers an entry's own landing
    and falls back to the leaf's, so a family with one surface stays unchanged.
    """
    directory = payload_dir or PRE_2019_LEG["landing"]
    if not os.path.isdir(directory):
        raise ManifestError(
            "abort: the pre-2019 price cache is not present at %s. Without it "
            "every listing spell for a security already listed in 2018 opens at "
            "the first 2019 session, which is a fabricated listing date rather "
            "than a missing one." % directory)

    names, unknown = [], []
    for name in sorted(os.listdir(directory)):
        p = os.path.join(directory, name)
        if (os.path.isfile(p) and not os.path.islink(p)
                and os.path.splitext(name)[1].lower()
                in PRE_2019_LEG["extensions"]):
            names.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise ManifestError(
            "abort: %d entr(y/ies) in the pre-2019 price cache are not "
            "per-security parquets:\n%s\n  store: %s"
            % (len(unknown), "\n".join("    %s" % n for n in unknown[:20]),
               directory))
    if not names:
        raise ManifestError("abort: the pre-2019 price cache %s is empty"
                            % directory)

    landing = directory.replace("\\", "/")
    out = []
    for name in names:
        p = os.path.join(directory, name)
        out.append({
            "locator": name,
            "landing_directory": landing,
            "format": "parquet",
            "raw_sha256": file_sha256(p),
            "export_vintage": _dt.date.fromtimestamp(
                os.path.getmtime(p)).isoformat(),
            "observed_at": observed_at,
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed",
            "leg": "pre-2019",
        })
    return out


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: build_prices_leaf.py <run_dir> <run_id> <as_of>")
        return 2
    record = write_leaf(argv[1], build(argv[2], argv[3]))
    for k, v in record.items():
        print("%-15s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
