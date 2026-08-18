"""F0-R1 / F0-R4 · every production-reachable declaration, and what backs it.

F0-R1 fixes what `config_hash` covers: the COMPLETE machine-readable declaration
registry, not a runtime-parameter subset. That settles the payload. It does not
settle the thing F-0 actually found, which is subtler and is what F0-R4
addresses:

    a registry entry is a sentence. A sentence can be true when it is written
    and false three commits later, and `config_hash` will not notice, because
    the sentence did not change — the code under it did.

`unexplained_gap_abort_scope = "held_positions_only"` is the sharp case. Rewrite
the guard to ignore holdings and that string still reads `held_positions_only`,
the registry still hashes the same, and every parity check still passes.

So F0-R4 gives every production-reachable declaration one of two backings, and
this module is where the choice is recorded and CHECKED:

  IMPLEMENTATION_DERIVED   the registry value IS the module constant. Change the
                           behaviour and the declaration moves with it, so
                           config_hash moves too. Preferred, and mechanical.
                           Its `check` is therefore NOT a drift detector — both
                           sides read the same constant. What it catches is the
                           derivation being replaced by a copy of today's value,
                           which is how a derived binding silently stops being
                           one.
  BEHAVIORAL_CONFORMANCE   the value is prose that no constant can carry. It is
                           backed by an executable check that exercises the
                           BEHAVIOUR the sentence describes — not by a test that
                           re-reads the sentence.

`verify_declaration_bindings()` runs every check. A declaration with no binding
is a violation, not a default: `assert_declarations_conform()` is what a seal
calls, so an unbacked sentence stops finalization rather than travelling in a
manifest as if it had been verified.

The conformance checks live in core rather than in the test suite on purpose.
A check that only exists under pytest is not available to `seal()`, and "the
tests passed on some machine once" is not a provenance record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

IMPLEMENTATION_DERIVED = "IMPLEMENTATION_DERIVED"
BEHAVIORAL_CONFORMANCE = "BEHAVIORAL_CONFORMANCE"
BINDING_KINDS: tuple[str, ...] = (IMPLEMENTATION_DERIVED, BEHAVIORAL_CONFORMANCE)


class DeclarationConformanceError(RuntimeError):
    """F0-R4: a declaration is not backed by the behaviour it describes."""


@dataclass(frozen=True)
class DeclarationBinding:
    key: str
    kind: str
    evidence: str
    check: Callable[[], None]

    def __post_init__(self) -> None:
        if self.kind not in BINDING_KINDS:
            raise DeclarationConformanceError(
                f"{self.key}: binding kind {self.kind!r} is not defined; "
                f"known kinds are {BINDING_KINDS}")
        if not self.evidence.strip():
            raise DeclarationConformanceError(
                f"{self.key}: a binding must name its evidence")


# --- implementation-derived checks --------------------------------------------

def _derived(key: str, getter: Callable[[], object]):
    def check() -> None:
        from core.b0_master_prereg import spec

        declared, actual = spec(key), getter()
        if declared != actual:
            raise DeclarationConformanceError(
                f"F0-R4: {key} declares {declared!r} but the implementation now "
                f"reads {actual!r}. The declaration is derived from the module, "
                f"so this means the derivation itself was broken.")
    return check


def _c_status_event_semantics():
    from core import b0_market_state as ms
    return ms.EVENT_SEMANTICS


def _c_status_by_event_semantics():
    from core import b0_market_state as ms
    return tuple(sorted((k, v) for k, v in ms.STATUS_BY_EVENT_SEMANTICS.items()))


def _c_price_lookback_sessions():
    from core import b0_listing_spell as ls
    return tuple(sorted(ls.PRICE_LOOKBACK_SESSIONS.items()))


def _c_spell_bridging_tolerance():
    from core import b0_listing_spell as ls
    return ls.SPELL_BRIDGING_SESSION_TOLERANCE


def _c_unknown_fails_closed():
    from core import b0_market_state as ms
    return ms.STATUS_BY_EVENT_SEMANTICS[ms.UNKNOWN_EVENT_SEMANTICS] is None


def _c_book_closure_may_explain():
    from core import b0_market_state as ms
    return ms.STATUS_BY_EVENT_SEMANTICS[ms.BOOK_CLOSURE] is not None


def _c_stale_mark_tolerance():
    from core import b0_pit_observability as pit
    return pit.STALE_MARK_SESSION_TOLERANCE


# --- behavioural conformance checks -------------------------------------------
# Each one exercises the behaviour the sentence claims, on a synthetic case.
# None of them reads the sentence back.

_SESSIONS = ("2020-06-24", "2020-06-25", "2020-06-26", "2020-06-29")
_AS_OF = _SESSIONS[-1]


def _observation(status="listed", available_from=None):
    from core.b0_pit_observability import PitPriceObservation

    return PitPriceObservation(
        as_of=_AS_OF, stock_id="F0R4", price_observed_through=_SESSIONS[0],
        expected_sessions=_SESSIONS, known_status=status,
        status_available_from=available_from)


def _conform_o_e_1_availability_rule() -> None:
    """A status available ON the first missing session must not explain it."""
    from core.b0_pit_observability import (
        EXPLAINED_SUSPENSION, UNEXPLAINED_GAP, classify_price_gap,
    )

    same_day = classify_price_gap(
        _observation("suspended", available_from=_SESSIONS[1]))
    if same_day.classification != UNEXPLAINED_GAP or "O-E-1" not in same_day.reason:
        raise DeclarationConformanceError(
            "F0-R4/O-E-1: a status available on the first missing session was "
            f"classified {same_day.classification}; the rule says strictly before")
    before = classify_price_gap(
        _observation("suspended", available_from=_SESSIONS[0]))
    if before.classification != EXPLAINED_SUSPENSION:
        raise DeclarationConformanceError(
            "F0-R4/O-E-1: a status available strictly before the first missing "
            f"session was classified {before.classification}, not explained")


def _conform_unexplained_gap_abort_scope() -> None:
    """Held aborts; the identical observation unheld does not."""
    from core.b0_pit_observability import (
        PriceObservabilityError, assert_no_unexplained_gap_in_holdings,
    )

    obs = _observation()
    try:
        assert_no_unexplained_gap_in_holdings(_AS_OF, [obs], {"F0R4": 1000})
    except PriceObservabilityError:
        pass
    else:
        raise DeclarationConformanceError(
            "F0-R4/O-F: a HELD position with an unexplained gap did not abort")
    try:
        assert_no_unexplained_gap_in_holdings(_AS_OF, [obs], {})
    except PriceObservabilityError as exc:
        raise DeclarationConformanceError(
            f"F0-R4/O-F: an unexplained gap in a name B0 does not hold aborted "
            f"the route ({exc})") from None


def _conform_status_source_completeness_required() -> None:
    """An unexplained gap that is not held is a diagnostic, not an abort."""
    from core.b0_pit_observability import universe_gap_diagnostic

    report = universe_gap_diagnostic(_AS_OF, [_observation()], holdings={})
    if report["unexplained_total"] != 1 or report["aborts"]:
        raise DeclarationConformanceError(
            f"F0-R4/O-F: source completeness is declared not required, but an "
            f"unheld unexplained gap produced {report}")


def _conform_listing_spell_break_rule() -> None:
    """An unexplained gap then reappearance opens a spell at the first reobserved
    session; an EXPLAINED gap does not open one at all."""
    from core.b0_listing_spell import derive_current_spell

    priced = [s for s in _SESSIONS if s != _SESSIONS[1]]
    broken = derive_current_spell(_AS_OF, "F0R4", _SESSIONS, priced,
                                  lambda _s: False)
    if broken is None or broken.start != _SESSIONS[2] or \
            broken.opened_by != "reappearance":
        raise DeclarationConformanceError(
            f"F0-R4/O-G: an unexplained gap then reappearance produced "
            f"{broken}; the rule says a new spell at the first reobserved session")
    intact = derive_current_spell(_AS_OF, "F0R4", _SESSIONS, priced,
                                  lambda _s: True)
    if intact is None or intact.start != _SESSIONS[0] or \
            intact.opened_by != "first_observation":
        raise DeclarationConformanceError(
            f"F0-R4/O-G: an EXPLAINED gap broke the spell ({intact})")


def _conform_price_lookback_reset() -> None:
    """A window longer than the current spell yields NA, not a number."""
    from core.b0_listing_spell import ListingSpell, price_lookback_or_na

    short = ListingSpell(stock_id="F0R4", start=_SESSIONS[-1],
                         opened_by="reappearance", as_of=_AS_OF)
    if price_lookback_or_na("adv20", short, _SESSIONS, 5e8) is not None:
        raise DeclarationConformanceError(
            "F0-R4/O-G: a spell shorter than the ADV20 window returned a value")
    long_enough = ListingSpell(stock_id="F0R4", start=_SESSIONS[0],
                               opened_by="first_observation", as_of=_AS_OF)
    if price_lookback_or_na("adv20", long_enough, _SESSIONS * 6, 5e8) != 5e8:
        raise DeclarationConformanceError(
            "F0-R4/O-G: a spell long enough for the window returned NA")


def _conform_reappearance_may_not_explain() -> None:
    """The return opens a spell going forward and never accounts for the gap."""
    from core.b0_listing_spell import (
        ListingSpell, ListingSpellError, assert_disappearance_not_explained_by_return,
    )

    spell = ListingSpell(stock_id="F0R4", start=_SESSIONS[2],
                         opened_by="reappearance", as_of=_AS_OF)
    try:
        assert_disappearance_not_explained_by_return(
            spell, _SESSIONS[3], lambda _s: False)
    except ListingSpellError:
        pass
    else:
        raise DeclarationConformanceError(
            "F0-R4/O-G: a disappearance at or after the spell start was accepted; "
            "the ordering that makes the O-F abort PIT-valid was not enforced")


def _conform_snapshot_delisting_audit_only() -> None:
    """The current-snapshot delisting fields stay unreachable from the route."""
    from core.b0_invariants import (
        AUDIT_ONLY_MODULES, AUDIT_ONLY_SYMBOLS, B0_ENTRY_MODULES, find_violations,
    )

    violations = find_violations(B0_ENTRY_MODULES, AUDIT_ONLY_MODULES,
                                 AUDIT_ONLY_SYMBOLS)
    if violations:
        raise DeclarationConformanceError(
            f"F0-R4/O-F: current-snapshot delisting fields are declared "
            f"audit-only but are reachable: {violations}")


def _conform_unknown_status_is_normal() -> None:
    """Absence of a status record must never read as 'trading normally'."""
    from core.b0_market_state import (
        MarketStateError, SecurityStatusTable, SourceContract,
        assert_unknown_is_not_normal,
    )

    contract = SourceContract(
        name="f0r4", kind="security_status", importer_version="f0r4",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min=_SESSIONS[0], date_max=_AS_OF,
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    table = SecurityStatusTable((), contract)
    try:
        assert_unknown_is_not_normal("F0R4", table, has_price_gap=True)
    except MarketStateError:
        pass
    else:
        raise DeclarationConformanceError(
            "F0-R4/O-E: an absent status record did not abort on a price gap")


def _conform_permanent_disappearance_not_a_concept() -> None:
    """O-B carries no 'gone forever' observable to be asked about at as_of."""
    from core.b0_pit_observability import PitPriceObservation

    forbidden = ("permanently_gone", "last_price_date", "final_trading_day")
    present = [f for f in forbidden
               if f in PitPriceObservation.__dataclass_fields__]
    if present:
        raise DeclarationConformanceError(
            f"F0-R4/O-B: {present} reappeared on the PIT observation; permanent "
            f"disappearance is not a concept B0 has at as_of")


# --- the register -------------------------------------------------------------
# Every production-reachable declaration. A key that decides route behaviour and
# is absent here is the gap F0-R4 closes, so the completeness of THIS tuple is
# itself asserted (`assert_declarations_conform`).

DECLARATION_BINDINGS: tuple[DeclarationBinding, ...] = (
    # --- implementation-derived ----------------------------------------------
    DeclarationBinding(
        "status_event_semantics", IMPLEMENTATION_DERIVED,
        "core.b0_market_state.EVENT_SEMANTICS",
        _derived("status_event_semantics", _c_status_event_semantics)),
    DeclarationBinding(
        "status_by_event_semantics", IMPLEMENTATION_DERIVED,
        "core.b0_market_state.STATUS_BY_EVENT_SEMANTICS",
        _derived("status_by_event_semantics", _c_status_by_event_semantics)),
    DeclarationBinding(
        "unknown_event_semantics_fails_closed", IMPLEMENTATION_DERIVED,
        "core.b0_market_state.STATUS_BY_EVENT_SEMANTICS[UNKNOWN]",
        _derived("unknown_event_semantics_fails_closed", _c_unknown_fails_closed)),
    DeclarationBinding(
        "book_closure_may_explain_absence", IMPLEMENTATION_DERIVED,
        "core.b0_market_state.STATUS_BY_EVENT_SEMANTICS[BOOK_CLOSURE]",
        _derived("book_closure_may_explain_absence", _c_book_closure_may_explain)),
    DeclarationBinding(
        "price_lookback_sessions", IMPLEMENTATION_DERIVED,
        "core.b0_listing_spell.PRICE_LOOKBACK_SESSIONS",
        _derived("price_lookback_sessions", _c_price_lookback_sessions)),
    DeclarationBinding(
        "spell_bridging_tolerance", IMPLEMENTATION_DERIVED,
        "core.b0_listing_spell.SPELL_BRIDGING_SESSION_TOLERANCE",
        _derived("spell_bridging_tolerance", _c_spell_bridging_tolerance)),
    DeclarationBinding(
        "stale_mark_session_tolerance", IMPLEMENTATION_DERIVED,
        "core.b0_pit_observability.STALE_MARK_SESSION_TOLERANCE",
        _derived("stale_mark_session_tolerance", _c_stale_mark_tolerance)),

    # --- behavioural conformance ---------------------------------------------
    DeclarationBinding(
        "o_e_1_availability_rule", BEHAVIORAL_CONFORMANCE,
        "classify_price_gap: same-day status does not explain; earlier does",
        _conform_o_e_1_availability_rule),
    DeclarationBinding(
        "status_availability_rule", BEHAVIORAL_CONFORMANCE,
        "same behaviour as o_e_1_availability_rule, stated in O-E's wording",
        _conform_o_e_1_availability_rule),
    DeclarationBinding(
        "unexplained_gap_abort_scope", BEHAVIORAL_CONFORMANCE,
        "assert_no_unexplained_gap_in_holdings: held aborts, unheld does not",
        _conform_unexplained_gap_abort_scope),
    DeclarationBinding(
        "status_source_completeness_required", BEHAVIORAL_CONFORMANCE,
        "universe_gap_diagnostic: unheld unexplained gap reports, does not abort",
        _conform_status_source_completeness_required),
    DeclarationBinding(
        "listing_spell_break_rule", BEHAVIORAL_CONFORMANCE,
        "derive_current_spell: unexplained gap reopens, explained gap does not",
        _conform_listing_spell_break_rule),
    DeclarationBinding(
        "price_lookback_reset_at_spell_start", BEHAVIORAL_CONFORMANCE,
        "price_lookback_or_na: short spell -> NA, long spell -> value",
        _conform_price_lookback_reset),
    DeclarationBinding(
        "reappearance_may_explain_earlier_gap", BEHAVIORAL_CONFORMANCE,
        "assert_disappearance_not_explained_by_return",
        _conform_reappearance_may_not_explain),
    DeclarationBinding(
        "snapshot_delisting_fields_are_audit_only", BEHAVIORAL_CONFORMANCE,
        "AST import-closure: audit-only symbols unreachable from B0 entries",
        _conform_snapshot_delisting_audit_only),
    DeclarationBinding(
        "unknown_status_is_normal", BEHAVIORAL_CONFORMANCE,
        "assert_unknown_is_not_normal: absent record + gap aborts",
        _conform_unknown_status_is_normal),
    DeclarationBinding(
        "permanent_disappearance_is_a_concept", BEHAVIORAL_CONFORMANCE,
        "PitPriceObservation carries no permanence field",
        _conform_permanent_disappearance_not_a_concept),
)

# Declarations that decide what the route does. Every one must be bound above.
# Kept explicit rather than inferred from a naming convention, because a
# convention is what a new key silently fails to follow.
PRODUCTION_REACHABLE_DECLARATIONS: tuple[str, ...] = tuple(
    b.key for b in DECLARATION_BINDINGS)

_BY_KEY: dict[str, DeclarationBinding] = {b.key: b for b in DECLARATION_BINDINGS}

if len(_BY_KEY) != len(DECLARATION_BINDINGS):        # pragma: no cover
    raise RuntimeError("duplicate declaration binding key")


def binding_kinds() -> dict:
    return {b.key: b.kind for b in DECLARATION_BINDINGS}


def verify_declaration_bindings() -> list[str]:
    """Run every check. Returns the failures; empty means all conform."""
    from core.b0_master_prereg import specified_keys

    known = set(specified_keys())
    failures: list[str] = []
    for b in DECLARATION_BINDINGS:
        if b.key not in known:
            failures.append(
                f"{b.key}: bound here but absent from the frozen registry, so "
                f"config_hash does not cover it (F0-R1)")
            continue
        try:
            b.check()
        except Exception as exc:
            failures.append(f"{b.key}: {exc}")
    return failures


def assert_declarations_conform() -> None:
    """F0-R4, as a gate. Called by `seal()`."""
    failures = verify_declaration_bindings()
    if failures:
        raise DeclarationConformanceError(
            f"F0-R4: {len(failures)} production-reachable declaration(s) are not "
            f"backed by the behaviour they describe: {failures[:5]}. A registry "
            f"sentence that the implementation no longer honours hashes exactly "
            f"like one that it does."
        )


def summary() -> dict:
    return {
        "declarations": len(DECLARATION_BINDINGS),
        "implementation_derived": sum(
            1 for b in DECLARATION_BINDINGS if b.kind == IMPLEMENTATION_DERIVED),
        "behavioral_conformance": sum(
            1 for b in DECLARATION_BINDINGS if b.kind == BEHAVIORAL_CONFORMANCE),
        "failures": verify_declaration_bindings(),
    }
