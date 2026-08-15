# P0-R3 — Source-Lineage Adjudication, Raw Snapshot, and Full R-FWD Qualification

**Status: APPROVED — Phase A (document) approved; Phase B (read-only) authorized. Phase C, Phase D, Phase E, and all production/cache/Scheduler writes remain unauthorized (§14).**
**Study code:** P0-R3
**Author:** Claude, per user instruction 2026-08-15 (revision round 5 — final consistency pass: AC-R3-7's proxy-disclosure PASS loophole closed; AC-R3-8/AC-R3-27 unified into one FAIL-OR/PASS-AND rule for Gate R3-N; AC-R3-13 now mandates gate FAIL on any incomplete month coverage with an explicit diagnostic-only carve-out and denominator-shrinking ban; §13.7's AC count arithmetic corrected (31 live + 1 tombstone = 32, not 30 + 1 = 31); §13.7.3's validator disclosure replaced with the specific reported `spec_validator.py --strict` 0/100 / 8-false-negative parser-compatibility result)
**Approval event:** Phase A approved by user instruction, 2026-08-15, of the round-5 revision unchanged (approved draft SHA256 recorded in §14). This approval authorizes Phase B (§11 steps 1–3, read-only) only; it does not authorize Phase C, Phase D, Phase E, or any production/cache/Scheduler write (§14, §12).
**User approval:** APPROVED — 2026-08-15 (full scope in §14; external receipt at `docs/prereg_P0_R3_approval_receipt_2026-08-15.json`)
**Implementation authorized:** NO — Phase B is read-only tracing/cataloging/adjudication, not implementation; no code, test, adapter, or snapshot is authorized by this approval (§14)
**Drafting scope, round 5 (historical, unchanged by this approval event):** prereg document only, document-only revision. No Phase B, no Phase C, no snapshot, no code, no tests, no research artifacts, no staging, no commit. This revision edited the existing file in place (`docs/prereg_P0_R3_SourceLineage_RawSnapshot_RfwdQualification_2026-08-15.md`, unchanged filename since round 2); the round-1 file remains deleted (§15 proves only one prereg file exists after round 5). **This subsequent approval event is document-stamping (this header block and §14 only — no other section's normative content changed) plus one external `approval_receipt.json`, committed together with this document and nothing else.**

---

## 0. Relationship to P0-R2 — explicit non-modification

Unchanged from round 1. This document does not modify, reinterpret, reopen, or supersede any P0-R2 artifact, conclusion, gate result, or commit. P0-R2's Phase D Round 2 results (archived at `497a03ee04d676aa44f5948dcfc69d9c8edd3ebf`) are fixed, external, read-only inputs:

- A-leg common-key raw-score parity: **PASS**, `max_abs_diff = 0.0` (255/255 months with common-key data).
- A-leg membership: **NOT_EVALUATED** (`INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS`).
- B-leg parity and final (dual-confirm) membership: **NOT_EVALUATED** (`INSUFFICIENT_FROZEN_PIT_INPUTS`).
- **Gate C-R: FAIL.**

---

## 1. Context and non-claims

Round 1 assumed, on the strength of `phase_b_design_freeze.md` §10's own wording, that the 8 FinMind-based `HistoryBundle` datasets (`price/per/revenue/income/balance/cashflow/chip/shareholding`, consumed by `core/backtest.py::build_pit_stockdata`) were *the* required raw source for reconstructing R-FWD's decision-time universe and B-leg factors. This round's user correction is that this was never established — it was inherited, unverified, from P0-R2's own design document. **P0-R3 now treats the required raw-dataset family itself as an open research question, adjudicated by a new gate (R3-L, §7.1) before any source-sufficiency or snapshot work may proceed.**

**Non-claims (binding on every phase, every gate, every report this study produces) — unchanged from round 1, restated:**

1. Any new frozen historical snapshot MUST be called a **retrospective research reconstruction snapshot**, never **contemporaneous production evidence**.
2. Snapshot success does not mean R-FWD is qualified (Gate R3-F and Gate R3-Q are independent, both-required).
3. Parity success does not mean announcement-date PIT has been verified (`date + N days` remains an unverified proxy unless genuinely evidenced, §8).
4. Nothing here reopens or auto-triggers P0-R1, P0-R2, or Stage 2 of either study.
5. This document authorizes **prereg drafting only**. Phase B may not begin until Status is `APPROVED`.

---

## 2. Frozen identities

### 2.1 Repository baseline

`497a03ee04d676aa44f5948dcfc69d9c8edd3ebf` — `research(P0-R2): archive partial Phase D offline validation`. Parent `0b1af42224314d71e8d16121d356235ffa7aacf7`. This is a **commit identity anchor only**; it does not stand in for any file's real working-tree identity (§4 corrects round 1's error on exactly this point).

### 2.2 Frozen research oracle

`5f3f5d319ab52be3b892dacaab72987764583dcf` — `research(P0-U1): canonical ranking universe alignment — archived, not deployed`. Verified reachable this round (`git cat-file -e`).

Oracle callable (unchanged, restated verbatim):
```
beat_0050.strategies.high52_lab.Panel
dual_confirm_mask(P, "100萬", top_pct=20, source="real", min_cov=1.0, canonical=False)
```

### 2.3 P0-R2 result identity (restated, not reopened)

`research/p0_r2_identity_collector/phase_d_offline_validation_report.md`, `a_leg_parity_result.json` (SHA256 `db4adf10795acf415a43262ba2979fa6587ced96aa83130b480e5e5145850ebb`), `capacity_dry_run_report.json` (SHA256 `24ba11d71dcbff603933f0c8747cbf25c1a81005db875c000d652f7b25c9a884`) — all committed at `497a03ee...`, read-only inputs, not recomputed here.

---

## 3. Source-lineage adjudication — this round's read-only code-reading findings

This section records what was actually read this round (callable chains, by following real `import`/call graphs — no data file content beyond schema/column-name sampling already done in round 1, no new corpus scanning). It is the evidentiary basis for §7.1's Gate R3-L design and is explicitly **not** itself a Gate R3-L PASS verdict — that verdict is Phase B's job, once approved.

### 3.1 Decision-time universe (`listed_ok(as_of) & adv20(as_of) >= 1,000,000`)

- **As actually computed by the oracle:** `beat_0050/strategies/high52_lab.py`'s `Panel.__init__` sets `self.tier_valid = {name: (self.HAS_RET & (self.ADV >= thr)) for name, thr in ADV_TIERS}`, where:
  - `self.ADV = mat("adv20", np.float64)` — sourced from `obs_alpha.parquet`'s own `adv20` column, itself a genuinely trailing DuckDB-window computation (`scripts/build_research_base.py`'s field #18: `AVG(close×Trading_Volume) OVER (... ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)`), and `listed_ok` is field #19 (`first_date = MIN(date) OVER (PARTITION BY stock_id)`, first-listed-date flag) — **both genuinely PIT-safe on their own.**
  - `self.HAS_RET = np.isfinite(self.RET)`, and `self.RET = mat(RET_COL)` (`RET_COL = "fwd_x"`), sourced from `exec_ret.parquet` (a **forward-return** dataset) merged into `obs`. Critically, `Panel.__init__` also runs `obs = obs.dropna(subset=[RET_COL, "adv20"])` before building any matrix — **rows lacking a forward return are dropped from the panel entirely**, before `tier_valid` is even computed.
  - **Finding:** `Panel.tier_valid["100萬"]`, as literally computed, is not a pure function of `listed_ok`/`adv20` — it is additionally conditioned on forward-return availability (`HAS_RET`), which is definitionally unavailable to any real forward-looking (PIT-safe) computation. This is the exact mechanism behind the instruction's item 6.
- **Raw dataset family for the PIT-legitimate half** (`listed_ok`, `adv20`): TEJ (`obs_alpha.parquet`'s Stage 1/2 pipeline, ultimately `~/tej_cache/price_valuation`).
- **Raw dataset family for `HAS_RET`**: `exec_ret.parquet` — already one of the two FR-28-forbidden files; structurally cannot be part of any PIT-safe adapter input.
- **Code hashes:** `beat_0050/strategies/high52_lab.py` `09fbe6efa34e5c6e8481adafddad58d073970227c7804c8a269e6ed29b0f72f8`; `scripts/alpha_gate_lab.py` `be2f3dd8544034af69710a9b3a35e1d92ede8b7ce5fded8bd54c8898b4317e2a`.

### 3.2 A-leg `real_composite`

- **Producing callable chain (traced this round, full path):**
  `beat_0050/realbody/build_realbody_scores.py::main()` → `beat_0050.realbody.bt_bundle.bt_fetch_history(stock_id)` → `core.tej_bundle.tej_fetch_history(symbol)` (with two backtest-local overrides applied by `bt_bundle.py`: `core.tej_bundle._PCT_HISTORY_START` widened `2019→2004`; `bundle.chip` replaced with `institutional_flow`-derived data in place of `tej_fetch_history`'s own default `institutional_gross`) → returns a `core.backtest.HistoryBundle` → `core.score_store.score_row(bundle, as_of, mode, engines, strict=True)` → `core.backtest.build_pit_stockdata(bundle, as_of)` → `FundamentalEngine.evaluate` + `ValuationEngine.evaluate` + `ScoringManager.calculate_score` + `InvestmentAdvisor.advise` → `.total_score`, written to `realbody_scores_adv100w.parquet`'s `real_composite` column → merged into `Panel._real_comp` via `scripts/lab_paths.py::resolve_realbody(1e6)`.
- **Raw dataset family: TEJ cache, NOT FinMind.** `core/tej_bundle.py`'s own docstring documents the exact mapping (verified this round, not re-derived): `bundle.price/per ← ~/tej_cache/price_valuation`; `bundle.revenue ← ~/tej_cache/monthly_revenue` (via `core.backtest._pit_revenue`); `bundle.income/balance/cashflow ← ~/tej_cache/financial_statements` (wide→long reshape); `bundle.chip ← ~/tej_cache/institutional_gross` by `tej_bundle.py`'s own default, **overridden to `institutional_flow` by `bt_bundle.py`** for this specific research path; `bundle.shareholding ← ~/tej_cache/tdcc_weekly ∪ institutional_gross`.
- `core/backtest.py`'s own FinMind-based `fetch_history`/`cached_fetch_history` functions (which read `~/finmind_cache/*`, HistoryBundle's namesake mapping) exist and are real, but this round's tracing found them invoked only by the **live production app/L4a scoring path** — a separate consumer of the same `build_pit_stockdata`, not part of this chain.
- **Cutoff/publication semantics (per-field, traced this round):**
  - `price/per/chip/shareholding`: `_slice(df, as_of)`, plain `date <= as_of`, no lag (same-day-observable data).
  - `revenue`: `core.backtest._pit_revenue` — **genuinely PIT-aligned where possible.** Its own docstring (read this round): FinMind's revenue `date` is the announcement-month's 1st (an under-estimate of true announcement date, up to 9 days optimistic); TEJ's `monthly_revenue` dataset carries a genuine per-row `release_date` from 2019-01 onward (collector-observed first-seen date, "≈announcement date" — an approximation of the true legal disclosure date, not itself certified); rows without a known `release_date` fall back to the statutory deadline (next month's 10th) as a conservative estimate; months before TEJ's 2019-01 start fall back to the FinMind-style 1st-of-month approximation. **This is a real, meaningfully-better-than-naive PIT mechanism, but still not a fully-verified announcement date for the full 2005–2026 span.**
  - `income/balance/cashflow`: `_published(df)`, `date + PUBLISH_LAG_DAYS(45) <= as_of` — a **fixed-offset proxy**, not a real field (same mechanism used by the FinMind path).
- **Code hashes:** `beat_0050/realbody/build_realbody_scores.py` `1b9ff09dbad344a400fa4eb8456c8ef5b2ffdd16fe6a8d10637f85c02327249f`; `beat_0050/realbody/bt_bundle.py` `fa9beb0f91f3896293c000262e7b85e12a49e78059575b4ff551f121faa5535f`; `core/tej_bundle.py` `adf98b4a8731eff832722ad74a0e361cbb2e6f7cf4558ee477d9640df646b9a0`; `core/backtest.py` `3b0f8e9ebe97ffd1e184a4fec0a4cbdc1b8af15d47fa3974a167fac9802d3fb2`; `core/score_store.py` `58de00f76481ea1ce13fd6fa2f946ac0b2f3dae641e1d80f9b56319345bc7874`.

### 3.3 B-legs: `value_ind`, `revenue_yoy`, `high52_prox`, `momentum`

- **Producing callable chain:** `scripts/tej_universe_screen_validation.py::build_observations()` (Stage 1 — reads `~/tej_cache/{price_valuation, institutional_flow, fundamentals_quarterly, revenue_growth}`, writes `obs_dump_full.parquet`) → `scripts/alpha_gate_lab.py::build()` (Stage 2 — reads `obs_dump_full.parquet` + `~/tej_cache/{price_valuation, industry_map, institutional_flow, tdcc_weekly, director_pledge}`, writes `obs_alpha.parquet`, 20 supplemental columns) → `obs_alpha.parquet`'s named columns → read directly by `Panel.__init__`'s `self.F = {f: mat(f) for f in FACTORS if f in obs.columns}`.
- **This chain never touches `core.backtest.build_pit_stockdata` or any `HistoryBundle` at all** — it is a wholly separate, bespoke feature-engineering codebase from §3.2's A-leg chain.
- **Per-field formula and PIT semantics (from `scripts/build_research_base.py`'s own field dictionary, read this round):**
  - `momentum` (Stage 1, from `price_valuation`): `(close[i0]/close[i0−20] − 1) × 100`. Same-day/trailing, no lag needed.
  - `high52_prox` (Stage 1, from `price_valuation`): `close[i0] / rolling(240, min_periods=120).max() × 100`. Trailing window, right-anchored at `i0`, author-audited "無前瞻" (no lookahead).
  - `revenue_yoy` (Stage 1, from `revenue_growth`): TEJ's `revenue_growth` dataset's own `revenue_yoy_pct`. PIT: `known_date = month-end + 10 days`, `merge_asof(direction="backward")` — **a fixed-offset proxy**, since this round's schema sampling of `revenue_growth` (round 1, §2.5) found **no genuine disclosure-date column** in that dataset (contrast with §3.2's A-leg revenue, which does have TEJ `monthly_revenue`'s real per-row `release_date` — **B-leg `revenue_yoy` and A-leg `real_composite`'s revenue input come from two different TEJ datasets with two different PIT-safety levels**, a fact this round's tracing surfaced and round 1 did not know).
  - `value_ind` (Stage 2, cross-industry percentile of Stage 1's `value`): same-day cross-sectional percentile of `value` within `(as_of × tej_ind_name)`, falling back to full-market percentile when the industry sample is `< 5` stocks. Same-day, non-cross-period, author-audited "無前瞻". Depends on `tej_ind_name` (from `industry_map.parquet`), which the pipeline's own author flags as a **current-snapshot industry classification applied retroactively across all history** — a real, author-acknowledged, non-classic look-ahead risk (industry-reclassified stocks get today's industry label for their entire history).
- **Separately documented, author-acknowledged real PIT flaw (found this round, in `scripts/build_research_base.py`'s own "未來函數稽核結論 (2026-07-29)" section):** the shared 45-day quarterly-lag constant is legally correct for Q1–Q3 but **wrong for Q4** (Taiwan's statutory annual-report deadline is the following 3/31, not quarter-end+45 days ≈ 2/14) — affecting `eps/roe/op_income/net_income/eps_pos_q4`. The author's own note confirms this does **not** affect `value_ind/revenue_yoy/high52_prox/momentum/adv20` directly, but it is a live, real, code-documented defect in the same pipeline family and must be carried into Gate R3-P's evidence, not omitted because it happens to spare this study's 4 named B-legs.
  - **Numeric detail — inherited source-code annotation, NOT independently verified by R3 (round 3 correction).** The figures "8 named `as_of` dates (2020-02-27, 2021-02-26, 2022-02-25, 2023-02-24, 2024-02-29, 2024-03-29, 2025-02-27, 2026-02-26), 11,053 rows, 3.67% of the panel" are copied verbatim from `scripts/build_research_base.py:126-131` — a comment the pipeline's own author wrote, dated 2026-07-29, described there as "影響幅度 (實測)" (measured impact). **This study has not re-run that measurement or independently recomputed the row count or percentage.** They are recorded here as a precisely-cited inherited annotation, not as an R3-verified fact; Gate R3-P (Phase B) must independently confirm or correct them before they may be used in any qualification decision.
- **Other author-acknowledged risks (read this round, not previously known to this study) — same inherited-annotation caveat applies:** (a) `eps/roe/op_income/net_income/eps_pos_q4` "~61%" missing before 2019 (figure from `scripts/build_research_base.py:139-140`, not independently verified by R3) because `tej_cache/fundamentals_quarterly` only starts 2019 (`tej_cache/financial_statements` has pre-2019 data but this chain does not read it, per `scripts/build_research_base.py:140-141`); (b) the population is implicitly restricted to tickers still present in the live `tej_cache` — a real, author-acknowledged **survivorship-bias risk** for any delisted stock no longer cached (`scripts/build_research_base.py:142`).
- **Code hashes:** `scripts/tej_universe_screen_validation.py` `9405b18ce27376381370268ccf85c06bd65c29be894b171bb87093de34d921da`; `scripts/alpha_gate_lab.py` `be2f3dd8544034af69710a9b3a35e1d92ede8b7ce5fded8bd54c8898b4317e2a`.

### 3.4 Preliminary reading (not a Gate R3-L verdict)

Based solely on the above, this round's tracing suggests the FinMind `HistoryBundle` 8-dataset family (`~/finmind_cache/*`) is **not** the raw source for any of the 6 target fields — all 6 trace back to `~/tej_cache/*` through two distinct, unrelated code paths (§3.2's `build_pit_stockdata`-via-`tej_bundle` chain for the A-leg, §3.3's bespoke `tej_universe_screen_validation.py`/`alpha_gate_lab.py` chain for the 4 B-legs). If this reading survives Phase B's formal verification, the candidate **D\*** (Required Dataset Set) would be a **union**, per the instruction's own anticipated case: `{price_valuation, monthly_revenue, financial_statements, institutional_flow, institutional_gross, tdcc_weekly, revenue_growth, industry_map}` (all TEJ), not `HistoryBundle`'s FinMind 8. **This is a preliminary reading only — Gate R3-L (§7.1) is the formal, Phase-B-only adjudication step; nothing in this document scores it PASS.**

---

## 4. Windows-Git dependency-path evidence (corrects round 1's error)

Round 1 stated the 5 oracle/adapter-relevant code files were "modified" relative to HEAD, based on a WSL `git status` check. Per this round's instruction, that check has been redone with **native Windows Git** (`git version 2.54.0.windows.1`), scoped to the exact dependency paths, at HEAD `497a03ee04d676aa44f5948dcfc69d9c8edd3ebf`:

```
git status --short -- core/backtest.py core/data_cache.py core/score_store.py core/tej_bundle.py \
  core/canonical_universe.py scripts/lab_paths.py scripts/build_research_base.py \
  scripts/tej_universe_screen_validation.py scripts/alpha_gate_lab.py \
  beat_0050/strategies/high52_lab.py beat_0050/strategies/dual100_lab.py \
  beat_0050/realbody/bt_bundle.py beat_0050/realbody/build_realbody_scores.py
```
**Output: empty.** All 13 paths are clean (byte-identical to HEAD) under Windows Git. Round 1's "全部 modified" claim is **retracted** — it was an artifact of a WSL git installation whose line-ending normalization disagrees with the native Windows checkout on these files, not a real content difference. **WSL Git's CRLF-driven status is not used as git-state evidence anywhere in this document.**

Because all 13 files are Windows-Git-clean, their **git-committed blob at `497a03ee...`** is already a valid durable identity for each — no separate byte-copy preservation is needed for *these specific files* under §5's rule. §5's rule remains necessary for whatever files Phase B's fuller inventory finds to be genuinely modified/untracked once it runs the same Windows-Git-scoped check over a larger path set.

---

## 5. Durable identity rule (corrects round 1's error)

Round 1 proposed `git hash-object -w` loose blobs as sufficient preservation for modified/untracked dependencies. Per this round's instruction, that is **not** sufficient on its own — a loose object unreferenced by any branch/commit/tag is eligible for `git gc` pruning (the same risk P0-R1's own `data_snapshot_manifest.json` already documents). The corrected rule, binding for Phase B onward:

> A dependency file's identity is durably frozen if, and only if, **either** (a) it is a reachable committed blob (verified via `git rev-parse <commit>:<path>` matching a blob that `git merge-base --is-ancestor` or equivalent confirms is reachable from a live ref), **or** (b) an independent durable byte copy exists outside `.git/objects` together with its SHA256, byte count, and a documented, reproducible verify command. A `git hash-object -w` loose blob **MAY** be recorded as auxiliary, supporting evidence, but **MUST NOT**, by itself, satisfy the freeze requirement for any file that is not otherwise reachable-committed or byte-copied.

---

## 6. Source-sufficiency gate (Gate R3-S) — redesigned around D\*, not fixed to FinMind

Gate R3-S no longer presupposes the 8 FinMind `HistoryBundle` datasets as the required set. It evaluates **D\***, the dataset set Gate R3-L (§7.1) freezes. Round 1's finding — that the local `~/finmind_cache/*` datasets cover only ~76–78 tickers, date ranges starting 2019-01 — is retained **only** as evidence that FinMind is (at minimum) an insufficient *candidate* source family for a 255-month/full-market reconstruction; it is explicitly **not** treated as proof that FinMind is *the* required family that turned out to be insufficient, since §3.4's preliminary reading suggests FinMind was never the required family to begin with. Both readings are compatible: FinMind may be irrelevant (per §3.4) **and** insufficient in coverage (per round 1) simultaneously — the document does not need to pick one framing over the other; Phase B does the actual test.

For every dataset in the eventually-frozen D\*, Phase B must record (unchanged content from round 1, restated): exact path, source/provider, full-corpus schema, ticker/date/publication-date semantics, first/last structural date (full corpus, not a 1-file sample), revision policy, duplicate-key policy, missingness rules, PIT cutoff, SHA256, and an explicit per-dataset eligibility verdict. **Any required dataset missing, undocumented, or unhashable fails Gate R3-S outright.**

**Round 3 clarification of the change rule's scope.** Gate R3-L's own act of adjudicating between the FinMind and TEJ *candidate* families (§7.1) — including whichever composition it lands on — is the **first** D\* determination for this study, not a "change." §3.4's preliminary reading (TEJ-only union) is a pre-Phase-B hypothesis, not a prior frozen D\*; Phase B formally testing and confirming or revising that hypothesis, and Gate R3-L then freezing whatever D\* results, does not itself trigger the diff/reapproval process below — there is nothing to diff against yet.

**Only a change to D\* *after* that first freeze** (e.g. Phase B or a later phase discovers an additional required dataset, or Gate R3-L's frozen D\* must be revised once new evidence surfaces) **must**: (a) be written into the Phase B design-freeze document, (b) disclose the complete diff against the previously-frozen D\*, (c) receive a fresh, explicit user approval, and (d) be recorded under a new `DStarManifest` identity (§13.3) distinct from the first-frozen one — **before** Phase C snapshot work may begin on the changed set.

---

## 7. Gates

### 7.0 Phase C admission rule (new this round)

Phase C (snapshot creation) may begin **only if all three** of the following hold:

1. **Gate R3-L PASSes** and D\* is frozen (§7.1).
2. **Gate R3-S PASSes** for the frozen D\* (§7.2/§6).
3. **Gate R3-P PASSes** — i.e. every dataset in D\* has a genuine, evidenced PIT-cutoff basis, not merely an unverified fixed-offset proxy (§7.4) — for at least the fields this study needs to reconstruct.

D\* and the Phase B design-freeze document (recording R3-L's evidence, R3-S's per-dataset sufficiency record, and R3-P's per-dataset PIT evidence) must be **disclosed to the user in full** before Phase C is requested, and Phase C requires its **own, separate, explicit approval** — Phase A's approval of this document does not extend to it (already stated in §11, restated here as the binding admission test).

**If Gate R3-S or Gate R3-P FAILs:** Phase C does not proceed. The study stops at Phase B and files a **null/blocked result** — a report stating which gate failed, for which dataset(s)/field(s), and why, with no snapshot, no qualification claim, and no further phase attempted. The **sole exception**: the user may explicitly approve, as a distinct and separately-labeled decision, a **"diagnostic-only snapshot"** — a snapshot built despite an R3-S or R3-P FAIL, expressly for further root-cause investigation. A diagnostic-only snapshot **MUST**: (a) be labeled `DIAGNOSTIC_ONLY — NOT QUALIFICATION-ELIGIBLE` in its manifest and every report that references it; (b) never be used as an input to Gate R3-U/R3-B/R3-Q/R3-I/R3-N or any qualification verdict; (c) require the same fresh, explicit, separately-recorded user approval as any other Phase C authorization — it is never a default fallback the study may take on its own initiative.

### 7.1 Gate R3-L — Source-lineage adjudication (new; must run before every other gate)

**Purpose:** prove, via static callable/data-lineage tracing (not data execution, not parity computation), the true producing chain for each of the 6 target fields:

```
decision-time universe · A-leg real_composite · value_ind · revenue_yoy · high52_prox · momentum
```

**Required record per field** (§3 above is this round's read-only contribution toward that record, not the record itself — Phase B must formally verify, extend, and sign off on it):
- producing callable chain (module path → function/class → module path → ... , traced to the actual raw-file read)
- raw dataset family (name each dataset actually read, not a family inferred by name-similarity to `HistoryBundle`)
- exact source paths (absolute, with any environment-variable resolution documented)
- transformation formulas (verbatim from source, not paraphrased into a different equivalent form)
- cutoff/publication semantics (genuine field vs. fixed-offset proxy, explicitly labeled either way)
- code hashes (every file in the chain)
- git state (Windows-Git-scoped, per §4's corrected method — never WSL-git-derived)

**Freeze rule:** Gate R3-L PASSes, and **D\*** (Required Dataset Set) is frozen, only once every one of the 6 fields has a complete, evidenced record with **no unresolved ambiguity** in which raw file(s) actually produced it. If different fields require different raw-dataset families, **D\* is their proven union** — never a choice of one family that happens to be more convenient.

**FinMind's 8 `HistoryBundle` datasets and TEJ's `tej_cache` datasets are both, at this stage, candidate source families only.** Neither may be called "required" until Gate R3-L resolves the actual lineage for each field.

**If lineage cannot be uniquely resolved for any of the 6 fields** (e.g. a producing chain forks based on a runtime flag whose value at any historical `as_of` cannot be reconstructed, or two candidate producers cannot be disambiguated), **Gate R3-L FAILs**, and Gates R3-S/F/P/U/B/Q/I/N are all **NOT_EVALUATED** for this study — there is no partial-lineage path forward.

### 7.2 Gate R3-S — Source sufficiency

Redesigned in §6. Evaluates D\* only after Gate R3-L PASSes.

### 7.3 Gate R3-F — Snapshot integrity

Unchanged from round 1 (§9 below, manifest-first / real byte copy / no hard-links / post-copy re-hash / no source mutation / no reverse-reconstruction).

### 7.4 Gate R3-P — PIT/announcement-date validity

Unchanged binding rule from round 1, restated: `date + N days` (whatever N is, for whichever dataset) may be recorded only as an **unverified proxy** unless a genuine, evidenced disclosure-date field backs it. §3's findings materially update the *evidence* feeding this gate (e.g. TEJ `monthly_revenue`'s real `release_date` for A-leg revenue post-2019, versus `revenue_growth`'s lack of one for B-leg `revenue_yoy`; the documented Q4 45-day-lag flaw) but not the rule itself. If no reliable evidence exists for a dataset, **Gate R3-P FAILs for that dataset**, and `COMPARABLE_IDENTITY`/full qualification remain **BLOCKED** for anything depending on it.

### 7.5 Gate R3-U — Decision-time universe exact parity (strengthened this round)

Binding rule, restated verbatim from the instruction:

> `Panel.tier_valid["100萬"] = HAS_RET & ADV>=1,000,000`. `HAS_RET` depends on forward return and may exist **only** on the oracle side. The adapter side **MUST NOT** read, derive, or proxy `HAS_RET`, or any other future-return-availability signal, under any name or transformation. The adapter may use **only** decision-time PIT-eligible inputs. The adapter's population **MUST NOT** be narrowed to the oracle's (or to any common-population intersection) merely to manufacture an exact match — see §7.7's binding prohibition, which this gate especially depends on.

**New Gate R3-U/R3-N acceptance criterion (added this round):** if exact membership match between adapter and oracle populations is achievable **only** by the adapter reading, deriving, or being fed `HAS_RET` or an equivalent future-return-availability mask, **both Gate R3-N and Gate R3-U FAIL** — this is treated as a future-input-access violation (R3-N) *and* a universe-parity failure (R3-U) simultaneously, not a success under either. When a genuinely PIT-only-constructed universe fails to match the oracle's population, the study **must honestly record that as a FAIL** — the decision-time universe's own definition (§8) may **not** be edited, loosened, or reinterpreted merely to close the gap.

### 7.6 Gates R3-B, R3-Q, R3-I, R3-N

Unchanged in substance from round 1: `R3-B` — four B-leg raw-score parities, tolerance `<=1e-12`, each with its own float32/float64-representation regression test (mirroring P0-R2's A-leg fix, per AC-R3-11); `R3-Q` — 255-month **full-population** final membership exact match plus common raw-score tolerance across all legs; `R3-I` — real process isolation / import-manifest evidence (not the `LIMITED_*_ONLY` downgrade P0-R2 Phase D Round 2 used as its honest floor); `R3-N` — genuine future-input-access evidence artifact.

**Timing (round 3 correction, see §11 for the full phase mapping):** these four gates are scored together, single-shot, in **Phase E** — this is the only genuinely "first-scored-together" moment in the study. `R3-L`, `R3-S`, and `R3-P` are **not** first scored in Phase E; they are scored earlier (`R3-L`/`R3-S`/`R3-P` in Phase B, `R3-F` in Phase C) and are only **re-disclosed and re-verified** (not re-adjudicated from scratch) alongside `R3-U/B/Q/I/N` at Phase E's single-shot reveal, so the final report presents all 9 gates' status together even though 4 of them were actually resolved in earlier phases.

### 7.7 Binding prohibitions (restated, both apply to every gate above, not only R3-U)

1. No gate may be satisfied by restricting a comparison to a common-population intersection and reporting the intersection's agreement rate as the full-population result (P0-R2 Phase D Round 1's retracted mistake is binding precedent, not merely a historical note).
2. Any required gate that FAILs blocks R-FWD `QUALIFIED` status outright — no aggregate/weighted scoring, no gate skipped by citing another gate's PASS.

---

## 8. Exact reconstruction semantics (round 3 correction: §3 is provisional, not a frozen reuse basis)

**Round 3 correction.** Round 2 stated the B-leg formulas were "§3.3's traced formulas, reused verbatim." That overstated §3's status: §3 is this round's **read-only, un-verified-by-execution** code tracing — a **provisional lineage description**, not a Phase-B-verified, frozen specification. Nothing in §3 has been checked against the actual data, re-derived independently, or signed off as a gate result. Calling it "reused verbatim" implied a level of freeze §3 does not yet have.

- **Decision-time universe:** `listed_ok(as_of) AND adv20(as_of) >= 1,000,000` — and, per §7.5, explicitly **not** `Panel.tier_valid`'s literal `HAS_RET`-gated computation; the adapter reconstructs the pure PIT definition independently. §3.1's mechanism description is likewise provisional pending Phase B's formal freeze below.
- **B-legs:** `value_ind`, `revenue_yoy`, `high52_prox`, `momentum` — §3.3's traced formulas are a **provisional lineage description** of what this round's code-reading found, not yet a frozen specification this study may implement against.
- **A-leg representation:** MUST include the frozen `Panel`'s `np.float32` storage semantics (P0-R2's established fix, restated as binding here too).
- **Ranking/NaN/ties/percentile/complete-case/fusion:** reused verbatim from `core/canonical_universe.py`'s `rank_pct_desc`/`topk_mask_desc`/`build_canonical_valid_mask` — this specific reuse claim is **not** provisional, since these three functions are read directly, in full, with no interpretation step in between (unlike §3's multi-hop callable-chain tracing).
- **Oracle (single source of truth, restated, not to drift across this document):**
  ```
  Panel + dual_confirm_mask(P, "100萬", top_pct=20, source="real", min_cov=1.0, canonical=False)
  ```

**Phase B freeze requirement (new this round, binding — see §11 Phase B step 3).** Before Phase C may begin, Phase B must formally freeze, for the A-leg and each of the 4 B-legs, a complete record covering:

1. exact callable chain (module → function/class → module → ..., to the raw-file read)
2. code SHA256 for every file in the chain
3. exact input fields consumed (column names, source dataset, dtype)
4. every constant used (e.g. lag days, window length, threshold), with its source-code location
5. window/lookback specification (length, alignment, `min_periods`, direction)
6. merge/join key and `merge_asof` direction where applicable
7. industry (or other cross-sectional grouping) fallback rule, exactly as coded
8. NaN/tie/ranking semantics (how missing values, ties, and rank ordering are actually handled)
9. the formula itself, written step-by-step from the actual source, not paraphrased into an equivalent-looking closed form

**Only once this record is complete for all 5 legs does §3's provisional lineage description convert into a frozen specification this study may build a snapshot or adapter against. An incomplete record for any one leg blocks Phase C for the entire study, not only for that leg — there is no partial-leg snapshot or partial-leg admission path (AC-R3-24, §10.6).**

---

## 9. Snapshot protocol (Phase C only, not authorized by this document)

Unchanged from round 1: manifest-first; real byte copies, no hard-links; read-only after copy; per-file SHA256/bytes/row-count/schema-fingerprint; canonical aggregate hash; large files `.gitignore`'d, small manifest version-controlled; post-copy re-hash with zero-mismatch-tolerance; no source mutation; no reverse-reconstruction from current/derived outputs.

**Coherent-copy assertion (new this round, binding for every file copied in Phase C).** For each source file, the snapshot process must record and check:

```
source_pre_sha256  == copied_sha256  == source_post_sha256
```

where `source_pre_sha256` is the SHA256 of the source file computed **immediately before** the copy begins, `copied_sha256` is the SHA256 of the destination copy computed **immediately after** the copy completes, and `source_post_sha256` is the SHA256 of the **source** file (re-read, not cached) computed **immediately after** the copy completes. All three must be identical.

**If any source file's hash changes between the pre- and post-copy read** (i.e. `source_pre_sha256 != source_post_sha256`) — whatever the cause, including a concurrent collector process, a scheduled cache refresh, or manual edits — **Gate R3-F FAILs for the entire snapshot batch**, not merely for the affected file. A snapshot built from a source corpus that mutated mid-copy cannot be trusted for any file in that batch (a partial, silently-inconsistent snapshot is worse than an explicit failure), so the whole batch must be discarded and re-copied from a stable source state before Gate R3-F may be re-attempted.

---

## 10. Acceptance criteria

Given/When/Then, every criterion below written **self-sufficiently in this document** — none depends on, or is a stand-in reference to, the deleted round-1 file (`docs/prereg_P0_R3_RawHistoryBundleSnapshot_RfwdQualification_2026-08-15.md`). Round 1 originally introduced AC-R3-1 through AC-R3-18 (by number and one-line topic only); round 2 added AC-R3-19 through AC-R3-21 for Gate R3-L and rewrote AC-R3-2 in full; round 3 added AC-R3-22 through AC-R3-25 (coherent-copy violation, Phase C admission blocking, leg-formula freeze completeness, D\* first-adjudication scope); round 4 rewrote AC-R3-1, AC-R3-3, AC-R3-6 through AC-R3-18 in full Given/When/Then form (they previously read only "unchanged"/"restated from round 1," a reference this document can no longer resolve since that file is deleted) and added AC-R3-26 through AC-R3-31 (Gate R3-I/R3-N minimum evidence semantics; inherited-numeric-annotation citation; D\* coverage no-waiver; durable-identity gap; single-shot violation); **round 5 (this revision) closes AC-R3-7's proxy-disclosure PASS loophole, unifies AC-R3-8 with AC-R3-27 into one FAIL-OR/PASS-AND rule, strengthens AC-R3-13 to mandate an explicit gate FAIL on incomplete month coverage, and corrects the §13.7 AC-count arithmetic**. §13.4 maps every FR-R3-*/NFR-R3-* to the AC-R3-* that verifies it, in both directions, with an explicit orphan check (§13.7, corrected this round).

### 10.1 Source-lineage adjudication (feeds Gate R3-L — new this round)

- **AC-R3-19 (lineage ambiguity).** *Given* a target field's producing chain cannot be traced to a single, unambiguous raw-dataset family (e.g. two candidate code paths both plausibly produce it and cannot be disambiguated from static tracing alone). *When* Gate R3-L is scored. *Then* Gate R3-L FAILs, and Gates R3-S through R3-N are all reported `NOT_EVALUATED` — never resolved by picking the more convenient candidate.
- **AC-R3-20 (union requirement).** *Given* different B-legs (or the A-leg vs. any B-leg) are found to require different raw-dataset families (as §3.4's preliminary reading already suggests). *When* D\* is frozen. *Then* D\* MUST be the proven union of every field's evidenced family — never a subset chosen because it is smaller, cheaper to snapshot, or was assumed correct by a prior study.
- **AC-R3-21 (lineage claim without evidence).** *Given* any report from this study asserts a field's raw source without citing the specific traced callable chain, file path, and code hash recorded under Gate R3-L. *Then* that assertion is invalid and must be struck or backed with the missing evidence before the report may be finalized.

### 10.2 Source and schema integrity (feeds Gate R3-S)

- **AC-R3-1 (source missing — round 4: rewritten in full, self-sufficient).** *Given* a dataset named in the frozen D\* (§6) is not found at its documented source path when Phase B's inventory scan runs (the path is missing, unreadable, or resolves to zero files). *When* Gate R3-S is scored. *Then* Gate R3-S FAILs for that dataset, named explicitly by dataset name and the exact expected path that was checked; the failure blocks Phase C admission (§7.0) for any content that depends on that dataset, and the study may not substitute a different, undeclared path to work around the failure without going through §6's D\*-change disclosure/reapproval process.
- **AC-R3-2 (schema drift — tightened this round).** *Given* two per-stock files within the same dataset have different column sets or dtypes than what this prereg or the Phase B design-freeze document pre-declared. *When* Phase B's schema scan runs. *Then* Gate R3-S FAILs, **or** the study stops and a formal errata document is filed and separately user-approved before resuming — **there is no self-judged "benign drift" exception any longer.** Round 1's language permitting a drift to be waved through as "proven benign" (e.g. a delisted stock's earlier schema) is retracted; any drift not pre-declared in an approved document is treated as unresolved until a human explicitly rules on it.
- **AC-R3-3 (duplicate ticker/date — round 4: rewritten in full, self-sufficient).** *Given* a dataset in D\* contains more than one row for the same natural key (ticker+date for price-like datasets, or the dataset's own documented natural key otherwise) without a pre-declared, deterministic tie-break rule. *When* Phase B's schema/integrity scan runs. *Then* Gate R3-S FAILs for that dataset until either (a) the duplication is shown to be a legitimate multi-row structure (e.g. distinct `report_type`/restatement-sequence columns that together restore key uniqueness) and that structure is written into the Phase B design-freeze document, or (b) an explicit, deterministic tie-break rule is defined and disclosed in that document. A silent, undocumented `drop_duplicates()`-style default resolution does **not** satisfy either branch and leaves Gate R3-S FAILed.
- **AC-R3-4 → superseded by AC-R3-19/20 (tombstone — retained for numbering continuity only, not itself a live requirement).** Round 1's "obs_alpha/HistoryBundle mapping mismatch" criterion no longer applies as written, because that criterion presupposed FinMind's `HistoryBundle` as the fixed required mapping — an assumption round 2/3 retracted (§1, §6). Its subject matter (verifying which raw family actually produces each field) is now covered, and superseded in full, by **AC-R3-19** (lineage ambiguity) and **AC-R3-20** (union requirement) under Gate R3-L. No report from this study may cite "AC-R3-4" as a satisfied or failed criterion; cite AC-R3-19/20 instead.
- **AC-R3-5 (coverage insufficiency).** *Given* D\* (once frozen) includes a dataset whose local coverage cannot support the full 255-month/full-market reconstruction target (§4's canonical dates list). *When* Gate R3-S is scored. *Then* Gate R3-S FAILs for that dataset, named explicitly (not merged into a vague "insufficient" summary), and — per the round-4 correction to NFR-R3-2 (§13.2) — **no general waiver of this rule exists**; Phase C (qualification-track) is blocked until the dataset is either genuinely sufficient or replaced via §6's disclosed D\*-change process.

### 10.3 Revision, missingness, and PIT semantics — round 4: rewritten in full, self-sufficient

Originally introduced (by number and topic only) in round 1; the text below is this document's own, complete normative content — it does not depend on the deleted round-1 file.

- **AC-R3-6 (revision data — feeds Gate R3-P).** *Given* a dataset in D\* is found to carry revised/restated values for the same historical `(ticker, date)` row across two different vintages/snapshots (e.g. a later-corrected financial statement). *When* Gate R3-P and the snapshot-reconstruction logic are scored. *Then* every historical `as_of` reconstruction MUST use only the value that was knowable **as of that `as_of`** (the earliest/first-vintage value the field carried), never a later-revised value — using a later revision for an earlier decision date is treated as a genuine future-input violation, and Gate R3-P FAILs for that dataset unless first-vintage values are demonstrably available and actually used.
- **AC-R3-7 (missing publication date — feeds Gate R3-P — round 5: PASS-track loophole closed).** *Given* a dataset in D\* has no genuine per-row publication/availability evidence — no genuine disclosure-date field, only a period-end date. *When* Gate R3-P is scored for that dataset. *Then*:
  1. The dataset's cutoff MUST be recorded as `cutoff_semantics.kind = "fixed_offset_proxy"` (§13.3), never as `"genuine_field"`, regardless of how thoroughly that proxy is documented — the absence of genuine evidence is not curable by disclosure quality.
  2. **Gate R3-P FAILs for that dataset in the qualification track, unconditionally, even when the `fixed_offset_proxy` classification is fully and explicitly disclosed.** Full disclosure of a proxy is a precondition for *any* further use of the dataset (it is what separates an honest proxy from an undisclosed one, per item 3 below) — it is never itself sufficient to make Gate R3-P PASS. There is no "well-documented proxy" exception that converts a FAIL into a PASS; §1 non-claim 3 and §7.4's binding rule already establish that `date + N days` is an unverified proxy, and this AC makes explicit that qualification-track Gate R3-P treats "unverified" as a FAIL condition, not a caveat on a PASS.
  3. If the proxy status is **not** explicitly disclosed in the Phase B design-freeze document at all, that is a strictly worse, separate failure mode (an undisclosed proxy is treated as no evidence whatsoever) — but disclosure never upgrades the outcome past FAIL in the qualification track; it only distinguishes an honest FAIL from a concealed one.
  4. **The dataset's proxy-based reconstruction may be used only within an explicitly, separately user-approved `DIAGNOSTIC_ONLY — NOT QUALIFICATION-ELIGIBLE` snapshot (§7.0)** — for root-cause investigation, never for a qualification verdict. Using a proxy-classified dataset's output as if it satisfied Gate R3-P for qualification purposes, under any label, is prohibited.
- **AC-R3-8 (forbidden future input — feeds Gate R3-N — round 5: unified with AC-R3-27 into one FAIL/PASS rule, not two independent criteria).** *Given* either (a) a **static** scan of the Phase D adapter's source (AST/import-graph, per the method P0-R2 Phase D established) finds a reference to `exec_ret.parquet`, `obs_alpha.parquet`, or any file/column definitionally knowable only after the `as_of` being scored, **or** (b) a **real, executed** access-trace of the adapter process (AC-R3-27) shows the process actually opened such a file/column at runtime. *When* the future-input-access check runs. *Then* **either (a) or (b) alone is sufficient to FAIL Gate R3-N** immediately and unconditionally — this is a hard-fail with no tolerance or threshold, unlike the numeric parity gates, and the two detection methods are **OR-combined for FAIL**, not independently scored.
  **The converse does not hold: a clean static scan finding no forbidden reference is NOT sufficient, by itself, to PASS Gate R3-N.** A static scan only proves what the adapter's source *could* do, never what it *actually did* at runtime (e.g. a dynamically-constructed path, an indirect read through a helper the scan didn't recognize, or a forbidden read the scan's forbidden-target list didn't yet name would all evade a static-only check while still being real violations). **Gate R3-N may PASS only when AC-R3-27's full minimum-evidence requirement is independently satisfied** — a real executed access-trace, with durable hash identity, never labeled `LIMITED_STATIC_CHECK_ONLY` or any other placeholder as a final result, checked against the complete forbidden-target list with an empty reached set. A static-scan-only result, however clean, is recorded at most as `LIMITED_STATIC_CHECK_ONLY` (P0-R2 Phase D Round 2's honest floor for a non-qualifying partial result) and leaves Gate R3-N `NOT_EVALUATED`-for-PASS-purposes — it can still trigger a FAIL per this AC's first paragraph, but it can never trigger a PASS.
- **AC-R3-9 (process import contamination — feeds Gate R3-I).** *Given* the adapter process and the oracle/reference-computation process (§7.1's producing-chain distinction) are found to share a live Python interpreter instance, or the adapter's own import graph reaches `beat_0050.strategies.high52_lab` (the oracle module) at any point, directly or transitively. *When* the process-isolation check runs. *Then* Gate R3-I FAILs — the adapter must execute to completion with zero import edges, direct or transitive, into the oracle's own module, and as two genuinely distinct OS processes (not merely two Python objects in one process).

### 10.4 Reconstruction correctness (feeds Gate R3-U / R3-B / R3-Q) — round 4: AC-R3-10, 11, 12, 13, 14, 15, 16 rewritten in full, self-sufficient

- **AC-R3-10 (population mismatch).** *Given* the adapter's reconstructed decision-time-universe population for a given `as_of` differs from the oracle's `Panel.tier_valid["100萬"]` population for that same `as_of` (§7.5). *When* Gate R3-U is scored for that date. *Then* the mismatch is reported in full (oracle-only count, adapter-only count, common count — mirroring `population_diagnostics`'s existing field shape from P0-R2 Phase D) and Gate R3-U FAILs for that date; the comparison is never narrowed to the common-population intersection to report a smaller, more favorable mismatch figure (§7.7 item 1's binding prohibition, strengthened this round by §7.5's `HAS_RET` rule).
- **AC-R3-10a (future-return mask as the only path to a match).** *Given* an exact adapter/oracle membership match is achievable only by the adapter using `HAS_RET` or an equivalent forward-return-availability signal. *When* Gate R3-U/R3-N are scored. *Then* **both FAIL** (§7.5). The study reports the true PIT-only mismatch rate honestly rather than the artificially-matched rate.
- **AC-R3-11 (float32/float64 drift).** *Given* a raw score computed by the adapter and the corresponding oracle score, both derived from the same underlying number, differ only because the oracle's `Panel` internals store the value as `np.float32` while the adapter computed it natively as `np.float64` (P0-R2's established root cause). *When* raw-score parity is scored for that leg (A-leg or any of the 4 B-legs). *Then* the adapter MUST reproduce the oracle's actual float32 storage truncation before comparison (a frozen-semantics reproduction, never a tolerance widened to paper over the gap), and **every** leg (A and all 4 B-legs) MUST carry its own regression test proving the fix is real — a test that fails without the truncation and passes with it, mirroring P0-R2's `test_float32_truncation_brings_common_key_raw_scores_within_tolerance`. Absence of a leg-specific regression test is itself a Gate R3-B/A-leg-parity finding deficiency, not merely a style gap.
- **AC-R3-12 (tie boundary).** *Given* the `top_pct=20` cutoff (§2.2's oracle definition) falls exactly on a rank value shared by two or more stocks for some `as_of` (a tie at the `topk_mask_desc` boundary). *When* the adapter reconstructs that date's top-20% set. *Then* the adapter MUST use the identical tie-break behavior that `core/canonical_universe.py`'s `rank_pct_desc`/`topk_mask_desc` actually implements (§8, reused verbatim — never a different, seemingly-equivalent tie-break reimplementation), and any date where the tie-break choice changes membership must be flagged explicitly in that date's per-date result, never silently absorbed into the aggregate match rate.
- **AC-R3-13 (254/255-month partial completion — round 5: explicit gate-FAIL outcome, diagnostic-only disclosure carve-out, denominator-shrinking ban made explicit).** *Given* the adapter or oracle produces usable output for fewer than all 255 canonical `as_of` dates (one or more dates missing from either side, per the frozen dates list). *When* the parity aggregate for Gate R3-U, Gate R3-B, or Gate R3-Q is computed. *Then*:
  1. **Every one of Gate R3-U, R3-B, and R3-Q that the missing month(s) fall within scope of MUST FAIL** for qualification-track purposes — full-population, full-month-set coverage is a precondition of a qualification PASS for these gates, not merely a completeness note attached to one. A 254/255 (or fewer) result is not "PASS with a caveat"; it is a FAIL.
  2. The study MAY still disclose a **254-month (or however-many-month) diagnostic result** alongside the FAIL — e.g. for root-cause investigation — but that disclosure MUST be labeled explicitly as a diagnostic/partial result and **MUST NOT be described, or read by any later report, as "full parity," "complete parity," or a qualification PASS** for the gate(s) in question, under any wording.
  3. **The denominator is never shrunk to make the reported result look more complete than it is.** The study reports the true denominator (255, the frozen canonical month count) and the true numerator (however many months actually had usable output), explicitly names every missing date and which side it is missing from (oracle-only or adapter-only), and never silently substitutes "months actually tested" for "months required" as if they were the same number without saying so.
- **AC-R3-14 (raw score passes, membership fails).** *Given* a date's raw-score parity is within tolerance (`<=1e-12`, NFR-R3-1) for every common key, but that same date's adapter/oracle populations differ (Gate R3-U FAIL for that date, per AC-R3-10). *When* the study's per-date or aggregate result is reported. *Then* raw-score PASS is reported independently and explicitly alongside membership FAIL for that date — a raw-score PASS must never be described or read as implying membership also passed; the two remain fully independent results in every report (this is the exact conflation P0-R2 Phase D Round 2 corrected, made binding here for R3 from the start).
- **AC-R3-15 (membership passes, PIT gate fails).** *Given* a date's adapter/oracle population membership matches exactly (Gate R3-U PASS for that date), but Gate R3-P has already FAILed for a dataset that date's reconstruction depends on (§7.4). *When* the study's qualification status is computed. *Then* that date's `COMPARABLE_IDENTITY`/full-qualification status remains BLOCKED despite the membership match — a downstream gate's PASS never overrides an upstream gate's FAIL (§7.7 item 2's binding prohibition).
- **AC-R3-16 (null/empty common keys fail closed).** *Given* a date's oracle and adapter populations share zero common keys (`common_keys_count = 0`, mirroring `a_leg_parity.py`'s existing `raw_score_parity` result shape). *When* raw-score parity is computed for that date. *Then* `within_tolerance` is recorded as `null`/`None`, never as `True` — the absence of any comparable data must never be reported as a passing comparison, and `null` is kept strictly distinct from `True` throughout every report this study produces.

### 10.5 Snapshot mechanics (feeds Gate R3-F) — round 4: AC-R3-17, 18 rewritten in full, self-sufficient

- **AC-R3-17 (snapshot hash mismatch).** *Given* a file's SHA256 recorded in the `SnapshotManifest` (§13.3) does not match the SHA256 an independent re-hash of the snapshot copy computes after Phase C completes. *When* the mandatory post-copy re-hash verification runs (§9). *Then* Gate R3-F FAILs for that file's dataset — the zero-mismatch-tolerance rule (§9) admits no "close enough" byte difference, and a single mismatched file blocks that dataset's use in every downstream gate that depends on it.
- **AC-R3-18 (hard-link detection).** *Given* a file in the Phase C snapshot destination shares an inode (or the NTFS-equivalent hard-link identity) with its source file, rather than being an independently-allocated byte copy. *When* the snapshot integrity check runs. *Then* Gate R3-F FAILs — a hard link is not an independent durable copy (a later mutation or deletion of the source would silently corrupt the supposedly-frozen snapshot), so the check must explicitly detect and reject hard-links, not merely verify content equality (which a hard link trivially satisfies).
- **AC-R3-22 (coherent-copy violation).** *Given* a source file's `source_pre_sha256 != source_post_sha256` for any file in a Phase C copy batch (§9). *When* Gate R3-F is scored. *Then* Gate R3-F FAILs for the **entire batch**, not only the changed file; the batch is discarded and must be re-copied from a stable source state before re-attempting Gate R3-F.

### 10.6 Phase-gating and admission (feeds §7.0 / Gate R3-L,S,P sequencing)

- **AC-R3-23 (Phase C admission blocked).** *Given* Gate R3-S or Gate R3-P FAILs in Phase B. *When* Phase C is considered. *Then* Phase C does not proceed; the study files a null/blocked result naming the failed gate and dataset/field, with no snapshot, no qualification claim, and no further phase — unless the user has separately and explicitly approved a diagnostic-only snapshot (§7.0), which itself may never feed a qualification verdict.
- **AC-R3-24 (leg-formula freeze incomplete — round 4: corrected, no partial-leg path).** *Given* the §8 Phase B freeze record (callable chain, code SHA256, input fields, constants, window, merge key, industry fallback, NaN/tie/ranking semantics, step-by-step formula) is incomplete for the A-leg **or any one** of the 4 B-legs. *When* Phase C (qualification-track snapshot) is considered. *Then* **Phase C does not proceed at all, for any leg** — there is no partial-leg snapshot and no partial-leg qualification path. The five legs (A + 4 B) are qualified as one unit against one oracle definition (`dual_confirm_mask`, §2.2/§8); a snapshot or qualification attempt covering only the legs whose freeze record happens to be complete, while treating the remainder as silently deferred, is exactly the kind of manufactured-partial-result this study's binding prohibitions (§7.7) exist to prevent. **Round 4 correction:** round 3's wording ("Phase C does not proceed for that leg's dependent snapshot content") wrongly implied a leg-by-leg admission path; that wording is retracted and replaced by this whole-study block.
- **AC-R3-25 (D\* first-adjudication is not a "change").** *Given* Gate R3-L's first-ever adjudication resolves D\* to a composition different from §3.4's preliminary reading (e.g. it includes FinMind datasets §3.4 did not anticipate). *When* D\* is frozen for the first time. *Then* this is **not** treated as a "D\* change" under §6's diff/reapproval rule — that rule applies only to changes **after** the first freeze (§6 round 3 clarification).

### 10.7 Gate R3-I / R3-N minimum evidence acceptance semantics (new this round — fixed now, not deferred to Phase B)

Phase B may still design and freeze the *concrete* artifact schema (exact field names, file format, storage location) for the R3-I/R3-N evidence artifacts — but the **minimum semantics an artifact must satisfy to PASS** are fixed by this prereg now, not left open for Phase B to decide later.

- **AC-R3-26 (Gate R3-I — process-isolation evidence, minimum acceptance semantics).** *Given* Gate R3-I is scored. *Then* it may PASS only if the evidence artifact records **all** of: (a) a genuine, independently-attributable process identity for both the oracle/reference computation and the adapter — a real OS PID plus process-start-time (or equivalent), not merely "ran inside a `subprocess.run()` call" with no captured identity; (b) an import/access manifest whose own bytes have a durable hash identity per §5 (SHA256 recorded and reproducible), not an in-memory-only or ephemeral result; (c) the manifest is never labeled `LIMITED_*_ONLY`, a placeholder, or a self-declared PASS with no underlying artifact — P0-R2 Phase D Round 2's `LIMITED_A_LEG_PROCESS_SEPARATION_ONLY` downgrade is the explicit **floor** this gate must exceed, not a form it may repeat as a final result; (d) the full, real forbidden-target list for this study's adapter (mirroring FR-24's contract) is actually monitored **during the run** (not a static source-code scan alone), and the resulting reached-forbidden-targets set is recorded and is empty. *If any of (a)–(d) is missing, unevidenced, or downgraded to a LIMITED/placeholder form, Gate R3-I FAILs* — it does not default to PASS, and it is never scored PASS merely because no violation was observed under insufficient monitoring that could not have caught one.
- **AC-R3-27 (Gate R3-N — future-input-access evidence, minimum acceptance semantics — round 5: unified with AC-R3-8, see that criterion for the FAIL-trigger side of this same rule).** *Given* Gate R3-N is scored. *Then* it may PASS only if the evidence artifact records **all** of: (a) a real, executed access-trace covering every file the adapter process actually opened during the run — not merely a static AST/import-graph scan of the adapter's own source, which proves only what the code *could* do, not what it *did*; (b) that trace's own bytes have a durable hash identity per §5; (c) it is never labeled `LIMITED_STATIC_CHECK_ONLY` or any other placeholder/self-declared-PASS form as a **final qualification result** — that label is P0-R2 Phase D Round 2's honest floor for a partial, non-qualifying result, not an acceptable Gate R3-N PASS basis; (d) the full named forbidden-target list (`exec_ret.parquet`, `obs_alpha.parquet`, and any other file Phase B's Gate R3-L lineage work identifies as future-only) is checked against the real trace, and the resulting reached set is recorded and is empty. *If any of (a)–(d) is missing, Gate R3-N FAILs* — absence of evidence is scored as a FAIL, never as a PASS-by-silence. **This is one side of a single rule with AC-R3-8: AC-R3-8 governs the FAIL trigger (a violation found by either static scan or executed trace fails the gate); this AC governs the PASS floor (only a complete executed trace, never a clean static scan alone, can pass it). The two are not independently satisfiable criteria — a report may not cite AC-R3-8's "no static violation found" as satisfying AC-R3-27's PASS requirement.**

### 10.8 Traceability-closing acceptance criteria (new this round — formalize FR-R3-13 and NFR-R3-2/3/6, replacing narrative-only coverage)

- **AC-R3-28 (inherited numeric annotation without citation — formalizes FR-R3-13 / NFR-R3-5).** *Given* any report or prereg text this study produces states a numeric figure (count, percentage, date list, row count, etc.) that originates from another file's own comment/docstring rather than from this study's own independently-executed measurement. *When* that figure is included in the document. *Then* it MUST carry both (a) the exact source file path and line range it was copied from, and (b) an explicit "not independently verified by R3" caveat, until the figure is independently recomputed and confirmed (at which point the caveat is replaced by the confirming evidence). *A numeric figure lacking either (a) or (b) must be struck from the document before it may be finalized.* This AC generalizes the practice §3.3 already applied to the 3.67%/8-dates/11,053-rows/61% figures to every future figure of the same kind.
- **AC-R3-29 (D\* coverage gap — no general waiver — formalizes the round-4-corrected NFR-R3-2).** *Given* any dataset in the frozen D\* is missing coverage for one or more of the 255 required canonical months across the full-market reconstruction target. *When* Gate R3-S is scored. *Then* Gate R3-S FAILs for that dataset, named explicitly, and Phase C (qualification-track) is blocked under §7.0 — **there is no general/blanket waiver of this rule.** The sole permitted continuation is the §7.0 diagnostic-only-snapshot exception, which can never convert Gate R3-S to PASS and can never feed a qualification verdict.
- **AC-R3-30 (durable-identity gap — formalizes NFR-R3-3).** *Given* any code or dataset file referenced as evidence by a scored gate (R3-L through R3-N) lacks a durable identity satisfying §5's rule (neither a reachable committed blob nor an independent byte copy with SHA256+bytes+documented verify command — a bare `git hash-object -w` loose blob does not, by itself, count). *When* that gate's evidence is audited. *Then* the referencing gate FAILs until the durable identity is established — a gate's PASS may never rest on a file whose byte identity cannot be independently reproduced later.
- **AC-R3-31 (single-shot violation — formalizes NFR-R3-6).** *Given* Gates R3-U/R3-B/R3-Q/R3-I/R3-N (Phase E's single-shot scope, §7.6/§11) are run more than once against the same frozen snapshot and adapter code, and a later run's result is reported in place of, or in preference to, an earlier run's result, without a separately disclosed methodology-fix report explaining the defect in the earlier run and why the fix is not tuning toward a favorable outcome. *When* this pattern is detected (e.g. by comparing report/commit timestamps against the recorded single run). *Then* the reported result is treated as a single-shot-discipline violation and is invalid as a qualification basis — every run must be disclosed (not only the most favorable one), mirroring the round-to-round correction discipline this document's own revision history (round 1→2→3→4) already models.

---

## 11. Execution phases (gate timing corrected this round — see §7.0/§7.6)

- **Phase A — Document review / manual approval.** This document only. Ends when Status changes to `APPROVED`.
- **Phase B — Read-only source-lineage adjudication, then source-sufficiency and PIT-evidence inventory.** Authorized by Phase A approval **only**, and internally ordered:
  1. First, formally complete Gate R3-L's per-field record (§7.1) via static callable/import tracing, for all 6 target fields.
  2. **Only if Gate R3-L PASSes** and D\* is frozen: evaluate **Gate R3-S** (source sufficiency, §6/§7.2) over D\*, **and** evaluate **Gate R3-P** (PIT/announcement-date validity, §7.4) over D\*'s per-dataset cutoff evidence. Both are scored in Phase B, not deferred to Phase E.
  3. Also in this step: complete the per-leg freeze record required by §8 (exact callable chain, code SHA256, input fields, constants, window, merge/join key, industry-fallback rule, NaN/tie/ranking semantics, step-by-step formula) for the A-leg and all 4 B-legs — required before Phase C, per §8's binding rule.
  If Gate R3-L FAILs, Phase B stops there; Gates R3-S/R3-P (and everything downstream) are `NOT_EVALUATED` and the study reports a null/blocked result (§7.0).
  **Phase B MUST NOT run parity, membership, raw-score comparison, or any performance computation** — it is read-only tracing, cataloging, and (for R3-S/R3-P) sufficiency/evidence adjudication over already-existing files' metadata/schema, never over computed scores.
- **Phase C — Snapshot creation.** Requires **separate, explicit user approval** beyond Phase A's, granted only after the §7.0 admission rule is satisfied (Gate R3-L PASS + Gate R3-S PASS + Gate R3-P PASS, D\* disclosed in full, design-freeze document written, per-leg formula freeze from Phase B step 3 complete) — **or**, as the sole exception, an explicit separate approval of a diagnostic-only snapshot (§7.0). Snapshot copying is followed immediately by the coherent-copy assertion (§9) and scored as **Gate R3-F** in this phase, not in Phase E.
- **Phase D — Tests / minimal offline adapter implementation.** Failing-tests-first, against the Phase C snapshot only.
- **Phase E — Single-shot reveal of R3-U/R3-B/R3-Q/R3-I/R3-N, with re-disclosure of all earlier-resolved gates.** One real run scores Gates `R3-U`, `R3-B`, `R3-Q`, `R3-I`, `R3-N` together, single-shot, not iterated to seek a more favorable result (§7.6). The Phase E report then **re-discloses and re-verifies** (re-states the already-recorded status of, and re-confirms nothing has drifted since) Gates `R3-L`, `R3-S`, `R3-P` (resolved in Phase B) and `R3-F` (resolved in Phase C) alongside the 5 newly-scored gates, so the final report shows all 9 gates' status together. **This re-disclosure must not be described, or read by any later report, as those 4 gates having been "first scored" or "scored together" in Phase E — they were scored earlier, in the phases named above; Phase E only re-presents them.**
- **Phase F — Report and archive.** No Stage-2-equivalent activation implied by completing this phase.

**Post-approval correction (this document's Phase A approval, §14, dated 2026-08-15): Phase B is authorized, per the steps enumerated above — Status is `APPROVED` and this is no longer a pending/IN REVIEW condition.** Phase C, however, remains unauthorized by this document: it requires its own separate, explicit user approval per §7.0/§11's admission rule (Gate R3-L PASS + Gate R3-S PASS + Gate R3-P PASS, D\* disclosed in full, the design-freeze document written, and the §8 per-leg formula freeze from Phase B step 3 complete) — or, as the sole exception, a separately, explicitly approved diagnostic-only snapshot (§7.0). No data snapshot, no manifest, no test file, and no implementation code may be created until that separate Phase C approval is granted.

---

## 12. Out of scope

Unchanged from round 1: production writes; live collector; evidence-root activation; Task Scheduler; back-filling production evidence or labeling any P0-R3 output as contemporaneous production evidence; strategy/factor/weight/threshold tuning; new ADV-floor research; any performance/CAGR/Sharpe metric; P0-R2 Stage 2 activation; modifying any P0-R2 or P0-U1 artifact; using `obs_alpha.parquet`/`exec_ret.parquet` as an R-FWD adapter input under any name or derived form.

---

## 13. Mechanical specification (new this round: FR/NFR, data models, AC traceability, edge cases, API surface)

This section exists to make every gate above independently checkable against a mechanical requirement, not only a narrative description. It does not authorize any phase; it specifies what Phase B onward must implement once approved.

### 13.1 Functional requirements (FR-R3-*)

| ID | Requirement | Feeds gate |
|---|---|---|
| FR-R3-1 | Statically trace and record the producing callable chain, raw dataset family, source paths, transformation formula, cutoff semantics, code hashes, and git state for each of the 6 target fields. | R3-L |
| FR-R3-2 | Freeze D\* as the proven union of every field's evidenced raw-dataset family once, and only once, Gate R3-L PASSes for all 6 fields. | R3-L |
| FR-R3-3 | For every dataset in D\*, record path, provider, full-corpus schema, ticker/date/publication semantics, first/last structural date, revision policy, duplicate-key policy, missingness rules, PIT cutoff type, SHA256, and an explicit per-dataset eligibility verdict. | R3-S |
| FR-R3-4 | For every dataset in D\*, classify its cutoff/publication field as `genuine` or `fixed_offset_proxy` and record the supporting evidence (or absence thereof) for each. | R3-P |
| FR-R3-5 | Build a real-byte-copy, hard-link-free snapshot per dataset, with the §9 coherent-copy assertion checked for every file. | R3-F |
| FR-R3-6 | Reconstruct the decision-time universe using only PIT-eligible inputs (`listed_ok`, `adv20`); never read, derive, or proxy `HAS_RET` or any forward-return-availability signal. | R3-U |
| FR-R3-7 | Compute raw-score parity for the A-leg and all 4 B-legs against the oracle's values, including float32/float64 storage-representation matching per leg. | R3-B |
| FR-R3-8 | Compute a 255-month, full-population (never common-population-narrowed) final membership exact-match result plus cross-leg raw-score tolerance. | R3-Q |
| FR-R3-9 | Produce a genuine process-isolation / import-manifest evidence artifact (not a `LIMITED_*_ONLY` placeholder). | R3-I |
| FR-R3-10 | Produce a genuine future-input-access evidence artifact (not a static-only, unwritten check). | R3-N |
| FR-R3-11 | Block Phase C whenever Gate R3-S or Gate R3-P FAILs, except via a separately, explicitly approved diagnostic-only snapshot that may never feed a qualification verdict. | §7.0 |
| FR-R3-12 | Require full-diff disclosure and fresh user approval for any D\* change occurring after D\*'s first freeze (not for the first freeze itself). | §6 |
| FR-R3-13 | Any numeric claim copied from another file's own comment/annotation must carry an exact `path:line` citation and an explicit "not independently verified by R3" caveat until independently confirmed. | §3.3 |

### 13.2 Non-functional requirements (NFR-R3-*, measurable)

| ID | Requirement | Threshold |
|---|---|---|
| NFR-R3-1 | Raw-score comparison tolerance. | Absolute difference `<= 1e-12`, computed in float64 after each side's real storage-representation (e.g. float32 truncation) is reproduced. |
| NFR-R3-2 | D\* corpus coverage (round 4: general-waiver clause removed). | 0 missing required months across the full 255-month/full-market reconstruction target for every frozen dataset. **No general/blanket waiver of this threshold exists.** Any missing month fails Gate R3-S for that dataset (AC-R3-5, AC-R3-29) and blocks qualification-track Phase C under §7.0. The sole permitted continuation is a separately, explicitly approved **diagnostic-only snapshot** (§7.0) — which itself never converts Gate R3-S to PASS and can never feed a qualification verdict, so it is not a waiver of this NFR, only a narrowly-scoped, non-qualifying exception to the Phase C admission block. |
| NFR-R3-3 | Durable-identity coverage. | 100% of code/dataset files referenced by any scored gate have a durable identity per §5 (reachable committed blob, or byte copy + SHA256 + bytes + documented verify command) — no exceptions, no loose-blob-only identities. |
| NFR-R3-4 | Snapshot copy integrity. | 100% of files in every Phase C batch pass the 3-way coherent-copy assertion (§9); 0-mismatch tolerance on post-copy re-hash. |
| NFR-R3-5 | Inherited-annotation auditability. | 100% of numeric claims sourced from another file's own comment carry an exact `path:line` citation and a "not independently verified" caveat (until independently confirmed, at which point the caveat is replaced with the confirming evidence). |
| NFR-R3-6 | Single-shot discipline. | Phase E's R3-U/R3-B/R3-Q/R3-I/R3-N scoring is one run; 0 silent re-runs seeking a more favorable result — any re-run requires a separately disclosed methodology-fix report, mirroring P0-R2 Phase D's round-1→round-2 correction precedent. |

### 13.3 Data models

```
LineageRecord {
  field_name: str                      # one of the 6 target fields
  callable_chain: [str]                 # ordered module/function hops, ending at the raw-file read
  raw_dataset_family: [str]             # named datasets actually read, not name-similarity inference
  source_paths: [str]                   # absolute, with any env-var resolution documented
  transformation_formula: str           # verbatim from source, not paraphrased
  cutoff_semantics: {
    kind: "genuine_field" | "fixed_offset_proxy"
    detail: str                         # field name, or the offset constant + its source location
  }
  code_hashes: {path: sha256}           # every file in the chain
  git_state: {path: status}             # Windows-Git-scoped only, per §4
  verdict: "TRACED" | "AMBIGUOUS"
}

DatasetIdentity {
  dataset_name: str
  provider: str                         # e.g. "TEJ", "FinMind"
  path: str
  schema_fingerprint: str
  first_date: date
  last_date: date
  revision_policy: str
  duplicate_key_policy: str
  missingness_notes: str
  pit_cutoff_type: "genuine_field" | "fixed_offset_proxy"
  sha256: str
  bytes: int
  eligibility_verdict: "SUFFICIENT" | "INSUFFICIENT"
}

DStarManifest {
  version: int
  frozen_at: iso8601
  is_first_freeze: bool
  datasets: [DatasetIdentity]
  source_lineage_records: [str]         # field_name references into LineageRecord set
  change_history: [
    { from_version: int, to_version: int, diff: str, approved_by: str, approved_at: iso8601 }
  ]                                     # empty for the first freeze (§6 round-3 clarification, AC-R3-25)
}

SnapshotManifest {
  dataset_name: str
  files: [
    {
      relative_path: str
      source_pre_sha256: str
      copied_sha256: str
      source_post_sha256: str
      bytes: int
      row_count: int
      schema_fingerprint: str
      coherent: bool                    # source_pre == copied == source_post
    }
  ]
  aggregate_hash: str
  created_at: iso8601
  gate_r3f_status: "PASS" | "FAIL"
}

GateResult {
  gate_id: "R3-L" | "R3-S" | "R3-P" | "R3-F" | "R3-U" | "R3-B" | "R3-Q" | "R3-I" | "R3-N"
  status: "PASS" | "FAIL" | "NOT_EVALUATED"
  evidence_refs: [str]                  # paths/IDs into the records above
  reason_code: str | null
  scored_in_phase: "B" | "C" | "E"
  scored_at: iso8601
}
```

### 13.4 FR/NFR ↔ AC traceability (round 4: complete in both directions, no orphans — see §13.7 for the mechanical check)

**FR-R3-* → covering AC-R3-***

| FR | Requirement (short) | Covering AC(s) |
|---|---|---|
| FR-R3-1 | Trace producing chain per field | AC-R3-19, AC-R3-20, AC-R3-21 |
| FR-R3-2 | Freeze D\* as proven union | AC-R3-20, AC-R3-25 |
| FR-R3-3 | Per-dataset sufficiency record | AC-R3-1, AC-R3-2, AC-R3-3, AC-R3-5 |
| FR-R3-4 | Per-dataset PIT-cutoff classification | AC-R3-6, AC-R3-7 |
| FR-R3-5 | Snapshot copy + coherent-copy assertion | AC-R3-17, AC-R3-18, AC-R3-22 |
| FR-R3-6 | Decision-time universe, no `HAS_RET` | AC-R3-10, AC-R3-10a, AC-R3-12, AC-R3-13 |
| FR-R3-7 | Raw-score parity, A-leg + 4 B-legs | AC-R3-11, AC-R3-13, AC-R3-16 |
| FR-R3-8 | 255-month full-population final membership | AC-R3-13, AC-R3-14, AC-R3-15 |
| FR-R3-9 | Process-isolation evidence artifact | AC-R3-9, AC-R3-26 |
| FR-R3-10 | Future-input-access evidence artifact | AC-R3-8, AC-R3-27 |
| FR-R3-11 | Block Phase C on R3-S/R3-P FAIL | AC-R3-23, AC-R3-24, AC-R3-29 |
| FR-R3-12 | D\* post-freeze change diff/reapproval | AC-R3-25 |
| FR-R3-13 | Inherited-annotation citation discipline | AC-R3-28 |

**NFR-R3-* → covering AC-R3-***

| NFR | Requirement (short) | Covering AC(s) |
|---|---|---|
| NFR-R3-1 | Raw-score tolerance `<=1e-12` | AC-R3-11 |
| NFR-R3-2 | D\* corpus coverage, no general waiver | AC-R3-5, AC-R3-29 |
| NFR-R3-3 | Durable-identity coverage, 100% | AC-R3-30 |
| NFR-R3-4 | Snapshot copy integrity | AC-R3-17, AC-R3-18, AC-R3-22 |
| NFR-R3-5 | Inherited-annotation auditability | AC-R3-28 |
| NFR-R3-6 | Single-shot discipline | AC-R3-31 |

Every FR-R3-1 through FR-R3-13 and every NFR-R3-1 through NFR-R3-6 has at least one covering AC in the tables above — see §13.7 for the mechanical orphan check confirming this, and for the reverse direction (every AC-R3-* maps to at least one FR/NFR).

### 13.5 Snapshot/source-mutation edge cases (must be handled by Phase C's implementation, not merely by the coherent-copy assertion's headline rule)

1. **Source file deleted between manifest build and copy.** Treated as a coherent-copy failure for that file (there is no `source_post_sha256` to compare) — Gate R3-F FAILs for the batch, per §9.
2. **Source file's mtime changes but content is byte-identical.** Not a failure — the assertion is content-hash-based only; mtime is not compared.
3. **Source file mutates and then reverts to its original bytes within the copy window.** Still a failure if `source_pre_sha256` was captured before the mutation and `source_post_sha256` is captured after the revert but the *copy* itself captured the mutated intermediate state — the three-way check (not a simple pre/post-only check) is what catches this; `copied_sha256` must independently match both endpoints, not merely have them match each other.
4. **A new, unmanifested file appears in the source directory mid-batch.** Must NOT be silently included in the snapshot; only files enumerated in the pre-copy manifest are copied, and a new file discovered later requires a fresh manifest and a fresh copy pass (not an in-place addition).
5. **Wall-clock skew makes "pre" appear to sort after "post."** Ordering guarantees must come from the copy process's own monotonic sequencing (e.g. issuing the pre-hash read, then the copy, then the post-hash read, all within one uninterrupted sequential routine), never from comparing timestamps across possibly-skewed clocks.

### 13.6 API surface

**HTTP API: N/A.** This study has no network-facing service component at any phase.

**Offline CLI contract: deferred to Phase B.** This document does not fabricate command names, flags, or argument shapes for lineage-tracing, snapshot-building, or gate-scoring tools — none has been designed yet. Phase B must specify and freeze the actual CLI contract (mirroring P0-R2's precedent of `a_leg_oracle.py`/`a_leg_adapter.py`/`a_leg_parity_runner.py` each taking explicit `--` flags for frozen paths, never resolving a live path itself) before any such tool may be implemented in Phase D.

### 13.7 Round 4 mechanical self-sufficiency check (new this round)

**Purpose.** Round 4's instruction requires (a) a full enumeration proving no orphan FR/NFR/AC, (b) a search confirming no remaining normative text stands in for the deleted round-1 document, and (c) an honest disclosure of any generic-spec-validator limitation rather than an unearned "PASS" claim. This subsection is that record, produced by manual inspection of this document as it stands after this round's edits — not by an external tool run.

**13.7.1 Full enumeration (round 5: AC count corrected — 31 live + 1 tombstone = 32 total, not 30 + 1 = 31 as round 4 miscounted).**

- **FR-R3-*:** 13 requirements (FR-R3-1 through FR-R3-13, §13.1) — all 13 appear as rows with a non-empty covering-AC list in §13.4's FR table. **0 orphan FRs.**
- **NFR-R3-*:** 6 requirements (NFR-R3-1 through NFR-R3-6, §13.2) — all 6 appear as rows with a non-empty covering-AC list in §13.4's NFR table. **0 orphan NFRs.**
- **AC-R3-*:** **32 criteria total.** Enumerating every distinct AC-R3-* label used anywhere in §10: `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31` — that is **31 distinct numeric/lettered identifiers plus the `10a` suffix insertion, i.e. 32 labels**, of which:
  - **31 are live, self-sufficient Given/When/Then criteria**: `1, 2, 3, 5, 6, 7, 8, 9, 10, 10a, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31` (round 4 miscounted this set as "30 live" — a plain arithmetic error, corrected here: counting each label once, including `10a`, the set has 31 members, not 30).
  - **1 is a tombstone**: `AC-R3-4` (§10.2), explicitly not a live requirement, pointing to its replacements AC-R3-19/AC-R3-20.
  - `31 live + 1 tombstone = 32 total` — reconciles exactly with the "32 criteria total" figure (which round 4 stated correctly even though its "30 live" sub-count was wrong).
  - **Mechanical reconciliation result:** 31 live definitions in §10 → 31 of those 31 appear in at least one FR or NFR row of §13.4's tables → **31 mapped, 0 unmapped**. Checking the reverse direction — every AC-R3-* label appearing anywhere in §13.4's "Covering AC(s)" columns — confirms only labels from the 31-live set appear there (AC-R3-4 does **not** appear in any §13.4 row, consistent with its tombstone status) → **0 mapped-without-live** (no AC is cited as covering an FR/NFR without itself having a live definition in §10).

**13.7.2 "Retained / unchanged / restated" search — confirms no remaining reliance on the deleted round-1 file.**

A manual text search of this document (post-round-4-edit) for the strings "retained", "unchanged from round 1", and "restated ... from round 1" as **normative content** (i.e. as the entire substance of a requirement, rather than as a historical note about when a requirement was *introduced*) finds:

- §10.2's AC-R3-1/AC-R3-3, §10.3's AC-R3-6–9, §10.4's AC-R3-10/11/12/13/14/15/16, and §10.5's AC-R3-17/18 — **all previously read only "Unchanged from round 1" / "restated verbatim from round 1, no content change"; all have been rewritten in full, self-sufficient Given/When/Then form this round** (§10.2–§10.5 above). None of these any longer depends on reading the deleted file to know its own content.
- Remaining occurrences of "round 1" in the document (e.g. §0's "Unchanged from round 1" for the non-claims list in §1, §1's "Round 1 assumed...", §4/§5/§9's "corrects round 1's error", §11's phase-numbering history) are **historical/provenance notes** — they describe what round 1 *originally said or got wrong*, as context for why a rule now reads the way it does, and are not themselves the normative rule text. The one substantive exception checked and confirmed clean: §1's numbered non-claims list (1–5) is fully spelled out in this document's own text, not a reference requiring the deleted file to resolve.
- **Conclusion: no requirement in this document, after this round's edits, requires reading the deleted round-1 file to determine its own normative content.** Historical attribution notes remain (by design — they are part of this study's audit trail of its own corrections), but they are documented as history, not substituted for specification.

**13.7.3 Generic spec-validator compatibility — round 5: specific disclosure, not a generic "none was run" statement.**

This document uses **numbered Markdown headings with embedded gate/AC/FR/NFR IDs** (e.g. `### 10.4 Reconstruction correctness`, `AC-R3-10a`) rather than a machine-parseable requirements format (e.g. ReqIF, a structured YAML/JSON requirements file, or a tool-specific DSL).

- **Round 4 (the round that drafted §13.7 originally):** the drafting author did not execute any spec-validator tool against this document. That remains true and is restated here precisely rather than folded into a blanket "none was run" claim, since a validator run **has** since been reported (next bullet), and the two facts must not be blurred together.
- **This round (round 5), per an independent review's report:** an independent reviewer executed a general-purpose `spec_validator.py --strict` against this document and reported a result of **0/100**, with **8 missing-section false negatives** — i.e. the validator's parser did not recognize 8 sections it expected to find, because this document's numbered/nested Markdown heading style (`## 13.`, `### 13.4`, bold-inline `AC-R3-10a` IDs, etc.) does not match whatever section-detection pattern that generic tool expects. This document records that reported result as-is; the drafting author of this round did not independently re-run the tool and cannot independently verify the raw tool output or its exact false-negative list beyond what was reported — if the user needs that underlying evidence preserved, it should be captured as a durable artifact (§5) separately from this document.
- **This 0/100 / 8-missing-section result is explicitly a parser/format compatibility limitation, not a substantive spec PASS or FAIL.** A 0/100 score from a tool that cannot parse the document's structure at all carries no information about whether the document's actual requirements are complete or correct — it is not evidence toward either verdict, and this document does not treat it as one. Specifically:
  - The FR-R3-*/NFR-R3-*/AC-R3-* IDs are plain bold/inline-code Markdown text, not a schema a generic tool would recognize as a requirement identifier.
  - The §13.4 tables are Markdown tables, not a structured cross-reference format most requirements-traceability tools ingest.
  - AC-R3-10a's non-integer suffix is a human-readable insertion convention, not a format most ID-parsing tools anticipate.
  - A tool reporting "missing section" for a section that is, in fact, present (as confirmed by §13.7.1's direct manual count) is by definition a **false negative** of the tool's parser, not a true finding about this document.

**This document's actual, substantive completeness verification remains §13.7.1's mechanical FR/NFR/AC extraction and its reverse mapping** — a manual, item-by-item cross-check of every FR/NFR/AC's presence in the traceability tables (re-verified this round: 31 live definitions, 31 mapped, 0 unmapped, 0 mapped-without-live). That manual result is not superseded, contradicted, or validated by the generic tool's 0/100 — the two measure different things (structural parseability by a generic tool vs. actual requirement-to-criterion coverage), and this document does not conflate them into a single "PASS/FAIL" headline. If the user needs the generic validator to score this document meaningfully, Phase B (once approved) should be the point where this document's requirements are transcribed into whatever machine-readable format that validator needs — that transcription is out of scope for this drafting-only round.

---

## 14. Approval fields (avoiding self-reference)

```text
Status: APPROVED — Phase A (this document) approved; Phase B (read-only source-lineage adjudication, source-sufficiency inventory, PIT-evidence inventory, per §11 steps 1-3) authorized. Phase C, Phase D, Phase E, and all production/cache/Scheduler writes are NOT authorized by this approval.
User approval: APPROVED — iam102038@gmail.com, 2026-08-15.
Approved scope:
  - Phase A: this document, as approved. Content identical to the pre-stamp draft identified below; only this §14 block and the top-of-document Status / Approval event / User approval / Implementation authorized / Drafting-scope fields were edited to record the approval — no normative content in §0-§13 or §15 changed.
  - Phase B, per §11 steps 1-3 only: (1) Gate R3-L per-field static callable/import tracing for all 6 target fields; (2) if and only if Gate R3-L PASSes, Gate R3-S (source sufficiency) and Gate R3-P (PIT/announcement-date validity) evaluation over the frozen D*; (3) the §8 per-leg freeze record (callable chain, code SHA256, input fields, constants, window, merge key, industry fallback, NaN/tie/ranking semantics, formula) for the A-leg and all 4 B-legs. Phase B MUST NOT run parity, membership, raw-score comparison, or any performance computation (§11, restated, binding).
Explicitly NOT authorized by this approval:
  - Phase C (snapshot creation, §9) — requires its own separate, explicit approval per §7.0/§11, gated on Gate R3-L/R3-S/R3-P all PASSing.
  - Phase D (tests / minimal offline adapter implementation, §11).
  - Phase E (single-shot R3-U/R3-B/R3-Q/R3-I/R3-N parity/membership/isolation/future-input reveal, §7.6/§11).
  - Any production, cache, or Task Scheduler write of any kind (§12, restated).
  - Any diagnostic-only snapshot (§7.0) — that remains its own separately, explicitly approved decision, not implied by this approval.
Implementation authorized: NO. Phase B is read-only tracing/cataloging/adjudication, not implementation. No code, test, adapter, snapshot, manifest, or production/cache/Scheduler write is authorized by this approval.
Approved repository baseline commit: 497a03ee04d676aa44f5948dcfc69d9c8edd3ebf (confirmed at approval — verified as the current HEAD at approval time, §2.1).
Approved draft SHA256: f08c289c048600e7cf47225d40267a8e7b3baec4dbf2ab1148125da30887a7a2 — the round-5 revision content exactly as it stood immediately before this approval-stamping edit; this is the exact content the user reviewed and approved.
Approval receipt: recorded externally in `docs/prereg_P0_R3_approval_receipt_2026-08-15.json` — per the self-reference-avoidance convention this section already establishes, this document does not, and must not, compute or embed its own post-stamp SHA256; that value (the SHA256 of this file as it exists on disk immediately after this approval edit) is recorded only in that external receipt file, together with the approved-draft SHA256 above and the repository baseline commit.
```

An `approval_receipt.json` was created as part of this approval event (`docs/prereg_P0_R3_approval_receipt_2026-08-15.json`), recording this document's post-stamp SHA256 externally per the rule stated above. No research output directory, snapshot, manifest, test, adapter code, or any Phase B work product was created this round, in round 5, in round 4, in round 3, in round 2, or in round 1 — Phase B has not begun. This approval event consists of document-stamping plus one external receipt file, committed together with this document and nothing else.

**Same-day consistency correction (post-commit `76aaf35120a36fda8940c70a644b731d065c4f43`):** two residual pre-approval-state sentences, left un-updated by the initial stamping pass, were found to contradict the just-recorded approval and are corrected here — no scope, gate, AC, or approved-content change: (a) §8's closing sentence ("An incomplete record for any leg blocks that leg from proceeding to Phase C") wrongly implied a leg-by-leg admission path already retracted by AC-R3-24 (§10.6); corrected to state the whole-study block. (b) §11's closing sentence ("This document does not authorize Phase B or Phase C") was pre-approval boilerplate now contradicted by Status: `APPROVED` and this section's own Phase B authorization; corrected to state Phase B is authorized while Phase C remains separately gated. The external receipt records both the pre-correction and post-correction document SHA256/byte/line counts.

---

## 15. Drafting-round integrity statement

This revision (round 5) was produced by document editing only: closing AC-R3-7's proxy-disclosure PASS loophole; unifying AC-R3-8 and AC-R3-27 into one explicit FAIL-OR/PASS-AND rule for Gate R3-N; strengthening AC-R3-13 to mandate an explicit gate FAIL (not merely a completeness note) whenever fewer than 255 canonical months are covered, with a diagnostic-only disclosure carve-out and an explicit denominator-shrinking ban; correcting §13.7.1's AC-count arithmetic (31 live + 1 tombstone = 32, re-verified this round by direct enumeration of every `AC-R3-*` label defined in §10 and cross-checked against §13.4's mapping tables — 31 defined, 31 mapped, 0 unmapped among the live set, 0 mapped-without-live); and replacing §13.7.3's generic "no validator was run" disclosure with the specific record that an independent review reported executing `spec_validator.py --strict` and receiving a 0/100 score with 8 missing-section false negatives, attributed explicitly to the tool's inability to parse this document's numbered/nested heading and inline-ID format, and explicitly not treated as a substantive spec PASS or FAIL. **No new code tracing, no new corpus scan, no parity/membership/raw-score/performance computation, and no data execution of any kind occurred this round.** The `spec_validator.py --strict` run itself was not executed or independently reproduced by this round's drafting author — its 0/100 / 8-false-negative result is recorded here as an independent review's reported finding, not as this round's own tool output; the AC-count re-verification, by contrast, *was* performed directly this round (via enumeration of the document's own text, not an external tool). Round 2–4's read-only code tracing (§3) and prior corrections are unchanged in substance this round. The round-1 file (`docs/prereg_P0_R3_RawHistoryBundleSnapshot_RfwdQualification_2026-08-15.md`) remains deleted, as it was in rounds 2–4; no second new file was created this round — only this one file was edited in place. Only this file is new relative to the repository baseline (verified in the accompanying report, §"staged diff empty").
