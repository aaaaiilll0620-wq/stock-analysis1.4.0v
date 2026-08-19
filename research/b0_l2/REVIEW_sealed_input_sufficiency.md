# Review · sealed-input materialization sufficiency + outcome vocabulary

**Scope (fixed by the ruling):** sealed-input materialization sufficiency, and
outcome vocabulary conformance. **No strategy semantics may change.** This
document is review material only — nothing below has been implemented.

Derived from run `L2-2520c80aa980d681` (`RUN INVALID — IMPLEMENTATION CONFORMANCE
FAILURE`), against Baseline Seal `7faad84a…` / Master v1.20 / commit `d49222b1`.

Every requirement below was **measured**, by driving each frozen member with
synthetic series and recording the shortest input at which it stops returning
`None` — not read off a docstring.

---

## 1 · Dependency-lookback matrix (transitive closure, all 11 frozen members)

§4.1 complete-case requires **all eleven**. One NA rejects the row, so the
binding constraint is the maximum over the whole set, per input series.

| frozen member | input series | measured minimum | sealed state supplies | margin | verdict |
|---|---|---|---|---|---|
| `roe` | `net_income_by_quarter` | 4 | 8 | +4 | OK |
| `net_margin` | `net_income_by_quarter`, `revenue_by_quarter` | 4 | 8 | +4 | OK |
| `gross_margin` | `gross_profit_by_quarter`, `revenue_by_quarter` | 4 | 8 | +4 | OK |
| `eps_growth` | `eps_by_quarter` | 5 | 8 | +3 | OK |
| `PEG` | `eps_by_quarter` (via `eps_growth`) + `per_tse` | 5 | 8 | +3 | OK |
| `debt_to_asset` | scalars | — | scalar | — | OK |
| `current_ratio` | scalars | — | scalar | — | OK |
| `value_ind_pct_b` | cross-section (`pbr_tse`, `pit_industry`) | ≥2 per industry | full universe | — | OK |
| `momentum_12_1` | `month_end_prices` | **14** | **14** | **0** | OK, zero margin |
| `revenue_yoy` | `monthly_revenue` | **13** | **13** | **0** | OK, zero margin |
| `revenue_accel` | `monthly_revenue` | **18** | **13** | **−5** | **DEFECT D-1** |

**Binding constraint per series:**

```
monthly_revenue          max(13, 18) = 18     supplied 13   -> UNDER-SUPPLIED
month_end_prices         14                   supplied 14   -> exactly met
quarterly series         max(4, 4, 4, 5) = 5  supplied 8    -> met
```

The frozen registry already states the answer: `lookback_L_months = 18`, and
`compute_revenue_accel`'s own docstring says *"L = 18 is derived from it"*. The
materializer used 13 and no check compared the two.

### Why 141/141 hashing green did not catch it

The 141 state hashes prove *the same inputs produce the same bytes*. They cannot
prove *the inputs satisfy the frozen members' lookback*. Nothing in the repo
compared a member's requirement against what the materializer supplies — that
absent comparison is the root cause, not the number 13.

---

## 2 · Two further defects in the same class (found by the closure sweep)

The ruling asked specifically that this not stop at `revenue_accel`. It should
not.

### D-2 · quarterly series are published-row-ordered, not calendar-indexed

`compute_eps_growth` is positional: `EPS_t` vs `EPS_{t-4}` = `series[-1]` vs
`series[-5]`. `compute_roe_ttm` / `compute_margin_ttm` sum "the four most recent
quarterly" values. The materializer supplies **the last 8 published quarters,
gaps closed up**. Measured at period 1:

```
securities with 8 published quarters        1,730
  whose last 8 are NOT calendar-contiguous    177   (10.23%)
```

For those 177, `series[-5]` is **not** four quarters before `series[-1]`, so
`eps_growth` (and therefore `PEG`) compares the wrong base period, and the TTM
sums span five calendar quarters instead of four. It produces a number, and the
number is silently wrong — the same failure shape as D-1, one layer down.

> **This one carries an M-3-shaped ambiguity and I am not resolving it here.**
> `compute_roe_ttm` says "the four most recent quarterly net incomes, where q is
> the latest quarter published on or before the decision date". That admits two
> readings: *four most recent PUBLISHED* (current behaviour) or *four most recent
> CALENDAR quarters, absent ones as None* (which propagates NA to complete-case).
> `compute_eps_growth`'s `EPS_{t-4}` reads as calendar. **Which reading is frozen
> is a ruling, not a materializer choice**, and the two differ for 10.23% of the
> universe. Recorded for decision; no code proposed until it is ruled.

### D-3 · monthly_revenue relies on an unguaranteed property

`compute_revenue_yoy` is likewise positional (`[-1]` vs `[-13]`). Measured at
period 1: **0 of 1,647** securities have a non-contiguous last-18 window, so the
current output is correct — but by luck of the corpus, not by construction. A
future vintage with one missing month would silently mis-compare.

`month_end_prices` is already calendar-indexed with explicit `None` (built from
`pd.period_range`), which is the shape the other two should have.

---

## 3 · Impacted-files inventory

| file | change class | what changes |
|---|---|---|
| `research/b0_materializer/build_market_side_state.py` | **materialization sufficiency** | `MONTHS_REVENUE 13 → 18`; derive the constant from the frozen members instead of a literal; calendar-index the revenue window (D-3); quarterly indexing only if D-2 is ruled calendar |
| `core/b0_master_prereg.py` | **vocabulary conformance** | extend `L2_OUTCOMES`; add a `feature_input_requirements` declaration so the requirement is registered, not inferred |
| `core/b0_features.py` | **read-only introspection** | add a pure accessor exposing each member's minimum series length. **No formula, no constant, no threshold changes** |
| `docs/FrozenB0_MasterPreregistration.md` | amendment | §4.1a (input sufficiency) + §M-2 vocabulary; version → 1.21 |
| `research/b0_registry/freeze_master_prereg.py` | version bump | 1.20 → 1.21 |
| `tests/test_b0_input_sufficiency.py` | **new** | the closure test (below) |
| `tests/test_b0_l2_outcomes.py` | **new** | vocabulary conformance |
| `data/b0/market_state/*.parquet`, `market_state_manifest.json` | rebuild | 141 states rebuilt; **composed hash WILL change** (`bbe3d06d…` → new) |
| `research/b0_materializer/*_receipt.json`, `preflight_141_receipt.json` | regenerate | new hashes |
| `artifacts/baseline_seal/…` | new seal | v1.21 seal; `7faad84a…` marked SUPERSEDED with reason |

**Explicitly NOT touched:** `b0_eligibility.py`, `b0_decision.py`,
`b0_execution.py`, `b0_cost_model.py`, `b0_corporate_actions.py`,
`b0_share_unit_adjustment.py`, `b0_bonus_share_source.py`,
`b0_valuation_source.py`, any factor formula, any threshold, weight, universe
rule, `share_rounding`, the 5% cap, or CA semantics.

**Expected hash movement:** the 141-state composed hash changes because
`monthly_revenue` genuinely gains 5 months of content. That is a *content*
change to sealed inputs, not a provenance-only change, and the new authorization
must bind the new value.

---

## 4 · Proposed tests

**T-1 · transitive lookback closure (the test whose absence caused this).**
For every member in `required_feature_keys()`, binary-search its minimum length
per input series, and assert the materializer's supplied length ≥ that minimum.
Parameterised over members, so a new member cannot be added without appearing.

**T-2 · no zero-margin by accident.** Assert supplied ≥ required and report the
margin; require the *reason* for any zero-margin case to be declared, so
`momentum_12_1` at exactly 14 is a stated decision rather than a coincidence.

**T-3 · registry agreement.** Assert the measured `monthly_revenue` requirement
equals the frozen `lookback_L_months = 18`. Had this existed, D-1 would have been
a red test before the seal.

**T-4 · sealed-state sufficiency, on the artefacts.** Over all 141 sealed states,
assert every supplied series length ≥ requirement, and that `revenue_accel` is
not NA for 100% of any period.

**T-5 · complete-case is reachable.** Assert at least one security passes §4.1
complete-case in every one of the 141 periods. A universe-wide rejection is now a
test failure, not a silently valid run. *(This asserts reachability only — no
count, no name, no score.)*

**T-6 · calendar contiguity.** Assert each supplied monthly/quarterly window is
calendar-contiguous or carries explicit `None` for absent periods, so the
positional readers are given the shape they assume.

**T-7 · vocabulary conformance.** Assert `L2_OUTCOMES` contains a token for every
formal result §6.1.14 and the result ontology name — including
`RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` and
`NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK`.

**T-8 · terminal outcomes are recordable.** Assert `L2Opening` accepts each
terminal outcome — this run could not record its own result.

---

## 5 · Master amendment diff (proposed)

```diff
+### 4.1a Input sufficiency (v1.21, normative)
+
+每一個 §4.1 complete-case 成員都有 minimum input lookback。
+materializer 供給的序列長度 MUST >= 該成員的 minimum,且該需求 MUST 由凍結成員
+自身推導,不得在 materializer 中以 literal 重述。
+
+  monthly_revenue    >= 18   (revenue_accel 6 x YoY,每個 YoY 13 個月)
+  month_end_prices   >= 14   (momentum_12_1)
+  quarterly series   >=  5   (eps_growth)
+
+供給不足 = sealed-input materialization defect,屬 F-CA-A 類 pre-open baseline
+defect;MUST 於 Baseline Seal 前由 conformance preflight 擋下,不得於 sealed run
+期間發現後修補。
+
+**§4.1a-R2 · 序列形狀。** positional reader(`series[-1]` vs `series[-13]` /
+`[-5]`)要求 calendar-indexed 序列,缺漏期以顯式 `None` 表示,不得將缺漏期
+壓縮掉。壓縮會使比較基期靜默錯位。
+
+### M-2 · L2 outcome vocabulary (v1.21)
+
-L2_OUTCOMES = (SUPPORTED, NOT_SUPPORTED, NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK)
+L2_OUTCOMES = (SUPPORTED,
+               NOT_SUPPORTED,
+               NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK,
+               NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK,   # §6.1.14 F-CA-B
+               RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE)        # §6.1.14 F-CA-C
+
+§6.1.14 於 v1.20 引入兩個正式結果而未擴充機器詞彙,致本次 run 無法記錄自身結果。
+機器詞彙 MUST 覆蓋 result ontology 的每一個終局值。
```

*(Diff is directional. `L2_OUTCOMES` is a frozen tuple; extending it is a
normative change and needs a new Master version and a new seal.)*

---

## 6 · What I need ruled before implementing

1. **D-2 reading** — "four most recent PUBLISHED quarters" or "four most recent
   CALENDAR quarters with None for absent"? Differs for 10.23% of the universe.
   Everything else here is mechanical; this one is a ruling.
2. **D-3 scope** — enforce calendar-indexing for monthly revenue now (currently
   0% affected, so it is a guarantee not a correction), or record and defer?
3. **`momentum_12_1` zero margin** — leave at exactly 14, or widen the supply and
   state the margin? Widening changes no semantics; leaving it is also defensible.
4. **Vocabulary extent** — add only the two §6.1.14 names, or a general
   `RUN_INVALID_*` family?

Nothing is implemented. No file above has been modified.
