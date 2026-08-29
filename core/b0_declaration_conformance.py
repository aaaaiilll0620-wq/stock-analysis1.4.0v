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


def _c_claim_bearing_event_kinds():
    from core import b0_corporate_actions as ca
    return ca.CLAIM_BEARING_EVENT_KINDS


def _conform_claim_only_state_is_ca_applicable() -> None:
    """B0.7 / R3+R4, as behaviour rather than as a sentence.

    Four things have to be true at once, and each of them was false or
    unenforced somewhere before B0.7:

      1. a claim with no covering spell IS reachable by a claim-bearing event
      2. it is NOT reachable by a kind whose frozen transition ignores claims
      3. reaching it opens no underlying holding spell
      4. an event older than the claim does not reach it

    Drop any one and the declaration above still hashes the same.
    """
    from fractions import Fraction

    from core.b0_corporate_actions import (
        CorporateActionEvent, RECONSTRUCTIBLE, ca_economic_interest_applies,
        assert_claim_bearing_registry_conforms,
    )
    from core.b0_state import HoldingSpell, PortfolioState, SecurityReceivable

    claim = SecurityReceivable(
        security_id="AAAA", shares=Fraction(1, 5),
        credit_tradable_date="2018-01-05", event_id="seed|x|2018-01-05",
        origin_effective_date="2018-01-05")
    state = PortfolioState(
        "2019-06-13", 0.0, {}, security_receivables=(claim,),
        applied_ca_event_ids=frozenset({"seed|x|2018-01-05"}),
        holding_spells=(HoldingSpell("AAAA", "2017-05-02", "2017-08-01"),))

    def ev(kind, date):
        return CorporateActionEvent("AAAA", kind, date, RECONSTRUCTIBLE,
                                    knowledge_ts="2010-01-01")

    if state.underlying_exposure_applies("AAAA", "2019-01-05", "2019-06-13"):
        raise DeclarationConformanceError(
            "B0.7/R2: a claim reopened an underlying holding spell")
    if not ca_economic_interest_applies(state, ev("stock_dividend", "2019-01-05"),
                                        as_of="2019-06-13"):
        raise DeclarationConformanceError(
            "B0.7/R3: a claim-bearing event did not reach an outstanding claim; "
            "this is the B0.6 failure, undone")
    if ca_economic_interest_applies(state, ev("cash_capital_increase",
                                              "2019-01-05"),
                                    as_of="2019-06-13"):
        raise DeclarationConformanceError(
            "B0.7/R4: a kind whose transition ignores claims reached one anyway")
    if ca_economic_interest_applies(state, ev("stock_dividend", "2017-09-09"),
                                    as_of="2019-06-13"):
        raise DeclarationConformanceError(
            "B0.7/R3: an event older than the claim reached it; retroactive "
            "application is what B0.1 removed on the underlying side")
    assert_claim_bearing_registry_conforms()


def _conform_ca_event_delivery_scope() -> None:
    """R10: required deliveries arrive; a market row is not a precondition."""
    from fractions import Fraction

    from core.b0_corporate_actions import (
        CorporateActionEvent, NOT_RECONSTRUCTIBLE, deliver_ca_events,
    )
    from core.b0_state import HoldingSpell, PortfolioState, SecurityReceivable

    claim = SecurityReceivable(
        security_id="AAAA", shares=Fraction(1, 5),
        credit_tradable_date="2018-01-05", event_id="seed|x|2018-01-05",
        origin_effective_date="2018-01-05")
    state = PortfolioState(
        "2019-06-13", 0.0, {}, security_receivables=(claim,),
        applied_ca_event_ids=frozenset({"seed|x|2018-01-05"}),
        holding_spells=(HoldingSpell("AAAA", "2017-05-02", "2017-08-01"),))
    gone = CorporateActionEvent(
        "AAAA", "holder_side_reorganization_exit", "2019-01-05",
        NOT_RECONSTRUCTIBLE, "terms not observable", knowledge_ts="2019-01-05")
    future = CorporateActionEvent(
        "AAAA", "stock_dividend", "2019-09-09", NOT_RECONSTRUCTIBLE,
        "terms not observable", knowledge_ts="2019-09-09")

    got = deliver_ca_events({"AAAA": [gone, future]}, state, as_of="2019-06-13")
    ids = [e.canonical_event_id() for e in got]
    if ids != [gone.canonical_event_id()]:
        raise DeclarationConformanceError(
            f"R10: delivery over the economic-interest set returned {ids}; a "
            f"PIT-available event on an outstanding claim must arrive and a "
            f"future one must not")


def _c_l3_price_span_floor_rule():
    from core import b0_l3_price_span as lsp
    return lsp.FLOOR_RULE


def _c_l3_span_endpoint_derivations():
    from core import b0_l3_price_span as lsp
    return lsp.ENDPOINT_DERIVATIONS


def _c_l3_lineage_floor_drift_policy():
    from core import b0_l3_price_span as lsp
    return lsp.FLOOR_DRIFT_POLICY


def _conform_l3_lineage_floor_dispositions() -> None:
    """§19.3 step 3: the three floor relations, exercised rather than restated.

    The sentence "the lineage floor does not drift" is exactly the F0-R4 shape —
    it stays readable while the code under it starts widening the span. So the
    check that backs it asks the code what it DOES when the observed floor is
    later, equal and earlier than the frozen one.
    """
    from core.b0_l3_price_span import L3SpanError, assert_floor_conforms

    frozen = "2010-01-04"
    try:
        assert_floor_conforms(frozen, "2010-01-05")
    except L3SpanError:
        pass
    else:
        raise DeclarationConformanceError(
            "§19.3: an observed floor LATER than the frozen lineage floor means "
            "the required history is missing; it must abort, not proceed shallow")

    if assert_floor_conforms(frozen, frozen) != "PROCEED":
        raise DeclarationConformanceError(
            "§19.3: an observed floor equal to the frozen one is the normal case")

    earlier = assert_floor_conforms(frozen, "2004-01-02")
    if earlier != "CLIP_TO_LINEAGE_FLOOR_NEW_LINEAGE_VERSION_REQUIRED":
        raise DeclarationConformanceError(
            "§19.3: newly available earlier history must leave THIS lineage "
            "clipped to its frozen floor (a new lineage version adopts it); the "
            "disposition returned was %r" % earlier)


def _conform_l3_span_endpoints_are_derived() -> None:
    """§19.2: the three derived endpoints, and the floor that is not defaulted."""
    from core.b0_l3_price_span import (
        L3SpanError, bonus_window, capture_lineage_floor, price_span,
    )

    if price_span("2004-01-02", "2026-03-31") != ("2004-01-02", "2026-03-31"):
        raise DeclarationConformanceError(
            "§19.2: price_span must be (lineage floor, execution session) exactly")
    try:
        price_span("2026-03-31", "2004-01-02")
    except L3SpanError:
        pass
    else:
        raise DeclarationConformanceError(
            "§19.2: an execution session before the floor is an abort — a span "
            "that cannot price the trade the decision authorises is not shorter, "
            "it is invalid")

    # 14 month-ends ending 2026-03 reach 2025-02; the window opens the DAY AFTER
    # that month's last session, which is what makes an event on it divide both
    # momentum anchors alike.
    if bonus_window("2026-03-30", "2025-02-27") != ("2025-02-28", "2026-03-30"):
        raise DeclarationConformanceError(
            "§19.2: bonus_window must open the day after the earliest required "
            "month-end price and close at as_of")
    try:
        bonus_window("2026-03-30", "2025-03-31")
    except L3SpanError:
        pass
    else:
        raise DeclarationConformanceError(
            "§19.2: a month-end session outside the oldest month the reach needs "
            "must abort; a silently short window is how a boundary inside the "
            "reach goes unseen")

    try:
        capture_lineage_floor("2004-01-02", source_manifest_is_hash_bound=False,
                              leg_coverage_is_complete=True,
                              quarantine_applied=True)
    except L3SpanError:
        pass
    else:
        raise DeclarationConformanceError(
            "§19.3 step 1: a floor may not be captured from sources nobody "
            "hashed — that is not evidence a seal can bind")


def _c_l3_capture_binding_chain():
    from core import b0_l3_lineage_capture as lcap
    return lcap.BINDING_CHAIN


def _c_l3_manifest_purposes():
    from core import b0_l3_lineage_capture as lcap
    return lcap.MANIFEST_PURPOSES


def _c_l3_lineage_basis_fields():
    from core import b0_l3_lineage_capture as lcap
    return lcap.LINEAGE_BASIS_FIELDS


def _conform_l3_capture_chain_is_one_way() -> None:
    """§20: a capture binds the authority; the SEAL binds the capture, not both.

    The deadlock this forbids is easy to reintroduce, because binding the seal
    from the capture looks like extra rigour rather than a cycle.
    """
    from core.b0_l3_lineage_capture import (
        CAPTURE_AUTHORITY, LineageCaptureError, PURPOSE_CAPTURE,
        PURPOSE_PRODUCTION, assert_manifest_binding,
    )

    if assert_manifest_binding(PURPOSE_CAPTURE,
                               capture_authority=CAPTURE_AUTHORITY) != \
            PURPOSE_CAPTURE:
        raise DeclarationConformanceError("§20: a capture manifest must be admissible")
    for seal in ("PENDING", "L3SEAL-real-looking", ""):
        try:
            assert_manifest_binding(PURPOSE_CAPTURE, route_seal_id=seal,
                                    capture_authority=CAPTURE_AUTHORITY)
        except LineageCaptureError:
            continue
        raise DeclarationConformanceError(
            "§20: a capture manifest naming route_seal_id %r closes the chain "
            "into a cycle and must abort" % seal)
    try:
        assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id="PENDING",
                                lineage_id="L3-" + "0" * 64,
                                capture_record_sha256="0" * 64)
    except LineageCaptureError:
        pass
    else:
        raise DeclarationConformanceError(
            "§20: 'PENDING' is a placeholder, not a route seal; a production "
            "manifest that accepts it reads as bound in every audit")


def _conform_l3_lineage_identity_is_not_circular() -> None:
    """§20: the id comes from the basis, and the basis may not contain the id."""
    from core.b0_l3_lineage_capture import (
        LINEAGE_BASIS_FIELDS, LineageCaptureError, assert_lineage_id,
        display_alias, lineage_id_from_basis,
    )

    basis = {f: "x" for f in LINEAGE_BASIS_FIELDS}
    lid = assert_lineage_id(lineage_id_from_basis(basis))
    if lineage_id_from_basis(basis) != lid:
        raise DeclarationConformanceError("§20: the identity must be deterministic")
    if lineage_id_from_basis({**basis, "lineage_price_floor": "y"}) == lid:
        raise DeclarationConformanceError(
            "§20: a different floor must name a different lineage")
    try:
        lineage_id_from_basis({**basis, "lineage_id": lid})
    except LineageCaptureError:
        pass
    else:
        raise DeclarationConformanceError(
            "§20: folding the id back into the basis makes the identity depend "
            "on itself; it must abort")
    alias = display_alias(lid)
    if len(alias) >= len(lid):
        raise DeclarationConformanceError("§20: the alias must be shorter than the id")
    try:
        assert_lineage_id(alias)
    except LineageCaptureError:
        return
    raise DeclarationConformanceError(
        "§20: the 16-hex alias is for display; accepting it as an identity is "
        "how a truncated hash becomes a binding")


def _conform_l3_capture_writer_trusts_nobody() -> None:
    """§20: the low-level writer refuses an inadmissible record it is handed.

    A guard that only runs inside the sanctioned transaction is a comment: the
    writer is importable, and a record built by hand reached disk before this.
    """
    from core.b0_l3_lineage_capture import (
        CAPTURE_AUTHORITY, DIAGNOSTIC_EXPECTED_FLOOR, LINEAGE_BASIS_FIELDS,
        LineageCaptureError, RATIFIED_INVENTORY_AUTHORITY,
        assert_record_is_admissible, build_capture_record,
    )

    legs = [{"leg": "pre-2019", "entry_count": 2, "inventory_digest": "a" * 64,
             "leg_floor": "2004-01-02", "quarantine_boundary": "2019-01-01",
             "rows_dropped_by_quarantine": 1, "admissible_rows": 1},
            {"leg": "2019+", "entry_count": 2, "inventory_digest": "a" * 64,
             "leg_floor": "2019-01-02", "quarantine_boundary": "2019-01-01",
             "rows_dropped_by_quarantine": 0, "admissible_rows": 1}]
    basis = {f: "a" * 64 for f in LINEAGE_BASIS_FIELDS}
    basis.update({"capture_authority": CAPTURE_AUTHORITY,
                  "capture_run_id": "L3-FLOOR-CAPTURE-20260826-A01",
                  "as_of": "2026-08-26", "master_version": "1.35",
                  "lineage_price_floor": DIAGNOSTIC_EXPECTED_FLOOR,
                  "repo_commit_sha": "0" * 40, "leg_summaries": legs})
    good = build_capture_record(
        basis, capture_date="2026-08-27",
        required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
        tracked_clean=True, untracked_clean=True)
    assert_record_is_admissible(good)
    for mutate in ({"lineage_price_floor": "2013-01-01"},
                   {"capture_run_id": "whatever"},
                   {"route_seal_id": "L3SEAL-" + "a" * 64},
                   {"tracked_clean": False},
                   {"required_datasets_provenance": "PROVISIONAL"}):
        try:
            assert_record_is_admissible({**good, **mutate})
        except LineageCaptureError:
            continue
        raise DeclarationConformanceError(
            "§20: a record with %s was admitted; the writer must not trust its "
            "caller" % list(mutate))


def _c_l3_floor_capture_required_datasets():
    from core import b0_l3_lineage_capture as lcap
    return lcap.FLOOR_CAPTURE_REQUIRED_DATASETS


def _conform_l3_floor_capture_inventory_is_fixed() -> None:
    """§20.8 / C-71: exactly the causal closure — short OR long is refused."""
    from core.b0_l3_lineage_capture import (
        FLOOR_CAPTURE_REQUIRED_DATASETS, LineageCaptureError,
        assert_capture_inventory, assert_floor_is_a_trading_session,
        assert_prices_are_on_calendar,
    )

    assert_capture_inventory(FLOOR_CAPTURE_REQUIRED_DATASETS)
    for wrong in (("prices",), ("calendar",),
                  tuple(FLOOR_CAPTURE_REQUIRED_DATASETS) + ("valuation",), ()):
        try:
            assert_capture_inventory(wrong)
        except LineageCaptureError:
            continue
        raise DeclarationConformanceError(
            "§20.8: capture inventory %s was accepted; it is fixed, so both a "
            "shorter and a longer set must abort" % (wrong,))

    sessions = ("2004-01-02", "2004-01-05")
    assert_floor_is_a_trading_session("2004-01-02", sessions)
    try:
        assert_floor_is_a_trading_session("2004-01-03", sessions)
    except LineageCaptureError:
        pass
    else:
        raise DeclarationConformanceError(
            "§20.8: a floor that is not a declared session was accepted")
    assert_prices_are_on_calendar(["2004-01-02"], sessions)
    try:
        assert_prices_are_on_calendar(["2004-01-02", "2004-01-03"], sessions)
    except LineageCaptureError:
        pass
    else:
        raise DeclarationConformanceError(
            "§20.8: an off-calendar price row was accepted; it would deepen the "
            "floor silently")


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


# --- v1.37 · C-72 · §9.6e · L2 observation accounting -------------------------

def _c_frozen_b0_l2_replay_permitted():
    from core import b0_master_prereg as mp
    return mp.LINEAGE_L2_REPLAY_PERMITTED[mp.FROZEN_B0_LINEAGE]


def _conform_frozen_b0_reopening_is_unreachable() -> None:
    """§9.6e-R5: no input combination reopens Frozen B0 — including a good one.

    The interesting case is the LAST one. A refusal that only fires on malformed
    input would leave the path open to anyone who fills the form in correctly,
    which is precisely the reading §9.6e-R5 forbids.
    """
    from core.b0_master_prereg import (
        FROZEN_B0_LINEAGE, ImplementationConformanceRepair, L2Opening,
        L2ReopeningUnreachable, L2_RUN_INVALID_CONFORMANCE,
        assert_l2_reopening_reachable, assert_reopening_admissible,
        l2_replay_permitted,
    )

    if l2_replay_permitted(FROZEN_B0_LINEAGE):
        raise DeclarationConformanceError(
            "§9.6e-R5: Frozen B0 reports its L2 replay as permitted")
    try:
        assert_l2_reopening_reachable()          # the default IS Frozen B0
    except L2ReopeningUnreachable:
        pass
    else:
        raise DeclarationConformanceError(
            "§9.6e-R5: the default lineage was reachable; a caller that names "
            "nothing is asking about Frozen B0 and must be refused")

    previous = L2Opening(
        opened_at="2026-08-19T10:03:02.000000+00:00", spec_sha256="a" * 64,
        code_commit="3256270b", data_manifest_sha256="b" * 64,
        outcome=L2_RUN_INVALID_CONFORMANCE)
    good_repair = ImplementationConformanceRepair(
        description="a repair that is well formed in every respect",
        frozen_semantics_reference="§6.1.7 exposure interval rule",
        semantics_frozen_before_run=True, changes_strategy_semantics=False,
        performance_consulted=False, selected_by_portfolio_exposure=False)
    for repair in (None, good_repair):
        try:
            assert_reopening_admissible(
                previous, repair,
                previous_baseline_seal_sha256="c" * 64,
                new_baseline_seal_sha256="d" * 64,
                authorization_reference="a fresh explicit authorization")
        except L2ReopeningUnreachable:
            continue
        except Exception as exc:                 # refused, but for a lesser reason
            raise DeclarationConformanceError(
                "§9.6e-R5: Frozen B0 reopening was refused as %s, not as "
                "unreachable; the lineage question must be asked FIRST, or a "
                "caller who fixes the lesser complaint reaches the mechanism"
                % type(exc).__name__)
        raise DeclarationConformanceError(
            "§9.6e-R5: a Frozen B0 reopening claim was ADMITTED (repair=%r); "
            "the path is closed for every input combination" % (repair,))

    # Scope limit, tested from the other side: the machinery itself still works
    # for a lineage this ruling does not reach. A gate that refused everything
    # would satisfy the check above while quietly deleting C-56.
    assert_l2_reopening_reachable("B1_LINEAGE_NOT_YET_OPENED")


def _conform_reclassification_does_not_reopen_accounting() -> None:
    """§9.6e-R4, on injected rows: accounting follows the seven conditions.

    Three sides, because two would not pin it: an attestation filed against a
    row recorded as F-CA-B does not retire that row (re-classification is not
    an excuse), the same attestation DOES retire a row actually recorded as
    F-CA-C (the rule was not simply broken), and an attestation that denies any
    one condition is refused outright (the exclusion needs all seven).
    """
    import os
    import tempfile

    from core.b0_master_prereg import (
        ATTESTED_CONDITIONS, L2Opening, L2_NOT_EVALUABLE_CA_BLOCK,
        L2_RUN_INVALID_CONFORMANCE, MasterPreregViolation,
        NonConsumptionAttestation, effective_observations,
        record_non_consumption, record_opening,
    )

    opened_at = "2026-08-19T10:03:02.000000+00:00"
    run_id = "L2-0000000000000001"

    def _attestation(**kw):
        base = dict(opened_at=opened_at, run_id=run_id,
                    outcome=L2_RUN_INVALID_CONFORMANCE,
                    ruling="§9.6e-R1 re-classified the defect class",
                    evidence="injected fixture, not a real run")
        base.update({c: True for c in ATTESTED_CONDITIONS})
        base.update(kw)
        return NonConsumptionAttestation(**base)

    def _observed(recorded_outcome, attestation):
        with tempfile.TemporaryDirectory() as tmp:
            reg = os.path.join(tmp, "registry.jsonl")
            att = os.path.join(tmp, "nonconsumption.jsonl")
            record_opening(L2Opening(
                opened_at=opened_at, spec_sha256="a" * 64,
                code_commit="3256270b", data_manifest_sha256="b" * 64,
                outcome=recorded_outcome,
                detail='{"run_id": "%s"}' % run_id), reg)
            if attestation is not None:
                record_non_consumption(attestation, att)
            return effective_observations(reg, att)

    kept = _observed(L2_NOT_EVALUABLE_CA_BLOCK, _attestation())
    if kept != (run_id,):
        raise DeclarationConformanceError(
            "§9.6e-R4: a row recorded as %s was retired by an attestation "
            "naming a re-classified defect class (%r). Accounting must follow "
            "the seven conditions and the RECORDED row, not the re-labelling."
            % (L2_NOT_EVALUABLE_CA_BLOCK, kept))

    excused = _observed(L2_RUN_INVALID_CONFORMANCE, _attestation())
    if excused != ():
        raise DeclarationConformanceError(
            "§9.6a: a fully attested row recorded as %s was still counted "
            "(%r); the narrow exemption itself has stopped working."
            % (L2_RUN_INVALID_CONFORMANCE, excused))

    try:
        _observed(L2_RUN_INVALID_CONFORMANCE,
                  _attestation(zero_effective_decision_observations=False))
    except MasterPreregViolation:
        pass
    else:
        raise DeclarationConformanceError(
            "§9.6a-R2: an attestation denying condition 1 was accepted; the "
            "seven conditions are a conjunction, and the run this ruling "
            "governs fails exactly that one")


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
    DeclarationBinding(
        "ca_claim_only_state_is_ca_applicable", BEHAVIORAL_CONFORMANCE,
        "ca_economic_interest_applies: claim reachable, spell still closed, "
        "non-claim-bearing kinds and pre-claim events still excluded",
        _conform_claim_only_state_is_ca_applicable),
    DeclarationBinding(
        "ca_event_delivery_scope", BEHAVIORAL_CONFORMANCE,
        "deliver_ca_events: PIT-available event on a claim arrives without a "
        "market row; a future event does not",
        _conform_ca_event_delivery_scope),
    DeclarationBinding(
        "ca_claim_bearing_event_kinds", IMPLEMENTATION_DERIVED,
        "core.b0_corporate_actions.CLAIM_BEARING_EVENT_KINDS",
        _derived("ca_claim_bearing_event_kinds", _c_claim_bearing_event_kinds)),

    # --- v1.34 · C-68 · §19 · L3 prospective span endpoints -------------------
    DeclarationBinding(
        "l3_price_span_floor_rule", IMPLEMENTATION_DERIVED,
        "core.b0_l3_price_span.FLOOR_RULE",
        _derived("l3_price_span_floor_rule", _c_l3_price_span_floor_rule)),
    DeclarationBinding(
        "l3_span_endpoint_derivations", IMPLEMENTATION_DERIVED,
        "core.b0_l3_price_span.ENDPOINT_DERIVATIONS",
        _derived("l3_span_endpoint_derivations", _c_l3_span_endpoint_derivations)),
    DeclarationBinding(
        "l3_lineage_floor_drift_policy", IMPLEMENTATION_DERIVED,
        "core.b0_l3_price_span.FLOOR_DRIFT_POLICY",
        _derived("l3_lineage_floor_drift_policy", _c_l3_lineage_floor_drift_policy)),
    DeclarationBinding(
        "l3_lineage_floor_may_drift_within_lineage", BEHAVIORAL_CONFORMANCE,
        "assert_floor_conforms: later aborts, equal proceeds, earlier stays "
        "clipped to the frozen floor",
        _conform_l3_lineage_floor_dispositions),
    DeclarationBinding(
        "l3_span_applies_to", BEHAVIORAL_CONFORMANCE,
        "price_span / bonus_window / capture_lineage_floor: endpoints are "
        "derived or refused, never defaulted",
        _conform_l3_span_endpoints_are_derived),

    # --- v1.35 · C-70 · §20 · lineage floor capture contract ------------------
    DeclarationBinding(
        "l3_capture_binding_chain", IMPLEMENTATION_DERIVED,
        "core.b0_l3_lineage_capture.BINDING_CHAIN",
        _derived("l3_capture_binding_chain", _c_l3_capture_binding_chain)),
    DeclarationBinding(
        "l3_manifest_purposes", IMPLEMENTATION_DERIVED,
        "core.b0_l3_lineage_capture.MANIFEST_PURPOSES",
        _derived("l3_manifest_purposes", _c_l3_manifest_purposes)),
    DeclarationBinding(
        "l3_lineage_basis_fields", IMPLEMENTATION_DERIVED,
        "core.b0_l3_lineage_capture.LINEAGE_BASIS_FIELDS",
        _derived("l3_lineage_basis_fields", _c_l3_lineage_basis_fields)),
    DeclarationBinding(
        "l3_capture_manifest_may_name_a_route_seal", BEHAVIORAL_CONFORMANCE,
        "assert_manifest_binding: a capture naming any seal aborts; a "
        "production manifest refuses a placeholder seal",
        _conform_l3_capture_chain_is_one_way),
    DeclarationBinding(
        "l3_floor_capture_required_datasets", IMPLEMENTATION_DERIVED,
        "core.b0_l3_lineage_capture.FLOOR_CAPTURE_REQUIRED_DATASETS",
        _derived("l3_floor_capture_required_datasets",
                 _c_l3_floor_capture_required_datasets)),
    DeclarationBinding(
        "l3_floor_capture_inventory_is_caller_selectable", BEHAVIORAL_CONFORMANCE,
        "assert_capture_inventory / assert_floor_is_a_trading_session / "
        "assert_prices_are_on_calendar: the closure is fixed, the floor must be "
        "a session, off-calendar rows are refused",
        _conform_l3_floor_capture_inventory_is_fixed),
    DeclarationBinding(
        "l3_capture_writer_trusts_its_caller", BEHAVIORAL_CONFORMANCE,
        "assert_record_is_admissible / write_capture_record_exclusively: a "
        "hand-made record with a wrong floor, run id, seal, dirty tree or "
        "provisional inventory is refused at the writer",
        _conform_l3_capture_writer_trusts_nobody),
    DeclarationBinding(
        "l3_lineage_id_is_the_full_basis_digest", BEHAVIORAL_CONFORMANCE,
        "lineage_id_from_basis / assert_lineage_id: derived from the basis, "
        "deterministic, and the display alias is refused as an identity",
        _conform_l3_lineage_identity_is_not_circular),

    # --- v1.37 · C-72 · §9.6e · L2 observation accounting ---------------------
    DeclarationBinding(
        "frozen_b0_l2_replay_permitted", IMPLEMENTATION_DERIVED,
        "core.b0_master_prereg.LINEAGE_L2_REPLAY_PERMITTED[FROZEN_B0]",
        _derived("frozen_b0_l2_replay_permitted",
                 _c_frozen_b0_l2_replay_permitted)),
    DeclarationBinding(
        "frozen_b0_l2_reopening_is_unreachable", BEHAVIORAL_CONFORMANCE,
        "assert_reopening_admissible: Frozen B0 is refused as unreachable "
        "before anything else is asked, including with a well-formed repair, a "
        "new seal and a named authorization; another lineage still reaches the "
        "mechanism",
        _conform_frozen_b0_reopening_is_unreachable),
    DeclarationBinding(
        "l2_reclassification_does_not_reopen_accounting", BEHAVIORAL_CONFORMANCE,
        "effective_observations on injected rows: an attestation naming a "
        "re-classified defect class does not retire an F-CA-B row, does retire "
        "an F-CA-C row, and is refused outright when any condition is denied",
        _conform_reclassification_does_not_reopen_accounting),
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
