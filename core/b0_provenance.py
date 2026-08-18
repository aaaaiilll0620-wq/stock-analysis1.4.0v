"""B-21 provenance / reproducibility for Frozen B0.

S-8 is only useful if a completed B0 evaluation can be bound, uniquely and
mechanically, to everything that produced it. "I think we used those files" is
not provenance. Six categories must be reconstructible:

  1. code     — commit SHA, dirty state, dependency lock
  2. config   — canonical serialisation + hash, no unregistered override
  3. data     — per-dataset identity/version/hash, schema hash, date coverage,
                importer lineage
  4. derived  — PIT industry timeline, B/M reference, feature caches; each with
                its own hash AND its upstream hashes
  5. execution— initial portfolio state hash, decision date, market-data as-of,
                route/module version
  6. output   — target/intent/receipt/NAV hashes, each traceable back to 1-5

and one invariant on top:

    same sealed (code, config, data, initial state) => same output hashes.

Determinism is asserted bit-exact. Any legitimate non-deterministic source must
be enumerated item by item; a global tolerance would let a real difference hide
inside "close enough", which is the same failure mode B-20 rejects for parity.

Unregistered sources fail loudly rather than being recorded. Recording an
unregistered dataset overlay does not make the run reproducible — it documents
that it was not. B-19 found `TEJ_RUNTIME_OVERLAY`, an environment variable that
silently merges a replacement parquet over any dataset; a B0 final run with it
set is not a B0 run.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Mapping, Sequence

from core.b0_canonical_hash import CANONICAL_HASH_VERSION, canonical_sha256
from core.b0_canonical_hash import file_sha256 as _file_sha256

# Environment variables that may legitimately differ between machines because
# they only relocate inputs whose *content* is hashed separately.
SEALED_ENV_ALLOWLIST: tuple[str, ...] = ("TEJ_CACHE", "MARKET_CACHE", "FINMIND_CACHE")

# Environment variables that must be UNSET for a sealed B0 run. These change
# what data means, not merely where it lives.
FORBIDDEN_ENV: tuple[str, ...] = ("TEJ_RUNTIME_OVERLAY",)

# F0-R6: `specification` is a section of its own. A sealed run that cannot name
# which master preregistration it obeyed is bound to its code and its data and
# to no rules.
PROVENANCE_SECTIONS: tuple[str, ...] = (
    "specification", "code", "config", "data", "derived", "execution", "output",
)

# --- M-3 ruling (Master v1.14): two-stage provenance --------------------------
#
# The seal Master §13.3 requires BEFORE L2 may open cannot describe a run: the
# only way to populate `execution.decision_date` and `output.artifacts` is to
# run the B0 route, which is the step the seal exists to authorise. Sealing was
# therefore unreachable, and the gap was ruled on rather than papered over.
#
# The roles are split. A BASELINE seal binds everything that is knowable before
# any decision exists — specification, code, config, data, derived inputs, the
# opening state, route identity and the L2 opening protocol — and records the
# absence of a run as an EXPLICIT state. A RUN record is taken after the user
# opens L2 and references the baseline by hash.
#
# `NOT_EXECUTED_PRE_L2` is provenance, not missing provenance: it asserts "no
# decision had been made when this was sealed". A blank field would merely fail
# to say anything, which is the ambiguity this ruling removes.
EXECUTED: str = "EXECUTED"
NOT_EXECUTED_PRE_L2: str = "NOT_EXECUTED_PRE_L2"
PRODUCED: str = "PRODUCED"
NOT_PRODUCED_PRE_L2: str = "NOT_PRODUCED_PRE_L2"

EXECUTION_STATUSES: tuple[str, ...] = (EXECUTED, NOT_EXECUTED_PRE_L2)
OUTPUT_STATUSES: tuple[str, ...] = (PRODUCED, NOT_PRODUCED_PRE_L2)

SEAL_STAGE_BASELINE: str = "B0_BASELINE_SEAL"
SEAL_STAGE_L2_RUN: str = "L2_RUN_PROVENANCE"


class ProvenanceError(RuntimeError):
    """Fail-loud: a sealed run cannot be bound to its inputs."""


class SealRaceError(ProvenanceError):
    """Repository identity moved between preflight and the seal being written.

    This repository has an autonomous scheduled commit mechanism, so "the tree
    was clean when I checked" is not the same claim as "the tree was clean when
    the seal was taken". A seal that binds a commit the tree no longer matches
    binds nothing.
    """


def _h(payload: Any) -> str:
    """F0-R7: delegates to the one canonical primitive.

    This used to be a second serializer (`default=str`, no normalisation pass).
    It agreed with the route's hash on the frozen registry, which is not the
    same as being the same function — see `core/b0_canonical_hash.py`.
    """
    return canonical_sha256(payload)


file_sha256 = _file_sha256      # F0-R2 / F0-R3: raw bytes, not canonicalised


# --- 0. specification (F0-R2 / F0-R6) -----------------------------------------

@dataclass(frozen=True)
class SpecificationProvenance:
    """Which frozen specification the run obeyed, by raw-byte identity."""
    document: str
    spec_sha256: str
    version: str

    def validate(self) -> None:
        for f in ("document", "spec_sha256", "version"):
            if not str(getattr(self, f)).strip():
                raise ProvenanceError(
                    f"specification: {f} is required — a sealed run that cannot "
                    f"name the specification it obeyed is bound to its inputs "
                    f"and to no rules (F0-R6)")
        if len(self.spec_sha256) != 64:
            raise ProvenanceError(
                f"specification: spec_sha256 must be a sha256 hex digest, got "
                f"{self.spec_sha256!r}")

    @classmethod
    def from_frozen_master(cls, version: str) -> "SpecificationProvenance":
        from core.b0_master_prereg import MASTER_PREREG_DOC, spec_document_sha256

        return cls(document=MASTER_PREREG_DOC,
                   spec_sha256=spec_document_sha256(), version=version)


# --- 1. code -----------------------------------------------------------------

@dataclass(frozen=True)
class CodeProvenance:
    commit_sha: str
    dirty: bool
    dirty_diff_sha256: str | None      # required when dirty
    dependency_lock_sha256: str | None
    # F0-R3: the commit SHA identifies a tree; these identify the modules that
    # carry B0's normative behaviour. A commit SHA alone makes the binding
    # implicit, and an implicit binding cannot be checked without the repository.
    normative_module_sha256: Mapping[str, str] = field(default_factory=dict)

    def validate(self, *, final_seal: bool) -> None:
        if not self.commit_sha:
            raise ProvenanceError("code: commit_sha is required")
        if self.dirty:
            if final_seal:
                raise ProvenanceError(
                    "code: a final seal may not be taken on a dirty working "
                    "tree, because a dirty tree cannot be recovered from the commit alone"
                )
            if not self.dirty_diff_sha256:
                raise ProvenanceError(
                    "code: dirty tree must carry dirty_diff_sha256; recording "
                    "that it was dirty without recording what differed is not provenance"
                )
        if final_seal:
            from core.b0_master_prereg import NORMATIVE_MODULES

            missing = [m for m in NORMATIVE_MODULES
                       if not str(self.normative_module_sha256.get(m, "")).strip()]
            if missing:
                raise ProvenanceError(
                    f"code: {len(missing)} normative module(s) have no hash in "
                    f"the manifest: {missing[:5]} (F0-R3). Implementation "
                    f"identity is the commit SHA AND the module hashes; the "
                    f"commit alone binds them only implicitly.")


# --- 2. config ---------------------------------------------------------------

@dataclass(frozen=True)
class ConfigProvenance:
    canonical: Mapping[str, Any]
    registered_overrides: Mapping[str, str]   # key -> frozen prereg clause

    @property
    def config_sha256(self) -> str:
        return _h(self.canonical)

    def validate(self) -> None:
        if not self.canonical:
            raise ProvenanceError("config: canonical config must not be empty")
        for key, clause in self.registered_overrides.items():
            if not clause or not str(clause).strip():
                raise ProvenanceError(
                    f"config: override {key!r} registered with an empty clause — "
                    f"provenance theatre, not provenance"
                )


# --- 3. data -----------------------------------------------------------------

@dataclass(frozen=True)
class DatasetProvenance:
    name: str
    content_sha256: str
    schema_sha256: str
    date_min: str
    date_max: str
    importer_version: str

    def validate(self) -> None:
        for f in ("name", "content_sha256", "schema_sha256",
                  "date_min", "date_max", "importer_version"):
            if not getattr(self, f):
                raise ProvenanceError(f"data[{self.name or '?'}]: {f} is required")


# --- 4. derived --------------------------------------------------------------

@dataclass(frozen=True)
class DerivedArtifactProvenance:
    name: str
    content_sha256: str
    upstream_sha256: tuple[str, ...]     # hashes of every input it was built from

    def validate(self) -> None:
        if not self.name or not self.content_sha256:
            raise ProvenanceError("derived: name and content_sha256 are required")
        if not self.upstream_sha256:
            raise ProvenanceError(
                f"derived[{self.name}]: upstream_sha256 is required — an artifact "
                f"without its inputs is not reconstructible"
            )


# --- 5 / 6. execution + output ----------------------------------------------

@dataclass(frozen=True)
class ExecutionProvenance:
    decision_date: str
    initial_state_sha256: str
    market_data_as_of: Mapping[str, str]     # dataset -> as-of timestamp
    route_module: str
    route_version: str
    status: str = EXECUTED

    @classmethod
    def pre_l2_baseline(cls, *, initial_state_sha256: str,
                        market_data_as_of: Mapping[str, str],
                        route_module: str, route_version: str
                        ) -> "ExecutionProvenance":
        """The opening state and route identity, with no decision taken.

        The baseline still binds WHICH engine would run and WHAT state it would
        start from — those are knowable without running anything, and leaving
        them out would let the route change between the seal and L2.
        """
        return cls(decision_date="", initial_state_sha256=initial_state_sha256,
                   market_data_as_of=market_data_as_of, route_module=route_module,
                   route_version=route_version, status=NOT_EXECUTED_PRE_L2)

    def validate(self) -> None:
        if self.status not in EXECUTION_STATUSES:
            raise ProvenanceError(
                f"execution: status must be one of {EXECUTION_STATUSES}, got "
                f"{self.status!r}")
        # Bound at BOTH stages: the opening state and the engine identity are
        # knowable before any decision, so a baseline that omitted them would
        # let either change silently before L2 opened.
        for f in ("initial_state_sha256", "route_module", "route_version"):
            if not getattr(self, f):
                raise ProvenanceError(f"execution: {f} is required")
        if not self.market_data_as_of:
            raise ProvenanceError("execution: market_data_as_of is required")
        if self.status == NOT_EXECUTED_PRE_L2:
            if self.decision_date:
                raise ProvenanceError(
                    f"execution: status is {NOT_EXECUTED_PRE_L2} but decision_date "
                    f"is set to {self.decision_date!r}. A baseline seal records "
                    f"that no decision existed; naming one fabricates a run.")
        elif not self.decision_date:
            raise ProvenanceError("execution: decision_date is required")


@dataclass(frozen=True)
class OutputProvenance:
    artifacts: Mapping[str, str]             # artifact name -> sha256
    status: str = PRODUCED

    @classmethod
    def pre_l2_baseline(cls) -> "OutputProvenance":
        """No target list, intent, receipt or NAV exists yet — stated, not blank."""
        return cls(artifacts={}, status=NOT_PRODUCED_PRE_L2)

    def validate(self) -> None:
        if self.status not in OUTPUT_STATUSES:
            raise ProvenanceError(
                f"output: status must be one of {OUTPUT_STATUSES}, got {self.status!r}")
        if self.status == NOT_PRODUCED_PRE_L2:
            if self.artifacts:
                raise ProvenanceError(
                    f"output: status is {NOT_PRODUCED_PRE_L2} but "
                    f"{sorted(self.artifacts)} were supplied. A baseline seal that "
                    f"carries output hashes is claiming a run that did not happen.")
            return
        if not self.artifacts:
            raise ProvenanceError("output: at least one artifact hash is required")
        for k, v in self.artifacts.items():
            if not v:
                raise ProvenanceError(f"output[{k}]: sha256 is required")


# --- environment -------------------------------------------------------------

def assert_no_unregistered_sources(env: Mapping[str, str] | None = None,
                                   *,
                                   registered_overrides: Mapping[str, str] | None = None) -> None:
    """Forbidden env must be unset; allowlisted env only relocates hashed inputs.

    A forbidden variable is not recorded and tolerated: an unregistered dataset
    overlay is a different dataset, so the run is simply not the run it claims
    to be.
    """
    env = os.environ if env is None else env
    registered = dict(registered_overrides or {})
    for var in FORBIDDEN_ENV:
        if env.get(var):
            if var in registered and str(registered[var]).strip():
                continue          # explicitly authorised by a frozen clause
            raise ProvenanceError(
                f"provenance: {var} is set ({env[var]!r}) but carries no frozen "
                f"preregistration clause. An unregistered overlay is another "
                f"dataset — the sealed run is invalid, not merely annotated."
            )


# --- manifest ----------------------------------------------------------------

@dataclass(frozen=True)
class ProvenanceManifest:
    specification: SpecificationProvenance
    code: CodeProvenance
    config: ConfigProvenance
    data: tuple[DatasetProvenance, ...]
    derived: tuple[DerivedArtifactProvenance, ...]
    execution: ExecutionProvenance
    output: OutputProvenance
    declared_nondeterminism: tuple[str, ...] = field(default=())
    # Bound by the BASELINE seal: the gate L2 will be judged against has to be
    # fixed before the run, or "did it pass" becomes a question answered after
    # seeing the numbers.
    l2_opening_protocol: Mapping[str, Any] = field(default_factory=dict)
    # Set only on an L2 RUN record, naming the baseline it descends from.
    baseline_seal_sha256: str | None = None
    # F0-R7: which serialisation produced every hash in this manifest.
    canonical_hash_version: str = CANONICAL_HASH_VERSION

    @property
    def stage(self) -> str:
        return (SEAL_STAGE_BASELINE
                if self.execution.status == NOT_EXECUTED_PRE_L2
                else SEAL_STAGE_L2_RUN)

    @property
    def sealed_input_sha256(self) -> str:
        """Hash of (code, config, data, initial state) — outputs deliberately excluded."""
        return _h({
            # F0-R6: every required binding appears DIRECTLY, not by implication.
            "specification": asdict(self.specification),
            "code": asdict(self.code),
            "normative_modules": dict(self.code.normative_module_sha256),
            "config": {"hash": self.config.config_sha256,
                       "overrides": dict(self.config.registered_overrides)},
            "data": [asdict(d) for d in self.data],
            "derived": [asdict(d) for d in self.derived],
            "initial_state": self.execution.initial_state_sha256,
            "decision_date": self.execution.decision_date,
            "market_data_as_of": dict(self.execution.market_data_as_of),
            "route": [self.execution.route_module, self.execution.route_version],
            # M-3 (v1.14): the lifecycle state is part of the sealed identity.
            # A baseline and a run over identical inputs are different records,
            # and must not collapse to the same hash.
            "execution_status": self.execution.status,
            "output_status": self.output.status,
            "l2_opening_protocol": dict(self.l2_opening_protocol),
            "baseline_seal_sha256": self.baseline_seal_sha256,
            "canonical_hash_version": self.canonical_hash_version,
        })

    def sealed_input_sha256_payload_sections(self) -> tuple:
        """F0-R6: which bindings the sealed-input hash actually contains.

        Exposed so the binding set is queryable rather than something a
        reader has to re-derive from the hash function."""
        return ("specification", "code", "normative_modules", "config",
                "data", "derived", "initial_state", "decision_date",
                "market_data_as_of", "route", "execution_status",
                "output_status", "l2_opening_protocol", "baseline_seal_sha256",
                "canonical_hash_version")

    @property
    def output_sha256(self) -> str:
        return _h(dict(self.output.artifacts))

    @property
    def manifest_sha256(self) -> str:
        return _h({"inputs": self.sealed_input_sha256, "outputs": self.output_sha256})


@dataclass(frozen=True)
class RepoIdentityGuard:
    """Binds an expected repository identity across the seal critical section.

    This repository carries scheduled tasks that commit to it without human
    action, so preflight and seal are not the same instant. The guard is
    snapshotted before the checks run and re-checked immediately before the
    seal hash is returned; anything that moved in between aborts.
    """
    expected_head: str
    expected_clean: bool
    expected_normative_module_sha256: Mapping[str, str]

    @staticmethod
    def _git(*args: str, repo_root: str | None = None) -> str:
        import subprocess

        proc = subprocess.run(("git",) + args, capture_output=True, text=True,
                              cwd=repo_root)
        if proc.returncode != 0:
            raise ProvenanceError(
                f"provenance: `git {' '.join(args)}` failed — repository identity "
                f"cannot be established: {proc.stderr.strip()}")
        return proc.stdout

    @classmethod
    def snapshot(cls, *, repo_root: str | None = None) -> "RepoIdentityGuard":
        from core.b0_master_prereg import normative_module_hashes

        head = cls._git("rev-parse", "HEAD", repo_root=repo_root).strip()
        porcelain = cls._git("status", "--porcelain", repo_root=repo_root).strip()
        return cls(expected_head=head, expected_clean=not porcelain,
                   expected_normative_module_sha256=dict(normative_module_hashes()))

    def recheck(self, *, repo_root: str | None = None) -> None:
        from core.b0_declaration_conformance import assert_declarations_conform
        from core.b0_master_prereg import normative_module_hashes

        head = self._git("rev-parse", "HEAD", repo_root=repo_root).strip()
        if head != self.expected_head:
            raise SealRaceError(
                f"seal: HEAD moved during the critical section — expected "
                f"{self.expected_head}, found {head}. Something committed to this "
                f"repository while the seal was being taken.")
        porcelain = self._git("status", "--porcelain", repo_root=repo_root).strip()
        is_clean = not porcelain
        if is_clean != self.expected_clean:
            raise SealRaceError(
                f"seal: working tree cleanliness changed during the critical "
                f"section — expected {'clean' if self.expected_clean else 'dirty'}, "
                f"found {'clean' if is_clean else porcelain.splitlines()[:5]}")
        current = dict(normative_module_hashes())
        moved = sorted(k for k in set(current) | set(self.expected_normative_module_sha256)
                       if current.get(k) != self.expected_normative_module_sha256.get(k))
        if moved:
            raise SealRaceError(
                f"seal: normative module hashes changed during the critical "
                f"section: {moved[:5]}")
        assert_declarations_conform()


def seal(manifest: ProvenanceManifest, *, final_seal: bool = True,
         env: Mapping[str, str] | None = None,
         guard: "RepoIdentityGuard | None" = None) -> str:
    """Validate every section and return the manifest hash, or abort.

    `final_seal=True` is the L2-eligible seal: it additionally forbids a dirty
    working tree, because a dirty tree cannot be recovered from a commit alone.

    Two stages exist (M-3 ruling, Master v1.14). A BASELINE manifest declares
    `NOT_EXECUTED_PRE_L2` / `NOT_PRODUCED_PRE_L2` and is the seal that must be
    taken before L2 may open; an L2 RUN manifest carries real outputs and must
    name the baseline it descends from. `guard`, when supplied, is re-checked
    immediately before the hash is returned.
    """
    # An empty `output.artifacts` is a legal BASELINE state, so emptiness alone
    # can no longer stand in for absence: the section object must still exist.
    missing = [s for s in PROVENANCE_SECTIONS if getattr(manifest, s, None) is None]
    if not missing:
        # `data` and `derived` are collections: empty means nothing was declared.
        missing += [s for s in ("data", "derived") if not getattr(manifest, s)]
    if missing:
        raise ProvenanceError(f"provenance: missing sections {sorted(set(missing))}")
    assert_no_unregistered_sources(
        env, registered_overrides=manifest.config.registered_overrides)
    manifest.specification.validate()
    manifest.code.validate(final_seal=final_seal)
    manifest.config.validate()
    for d in manifest.data:
        d.validate()
    for d in manifest.derived:
        d.validate()
    manifest.execution.validate()
    manifest.output.validate()

    # --- stage gates (M-3 ruling, Master v1.14) ------------------------------
    if manifest.stage == SEAL_STAGE_BASELINE:
        if manifest.output.status != NOT_PRODUCED_PRE_L2:
            raise ProvenanceError(
                f"provenance: execution is {NOT_EXECUTED_PRE_L2} but output is "
                f"{manifest.output.status}. A baseline cannot carry outputs of a "
                f"run that has not happened.")
        if not manifest.l2_opening_protocol:
            raise ProvenanceError(
                "provenance: a baseline seal must bind l2_opening_protocol — the "
                "gate L2 will be judged against has to be fixed before the run, "
                "or 'did it pass' becomes a question answered after seeing the "
                "numbers.")
        if manifest.baseline_seal_sha256:
            raise ProvenanceError(
                "provenance: a baseline seal must not reference another baseline; "
                "baseline_seal_sha256 belongs on an L2 run record.")
    else:
        if manifest.output.status != PRODUCED:
            raise ProvenanceError(
                f"provenance: execution is {EXECUTED} but output is "
                f"{manifest.output.status}; a completed run produces artifacts.")
        ref = str(manifest.baseline_seal_sha256 or "")
        if len(ref) != 64:
            raise ProvenanceError(
                "provenance: an L2 run record must name the baseline seal it "
                "descends from via baseline_seal_sha256 (64-hex). A run that "
                "cannot point at the baseline authorising it is unbound.")

    if final_seal:
        # Checked LAST, and only for a final seal. Structural faults surface
        # first because they are actionable here; a blocking data requirement
        # says "everything is well-formed, but the input corpus is still
        # incomplete" — an incomplete corpus must not be sealed as if complete.
        #
        # F-0 added the second check. A seal binds a run to its inputs, so what
        # each hash is required to cover has to be decided BEFORE a seal means
        # anything; sealing under an undefined scope produces a manifest whose
        # guarantee nobody can state.
        from core.b0_declaration_conformance import assert_declarations_conform
        from core.b0_finalization_items import assert_not_blocked

        assert_not_blocked("final_provenance_seal")
        # F0-R4: a declaration the implementation no longer honours hashes
        # exactly like one it does, so the sentences are checked against the
        # behaviour before the manifest claims to bind them.
        assert_declarations_conform()

        from core.b0_frozen_spec import assert_no_blocking_requirements
        try:
            assert_no_blocking_requirements("final_provenance_seal")
        except Exception as exc:
            raise ProvenanceError(str(exc)) from exc

    # LAST statement before the hash exists. Everything above read the
    # repository; this asserts the repository did not move while it was read.
    if guard is not None:
        guard.recheck()
    return manifest.manifest_sha256


# --- baseline immutability ----------------------------------------------------

# Which sealed-input bindings a later L2 run inherits and must not restate
# differently. A run that quietly changed its config or its dataset hashes while
# still pointing at the old baseline would present the baseline's authority over
# inputs the baseline never saw.
BASELINE_BOUND_FIELDS: tuple[str, ...] = (
    "specification", "code", "config", "data", "derived",
    "l2_opening_protocol", "canonical_hash_version",
)


def baseline_binding_sha256(manifest: ProvenanceManifest) -> str:
    """Identity of only the bindings a baseline fixes for every later run."""
    return _h({
        "specification": asdict(manifest.specification),
        "code": asdict(manifest.code),
        "normative_modules": dict(manifest.code.normative_module_sha256),
        "config": {"hash": manifest.config.config_sha256,
                   "overrides": dict(manifest.config.registered_overrides)},
        "data": [asdict(d) for d in manifest.data],
        "derived": [asdict(d) for d in manifest.derived],
        "initial_state": manifest.execution.initial_state_sha256,
        "route": [manifest.execution.route_module, manifest.execution.route_version],
        "l2_opening_protocol": dict(manifest.l2_opening_protocol),
        "canonical_hash_version": manifest.canonical_hash_version,
    })


def assert_baseline_not_mutated(baseline: ProvenanceManifest,
                                run: ProvenanceManifest) -> None:
    """An L2 run record may add outputs; it may not restate the baseline."""
    if baseline.stage != SEAL_STAGE_BASELINE:
        raise ProvenanceError("assert_baseline_not_mutated: first argument is not a baseline")
    if run.stage != SEAL_STAGE_L2_RUN:
        raise ProvenanceError("assert_baseline_not_mutated: second argument is not a run record")
    expected = baseline.manifest_sha256
    if run.baseline_seal_sha256 != expected:
        raise ProvenanceError(
            f"provenance: run names baseline {run.baseline_seal_sha256} but the "
            f"baseline supplied hashes to {expected}")
    if baseline_binding_sha256(run) != baseline_binding_sha256(baseline):
        raise ProvenanceError(
            "provenance: the L2 run restates bindings the baseline already fixed "
            f"({', '.join(BASELINE_BOUND_FIELDS)}). A run may add outputs; it may "
            "not replace the baseline it claims to descend from.")


# --- deterministic replay invariant ------------------------------------------

def verify_replay(original: ProvenanceManifest, replay: ProvenanceManifest) -> None:
    """Same sealed inputs must reproduce the same outputs, bit-exact.

    Declared non-deterministic sources are enumerated per item on the manifest;
    there is deliberately no tolerance parameter. A global tolerance would let a
    genuine difference hide inside rounding.
    """
    if original.sealed_input_sha256 != replay.sealed_input_sha256:
        raise ProvenanceError(
            "replay: sealed inputs differ — this is not a replay of the same run. "
            f"{original.sealed_input_sha256[:12]} vs {replay.sealed_input_sha256[:12]}"
        )
    if original.output_sha256 == replay.output_sha256:
        return
    declared = set(original.declared_nondeterminism) | set(replay.declared_nondeterminism)
    differing = sorted(k for k in set(original.output.artifacts) | set(replay.output.artifacts)
                       if original.output.artifacts.get(k) != replay.output.artifacts.get(k))
    undeclared = [k for k in differing if k not in declared]
    if undeclared:
        raise ProvenanceError(
            f"replay: identical sealed inputs produced different outputs for "
            f"{undeclared} with no declared non-determinism"
        )
