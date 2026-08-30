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

5 · A DECLARED SPAN IS A MEASUREMENT, AND A MEASUREMENT DECAYS INTO A CONSTANT
    `covers` was measured by hand and written down. `raw_sha256` catches a
    REPACKED archive; it says nothing about an archive whose bytes are exactly
    what was declared and whose SPAN was declared wrong — and that is not
    hypothetical here, because the archive's own filename is wrong
    (股價0817-0828.zip covers 2026-08-18 .. 08-28). The span is what the leaf
    PUBLISHES as the archive's coverage, so it is re-measured from the archive's
    rows at build time (`assert_declared_span`) rather than trusted.

6 · THE DECLARED SET AND THE SEALED CONTRACT ARE TWO DIFFERENT LISTS
    `build_price_panel.assert_reads_the_sealed_source` recomputes the composed
    fingerprint from `data/b0/price_2019plus_new.parquet` — a SEALED ARTEFACT,
    not from the archives. So declaring a third archive here moved the read set
    and left that gate reporting a match: measured 2026-08-30, the declared set
    was three archives spanning to 2026-08-28 while the sealed contract named
    two and stopped at 2026-08-17, and the fingerprint gate passed.

    It was harmless only because `panel_span()` clips at 2026-04-01 and the new
    archive contributes no rows — a fact about a FROZEN WINDOW that a future
    `window_end` change silently invalidates. So it is checked, not assumed:
    `reconcile_declarations_with_sealed_contract` compares the two lists every
    build, and an archive reaching past the contract must carry a named
    allowance keyed to the exact sealed fingerprint it diverges from, whose
    stated reason is re-verified against the panel end on every build.

    python research/b0_materializer/build_prices_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import io
import json
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

# --- S-9 · the declared span is RE-MEASURED, never trusted ----------------------
#
# ⚠ `raw_sha256` AND `covers` FAIL DIFFERENTLY, AND ONLY ONE OF THEM WAS CHECKED.
#
# A repacked archive changes its bytes, so the hash names it. An archive whose
# bytes are exactly what was declared and whose SPAN was written down wrong is
# invisible to the hash — and `covers` is not commentary: it is what this leaf
# publishes as the archive's coverage, and `build_price_panel` copies it into
# the panel receipt as `from_2019_declared_inventory`.
#
# The precedent is in this very directory: 股價0817-0828.zip is NAMED for 0817
# and does not contain 2026-08-17. A hand-measured constant that nothing
# re-measures is the same shape as the filename, one indirection later.
#
# So the span is re-derived from the archive's own rows. Cost, measured rather
# than assumed (2026-08-31, this clone):
#
#     股價 2019-2022.zip       1,785,993 rows   286 MB decompressed   2.9 s
#     股價2023-20260817.zip    1,684,634 rows   273 MB decompressed   2.8 s
#     股價0817-0828.zip           17,586 rows   2.8 MB decompressed   0.03 s
#
# ~5.7 s for the whole declared set, against ~1.4 s for the rest of the build.
# That is paid ONCE PER PROCESS, memoised on `raw_sha256` — and the key is not a
# promise: `build()` re-hashes every archive from its bytes and asserts it
# against the declaration BEFORE the lookup, so a cache hit is a hit on bytes
# just proven identical. Nothing is persisted, so nothing is trusted across
# runs and there is no ledger to hand-edit.
ARCHIVE_DATE_COLUMN = "年月日"
ARCHIVE_TEXT_ENCODING = "utf-16"
ARCHIVE_DELIMITER = "\t"

DECLARED_SPAN_VERIFICATION = {
    "rule": "DECLARED_COVERS_IS_RE_MEASURED_FROM_THE_ARCHIVE_ROWS_EVERY_BUILD",
    "method": (
        "stream every member of every declared archive, take min and max of the "
        "%s column by NAME (not by position), and require exact equality with "
        "both ends of the declared span" % ARCHIVE_DATE_COLUMN),
    "memoised_on": "raw_sha256",
    "memo_is_sound_because": (
        "the archive is re-hashed from its bytes and asserted against the "
        "declaration before the memo is consulted, so a hit is a hit on bytes "
        "proven identical in this same build. The memo is process-local and "
        "never written to disk."),
    "catches": [
        "a span declared wrong at either end while the bytes are exactly what "
        "was declared — the case raw_sha256 cannot see",
        "a span taken from the filename rather than from the contents",
        "a member added to the archive whose rows fall outside the declared span",
        "a date field that is neither YYYYMMDD nor YYYY-MM-DD, and a row whose "
        "field count disagrees with its own header",
    ],
    "does_not_catch": [
        "sessions MISSING inside a correctly declared span — this is a span "
        "check, not a completeness check; the calendar/coverage question belongs "
        "to core.b0_price_universe and the D-1 audit",
        "securities missing from the roster (that is roster_basis, declared "
        "separately, and D1-6)",
        "a wrong `leg` or `roster_basis` — neither is derivable from the rows",
        "values: prices and volumes are not re-verified here",
    ],
}

_SPAN_CACHE: dict = {}


def _iso_day(value: str, where: str) -> str:
    """`20260818` or `2026-08-18` -> `2026-08-18`. Anything else aborts.

    Both forms occur: TEJ writes 年月日 as YYYYMMDD, and the readers parse it
    with `pd.to_datetime`, which also accepts the dashed form. Guessing at a
    third form is how a misparse becomes a span.
    """
    v = str(value).strip()
    if len(v) == 8 and v.isdigit():
        return "%s-%s-%s" % (v[:4], v[4:6], v[6:])
    if (len(v) == 10 and v[4] == "-" and v[7] == "-"
            and v[:4].isdigit() and v[5:7].isdigit() and v[8:].isdigit()):
        return v
    raise ManifestError(
        "abort: %s carries the date field %r, which is neither YYYYMMDD nor "
        "YYYY-MM-DD. A date this module cannot read is not a span it may "
        "publish." % (where, value))


def observed_archive_span(path: str, raw_sha256: str) -> dict:
    """Re-measure (min, max, rows) over EVERY row of EVERY member.

    Every member, not `namelist()[0]`: a second member is not visible in the
    span unless it is read, and the declaration speaks for the whole archive.
    """
    key = str(raw_sha256).lower()
    if key in _SPAN_CACHE:
        return dict(_SPAN_CACHE[key])

    lo = hi = None
    rows = 0
    members = []
    with zipfile.ZipFile(path) as z:
        infos = sorted(z.infolist(), key=lambda i: i.filename)
        for info in infos:
            if info.is_dir():
                continue
            members.append(info.filename)
            with z.open(info) as fh:
                text = io.TextIOWrapper(fh, encoding=ARCHIVE_TEXT_ENCODING,
                                        newline="")
                header = text.readline().rstrip("\r\n").split(ARCHIVE_DELIMITER)
                if ARCHIVE_DATE_COLUMN not in header:
                    raise ManifestError(
                        "abort: member %s of %s has no %s column (header: %s). "
                        "The date column is located by NAME because a reordered "
                        "export would otherwise shift the span silently."
                        % (info.filename, os.path.basename(path),
                           ARCHIVE_DATE_COLUMN, header))
                idx = header.index(ARCHIVE_DATE_COLUMN)
                width = len(header)
                for lineno, line in enumerate(text, start=2):
                    line = line.rstrip("\r\n")
                    if not line:
                        continue
                    fields = line.split(ARCHIVE_DELIMITER)
                    if len(fields) != width:
                        raise ManifestError(
                            "abort: %s member %s line %d has %d field(s) against "
                            "a %d-column header. A row this module cannot align "
                            "is not a row it may take a date from."
                            % (os.path.basename(path), info.filename, lineno,
                               len(fields), width))
                    day = _iso_day(fields[idx], "%s member %s line %d"
                                   % (os.path.basename(path), info.filename,
                                      lineno))
                    rows += 1
                    if lo is None or day < lo:
                        lo = day
                    if hi is None or day > hi:
                        hi = day
    if not rows:
        raise ManifestError(
            "abort: %s holds no data rows, so it evidences no span at all. An "
            "empty archive is not a zero-length coverage claim."
            % os.path.basename(path))
    observed = {"observed_covers": [lo, hi], "rows": rows,
                "members_read": members}
    _SPAN_CACHE[key] = observed
    return dict(observed)


def assert_declared_span(path: str, locator: str, raw_sha256: str,
                         declarations: dict = None) -> dict:
    """The declared `covers` must equal the span the archive actually holds."""
    declarations = (CONSUMED_ARCHIVE_DECLARATIONS if declarations is None
                    else declarations)
    declared = list(declarations[locator]["covers"])
    observed = observed_archive_span(path, raw_sha256)
    if observed["observed_covers"] != declared:
        raise ManifestError(
            "abort: %s declares covers %s but its %d rows span %s. `covers` is "
            "what this leaf PUBLISHES as the archive's coverage, and the bytes "
            "match the declaration — so this is a mis-declared span, exactly "
            "the failure raw_sha256 cannot see. Declare the measured span (the "
            "filename is not evidence: 股價0817-0828.zip is named 0817 and "
            "starts on 2026-08-18). file: %s"
            % (locator, declared, observed["rows"],
               observed["observed_covers"], path))
    observed["declared_covers"] = declared
    observed["verified_against"] = "archive rows, this build"
    return observed


def verify_declared_spans(landing_dir: str = "",
                          declarations: dict = None) -> dict:
    """Every declared archive's span, re-measured. Used by the panel builder."""
    declarations = (CONSUMED_ARCHIVE_DECLARATIONS if declarations is None
                    else declarations)
    landing = landing_dir or os.path.join(REPO, LANDING_DIRECTORY)
    out = {}
    for locator in sorted(declarations):
        path = os.path.join(landing, locator)
        if not os.path.isfile(path):
            raise ManifestError(
                "abort: declared price archive %s is absent from %s, so its "
                "declared span cannot be verified." % (locator, landing))
        raw = file_sha256(path)
        if raw != declarations[locator]["raw_sha256"]:
            raise ManifestError(
                "abort: %s hashes to %s but the declared inventory names %s. "
                "The span may not be verified under a declaration that does not "
                "own these bytes." % (locator, raw[:16],
                                      declarations[locator]["raw_sha256"][:16]))
        out[locator] = assert_declared_span(path, locator, raw, declarations)
    return out


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

# --- S-8 · the declared set vs the SEALED contract ------------------------------
#
# ⚠ THE FINGERPRINT GATE CANNOT SEE THIS, BY CONSTRUCTION.
#
# `build_price_panel.assert_reads_the_sealed_source` recomputes the composed
# manifest with `rebuild_audit_new_source.coverage("new")`, which reads
# `data/b0/price_2019plus_new.parquet` — a SEALED ARTEFACT whose rows stop at
# 2026-08-17. It never opens the archives. So declaring a third archive changed
# the set this module reads and left that gate reporting a match. Measured
# 2026-08-30, both true at once:
#
#     declared archives  3, spanning ... 2026-08-28
#     sealed contract    b0_price_universe_20260817, upstream_zips = 2 names,
#                        date_max 2026-08-17, securities 2306,
#                        content_sha256 2646356f406a585c…
#     gate               PASSED, recomputed sha == 2646356f406a585c…
#
# It carried no rows only because `panel_span()` ends at 2026-04-01, which is
# before the new archive's first session. That is a fact about the FROZEN
# WINDOW, not about the sources — move `window_end` past 2026-04 and the panel
# starts carrying rows the sealed contract does not describe, with the same gate
# still reporting a match.
#
# The two lists are therefore reconciled directly, and "the panel clips it away"
# is the one thing that may NOT be assumed: it is re-checked against the panel's
# own end every build.
SEALED_PRICE_CONTRACT_JSON = os.path.join(
    "research", "d1_price_universe", "price_source_contract.json")

# The panel end is derived HERE rather than in `build_price_panel`, which now
# calls this: the allowance below is only valid while the clip holds, so the
# clip and the allowance must not be able to drift apart, and this module is
# inside `FLOOR_CAPTURE_CODE_CLOSURE` while a second copy of the rule would not
# be bound by anything.
FROZEN_TRADING_CALENDAR = os.path.join("data", "b0", "trading_calendar.csv")

# The only condition under which a declared archive may reach past the sealed
# contract. A CLOSED vocabulary with one member: an allowance naming any other
# condition aborts, so a future allowance cannot be granted by inventing a
# reason in prose.
ALLOWANCE_CONDITION_PANEL_CLIPS = (
    "PANEL_END_IS_STRICTLY_BEFORE_THE_ARCHIVES_FIRST_COVERED_SESSION")

# --- WHOSE clip? ----------------------------------------------------------------
#
# ⚠ A CLIP-BASED ALLOWANCE IS A STATEMENT ABOUT A READER, NOT ABOUT AN ARCHIVE.
#
# The condition above WAS re-verified every build — against `panel_end_session()`,
# which is the L2 composed panel's end and nothing else. The L2 panel is not the
# only consumer of this leaf:
#
#   L2 composed price panel   `build_price_panel.panel_span()` ends at
#                             `panel_end_session()` = the first session after the
#                             FROZEN `window_end`, 2026-04-01. Derivable HERE,
#                             from frozen inputs.
#   L3 prospective route      `l3_assemble._assemble` calls
#                             `l3_readers.read_prices(run_dir, SOURCE_DEPTH_PROBE,
#                             price_span[1])`, and §19.2 fixes `price_span[1]` as
#                             the period's EXECUTION session. That route never
#                             inherits `window_end` at all.
#
# Measured for Month 1 (U-2: decision 2026-09-30, execution 2026-10-01): the L3
# read end is 2026-10-01, so ALL 17,586 rows of 股價0817-0828.zip (1,954
# securities x 9 sessions, 2026-08-18 .. 08-28) enter the decision input, while
# the same archive contributes 0 rows to the L2 panel. Both are true at once —
# and the allowance's stated reason was only ever checked against the second.
# "The clip is checked, not assumed" was true of the CHECK and false of the
# consumer at risk.
#
# This is not a Month-1 accident. `run_l3_prospective._assert_intent_claim_is_today`
# forces a prospective decision date to be TODAY in Asia/Taipei and §19.2 puts the
# read end at the execution session after it, so on the L3 route the read end is
# bounded BELOW by the day the run happens. An archive of sessions that have
# already occurred can therefore NEVER satisfy `read_end < covers[0]` there. The
# clip condition is not merely false for L3 today; it is unsatisfiable on that
# route, permanently.
#
# So an allowance is granted TO NAMED CONSUMERS. A consumer whose read end this
# module cannot derive may not be named on a clip-based allowance at all —
# "checked" would otherwise mean "checked against a value that was never
# computed", which is the defect rather than a fix for it. The consumers an
# allowance is NOT granted to are recorded by name and travel in the leaf, and
# `run_l3_prospective` refuses to run a period whose declared source set names
# this route among them.
CONSUMER_L2_PANEL = "L2_COMPOSED_PRICE_PANEL"
CONSUMER_L3_PROSPECTIVE = "L3_PROSPECTIVE_ROUTE"

LEAF_CONSUMERS = {
    CONSUMER_L2_PANEL: {
        "reads_through": "build_price_panel.panel_span()[1]",
        "read_end_derivation": "FIRST_SESSION_AFTER_THE_FROZEN_WINDOW_END",
        "read_end_is_derivable_here": True,
        "derived_by": "build_prices_leaf.panel_end_session",
    },
    CONSUMER_L3_PROSPECTIVE: {
        "reads_through":
            "l3_readers.read_prices(run_dir, SOURCE_DEPTH_PROBE, price_span[1])",
        "read_end_derivation": "EXECUTION_SESSION_OF_THE_DECISION_PERIOD",
        "read_end_is_derivable_here": False,
        "derived_by": "core.b0_l3_price_span.price_span, once per run",
        "why_not_derivable_here": (
            "the endpoint is the period's execution session (§19.2), which "
            "belongs to a run this module knows nothing about. It is bounded "
            "BELOW by that run's own decision date — a prospective intent may be "
            "claimed only on today's Asia/Taipei date — so on this route "
            "`read_end < covers[0]` is unsatisfiable for any archive of sessions "
            "that have already happened, not merely false today. A consumer like "
            "this is refused at ITS OWN gate; it is never allowed here."),
    },
}

CONSUMER_SCOPED_ALLOWANCE_RULE = {
    "rule": "AN_ALLOWANCE_IS_GRANTED_TO_NAMED_CONSUMERS_NEVER_TO_THE_LEAF",
    "why": (
        "the one allowance condition is a predicate over a READER's end, and "
        "this leaf has consumers that stop in different places. Verified "
        "against one and relied on by another, an allowance records 'checked' "
        "about a consumer that was never checked — measured: the L2 panel takes "
        "0 rows from 股價0817-0828.zip while the L3 prospective route takes all "
        "17,586 of them for Month 1."),
    "hard_aborts": [
        "an allowance naming no consumer",
        "an allowance naming a consumer outside LEAF_CONSUMERS",
        "an allowance naming a consumer whose read end is not derivable here",
        "an allowance that neither grants nor explains a declared consumer",
    ],
    "consumers": sorted(LEAF_CONSUMERS),
    "denied_consumers_are_gated_by": (
        "the consumer itself. This module publishes the refusal; the L3 route "
        "enforces it in run_l3_prospective.assert_declared_sources_admit_this_route."),
}

DIVERGENCE_NOT_IN_CONTRACT = "NOT_NAMED_BY_THE_SEALED_CONTRACT"
DIVERGENCE_BEYOND_DATE_MAX = "COVERAGE_ENDS_AFTER_THE_CONTRACT_DATE_MAX"

# ⚠ AN ALLOWANCE IS KEYED TO THE EXACT SEALED FINGERPRINT IT DIVERGES FROM.
#
# Not to the contract's NAME: `register_price_source.py` hard-codes
# `b0_price_universe_20260817`, so a re-registration that recomposes the corpus
# keeps the name and would let a stale allowance survive the very event it must
# not survive. Keying on `content_sha256` means re-registering the source voids
# every allowance written against the old one and forces re-adjudication — and
# it means granting one requires pasting a 64-hex sealed fingerprint next to an
# exact filename, which is not something that happens by accident.
#
# The bytes of the archive itself are NOT part of this key: they are already
# gated, twice and unconditionally, by the `raw_sha256` comparison in `build()`
# and in `build_price_panel.declared_zip_inventory`. Putting them here would add
# no gate and would make the key untestable against a substituted source
# surface.
ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES = {
    ("股價0817-0828.zip",
     "2646356f406a585c53954430eb5ad2967ddebc5c20ef12ea51f4333009d63549"): {
        "sealed_contract_name": "b0_price_universe_20260817",
        "condition": ALLOWANCE_CONDITION_PANEL_CLIPS,
        # WHO this is granted to. The clip is a fact about the L2 panel's end,
        # so it is granted to the L2 panel and to nothing else. The L3 route is
        # refused BY NAME below rather than inheriting a permission earned by a
        # reader that stops four months earlier.
        "granted_to_consumers": (CONSUMER_L2_PANEL,),
        "not_granted_to_consumers_because": {
            CONSUMER_L3_PROSPECTIVE: (
                "the L3 route reads [lineage_price_floor, execution_session] and "
                "never inherits `window_end`. For Month 1 (U-2: decision "
                "2026-09-30, execution 2026-10-01) it reads through 2026-10-01 "
                "and therefore takes all 17,586 rows of this archive — the "
                "clip that the allowance rests on does not exist on that route, "
                "and cannot: §19.2's endpoint is bounded below by the run's own "
                "decision date. The archive is ROSTER_SNAPSHOT_DERIVED, so a "
                "decision taken over it stands on rows whose survivorship "
                "properties are outside what D-1 verified and B-21 sealed. "
                "Resolving that means recomposing the corpus and re-registering "
                "the contract under data/b0/, which R-W1-1 freezes — so the L3 "
                "route ABORTS on this archive (§7, A-8) instead of reading it "
                "under an allowance earned by a different reader."),
        },
        "granted_because": (
            "the archive covers 2026-08-18 .. 2026-08-28 and the sealed "
            "contract stops at 2026-08-17, so it is declared and read while "
            "standing outside what D-1 verified and B-21 sealed. Every session "
            "it carries is after the panel's end, so it contributes no row to "
            "any composed panel — which is a fact about the frozen window, not "
            "about the archive, and is therefore re-checked here every build "
            "rather than restated."),
        "why_the_contract_was_not_reissued": (
            "resolving this properly means recomposing the corpus and "
            "re-registering the contract, which regenerates "
            "data/b0/price_2019plus_new.parquet and the D-1 audit artefacts. "
            "data/b0/ is frozen by ruling R-W1-1, so that is not available "
            "here. The divergence is therefore made DETECTABLE and bounded "
            "instead of resolved; §7 and A-8 own the re-adjudication."),
        "what_invalidates_it": (
            "any `window_end` that moves the panel end to 2026-08-18 or later, "
            "and any re-registration of the price source (which changes "
            "content_sha256 and voids this key). Both abort rather than "
            "degrade."),
    },
}

SEALED_SOURCE_RECONCILIATION_RULE = {
    "rule": "THE_DECLARED_ARCHIVE_SET_MUST_RECONCILE_WITH_THE_SEALED_CONTRACT",
    "why_the_fingerprint_gate_is_not_this_gate": (
        "build_price_panel.assert_reads_the_sealed_source recomputes the "
        "composed fingerprint from data/b0/price_2019plus_new.parquet, a sealed "
        "artefact that stops at the contract's date_max. It never opens the "
        "archives, so an archive added beside it changes what is READ without "
        "changing what that gate MEASURES. Both gates are needed; neither "
        "substitutes for the other."),
    "hard_aborts": [
        "a declared archive the contract names, whose declared bytes differ "
        "from the bytes the contract recorded",
        "an archive the contract names that is not declared here",
        "a divergence with no allowance keyed to this exact sealed fingerprint",
        "an allowance whose condition is not in the closed vocabulary",
        "an allowance whose stated condition no longer holds",
        "an allowance for this fingerprint that no longer describes a "
        "divergence — a spent allowance is removed, not left lying about",
        "an allowance that does not name the consumers it is granted to, names "
        "one outside the closed set, names one whose read end is not derivable "
        "here, or leaves a declared consumer unaddressed",
    ],
    "allowance_conditions": [ALLOWANCE_CONDITION_PANEL_CLIPS],
    "allowance_key": "(archive locator, sealed contract content_sha256)",
    "allowance_scope": CONSUMER_SCOPED_ALLOWANCE_RULE["rule"],
}


def panel_end_session() -> str:
    """The last session a composed panel may carry: the first after window_end.

    §6.5 executes at the OPEN of the session following the decision date, and
    nothing beyond it is reachable by B0. Owned here and consumed by
    `build_price_panel.panel_span`, so the clip that an allowance depends on has
    exactly one definition.
    """
    import csv

    from core.b0_master_prereg import spec as frozen_spec

    end = str(frozen_spec("window_end"))
    path = os.path.join(REPO, FROZEN_TRADING_CALENDAR)
    if not os.path.isfile(path):
        raise ManifestError(
            "abort: the frozen trading calendar %s is absent, so the panel end "
            "cannot be established. It is not optional: an allowance whose "
            "reason is 'the panel clips this away' is void if the clip cannot "
            "be measured." % FROZEN_TRADING_CALENDAR)
    with open(path, encoding="utf-8") as fh:
        after = sorted(r["session"] for r in csv.DictReader(fh)
                       if str(r["session"]) > end)
    if not after:
        raise ManifestError(
            "abort: the calendar has no session after window_end %s, so the "
            "§6.5 execution session of the final decision month does not exist"
            % end)
    return after[0]


def sealed_contract_payload(path: str = "") -> dict:
    """The registered D1-7 contract document. One path, shared with the panel."""
    p = path or os.path.join(REPO, SEALED_PRICE_CONTRACT_JSON)
    if not os.path.isfile(p):
        raise ManifestError(
            "abort: the sealed price source contract %s is absent. The declared "
            "archive set cannot be reconciled against a contract that is not "
            "there, and an unreconciled set is exactly the silent divergence "
            "this check exists for." % SEALED_PRICE_CONTRACT_JSON)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _check_clip_holds_for_consumer(*, locator, covers, consumer, read_end,
                                   date_max):
    """The one allowance condition, checked — for ONE NAMED CONSUMER.

    The predicate is `read_end < covers[0]`, and `read_end` belongs to a reader.
    It is therefore taken from the consumer the allowance names, never from
    "the" panel end: the same archive is clipped away by one consumer of this
    leaf and read in full by another, so a clip verified without a consumer is
    a clip verified for whichever reader happened to be in the author's mind.
    """
    checks = {
        "consumer": consumer,
        "read_end": read_end,
        "read_end_derivation": LEAF_CONSUMERS[consumer]["read_end_derivation"],
        "archive_first_covered_session": covers[0],
        "contract_date_max": date_max,
        "read_end_before_archive_start": read_end < covers[0],
        "read_end_within_contract_date_max": read_end <= date_max,
    }
    if not checks["read_end_before_archive_start"]:
        raise ManifestError(
            "abort: the allowance for %s states that %s clips it away, and that "
            "is no longer true: that consumer's read end is %s, which is NOT "
            "before the archive's first covered session %s. It would carry rows "
            "the sealed contract (date_max %s) does not describe. This is the "
            "future edit the allowance was written to catch — re-register the "
            "price source or withdraw the archive; do not widen the allowance."
            % (locator, consumer, read_end, covers[0], date_max))
    if not checks["read_end_within_contract_date_max"]:
        raise ManifestError(
            "abort: %s reads through %s, which is after the sealed contract's "
            "date_max %s, so it reaches past what D-1 verified and B-21 sealed, "
            "whatever %s contributes." % (consumer, read_end, date_max, locator))
    return checks


def _allowance_consumers(locator: str, allowance: dict) -> tuple:
    """The consumers an allowance is granted to. Closed, checked, exhaustive."""
    raw = allowance.get("granted_to_consumers")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ManifestError(
            "abort: the allowance for %s names no consumer. Its condition (%s) "
            "is a predicate over a READER's end, and this leaf has %d readers "
            "(%s) that stop in different places. A leaf-wide allowance is the "
            "S-8 defect one level in: checked against one consumer and relied "
            "on by another."
            % (locator, ALLOWANCE_CONDITION_PANEL_CLIPS, len(LEAF_CONSUMERS),
               sorted(LEAF_CONSUMERS)))
    consumers = {str(c) for c in raw}
    unknown = sorted(consumers - set(LEAF_CONSUMERS))
    if unknown:
        raise ManifestError(
            "abort: the allowance for %s is granted to %s, which %s not in the "
            "declared consumer set %s. A consumer this module cannot describe "
            "is a consumer whose read end it cannot check."
            % (locator, unknown, "is" if len(unknown) == 1 else "are",
               sorted(LEAF_CONSUMERS)))
    undecidable = sorted(c for c in consumers
                         if not LEAF_CONSUMERS[c]["read_end_is_derivable_here"])
    if undecidable:
        raise ManifestError(
            "abort: the allowance for %s is granted to %s, whose read end is "
            "NOT derivable in this module.\n%s\nThe condition %s is verified as "
            "`read_end < covers[0]`, so granting it to such a consumer would "
            "record 'checked' beside a value that was never computed — which is "
            "the defect this scope exists to remove, not a fix for it. A "
            "consumer like that is refused at its own gate."
            % (locator, undecidable,
               "\n".join("  %s: %s" % (c, LEAF_CONSUMERS[c].get(
                   "why_not_derivable_here", "")) for c in undecidable),
               ALLOWANCE_CONDITION_PANEL_CLIPS))
    explained = set(allowance.get("not_granted_to_consumers_because") or {})
    unaddressed = sorted(set(LEAF_CONSUMERS) - consumers - explained)
    if unaddressed:
        raise ManifestError(
            "abort: the allowance for %s neither grants nor explains %s. Every "
            "declared consumer must be named on one side, so that a consumer "
            "added to this module forces every standing allowance to be "
            "re-adjudicated instead of inheriting a silence."
            % (locator, unaddressed))
    return tuple(sorted(consumers))


def reconcile_declarations_with_sealed_contract(
        payload: dict = None, panel_end: str = "",
        declarations: dict = None) -> dict:
    """Compare the declared archive inventory against the sealed contract.

    Returns the record that travels into the artefact. Raises on any divergence
    that is not covered by a named allowance whose condition still holds.
    """
    payload = sealed_contract_payload() if payload is None else payload
    declarations = (CONSUMED_ARCHIVE_DECLARATIONS if declarations is None
                    else declarations)
    contract = payload.get("contract") if isinstance(payload, dict) else None
    named_raw = payload.get("upstream_zips") if isinstance(payload, dict) else None
    if not isinstance(contract, dict) or not isinstance(named_raw, dict):
        raise ManifestError(
            "abort: the sealed price source contract document must carry a "
            "`contract` object and an `upstream_zips` map naming the archives "
            "it was composed from. Without both there is nothing to reconcile "
            "the declared set against, and 'nothing to compare' is how this "
            "divergence stayed silent.")
    name = str(contract.get("name", "")).strip()
    date_max = str(contract.get("date_max", "")).strip()
    fingerprint = str(contract.get("content_sha256", "")).strip().lower()
    if not (name and date_max and fingerprint):
        raise ManifestError(
            "abort: the sealed contract must declare name, date_max and "
            "content_sha256; got name=%r date_max=%r content_sha256=%r"
            % (name, date_max, fingerprint))
    named = {str(k): str(v).strip().lower() for k, v in named_raw.items()}

    panel_end = str(panel_end).strip() or panel_end_session()
    _iso_day(panel_end, "the panel end")
    # The read end of every consumer this module can derive one for. A consumer
    # absent from this map cannot hold a clip-based allowance, and
    # `_allowance_consumers` refuses to name it rather than defaulting it.
    read_ends = {CONSUMER_L2_PANEL: panel_end}
    underivable = sorted(c for c, d in LEAF_CONSUMERS.items()
                         if d["read_end_is_derivable_here"] and c not in read_ends)
    if underivable:
        raise ManifestError(
            "abort: %s %s declared read_end_is_derivable_here but this "
            "reconciliation produces no read end for %s. A consumer that claims "
            "a derivable end and is then not derived would be silently skipped "
            "on every allowance." % (underivable,
                                     "is" if len(underivable) == 1 else "are",
                                     "it" if len(underivable) == 1 else "them"))

    absent = sorted(n for n in named if n not in declarations)
    if absent:
        raise ManifestError(
            "abort: the sealed contract %s was composed from %s, which the "
            "declared archive inventory does not name. A source the contract "
            "stands on that this module does not read is a shorter panel "
            "wearing the sealed fingerprint." % (name, absent))

    divergences, aligned = {}, []
    for locator in sorted(declarations):
        d = declarations[locator]
        covers = [str(x) for x in d["covers"]]
        reasons = []
        if locator not in named:
            reasons.append(DIVERGENCE_NOT_IN_CONTRACT)
        elif named[locator] != str(d["raw_sha256"]).strip().lower():
            raise ManifestError(
                "abort: %s is named by the sealed contract %s with bytes %s, "
                "but the declared inventory names %s for the same locator. Same "
                "name, different bytes is a different source: the contract and "
                "the read set are not describing the same archive."
                % (locator, name, named[locator][:16],
                   str(d["raw_sha256"])[:16]))
        if covers[1] > date_max:
            reasons.append(DIVERGENCE_BEYOND_DATE_MAX)
        if reasons:
            divergences[locator] = {"reasons": reasons, "covers": covers}
        else:
            aligned.append(locator)

    granted = {}
    for locator in sorted(divergences):
        covers = divergences[locator]["covers"]
        allowance = ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES.get(
            (locator, fingerprint))
        if allowance is None:
            raise ManifestError(
                "abort: %s diverges from the sealed price source contract (%s) "
                "and no allowance is declared for it.\n"
                "  divergence      : %s\n"
                "  archive covers  : %s .. %s\n"
                "  contract name   : %s\n"
                "  contract date_max: %s\n"
                "  contract names  : %s\n"
                "  declared set    : %s\n"
                "The fingerprint gate cannot see this: it recomputes the "
                "composed manifest from a sealed artefact, not from these "
                "archives. Either re-register the price source so the contract "
                "describes what is read, or declare an allowance in "
                "build_prices_leaf.ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES "
                "keyed (%r, %r) with a condition from %s."
                % (locator, fingerprint[:16],
                   divergences[locator]["reasons"], covers[0], covers[1],
                   name, date_max, sorted(named), sorted(declarations),
                   locator, fingerprint,
                   [ALLOWANCE_CONDITION_PANEL_CLIPS]))
        condition = str(allowance.get("condition", ""))
        if condition != ALLOWANCE_CONDITION_PANEL_CLIPS:
            raise ManifestError(
                "abort: the allowance for %s names the condition %r, which is "
                "not one of %s. An allowance is granted by a condition this "
                "module CHECKS, never by a reason written in prose."
                % (locator, condition, [ALLOWANCE_CONDITION_PANEL_CLIPS]))
        consumers = _allowance_consumers(locator, allowance)
        granted[locator] = {
            "condition": condition,
            "granted_to_consumers": list(consumers),
            "denied_to_consumers": [c for c in sorted(LEAF_CONSUMERS)
                                    if c not in consumers],
            # One checked record PER GRANTED CONSUMER, against that consumer's
            # own read end. There is no consumer-free "checked".
            "checked": {
                consumer: _check_clip_holds_for_consumer(
                    locator=locator, covers=covers, consumer=consumer,
                    read_end=read_ends[consumer], date_max=date_max)
                for consumer in consumers},
            "not_granted_to_consumers_because": dict(
                allowance.get("not_granted_to_consumers_because") or {}),
            "reasons": divergences[locator]["reasons"],
            "covers": covers,
            "granted_because": allowance.get("granted_because", ""),
            "why_the_contract_was_not_reissued": allowance.get(
                "why_the_contract_was_not_reissued", ""),
            "what_invalidates_it": allowance.get("what_invalidates_it", ""),
        }

    # Fail-closed in the other direction too. An allowance written against THIS
    # sealed fingerprint that no longer describes a divergence has been spent —
    # left in place it becomes a standing permission nobody re-reads, which is
    # the shape this whole check exists to remove.
    spent = sorted(loc for (loc, fp) in ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES
                   if fp == fingerprint and loc not in divergences)
    if spent:
        raise ManifestError(
            "abort: allowance(s) %s are declared against the sealed contract %s "
            "but no longer describe a divergence. A spent allowance is removed, "
            "not left standing." % (spent, fingerprint[:16]))

    # The refusal list, published PER CONSUMER and covering every declared
    # consumer, including the ones with nothing refused. A consumer looks itself
    # up by name: absent from this map is not "nothing refused", it is "this
    # leaf does not know you", and the consumer's own gate treats that as an
    # abort rather than as permission.
    denied_by_consumer = {c: [] for c in sorted(LEAF_CONSUMERS)}
    for locator in sorted(granted):
        for consumer in granted[locator]["denied_to_consumers"]:
            denied_by_consumer[consumer].append(locator)

    return {
        "rule": SEALED_SOURCE_RECONCILIATION_RULE["rule"],
        "consumer_scope_rule": CONSUMER_SCOPED_ALLOWANCE_RULE,
        "leaf_consumers": sorted(LEAF_CONSUMERS),
        "archives_denied_to_consumer": denied_by_consumer,
        "sealed_contract_name": name,
        "sealed_contract_content_sha256": fingerprint,
        "sealed_contract_date_max": date_max,
        "sealed_contract_names_archives": sorted(named),
        "declared_archives": sorted(declarations),
        "reconciled_without_allowance": aligned,
        "divergences": {k: v["reasons"] for k, v in sorted(divergences.items())},
        "allowances_granted": granted,
        "panel_end_checked": panel_end,
        "why_the_fingerprint_gate_is_not_this_gate":
            SEALED_SOURCE_RECONCILIATION_RULE[
                "why_the_fingerprint_gate_is_not_this_gate"],
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
            #
            # S-9: and neither is the CONSTANT. `covers` is re-measured from the
            # archive's own rows before it is published, because the bytes
            # matching `raw_sha256` says nothing about whether the span written
            # beside them was measured correctly.
            entry["covers"] = list(declaration["covers"])
            entry["covers_verified"] = assert_declared_span(p, name, raw)
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

    # S-8. Not conditional on anything: the declared set and the sealed contract
    # are reconciled on EVERY build, and the record of that reconciliation —
    # including the checked clip that today's single allowance rests on — is
    # part of the leaf, so a reader cannot open the leaf without seeing which
    # archives stand outside the contract and on what condition.
    reconciliation = reconcile_declarations_with_sealed_contract()

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
            # What was re-measured rather than trusted, and what that does and
            # does not catch — beside the spans it certifies.
            "declared_span_verification": DECLARED_SPAN_VERIFICATION,
            # The declared set against the sealed contract, with every allowance
            # named, its condition checked, and the panel end it was checked
            # against recorded. A future `window_end` that voids the clip aborts
            # here rather than widening the panel quietly.
            "sealed_source_reconciliation": reconciliation,
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
