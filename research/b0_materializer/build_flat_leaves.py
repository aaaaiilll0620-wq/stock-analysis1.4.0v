# -*- coding: utf-8 -*-
"""W4 · the remaining dataset leaves, all of which land as flat directories.

`financials`, `prices` and `valuation` each needed their own producer because
each has a locator form of its own. The rest share one shape — a directory of
files, some consumed and some deliberately not — so they share one engine and
differ only by declaration.

The declaration is per family and explicit. `ENUMERATED_EXTENSIONS` is NOT a
global policy (that was rejected): each family names the extensions its own
landing surface actually holds, and every entry the enumeration finds is then
named `consumed` or `not_consumed` with a reason. A family whose upstream cannot
be established does not get a guessed one — see `corporate_actions`.

⚠ W1 measured that all six of these builders enumerate with a glob today, so
each is an O-H instance waiting to happen:

    build_monthly_revenue_pit.py:70   CORPUS/*.xlsx
    build_price_panel.py:159          OLD_CACHE/*.parquet
    build_bonus_share_panel.py:81     RAW/<pattern>
    build_market_state.py:117         SUSP_DIR/暫停交易*.zip
    ingest_status_export.py:103       SRC_DIR/<pattern>

    python research/b0_materializer/build_flat_leaves.py <run_dir> <run_id> <as_of> [dataset ...]
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError, build_leaf, write_leaf,
)

_TEJ = os.path.join("tej_exports", "DataExport0806")

# A-4. `source_family` / `authority` are DECLARED per family, never defaulted.
#
# Both fields are already a closed vocabulary owned by the manifest engine
# (`SOURCE_FAMILIES`, `AUTHORITY_LEVELS`), and R-W1-2 is what gives them meaning:
# two source families coexist, TEJ is the authoritative one, and the live feed
# supplies immediacy rather than authority. No taxonomy is introduced here; this
# engine stops SUPPLYING one.
#
# ⚠ Until now this engine hardcoded `TEJ` / `AUTHORITATIVE` for every entry of
# every flat family. Three of the four families are TEJ exports, so the constant
# was right for them by accident — and wrong for `calendar`, whose bytes are
# `~/market_cache/taiex_daily.parquet`. A manifest whose whole purpose is
# provenance was therefore asserting, in the very field the R-W1-2 audit reads,
# that a live-derived file was a TEJ export: the exact shape a silent source swap
# would take, with nothing in the artefact able to contradict it.
#
# So the value is per family, and a family that fails to declare one ABORTS. A
# default is what produced the defect.
_FAMILY_PROVENANCE_FIELDS = ("source_family", "authority")


def _declared_provenance(dataset: str, spec: dict) -> dict:
    """The family's own declared `source_family` / `authority`, or an abort.

    Not `spec.get(..., "TEJ")`. An undeclared family must be unbuildable: a
    default cannot be distinguished downstream from a deliberate declaration,
    and this leaf is the artefact provenance is read from.

    Only ABSENCE is checked here. Whether a declared value is IN the vocabulary
    is `source_ownership_manifest._assert_entry_vocabulary`'s call, and it
    already fails closed on the way through `build_leaf`. A second
    authentication of the same fact is not a second check.
    """
    absent = [f for f in _FAMILY_PROVENANCE_FIELDS if not spec.get(f)]
    if absent:
        raise ManifestError(
            "abort: the %s family declares no %s. Every entry's provenance is "
            "read from this leaf; a family that does not say which source "
            "family produced its bytes cannot be given one by default — that "
            "is how a live-derived file came to be stamped TEJ."
            % (dataset, absent))
    return {f: spec[f] for f in _FAMILY_PROVENANCE_FIELDS}


# `consumed` is a tuple of exact filenames — never a pattern. A pattern is how a
# file joins the panel without anyone deciding that it should.
FLAT_FAMILIES: dict = {
    "revenue": {
        "landing": os.path.join(_TEJ, "月營收2004-202608"),
        "source_family": "TEJ",
        "authority": "AUTHORITATIVE",
        "extensions": (".xlsx",),
        "consumed": ("20260806091706.xlsx",),
        "not_consumed_reason": "not the declared monthly-revenue export",
        "notes": (
            "exported 2026-08-06, so it does NOT contain July 2026 revenue "
            "(announced ~08-10). An L3 decision at an as_of after that date "
            "needs a newer export, and this leaf is where that shows up."),
    },
    "industry": {
        "landing": os.path.join(_TEJ, "產業類別"),
        "source_family": "TEJ",
        "authority": "AUTHORITATIVE",
        "extensions": (".xlsx",),
        "consumed": ("歷史產業類別.xlsx",),
        "not_consumed_reason": "not the declared historical industry table",
        "notes": (
            "O-E ruled the live `industry_map` NOT_PIT_SAFE — 49.4% of names "
            "changed sector under it — so this must be a DATED historical "
            "table, never a current-state lookup."),
    },
    "security_status": {
        "landing": os.path.join(_TEJ, "暫停交易2004-20260818"),
        "source_family": "TEJ",
        "authority": "AUTHORITATIVE",
        "extensions": (".zip",),
        # The producer's own filter is `SUSP_GLOB = "暫停交易*.zip"`, with the
        # comment "the sibling 事件+下市.zip is a different source"
        # (`p1a_o_e_market_state/build_market_state.py:51-52`). Six archives,
        # and 事件+下市.zip is explicitly NOT one of them.
        "consumed": ("暫停交易2004-2007.zip", "暫停交易2008-2011.zip",
                     "暫停交易2012-2015.zip", "暫停交易2016-2019.zip",
                     "暫停交易2020-2023.zip", "暫停交易2024-20260818.zip"),
        "not_consumed_reason": (
            "a different source: the producer's suspension corpus is "
            "暫停交易*.zip only (build_market_state.py:52)"),
        "notes": (
            "known_status + status_available_from. B0.6 exists because the "
            "second field was absent from the state; O-E-1 needs the date a "
            "status became KNOWABLE, not when it became effective."),
    },
    "calendar": {
        # NOT the TEJ suspension export. `build_market_state.py:53` reads
        # `CAL_SRC = ~/market_cache/taiex_daily.parquet` and writes
        # `data/b0/trading_calendar.csv`. Sharing a producer file is not sharing
        # a source, and the first declaration here conflated the two.
        "landing": os.path.join(os.path.expanduser("~"), "market_cache"),
        # A-4. `taiex_daily.parquet` is NOT a TEJ export. `core/market_index.py`
        # produces it from a one-off FinMind `TaiwanStockPrice(TAIEX)` seed plus
        # daily TWSE `MI_INDEX` increments — the same collector response
        # `price_valuation_daily` is built from. It is the LIVE family, and under
        # R-W1-2 a live source supplies immediacy, not authority, so
        # SUPPLEMENTARY is the only authority level it can honestly carry
        # (`_assert_entry_vocabulary` refuses the other combination).
        #
        # ⚠ That is a real statement, not a downgrade of ceremony: the calendar
        # decides WHEN, and it has NO authoritative source behind it. R-W1-2
        # gives TEJ the authority and the calendar's bytes do not come from TEJ,
        # so no TEJ leg exists to reconcile it against. The old `TEJ` /
        # `AUTHORITATIVE` stamp did not fix that — it hid it. What it exposes is
        # N-1, ruled 2026-09-02: the route may not be sealed while the family
        # that decides WHEN is the only SUPPLEMENTARY input
        # (`docs/A1N1_L3RouteSeal_AdjudicationOptions_2026-09-01.md` §9.4).
        #
        # This applies to the whole landing surface, the not_consumed siblings
        # included: what is declared is the surface these bytes were read from,
        # and that surface is the live cache.
        "source_family": "LIVE",
        "authority": "SUPPLEMENTARY",
        "extensions": (".parquet",),
        "consumed": ("taiex_daily.parquet",),
        # A shared cache root: these belong to other consumers, and each is
        # named so that a NEW sibling appearing is an abort rather than a shrug.
        "declared_subdirectories": (
            "institutional_flow_daily", "margin_daily", "monthly_revenue",
            "price_valuation_daily", "shareholding_daily"),
        "not_consumed_reason": "not the TAIEX daily series the calendar derives from",
        "notes": (
            "sessions come from the TAIEX daily series, not from any TEJ "
            "export. The calendar fixes as_of (§6.6) and the execution session "
            "(§6.5), so it decides WHEN, which decides everything else. W1 "
            "measured this cache at 2026-08-26 while the canonical calendar "
            "stops at 2026-08-17."),
    },
}

# ⚠ NOT DECLARED, deliberately.
#
# `data/b0/corporate_actions_ledger.csv` is consumed everywhere and no builder
# for it exists under `research/b0_materializer/`. Its upstream could be guessed
# from the 配股相關 / 除權息 exports, but a guessed lineage for the family that
# decides holder outcomes is exactly the wrong place to guess: this is the
# ledger that carries the NOT_RECONSTRUCTIBLE rows B0.7 terminates on.
#
# So it stays undeclared, the aggregate stays NOT_READY, and the reason is
# nameable rather than "a file was missing".
UNRESOLVED_FAMILIES: dict = {
    "corporate_actions": (
        "no producer for data/b0/corporate_actions_ledger.csv exists under "
        "research/b0_materializer/; its upstream export set has not been "
        "established. Needs a ruling before an L3 leaf can declare it."),
    "bonus_shares": (
        "sourced from harvested exchange payloads under artifacts/.../raw with "
        "a pattern glob (build_bonus_share_panel.py:81); the payload key form "
        "has not been established, and it is not a flat filename surface."),
}


def _members(path: str) -> list:
    import zipfile

    with zipfile.ZipFile(path) as z:
        return [{"name": i.filename, "size": int(i.file_size),
                 "crc32": "%08x" % i.CRC}
                for i in sorted(z.infolist(), key=lambda i: i.filename)]


def build(dataset: str, run_id: str, as_of: str, landing_dir: str = "") -> dict:
    if dataset in UNRESOLVED_FAMILIES:
        raise ManifestError(
            "abort: %s has no declared source contract yet.\n  %s"
            % (dataset, UNRESOLVED_FAMILIES[dataset]))
    if dataset not in FLAT_FAMILIES:
        raise ManifestError(
            "abort: %r is not a flat-directory family. financials, prices and "
            "valuation have their own producers." % dataset)

    spec = FLAT_FAMILIES[dataset]
    landing = landing_dir or os.path.join(REPO, spec["landing"])
    if not os.path.isdir(landing):
        raise ManifestError("abort: %s landing directory not found: %s"
                            % (dataset, landing))
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    # Some families land in a dedicated export folder; `calendar` lands in a
    # shared cache root whose sibling directories belong to other consumers. A
    # subdirectory is still an unknown — it is where a new file would appear —
    # so it must be DECLARED rather than assumed harmless.
    declared_dirs = set(spec.get("declared_subdirectories", ()))
    present, unknown, subdirs = [], [], []
    for name in sorted(os.listdir(landing)):
        p = os.path.join(landing, name)
        if os.path.islink(p):
            unknown.append(name)
        elif os.path.isdir(p):
            (subdirs if name in declared_dirs else unknown).append(name)
        elif os.path.splitext(name)[1].lower() in spec["extensions"]:
            present.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise ManifestError(
            "abort: %d entr(y/ies) in the %s landing directory are not a "
            "declared format:\n%s\n  directory: %s\n  declared:  %s\n"
            "Every entry must be named accepted or rejected."
            % (len(unknown), dataset, "\n".join("    %s" % n for n in unknown),
               landing, list(spec["extensions"])))

    missing = [f for f in spec["consumed"] if f not in present]
    if missing:
        raise ManifestError(
            "abort: %s declares %s as consumed but they are not present under "
            "%s. A declared source that disappears must be noticed."
            % (dataset, missing, landing))

    provenance = _declared_provenance(dataset, spec)
    entries = []
    for name in present:
        p = os.path.join(landing, name)
        consumed = name in spec["consumed"]
        entry = {
            "locator": name,
            "format": os.path.splitext(name)[1].lower().lstrip("."),
            "raw_sha256": file_sha256(p),
            "export_vintage": _dt.date.fromtimestamp(
                os.path.getmtime(p)).isoformat(),
            "observed_at": observed_at,
            **provenance,
            "disposition": "consumed" if consumed else "not_consumed",
        }
        if not consumed:
            entry["not_consumed_reason"] = spec["not_consumed_reason"]
        if entry["format"] == "zip" and consumed:
            # The archive rule is the engine's, not prices': a zip must
            # inventory its members whichever family it belongs to. Two of these
            # families land as archives, and a member appearing inside one is as
            # invisible as a file appearing in the directory.
            entry["members"] = _members(p)
        entries.append(entry)

    return build_leaf(
        dataset=dataset, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=spec["landing"].replace("\\", "/"),
        accepted_extensions=spec["extensions"],
        policies={"family_notes": {"rule": "FAMILY_SPECIFIC_CONSTRAINTS",
                                   "detail": spec["notes"]}})


def main(argv) -> int:
    if len(argv) < 4:
        print("usage: build_flat_leaves.py <run_dir> <run_id> <as_of> [dataset ...]")
        return 2
    run_dir, run_id, as_of = argv[1], argv[2], argv[3]
    targets = argv[4:] or sorted(FLAT_FAMILIES)
    for dataset in targets:
        rec = write_leaf(run_dir, build(dataset, run_id, as_of))
        print("%-18s %s  %s" % (rec["dataset"], rec["payload_sha256"][:16],
                                rec["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
