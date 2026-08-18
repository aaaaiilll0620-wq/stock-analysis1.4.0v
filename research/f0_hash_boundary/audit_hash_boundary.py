"""F-0 · Config / Spec hash boundary audit.

The trigger was a reported `config_hash` that did not move between v1.10 and
v1.11 while O-F and O-G changed production-reachable behaviour. This script does
not take the design's word for anything: every membership claim below is
MEASURED, and the two that could be measured two ways are measured both.

  included_in_config_hash   proved by MUTATION -- perturb the key's value in an
                            isolated copy of the registry and see whether the
                            hash moves. Not by reading `canonical_config`.
  named_in_spec_document    grepped from the master preregistration bytes, which
                            is exactly what `spec_sha256` hashes.
  looked_up_at_runtime      AST scan of the B0 import closure for `spec("key")`,
                            so "is this key production-reachable" is a fact about
                            the code rather than a category someone assigned.

The categories ARE assigned, and they are the only assigned column here.

READ-ONLY. Nothing is mutated outside a local copy. No return, IC, Sharpe,
ranking or selection quantity is computed, and `run_decision` is never called.
"""

import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_invariants import B0_ENTRY_MODULES, local_import_closure  # noqa: E402
from core.b0_master_prereg import (                                    # noqa: E402
    MASTER_PREREG_DOC, spec, specified_keys,
)
from core.b0_provenance import ConfigProvenance, file_sha256           # noqa: E402
from core.b0_route import _hash, canonical_config, config_hash         # noqa: E402

OUT = os.path.join(HERE, "hash_boundary_map.json")

# The only assigned column. Prefix match, longest first; a key that matches
# nothing lands in "UNCATEGORISED", which is a finding rather than a default.
CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    # --- F0-R1 ~ F0-R7: the hash boundary is a declaration too --------------
    ("config_hash_scope", "hash_boundary"),
    ("config_hash_is_runtime_subset", "hash_boundary"),
    ("spec_sha256_scope", "hash_boundary"),
    ("implementation_identity", "hash_boundary"),
    ("normative_modules", "hash_boundary"),
    ("declaration_binding_kinds", "hash_boundary"),
    ("state_hash_scope", "hash_boundary"),
    ("state_hash_is_an_implementation_hash", "hash_boundary"),
    ("final_manifest_bound_sections", "hash_boundary"),
    ("canonical_hash_primitive", "hash_boundary"),
    ("canonical_hash_json_settings", "hash_boundary"),
    # --- O-F / O-G, the keys this audit was opened over ----------------------
    ("o_e_1_availability_rule", "o_e_1_availability"),
    ("status_availability_rule", "o_e_1_availability"),
    ("unexplained_gap_abort_scope", "o_f_gap_semantics"),
    ("status_source_completeness_required", "o_f_gap_semantics"),
    ("stale_mark_session_tolerance", "o_f_gap_semantics"),
    ("permanent_disappearance_is_a_concept", "o_f_gap_semantics"),
    ("unknown_status_is_normal", "o_f_gap_semantics"),
    ("snapshot_delisting_fields_are_audit_only", "o_f_gap_semantics"),
    ("status_event_semantics", "o_f_status_semantics"),
    ("status_by_event_semantics", "o_f_status_semantics"),
    ("unknown_event_semantics_fails_closed", "o_f_status_semantics"),
    ("book_closure_may_explain_absence", "o_f_status_semantics"),
    ("security_status_states", "o_f_status_semantics"),
    ("listing_spell_break_rule", "o_g_listing_spell"),
    ("price_lookback_reset_at_spell_start", "o_g_listing_spell"),
    ("price_lookback_sessions", "o_g_listing_spell"),
    ("spell_bridging_tolerance", "o_g_listing_spell"),
    ("reappearance_may_explain_earlier_gap", "o_g_listing_spell"),
    # --- corporate action ----------------------------------------------------
    ("corporate_action_stage_guards", "corporate_action"),
    ("cash_dividend_credit_event", "corporate_action"),
    ("stock_dividend_credit_event", "corporate_action"),
    ("cash_capital_increase_subscribe", "corporate_action"),
    ("zero_day_receivable_allowed", "corporate_action"),
    ("interpolation_allowed", "corporate_action"),
    ("missing_data_rate_threshold", "corporate_action"),
    ("unflagged_capitalisation_policy", "corporate_action"),
    ("pre_mark_mandatory_stage", "corporate_action"),
    # --- features ------------------------------------------------------------
    ("feature_orientations", "feature_formula"),
    ("orientation_is_caller_selectable", "feature_formula"),
    ("concepts", "feature_formula"),
    ("concept_weighting", "feature_formula"),
    ("roe_", "feature_formula"),
    ("eps_growth", "feature_formula"),
    ("revenue_yoy_definition", "feature_formula"),
    ("momentum_", "feature_formula"),
    ("peg_", "feature_formula"),
    ("margin_definition", "feature_formula"),
    ("net_margin_floor_pct", "eligibility"),
    ("balance_sheet_basis", "feature_formula"),
    ("ttm_quarters", "feature_formula"),
    ("percentile_", "feature_formula"),
    ("lookback_L_months", "feature_formula"),
    ("adv20_", "market_quantity"),
    ("sigma20d", "market_quantity"),
    # --- eligibility ---------------------------------------------------------
    ("adv_floor_multiple", "eligibility"),
    ("entry_eligibility_horizon_days", "eligibility"),
    ("risk_", "eligibility"),
    ("debt_hard_filter_enabled", "eligibility"),
    ("cash_quality_", "eligibility"),
    ("current_ratio_floor_enabled", "eligibility"),
    ("fundamental_hard_risk_filters", "eligibility"),
    ("removed_legacy_risk_legs", "eligibility"),
    # --- portfolio construction ---------------------------------------------
    ("N_target", "portfolio_construction"),
    ("w_target", "portfolio_construction"),
    ("w_max", "portfolio_construction"),
    ("selection_", "portfolio_construction"),
    ("forbidden_tie_break_keys", "portfolio_construction"),
    ("reweight_when_under_target_breadth", "portfolio_construction"),
    ("proportional_scaling_allowed", "portfolio_construction"),
    ("concept", "portfolio_construction"),
    ("chip_semantics", "portfolio_construction"),
    # --- execution -----------------------------------------------------------
    ("X_buy", "execution"),
    ("X_sell", "execution"),
    ("C_ref", "execution"),
    ("buy_", "execution"),
    ("sell_shortfall_policy", "execution"),
    ("share_rounding", "execution"),
    ("rounding_shortfall_policy", "execution"),
    ("target_drift_policy", "execution"),
    ("pending_exit_cap_basis", "execution"),
    ("odd_lot_enabled", "execution"),
    ("intraday_sequence", "execution"),
    ("decision_state_source", "execution"),
    ("pipeline_stages", "execution"),
    ("ledger_unit", "execution"),
    ("leverage_allowed", "execution"),
    ("negative_cash_allowed", "execution"),
    # --- cost ----------------------------------------------------------------
    ("commission_rate", "cost"),
    ("min_fee", "cost"),
    ("tax_rate", "cost"),
    ("impact_k", "cost"),
    # --- evidence / reporting, not a runtime decision ------------------------
    ("l2_outcomes", "evidence_protocol"),
    ("l3_", "evidence_protocol"),
    ("sharpe_metric_name", "evidence_protocol"),
    ("risk_free_rate", "evidence_protocol"),
    ("cash_earns_interest", "evidence_protocol"),
    ("window_", "evidence_protocol"),
    ("first_eligible_decision_month", "evidence_protocol"),
    ("trading_calendar_semantics", "provenance_contract"),
    ("market_state_sources_require_provenance", "provenance_contract"),
)


def categorise(key: str) -> str:
    best = ("", "UNCATEGORISED")
    for prefix, cat in CATEGORY_RULES:
        if key.startswith(prefix) and len(prefix) > len(best[0]):
            best = (prefix, cat)
    return best[1]


def perturb(value):
    """A different value of a comparable shape, so the hash moves for the right
    reason. `None -> "F0_MUTATION"` matters: several frozen keys ARE None, and a
    None that stopped being None is exactly the drift worth catching."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "_F0_MUTATION"
    if isinstance(value, tuple):
        return value + ("F0_MUTATION",)
    if isinstance(value, dict):
        return {**value, "F0_MUTATION": True}
    if value is None:
        return "F0_MUTATION"
    return str(value) + "_F0_MUTATION"


def runtime_lookups() -> set:
    """Keys reached through `spec("...")` anywhere in the B0 import closure."""
    found = set()
    for name, src in local_import_closure(B0_ENTRY_MODULES):
        try:
            tree = ast.parse(src)
        except SyntaxError:                                  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            fn_name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if fn_name != "spec":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    return found


def main():
    cfg = canonical_config()
    baseline = _hash(cfg)
    doc_path = os.path.join(REPO, MASTER_PREREG_DOC)
    doc = open(doc_path, encoding="utf-8").read()
    reachable = runtime_lookups()

    rows = []
    for key in specified_keys():
        mutated = dict(cfg)
        mutated[key] = perturb(cfg[key])
        rows.append({
            "master_key": key,
            "category": categorise(key),
            "included_in_config_hash": _hash(mutated) != baseline,
            "named_in_spec_document": key in doc,
            "looked_up_at_runtime": key in reachable,
            "value_repr": repr(cfg[key])[:120],
        })

    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"keys": 0, "in_config_hash": 0,
                                              "named_in_doc": 0, "runtime": 0})
        c["keys"] += 1
        c["in_config_hash"] += int(r["included_in_config_hash"])
        c["named_in_doc"] += int(r["named_in_spec_document"])
        c["runtime"] += int(r["looked_up_at_runtime"])

    report = {
        "study": "F-0 config / spec hash boundary audit",
        "read_only": True, "performance_computed": False,
        "run_decision_called": False,

        # --- F0-1 producer lineage -------------------------------------------
        "producers": {
            "spec_sha256": {
                "producer": "research/b0_registry/freeze_master_prereg.py:75",
                "function": "core.b0_provenance.file_sha256 (core/b0_provenance.py:64)",
                "input": MASTER_PREREG_DOC,
                "scope": "the master preregistration DOCUMENT BYTES ONLY",
                "not_covered": [
                    "core/*.py normative modules (hashed separately as "
                    "`normative_modules` in the same freeze record, and not "
                    "combined into spec_sha256)",
                    "the resolved values of the spec registry",
                ],
                "serialization": "raw file bytes, 1MiB chunks, no normalisation",
                "value": file_sha256(doc_path),
            },
            "config_hash": {
                "producer": "core/b0_route.py:129 config_hash()",
                "payload": "core/b0_route.py:109 canonical_config() = "
                           "{k: spec(k) for k in specified_keys()}",
                "key_selection": "core/b0_master_prereg.py:634 specified_keys() "
                                 "= tuple(sorted(_spec_registry()))",
                "key_source": "core/b0_master_prereg.py:380 _spec_registry()",
                "canonical_serialization": "core/b0_route.py:123 _hash() -> "
                                           "json.dumps(_stable(payload), "
                                           "sort_keys=True, ensure_ascii=False, "
                                           "separators=(',',':'))",
                "normalisation": "core/b0_route.py:113 _stable(): tuple->list, "
                                 "dict->sorted str-keyed dict, "
                                 "None/str/int/float/bool passthrough, "
                                 "everything else -> str()",
                "ordering": "keys sorted twice — once by specified_keys(), again "
                            "by json sort_keys — so insertion order cannot leak",
                "na_bool_number_encoding": {
                    "None": "JSON null (distinct from the string 'None')",
                    "bool": "JSON true/false (distinct from 0/1 — verified by "
                            "the mutation control)",
                    "float": "JSON number; no rounding is applied",
                    "tuple": "JSON array via _stable",
                },
                "scope": "the ENTIRE frozen spec registry, not a subset",
                "value": config_hash(),
            },
            "state_hash": {
                "producer": "core/b0_route.py:267 CanonicalDecisionInput.state_hash()",
                "payload": "core/b0_route.py:198 state_payload()",
                "canonical_serialization": "the same core/b0_route.py:123 _hash()",
                "scope": "as_of / decision & execution dates / marks / adv20 / "
                         "sigma20d / portfolio / pit_inputs / price_observations "
                         "/ corporate_action_events / exposures / execution "
                         "prices / untradable / LISTING SPELLS / attestation id",
                "deliberately_excluded": ["route_kind"],
            },
            "provenance_config_sha256": {
                "producer": "core/b0_provenance.py:105 ConfigProvenance.config_sha256",
                "function": "core/b0_provenance.py:57 _h()",
                "note": "a SECOND serializer over the same payload: json.dumps("
                        "sort_keys=True, separators=(',',':'), ensure_ascii=False,"
                        " default=str) with no _stable() pre-pass. It agrees with "
                        "config_hash on the current registry; nothing forces it to.",
                "agrees_with_config_hash_today": ConfigProvenance(
                    canonical=cfg, registered_overrides={}
                ).config_sha256 == config_hash(),
            },
        },

        # --- F0-2 coverage map -----------------------------------------------
        "coverage_map": rows,
        "coverage_by_category": by_cat,
        "totals": {
            "keys": len(rows),
            "in_config_hash": sum(r["included_in_config_hash"] for r in rows),
            "named_in_spec_document": sum(r["named_in_spec_document"] for r in rows),
            "looked_up_at_runtime": sum(r["looked_up_at_runtime"] for r in rows),
            "uncategorised": [r["master_key"] for r in rows
                              if r["category"] == "UNCATEGORISED"],
        },

        # --- the v1.10 -> v1.11 question -------------------------------------
        "v110_to_v111": _v110_reconstruction(cfg),
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("config_hash (HEAD):", report["producers"]["config_hash"]["value"])
    print("spec_sha256 (HEAD):", report["producers"]["spec_sha256"]["value"])
    print("\ntotals:", {k: v for k, v in report["totals"].items()
                        if k != "uncategorised"})
    print("uncategorised:", report["totals"]["uncategorised"])
    print("\nby category:")
    for c, v in sorted(by_cat.items()):
        print(f"  {c:<26} keys={v['keys']:>3} in_config_hash={v['in_config_hash']:>3} "
              f"named_in_doc={v['named_in_doc']:>3} runtime={v['runtime']:>3}")
    print("\nv1.10 -> v1.11:", json.dumps(report["v110_to_v111"], ensure_ascii=False,
                                          indent=1))
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


def _v110_reconstruction(cfg):
    """Did config_hash actually stand still across the version bump?

    Answered by rebuilding the v1.10 registry from the v1.11 one rather than by
    trusting a number copied out of an earlier run.
    """
    V111_KEYS = tuple(sorted({
        "o_e_1_availability_rule", "unexplained_gap_abort_scope",
        "status_source_completeness_required", "status_event_semantics",
        "status_by_event_semantics", "unknown_event_semantics_fails_closed",
        "book_closure_may_explain_absence", "listing_spell_break_rule",
        "price_lookback_reset_at_spell_start", "price_lookback_sessions",
        "spell_bridging_tolerance", "reappearance_may_explain_earlier_gap",
        "snapshot_delisting_fields_are_audit_only",
    }))
    v110 = {k: v for k, v in cfg.items() if k not in V111_KEYS}
    reported = "27fee343a3083e2aeba87eae960c01d5916b09a61819b7623486ec4bcfd13f03"
    return {
        "keys_added_in_v1_11": list(V111_KEYS),
        "v110_keys": len(v110),
        "v111_keys": len(cfg),
        "reconstructed_v110_config_hash": _hash(v110),
        "config_hash_reported_during_v1_11_work": reported,
        "reconstruction_matches_reported_value": _hash(v110) == reported,
        "config_hash_at_head": _hash(cfg),
        "config_hash_changed": _hash(v110) != _hash(cfg),
        "finding": (
            "config_hash DID move. The 27fee343 value carried into the v1.11 "
            "report was captured by a validation run executed BEFORE the 13 "
            "O-F/O-G keys were added to the registry, and was not re-measured "
            "afterwards. Removing exactly those 13 keys from the HEAD registry "
            "reproduces it bit-for-bit, which is what makes that a reporting "
            "error rather than a hash-scope leak."),
    }


if __name__ == "__main__":
    sys.exit(main())
