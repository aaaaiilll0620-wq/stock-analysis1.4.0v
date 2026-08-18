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

from core.b0_canonical_hash import canonical_sha256
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


class ProvenanceError(RuntimeError):
    """Fail-loud: a sealed run cannot be bound to its inputs."""


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

    def validate(self) -> None:
        for f in ("decision_date", "initial_state_sha256", "route_module", "route_version"):
            if not getattr(self, f):
                raise ProvenanceError(f"execution: {f} is required")
        if not self.market_data_as_of:
            raise ProvenanceError("execution: market_data_as_of is required")


@dataclass(frozen=True)
class OutputProvenance:
    artifacts: Mapping[str, str]             # artifact name -> sha256

    def validate(self) -> None:
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
        })

    def sealed_input_sha256_payload_sections(self) -> tuple:
        """F0-R6: which bindings the sealed-input hash actually contains.

        Exposed so the binding set is queryable rather than something a
        reader has to re-derive from the hash function."""
        return ("specification", "code", "normative_modules", "config",
                "data", "derived", "initial_state", "decision_date",
                "market_data_as_of", "route")

    @property
    def output_sha256(self) -> str:
        return _h(dict(self.output.artifacts))

    @property
    def manifest_sha256(self) -> str:
        return _h({"inputs": self.sealed_input_sha256, "outputs": self.output_sha256})


def seal(manifest: ProvenanceManifest, *, final_seal: bool = True,
         env: Mapping[str, str] | None = None) -> str:
    """Validate every section and return the manifest hash, or abort.

    `final_seal=True` is the L2-eligible seal: it additionally forbids a dirty
    working tree, because a dirty tree cannot be recovered from a commit alone.
    """
    missing = [s for s in PROVENANCE_SECTIONS if getattr(manifest, s, None) in (None, (), {})]
    if missing:
        raise ProvenanceError(f"provenance: missing sections {missing}")
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
    return manifest.manifest_sha256


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
