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
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.b0_canonical_hash import canonical_sha256, file_sha256   # noqa: E402

ROUTE_SEAL_CONTRACT_VERSION = "b0_l3_route_seal@2"
ROUTE_SEAL_ID_PREFIX = "L3SEAL-"
RATIFIED_ROUTE_SEAL_CONTRACT_STATUS = "RATIFIED"
DERIVED_SEAL_FIELDS = frozenset({
    "route_seal_id", "route_seal_payload_sha256", "route_seal_raw_sha256",
})
SEAL_ROOT = os.path.join(REPO, "artifacts", "l3_route_seal", "seals")

# A `route_seal_id` that names no seal. `source_ownership_manifest` accepts any
# non-empty string, so these have to be refused HERE or a placeholder becomes an
# identity.
PLACEHOLDER_SEAL_IDS = frozenset({
    "PENDING", "TBD", "NONE", "NULL", "PLACEHOLDER", "UNSEALED", "N/A", "-",
})

# Where a module named in an import may live. A file outside these roots is not
# part of this repository's route and is reported rather than silently bound.
MODULE_ROOTS = (
    "",
    os.path.join("research", "b0_l3"),
    os.path.join("research", "b0_l3_runner"),
    os.path.join("research", "b0_checkpoint"),
    os.path.join("research", "b0_materializer"),
    os.path.join("research", "b0_l2"),
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


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", REPO, *args], text=True, encoding="utf-8",
        errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False)
    if proc.returncode:
        raise RouteSealError(
            "abort: could not establish committed repository identity with "
            "git %s: %s" % (" ".join(args), proc.stderr.strip()[:500]))
    return proc.stdout


def current_repo_identity() -> dict:
    """Committed, clean repository identity used by the seal and verifier."""
    commit = _git("rev-parse", "HEAD").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RouteSealError("abort: git HEAD is not a full commit sha: %r" % commit)
    tracked = _git("status", "--porcelain=v1", "--untracked-files=no")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    if tracked.strip() or untracked.strip():
        raise RouteSealError(
            "abort: a route seal requires a clean committed repository "
            "(tracked_dirty=%s, untracked_count=%d)."
            % (bool(tracked.strip()), len(untracked.splitlines())))
    tree_inventory = _git("ls-tree", "-r", "--full-tree", "HEAD")
    return {
        "repo_commit_sha": commit,
        "tracked_tree_sha256": canonical_sha256(tree_inventory),
        "tracked_clean": True,
        "untracked_clean": True,
        "untracked_inventory_sha256": canonical_sha256([]),
    }


def verified_capture_binding(capture_record_path: str) -> dict:
    """Verify the canonical capture record and return stable binding fields."""
    try:
        from core.b0_l3_lineage_capture import load_and_verify_capture_record
        loaded = load_and_verify_capture_record(capture_record_path)
    except Exception as exc:
        raise RouteSealError(
            "abort: route seal cannot bind an unverified lineage capture: %s"
            % exc) from exc
    record = loaded["record"]
    return {
        "lineage_id": record["lineage_id"],
        "capture_run_id": record["capture_run_id"],
        "capture_as_of": record["as_of"],
        "lineage_price_floor": record["lineage_price_floor"],
        "capture_record_payload_sha256": loaded["payload_sha256"],
        "capture_record_raw_sha256": loaded["raw_sha256"],
    }


# --- P1-8 - RATIFICATION PROTECTED THE WRITER AND NOBODY HAS TO BE THE WRITER ----
#
# `assert_route_seal_contract_ratified()` was called from `write_route_seal` and
# from nowhere else. `write_route_seal` is deliberately unreachable from the
# runner, which means the ONE door the gate stood in front of is the one door
# nobody has to walk through. Everything downstream -- reading a seal file,
# verifying it against the working tree, matching it to a source aggregate,
# copying its fields into a period receipt -- asked nothing. A hand-written,
# internally self-consistent seal file plus an aggregate naming it was therefore
# LOADED AND HONOURED while the contract was still `NOT_YET_RATIFIED`. Measured,
# not reasoned: all four consumer calls returned successfully on such a file.
#
# THIS IS C-72'S SHAPE, ONE LAYER OUT. C-72's first landing was rejected with
# "the gate was added to the core API, but the real opening boundary was never
# asked": `assert_reopening_admissible` existed, and `scripts/b0_open_l2.py` and
# `scripts/b0_baseline_seal.py` -- the entry points that actually created run
# directories, opening claims and seals -- never called it. The ruling (Master
# section 9.6e, "the gate must be set at the real opening boundary") fixed it by
# putting the guard at the real boundaries, BEFORE anything else those entry
# points do, and pinning with AST that they ask it.
#
# So the gate now stands at both ends of the contract, in three places:
#
#   WRITER    `write_route_seal`                     -- unchanged, still first
#   READER    `load_route_seal`                      -- the only door to a seal
#                                                       ARTEFACT
#   EXECUTION `run_l3_prospective.assert_route_execution_admissible`
#                                                    -- the real boundary: the
#                                                       function that decides
#                                                       whether the first
#                                                       prospective observation
#                                                       may happen at all
#
# And, following 9.6e(b), the MECHANISM stays separately reachable so it can be
# tested without a fictitious ratification: `read_seal_artifact`,
# `assert_seal_binds_current_route`, `assert_aggregate_names_this_seal`,
# `assert_declared_floor_is_the_captured_floor`, `route_seal_receipt_fields` and
# `route_seal_payload` answer "is this seal well-formed / does it bind this tree
# / does it match these sources / does it match this floor" and never answer
# "may a seal be honoured at all". A test that needed the gate widened in order
# to reach the mechanism would be a test that widens the gate.
#
# This RATIFIES NOTHING. `ROUTE_SEAL_CONTRACT_STATUS` is still
# `NOT_YET_RATIFIED` (A-1, an open adjudication); the change is that the
# fail-closed state is now actually closed at the doors that get used.

# The boundaries required to ask the gate before doing anything else. Declared
# as data so the tests can pin them with AST rather than by reading a comment.
RATIFICATION_GATED_BOUNDARIES = (
    "write_route_seal",
    "load_route_seal",
)


def assert_route_seal_contract_ratified() -> str:
    """No seal may be TAKEN, READ or HONOURED until the contract is ratified."""
    from core.b0_l3_lineage_capture import ROUTE_SEAL_CONTRACT_STATUS
    if ROUTE_SEAL_CONTRACT_STATUS != RATIFIED_ROUTE_SEAL_CONTRACT_STATUS:
        raise RouteSealError(
            "abort: route-seal contract status is %r, not %r; seal creation "
            "AND the honouring of an existing seal both remain fail-closed. A "
            "seal file that hashes to its own name is still only a well-formed "
            "artefact of a contract nobody has ratified, and anyone can write "
            "one."
            % (ROUTE_SEAL_CONTRACT_STATUS,
               RATIFIED_ROUTE_SEAL_CONTRACT_STATUS))
    return ROUTE_SEAL_CONTRACT_STATUS


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
            if found and _rel(found) not in seen:
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


def assert_route_is_sealable() -> dict:
    """The route's own closure module must declare nothing still owed.

    Read from `route_closure.seal_payload()` rather than restated. That list is
    where A2's boundary is maintained, and a second copy of it here would go
    stale in exactly the direction that matters -- claiming sealable when the
    authority still says otherwise.
    """
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


def route_seal_payload(capture_record_path: str) -> dict:
    """Everything a route seal binds, ready to be hashed. Writes nothing."""
    from route_closure import (
        REQUIRED_DATASET_FLOOR, production_route_code_closure,
    )

    closure_payload = assert_route_is_sealable()
    files = sealed_file_set()
    if not files:
        raise RouteSealError(
            "abort: the exact route closure is empty; an empty seal binds no "
            "executable route.")
    producers = assert_no_producer_is_unbound(files)
    capture = verified_capture_binding(capture_record_path)
    repo = current_repo_identity()
    return {
        "contract_version": ROUTE_SEAL_CONTRACT_VERSION,
        "closure_kind": "PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE",
        **capture,
        **repo,
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


def route_seal_id(payload) -> str:
    """`L3SEAL-<payload digest>`; derived fields never feed their own ID."""
    body = {k: v for k, v in payload.items() if k not in DERIVED_SEAL_FIELDS}
    return ROUTE_SEAL_ID_PREFIX + canonical_sha256(body)


def seal_path(seal_id: str) -> str:
    if not re.fullmatch(r"L3SEAL-[0-9a-f]{64}", str(seal_id or "")) or \
            os.path.basename(seal_id) != seal_id:
        raise RouteSealError("abort: %r is not a single-component seal id"
                             % seal_id)
    return os.path.join(SEAL_ROOT, seal_id + ".json")


def write_route_seal(capture_record_path: str) -> tuple:
    """Take the route seal. O_EXCL, content-addressed, never overwritten.

    NOT called by the runner, and not reachable from any of its modes. Taking
    the first L3 route seal fixes what "the production route" means for every
    prospective observation afterwards; it is a separately-authorised act, not
    a side effect of running a period.
    """
    # This is deliberately the first operation: an unratified contract may not
    # create directories, inspect a candidate capture, or emit partial output.
    assert_route_seal_contract_ratified()
    payload = route_seal_payload(capture_record_path)
    ident = route_seal_id(payload)
    payload_digest = ident[len(ROUTE_SEAL_ID_PREFIX):]
    payload = {**payload, "route_seal_id": ident,
               "route_seal_payload_sha256": payload_digest}
    os.makedirs(SEAL_ROOT, exist_ok=True)
    path = seal_path(ident)
    body = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
            + "\n").encode("utf-8")
    # P2-11. Same bytes, same refusal on a taken path; the difference is that
    # the seal file appears complete or not at all. A zero-byte seal at a
    # content-addressed path would be permanently unwritable, and a route seal
    # is exactly the artefact nobody can re-take under a different name.
    from core.b0_l3_lineage_capture import publish_bytes_exclusively

    try:
        publish_bytes_exclusively(path, body)
    except FileExistsError as exc:
        raise RouteSealError(
            "abort: %s already exists. A route seal is content-addressed, so a "
            "collision means this exact route is already sealed." % path
        ) from exc
    return ident, path


def read_seal_artifact(seal_id: str) -> dict:
    """MECHANISM: is there a seal file at this id, and does it hash to its name?

    Separated from `load_route_seal` for 9.6e(b)'s reason. This answers "is this
    artefact well-formed"; it never answers "may a seal be honoured", which is
    the gate's question and the gate's alone. Keeping the two apart is what lets
    the well-formedness tests keep running without any test needing the
    ratification gate widened in order to reach them.
    """
    path = seal_path(seal_id)
    if not os.path.exists(path):
        raise RouteSealError(
            "abort: no route seal at %s. The execute gate requires a seal that "
            "content-binds the whole A2 route; there is no default and no "
            "'latest'." % path)
    with open(path, encoding="utf-8") as fh:
        seal = json.load(fh)
    recomputed = route_seal_id(seal)
    expected_payload = recomputed[len(ROUTE_SEAL_ID_PREFIX):]
    if recomputed != seal.get("route_seal_id") or recomputed != seal_id or \
            seal.get("route_seal_payload_sha256") != expected_payload:
        raise RouteSealError(
            "abort: %s does not hash to its own filename (recomputed %s). The "
            "seal has been altered since it was taken."
            % (path, recomputed[:16]))
    return seal


def load_route_seal(seal_id: str) -> dict:
    """The only door to a seal ARTEFACT. The gate first, then the mechanism.

    P1-8. Ratification is asked HERE and not only in `write_route_seal`, because
    the writer is deliberately unreachable from the runner and the reader is
    not. Anyone can hand-write a JSON file that hashes to its own name; what
    they cannot do is make an unratified contract admit it.
    """
    assert_route_seal_contract_ratified()
    return read_seal_artifact(seal_id)


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
    if not sealed or seal.get("file_count") != len(sealed):
        raise RouteSealError(
            "abort: the route seal's exact file set is empty or its declared "
            "file_count disagrees with the bound mapping.")
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
    if drifted or unsealed or dropped:
        raise RouteSealError(
            "abort: the working tree is not the sealed route.\n"
            "  changed since the seal (%d): %s\n"
            "  reached now and never sealed (%d): %s\n"
            "  sealed but no longer reached (%d): %s\n"
            "A prospective observation binds the code that produced it; "
            "none of these may be repaired by re-sealing after the fact."
            % (len(drifted), drifted[:8], len(unsealed), unsealed[:8],
               len(dropped), dropped[:8]))
    current_repo = current_repo_identity()
    bound_repo = {k: seal.get(k) for k in current_repo}
    if bound_repo != current_repo:
        raise RouteSealError(
            "abort: the current committed repository identity is not the "
            "identity bound by the route seal.")
    return {"sealed_files": len(sealed), "verified_files": len(sealed),
            "sealed_but_no_longer_reached": dropped}


def route_seal_receipt_fields(seal: dict, *, raw_sha256: str) -> dict:
    """Exact binding fields a period receipt must copy from a verified seal."""
    if not re.fullmatch(r"[0-9a-f]{64}", str(raw_sha256 or "")):
        raise RouteSealError(
            "abort: route_seal_raw_sha256 must be a full sha256 digest")
    ident = route_seal_id(seal)
    if seal.get("route_seal_id") != ident:
        raise RouteSealError("abort: receipt source does not re-derive its seal id")
    return {
        "lineage_id": seal["lineage_id"],
        "capture_record_payload_sha256":
            seal["capture_record_payload_sha256"],
        "capture_record_raw_sha256": seal["capture_record_raw_sha256"],
        "route_seal_id": ident,
        "route_seal_payload_sha256": ident[len(ROUTE_SEAL_ID_PREFIX):],
        "route_seal_raw_sha256": raw_sha256,
        "route_repo_commit_sha": seal["repo_commit_sha"],
        "route_tracked_tree_sha256": seal["tracked_tree_sha256"],
    }


# --- P1-7 - THE SEAL CARRIES THE FLOOR AND NOTHING COMPARED THE TWO -------------
#
# `verified_capture_binding` puts `lineage_price_floor` into the seal straight
# out of the verified capture record, so the seal has always KNOWN the floor.
# The runner nevertheless took `--lineage-price-floor` from its caller and
# handed it to `l3_assemble` without ever comparing the two.
#
# The floor is not bookkeeping. C-68 froze `price_span[0]` as the
# lineage-inception corpus coverage floor; it feeds `spell_start`, `spell_start`
# decides via `n_in_spell` whether ADV20 and sigma20d go NA, and O-G blanks
# month-end prices on the same basis. A floor one session away from the captured
# one is a DIFFERENT ELIGIBLE POPULATION and a different state hash, arrived at
# silently, in a run whose receipt would say it was bound to that capture.
#
# Declaration plus verification, not derivation: the caller still has to state
# the floor it believes it is running on -- the same shape as
# `--prior-source-manifest` -- and the seal decides whether it was right.

def assert_declared_floor_is_the_captured_floor(seal, declared_floor) -> str:
    """The section 19 / C-68 floor a run assembles on must be the CAPTURED one.

    Reads the seal's `lineage_price_floor`, which arrived there through
    `verified_capture_binding` -> `load_and_verify_capture_record`, so this
    compares against the capture record rather than against a copy of it.
    """
    captured = str((seal or {}).get("lineage_price_floor") or "").strip()
    if not captured:
        raise RouteSealError(
            "abort: the route seal carries no lineage_price_floor, so nothing "
            "binds the floor this run would assemble on. A seal that cannot "
            "name the captured floor cannot admit a caller's.")
    declared = str(declared_floor or "").strip()
    if not declared:
        raise RouteSealError(
            "abort: no --lineage-price-floor was declared, and it has no "
            "default. The capture bound to this seal froze %s; a run must "
            "state the floor it believes it is executing on so that the seal "
            "can refuse a different one." % captured)
    if declared != captured:
        raise RouteSealError(
            "abort: this run declares --lineage-price-floor %s and the lineage "
            "capture bound to route seal %s froze %s. The floor sets "
            "spell_start, spell_start decides via n_in_spell whether ADV20 and "
            "sigma20d go NA and whether O-G blanks month-end prices, so the "
            "two floors select DIFFERENT ELIGIBLE POPULATIONS. C-68 froze this "
            "value at lineage inception; it is not a per-run argument."
            % (declared, str((seal or {}).get("route_seal_id", ""))[:16],
               captured))
    return captured


def assert_aggregate_names_this_seal(aggregate, seal_id: str) -> str:
    """The run's sources must be tied to THIS route, not to a placeholder.

    `source_ownership_manifest.assemble_aggregate` requires `route_seal_id` to
    be non-empty and checks nothing else, so `PENDING` -- which is what every
    fixture and every pre-seal harvest uses -- passes it. Refusing placeholders
    is therefore this module's job, not the manifest's.
    """
    declared = str((aggregate or {}).get("route_seal_id", "")).strip()
    if not declared or declared.upper() in PLACEHOLDER_SEAL_IDS:
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
    "ENTRY_POINTS",
    "MODULE_ROOTS",
    "PLACEHOLDER_SEAL_IDS",
    "RATIFICATION_GATED_BOUNDARIES",
    "RATIFIED_ROUTE_SEAL_CONTRACT_STATUS",
    "ROUTE_SEAL_CONTRACT_VERSION",
    "ROUTE_SEAL_ID_PREFIX",
    "SEAL_ROOT",
    "SOURCE_PRODUCER_GLOBS",
    "RouteSealError",
    "assert_aggregate_names_this_seal",
    "assert_declared_floor_is_the_captured_floor",
    "assert_no_producer_is_unbound",
    "assert_route_is_sealable",
    "assert_route_seal_contract_ratified",
    "assert_seal_binds_current_route",
    "current_repo_identity",
    "load_route_seal",
    "read_seal_artifact",
    "route_closure_files",
    "sealed_file_set",
    "route_seal_id",
    "route_seal_payload",
    "route_seal_receipt_fields",
    "seal_path",
    "source_producer_files",
    "verified_capture_binding",
    "write_route_seal",
]
