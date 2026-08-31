"""§20 · C-70 — the contract that turns a computed floor into a lineage fact.

§19 / C-68 ruled WHAT `price_span[0]` is: a corpus coverage floor captured once
at lineage inception and frozen for that lineage. It did not say how a captured
number becomes irrevocable, and until it does the route can compute a floor but
cannot own one. That gap is this module.

    price leaf          RUN-scoped. One run's declared sources, one manifest.
    capture record      LINEAGE-scoped. Written once, never overwritten, and it
                        binds backwards to the complete price leaf that produced
                        the floor.

THE CHAIN IS ONE-WAY, AND THAT IS THE WHOLE POINT (`BINDING_CHAIN`):

    v1.35/C-70 capture authority
        -> lineage_price_floor capture record
            -> final route seal
                -> period receipts

The obvious-looking alternative — make the capture bind the route seal — is a
deadlock: the route seal must bind the capture record, so each would wait for the
other. A capture therefore binds the specification and the repo instead: Master
version + spec hash + freeze hash, this floor-capture code closure, the price
leaf and aggregate manifest hashes, and a committed repo identity. The route seal
later binds the capture record's hash, and every period receipt names the lineage
and that same hash.

IDENTITY IS CONTENT-DERIVED, AND THE HASH MAY NOT EAT ITSELF.
`lineage_id` is derived from `lineage_basis` — the capture facts WITHOUT the
lineage id and without any record-level hash. Deriving it from the finished
record would be circular. The first 16 hex are a DISPLAY alias only; the
canonical identity is always the full 64.

NO DATE HERE IS NORMATIVE. `DIAGNOSTIC_EXPECTED_FLOOR` is a stop-check inherited
from §19.7, not the frozen value: a capture that disagrees with it refuses to
create anything, and the run-scoped evidence of that refusal is preserved.
"""

from __future__ import annotations

import errno
import os
import re
import tempfile

CONTRACT_VERSION = "L3_LINEAGE_FLOOR_CAPTURE_CONTRACT_V1"

# ASCII on purpose (a hashed declaration one console codec away from unreadable
# is not evidence). Reads as: Master v1.35, closure C-70, section 19+1.
CAPTURE_AUTHORITY = "MASTER_V1_35_C70_SECTION_20_CAPTURE_AUTHORITY"

BINDING_CHAIN: tuple[str, ...] = (
    "capture_authority", "lineage_price_floor_capture_record",
    "final_route_seal", "period_receipt",
)

# §19.7. The value a capture must AGREE WITH before it may create anything —
# never the value it may adopt. Diagnostic provenance: M1 (2026-08-27), reader
# semantics replicated without manifest sha verification.
DIAGNOSTIC_EXPECTED_FLOOR = "2004-01-02"


class LineageCaptureError(RuntimeError):
    """Fail-loud: a capture may not become a lineage fact on these terms."""


# --- P2-11 · PUBLICATION IS A RENAME, NOT A CLAIM FOLLOWED BY A WRITE -------------
#
# Every immutable record in this route used to be published in two steps:
#
#     fd = os.open(final_path, O_CREAT | O_EXCL)   # claim
#     ...write the bytes into it...                # publish
#
# The claim is atomic; the pair is not. A crash, a kill, a full disk or an
# exception raised by the byte producer between the two leaves a ZERO-BYTE FILE
# AT THE FINAL PATH -- and because every one of these records is immutable by
# design, the next attempt finds the path taken and aborts. The failure mode is
# therefore UNRECOVERABLE rather than retryable: the period can never be written
# again under that name, and nothing on disk says why. Measured, not reasoned:
# the interrupted attempt leaves 0 bytes and the retry aborts permanently.
#
# It is also a visibility defect. Between the claim and the last byte the final
# path exists and is readable, so a concurrent reader -- another leaf builder,
# the aggregate barrier, an operator -- can open a half-written or empty record
# and get a JSON decode error attributed to the wrong cause.
#
# The publication below writes into a hidden temporary IN THE SAME DIRECTORY
# (same filesystem, so the rename is a metadata operation), flushes and fsyncs
# it, and only then makes it visible under its final name with an atomic
# NO-REPLACE rename. The final path therefore only ever exists complete.
#
# TWO PROPERTIES THAT MUST BOTH SURVIVE, AND DO:
#
#   EXCLUSIVITY   publishing over an existing final path still FAILS. The
#                 no-replace rename is the guarantee, not the early existence
#                 check above it: the check is a cheap courtesy that closes no
#                 race, the rename closes it. `FileExistsError` is raised
#                 rather than a module-specific error so that every caller can
#                 keep translating it into the exact refusal it already wrote.
#
#   BYTE IDENTITY the bytes are produced by whatever primitive already produced
#                 them -- S-5 deliberately delegated decision-record bytes to
#                 `core.b0_master_prereg.write_provenance_json` so that record
#                 content stayed byte-identical, and that module is pinned. The
#                 writer is therefore a CALLBACK handed a path: the same
#                 primitive writes the same bytes, and this function only
#                 changes WHICH NAME they are written under first.
#
# What is deliberately NOT done: falling back to a replacing rename. On a
# filesystem that offers no no-replace primitive this refuses, because a
# replacing publication would silently overwrite a frozen record -- exactly the
# thing exclusivity exists to prevent.

PUBLICATION_IS_ATOMIC_NO_REPLACE = True
PARTIAL_PUBLICATION_SUFFIX = ".partial"


def _fsync_file(path: str) -> None:
    """Force this file's bytes to the device before it is given its real name."""
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(directory: str) -> bool:
    """Force the rename itself to the device. Not available on every platform."""
    if os.name == "nt":
        return False
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return False
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def rename_no_replace(source: str, destination: str) -> None:
    """Publish `source` as `destination`, or raise. NEVER replaces.

    `os.rename` is no-replace on Windows and SILENTLY REPLACING on POSIX, so it
    cannot be used unguarded: the same call would enforce exclusivity on one
    platform and destroy it on the other. `os.link` is atomic and fails with
    `FileExistsError` when the destination is taken, which is the POSIX half.
    """
    if os.name == "nt":
        os.rename(source, destination)
        return
    try:
        os.link(source, destination)
    except FileExistsError:
        raise
    except OSError as exc:
        raise LineageCaptureError(
            "abort: this filesystem offers no no-replace publication "
            "primitive (os.link -> %s). Publishing with a replacing rename "
            "would overwrite a record that is immutable by contract, so the "
            "publication refuses rather than degrading to one." % exc) from exc
    os.unlink(source)


def publish_exclusively(path: str, writer):
    """Write via a hidden same-directory temporary, then publish atomically.

    `writer(temporary_path)` produces the bytes and returns whatever the caller
    wants back (the blob, for the primitives that already returned one). The
    final path appears complete or not at all, and a taken final path raises
    `FileExistsError` for the caller to translate.
    """
    absolute = os.path.abspath(path)
    directory, base = os.path.dirname(absolute), os.path.basename(absolute)
    if not base:
        raise LineageCaptureError(
            "abort: %r names no file to publish" % (path,))
    os.makedirs(directory, exist_ok=True)
    # A cheap early refusal so the common collision costs no temporary file.
    # It closes no race and is NOT the guarantee -- the rename below is.
    if os.path.lexists(absolute):
        raise FileExistsError(errno.EEXIST, "File exists", absolute)
    fd, temporary = tempfile.mkstemp(
        prefix="." + base + ".", suffix=PARTIAL_PUBLICATION_SUFFIX,
        dir=directory)
    os.close(fd)
    try:
        produced = writer(temporary)
        _fsync_file(temporary)
        rename_no_replace(temporary, absolute)
    except BaseException:
        # The temporary is the only thing this function created; a failed
        # publication leaves the directory exactly as it found it.
        try:
            if os.path.lexists(temporary):
                os.unlink(temporary)
        except OSError:
            pass
        raise
    _fsync_directory(directory)
    return produced


def publish_bytes_exclusively(path: str, blob: bytes) -> bytes:
    """`publish_exclusively` for callers that already hold the exact bytes."""
    def _write(temporary: str) -> bytes:
        with open(temporary, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        return blob

    return publish_exclusively(path, _write)


# --- manifest purposes ----------------------------------------------------------
#
# One manifest shape, two contracts. Stated as data because the difference is
# exactly what a placeholder seal id hides.

PURPOSE_CAPTURE = "LINEAGE_FLOOR_CAPTURE"
PURPOSE_PRODUCTION = "PRODUCTION_RUN"
# A run that reads sources to check something — a reader fixture, an assembly
# parity check — is neither of the above. Before this existed such runs borrowed
# the capture purpose, which made every diagnostic look like a lineage event.
PURPOSE_DIAGNOSTIC = "UNSEALED_DIAGNOSTIC"
MANIFEST_PURPOSES: tuple[str, ...] = (
    PURPOSE_CAPTURE, PURPOSE_PRODUCTION, PURPOSE_DIAGNOSTIC)

DIAGNOSTIC_EVIDENCE_CLASS = "NOT_L3_EVIDENCE"

# The seal contract does not exist yet, and "not in a denylist" is not a format.
# Until a ratified content-addressed seal lands, PRODUCTION_RUN fails CLOSED.
ROUTE_SEAL_CONTRACT_STATUS = "NOT_YET_RATIFIED"
ROUTE_SEAL_ID_RE = re.compile(r"^L3SEAL-[0-9a-f]{64}$")

# A seal id is either a real seal or it is nothing. These are the strings that
# have been used as "not yet" in this project and in most others; every one of
# them is a binding that looks satisfied.
PLACEHOLDER_ROUTE_SEAL_IDS: tuple[str, ...] = (
    "", "PENDING", "PENDING_SEAL", "TBD", "TODO", "NONE", "NULL", "N/A",
    "PLACEHOLDER", "UNSEALED", "0", "-",
)


def assert_manifest_binding(purpose: str, *, route_seal_id=None,
                            capture_authority=None, lineage_id=None,
                            capture_record_sha256=None,
                            route_seal_artifact=None) -> str:
    """What a manifest of each purpose must be tied to. Returns the purpose."""
    if purpose == PURPOSE_DIAGNOSTIC:
        bound = [n for n, v in (("route_seal_id", route_seal_id),
                                ("capture_authority", capture_authority),
                                ("lineage_id", lineage_id),
                                ("capture_record_sha256", capture_record_sha256))
                 if v is not None]
        if bound:
            raise LineageCaptureError(
                "abort: an %s manifest may not bind %s. It is %s: a run that "
                "reads sources to check something, and dressing it in a "
                "lineage's bindings is how a diagnostic becomes mistaken for "
                "one." % (PURPOSE_DIAGNOSTIC, bound, DIAGNOSTIC_EVIDENCE_CLASS))
        return purpose

    if purpose not in MANIFEST_PURPOSES:
        raise LineageCaptureError(
            "abort: manifest purpose %r is not one of %s. A run without a "
            "declared purpose is a run whose binding rules are unknown."
            % (purpose, MANIFEST_PURPOSES))

    if purpose == PURPOSE_CAPTURE:
        if route_seal_id is not None:
            raise LineageCaptureError(
                "abort: a %s manifest may not name a route_seal_id (%r). The "
                "route seal binds the capture record, so a capture that bound a "
                "seal would close the loop the chain exists to keep open: %s"
                % (PURPOSE_CAPTURE, route_seal_id, " -> ".join(BINDING_CHAIN)))
        if capture_authority != CAPTURE_AUTHORITY:
            raise LineageCaptureError(
                "abort: a %s manifest must bind the C-70 capture authority %r, "
                "got %r." % (PURPOSE_CAPTURE, CAPTURE_AUTHORITY, capture_authority))
        return purpose

    if capture_authority is not None:
        raise LineageCaptureError(
            "abort: a %s manifest may not stand on the capture authority; that "
            "authority exists only to make ONE lineage fact, and reusing it for "
            "a decision run would route around the seal."
            % PURPOSE_PRODUCTION)
    assert_route_seal_is_real(route_seal_id, artifact=route_seal_artifact)
    # The lineage binding lives one link further down the chain — on the PERIOD
    # RECEIPT (`assert_receipt_names_its_lineage`), because that is where §19.4
    # already binds the two floors. Validated here only if a caller supplies it.
    if lineage_id is not None:
        assert_lineage_id(lineage_id)
    if capture_record_sha256 is not None:
        _assert_sha256("capture_record_sha256", capture_record_sha256)
    return purpose


def assert_receipt_names_its_lineage(receipt: dict, *,
                                     capture_record_path=None) -> dict:
    """§19.4 + §20: a period receipt must say which frozen floor it used.

    Shape first, then SUBSTANCE. Checking only that the fields look like a
    lineage id and a digest is the F0-R4 failure: both are satisfied by strings
    that point at nothing. With `capture_record_path` this verifies the record
    itself, that the receipt's digest is that record's, and that the floor the
    receipt used is the floor the record froze.
    """
    missing = [f for f in ("lineage_id", "capture_record_sha256",
                           "lineage_price_floor", "observed_price_coverage_floor")
               if not receipt.get(f)]
    if missing:
        raise LineageCaptureError(
            "abort: the period receipt does not bind %s. A receipt that names a "
            "floor but not the capture that froze it cannot be audited against "
            "the lineage." % missing)
    assert_lineage_id(receipt["lineage_id"])
    _assert_sha256("capture_record_sha256", receipt["capture_record_sha256"])
    if capture_record_path is None:
        return {"verified": "SHAPE_ONLY"}

    loaded = load_and_verify_capture_record(capture_record_path)
    record = loaded["record"]
    if record["lineage_id"] != receipt["lineage_id"]:
        raise LineageCaptureError(
            "abort: the receipt names lineage %s but the record at %s is %s"
            % (receipt["lineage_id"], capture_record_path, record["lineage_id"]))
    if receipt["capture_record_sha256"] not in (loaded["payload_sha256"],
                                                loaded["raw_sha256"]):
        raise LineageCaptureError(
            "abort: the receipt's capture_record_sha256 %s matches neither the "
            "record's payload hash %s nor its raw hash %s — it points at "
            "nothing." % (receipt["capture_record_sha256"][:16],
                          loaded["payload_sha256"][:16], loaded["raw_sha256"][:16]))
    if receipt["lineage_price_floor"] != record["lineage_price_floor"]:
        raise LineageCaptureError(
            "abort: the receipt ran on floor %s but lineage %s froze %s. This is "
            "the drift §19.3 exists to catch, one level up."
            % (receipt["lineage_price_floor"], display_alias(record["lineage_id"]),
               record["lineage_price_floor"]))
    return {"verified": "AGAINST_THE_RECORD", "record": record}


def assert_route_seal_is_real(route_seal_id, *, artifact=None) -> str:
    """A real seal is a CONTENT-ADDRESSED artefact, not a non-placeholder string.

    Three layers, because the first two are what a plausible id gets past:

      1. not a placeholder (`PENDING`, `""`, ...) — necessary, nowhere near
         sufficient: `"x"` passes it;
      2. the ratified id form, `L3SEAL-<64 hex>`, so that the id IS the digest;
      3. the artefact exists and hashes to that digest.

    And then it FAILS CLOSED anyway, because no seal contract has been ratified:
    a production run cannot be admitted by a rule that does not exist yet. The
    layers are written now so that ratifying the contract is a deliberate edit
    here rather than a silent widening somewhere else.
    """
    if not isinstance(route_seal_id, str) or \
            route_seal_id.strip().upper() in PLACEHOLDER_ROUTE_SEAL_IDS:
        raise LineageCaptureError(
            "abort: %r is a placeholder, not a route seal. A manifest carrying "
            "one reads as bound in every audit that only checks the field is "
            "present." % (route_seal_id,))
    if not ROUTE_SEAL_ID_RE.match(route_seal_id):
        raise LineageCaptureError(
            "abort: %r is not a content-addressed route seal id. The form is "
            "L3SEAL-<64 hex>, so that the id is the digest of the sealed "
            "artefact rather than a name somebody chose." % (route_seal_id,))
    digest = route_seal_id.split("-", 1)[1]
    if artifact is None:
        raise LineageCaptureError(
            "abort: route seal %s names no artefact. An id that nothing is "
            "checked against is a claim, not a seal." % route_seal_id)
    from core.b0_canonical_hash import file_sha256

    if not os.path.isfile(artifact):
        raise LineageCaptureError(
            "abort: route seal artefact %s does not exist" % artifact)
    got = file_sha256(artifact)
    if got != digest:
        raise LineageCaptureError(
            "abort: route seal %s does not match its artefact (%s hashes to "
            "%s). A seal that does not hash its own bytes seals nothing."
            % (route_seal_id, artifact, got))
    raise LineageCaptureError(
        "abort: the L3 route seal contract is %s, so no PRODUCTION_RUN can be "
        "admitted yet. This is fail-closed on purpose: %s must land, be ruled "
        "on and be bound to the capture record before a production manifest "
        "can be honest. Use %s for a run that only reads sources."
        % (ROUTE_SEAL_CONTRACT_STATUS, "the seal contract", PURPOSE_DIAGNOSTIC))


# --- the capture run ------------------------------------------------------------

CAPTURE_RUN_ID_RE = re.compile(r"^L3-FLOOR-CAPTURE-(\d{8})-A(\d{2})$")
FIRST_ATTEMPT = 1
ATTEMPTS_ARE_NEVER_REUSED = True

# A capture is not a decision. It has an as_of because the sources are read at a
# point in time; it has no decision and no execution, and inventing either would
# manufacture a prospective decision that nobody made.
CAPTURE_RUN_HAS_NO_DECISION_FIELDS: tuple[str, ...] = (
    "decision_date", "execution_date")


def assert_capture_run_id(run_id: str, as_of: str) -> int:
    """`L3-FLOOR-CAPTURE-<as_of YYYYMMDD>-A<NN>`. Returns the attempt number."""
    m = CAPTURE_RUN_ID_RE.match(str(run_id or ""))
    if not m:
        raise LineageCaptureError(
            "abort: %r is not a capture run id. The form is "
            "L3-FLOOR-CAPTURE-<as_of YYYYMMDD>-A<NN>, so that a run id names "
            "the day its sources were read and which attempt it was."
            % (run_id,))
    assert_iso_date("as_of", as_of)
    stamp, attempt = m.group(1), int(m.group(2))
    if stamp != str(as_of).replace("-", ""):
        raise LineageCaptureError(
            "abort: capture run id %r carries the date %s but as_of is %s. A run "
            "id that disagrees with its own as_of is unusable as evidence."
            % (run_id, stamp, as_of))
    if attempt < FIRST_ATTEMPT:
        raise LineageCaptureError(
            "abort: attempt A%02d does not exist; attempts start at A%02d."
            % (attempt, FIRST_ATTEMPT))
    return attempt


MAX_ATTEMPT = 99


def next_attempt_run_id(run_id: str, *, capture_date: str | None = None) -> str:
    """A failed attempt is never cleared or reused — the next one is A(NN+1).

    A99 has no successor: `A100` does not match the run-id form, and returning
    it would hand back a string that every later guard rejects. Ninety-nine
    failed captures is a reason to stop and think, not to widen the field.
    """
    m = CAPTURE_RUN_ID_RE.match(str(run_id or ""))
    if not m:
        raise LineageCaptureError("abort: %r is not a capture run id" % (run_id,))
    previous_date = "%s-%s-%s" % (m.group(1)[:4], m.group(1)[4:6],
                                   m.group(1)[6:])
    next_date = assert_iso_date("capture_date", capture_date or previous_date)
    if next_date < previous_date:
        raise LineageCaptureError(
            "abort: a later capture attempt may not move backwards from %s "
            "to %s." % (previous_date, next_date))
    nxt = int(m.group(2)) + 1
    if nxt > MAX_ATTEMPT:
        raise LineageCaptureError(
            "abort: A%02d is the last attempt id the form admits, so there is no "
            "A%d. %d failed captures is a finding to report, not a counter to "
            "widen." % (MAX_ATTEMPT, nxt, MAX_ATTEMPT))
    return "L3-FLOOR-CAPTURE-%s-A%02d" % (next_date.replace("-", ""), nxt)


def assert_iso_date(name: str, value) -> str:
    """A real calendar date in the extended form, not a string that looks like one.

    `date.fromisoformat` accepts the BASIC form `20260826` since 3.11, so the
    shape is pinned here too: two representations of the same day would hash to
    two different lineages.
    """
    import datetime

    text = str(value)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise LineageCaptureError(
            "abort: %s must be an ISO calendar date in the form YYYY-MM-DD, got "
            "%r" % (name, value))
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise LineageCaptureError(
            "abort: %s is not an ISO calendar date that exists: %r" % (name, value))


def assert_no_decision_fields(record: dict) -> None:
    """Absent or explicitly null. Never a plausible-looking fabrication."""
    bad = [f for f in CAPTURE_RUN_HAS_NO_DECISION_FIELDS
           if record.get(f) is not None]
    if bad:
        raise LineageCaptureError(
            "abort: a capture run carries no %s; %s was filled in. A capture "
            "reads sources, it does not decide anything, and a fabricated "
            "decision date would let this run be mistaken for a prospective one."
            % (" or ".join(CAPTURE_RUN_HAS_NO_DECISION_FIELDS), bad))


# --- repo identity --------------------------------------------------------------

FULL_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Gitignored run artefacts are the OUTPUT of running; requiring them absent would
# make the second capture attempt impossible for a reason that has nothing to do
# with source integrity.
GITIGNORED_RUN_ARTEFACTS_COUNT_AS_DIRTY = False


def assert_repo_identity(*, commit_sha, tracked_clean: bool,
                         untracked_clean: bool) -> str:
    """A capture is only as durable as the tree it can be re-derived from."""
    if not FULL_COMMIT_SHA_RE.match(str(commit_sha or "")):
        raise LineageCaptureError(
            "abort: repo identity must be a full 40-hex commit sha, got %r. An "
            "abbreviation is not an identity — it is a prefix that a future "
            "object can collide with." % (commit_sha,))
    dirty = [n for n, ok in (("tracked", tracked_clean),
                             ("untracked", untracked_clean)) if not ok]
    if dirty:
        raise LineageCaptureError(
            "abort: the working tree is not clean (%s). A capture record binds a "
            "commit; if the tree it was read from is not that commit, the "
            "binding names bytes that were never used."
            % ", ".join(dirty))
    return str(commit_sha)


# --- what the capture binds -----------------------------------------------------

# The leaf is the sole authority for every source's raw sha256; copying thousands
# of them here would create a second copy to disagree with. The capture binds the
# leaf's payload hash, and summarises each leg well enough to see WHAT was read.
LEG_SUMMARY_FIELDS: tuple[str, ...] = (
    "leg", "entry_count", "inventory_digest", "leg_floor",
    "quarantine_boundary", "rows_dropped_by_quarantine", "admissible_rows",
)

LINEAGE_BASIS_FIELDS: tuple[str, ...] = (
    "contract_version",
    "capture_authority",
    "capture_run_id",
    "as_of",
    "lineage_price_floor",
    "price_leaf_payload_sha256",
    "aggregate_manifest_payload_sha256",
    "leg_summaries",
    "master_version",
    "spec_sha256",
    "master_prereg_freeze_sha256",
    "floor_capture_code_closure_sha256",
    "repo_commit_sha",
)

# Anything derived FROM the basis may never be part of it.
SELF_REFERENTIAL_FIELDS: tuple[str, ...] = (
    "lineage_id", "lineage_basis_sha256", "capture_record_payload_sha256",
    "capture_record_raw_sha256", "route_seal_id",
)

LINEAGE_ID_PREFIX = "L3-"
DISPLAY_ALIAS_LENGTH = 16
CANONICAL_IDENTITY_IS_THE_FULL_DIGEST = True


def _assert_sha256(name: str, value) -> str:
    if not isinstance(value, str) or not re.match(r"^[0-9a-f]{64}$", value):
        raise LineageCaptureError(
            "abort: %s must be a full sha256 hex digest, got %r" % (name, value))
    return value


def assert_basis_is_not_self_referential(basis: dict) -> None:
    present = [f for f in SELF_REFERENTIAL_FIELDS if f in basis]
    if present:
        raise LineageCaptureError(
            "abort: %s may not appear in the lineage basis — the basis is what "
            "those values are derived FROM, and folding them back in makes the "
            "identity depend on itself." % present)


def lineage_basis(**fields) -> dict:
    """The canonical facts a lineage is named by. Complete or it aborts."""
    assert_basis_is_not_self_referential(fields)
    missing = [f for f in LINEAGE_BASIS_FIELDS if f not in fields]
    extra = [f for f in fields if f not in LINEAGE_BASIS_FIELDS]
    if missing or extra:
        raise LineageCaptureError(
            "abort: the lineage basis is exactly %s; missing %s, unexpected %s. "
            "A basis that varies by caller names different lineages for the same "
            "capture." % (list(LINEAGE_BASIS_FIELDS), missing, extra))
    return {k: fields[k] for k in LINEAGE_BASIS_FIELDS}


def lineage_basis_sha256(basis: dict) -> str:
    from core.b0_canonical_hash import canonical_sha256

    return canonical_sha256(lineage_basis(**basis))


def lineage_id_from_basis(basis: dict) -> str:
    """`L3-<full 64-hex basis digest>`. The full digest IS the identity."""
    return LINEAGE_ID_PREFIX + lineage_basis_sha256(basis)


def assert_lineage_id(lineage_id) -> str:
    if not isinstance(lineage_id, str) or \
            not re.match(r"^L3-[0-9a-f]{64}$", lineage_id):
        raise LineageCaptureError(
            "abort: %r is not a lineage id. The canonical form is L3- followed "
            "by the FULL 64-hex basis digest; a shortened one is a display "
            "alias and may never be stored, compared or bound." % (lineage_id,))
    return lineage_id


def display_alias(lineage_id: str) -> str:
    """For humans and logs ONLY. Never an identity, never a path component."""
    assert_lineage_id(lineage_id)
    return lineage_id[:len(LINEAGE_ID_PREFIX) + DISPLAY_ALIAS_LENGTH]


# --- the artefact -----------------------------------------------------------------

ARTIFACT_DIR_NAME = "artifacts"
LINEAGE_ROOT_PARTS: tuple[str, ...] = ("l3_run", "lineages")
CAPTURE_FILENAME = "lineage_price_floor_capture.json"
CANONICAL_CAPTURE_LOCATION = "artifacts/l3_run/lineages/<lineage_id>/" + \
    CAPTURE_FILENAME

# Runtime evidence lives in the artefact tree, not in the code tree, and there is
# exactly ONE original. A convenience copy under research/ would be a second
# authority the moment the two differ.
NO_SECOND_ORIGINAL_UNDER_RESEARCH = True


def default_artifact_root(repo_root: str) -> str:
    """`<repo>/artifacts`, or `B0_ARTIFACT_DIR` when the harness redirects it."""
    return os.environ.get("B0_ARTIFACT_DIR") or \
        os.path.join(repo_root, ARTIFACT_DIR_NAME)


def lineage_dir(artifact_root: str, lineage_id: str) -> str:
    """`<artifact_root>/l3_run/lineages/<lineage_id>`."""
    assert_lineage_id(lineage_id)
    return os.path.join(artifact_root, *LINEAGE_ROOT_PARTS, lineage_id)


def capture_path(artifact_root: str, lineage_id: str) -> str:
    return os.path.join(lineage_dir(artifact_root, lineage_id), CAPTURE_FILENAME)


def create_lineage_dir_exclusively(artifact_root: str, lineage_id: str) -> str:
    """Exclusive create. An existing lineage directory is an abort, not a resume."""
    path = lineage_dir(artifact_root, lineage_id)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    try:
        os.mkdir(path)
    except FileExistsError:
        raise LineageCaptureError(
            "abort: lineage directory %s already exists. A lineage is captured "
            "once; a second capture under the same identity would either "
            "overwrite the frozen floor or hide that it disagreed." % path)
    return path


def assert_record_is_admissible(record: dict) -> dict:
    """Every guard, applied to the RECORD — not to what a caller promised.

    The writer is reachable directly, so it may not trust its caller: a record
    handed to it must re-derive to the same lineage id, carry a floor equal to
    the diagnostic expected value, name a well-formed capture run consistent
    with its own as_of, carry real digests, name a committed clean tree, and
    describe both price legs. A guard that only runs in the happy path is a
    comment.
    """
    basis = {k: record[k] for k in LINEAGE_BASIS_FIELDS if k in record}
    missing = [k for k in LINEAGE_BASIS_FIELDS if k not in record]
    if missing:
        raise LineageCaptureError(
            "abort: the record does not carry the lineage basis; missing %s"
            % missing)
    recomputed = lineage_id_from_basis(basis)
    if record.get("lineage_id") != recomputed:
        raise LineageCaptureError(
            "abort: the record's lineage_id %r is not the digest of its own "
            "basis (%r). An identity that does not re-derive is a label."
            % (record.get("lineage_id"), recomputed))
    if record.get("lineage_basis_sha256") != recomputed[len(LINEAGE_ID_PREFIX):]:
        raise LineageCaptureError(
            "abort: lineage_basis_sha256 disagrees with the recomputed basis digest")
    if record.get("manifest_purpose") != PURPOSE_CAPTURE:
        raise LineageCaptureError(
            "abort: only a %s run may write a capture record; this one says %r"
            % (PURPOSE_CAPTURE, record.get("manifest_purpose")))
    assert_no_decision_fields(record)
    if record.get("route_seal_id") is not None:
        raise LineageCaptureError(
            "abort: a capture record may not name a route seal (%s)"
            % " -> ".join(BINDING_CHAIN))
    assert_capture_run_id(record["capture_run_id"], record["as_of"])
    assert_iso_date("lineage_price_floor", record["lineage_price_floor"])
    assert_floor_matches_expected(
        record["lineage_price_floor"],
        record.get("diagnostic_expected_floor", DIAGNOSTIC_EXPECTED_FLOOR))
    for f in ("price_leaf_payload_sha256", "aggregate_manifest_payload_sha256",
              "spec_sha256", "master_prereg_freeze_sha256",
              "floor_capture_code_closure_sha256"):
        _assert_sha256(f, record.get(f))
    assert_repo_identity(commit_sha=record.get("repo_commit_sha"),
                         tracked_clean=bool(record.get("tracked_clean")),
                         untracked_clean=bool(record.get("untracked_clean")))
    assert_leg_summaries(record.get("leg_summaries"))
    assert_inventory_is_ratified(record.get("required_datasets_provenance"))
    return record


def write_capture_record_exclusively(artifact_root: str, record: dict) -> tuple:
    """Atomic exclusive publication. Returns (payload_sha256, raw_sha256).

    P2-11. The claim used to be `O_CREAT | O_EXCL` on the FINAL path with the
    bytes written afterwards, so an interruption between the two froze a
    ZERO-BYTE capture record under a lineage id that can never be captured
    again. `publish_exclusively` keeps the refusal -- a taken path still fails
    -- and makes the record appear whole or not at all.

    Refuses an inadmissible record even when handed one directly — see
    `assert_record_is_admissible`. `capture_lineage_floor` is the sanctioned
    entry point; this is the last line, not the only one.
    """
    import json

    from core.b0_canonical_hash import canonical_sha256, file_sha256

    assert_record_is_admissible(record)
    lineage_id = assert_lineage_id(record.get("lineage_id"))
    path = capture_path(artifact_root, lineage_id)
    body = {k: v for k, v in record.items()
            if k not in ("capture_record_payload_sha256",)}
    body["capture_record_payload_sha256"] = canonical_sha256(body)
    blob = json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True)

    def _write(temporary: str) -> None:
        # Byte-for-byte the write this function has always performed;
        # only the NAME it is written under first has changed.
        with open(temporary, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(blob + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    try:
        publish_exclusively(path, _write)
    except FileExistsError:
        raise LineageCaptureError(
            "abort: %s already exists. A capture record is written once; "
            "overwriting one rewrites a frozen lineage fact." % path)
    return body["capture_record_payload_sha256"], file_sha256(path)


REQUIRED_PRICE_LEGS: tuple[str, ...] = ("pre-2019", "2019+")

# §20.8 · C-71 · THE FLOOR CAUSAL CLOSURE — fixed, and not a caller's choice.
#
# v1.35 required a capture to read the full nine-family production inventory.
# That blocked A01 on a `valuation` board payload that had not been harvested —
# for a quantity valuation cannot move. The earliest admissible trading session
# is decided by the price corpus and by which sessions exist; `valuation` and
# `corporate_actions` cannot change it, so requiring them neither protects the
# floor nor belongs in the lineage identity.
#
#   prices    both legs. §2.8.3 splits the lineage at 2019-01-01 and the halves
#             live in different trees, so one leg alone is a different corpus.
#   calendar  the floor must be a SESSION, and price rows off the declared
#             calendar must be refused rather than silently deepening the floor.
#
# The D-1 quarantine is deliberately NOT a tenth family: it is a rule plus the
# code that enforces it, bound by the spec and by FLOOR_CAPTURE_CODE_CLOSURE.
FLOOR_CAPTURE_REQUIRED_DATASETS: tuple[str, ...] = ("calendar", "prices")

D1_QUARANTINE_AUTHORITY = {
    "rule": "PRE_2019_CACHE_ROWS_ONLY_THE_2019_ERA_IS_D1_QUARANTINED",
    "boundary": "2019-01-01",
    "bound_by": "specification + FLOOR_CAPTURE_CODE_CLOSURE, not a dataset family",
}

# A PRODUCTION_RUN is unchanged: it still binds all nine families.
PRODUCTION_INVENTORY_IS_UNCHANGED_BY_C71 = True


def assert_capture_inventory(required) -> tuple:
    """The capture inventory is fixed. Short OR long is a refusal.

    Not "at least these": a caller that could add families would put a hash that
    cannot move the floor into the lineage identity, and one that could drop the
    calendar would let an off-calendar row set it.
    """
    got = tuple(sorted(set(required or ())))
    want = tuple(sorted(FLOOR_CAPTURE_REQUIRED_DATASETS))
    if got != want:
        raise LineageCaptureError(
            "abort: a %s run reads exactly %s. It declared %s (missing %s, "
            "extra %s). The floor's causal closure is fixed by §20.8, not "
            "chosen per run." % (PURPOSE_CAPTURE, list(want), list(got),
                                 sorted(set(want) - set(got)),
                                 sorted(set(got) - set(want))))
    return want


def assert_floor_is_a_trading_session(floor: str, sessions) -> str:
    """The floor is the earliest admissible SESSION, not the earliest row.

    A price row on a day the declared calendar does not have is either a bad
    date or a source from another calendar; either way it must not become the
    day a lineage is frozen at.
    """
    assert_iso_date("lineage_price_floor", floor)
    if floor not in set(sessions or ()):
        raise LineageCaptureError(
            "abort: the observed floor %s is not a session in the declared "
            "calendar. A floor that is not a trading session cannot be the "
            "earliest admissible one." % floor)
    return floor


def assert_prices_are_on_calendar(dates, sessions) -> int:
    """No off-calendar price row may reach the floor derivation."""
    known = set(sessions or ())
    off = sorted({str(d) for d in dates if str(d) not in known})
    if off:
        raise LineageCaptureError(
            "abort: %d price date(s) are not sessions in the declared calendar "
            "(earliest %s). One of them would silently deepen the floor."
            % (len(off), off[0]))
    return 0

# §20.8 / W4-A2. The inventory a capture stands on may not describe itself as
# provisional: a floor captured from "whatever sources we had" is not a fact
# about the corpus.
RATIFIED_INVENTORY_AUTHORITY = (
    "RATIFIED — research/b0_l3/route_closure.py :: DATASET_FAMILIES / "
    "REQUIRED_DATASET_FLOOR (W4/A2 production-route transitive source "
    "inventory), cross-checked against the retrospective loader by "
    "assert_inventories_agree()")
PROVISIONAL_MARKERS: tuple[str, ...] = ("PROVISIONAL", "OWED", "TBD", "DRAFT")


def assert_inventory_is_ratified(provenance) -> str:
    """A capture may not stand on a source list that says it is not final."""
    text = str(provenance or "")
    if not text:
        raise LineageCaptureError(
            "abort: the run declares no required-datasets provenance, so what "
            "the floor was read from cannot be established")
    hit = [m for m in PROVISIONAL_MARKERS if m in text.upper()]
    if hit:
        raise LineageCaptureError(
            "abort: the source inventory still describes itself as %s (%r). A "
            "lineage floor captured from a provisional source set freezes an "
            "accident." % (hit, text[:120]))
    return text


def assert_leg_summaries(summaries) -> tuple:
    """§2.8.3's two legs, each summarised — not one leg wearing both hats."""
    if not isinstance(summaries, (list, tuple)) or not summaries:
        raise LineageCaptureError(
            "abort: the capture record carries no leg summaries; a floor with no "
            "account of which legs produced it cannot be audited")
    legs = [s.get("leg") for s in summaries]
    missing = [l for l in REQUIRED_PRICE_LEGS if l not in legs]
    if missing:
        raise LineageCaptureError(
            "abort: leg summaries are missing %s. Declaring only the 2019+ leg "
            "once gave 1,706 of 1,958 securities a fabricated spell start of "
            "2019-01-02." % missing)
    for s in summaries:
        bad = [f for f in LEG_SUMMARY_FIELDS if f not in s]
        if bad:
            raise LineageCaptureError(
                "abort: leg %r summary is missing %s" % (s.get("leg"), bad))
        _assert_sha256("inventory_digest", s.get("inventory_digest"))
        if not isinstance(s.get("entry_count"), int) or s["entry_count"] < 1:
            raise LineageCaptureError(
                "abort: leg %r declares entry_count %r" % (s.get("leg"),
                                                           s.get("entry_count")))
        assert_iso_date("leg_floor", s.get("leg_floor"))
    return tuple(summaries)


def derive_leg_summaries(price_leaf: dict, admitted_prices,
                         *, rows_dropped_by_quarantine: int,
                         quarantine_boundary: str = "2019-01-01") -> tuple:
    """One canonical derivation for the two capture-leg summaries.

    `admitted_prices` is the fully verified reader output.  The quarantine
    count cannot be reconstructed from that output because the reader has
    intentionally discarded those rows, so the capture runner must count the
    raw pre-2019 cache rows on/after the boundary and supply that measured
    value.  Keeping the remaining arithmetic here prevents every runner from
    inventing a subtly different inventory projection or split.
    """
    from core.b0_canonical_hash import canonical_sha256

    if not isinstance(rows_dropped_by_quarantine, int) or \
            rows_dropped_by_quarantine < 0:
        raise LineageCaptureError(
            "abort: rows_dropped_by_quarantine must be a non-negative integer")
    assert_iso_date("quarantine_boundary", quarantine_boundary)
    entries = [e for e in (price_leaf or {}).get("entries", ())
               if e.get("disposition") == "consumed"]
    result = []
    for leg in REQUIRED_PRICE_LEGS:
        leg_entries = [e for e in entries if e.get("leg") == leg]
        if not leg_entries:
            raise LineageCaptureError(
                "abort: prices leaf has no consumed %s entry" % leg)
        inventory = [{k: e[k] for k in ("locator", "raw_sha256", "members")
                      if k in e} for e in leg_entries]
        if leg == "pre-2019":
            mask = admitted_prices["date"] < quarantine_boundary
            dropped = rows_dropped_by_quarantine
        else:
            mask = admitted_prices["date"] >= quarantine_boundary
            dropped = 0
        frame = admitted_prices.loc[mask]
        if frame.empty:
            raise LineageCaptureError(
                "abort: verified reader admitted no %s price rows" % leg)
        result.append({
            "leg": leg,
            "entry_count": len(leg_entries),
            "inventory_digest": canonical_sha256(inventory),
            "leg_floor": str(frame["date"].min()),
            "quarantine_boundary": quarantine_boundary,
            "rows_dropped_by_quarantine": dropped,
            "admissible_rows": int(len(frame)),
        })
    return assert_leg_summaries(result)


def build_capture_record(basis: dict, *, capture_date: str,
                         diagnostic_expected_floor: str = DIAGNOSTIC_EXPECTED_FLOOR,
                         **evidence) -> dict:
    """basis -> the record, with identity derived and the stop-check recorded."""
    basis = lineage_basis(**basis)
    lineage_id = lineage_id_from_basis(basis)
    record = dict(basis)
    record.update({
        "lineage_id": lineage_id,
        "lineage_basis_sha256": lineage_id[len(LINEAGE_ID_PREFIX):],
        "lineage_id_display_alias": display_alias(lineage_id),
        "capture_date": str(capture_date),
        "manifest_purpose": PURPOSE_CAPTURE,
        "binding_chain": list(BINDING_CHAIN),
        "diagnostic_expected_floor": str(diagnostic_expected_floor),
        "diagnostic_expected_floor_matched": True,
        "decision_date": None,
        "execution_date": None,
        "route_seal_id": None,
        "decision_layer_invoked": False,
        "performance_computed": False,
    })
    record.update(evidence)
    return record


# --- the one sanctioned way in -----------------------------------------------------

def capture_lineage_floor(artifact_root: str, *, basis: dict, capture_date: str,
                          required_datasets_provenance: str,
                          tracked_clean: bool, untracked_clean: bool,
                          diagnostic_expected_floor: str = DIAGNOSTIC_EXPECTED_FLOOR
                          ) -> dict:
    """THE capture transaction. Every guard runs BEFORE anything is created.

    Ordering is the contract, not a detail: the floor check, the run id, the
    digests, the repo identity, the legs and the inventory are all settled while
    the filesystem is still untouched, so a refusal cannot leave a half-made
    lineage behind (§20.9). Only then is the directory created exclusively and
    the record written under O_EXCL.

    Returns `{"record", "path", "payload_sha256", "raw_sha256"}`.
    """
    record = build_capture_record(
        basis, capture_date=capture_date,
        diagnostic_expected_floor=diagnostic_expected_floor,
        required_datasets_provenance=required_datasets_provenance,
        tracked_clean=bool(tracked_clean),
        untracked_clean=bool(untracked_clean))
    # Nothing exists yet, and nothing will unless this passes.
    assert_record_is_admissible(record)
    create_lineage_dir_exclusively(artifact_root, record["lineage_id"])
    payload, raw = write_capture_record_exclusively(artifact_root, record)
    return {"record": record,
            "path": capture_path(artifact_root, record["lineage_id"]),
            "payload_sha256": payload, "raw_sha256": raw}


def load_and_verify_capture_record(path: str) -> dict:
    """Read a capture record back and re-establish every claim it makes.

    Verified here rather than trusted: the record's own payload hash, the basis
    -> lineage id derivation, and then the full admissibility gate again. A
    record that was written before a guard existed does not silently pass.
    """
    import json

    from core.b0_canonical_hash import canonical_sha256, file_sha256

    if not os.path.isfile(path):
        raise LineageCaptureError("abort: no capture record at %s" % path)
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    declared = record.get("capture_record_payload_sha256")
    body = {k: v for k, v in record.items()
            if k != "capture_record_payload_sha256"}
    recomputed = canonical_sha256(body)
    if declared != recomputed:
        raise LineageCaptureError(
            "abort: the capture record at %s does not hash to its own declared "
            "payload sha256 (declared %r, recomputed %r)."
            % (path, declared, recomputed))
    assert_record_is_admissible(record)
    return {"record": record, "payload_sha256": recomputed,
            "raw_sha256": file_sha256(path)}


# --- the stop-check ---------------------------------------------------------------

# What a mismatch must NOT do. The run-scoped evidence is the only record of WHY
# a lineage was not created, so deleting it to "clean up" destroys the audit.
FAILED_CAPTURE_PRESERVATION: tuple[str, ...] = (
    "the run-scoped price leaf is preserved",
    "the run-scoped aggregate manifest is preserved",
    "the failure evidence is preserved",
    "no lineage directory is created",
    "no capture record is written",
    "the attempt id is never reused or cleared",
)


def assert_floor_matches_expected(floor: str,
                                  expected: str = DIAGNOSTIC_EXPECTED_FLOOR) -> str:
    """§19.7: disagree and nothing is created. The evidence stays.

    Deliberately raised BEFORE any directory or record exists, so that a
    mismatch cannot leave a half-made lineage behind.
    """
    if str(floor) != str(expected):
        raise LineageCaptureError(
            "STOP: the capture produced floor %s but the diagnostic expected "
            "value is %s. This is not a value to adopt (§19.7) — report it.\n"
            "Preserved, and required to stay preserved: %s"
            % (floor, expected, "; ".join(FAILED_CAPTURE_PRESERVATION)))
    return str(floor)


# --- the floor-capture code closure ------------------------------------------------

# Its OWN closure, not the production route's: what a capture's correctness
# actually depends on. Bound in the record so that a later reader can ask whether
# the code that made this fact is the code they are reading.
FLOOR_CAPTURE_CODE_CLOSURE: tuple[str, ...] = (
    "core/b0_l3_lineage_capture.py",
    "core/b0_l3_price_span.py",
    "core/b0_canonical_hash.py",
    "core/b0_master_prereg.py",
    "research/b0_l3/l3_readers.py",
    "research/b0_materializer/source_ownership_manifest.py",
    "research/b0_materializer/build_flat_leaves.py",
    "research/b0_materializer/build_prices_leaf.py",
    "research/b0_materializer/l3_temporal_snapshot.py",
    "research/b0_l3_runner/capture_l3_floor.py",
)


def floor_capture_code_closure_sha256(repo_root: str) -> str:
    """One digest over {path: raw sha256} for the closure above."""
    from core.b0_canonical_hash import canonical_sha256, file_sha256

    return canonical_sha256({
        p: file_sha256(os.path.join(repo_root, p))
        for p in FLOOR_CAPTURE_CODE_CLOSURE})
