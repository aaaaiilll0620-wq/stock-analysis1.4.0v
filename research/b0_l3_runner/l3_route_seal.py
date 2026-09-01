# -*- coding: utf-8 -*-
"""A2 · the COMPLETE replayable production route, content-bound.

`route_closure.production_route_code_closure()` answers a narrower question than
A2 asks. It walks `core.*` imports from `b0_adapter_production` and `b0_route`,
so what it returns is the canonical DECISION core -- and A2 ruled that the
closure is the whole replayable route. Everything between a declared source file
and `run_decision` is outside it today:

    the leaf producers, `source_ownership_manifest`, `l3_readers`,
    `l3_assemble`, `l3_snapshot`, `route_closure` itself, `b0_l3_run_layout`,
    `portfolio_checkpoint`, `portfolio_side`, and this route's runner

A run sealed on the core closure alone would bind the code that DECIDES and
leave unbound every line that decides WHAT THE DECISION SEES. That is the
under-inclusive-closure defect `route_closure`'s own docstring warns about, one
layer further out: it looks complete.

WHAT THIS MODULE IS AND IS NOT

It is the seal CONTRACT and the VERIFIER. It derives the closure, hashes it,
and checks a seal against the working tree. It does not take a seal as a side
effect of anything: `write_route_seal` is the only writer, it is O_EXCL and
content-addressed, and nothing in the runner calls it. Taking the first L3 route
seal is a deliberate, separately-authorised act.

THREE THINGS THE GATE NEEDS AND DID NOT HAVE

  1. `route_closure.seal_payload()` publishes
     `still_owed_before_a_seal_may_be_taken`. That list is the route's own
     statement that it is not sealable yet, and it is READ here rather than
     restated -- a copy would drift the moment A-line clears an entry.
  2. A seal artefact that content-binds every file of the closure, so "the
     route is sealed" is a rehash rather than a claim.
  3. `source_ownership_manifest` requires `route_seal_id` to be non-empty and
     nothing more, so the literal string `PENDING` satisfies it. A run whose
     sources point at a placeholder is a run whose sources are tied to no route
     at all.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.b0_canonical_hash import canonical_sha256, file_sha256   # noqa: E402

ROUTE_SEAL_CONTRACT_VERSION = "b0_l3_route_seal@1"
SEAL_ROOT = os.path.join(REPO, "artifacts", "l3_route_seal", "seals")

# A `route_seal_id` that names no seal. `source_ownership_manifest` accepts any
# non-empty string, so these have to be refused HERE or a placeholder becomes an
# identity.
#
# A-1b, ruled 2026-09-02 (§9.2). SINGLE SOURCE: the list is core's, imported,
# never restated. Two copies of it existed and they had drifted -- this module
# admitted `TODO`, `PENDING_SEAL` and `0`, which core refuses, so the same string
# was a placeholder or an identity depending on which layer happened to look at
# it first. And this layer looks first: `assert_aggregate_names_this_seal` runs
# inside the runner's gate, ahead of the manifest engine, so the WIDER list was
# the effective one. A drifting denylist drifts permissive.
#
# `core` is imported rather than the reverse because the vocabulary belongs to
# the binding contract, not to the runner that consults it.
def placeholder_seal_ids() -> frozenset:
    """core's list, read at CALL time — deliberately not snapshotted at import.

    A module-level `frozenset(_CORE_...)` would satisfy "single source" only
    while somebody keeps typing it that way: a hand-copied literal that happens
    to agree today is behaviourally identical to the import, so no test could
    tell them apart, and the copy is exactly the state this ruling removed.
    Reading at call time makes the dependency real — change core's list and this
    module follows, in the same process — so a copy is a FAILING test rather
    than a code-review opinion.
    """
    from core.b0_l3_lineage_capture import PLACEHOLDER_ROUTE_SEAL_IDS

    return frozenset(PLACEHOLDER_ROUTE_SEAL_IDS)

# Where a module named in an import may live. A file outside these roots is not
# part of this repository's route and is reported rather than silently bound.
# A-1c, ruled 2026-09-02 (§9.3). `research/b0_l2` was HERE and is not any more.
#
# It contributed 0 of the 45 files -- measured, and removing it left the closure
# identical file for file -- so this is not about a file. It is about a door: a
# root means a FUTURE import from L3 into the sealed retrospective line joins the
# prospective route's identity silently, and every later maintenance edit to L2
# would then move the route seal.
#
# Dropping it alone would only reverse which way the silence runs: `_module_file`
# returns None for anything outside these roots and `route_closure_files` skips
# it, so the same import would instead be MISSED. The ruling took the third
# option, so `assert_no_import_escapes_the_roots` exists below and the closure
# refuses rather than shrugs.
MODULE_ROOTS = (
    "",
    os.path.join("research", "b0_l3"),
    os.path.join("research", "b0_l3_runner"),
    os.path.join("research", "b0_checkpoint"),
    os.path.join("research", "b0_materializer"),
)

# The two files a prospective period actually starts from.
ENTRY_POINTS = (
    os.path.join("research", "b0_l3_runner", "run_l3_prospective.py"),
    os.path.join("research", "b0_checkpoint", "portfolio_side.py"),
)

# The leaf producers. Their OUTPUT is bound transitively (leaf payload hash ->
# aggregate payload hash -> attestation), but their CODE is reached by no import
# from the entry points -- a run consumes the leaves, it does not build them.
# Declared as a GLOB rather than a list, and cross-checked against the directory
# by `assert_no_producer_is_unbound`, because a hand-written list is how the
# provisional `REQUIRED_DATASETS` floor lost two families.
SOURCE_PRODUCER_GLOBS = (
    os.path.join("research", "b0_materializer", "build_*_leaf.py"),
    os.path.join("research", "b0_materializer", "build_flat_leaves.py"),
    os.path.join("research", "b0_materializer", "source_ownership_manifest.py"),
)


class RouteSealError(RuntimeError):
    """Fail-loud: the route is not sealed, or not the route that was sealed."""


def _rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), REPO).replace("\\", "/")


def _module_file(module: str):
    """Resolve one import name to a file inside this repository, or to None."""
    parts = module.split(".")
    for root in MODULE_ROOTS:
        candidate = os.path.join(REPO, root, *parts) + ".py"
        if os.path.isfile(candidate):
            return candidate
        package = os.path.join(REPO, root, *parts, "__init__.py")
        if os.path.isfile(package):
            return package
    return None


# Keyed on REPO so a test that repoints it gets its own answer rather than this
# process's first one. Without the cache the scan reran for every unresolved
# import of every file in the closure -- ~900 walks of ~40 directories, which
# took the route-seal test file from 9 seconds to 128.
_SEARCH_ROOTS_CACHE: dict = {}
# Same reason, one level down: the closure walk asks about the same handful of
# stdlib names once per file, and each miss costs a stat against every search
# root. Keyed on (REPO, module) so a repointed REPO is a different question.
_OUTSIDE_ROOTS_CACHE: dict = {}


def _module_search_roots() -> tuple:
    """Repository directories that could host an importable module, DERIVED.

    A directory qualifies if it DIRECTLY holds a `.py` file. Derived from the
    filesystem rather than listed, for the reason A-1b demonstrated one commit
    ago: a hand-maintained list of places to look drifts, and a drifting list of
    places to look drifts permissive -- the module it stops naming is the one
    that then escapes unnoticed.
    """
    cached = _SEARCH_ROOTS_CACHE.get(REPO)
    if cached is not None:
        return cached

    out = []
    for base in ("", "research"):
        base_dir = os.path.join(REPO, base) if base else REPO
        if not os.path.isdir(base_dir):
            continue
        for name in sorted(os.listdir(base_dir)):
            rel = os.path.join(base, name) if base else name
            full = os.path.join(REPO, rel)
            if not os.path.isdir(full) or name.startswith("."):
                continue
            try:
                with os.scandir(full) as it:
                    has_py = any(e.name.endswith(".py") for e in it)
            except OSError:
                continue
            if has_py:
                out.append(rel)
    result = tuple(out)
    _SEARCH_ROOTS_CACHE[REPO] = result
    return result


def _resolve_outside_roots(module: str):
    """The file this module name names in the repo but OUTSIDE `MODULE_ROOTS`.

    None for stdlib and third-party names, which resolve nowhere in the repo and
    are legitimately outside the route -- refusing every unresolved name would
    abort on `import os`. What this finds is the only interesting case: repo
    code the walker would otherwise skip in silence.
    """
    key = (REPO, module)
    if key in _OUTSIDE_ROOTS_CACHE:
        return _OUTSIDE_ROOTS_CACHE[key]

    declared = {os.path.normpath(r) for r in MODULE_ROOTS}
    parts = module.split(".")
    found = None
    for root in _module_search_roots():
        if os.path.normpath(root) in declared:
            continue
        candidate = os.path.join(REPO, root, *parts) + ".py"
        if os.path.isfile(candidate):
            found = candidate
            break
        package = os.path.join(REPO, root, *parts, "__init__.py")
        if os.path.isfile(package):
            found = package
            break
    _OUTSIDE_ROOTS_CACHE[key] = found
    return found


def assert_no_import_escapes_the_roots(path: str, module: str) -> None:
    """A1-c's guard. Repo code the route reaches must be reachable BY the route."""
    escaped = _resolve_outside_roots(module)
    if escaped is None:
        return
    raise RouteSealError(
        "abort: %s imports %r, which resolves to %s -- inside this repository "
        "but outside MODULE_ROOTS, so the closure would skip it and the seal "
        "would bind a route that reaches code it does not name.\n"
        "Silence in either direction is the thing A-1c refused: keeping a root "
        "binds such a module without anyone deciding to, dropping the root "
        "misses it without anyone noticing. Declare the root deliberately, or "
        "do not reach that code from the prospective route."
        % (_rel(path), module, _rel(escaped)))


def _imports(path: str) -> set:
    """Every module name a file imports, in all three import forms."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:                      # relative import
                continue
            if node.module == "core":
                out |= {"core." + a.name for a in node.names}
            elif node.module:
                out.add(node.module)
                # `from l3_snapshot import plan` also reaches `l3_snapshot`; a
                # `from package import module` reaches the submodule too.
                out |= {node.module + "." + a.name for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


def route_closure_files(entry_points=ENTRY_POINTS) -> tuple:
    """Every repository file the prospective route reaches, transitively.

    Derived, not declared. The one thing a derivation cannot see is a producer
    nobody imports, which is why `assert_no_producer_is_unbound` exists beside
    it rather than being folded in: a check that shares its blind spot with the
    thing it checks is not a check.
    """
    seen, queue = set(), []
    for entry in entry_points:
        path = os.path.join(REPO, entry)
        if not os.path.isfile(path):
            raise RouteSealError(
                "abort: route entry point %s does not exist. A closure cannot "
                "start from a file that is not there." % entry)
        queue.append(path)
    while queue:
        path = queue.pop()
        rel = _rel(path)
        if rel in seen:
            continue
        seen.add(rel)
        for module in sorted(_imports(path)):
            found = _module_file(module)
            if found is None:
                assert_no_import_escapes_the_roots(path, module)
                continue
            if _rel(found) not in seen:
                queue.append(found)
    return tuple(sorted(seen))


def source_producer_files() -> tuple:
    """The leaf producers present on disk, from the declared globs."""
    out = set()
    for pattern in SOURCE_PRODUCER_GLOBS:
        for path in glob.glob(os.path.join(REPO, pattern)):
            if os.path.isfile(path):
                out.add(_rel(path))
    return tuple(sorted(out))


def sealed_file_set() -> tuple:
    """The complete set a route seal binds: the derived closure PLUS producers.

    The producers are unioned in rather than expected to appear in the
    derivation, because no import reaches them -- a run CONSUMES leaves, it does
    not build them. Their output is bound transitively (leaf payload hash ->
    aggregate payload hash -> attestation); this is what binds the code.
    """
    return tuple(sorted(set(route_closure_files())
                        | set(source_producer_files())))


def assert_no_producer_is_unbound(bound) -> tuple:
    """Post-condition: no producer on disk is outside the sealed file set.

    A post-condition on the union rather than a check of the derivation, because
    the two share no blind spot: the derivation cannot see an unimported file,
    and this reads the directory.
    """
    producers = set(source_producer_files())
    missing = sorted(producers - set(bound))
    if missing:
        raise RouteSealError(
            "abort: %d source producer(s) are on disk and outside the sealed "
            "file set: %s. A leaf's CONTENT is bound by its payload hash, but "
            "the code that produced it is what a replay would have to re-run."
            % (len(missing), missing))
    return tuple(sorted(producers))


N1_RULING = ("N1-1, ruled 2026-09-02 · "
             "docs/A1N1_L3RouteSeal_AdjudicationOptions_2026-09-01.md §9.4")


def unauthoritative_floor_families() -> tuple:
    """Required dataset families whose DECLARED authority is not AUTHORITATIVE.

    Derived from the declarations, never restated here. That is the whole point
    of gating on it rather than on a prose item in
    `route_closure.still_owed_before_a_seal_may_be_taken`: a sentence somebody
    must remember to delete goes stale in the permissive direction, and this
    repository has already demonstrated it -- that list still carried "MASTER
    FREEZE records v1.32" long after `master_prereg_freeze.json` said 1.37.
    A derived gate opens by itself, on the day the declaration changes, and
    never before.

    Only the flat families carry a per-family declaration (A-4). The other
    producers declare authority per ENTRY, so a family-level statement about
    them would be a claim this function cannot make.
    """
    from route_closure import REQUIRED_DATASET_FLOOR
    import build_flat_leaves as flat

    return tuple(sorted(
        ds for ds in REQUIRED_DATASET_FLOOR
        if ds in flat.FLAT_FAMILIES
        and flat.FLAT_FAMILIES[ds].get("authority") != "AUTHORITATIVE"))


def assert_route_is_sealable() -> dict:
    """The route's own closure module must declare nothing still owed.

    Read from `route_closure.seal_payload()` rather than restated. That list is
    where A2's boundary is maintained, and a second copy of it here would go
    stale in exactly the direction that matters -- claiming sealable when the
    authority still says otherwise.

    N1-1 is checked FIRST and separately, following `route_closure`'s own idiom
    of listing the specification gap ahead of the code items "because no amount
    of implementation closes it". It is not an owed item: nothing anyone builds
    clears it, and it is not this route's boundary to move.
    """
    unauthoritative = unauthoritative_floor_families()
    if unauthoritative:
        raise RouteSealError(
            "abort: %s forbids taking a route seal while a required dataset "
            "family has no authoritative leg. Declared non-AUTHORITATIVE: %s.\n"
            "R-W1-2 gives authority to TEJ, and these families' bytes do not "
            "come from TEJ, so nothing exists to reconcile them against. The "
            "calendar decides WHEN, which decides everything else.\n"
            "This gate is DERIVED from the family declarations in "
            "build_flat_leaves.FLAT_FAMILIES, so it opens when a family "
            "genuinely gains an authoritative leg and not by anyone editing a "
            "list. Relabelling a family to clear it without changing where its "
            "bytes come from is the defect A-4 was written to expose."
            % (N1_RULING, ", ".join(unauthoritative)))

    from route_closure import seal_payload

    payload = seal_payload()
    owed = list(payload.get("still_owed_before_a_seal_may_be_taken") or ())
    if owed:
        raise RouteSealError(
            "abort: research/b0_l3/route_closure.py still declares %d item(s) "
            "owed before a route seal may be taken:\n  - %s\n"
            "That module is A2's boundary. A seal taken while it says this "
            "would bind a route its own closure says is incomplete."
            % (len(owed), "\n  - ".join(str(x)[:160] for x in owed)))
    return payload


# N-2, ruled 2026-09-02 (§9.5 of the A-1/N-1 options document). A route seal
# binds CODE. It does not bind the bytes any particular run reads, and it may
# not: `data/b0/trading_calendar.csv` gains a row every trading day, so binding
# it would expire the seal daily and contradict
# `PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE`.
#
# The ruling took disclosure over binding, and required the disclosure to sit
# somewhere a reader of the SEAL can see it rather than in a docstring, since
# the failure it guards against is somebody comparing leaf hashes across clones
# and having no way to learn that a leaf is no longer purely a function of the
# archives. So it is a field, and being a field it is inside the seal's own
# digest.
SEAL_BINDING_SCOPE = "PRODUCTION_ROUTE_CODE_ONLY"
SEAL_BINDING_DISCLOSURE = (
    "This seal binds the CODE of the production route: the derived import "
    "closure from `entry_points`, plus the source producers no import reaches. "
    "It does NOT bind data. The bytes a given run reads are bound by that run's "
    "leaf payload hashes and by the aggregate that indexes them, which live in "
    "the run's own manifests and receipts, not here. Two runs of one sealed "
    "route over different source bytes are the same route and different runs -- "
    "and a leaf hash that differs across clones is therefore NOT evidence that "
    "the route differs.")


def route_seal_payload() -> dict:
    """Everything a route seal binds, ready to be hashed. Writes nothing."""
    from route_closure import (
        REQUIRED_DATASET_FLOOR, production_route_code_closure,
    )

    closure_payload = assert_route_is_sealable()
    files = sealed_file_set()
    producers = assert_no_producer_is_unbound(files)
    return {
        "contract_version": ROUTE_SEAL_CONTRACT_VERSION,
        "closure_kind": "PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE",
        "binding_scope": SEAL_BINDING_SCOPE,
        "binding_disclosure": SEAL_BINDING_DISCLOSURE,
        "entry_points": [e.replace("\\", "/") for e in ENTRY_POINTS],
        "core_decision_closure": list(production_route_code_closure()),
        "required_dataset_floor": list(REQUIRED_DATASET_FLOOR),
        "route_closure_code_closure_size":
            closure_payload["code_closure_size"],
        "source_producers": list(producers),
        "file_count": len(files),
        "files": {path: file_sha256(os.path.join(REPO, path))
                  for path in files},
    }


ROUTE_SEAL_ID_PREFIX = "L3SEAL-"


def route_seal_id(payload) -> str:
    """Content-addressed, like the baseline seal. The payload IS the identity.

    A-1a, ruled 2026-09-02 (§9.1). The DIGEST is this module's: the canonical
    hash of the payload with its own id removed. The FORM is core's:
    `L3SEAL-<64 hex>`, matching `core.b0_l3_lineage_capture.ROUTE_SEAL_ID_RE`.

    The two modules had incompatible notions of "content-addressed" and each was
    internally consistent, so nothing failed -- lock B refused every production
    manifest before the disagreement could surface. This module hashed the
    PAYLOAD; core recomputed the sha256 of the seal FILE, which can never equal
    a payload hash, because the file additionally carries `route_seal_id` and is
    serialised with `indent=1`. Adding the prefix alone would have satisfied
    core's second layer and still failed its third. The ruling kept this
    module's digest and core's form, so core's third layer now recomputes the
    payload hash instead of hashing the bytes.
    """
    return ROUTE_SEAL_ID_PREFIX + canonical_sha256(
        {k: v for k, v in payload.items() if k != "route_seal_id"})


def seal_path(seal_id: str) -> str:
    if not seal_id or os.path.basename(seal_id) != seal_id:
        raise RouteSealError("abort: %r is not a single-component seal id"
                             % seal_id)
    return os.path.join(SEAL_ROOT, seal_id + ".json")


def write_route_seal() -> tuple:
    """Take the route seal. O_EXCL, content-addressed, never overwritten.

    NOT called by the runner, and not reachable from any of its modes. Taking
    the first L3 route seal fixes what "the production route" means for every
    prospective observation afterwards; it is a separately-authorised act, not
    a side effect of running a period.
    """
    payload = route_seal_payload()
    ident = route_seal_id(payload)
    payload = {**payload, "route_seal_id": ident}
    os.makedirs(SEAL_ROOT, exist_ok=True)
    path = seal_path(ident)
    body = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
            + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                     | getattr(os, "O_BINARY", 0))
    except FileExistsError as exc:
        raise RouteSealError(
            "abort: %s already exists. A route seal is content-addressed, so a "
            "collision means this exact route is already sealed." % path
        ) from exc
    try:
        os.write(fd, body)
    finally:
        os.close(fd)
    return ident, path


def load_route_seal(seal_id: str) -> dict:
    path = seal_path(seal_id)
    if not os.path.exists(path):
        raise RouteSealError(
            "abort: no route seal at %s. The execute gate requires a seal that "
            "content-binds the whole A2 route; there is no default and no "
            "'latest'." % path)
    with open(path, encoding="utf-8") as fh:
        seal = json.load(fh)
    recomputed = route_seal_id(seal)
    if recomputed != seal.get("route_seal_id") or recomputed != seal_id:
        raise RouteSealError(
            "abort: %s does not hash to its own filename (recomputed %s). The "
            "seal has been altered since it was taken."
            % (path, recomputed[:16]))
    return seal


def assert_seal_binds_current_route(seal) -> dict:
    """Every sealed file must still hash to the sealed value, and none may be new.

    Both directions. A file that changed is the obvious failure; a file the
    closure now reaches and the seal never bound is the one that looks like
    nothing happened.
    """
    if seal.get("contract_version") != ROUTE_SEAL_CONTRACT_VERSION:
        raise RouteSealError(
            "abort: seal contract %r, this verifier speaks %r"
            % (seal.get("contract_version"), ROUTE_SEAL_CONTRACT_VERSION))
    sealed = dict(seal.get("files") or {})
    current = sealed_file_set()

    missing = sorted(p for p in sealed if not os.path.isfile(
        os.path.join(REPO, p)))
    if missing:
        raise RouteSealError(
            "abort: %d sealed file(s) are gone: %s" % (len(missing), missing))
    drifted = sorted(p for p in sealed
                     if file_sha256(os.path.join(REPO, p)) != sealed[p])
    unsealed = sorted(set(current) - set(sealed))
    dropped = sorted(set(sealed) - set(current))
    if drifted or unsealed:
        raise RouteSealError(
            "abort: the working tree is not the sealed route.\n"
            "  changed since the seal (%d): %s\n"
            "  reached now and never sealed (%d): %s\n"
            "A prospective observation binds the code that produced it; "
            "neither of these may be repaired by re-sealing after the fact."
            % (len(drifted), drifted[:8], len(unsealed), unsealed[:8]))
    return {"sealed_files": len(sealed), "verified_files": len(sealed),
            "sealed_but_no_longer_reached": dropped}


def assert_aggregate_names_this_seal(aggregate, seal_id: str) -> str:
    """The run's sources must be tied to THIS route, not to a placeholder.

    `source_ownership_manifest.assemble_aggregate` requires `route_seal_id` to
    be non-empty and checks nothing else, so `PENDING` -- which is what every
    fixture and every pre-seal harvest uses -- passes it. Refusing placeholders
    is therefore this module's job, not the manifest's.
    """
    declared = str((aggregate or {}).get("route_seal_id", "")).strip()
    if not declared or declared.upper() in placeholder_seal_ids():
        raise RouteSealError(
            "abort: the source aggregate declares route_seal_id=%r, which "
            "names no route. `assemble_aggregate` only requires it to be "
            "non-empty, so a placeholder reaches this far; a run whose sources "
            "are tied to no route cannot be a prospective observation of one."
            % declared)
    if declared != str(seal_id):
        raise RouteSealError(
            "abort: the sources were harvested against route seal %s and this "
            "run is executing route seal %s. The decision would be made by "
            "code the source set was never tied to."
            % (declared[:16], str(seal_id)[:16]))
    return declared


__all__ = [
    "N1_RULING",
    "ROUTE_SEAL_ID_PREFIX",
    "assert_no_import_escapes_the_roots",
    "SEAL_BINDING_SCOPE",
    "SEAL_BINDING_DISCLOSURE",
    "unauthoritative_floor_families",
    "ENTRY_POINTS",
    "MODULE_ROOTS",
    "placeholder_seal_ids",
    "ROUTE_SEAL_CONTRACT_VERSION",
    "SEAL_ROOT",
    "SOURCE_PRODUCER_GLOBS",
    "RouteSealError",
    "assert_aggregate_names_this_seal",
    "assert_no_producer_is_unbound",
    "assert_route_is_sealable",
    "assert_seal_binds_current_route",
    "load_route_seal",
    "route_closure_files",
    "sealed_file_set",
    "route_seal_id",
    "route_seal_payload",
    "seal_path",
    "source_producer_files",
    "write_route_seal",
]
