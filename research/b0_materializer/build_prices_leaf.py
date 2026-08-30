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

4 · AN ARCHIVE ALSO EVIDENCES A ROSTER, AND NOT EVERY ARCHIVE EVIDENCES THE
    SAME ONE
    Two archives can carry the same eleven columns and still stand for different
    facts. A multi-year bulk pull carries the securities that existed across the
    years it spans, exits included. A query run today for "the last N sessions"
    carries the roster that exists TODAY — and nothing that left before today can
    appear in it, however many sessions it covers.

    Nothing in the bytes raises when the second is mistaken for the first: the
    columns match, the dates are real, the prices are real. What is absent is a
    population, and an absent population is exactly the D-1 defect
    (`core/b0_price_universe.py`). So the roster basis is DECLARED per archive
    (`roster_basis`), and an archive that cannot evidence delisted coverage says
    so in its own entry (`declared_properties.delisted_coverage`) rather than
    leaving a future reader to re-derive it from the row counts.

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

# The roster an archive can evidence. Declared, because it is not visible in the
# bytes: both bases produce the same eleven columns and the same real prices.
ROSTER_BASIS_BULK_HISTORICAL = "BULK_HISTORICAL_QUERY"
ROSTER_BASIS_CURRENT_SNAPSHOT = "CURRENT_ROSTER_SNAPSHOT"

# ⚠ A NAMED, DECLARED LIMITATION OF 股價0817-0828.zip — not a caveat in prose.
#
# Measured here on 2026-08-30, not inferred: this archive's 1,954 securities are
# EXACTLY the 1,954 present on 2026-08-17, the last session of
# 股價2023-20260817.zip. Zero added over nine sessions, zero dropped. A corpus
# that carries exits does not stay perfectly balanced by accident; a roster
# queried today does, by construction.
#
# It is therefore admissible as PRICES and inadmissible as EVIDENCE OF COVERAGE.
# The distinction has to survive in the manifest, because the next reader will
# see nine clean sessions of a perfectly balanced panel — which is what a
# complete corpus and a survivorship-filtered one look like from outside.
ROSTER_SNAPSHOT_LIMITATION = {
    "property": "ROSTER_SNAPSHOT_DERIVED_DOES_NOT_EVIDENCE_DELISTED_COVERAGE",
    "roster_basis": ROSTER_BASIS_CURRENT_SNAPSHOT,
    "measured": (
        "17,586 rows = 1,954 securities x 9 sessions, 2026-08-18 .. 2026-08-28, "
        "every session carrying all 1,954. The security set is identical to the "
        "1,954 on 2026-08-17, the final session of 股價2023-20260817.zip: 0 "
        "added, 0 dropped. That is the signature of a current-roster query run "
        "on 2026-08-30, not of a corpus that carries exits."),
    "corroboration": (
        "TEJ pads non-trading names instead of omitting them, so balance is not "
        "evidence of trading either: 1589 and 4804 carry frozen OHLC (5.5400 "
        "and 3.2700) with 0 成交量(千股) on all nine sessions."),
    "admissible_as": "prices for securities listed on 2026-08-17",
    "inadmissible_as": (
        "evidence that the composed corpus carries securities that left the "
        "exchange. It may never be cited toward D1-6 includes_delisted."),
    "does_not_change_includes_delisted": (
        "PriceSourceContract.includes_delisted for b0_price_universe_20260817 "
        "was earned by the 2019-2025 era of the other two legs and re-verified "
        "by rebuild_audit_new_source; nine sessions in 2026-08 add no year to "
        "the C1 window (2019-2025) and no termination to the 2018-12-28 C2 "
        "cluster, so they can neither support the standing nor withdraw it. A "
        "slice that cannot move a gate must not be read as having passed it."),
}

# ⚠ THE INVENTORY IS BY NAME AND BY HASH, NEVER BY COUNT.
#
# `build_price_panel.zip_leg` used to guard the same directory with
# `len(zips) != 2`. A count is not an inventory: it admits any two zips and
# refuses the right three, which is how a stray file gets to matter. Every
# archive that may be read is named here with the bytes it must have, the leg it
# belongs to, the span it actually covers, and the roster it can evidence.
#
# `covers` is MEASURED, not taken from the filename. 股價0817-0828.zip is named
# for 0817 and does not contain 2026-08-17 at all.
CONSUMED_ARCHIVE_DECLARATIONS = {
    "股價 2019-2022.zip": {
        "leg": "2019+",
        "raw_sha256":
            "41ef1cce47ffb8dc9f58fb9c47cfd579b00fbeab61b61cb3a4fc5df0e0823413",
        "covers": ("2019-01-02", "2022-12-30"),
        "roster_basis": ROSTER_BASIS_BULK_HISTORICAL,
    },
    "股價2023-20260817.zip": {
        "leg": "2019+",
        "raw_sha256":
            "049881046ef564e856c3564244337b00bc284707744d0595d8ced0842e19e409",
        "covers": ("2023-01-03", "2026-08-17"),
        "roster_basis": ROSTER_BASIS_BULK_HISTORICAL,
    },
    "股價0817-0828.zip": {
        "leg": "2019+",
        "raw_sha256":
            "c8aad1da263300838a8eb6817f5b20d72e7f55fa20cd992cdb7500447741d2f0",
        "covers": ("2026-08-18", "2026-08-28"),
        "roster_basis": ROSTER_BASIS_CURRENT_SNAPSHOT,
        "declared_properties": {"delisted_coverage": ROSTER_SNAPSHOT_LIMITATION},
    },
}

CONSUMED_ARCHIVES = tuple(CONSUMED_ARCHIVE_DECLARATIONS)

# Derived from the declarations, so the family-level statement cannot drift from
# the per-archive one. D1-6's `includes_delisted` is a property of the COMPOSED
# corpus and is not restated here — restating it would be a second place to
# update and one place to forget. What is stated is which archives can and
# cannot be cited toward it.
DELISTED_COVERAGE_POLICY = {
    "rule": "ROSTER_BASIS_IS_DECLARED_PER_ARCHIVE",
    "detail": (
        "an archive queried as 'the last N sessions' carries the roster that "
        "exists at query time; nothing that left the exchange before then can "
        "appear in it, at any session count. Same eleven columns, same real "
        "prices, different fact — and the difference does not raise."),
    "roster_basis_by_archive": {
        name: d["roster_basis"]
        for name, d in sorted(CONSUMED_ARCHIVE_DECLARATIONS.items())},
    "may_not_be_cited_toward_includes_delisted": sorted(
        name for name, d in CONSUMED_ARCHIVE_DECLARATIONS.items()
        if d["roster_basis"] == ROSTER_BASIS_CURRENT_SNAPSHOT),
    "declared_limitations": {
        name: d["declared_properties"]["delisted_coverage"]
        for name, d in sorted(CONSUMED_ARCHIVE_DECLARATIONS.items())
        if d.get("declared_properties", {}).get("delisted_coverage")},
    "d1_6_gate_owner": "core.b0_price_universe.assert_price_source_admissible",
}

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


# ⚠ `export_vintage` USED TO BE A TERNARY, AND BOTH BRANCHES WERE GUESSES.
#
#     "export_vintage": "2026-08-18" if consumed else "2026-08-06"
#
# The folder is named 0806, the two big archives were repacked on 2026-08-18, and
# the ternary encoded that coincidence as a rule. The moment a THIRD archive is
# consumed it inherits 2026-08-18 — 股價0817-0828.zip was packed 2026-08-30, so
# the stamp would have been 12 days wrong on the first day and wronger on every
# later one. The `else` branch was no better: 23 of the 24 workbooks were exported
# 2026-07-14/15, not 2026-08-06.
#
# A vintage is a fact about a file, so it is read off that file:
#
#   .zip   the archive's own member timestamps. They are inside the bytes the
#          entry already hashes, so the stamp is clone-stable by construction and
#          cannot drift from `raw_sha256`.
#   .xlsx  a workbook carries no packing stamp this module can read without
#          opening it, and `os.path.getmtime` is a property of THIS clone's
#          filesystem, not of the export. The capture manifest recorded each
#          workbook's mtime at harvest time, in the repository, keyed by content
#          hash — so the lookup is content-addressed and survives a rename, a
#          re-copy, or the 0806/0817 directory-name drift. A workbook whose bytes
#          that record does not know ABORTS BY NAME rather than being guessed at.
WORKBOOK_VINTAGE_MANIFEST = os.path.join("tej_exports",
                                         "DataExport0806_manifest.csv")

_WORKBOOK_VINTAGES: dict = {}


def _workbook_vintages() -> dict:
    """content sha256 -> recorded export date, from the in-repo capture manifest."""
    if not _WORKBOOK_VINTAGES:
        import csv

        path = os.path.join(REPO, WORKBOOK_VINTAGE_MANIFEST)
        if not os.path.isfile(path):
            raise ManifestError(
                "abort: the capture manifest %s is absent, so no workbook in the "
                "prices landing directory can be given an export vintage that is "
                "a recorded fact rather than a guess."
                % WORKBOOK_VINTAGE_MANIFEST)
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                sha = str(row.get("sha256", "")).strip().lower()
                stamp = str(row.get("mtime_utc", "")).strip()
                if sha and stamp:
                    _WORKBOOK_VINTAGES[sha] = stamp[:10]
    return _WORKBOOK_VINTAGES


def _zip_export_vintage(path: str) -> str:
    """The archive's own packing date, from its member timestamps."""
    with zipfile.ZipFile(path) as z:
        stamps = [i.date_time for i in z.infolist()]
    if not stamps:
        raise ManifestError(
            "abort: %s holds no members, so it carries no packing date and its "
            "export vintage cannot be established." % os.path.basename(path))
    y, m, d = max(stamps)[:3]
    return "%04d-%02d-%02d" % (y, m, d)


def export_vintage(path: str, fmt: str, raw_sha256: str) -> str:
    """Per-archive vintage, derived from the file — never from a branch."""
    if fmt == "zip":
        return _zip_export_vintage(path)
    stamp = _workbook_vintages().get(str(raw_sha256).lower())
    if not stamp:
        raise ManifestError(
            "abort: %s (sha %s) is present in the prices landing directory but "
            "its bytes are not recorded in %s, so its export vintage is not a "
            "known fact. Record it there rather than letting the leaf stamp a "
            "guess." % (os.path.basename(path), str(raw_sha256)[:12],
                        WORKBOOK_VINTAGE_MANIFEST))
    return stamp


def _members(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        return [{"name": i.filename, "size": int(i.file_size),
                 "crc32": "%08x" % i.CRC} for i in sorted(
                     z.infolist(), key=lambda i: i.filename)]


def _stamped_declaration(path: str, argument: str) -> str:
    """Normalise a CALLER-SUPPLIED declared landing path for the leaf doc.

    ⚠ `landing_directory` lives inside the leaf `doc`, so it is inside
    `_verify_self_hash` — it is part of the leaf's payload sha256, which is part
    of the aggregate's, which is part of `SourceAttestation.provenance_sha256`.
    A machine-absolute value therefore makes the SAME source bytes hash
    differently in every clone, silently: no error and no version signal. The
    A01 floor-capture evidence was produced in a different clone
    (`C:\\dev\\pj1_capture`), and the contract requires a later attempt to
    compare its source hashes against A01's, so a clone-dependent stamp turns a
    confirmation into a disagreement nobody can explain.

    A declared path is therefore stored repo-relative with forward slashes. An
    absolute path INSIDE the repo is relativised — deterministic and lossless,
    and the readers already re-join a relative landing to their own REPO
    (`l3_readers._leaf_and_landing`, `assert_landing_dir_matches`). An absolute
    path OUTSIDE the repo cannot be made portable at all, so it ABORTS rather
    than being silently relativised or silently stamped.

    Twin of `build_flat_leaves._stamped_declaration`; each stamps against its
    own module's REPO.
    """
    if not os.path.isabs(path):
        return path.replace("\\", "/")
    rel = os.path.relpath(os.path.abspath(path), REPO)
    if (rel == os.pardir or rel.startswith(os.pardir + os.sep)
            or os.path.isabs(rel)):
        raise ManifestError(
            "abort: %s=%r is an absolute path outside the repository (%s). The "
            "declared landing directory is stamped into the leaf payload hash, "
            "so a path that exists only on this machine makes the same source "
            "bytes hash differently in every clone. Declare a repo-relative "
            "path." % (argument, path, REPO))
    return rel.replace("\\", "/")


def build(run_id: str, as_of: str, landing_dir: str = "",
          pre_2019_dir: str = "", declared_landing_dir: str = "",
          declared_pre_2019_dir: str = "", observed_at: str = "") -> dict:
    # A `declared_*` argument means "READ the staged directory, DECLARE this
    # one". Without its staged read there is nothing for it to stand in for, and
    # an argument the callee ignores is a decision input the caller believes it
    # supplied (`run_l3_prospective.py:501-508`). Refused BY NAME, not dropped.
    if declared_landing_dir and not landing_dir:
        raise ManifestError(
            "abort: declared_landing_dir=%r was supplied without landing_dir. "
            "It only means anything when the 2019+ archives are read from a "
            "stand-in directory; on its own it would be silently dropped."
            % declared_landing_dir)
    if declared_pre_2019_dir and not pre_2019_dir:
        raise ManifestError(
            "abort: declared_pre_2019_dir=%r was supplied without "
            "pre_2019_dir. It only means anything when the pre-2019 cache is "
            "read from a stand-in directory; on its own it would silently "
            "redeclare the real cache." % declared_pre_2019_dir)
    landing = landing_dir or os.path.join(REPO, LANDING_DIRECTORY)
    if not os.path.isdir(landing):
        raise ManifestError("abort: prices landing directory not found: %s"
                            % landing)
    observed_at = observed_at or _dt.datetime.now().astimezone().isoformat(
        timespec="seconds")

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
        declaration = CONSUMED_ARCHIVE_DECLARATIONS.get(name)
        consumed = declaration is not None
        fmt = "zip" if name.lower().endswith(".zip") else "xlsx"
        raw = file_sha256(p)
        # A declared archive is declared BY ITS BYTES. Same name, different
        # bytes is a different source, and it is the case a name-only inventory
        # would wave through.
        if consumed and raw != declaration["raw_sha256"]:
            raise ManifestError(
                "abort: %s hashes to %s but the declared inventory names %s for "
                "that locator. An archive replaced in place is a new source, not "
                "an updated one; declare the new bytes rather than reading them "
                "under the old declaration. file: %s"
                % (name, raw[:16], declaration["raw_sha256"][:16], p))
        entry = {
            "locator": name,
            "format": fmt,
            "raw_sha256": raw,
            "export_vintage": export_vintage(p, fmt, raw),
            "observed_at": observed_at,
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed" if consumed else "not_consumed",
            "leg": declaration["leg"] if consumed else None,
        }
        if consumed:
            # MEASURED span and DECLARED roster basis travel with the entry. The
            # filename is not evidence of either: 股價0817-0828.zip covers
            # 2026-08-18 .. 2026-08-28 and does not contain 2026-08-17.
            entry["covers"] = list(declaration["covers"])
            entry["roster_basis"] = declaration["roster_basis"]
            if declaration.get("declared_properties"):
                entry["declared_properties"] = dict(
                    declaration["declared_properties"])
        else:
            entry["not_consumed_reason"] = NOT_CONSUMED_REASON
        if fmt == "zip":
            entry["members"] = _members(p)
        entries.append(entry)

    entries += _pre_2019_entries(
        observed_at, pre_2019_dir,
        declared_directory=declared_pre_2019_dir)

    # With no stand-in read, the stamp is this module's OWN declared constant —
    # never `os.path.join(REPO, ...)`. The constant is the contract, it is the
    # value A01's evidence carries, and it is the only form that survives a
    # different clone root.
    if not landing_dir:
        declared_landing = LANDING_DIRECTORY.replace("\\", "/")
    elif declared_landing_dir:
        declared_landing = _stamped_declaration(
            declared_landing_dir, "declared_landing_dir")
    else:
        # A staged read with nothing declared over it: the staging path IS the
        # declaration. That is the validation pass, whose leaves must point at
        # the snapshot the readers are about to open; throwaway and deliberately
        # not portable.
        declared_landing = landing.replace("\\", "/")

    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=declared_landing,
        accepted_extensions=ENUMERATED_EXTENSIONS,
        policies={
            "sentinel_zero": SENTINEL_ZERO_POLICY,
            "unit_authority": UNIT_AUTHORITY,
            "population_authority": POPULATION_AUTHORITY,
            "quarantined_era": QUARANTINED_ERA_POLICY,
            "leg_unit_conventions": LEG_UNIT_CONVENTIONS,
            # Named at leaf level as well as on the entry it constrains: a
            # reader who looks at the family's policies must not have to open
            # every archive entry to learn that one of the 2019+ archives
            # cannot evidence delisted coverage.
            "delisted_coverage": DELISTED_COVERAGE_POLICY,
        })


def _pre_2019_entries(observed_at: str, payload_dir: str = "",
                      declared_directory: str = "") -> list:
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

    # Same rule as the leaf's own landing: a caller's DECLARATION is normalised
    # so it is clone-stable, while a stand-in READ directory with nothing
    # declared over it is stamped as-is (the throwaway validation pass). The
    # default is this module's own constant, which is home-absolute by design —
    # the pre-2019 cache lives outside the repo.
    if declared_directory:
        landing = _stamped_declaration(declared_directory,
                                       "declared_pre_2019_dir")
    else:
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
