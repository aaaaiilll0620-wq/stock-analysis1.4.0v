# -*- coding: utf-8 -*-
"""W6a · L3 run-bound source ownership manifests: leaf + aggregate.

W5 froze the financials source contract as a CONSTANT in the L2 builder. That is
correct for L2, whose source set is finished, and wrong for L3, whose source set
changes every month by design: a concrete filename in builder code means every
ordinary re-export edits code, and the route's own hash then moves because DATA
ARRIVED — promoting a routine receipt refresh into what looks like a
production-route semantic change.

TWO CONTRACTS, NOT ONE CONTESTED CONTRACT:

    L2_RETROSPECTIVE_FINANCIALS_CONTRACT
        `build_financials_pit.py` + its `SOURCE_OWNERSHIP` constant. Untouched
        by this module. L2 is finished and stays finished.

    L3_PROSPECTIVE_SOURCE_MANIFEST_CONTRACT_V1
        this module. Per-run, immutable, content-bound.

⚠ THE SEPARATION IS NORMATIVE, NOT STYLISTIC. This module must never delete or
relocate L2's `SOURCE_OWNERSHIP`, make the L2 builder depend on an L3 manifest,
change L2 output, or be "shared" by refactoring L2 onto it. The first L3
financials manifest may be TRANSCRIBED from L2's declaration by hand or by a
one-off tool, but nothing here imports that constant at runtime: once
transcribed, the manifest's identity comes from concrete file hashes, its own
payload hash, and the run receipt that binds it — not from L2.

TWO TIERS:

    source_manifest_<dataset>.json    leaf. One dataset's own source semantics:
                                      concrete filename/URI, raw sha256, format,
                                      owns/yields (or that source's locator
                                      form), export vintage, observed_at,
                                      contract version, schema, run_id, as_of.

    source_ownership_manifest.json    aggregate index. Binds run_id, as_of,
                                      route_seal_id, required_datasets, and for
                                      every leaf its path + raw sha256 + payload
                                      sha256, plus its own payload sha256.

A W6b receipt therefore binds ONE hash — the aggregate's raw sha256 — and
transitively covers every source.

`REQUIRED_DATASETS` is not a caller argument. A caller that could shrink it
could omit a source and still look complete, which is the whole failure this
replaces. Until W4/A2 publish the production-route transitive source inventory,
the list here is PROVISIONAL and the aggregate reports
`NOT_READY_REQUIRED_SOURCE_MANIFEST_MISSING` rather than pretending readiness.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
_L3 = os.path.join(REPO, "research", "b0_l3")
if _L3 not in sys.path:
    sys.path.insert(0, _L3)

from core.b0_canonical_hash import canonical_sha256, file_sha256   # noqa: E402

LEAF_SCHEMA_VERSION = "b0_source_manifest_leaf@1"
AGGREGATE_SCHEMA_VERSION = "b0_source_ownership_manifest@1"
L3_CONTRACT_VERSION = "L3_PROSPECTIVE_SOURCE_MANIFEST_CONTRACT_V1"

AGGREGATE_FILENAME = "source_ownership_manifest.json"
LEAF_FILENAME = "source_manifest_%s.json"

READY = "READY"
NOT_READY = "NOT_READY_REQUIRED_SOURCE_MANIFEST_MISSING"

# The floor, DERIVED — see `research/b0_l3/route_closure.py`.
#
# ⚠ This was hand-listed first, at seven families, and silently omitted
# `industry` and `bonus_shares`. Both shape a decision:
# `SecurityPitInputs.pit_industry` is a feature input, and the bonus panel
# supplies the C-51 holder multiplier behind the share-unit-adjusted price
# series that momentum reads. Neither omission would have raised anything — the
# run would simply have decided differently. That is the exact failure this
# floor exists to prevent, committed while writing the thing that prevents it.
#
# So it is no longer written here. `route_closure` derives it from the
# `ProductionSources` fields and cross-checks it against the retrospective
# materializer's `load_sources()`, and a test fails if the two disagree.
#
# This is the aggregate's floor, not the caller's suggestion: `assemble_aggregate`
# takes `required=` for tests only.
from route_closure import REQUIRED_DATASET_FLOOR as REQUIRED_DATASETS  # noqa: E402

SELF_HASH_FIELD = "payload_sha256"

REQUIRED_LEAF_FIELDS: tuple[str, ...] = (
    "schema_version", "contract_version", "dataset", "run_id", "as_of",
    "entries",
)
REQUIRED_ENTRY_FIELDS: tuple[str, ...] = (
    "locator", "format", "raw_sha256", "export_vintage", "observed_at",
    # R-W1-2: two source families coexist and TEJ is authoritative. Which family
    # a file belongs to is therefore part of its identity, not context: W1
    # measured that on the 25-session overlap the two families disagree on the
    # population (~30 securities per session that FinMind lists and TEJ does
    # not), on volume precision (TEJ publishes 千股 so its share counts are
    # always multiples of 1,000), and on one sentinel-zero close.
    "source_family", "authority",
    # Ruling 1's invariant: every entry is NAMED accepted or rejected. A file
    # that is present and deliberately unused must say so — silence is what the
    # glob already did.
    "disposition",
)

SOURCE_FAMILIES: tuple[str, ...] = ("TEJ", "LIVE")
AUTHORITY_LEVELS: tuple[str, ...] = ("AUTHORITATIVE", "SUPPLEMENTARY")
DISPOSITIONS: tuple[str, ...] = ("consumed", "not_consumed")
REQUIRED_AGGREGATE_FIELDS: tuple[str, ...] = (
    "schema_version", "contract_version", "run_id", "as_of", "purpose",
    "route_seal_id", "required_datasets", "leaves", "readiness",
)


class ManifestError(SystemExit):
    """Fail-loud: the manifest and the world disagree, or the manifest is unfit."""


# --- period algebra ------------------------------------------------------------
#
# Deliberately a SECOND implementation of the same idea that lives in the L2
# builder. Sharing it would create the reverse dependency the ruling forbids,
# and the two contracts are versioned separately precisely so they may drift.

def norm_period(value) -> str:
    """`年月` -> canonical 'YYYYMM'. The two frozen formats, nothing else."""
    s = str(value).strip().replace("/", "")
    if len(s) != 6 or not s.isdigit():
        raise ManifestError(
            "abort: period value %r is not one of the frozen formats "
            "('%%Y%%m', '%%Y/%%m')" % (value,))
    return s


def owns_predicate(spec_value):
    """`['202606']` or `'<= 202603'` -> (predicate, human-readable members)."""
    if isinstance(spec_value, (tuple, list)):
        owned = {norm_period(p) for p in spec_value}
        return (lambda p: p in owned), sorted(owned)
    if isinstance(spec_value, str) and spec_value.startswith("<="):
        bound = norm_period(spec_value[2:])
        return (lambda p: p <= bound), ["<= %s" % bound]
    raise ManifestError(
        "abort: ownership declaration %r is not a supported form. Use a list of "
        "periods or '<= YYYYMM'. An unparsed declaration is an undeclared one."
        % (spec_value,))


def assert_periods_conform(entry: dict, periods) -> tuple:
    """Every period a file carries is either OWNED or explicitly YIELDED."""
    owns, _ = owns_predicate(entry["owns"])
    yields = {norm_period(p) for p in entry.get("yields", ())}

    seen = sorted({norm_period(p) for p in periods})
    owned = [p for p in seen if owns(p)]
    yielded = [p for p in seen if p in yields and not owns(p)]
    stray = [p for p in seen if not owns(p) and p not in yields]
    if stray:
        raise ManifestError(
            "abort: %s carries period(s) %s that it neither OWNS nor YIELDS.\n"
            "  owns:   %s\n  yields: %s\n"
            "Dropping them would be a silent skip; keeping them would make two "
            "files canonical for one period. The manifest must say which."
            % (entry["locator"], ", ".join(stray), entry["owns"],
               entry.get("yields", []) or "[]"))
    return tuple(owned), tuple(yielded)


# --- canonical hashing ---------------------------------------------------------

def payload_sha256(doc: dict) -> str:
    """Hash of a manifest's content, excluding the field that carries it."""
    return canonical_sha256({k: v for k, v in doc.items()
                             if k != SELF_HASH_FIELD})


def _write_immutable(path: str, doc: dict) -> tuple:
    """Exclusive create. Returns (payload_sha256, raw_sha256).

    `O_EXCL` rather than a mode string: "immutable once written" is enforced by
    the filesystem call, not by everyone remembering.
    """
    body = {k: v for k, v in doc.items() if k != SELF_HASH_FIELD}
    body[SELF_HASH_FIELD] = payload_sha256(body)

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ManifestError(
            "abort: a manifest already exists at %s. Manifests are immutable; a "
            "changed source set gets a NEW run manifest, never an overwrite."
            % path)
    with os.fdopen(fd, "wb") as fh:
        fh.write((json.dumps(body, ensure_ascii=False, sort_keys=True, indent=1)
                  + "\n").replace("\r\n", "\n").encode("utf-8"))
    return body[SELF_HASH_FIELD], file_sha256(path)


# --- leaf ----------------------------------------------------------------------

def build_leaf(*, dataset: str, run_id: str, as_of: str, entries,
               landing_directory: str = "", accepted_extensions=(),
               schema_sha256: str = "", policies=None,
               derived_dependencies=None) -> dict:
    """Assemble one dataset leaf. Validates before it is ever written."""
    if not dataset or not run_id or not as_of:
        raise ManifestError(
            "abort: a leaf must name its dataset, run_id and as_of. A source set "
            "that cannot say which run and which decision date it belongs to "
            "cannot be re-checked against either.")
    entries = list(entries)
    if not entries:
        raise ManifestError("abort: leaf %r declares no entries" % dataset)

    for i, e in enumerate(entries):
        absent = [f for f in REQUIRED_ENTRY_FIELDS if not e.get(f)]
        if absent:
            raise ManifestError(
                "abort: %s entry %d (%s) is missing %s. Absence is never a "
                "default here: a source that cannot say when it was exported or "
                "what its bytes hash to cannot be re-checked later."
                % (dataset, i, e.get("locator", "<unnamed>"), absent))

    locators = [e["locator"] for e in entries]
    if len(set(locators)) != len(locators):
        dupes = sorted({x for x in locators if locators.count(x) > 1})
        raise ManifestError(
            "abort: leaf %s declares %s more than once" % (dataset, dupes))

    for e in entries:
        _assert_entry_vocabulary(dataset, e)
        _assert_archive_inventory(dataset, e)

    if not [e for e in entries if e["disposition"] == "consumed"]:
        raise ManifestError(
            "abort: leaf %s consumes nothing. A leaf that declares only "
            "not_consumed entries is a dataset with no source, which is not the "
            "same fact as a dataset nobody declared." % dataset)

    doc = {
        "schema_version": LEAF_SCHEMA_VERSION,
        "contract_version": L3_CONTRACT_VERSION,
        "dataset": dataset,
        "run_id": run_id,
        "as_of": as_of,
        "landing_directory": landing_directory,
        "accepted_extensions": list(accepted_extensions),
        "schema_sha256": schema_sha256,
        # Rulings that constrain how this family's bytes may be READ, carried
        # beside the bytes. A consumer cannot reach the source without meeting
        # them — which is the point: the live sentinel zero and the TEJ unit
        # convention are not commentary, they decide values.
        "policies": dict(policies or {}),
        # A family whose rows are DERIVED from another family's source rather
        # than from its own files binds that family's leaf by payload hash.
        # `corporate_actions` is the case: its holder-side reorganization rows
        # come from security_status, not from any 配股相關 archive. Restating
        # the other family's files here would be two places to update and one
        # place to forget; a hash is checked.
        "derived_dependencies": dict(derived_dependencies or {}),
        "entries": entries,
    }
    assert_no_overlapping_ownership(doc)
    return doc


def load_leaf(path: str) -> dict:
    """Read, validate shape, verify the leaf's own payload hash."""
    doc = _load_json(path)
    _require_fields(path, doc, REQUIRED_LEAF_FIELDS)
    if doc["schema_version"] != LEAF_SCHEMA_VERSION:
        raise ManifestError(
            "abort: %s declares schema %r, this engine speaks %r. A manifest "
            "from another schema must be read by that schema's engine, not "
            "reinterpreted by this one." % (path, doc["schema_version"],
                                            LEAF_SCHEMA_VERSION))
    for i, e in enumerate(doc["entries"]):
        absent = [f for f in REQUIRED_ENTRY_FIELDS if not e.get(f)]
        if absent:
            raise ManifestError("abort: %s entry %d is missing %s"
                                % (path, i, absent))
    _verify_self_hash(path, doc)
    assert_no_overlapping_ownership(doc)
    return doc


def _assert_entry_vocabulary(dataset: str, e: dict) -> None:
    """Closed vocabularies. An unrecognised value is undeclared, not permissive."""
    for field, allowed in (("source_family", SOURCE_FAMILIES),
                           ("authority", AUTHORITY_LEVELS),
                           ("disposition", DISPOSITIONS)):
        if e[field] not in allowed:
            raise ManifestError(
                "abort: %s entry %s has %s=%r, which is not one of %s. A value "
                "nobody defined cannot be checked against anything."
                % (dataset, e["locator"], field, e[field], list(allowed)))

    if e["disposition"] == "not_consumed" and not str(
            e.get("not_consumed_reason", "")).strip():
        raise ManifestError(
            "abort: %s declares %s not_consumed without a reason. 'Present and "
            "deliberately unused' and 'present and silently skipped' look "
            "identical from the outside; the reason is what separates them."
            % (dataset, e["locator"]))

    if (e["source_family"] == "LIVE" and e["authority"] == "AUTHORITATIVE"):
        raise ManifestError(
            "abort: %s declares LIVE source %s AUTHORITATIVE. R-W1-2 makes TEJ "
            "authoritative; a live feed supplies immediacy, not authority."
            % (dataset, e["locator"]))


def _assert_archive_inventory(dataset: str, e: dict) -> None:
    """An archive must inventory its members.

    `build_price_panel.py` globs `ZIP_DIR/*.zip`, which is the O-H defect
    inverted and worse: a zip dropped into that directory is silently INCLUDED.
    One level down, a member added to or removed from a declared zip is equally
    invisible, because the zip's own hash is not consulted per member. So an
    archive entry declares every member, its size and its CRC.
    """
    # Only for archives that are actually READ. A not_consumed archive's members
    # cannot change any value, so requiring an inventory for it would be
    # ceremony — and ceremony is what stops people maintaining the parts that
    # matter.
    if not str(e["format"]).startswith("zip") or e["disposition"] != "consumed":
        return
    members = e.get("members")
    if not members:
        raise ManifestError(
            "abort: %s declares archive %s with no member inventory. `*.zip` is "
            "not a contract: an archive that gained or lost a member without "
            "the inventory changing is the same silent skip one level down."
            % (dataset, e["locator"]))
    for m in members:
        missing = [f for f in ("name", "size", "crc32") if not str(
                m.get(f, "")).strip()]
        if missing:
            raise ManifestError(
                "abort: %s archive %s member %r is missing %s"
                % (dataset, e["locator"], m.get("name", "<unnamed>"), missing))


def assert_archive_members_match(path: str, entry: dict) -> None:
    """Open the archive and check it still holds exactly what was declared."""
    import zipfile

    declared = {m["name"]: (int(m["size"]), str(m["crc32"]).lower())
                for m in entry["members"]}
    with zipfile.ZipFile(path) as z:
        actual = {i.filename: (int(i.file_size), "%08x" % i.CRC)
                  for i in z.infolist()}

    added = sorted(set(actual) - set(declared))
    removed = sorted(set(declared) - set(actual))
    if added or removed:
        raise ManifestError(
            "abort: archive %s no longer holds what the manifest declares.\n"
            "  members added:   %s\n  members removed: %s\n"
            "A re-packed archive is a new source, not the same source."
            % (entry["locator"], added or "none", removed or "none"))

    for name, (size, crc) in sorted(declared.items()):
        if actual[name] != (size, crc):
            raise ManifestError(
                "abort: archive %s member %s changed.\n"
                "  declared: size=%d crc=%s\n  actual:   size=%d crc=%s"
                % (entry["locator"], name, size, crc,
                   actual[name][0], actual[name][1]))


def assert_no_overlapping_ownership(leaf: dict) -> None:
    """Exactly one source may be canonical for a period.

    Skipped for leaves whose entries carry no `owns` — a source family may
    address its members some other way (a zip member inventory, a board/date
    payload key). Ownership overlap is only meaningful where ownership is
    declared in period terms.
    """
    entries = [e for e in leaf["entries"] if "owns" in e]
    if len(entries) < 2:
        return
    preds = {e["locator"]: owns_predicate(e["owns"])[0] for e in entries}

    probes = set()
    for e in entries:
        for key in ("owns", "yields"):
            v = e.get(key, [])
            if isinstance(v, (tuple, list)):
                probes |= {norm_period(p) for p in v}
            elif isinstance(v, str) and v.startswith("<="):
                probes.add(norm_period(v[2:]))

    names = sorted(preds)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            clash = sorted(p for p in probes if preds[a](p) and preds[b](p))
            if clash:
                raise ManifestError(
                    "abort: period(s) %s are declared OWNED by both %s and %s. "
                    "Two owners for one period is the conflict this contract "
                    "exists to refuse." % (", ".join(clash), a, b))


def assert_landing_dir_matches(leaf: dict, landing_dir: str = "") -> list:
    """Directory and leaf must describe the same files, byte for byte."""
    landing = landing_dir or leaf.get("landing_directory", "")
    if not landing:
        raise ManifestError(
            "abort: leaf %s declares no landing directory and none was supplied"
            % leaf["dataset"])
    if not os.path.isabs(landing):
        landing = os.path.join(REPO, landing)
    if not os.path.isdir(landing):
        raise ManifestError("abort: landing directory does not exist: %s"
                            % landing)

    accepted = tuple(leaf.get("accepted_extensions", ()))
    on_disk, rejected = set(), []
    for name in sorted(os.listdir(landing)):
        p = os.path.join(landing, name)
        ok = (os.path.isfile(p) and not os.path.islink(p)
              and (not accepted
                   or os.path.splitext(name)[1].lower() in accepted))
        (on_disk.add(name) if ok else rejected.append(name))

    declared = {e["locator"] for e in leaf["entries"]}

    missing = sorted(declared - on_disk)
    if missing:
        raise ManifestError(
            "abort: %d file(s) declared by leaf %s are NOT PRESENT:\n%s\n"
            "  landing directory: %s\n"
            "A declared source that disappears must be noticed, not absorbed."
            % (len(missing), leaf["dataset"],
               "\n".join("    %s" % n for n in missing), landing))

    undeclared = sorted((on_disk - declared) | set(rejected))
    if undeclared:
        raise ManifestError(
            "abort: %d entr(y/ies) in the landing directory are not declared by "
            "leaf %s:\n%s\n  landing directory: %s\n"
            "A new export is a NEW RUN MANIFEST, not a file that quietly joins "
            "an existing one." % (len(undeclared), leaf["dataset"],
                                  "\n".join("    %s" % n for n in undeclared),
                                  landing))

    paths = []
    for e in leaf["entries"]:
        p = os.path.join(landing, e["locator"])
        got = file_sha256(p)
        if got != e["raw_sha256"]:
            raise ManifestError(
                "abort: %s does not match the bytes leaf %s declares.\n"
                "  declared: %s\n  on disk:  %s\n"
                "The file was replaced in place. A replacement is a new source, "
                "and a new source needs a new run manifest."
                % (e["locator"], leaf["dataset"], e["raw_sha256"], got))
        if str(e["format"]).startswith("zip") and e["disposition"] == "consumed":
            assert_archive_members_match(p, e)
        paths.append(p)
    return paths


def write_leaf(run_dir: str, leaf: dict) -> dict:
    """Write one leaf immutably. Returns its index record for the aggregate."""
    path = os.path.join(run_dir, LEAF_FILENAME % leaf["dataset"])
    payload, raw = _write_immutable(path, leaf)
    return {"dataset": leaf["dataset"],
            "path": os.path.basename(path),
            "raw_sha256": raw,
            "payload_sha256": payload}


# --- aggregate -----------------------------------------------------------------

def assemble_aggregate(*, run_dir: str, run_id: str, as_of: str,
                       purpose: str, route_seal_id=None,
                       capture_authority=None,
                       required=REQUIRED_DATASETS) -> dict:
    """Index every leaf present in `run_dir` and state readiness honestly.

    `required` exists for tests, not for callers narrowing the floor: a run that
    could shorten its own requirement could omit a source and still look
    complete. Production callers take the module constant.

    §20 / C-70 · TWO PURPOSES, TWO BINDINGS. `purpose` is required because the
    two runs that read these sources answer to different authorities:

        LINEAGE_FLOOR_CAPTURE   binds the C-70 capture authority and may NOT
                                name a route seal — the seal will bind the
                                capture record, and binding both ways is a cycle.
        PRODUCTION_RUN          binds a REAL route seal. A placeholder like
                                "PENDING" is refused: it reads as bound in every
                                audit that only checks the field is present.
    """
    from core.b0_l3_lineage_capture import (                       # noqa: E402
        FLOOR_CAPTURE_REQUIRED_DATASETS, PURPOSE_CAPTURE,
        RATIFIED_INVENTORY_AUTHORITY, LineageCaptureError,
        assert_capture_inventory, assert_manifest_binding,
    )

    if purpose == PURPOSE_CAPTURE:
        # C-71 · §20.8. The capture inventory is the floor's causal closure and
        # it is FIXED: `required` is not a knob here, and a caller that passes a
        # different set is refused rather than quietly overridden.
        if required is REQUIRED_DATASETS:
            required = FLOOR_CAPTURE_REQUIRED_DATASETS
        try:
            required = assert_capture_inventory(required)
        except LineageCaptureError as exc:
            raise ManifestError(str(exc))
    if not run_id or not as_of:
        raise ManifestError("abort: an aggregate must name run_id and as_of.")
    try:
        assert_manifest_binding(purpose, route_seal_id=route_seal_id,
                                capture_authority=capture_authority)
    except LineageCaptureError as exc:
        raise ManifestError(str(exc))

    leaves, missing = {}, []
    for dataset in sorted(required):
        path = os.path.join(run_dir, LEAF_FILENAME % dataset)
        if not os.path.isfile(path):
            missing.append(dataset)
            continue
        leaf = load_leaf(path)
        if leaf["run_id"] != run_id:
            raise ManifestError(
                "abort: leaf %s belongs to run %r but the aggregate is for %r. "
                "A source set assembled from two runs is not a source set."
                % (dataset, leaf["run_id"], run_id))
        if leaf["as_of"] != as_of:
            raise ManifestError(
                "abort: leaf %s is as of %r but the aggregate is as of %r. Two "
                "decision dates in one manifest means at least one source was "
                "read at the wrong time." % (dataset, leaf["as_of"], as_of))
        leaves[dataset] = {
            "path": os.path.basename(path),
            "raw_sha256": file_sha256(path),
            "payload_sha256": leaf[SELF_HASH_FIELD],
        }

    # A declared dependency must resolve to THIS run's leaf, by payload hash.
    # A dependency pointing at another run's status source, or at a hash no leaf
    # in this run carries, is a source set stitched from two runs.
    for dataset in sorted(leaves):
        leaf = load_leaf(os.path.join(run_dir, LEAF_FILENAME % dataset))
        for dep_name, dep in sorted(leaf.get("derived_dependencies", {}).items()):
            if dep_name not in leaves:
                raise ManifestError(
                    "abort: leaf %s declares a dependency on %s, which is not "
                    "part of this run's source set." % (dataset, dep_name))
            got = leaves[dep_name]["payload_sha256"]
            if dep.get("payload_sha256") != got:
                raise ManifestError(
                    "abort: leaf %s depends on %s payload %s, but this run's "
                    "%s leaf is %s.\n"
                    "A dependency bound to a different run's source is not a "
                    "dependency, it is a coincidence."
                    % (dataset, dep_name, str(dep.get("payload_sha256"))[:16],
                       dep_name, got[:16]))

    undeclared = sorted(
        n for n in os.listdir(run_dir)
        if n.startswith("source_manifest_") and n.endswith(".json")
        and n[len("source_manifest_"):-len(".json")] not in required)
    if undeclared:
        raise ManifestError(
            "abort: %d source manifest(s) in the run directory are not in "
            "REQUIRED_DATASETS:\n%s\n"
            "A source nobody required is a source nobody has ruled on."
            % (len(undeclared), "\n".join("    %s" % n for n in undeclared)))

    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "contract_version": L3_CONTRACT_VERSION,
        "run_id": run_id,
        "as_of": as_of,
        "purpose": purpose,
        "route_seal_id": route_seal_id,
        "capture_authority": capture_authority,
        "required_datasets": sorted(required),
        "leaves": leaves,
        "readiness": NOT_READY if missing else READY,
        "missing_datasets": missing,
        # v1.35 · C-70 · §20.8. This used to say PROVISIONAL — owed by W4/A2.
        # The inventory it was owed by now EXISTS: `REQUIRED_DATASET_FLOOR` is
        # derived from `route_closure.DATASET_FAMILIES`, the production-route
        # transitive inventory, and `assert_inventories_agree()` checks it
        # against what the retrospective materializer actually loads. A capture
        # refuses a provisional inventory, so leaving the stale sentence here
        # would have blocked every capture for a reason that stopped being true.
        "required_datasets_provenance": RATIFIED_INVENTORY_AUTHORITY,
    }


def write_aggregate(run_dir: str, aggregate: dict) -> tuple:
    """Write the aggregate immutably. Returns (payload_sha256, raw_sha256).

    A NOT_READY aggregate is still written — the incomplete state is a fact
    worth preserving — but `assert_ready` refuses to let a run consume it.
    """
    return _write_immutable(os.path.join(run_dir, AGGREGATE_FILENAME), aggregate)


def load_aggregate(path: str) -> dict:
    doc = _load_json(path)
    _require_fields(path, doc, REQUIRED_AGGREGATE_FIELDS)
    if doc["schema_version"] != AGGREGATE_SCHEMA_VERSION:
        raise ManifestError(
            "abort: %s declares schema %r, this engine speaks %r"
            % (path, doc["schema_version"], AGGREGATE_SCHEMA_VERSION))
    _verify_self_hash(path, doc)
    return doc


def verify_aggregate(run_dir: str) -> dict:
    """Re-check an aggregate against the leaves actually on disk."""
    agg = load_aggregate(os.path.join(run_dir, AGGREGATE_FILENAME))
    for dataset, rec in sorted(agg["leaves"].items()):
        path = os.path.join(run_dir, rec["path"])
        if not os.path.isfile(path):
            raise ManifestError(
                "abort: aggregate indexes leaf %s at %s, which is not present."
                % (dataset, rec["path"]))
        raw = file_sha256(path)
        if raw != rec["raw_sha256"]:
            raise ManifestError(
                "abort: leaf %s has changed since the aggregate indexed it.\n"
                "  indexed:  %s\n  on disk:  %s\n"
                "Leaves are immutable; a changed source set is a new run."
                % (dataset, rec["raw_sha256"], raw))
        leaf = load_leaf(path)
        if leaf[SELF_HASH_FIELD] != rec["payload_sha256"]:
            raise ManifestError(
                "abort: leaf %s payload hash disagrees with the aggregate index"
                % dataset)
    return agg


def assert_ready(aggregate: dict) -> None:
    """A run may not consume an incomplete source set."""
    if aggregate["readiness"] != READY:
        raise ManifestError(
            "abort: source set is %s — missing %s.\n"
            "L3 does not start on a partial source inventory: a decision taken "
            "without a source that would have changed it is not a prospective "
            "observation, it is an accident."
            % (aggregate["readiness"],
               ", ".join(aggregate.get("missing_datasets", [])) or "unknown"))


# --- shared plumbing -----------------------------------------------------------

def _load_json(path: str) -> dict:
    if not os.path.isfile(path):
        raise ManifestError(
            "abort: no manifest at %s. A run with no declared source set is a "
            "run whose inputs cannot be re-checked." % path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError("abort: manifest %s is not readable JSON: %s"
                            % (path, exc))


def _require_fields(path: str, doc: dict, fields) -> None:
    missing = [f for f in fields if f not in doc]
    if missing:
        raise ManifestError("abort: manifest %s is missing required field(s) %s"
                            % (path, missing))


def _verify_self_hash(path: str, doc: dict) -> None:
    recorded = doc.get(SELF_HASH_FIELD)
    if not recorded:
        raise ManifestError(
            "abort: manifest %s carries no %s. Without it a receipt cannot bind "
            "the source set it was built from." % (path, SELF_HASH_FIELD))
    got = payload_sha256(doc)
    if got != recorded:
        raise ManifestError(
            "abort: manifest %s has been EDITED since it was written.\n"
            "  recorded:   %s\n  recomputed: %s\n"
            "A manifest is immutable once written: a changed source set is a "
            "new run manifest, never a rewritten one." % (path, recorded, got))
