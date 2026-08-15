# P0-R2 Phase D — Offline Validation Report (A-leg-only scope), Round 2

**Round 2 run date:** 2026-08-15 (corrects Round 1 of the same date — Round 1's
`phase_d_offline_validation_report.md` content is entirely superseded by this
file; Round 1's mistakes are documented in §5 for traceability, not repeated).
**Repository HEAD (fixed baseline, verified unchanged throughout both rounds):** `0b1af42224314d71e8d16121d356235ffa7aacf7`
**Staged diff:** empty throughout. **Working tree:** pre-existing unrelated dirty state preserved untouched; no `stash`/`clean`/`reset`; nothing staged or committed.
**Scope authorization:** user decision 2026-08-15 narrowing Phase D to A-leg-only (B-leg/final-fusion PIT raw inputs absent from the frozen snapshot), followed by a Round 2 correction request after reviewing Round 1's result.

---

## 0. Scope and non-claims

Unchanged from Round 1:
- B-leg (c2) parity, final dual-confirm fusion membership parity, any `QUALIFIED` R-FWD record, COMPARABLE_IDENTITY capacity, activation/Stage 2 — all **NOT_EVALUATED**, reason `INSUFFICIENT_FROZEN_PIT_INPUTS`.

**New this round:** A-leg **membership** is also **NOT_EVALUATED**, reason `INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS` — see §1–2. Only A-leg **raw-score** parity remains a reportable result.

---

## 1. R-FWD A-leg-only parity — 4 items disclosed separately

| Item | Round 2 result | Detail |
|---|---|---|
| **Membership (255/255 exact-match)** | **NOT_EVALUATED** — reason `INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS` | The adapter's population ("every stock_id present in the frozen realbody parquet for that date") is not the frozen design's decision-time universe (`listed_ok(as_of) & adv20(as_of) >= 1,000,000`) — computing that eligibility mask independently would need the same raw price/volume HistoryBundle data already missing from the frozen snapshot (§0). Round 1 computed a 169/255 verdict over the common-population intersection of two independently-and-differently-constructed populations and reported it as an official result — that was wrong; retracted. Population-difference **diagnostics** (informational only, not a gate result) are retained below. |
| **Raw-score tolerance (1e-12)** | **PASS** — `max_abs_diff = 0.0`, all 255 months, 255/255 dates had common-key data | See §3: this is the same real, common-key comparison as Round 1, corrected for a representation bug. |
| **Process separation** | `LIMITED_A_LEG_PROCESS_SEPARATION_ONLY` (not a PASS/FAIL claim) | Oracle pid 17192 ≠ adapter pid 8400 — verified only that the two subprocess launches were distinct OS processes. No `PROCESS_IMPORT_MANIFEST` evidence artifact was written this round; the oracle is a reference/research computation, not "production capture" (Round 1 mislabeled it as such). Full FR-24 audit: **NOT_EVALUATED**. |
| **Future-input static check** | `LIMITED_STATIC_CHECK_ONLY` (not a PASS/FAIL claim) | AST scan of `a_leg_adapter.py`'s own source: 0 forbidden-module imports, 0 forbidden-filename call arguments; adapter's only opened file: `realbody_scores_adv100w.parquet`. No `FUTURE_INPUT_ACCESS_TRACE` evidence artifact was written; Round 1's use of `r_fwd_adapter.build_future_input_access_audit` with a `bytes=0`/all-zero-SHA256 placeholder artifact to produce a `"status":"PASS"` result is retracted — that PASS was not backed by real evidence. Full FR-28 audit: **NOT_EVALUATED**. |

**Durable qualification persistence: PENDING** (unchanged). `qualification_status = NOT_QUALIFIED_A_LEG_ONLY_SCOPE`. No qualification record was created in either round.

Full per-month detail: `research/p0_r2_identity_collector/a_leg_parity_result.json` (regenerated this round; Round 1's file is fully superseded, not merged).

---

## 2. Population-difference diagnostics (informational — NOT a parity-gate result)

Mechanically recorded from the same-shaped 255-month run, for transparency about why membership is NOT_EVALUATED rather than merely asserting it:

- **Same population (exact key-set equality), oracle vs adapter: 124/255 months.**
- **Different population: 131/255 months.**
- Round 1's reported 86 "membership mismatches" were a byproduct of comparing two independently-and-differently-constructed populations, not a property of the score computation. This report does **not** re-derive or re-assert Round 1's membership-mismatch figure; membership is NOT_EVALUATED, full stop.
- Round 1's causal narrative ("float32 storage explains the mismatches" / "seasonal earnings clustering") is **retracted** — it explained a raw-score magnitude, not why populations differ, and was not evidenced. No causal claim is made here about *why* the 131 months differ in population; that would itself require the same missing decision-time-universe inputs to investigate rigorously.

---

## 3. Raw-score parity — frozen-semantics reproduction fix

**Root cause (unchanged from Round 1):** `beat_0050/strategies/high52_lab.py`'s `Panel.__init__` builds `Panel.F`/`Panel._real_comp` via a `mat()` closure whose default `dtype=np.float32` — the oracle's real_composite is genuinely stored and compared at float32 precision. The frozen `realbody_scores_adv100w.parquet` stores `real_composite` as float64.

**Round 1's bug:** the adapter read the parquet's native float64 value and compared it directly to the oracle's float32-truncated value — an apples-to-oranges comparison, not a real ~1e-6 disagreement between two independent computations.

**Round 2 fix:** `a_leg_adapter.py::load_adapter_a_leg_scores` now applies `astype(np.float32).astype(np.float64)` to `real_composite` immediately after reading — reproducing the SAME storage representation the oracle's `Panel.REAL_COMP` actually carries, before any ranking or comparison. This is a frozen-semantics reproduction fix (matching what the oracle's own code already does), not a tolerance adjustment or parameter tuning — the `1e-12` tolerance itself is unchanged.

**New regression test** (`tests/test_phase_d_a_leg_parity.py::test_float32_truncation_brings_common_key_raw_scores_within_tolerance`): proves, with a synthetic high-precision float64 source value, that (a) without the fix, adapter-vs-oracle raw scores are NOT within `1e-12` (reproducing Round 1's exact failure mode as a guard against regressing this fix), and (b) with the fix, they ARE within `1e-12` (`max_abs_diff == 0.0`).

**Re-run result (real frozen data, 255 months):** `raw_score_max_abs_diff = 0.0`, `raw_score_within_tolerance_all_dates = true`, common-key data present in all 255/255 months.

---

## 4. Capacity dry-run (P_ONLY_EVIDENCE, 3 fixed dates) — unaffected, byte-identical

Nothing in this round's corrections touches `capacity_driver.py`; it was not re-run. `research/p0_r2_identity_collector/capacity_dry_run_report.json` is **byte-identical** to Round 1's output:

`sha256 = 24ba11d71dcbff603933f0c8747cbf25c1a81005db875c000d652f7b25c9a884`

Round 1's numbers (unchanged, restated for completeness):

| as_of | P-A rows | P-B rows | app-fusion | l4a-fusion | payload bytes | attempt_total_bytes |
|---|---|---|---|---|---|---|
| 2026-08-07 | 885 | 1,670 | 67 | 67 | 370,412 | 517,528 |
| 2026-08-10 | 881 | 1,667 | 67 | 67 | 368,698 | 515,814 |
| 2026-08-11 | 882 | 1,674 | 53 | 53 | 384,318 | 531,434 |

`bootstrap_bytes_per_run = ceil(1.5 × 531,434) = 797,151`. All 3 dates real, no estimate substitution. Temp hygiene re-verified: no leftover `p0r2_capacity_dryrun_*` directories. COMPARABLE_IDENTITY: NOT_EVALUATED (unchanged reason).

---

## 5. What changed from Round 1 (for traceability, per user instruction)

| # | Round 1 (retracted) | Round 2 (corrected) |
|---|---|---|
| 1 | `membership_exact_match_count = 169/255`, reported as a parity-gate result | Membership `NOT_EVALUATED`, reason `INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS`; population-difference diagnostics kept, explicitly non-gate |
| 2 | Causal narrative: "float32 precision → membership mismatch, clustered around seasonal earnings dates" | Retracted — evidence only supports "all 86 Round-1 mismatches occurred in population-different months" (necessary, not sufficient, and not investigated further); no seasonal claim was ever mechanically verified |
| 3 | `raw_score_max_abs_diff = 3.66e-6`, tolerance FAILED | Adapter now reproduces oracle's float32 storage representation before comparison; `max_abs_diff = 0.0`, tolerance PASSED (255/255 months) |
| 4 | `process_isolation_audit`/`future_input_access_audit` built via `r_fwd_adapter.build_process_isolation_audit`/`build_future_input_access_audit` with placeholder `bytes=0`/all-zero-SHA256 "evidence artifacts", producing `"status":"PASS"`; oracle labeled `production_capture_process` | Replaced with `process_separation_check`/`future_input_static_check`, explicitly `LIMITED_*_ONLY` status, no PASS/FAIL claim, no fabricated evidence artifact, oracle re-labeled as a reference computation |
| 5 | Gate C-S marked NOT PASS, reasoning mixed in the real A-leg raw-score/membership failure | Gate C-S re-derived strictly from its own frozen definition (§6) — independent of Gate C-R's parity results |

---

## 6. Gates (per each gate's own frozen definition; never cross-contaminated)

| Gate | Status | Basis |
|---|---|---|
| **Gate H-D** | Carried forward: `PASS — archived by commit 099b9b15171c1e2ffb17e932295ec3c76f60725a` (per `approval_receipt.json`); re-verified only as a git-ancestry check against current HEAD. |
| **Gate C-P** | **NOT PASS.** Frozen definition requires spec approved + primary/mirror roots approved and independent + capacity sufficient (3/3 P_ONLY dry-runs done, `bootstrap_bytes_per_run` measured) + schemas/config/hashes frozen + protected paths/schedule scope explicit. Roots remain unapproved (Stage 2) → cannot PASS regardless of the completed P_ONLY capacity work. |
| **Gate C-R** | **FAIL.** Frozen definition requires 255-month **final** membership exact match + raw-score tolerance pass + no future-return access + process isolation pass. This round only ever attempted A-leg-only raw-score parity (PASS) with membership and full B-leg NOT_EVALUATED, and process isolation itself only reached `LIMITED_A_LEG_PROCESS_SEPARATION_ONLY` (not a real FR-24 audit PASS) and future-input access only reached `LIMITED_STATIC_CHECK_ONLY` (not a real FR-28 audit PASS). None of the 4 PASS conditions are actually met: final membership missing, decision-time-universe inputs missing, complete FR-24/FR-28 audits missing, and the announcement-date PIT blocker (unrelated to this run, unchanged) also independently blocks it. |
| **Gate C-S** | **PASS.** Frozen definition: "AC-3 至 AC-13 的 synthetic/regression tests 全過，現有 production outputs unchanged" — evaluated strictly on its own terms, independent of Gate C-R's real-parity results (Round 1's error). Full regression suite: **1138 passed, 2 skipped (pre-existing, unrelated), 0 failed**, including the required test list's named tests (`test_r_fwd_255_month_membership_parity`, `test_capacity_bootstrap_requires_three_dry_runs`, etc. — all present and passing, synthetic-fixture Phase C versions). Production outputs unchanged: verified via `git diff --stat` against every file this round's code reads (`core/*.py`, `beat_0050/**/*.py`, `scripts/lab_paths.py`, `scripts/identity_collector/{r_fwd_adapter,capacity,fusion,source_adapters,ranking_adapter}.py`) — identical to the pre-existing unrelated dirty-state diff present before this task began, zero new diff added. |
| **Gate C-A** | **NOT EVALUATED** (per instruction). |

**No claim is made that the collector is enabled, activated, or has any qualified/COMPARABLE_IDENTITY capability.** Stage 2 remains entirely unauthorized and untouched.

---

## 7. Tests

- `tests/test_phase_d_a_leg_parity.py`: 13 tests (was 11 in Round 1 — 2 net new: the float32-representation regression test and the membership-field-retraction test; several Round 1 tests rewritten to match the new NOT_EVALUATED/diagnostics shape).
- `tests/test_phase_d_capacity_driver.py`: unchanged, 4 tests (capacity code untouched this round).
- Focused run: `python -m pytest -q tests/test_phase_d_a_leg_parity.py tests/test_phase_d_capacity_driver.py` → **17 passed**.
- Full regression: `python -m pytest -q -p no:cacheprovider tests` → **1138 passed, 2 skipped, 0 failed**.

---

## 8. Follow-up (unchanged from Round 1)

Full R-FWD qualification (B-leg + final membership + decision-time universe + full FR-24/FR-28 evidence-backed audits) requires a new, separately pre-registered and user-approved frozen snapshot of the raw HistoryBundle datasets (`price/per/revenue/income/balance/cashflow/chip/shareholding`). This report does not request or assume that approval.
