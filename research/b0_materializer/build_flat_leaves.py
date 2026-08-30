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

    build_monthly_revenue_pit.py:70   CORPUS/*.xlsx   ← CLOSED 2026-08-30. It
                                      fired: 月營收7月完整.zip matched nothing
                                      and raised nothing. That builder now
                                      enumerates and classifies against this
                                      module's own revenue declaration.
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

# `consumed` is a tuple of exact filenames — never a pattern. A pattern is how a
# file joins the panel without anyone deciding that it should.
#
# `declarations` is optional and keyed by one of those exact filenames. It
# carries the per-file source semantics the engine cannot derive from a
# directory listing — a `format` that the extension understates, and the
# `owns`/`yields` period algebra — in the same shape
# `build_financials_leaf.DECLARATION` uses. A family whose sources address
# their members some other way (an archive inventory, a payload key) declares
# none, and `assert_no_overlapping_ownership` then has nothing to check.
FLAT_FAMILIES: dict = {
    "revenue": {
        "landing": os.path.join(_TEJ, "月營收2004-202608"),
        "extensions": (".xlsx", ".zip"),
        "consumed": ("20260806091706.xlsx", "月營收7月完整.zip"),
        # A MIXED-FORMAT source with a contested period, declared the way
        # `build_financials_leaf.DECLARATION` declares its own:
        # `20260806090633.xlsx` owns `<= 202603` and YIELDS 202606 to
        # `2026 0826 2385家.csv` (declared `"format": "csv:utf-16:tab"`), which
        # OWNS it. Same shape here, for the same reason.
        #
        # Measured 2026-08-30, so a later reader need not re-derive it:
        #
        #   20260806091706.xlsx  478,127 rows, 271 months 200401..202607.
        #                        Its 202607 is PARTIAL — 406 securities, all
        #                        announced 2026-08-01..2026-08-06, i.e. only
        #                        what had been published when it was exported.
        #   月營收7月完整.zip     one member 20260830033323.csv, 2,002 rows,
        #                        exactly ONE month (202607), announced
        #                        2026-08-01..2026-08-17.
        #
        #   On 202607 the archive is a STRICT SUPERSET: only-xlsx = 0,
        #   only-zip = 1,596, shared = 406. On those 406 the two disagree on 3
        #   revenue values — 2838 and 6020 are "." (not yet published) in the
        #   workbook and carry real figures in the archive, and 3003 was
        #   REVISED 658,000 -> 657,875 千元. The later export carries the
        #   finalised month, so it OWNS 202607 and the workbook YIELDS it.
        #
        # ⚠ The two `owns` clauses must stay DISJOINT: `assert_no_overlapping_
        # ownership` checks them against each other at build_leaf time, and
        # `build_monthly_revenue_pit` enforces them row-by-row against the
        # bytes, so neither month has two claimants.
        "declarations": {
            "20260806091706.xlsx": {
                "owns": "<= 202606",
                "yields": ["202607"],
            },
            "月營收7月完整.zip": {
                # A zip by container, a UTF-16LE tab-separated csv by content:
                # BOM ff fe, zero commas, 9 tabs in the header row, CRLF. The
                # `csv:utf-16:tab` half is the financials idiom; the `zip:`
                # prefix is what keeps `_assert_archive_inventory` demanding a
                # member inventory for it.
                "format": "zip:csv:utf-16:tab",
                "owns": ["202607"],
                "yields": [],
            },
        },
        "not_consumed_reason": "not the declared monthly-revenue export",
        "notes": (
            "20260806091706.xlsx was exported 2026-08-06, so its July 2026 "
            "month is PARTIAL — 406 of 2,002 securities, only those that had "
            "announced by then. 月營收7月完整.zip is the completed 202607 "
            "export: it OWNS that month, the workbook YIELDS it and owns "
            "<= 202606. An L3 decision at an as_of after ~08-10 that read only "
            "the workbook would see a July that is 80% absent and looks "
            "complete."),
    },
    "industry": {
        "landing": os.path.join(_TEJ, "產業類別"),
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

    Twin of `build_prices_leaf._stamped_declaration`; each stamps against its
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


def build(dataset: str, run_id: str, as_of: str, landing_dir: str = "",
          declared_landing_dir: str = "", observed_at: str = "") -> dict:
    # `declared_landing_dir` means "READ the staged directory, DECLARE this
    # one". Without a staged read there is nothing for it to stand in for, and
    # an argument the callee ignores is a decision input the caller believes it
    # supplied (`run_l3_prospective.py:501-508`). So it is refused BY NAME
    # rather than dropped.
    if declared_landing_dir and not landing_dir:
        raise ManifestError(
            "abort: declared_landing_dir=%r was supplied without landing_dir. "
            "It only means anything when the bytes are read from a stand-in "
            "directory; on its own it would be silently dropped."
            % declared_landing_dir)
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
    observed_at = observed_at or _dt.datetime.now().astimezone().isoformat(
        timespec="seconds")

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

    # Per-file source semantics, if the family declares any. A declaration for
    # a file the family does not consume is a decision aimed at nothing — it
    # would sit in the spec looking authoritative while the engine ignored it,
    # so it is refused rather than dropped.
    declarations = dict(spec.get("declarations", {}))
    aimless = [n for n in sorted(declarations) if n not in spec["consumed"]]
    if aimless:
        raise ManifestError(
            "abort: %s declares source semantics for %s, which it does not "
            "consume. A declaration the engine never applies is worse than "
            "none: it reads as a decision that was made."
            % (dataset, aimless))
    # Ownership is a family-wide property or it is nothing: an entry WITHOUT
    # `owns` is invisible to `assert_no_overlapping_ownership`, so one such
    # entry beside declared ones would be an undeclared claimant that no
    # overlap check can see.
    owning = [n for n in spec["consumed"] if "owns" in declarations.get(n, {})]
    if owning and len(owning) != len(spec["consumed"]):
        raise ManifestError(
            "abort: %s declares period ownership for %s but not for %s. Within "
            "one family ownership is declared for every consumed source or for "
            "none; an entry without `owns` is one the overlap check cannot see."
            % (dataset, owning,
               [n for n in spec["consumed"] if n not in owning]))

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
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed" if consumed else "not_consumed",
        }
        if consumed:
            entry.update(declarations.get(name, {}))
        else:
            entry["not_consumed_reason"] = spec["not_consumed_reason"]
        # `startswith`, not `==`: a declared format may QUALIFY the container
        # ("zip:csv:utf-16:tab" says what the member is), and the manifest
        # engine's own archive rules key off the same prefix
        # (`_assert_archive_inventory`, `assert_landing_dir_matches`). Matching
        # on equality here would let a qualified zip skip its inventory while
        # the validator still demanded one.
        if str(entry["format"]).startswith("zip") and consumed:
            # The archive rule is the engine's, not prices': a zip must
            # inventory its members whichever family it belongs to. Two of these
            # families land as archives, and a member appearing inside one is as
            # invisible as a file appearing in the directory.
            entry["members"] = _members(p)
        entries.append(entry)

    # With no stand-in read, the stamp is the family's OWN declared constant —
    # never `os.path.join(REPO, ...)`. The constant is the contract, it is the
    # value A01's evidence carries, and it is the only form that survives a
    # different clone root. (`calendar`'s constant is deliberately home-absolute:
    # its source is a shared cache outside the repo, not an export in it.)
    if not landing_dir:
        declared_landing = spec["landing"].replace("\\", "/")
    elif declared_landing_dir:
        declared_landing = _stamped_declaration(
            declared_landing_dir, "declared_landing_dir")
    else:
        # A staged read with nothing declared over it: the staging path IS the
        # declaration. That is the validation pass, whose leaves must point at
        # the snapshot the readers are about to open; it is throwaway evidence
        # and deliberately not portable.
        declared_landing = landing.replace("\\", "/")
    return build_leaf(
        dataset=dataset, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=declared_landing,
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
