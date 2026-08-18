"""M-3 register for specification gaps OUTSIDE the canonical core layers.

`core.b0_open_items` is the P-1b register: it holds behaviours a canonical-core
LAYER reaches at runtime, and `assert_selection_path_is_fully_specified` reads it
as "is the Selection path fully specified". A gap in provenance or hash scope is
not a Selection-path behaviour, and filing it there would make S-1 report a false
red — so it gets its own register rather than a widened one.

What lands here has the same M-3 status as anything in the other register: the
master preregistration is silent, silence is not a licence to choose, and the
run that would depend on the choice stops. The difference is only WHICH run
stops. These items block **finalization** — the final provenance seal — because
that is the step whose meaning depends on them.

The register is consulted by `core.b0_provenance.seal(final_seal=True)`, so an
open item is a mechanical stop and not a note somebody has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

BLOCKS: tuple[str, ...] = ("final_provenance_seal", "L2_opening")


class FinalizationBlocked(RuntimeError):
    """M-3: finalization depends on a scope the specification has not defined."""


@dataclass(frozen=True)
class FinalizationItem:
    key: str
    question: str
    why_it_matters: str
    measured: str                  # what the audit actually found
    options: tuple[str, ...]       # candidate rulings, NOT a recommendation
    blocks: tuple[str, ...]
    opened_by: str

    def __post_init__(self) -> None:
        for f in ("key", "question", "why_it_matters", "measured", "opened_by"):
            if not str(getattr(self, f)).strip():
                raise ValueError(f"{self.key or '?'}: {f} is required")
        if len(self.options) < 2:
            raise ValueError(
                f"{self.key}: an item with fewer than two candidate rulings is a "
                f"decision already taken, which is what this register exists to "
                f"prevent")
        bad = [b for b in self.blocks if b not in BLOCKS]
        if bad:
            raise ValueError(f"{self.key}: unknown blocked stage(s) {bad}")


# RESOLVED and removed from this register:
#
#   hash_scope_boundary -> F0-R1 ~ F0-R7 (master prereg v1.13, §11 C-46).
#       config_hash = the COMPLETE machine-readable declaration registry;
#       spec_sha256 = raw-byte identity of the frozen master document;
#       implementation identity = commit SHA + explicit normative-module hashes;
#       production-reachable declarations = implementation-derived or backed by
#           an executable behavioural conformance check
#           (core/b0_declaration_conformance.py);
#       state_hash = canonical concrete input-state identity, never an
#           implementation hash;
#       the B-21 manifest binds all of them DIRECTLY;
#       one shared serialization/hash primitive (core/b0_canonical_hash.py).
#
# The register stays. It is empty because the item was ruled on, not because
# the mechanism was retired -- the next finalization-blocking gap lands here
# rather than in somebody's judgement about whether a seal is safe.
FINALIZATION_ITEMS: tuple[FinalizationItem, ...] = ()


_BY_KEY: dict[str, FinalizationItem] = {i.key: i for i in FINALIZATION_ITEMS}

if len(_BY_KEY) != len(FINALIZATION_ITEMS):      # pragma: no cover
    raise RuntimeError("duplicate finalization-item key")


def open_keys() -> tuple[str, ...]:
    return tuple(i.key for i in FINALIZATION_ITEMS)


def items_blocking(stage: str) -> tuple[FinalizationItem, ...]:
    if stage not in BLOCKS:
        raise ValueError(f"unknown stage {stage!r}; known stages are {BLOCKS}")
    return tuple(i for i in FINALIZATION_ITEMS if stage in i.blocks)


def assert_not_blocked(stage: str) -> None:
    """Abort while a scope this stage depends on is still undefined."""
    blocking = items_blocking(stage)
    if blocking:
        detail = "; ".join(f"{i.key}: {i.question}" for i in blocking)
        raise FinalizationBlocked(
            f"M-3: {stage} is blocked by {len(blocking)} undefined "
            f"specification scope(s) — {detail}. The implementer must not pick "
            f"the scope; a ruling has to."
        )


def summary() -> dict:
    """Machine-readable mirror, so 'how much is undecided' stays a query."""
    return {
        "total": len(FINALIZATION_ITEMS),
        "keys": list(open_keys()),
        "by_stage": {s: len(items_blocking(s)) for s in BLOCKS},
    }
