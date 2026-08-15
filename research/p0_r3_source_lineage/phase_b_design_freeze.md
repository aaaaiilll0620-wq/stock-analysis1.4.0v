# P0-R3 Phase B — Design Freeze (Gate R3-L / R3-S / R3-P)

**Status:** Phase B complete. **Disposition: NULL/BLOCKED RESULT** (§7.0) — Gate R3-S and Gate R3-P both FAIL; Phase C does not proceed.
**Prereg:** `docs/prereg_P0_R3_SourceLineage_RawSnapshot_RfwdQualification_2026-08-15.md`, Status `APPROVED` (Phase A + Phase B read-only scope), approved 2026-08-15.
**Repository baseline commit (durable code evidence anchor):** `b97d31602ff21b150f2f8e0abc3d3ad527f32241` (current HEAD; identical to the prereg's `497a03ee04d676aa44f5948dcfc69d9c8edd3ebf` baseline for every code path this document as evidence — see §7 diff confirmation). All code hashes below are the **git-committed** blob content, not the live working tree, except where explicitly marked "uncommitted working-tree only" (§6.4).
**Scope actually performed this round (per user authorization, 2026-08-15):** read-only Gate R3-L per-field lineage confirmation; Gate R3-S dataset-sufficiency check (schema/coverage, metadata-only, no parity/performance computation); Gate R3-P PIT-evidence classification; §8 per-leg formula/code-identity freeze for A-leg + 4 B-legs. **No snapshot, no tests, no adapter, no parity execution, no cache/production/Scheduler write.**
**Tooling note:** dataset schema/date-range/row-count inspection used `pyarrow` installed into an ephemeral, session-local target directory (`pip install --target=<scratchpad>/pylibs pyarrow`) — a read-only inspection tool, not a cache/production write. No `~/tej_cache`, `market_cache`, or repository file was modified by this inspection.
**Correction note (same-day revision, per user review):** fixes 6 issues in the initial draft — (1) `financial_statements`/`monthly_revenue` schema drift promoted from "disclosed but moot" to an independent Gate R3-S FAIL ground (`SCHEMA_DRIFT_UNRESOLVED`, §2.4/§2.6); (2) `institutional_gross`/`tdcc_weekly`'s self-contradictory "unverified-optimistic yet `genuine_field`/PASS" classification corrected to a single `unresolved`/`fixed_offset_proxy`/FAIL classification (§1.2, §3, §3.1); (3) duplicate-key audit explicitly labeled `NOT_FULLY_EVALUATED` — single-file sample only, fail-fast/short-circuit, no new full-corpus sweep performed (§2.5); (4) D\* dataset-corpus durable identity explicitly recorded as **not established** this round, new `DURABLE_IDENTITY_NOT_ESTABLISHED` reason added to Gate R3-S and Gate R3-P (§2.7); (5) Gate R3-L's PASS scope explicitly limited to the approved committed baseline, with the live working-tree production lineage recorded `NOT_EVALUATED`/non-claim (§1.7). **Overall disposition unchanged:** R3-L PASS (scoped), R3-S FAIL, R3-P FAIL, R3-F/U/B/Q/I/N `NOT_EVALUATED`, `NULL_BLOCKED_RESULT`, Phase C blocked. This correction is itself read-only document editing: no Phase C, no snapshot, no tests, no adapter, no data/production modification, no staging/commit.

---

## 1. Gate R3-L — Source-lineage adjudication

### 1.1 Field 1 — Decision-time universe (`listed_ok`, `adv20`)

- **Producing callable chain:** `scripts/alpha_gate_lab.py::build()` (Stage 2) → DuckDB SQL directly against `Path.home()/"tej_cache"/price_valuation/*.parquet` (glob, `union_by_name=true`) — **no `DataProvider`/overlay/collector involvement; pure frozen-batch read.**
- **Raw dataset family:** TEJ `price_valuation` only.
- **Exact source path:** `<home>/tej_cache/price_valuation/*.parquet` (env override `TEJ_CACHE`; `Path.home()` = `os.path.expanduser("~")` resolved at process start).
- **Transformation formula (verbatim, `scripts/alpha_gate_lab.py:103-112`):**
  ```sql
  SELECT stock_id, date,
         AVG(close * Trading_Volume) OVER (PARTITION BY stock_id ORDER BY date
             ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
         MIN(date) OVER (PARTITION BY stock_id) AS first_date
  FROM read_parquet('<TEJ>/price_valuation/*.parquet', union_by_name=true)
  ```
  ```python
  listed_ok = (first_date <= "2004-01-15") | ((date - first_date).days >= 365)
  ```
- **Cutoff/publication semantics:** same-day trailing window (20-row DuckDB frame, right-anchored), no lag needed. `cutoff_semantics.kind = "genuine_field"` (structurally PIT-safe by construction).
- **Downstream note (binding on the adapter, §7.5/§8):** `beat_0050/strategies/high52_lab.py::Panel` additionally ANDs `tier_valid` with `HAS_RET` (forward-return availability, `np.isfinite(self.RET)`, `self.RET` sourced from `exec_ret.parquet`) — confirmed again this round at `high52_lab.py:94,140,144,146`. This is **not** part of the pure PIT definition; §7.5/AC-R3-10a's rule that the adapter MUST NOT read/derive `HAS_RET` remains the binding reconstruction target.
- **Code hashes (git-committed blob content, `git show HEAD:<path> | sha256sum`):**
  `scripts/alpha_gate_lab.py` `be2f3dd8544034af69710a9b3a35e1d92ede8b7ce5fded8bd54c8898b4317e2a`; `scripts/lab_paths.py` `8cb132fc436d26f41c579932f636ecfa947a27f964a728f01a8d5e453528d0b0`.
- **Git state (Windows-Git-scoped, `git.exe status --short`):** both files clean, identical to HEAD `b97d3160...`.
- **Verdict:** `TRACED`, unambiguous.

### 1.2 Field 2 — A-leg `real_composite`

- **Producing callable chain:** `beat_0050/realbody/build_realbody_scores.py::main()` → `beat_0050.realbody.bt_bundle.bt_fetch_history` → `core.tej_bundle.tej_fetch_history` (two process-local overrides, §6.1) → `core.score_store.score_row` → `core.backtest.build_pit_stockdata` → `FundamentalEngine`/`ValuationEngine`/`ScoringManager`/`InvestmentAdvisor` → `.total_score` → `realbody_scores_adv100w.parquet::real_composite`.
- **Raw dataset family, per `HistoryBundle` field — re-traced this round to full precision (round 3's reading was directionally correct but materially incomplete; see corrections below):**

  | field | producing code | raw source(s) | durable? |
  |---|---|---|---|
  | `price`, `per` | `core.tej_bundle._price_valuation()` → `DataProvider._read_local_price_valuation` → `DataProvider._read_tej("price_valuation")` (frozen batch only, committed version) **∪** `DataProvider._ensure_market_daily_price()` (`market_cache/price_valuation_daily/*.parquet`, freshness-gated ≤7 days, TEJ wins on date overlap); fallback (if primary path returns `None`) = `tej_bundle.py`'s own `_read("price_valuation", symbol)` (pure frozen batch) | `tej_cache/price_valuation` (+ `market_cache/price_valuation_daily`, see §1.2.1) | yes (committed) |
  | `revenue` | `core.backtest._pit_revenue(symbol, None)` → `DataProvider._read_tej("monthly_revenue")` (frozen batch, committed version) **∪** `DataProvider._ensure_market_monthly_rev()` (`market_cache/monthly_revenue/*.parquet`) | `tej_cache/monthly_revenue` (+ `market_cache/monthly_revenue`, see §1.2.1) | yes (committed) |
  | `income`, `balance`, `cashflow` | `core.tej_bundle._tej_financials()` → `tej_bundle.py`'s own `_read("financial_statements", symbol)` — **direct frozen-batch read, bypasses `DataProvider` entirely** (round-3 correction: earlier reading did not verify this distinction) | `tej_cache/financial_statements` only | yes (committed) |
  | `chip` | `beat_0050.realbody.bt_bundle._flow_chip()` (override, §6.1) — **direct** `pd.read_parquet(TEJ_CACHE/"institutional_flow"/f"{symbol}.parquet")`, no `DataProvider` involvement | `tej_cache/institutional_flow` only | yes (committed) |
  | `shareholding` | `core.tej_bundle._tej_shareholding()` → `tej_bundle.py`'s own `_read()` for both `tdcc_weekly` (`total_lots_thousand`) and `institutional_gross` (`foreign_holding_pct`) — **direct frozen-batch reads, bypasses `DataProvider`** | `tej_cache/tdcc_weekly` ∪ `tej_cache/institutional_gross` | yes (committed) |

  **Round-3 correction:** round 3's §3.2 stated all of price/per/chip/shareholding used a uniform "`_slice(df, as_of)`, plain date≤as_of" mechanism with no further nuance. This round's full trace shows `chip`/`shareholding`/`income`/`balance`/`cashflow` are **direct, single-source frozen-batch reads** (simplest case), while `price`/`per`/`revenue` go through `DataProvider`'s two-layer precedence merge (§1.2.1). This distinction matters for exact reconstruction (§8) and is now recorded precisely.

- **§1.2.1 — `DataProvider` merge layer (`price`/`per`/`revenue` only): fully traced, deterministic, empirically inert for this study's 255-month target.**
  `DataProvider._read_local_price_valuation`/`_read_tej_monthly_revenue`(-equivalent via `_pit_revenue`) merge **frozen `tej_cache`** with a **live production collector snapshot** (`market_cache/price_valuation_daily/*.parquet`, `market_cache/monthly_revenue/*.parquet`), gated by a 7-day-staleness check computed against `datetime.now()` at execution time, with a deterministic **TEJ-wins-on-date-overlap** dedup rule (`concat([tej, collector]).drop_duplicates(["date"], keep="first")`, TEJ always first in the concat). This is a single, well-defined precedence mechanism — **not** an unresolvable fork under AC-R3-19 (two candidate producers that "cannot be disambiguated"); the tie-break is total and deterministic.
  **Empirical verification this round (2026-08-15):** `market_cache/{price_valuation_daily,monthly_revenue}` on this machine hold data starting **2026-06-01 / 2026-07-14** at the earliest (directly enumerated, `ls` sorted). The study's 255 canonical `as_of` dates (per P0-R2's frozen `a_leg_parity_result.json::per_date`, §0's read-only input) run **2005-01-31 → 2026-03-31** — entirely before the collector snapshot's earliest date. **Conclusion: for every one of the 255 canonical months, the collector-snapshot layer contributes zero rows; the effective raw source for `price`/`per`/`revenue` (2019+ portion) is `tej_cache` alone**, verified by direct file inspection, not by code reading alone.
  **This finding is contingent on `market_cache`'s content as observed today and MUST be re-verified at any future Phase C snapshot attempt** (the collector directory grows daily and is out of this study's control).

- **§1.2.2 — Uncommitted working-tree divergence (disclosed, not part of the frozen evidence basis; AC-R3-30).**
  The **live working-tree** copies of `core/data_provider.py` and `tej_importer.py` differ substantially from the git-committed baseline (`git.exe status --short` reports both `M`; `git.exe diff --stat` shows 69 and 2272 changed lines respectively). The working-tree `data_provider.py` adds a **third** merge layer, `TEJ_RUNTIME_OVERLAY_DIR` (default `data/runtime_cache/dataexport0806/{dataset}.parquet`), inside `_read_tej()`; the working-tree `tej_importer.py` is an almost-total rewrite (434 → 2156 lines) documenting a new "DataExport0806" TEJ batch source.
  **This mechanism does NOT exist in the durable, committed baseline** (`git show HEAD:core/data_provider.py` has a plain `@staticmethod _read_tej` with no overlay; confirmed by direct diff). Per §5, a gate's evidence may not rest on a file lacking durable identity — this study's Gate R3-L record is therefore **anchored to the committed baseline**, under which no overlay layer exists at all for the runtime scoring chain.
  For completeness: even if the overlay mechanism *were* committed, `data/runtime_cache/dataexport0806/receipt.json` (read this round) records its content as `financial_statements: date_min=date_max=2026-06-01` (596 stocks) and `monthly_revenue: date_min=date_max=2026-07-01` (406 stocks) — both single-month snapshots strictly after the study's 2026-03-31 cutoff, i.e. **also empirically inert for the 255-month target**, for the same reason as §1.2.1.
  **Disclosed as a monitoring item, not a blocking finding:** should this working-tree change ever be committed, Gate R3-L's A-leg record for `price`/`revenue`/`income`/`balance`/`cashflow` (financial_statements now also reachable via the overlay path, per the uncommitted `_read_tej`) would need re-tracing.

- **Cutoff/publication semantics, per raw dataset (A-leg):**
  - `price_valuation`, `institutional_flow`: same-day observable, `genuine_field`, no lag.
  - `monthly_revenue`: **mixed.** `core.backtest._pit_revenue` (`core/backtest.py:150-194`) uses the dataset's own `release_date` column where present (`genuine_field`, confirmed present for rows with non-null values); falls back to `month + MonthBegin(1) + 9 days` (statutory-deadline approximation) where `release_date` is null. Empirically (§2), `release_date` is present with real values for essentially all rows from 2019-01 (per `tej_importer.py`'s own — currently uncommitted — documentation, "TEJ monthly_revenue 有逐筆營收發布日 (2019-01起)"; 8 of 1952 per-stock files have an **all-null** `release_date` column, forcing 100% fallback for those specific stocks — a schema-drift finding, §2.4). Per AC-R3-7, a dataset with only *partial* genuine coverage across the reconstruction span is recorded `fixed_offset_proxy` for qualification-track purposes (the un-cured portion is exactly what AC-R3-7 item 1 targets) — **moot here regardless, since `monthly_revenue`'s own structural coverage already fails Gate R3-S, §2.**
  - `financial_statements`: `core.backtest._published()` (`core/backtest.py:479-483`) applies a single fixed lag, `PUBLISH_LAG_DAYS = 45` (`core/backtest.py:58`), to every quarter uniformly — `fixed_offset_proxy`. The raw dataset **now contains** a genuine per-row disclosure date (`財報發布日`/`release_date`, per `tej_importer.py`'s current docstring, added in the 2026-08-06 TEJ re-export) but it is **not read** by `core.tej_bundle._to_long()` (only `date`/`type`/`value`/`origin_name` survive the wide→long reshape) — per AC-R3-7 item 1, this does not cure the classification; the absence of *consumption* by the actual producing chain is what governs, not the field's mere existence upstream. This dataset also inherits the same Q4-specific under-estimate already documented for the unrelated B-leg pipeline (`scripts/build_research_base.py`'s own 2026-07-29 audit note, §3.3 of the prereg): a single 45-day constant is short for Q4 (true legal deadline is the following 3/31, not ≈2/14) — independently confirmed here as the same numeric mechanism (`PUBLISH_LAG_DAYS=45`) applied without quarter-specific adjustment in `core/backtest.py::_published`.
  - `institutional_gross` (shareholding `ForeignInvestmentSharesRatio`), `tdcc_weekly` (shareholding `NumberOfSharesIssued`): `core.tej_bundle._tej_shareholding()` applies **no PIT lag at all** — the raw `date` column is treated as immediately knowable, and `build_pit_stockdata` only `_slice`s to `date ≤ as_of` then takes `.iloc[-1]`. **Neither dataset has confirmed genuine per-row publication/availability evidence backing this zero-lag treatment** — no disclosure-date field was found for either (contrast with `monthly_revenue`'s genuine `release_date`), and `scripts/alpha_gate_lab.py`'s own, separate consumption of the *same* `tdcc_weekly` dataset applies an explicit `TDCC_LAG_DAYS=4` for a different (non-target) field — itself evidence against treating the A-leg's zero-lag reading as safely PIT-correct. **Classification: `unresolved` / `fixed_offset_proxy` (offset = 0, unverified) for both `institutional_gross` and `tdcc_weekly` — Gate R3-P FAILs for both in the qualification track (§3), independently of and in addition to their Gate R3-S coverage FAIL (§2).** *(Correction: an earlier draft of this document described these two datasets as simultaneously "unverified-optimistic" and `genuine_field`-PASS-eligible — a self-contradictory pairing. The classification is now singular and unconditional.)*

- **Code hashes (git-committed blob content):**
  `beat_0050/realbody/build_realbody_scores.py` `1b9ff09dbad344a400fa4eb8456c8ef5b2ffdd16fe6a8d10637f85c02327249f`; `beat_0050/realbody/bt_bundle.py` `fa9beb0f91f3896293c000262e7b85e12a49e78059575b4ff551f121faa5535f`; `core/tej_bundle.py` `adf98b4a8731eff832722ad74a0e361cbb2e6f7cf4558ee477d9640df646b9a0`; `core/backtest.py` `3b0f8e9ebe97ffd1e184a4fec0a4cbdc1b8af15d47fa3974a167fac9802d3fb2`; `core/score_store.py` `58de00f76481ea1ce13fd6fa2f946ac0b2f3dae641e1d80f9b56319345bc7874`; `core/data_provider.py` (**committed** content) `a2fb806f638b5c8f5b7c238c35edbde7cda532d7fb2d3dacaac9f5c5eb681224` (git blob `fd197dc4804b4284628892dab454b5ef63b8c269`) — **working-tree copy differs, see §1.2.2, not used as evidence.**
- **Git state:** `build_realbody_scores.py`, `bt_bundle.py`, `tej_bundle.py`, `backtest.py`, `score_store.py` clean under Windows Git. `core/data_provider.py` **`M` (modified, uncommitted)** — durable identity for Gate R3-L purposes rests on the committed blob above, not the working-tree file (§5).
- **Verdict:** `TRACED`, unambiguous, anchored to the committed baseline. §1.2.1's collector-merge and §1.2.2's uncommitted-overlay layers are both fully documented and empirically confirmed inert for this study's 255-month target as of 2026-08-15 — flagged for mandatory re-verification at any future Phase C attempt.

### 1.3 Field 3 — `value_ind`

- **Producing callable chain:** `scripts/tej_universe_screen_validation.py::build_observations()` (Stage 1, computes `value`) → `scripts/alpha_gate_lab.py::build()` (Stage 2, computes `value_ind`) → `obs_alpha.parquet::value_ind`.
- **Raw dataset family:** TEJ `price_valuation` (`PER_TEJ` column) + TEJ `industry_map.parquet` (static).
- **Transformation formula (verbatim):**
  - `value` (`tej_universe_screen_validation.py:200-207`): `hist = per-stock PER_TEJ history up to and including i0, dropna, >0`; requires `len(hist) >= 60`; `value = 100 - 100*mean(hist < cur_pe)`.
  - `value_ind` (`alpha_gate_lab.py:117-125`): `ind = industry_map[["stock_id","tej_ind_name"]]`; `vind = groupby(["as_of","tej_ind_name"])["value"].rank(pct=True)*100`; `size = group size`; `mkt = groupby("as_of")["value"].rank(pct=True)*100`; `value_ind = vind if size>=5 else mkt`. Uses **pandas `.rank(pct=True)`** (average-rank tie handling) — this is the raw-factor-construction step and is distinct from the oracle's own final top-20% tie-break (`core/canonical_universe.py`'s stable-sort `pct()`), which operates on `value_ind` as an already-computed input, not on `value`.
- **Cutoff/publication semantics:** same-day cross-sectional (both `value` and `value_ind`), `genuine_field`, no lag.
- **Known non-classic risk (reconfirmed):** `tej_ind_name` (from `industry_map.parquet`) is a **current-snapshot** industry classification with no historical versioning — applied retroactively across all history. Real, author-acknowledged (`scripts/build_research_base.py`'s own field-dictionary note #20), not a lag/proxy issue, does not fit the `genuine_field`/`fixed_offset_proxy` binary cleanly; recorded as a separate disclosed risk per §7.4.
- **Code hashes:** `scripts/tej_universe_screen_validation.py` `9405b18ce27376381370268ccf85c06bd65c29be894b171bb87093de34d921da`; `scripts/alpha_gate_lab.py` `be2f3dd8544034af69710a9b3a35e1d92ede8b7ce5fded8bd54c8898b4317e2a`.
- **Verdict:** `TRACED`, unambiguous.

### 1.4 Field 4 — `revenue_yoy` (B-leg)

- **Producing callable chain:** `scripts/tej_universe_screen_validation.py::load_market()` + `attach_pit_fundamentals()` (Stage 1) → `obs_alpha.parquet::revenue_yoy` (Stage 2 does not recompute; only derives `rev_accel = revenue_yoy - rev_yoy_3m`).
- **Raw dataset:** TEJ `revenue_growth` **only** — `SELECT stock_id, date, revenue_yoy_pct FROM read_parquet('{cache}/revenue_growth/*.parquet', union_by_name=true)` (`tej_universe_screen_validation.py:81-85`). No `release_date`/disclosure-date column is requested or exists in this dataset.
- **Transformation formula (verbatim, `tej_universe_screen_validation.py:92-93,112-140`):** `known_date = to_datetime(date) + MonthEnd(0) + Timedelta(days=10)` (`MONTHLY_ANNOUNCE_LAG_DAYS=10`); `pd.merge_asof(price_dates, revenue.sort_values("known_date"), direction="backward")`.
- **Cutoff/publication semantics:** `fixed_offset_proxy`, **unconditional** — confirmed authoritatively (not just inferred) via `tej_importer.py`'s own current docstring: `revenue_growth (... 已被 monthly_revenue 取代): 單月營收成長率(YoY,非合併)。範圍從舊版的2004起(但只有成長率，無公告日)延續` — "only the growth rate, **no announcement date**". Per AC-R3-7, `cutoff_semantics.kind = "fixed_offset_proxy"` and **Gate R3-P FAILs for this dataset in the qualification track, unconditionally.**
- **Code hashes:** same as §1.3.
- **Verdict:** `TRACED`, unambiguous. (Lineage is unambiguous; the PIT classification is a separate Gate R3-P FAIL, §3.)

### 1.5 Field 5 — `high52_prox`

- **Producing callable chain:** `scripts/tej_universe_screen_validation.py::build_observations()` (Stage 1) → `obs_alpha.parquet` (Stage 2 passthrough, no recompute).
- **Raw dataset:** TEJ `price_valuation` (`close`).
- **Transformation formula (verbatim, `tej_universe_screen_validation.py:165-166,197-198`):** `g["_roll_max240"] = g["close"].rolling(240, min_periods=120).max()`; `high52_prox = close[i0] / _roll_max240[i0] * 100`.
- **Cutoff/publication semantics:** trailing, right-anchored rolling window, `genuine_field`, no lag.
- **Code hashes:** same as §1.3.
- **Verdict:** `TRACED`, unambiguous.

### 1.6 Field 6 — `momentum`

- **Producing callable chain:** same as §1.5.
- **Raw dataset:** TEJ `price_valuation` (`close`).
- **Transformation formula (verbatim, `tej_universe_screen_validation.py:182-188`):** `momentum = (close[i0] - close[i0-20]) / close[i0-20] * 100` (`i0 >= momentum_window=20` required).
- **Cutoff/publication semantics:** trailing, `genuine_field`, no lag.
- **Verdict:** `TRACED`, unambiguous.

### 1.7 Gate R3-L verdict: **PASS — scoped strictly to the approved committed baseline**

**Scope of this PASS:** all 6 fields have a complete, evidenced record with no unresolved ambiguity, **as traced against the approved repository baseline commit `497a03ee04d676aa44f5948dcfc69d9c8edd3ebf` and its docs-only descendant commits (current HEAD `b97d3160...`, which differs from `497a03ee...` only by 2 documentation commits, reconfirmed §7).** The apparent multi-layer complexity found in the A-leg's `price`/`per`/`revenue` chain (§1.2.1, §1.2.2) resolves to a single deterministic mechanism in every case, and both non-`tej_cache` layers are empirically confirmed to contribute zero rows within this study's 255-month target as observed 2026-08-15 (re-verification required before any future Phase C attempt).

**Explicit non-claim:** this PASS verdict does **not** evaluate, and must not be read as evaluating, the **current live working-tree** production lineage. `core/data_provider.py` and `tej_importer.py` carry substantial uncommitted changes (§1.2.2) that are excluded from this gate's evidence basis by construction (§5's durable-identity rule). The lineage of whatever code is *actually running in production right now*, if it differs from the committed baseline in a way that touches any of the 6 target fields, is **`NOT_EVALUATED`** by this Phase B round — a distinct, open question this document does not answer and does not claim to answer.

**D\* (Required Dataset Set), frozen — first freeze, not a "change" under AC-R3-25:**

```
D* = { price_valuation, revenue_growth, industry_map, monthly_revenue,
       financial_statements, institutional_flow, institutional_gross, tdcc_weekly }
```

8 datasets, all TEJ. Matches §3.4's preliminary reading exactly. `fundamentals_quarterly` and `director_pledge` — read by the shared `obs_dump_full.parquet`/`obs_alpha.parquet` build pipeline — are confirmed this round, by full field-dictionary trace, **not** to produce any of the 6 target fields (they feed `eps`/`roe`/`op_income`/`net_income`/`eps_pos_q4`/`pledge_pct`/etc., none of which are in scope) and are correctly excluded from D\*.

---

## 2. Gate R3-S — Source sufficiency

Metadata-only inspection (parquet footer/row-group statistics + full-column read of `date` for min/max; no parity, no membership, no performance computation), performed via `pyarrow` against the actual `~/tej_cache/*` corpus on this machine, 2026-08-15. Denominator: the frozen 255 canonical `as_of` dates from P0-R2's `a_leg_parity_result.json::per_date` (§0's read-only input), `2005-01-31 → 2026-03-31`.

| dataset | files | rows | date_min | date_max | schema | 255-month coverage | verdict |
|---|---:|---:|---|---|---|---|---|
| `price_valuation` | 2,300 | 9,009,907 | 2004-01-02 | 2026-07-14 | 1 uniform | full | **SUFFICIENT** |
| `revenue_growth` | 2,339 | 477,570 | 2004-01-01 | 2026-06-01 | 1 uniform | full | **SUFFICIENT** |
| `industry_map` | 1 (single file) | 2,436 | n/a (static, no date) | n/a | 1 | n/a (current snapshot) | **SUFFICIENT** (non-PIT retroactive-labeling risk disclosed, §1.3) |
| `institutional_flow` | 2,300 | 8,674,640 | 2004-01-02 | 2026-07-14 | 1 uniform | full | **SUFFICIENT** |
| `financial_statements` | 2,287 | 135,511 | 2005-06-01 | 2026-03-01 | **2 variants** (187/2287 files: `net_income`/`total_assets`/`total_liabilities`/`equity`/`operating_cash_flow`/`capex` typed `int64` instead of `double` — parquet type-inference artifact of all-integer-valued columns in those files) | near-full; possible Q1-2005 gap (first canonical `as_of`=2005-01-31, dataset's first structural row=2005-06-01) — **PIT-moot**: no Q1-2005 quarterly report would be legally publishable by 2005-01-31 regardless of dataset coverage | **INSUFFICIENT — Gate R3-S FAILS (schema-drift unresolved, AC-R3-2, §2.4)** |
| `monthly_revenue` | 1,952 | 168,885 | **2019-01-01** | 2026-06-01 | **2 variants** (8/1952 files: `release_date` typed `null` — all-null column, i.e. 100% fallback-proxy for those 8 stocks) | **INSUFFICIENT — 168/255 canonical months (2005-01-31 → 2018-12-28) have zero structural rows** | **INSUFFICIENT — Gate R3-S FAILS on two independent grounds: coverage (this column) and schema drift (AC-R3-2, §2.4)** |
| `institutional_gross` | 1,952 | 140,544 | **2026-04-01** | **2026-07-16** | 1 uniform | **INSUFFICIENT — 255/255 canonical months (all of 2005-01-31 → 2026-03-31) have zero structural rows; the entire on-disk range postdates the study's target window** | **INSUFFICIENT — Gate R3-S FAILS for this dataset** |
| `tdcc_weekly` | 1,942 | 664,226 | **2019-01-04** | 2026-07-09 | 1 uniform | **INSUFFICIENT — 168/255 canonical months (2005-01-31 → 2018-12-28) have zero structural rows** | **INSUFFICIENT — Gate R3-S FAILS for this dataset** |

### 2.1 `institutional_gross` — the decisive finding

Empirically confirmed by direct row-level inspection of 9 randomly-sampled per-stock files (not merely the aggregate metadata scan): every sampled file holds **exactly 72 rows, uniformly dated 2026-04-01 → 2026-07-16**. This flatly contradicts `tej_importer.py`'s own (currently uncommitted, §1.2.2) documentation, which claims this dataset "涵蓋回溯到2004-01-02，是實質擴大而不只是搬家" (coverage extends back to 2004-01-02). The narrow on-disk window matches that same docstring's description of the **old, pre-expansion** `inbox_chip_gross` seed window verbatim ("舊 inbox_chip_gross 只有 2026-04-01~07-16 這段「種子」窗口") — i.e. the actual `tej_cache/institutional_gross` directory has **not yet been re-populated** by whatever import run the new `tej_importer.py` docstring describes; the expansion is documented but not executed against this dataset. This is disclosed as-is; no attempt was made to reconcile or re-run the importer (out of Phase B's read-only scope).

### 2.2 `monthly_revenue` coverage gap

Confirmed by aggregate metadata scan (1,952 files) and an 8-file random sample (uniform `2019-01-01 → 2026-06-01`, 90 rows per stock for 7/8 sampled files). Directly affects A-leg `revenue` (§1.2): for any `as_of` before 2019-01, `core.backtest._pit_revenue(symbol, None)` has **zero** matching TEJ rows and no fallback (`fallback=None` passed by `tej_bundle.py`) — the `revenue` bundle field is empty for the entire pre-2019 span, and `build_pit_stockdata` degrades the revenue-dependent score components to their neutral defaults for those 168 months (confirmed non-crashing: `data/research_base/realbody_scores_adv100w.parquet::real_composite` has 100% non-null coverage even at `as_of=2005-01-31`, §6.2 — but the neutral-default values are not a genuine PIT reconstruction of 2005–2018 revenue trends).

### 2.3 `tdcc_weekly` coverage gap

Same 168-month gap pattern as `monthly_revenue`, structurally consistent with `tej_importer.py`'s own documentation ("tdcc_weekly...2019起(無變化)" — i.e. this one dataset's narrow start date IS accurately documented, unlike `monthly_revenue`/`institutional_gross`).

### 2.4 Schema-drift findings — independent Gate R3-S FAIL grounds (AC-R3-2, corrected this round)

`financial_statements`' `int64`-vs-`double` numeric-column variants (187/2287 files) and `monthly_revenue`'s `null`-vs-`string` `release_date` variant (8/1952 files) are **independent Gate R3-S FAIL grounds under AC-R3-2, not merely disclosed-but-moot observations.** Per round-4's AC-R3-2 rewrite, no "benign drift" self-judgment is permitted: a schema drift not pre-declared in an approved document is treated as unresolved — FAIL — until a human explicitly rules on it ("there is no self-judged 'benign drift' exception any longer"). Neither variant has been ruled on by the user or written into an approved errata document; both therefore stand as unresolved `SCHEMA_DRIFT_UNRESOLVED` failures:

- **`financial_statements`:** an earlier draft of this document incorrectly recorded `SUFFICIENT, schema-drift finding disclosed` — corrected here to **INSUFFICIENT / Gate R3-S FAIL**, reason `SCHEMA_DRIFT_UNRESOLVED`, independent of and in addition to `financial_statements`' existing Gate R3-P FAIL (§3).
- **`monthly_revenue`:** already failing Gate R3-S on coverage grounds (§2.2); the `release_date` type-drift is a **second, independent** FAIL ground for the same dataset, not merely a note carried alongside the coverage failure.

This correction does not change the round's overall disposition (both datasets already contributed to a decisive FAIL), but it changes how each dataset's FAIL is attributed and how many independent grounds exist — material to know which fixes would (or would not) be sufficient to reopen Gate R3-S for either dataset in a future round.

### 2.5 Duplicate-key integrity (AC-R3-3): **NOT_FULLY_EVALUATED**

**What was actually done:** a **single-file sample** — one stock (`1101`) — was checked for duplicate `(stock_id, date)` rows in 4 of the 8 D\* datasets (`price_valuation`, `revenue_growth`, `financial_statements`, `monthly_revenue`); zero duplicates found in that one file per dataset. `industry_map`, `institutional_flow`, `institutional_gross`, and `tdcc_weekly` were **not sampled at all** for duplicate keys.

**What this is not:** this is **not** a full-corpus duplicate-key sweep. It covers 1 file out of ~1,942–2,339 per dataset (well under 0.1% of the corpus for the 4 sampled datasets, 0% for the other 4), and cannot support a per-dataset `SUFFICIENT`/`INSUFFICIENT` duplicate-key verdict under AC-R3-3's own standard (which requires either a demonstrated legitimate multi-row structure or an explicit deterministic tie-break rule, written into this document, for the *dataset as a whole* — not a one-file spot-check).

**Disposition:** since Gate R3-S already has decisive, independently-established FAIL grounds (§2.1–§2.4: coverage insufficiency in 3 datasets, schema drift in 2 datasets), this study applies **fail-fast / short-circuit discipline**: duplicate-key integrity is recorded as `NOT_FULLY_EVALUATED` rather than completed to a `SUFFICIENT`/`INSUFFICIENT` verdict, and **no full-corpus duplicate-key sweep was performed or is being requested this round** — it would not change this round's disposition (Gate R3-S already FAILs on other grounds) and running an expensive full-corpus scan before knowing whether a future re-attempt will even reach this check as a live blocker is disproportionate. If Gate R3-S's coverage/schema-drift failures are ever cured in a future round, duplicate-key integrity must be completed in full (all files, all 8 datasets) before Gate R3-S may be scored `SUFFICIENT`.

**This document does not claim, and must not be read as claiming, that Gate R3-S's full eligibility-check surface (schema, coverage, revision policy, duplicate-key policy, missingness rules, PIT cutoff type, per §6/FR-R3-3 of the prereg) has been completed for every D\* dataset.** Coverage and schema-drift checks were completed (§2.1–§2.4, decisive); duplicate-key integrity was not (this section); revision-policy checks were not attempted at all this round, out of scope given the fail-fast disposition.

### 2.6 Gate R3-S verdict: **FAIL**

**4 of 8** D\* datasets fail, on two independent reason categories:

- **`COVERAGE_INSUFFICIENT`** (255-month coverage requirement, NFR-R3-2/AC-R3-5/AC-R3-29 — "0 missing required months... no general/blanket waiver"): `monthly_revenue`, `institutional_gross`, `tdcc_weekly`.
- **`SCHEMA_DRIFT_UNRESOLVED`** (AC-R3-2, §2.4): `financial_statements` (corrected this round from an earlier, incorrect `SUFFICIENT` verdict), `monthly_revenue` (second, independent ground on top of its own coverage FAIL).

All four are A-leg-only inputs (shareholding, pre-2019 revenue, and quarterly financials); none of the 4 B-leg target fields or the decision-time universe depend on them. **Gate R3-S is scored per §7.0 as a study-level gate; a FAIL on any D\* dataset blocks Phase C admission for any content depending on that dataset (AC-R3-1)** — here, A-leg `real_composite` specifically.

**Additionally**, per §2.7, none of the 8 D\* datasets have an established durable corpus identity (NFR-R3-3) this round — `DURABLE_IDENTITY_NOT_ESTABLISHED` is recorded as a further, independent reason attaching to this gate's FAIL, separate from the coverage/schema findings above.

**Not completed this round: duplicate-key integrity, `NOT_FULLY_EVALUATED`** (§2.5 — fail-fast/short-circuit; no full-corpus sweep performed or needed).

### 2.7 Durable identity of D\* datasets (NFR-R3-3): **NOT ESTABLISHED this round**

Per §5's rule, a dataset's identity is durably frozen only if it is a reachable committed blob or an independent byte copy exists outside `.git/objects` together with SHA256 + byte count + a documented, reproducible verify command. **None of the 8 D\* datasets received either treatment this round.** `~/tej_cache/*` is not a git-tracked corpus at all (it lives outside the repository, per `core/tej_bundle.py`'s own `TEJ_CACHE_DIR` resolution), and this Phase B round deliberately made **no byte copy** of any dataset file — Phase C (data snapshot creation) is not authorized this round, and a byte-copy-for-durability action would itself have the shape of a (partial) Phase C snapshot, which this round's scope explicitly excludes.

**Consequence:** every coverage/schema finding in §2 (row counts, date ranges, schema-variant counts) is an **observed-current-corpus finding**, valid and sufficient to support this round's FAIL determination (the corpus as it exists right now genuinely lacks the required coverage/schema uniformity — that fact does not depend on the corpus being durably frozen to be true today), but it is **not** a claim that this evidence is reproducible or stable over time. `~/tej_cache/*` is a live, externally-managed directory (per §2.1's own finding that `institutional_gross`'s content does not match its own importer's documentation, this corpus is demonstrably subject to out-of-band, partially-applied changes) and could differ at the next inspection. **This document records what was observed on 2026-08-15 and does not assert a frozen, NFR-R3-3-compliant corpus identity for any D\* dataset.** Should Gate R3-S ever be re-attempted, establishing durable identity (real byte copies, not merely re-running this same metadata scan) is itself a Phase C-shaped action requiring its own authorization, and is a precondition — not a formality — for any future `SUFFICIENT` verdict.

`DURABLE_IDENTITY_NOT_ESTABLISHED` is recorded against both Gate R3-S and Gate R3-P (§3.1) for this reason.

---

## 3. Gate R3-P — PIT/announcement-date validity

| dataset | genuine per-row evidence? | `cutoff_semantics.kind` | qualification-track verdict |
|---|---|---|---|
| `price_valuation` | same-day observable | `genuine_field` | PASS |
| `institutional_flow` | same-day observable | `genuine_field` | PASS |
| `industry_map` | static, no cutoff; separate retroactive-labeling risk (§1.3) | n/a | PASS w/ disclosed non-classic risk |
| `revenue_growth` | **none** (confirmed, `tej_importer.py`: "無公告日") | `fixed_offset_proxy` | **FAIL (AC-R3-7, unconditional)** |
| `monthly_revenue` | genuine 2019-01+ (partial; 8/1952 files 100% fallback), proxy fallback elsewhere | `fixed_offset_proxy` (partial-coverage does not cure, AC-R3-7 item 1) | **FAIL (AC-R3-7)** — moot, already fails Gate R3-S |
| `financial_statements` | genuine field now exists in raw dataset but is **not consumed** by the producing chain (45-day fixed lag applied instead) | `fixed_offset_proxy` | **FAIL (AC-R3-7, unconditional — "not curable by disclosure quality")** |
| `institutional_gross` | **not confirmed** — zero PIT lag applied without verified evidence that the raw `date` is genuinely same-day-public (§1.2; corrected this round from an earlier, self-contradictory `genuine_field`/PASS classification) | `unresolved` / `fixed_offset_proxy` (offset=0, unverified) | **FAIL** — no confirmed genuine per-row availability evidence; independent of, and in addition to, its Gate R3-S coverage FAIL |
| `tdcc_weekly` | **not confirmed** — zero lag applied by A-leg's consumption path; a separate consumer of the same dataset (`alpha_gate_lab.py`, non-target field) applies a 4-day lag, itself evidence against treating zero-lag as safe | `unresolved` / `fixed_offset_proxy` (offset=0, unverified) | **FAIL** — corrected this round from `NEEDS ADJUDICATION`; independent of, and in addition to, its Gate R3-S coverage FAIL |

### 3.1 Gate R3-P verdict: **FAIL**

**5 of 8** D\* datasets fail: `revenue_growth` (feeds B-leg `revenue_yoy` directly), `monthly_revenue`, `financial_statements`, `institutional_gross`, and `tdcc_weekly` (the latter four all feed A-leg `real_composite`) are all classified `fixed_offset_proxy` or `unresolved`/`fixed_offset_proxy` with no genuine per-row evidence actually consumed by, or verified for, the producing chain, per AC-R3-7's unconditional rule. **Correction this round:** an earlier draft classified `institutional_gross` as `genuine_field`/PASS while, elsewhere in the same document, describing it as "potentially unverified-optimistic" — a self-contradictory pairing. Both `institutional_gross` and `tdcc_weekly` are now classified singularly as `unresolved`/`fixed_offset_proxy` and FAIL, consistent with `revenue_growth`/`monthly_revenue`/`financial_statements`'s treatment.

This is a **second, independent** reason (alongside §2's coverage failure) blocking A-leg from Phase C admission on 4 of its 5 non-`price_valuation`/`institutional_flow` raw datasets (`monthly_revenue`, `financial_statements`, `institutional_gross`, `tdcc_weekly`), and the **sole** reason blocking the B-leg `revenue_yoy` field specifically (which has full structural coverage, §2, but fails on PIT-evidence grounds alone). **Additionally, per §2.7, `DURABLE_IDENTITY_NOT_ESTABLISHED` applies to this gate's evidence as well** — the dataset-level PIT classifications above rest on the same non-durable, observed-current-corpus basis as Gate R3-S's findings.

---

## 4. §8 per-leg formula/code-identity freeze

Per the prereg's §8 binding rule and §11 Phase B step 3. All five legs frozen to the 9-point record; **frozen as of git-committed baseline `b97d3160...`, code hashes as listed in §1.**

### 4.1 A-leg (`real_composite`)

1. **Callable chain:** `build_realbody_scores.py::main()` → `bt_bundle.bt_fetch_history()` → `tej_bundle.tej_fetch_history()` → `score_store.score_row()` → `backtest.build_pit_stockdata()` → `FundamentalEngine.evaluate` + `ValuationEngine.evaluate` + `ScoringManager.calculate_score` + `InvestmentAdvisor.advise` → `.total_score`.
2. **Code SHA256:** §1.2's table (5 files, all committed/clean).
3. **Input fields:** per §1.2's `HistoryBundle` table — `price`(open/max/min/close/Trading_Volume), `per`(PER_TSE→PER/PBR_TSE→PBR/dividend_yield_TSE→dividend_yield), `revenue`(revenue/revenue_year/revenue_month), `income`/`balance`/`cashflow`(long-format, English `type` keys per `_INCOME_MAP`/`_BALANCE_MAP`/`_CASHFLOW_MAP`, `core/tej_bundle.py:112-129`), `chip`(date/name/buy/sell), `shareholding`(NumberOfSharesIssued/ForeignInvestmentSharesRatio).
4. **Constants:** `_PCT_HISTORY_START` = `"2019-01-01"` (`core/tej_bundle.py:93`), **overridden to `"2004-01-01"` by `bt_bundle.py:27`, process-local, at import time**; `PUBLISH_LAG_DAYS = 45` (`core/backtest.py:58`); `MONTHLY_ANNOUNCE_LAG_DAYS` not applicable to this leg (A-leg revenue uses `_pit_revenue`'s own `+9 days` fallback constant, hard-coded at `core/backtest.py:175`, not a named module constant).
5. **Window/lookback:** PE/PB percentile window restricted to `date >= _PCT_HISTORY_START` (2004-01-01 for this build); no other rolling window in the A-leg chain itself (rolling windows for technical sub-scores live inside `TechnicalEngine`, out of this study's 6-field scope).
6. **Merge/join key + direction:** `_pit_revenue`: `merge` is implicit via `known_date` cutoff + `.iloc[-1]`-style latest-published selection inside `build_pit_stockdata`'s `_slice`; no explicit `merge_asof` in the A-leg revenue path (contrast with B-leg, §4.3–4.5, which does use `merge_asof`). `_published()` financial-statement filter: boolean mask, not a merge.
7. **Industry/cross-sectional fallback:** not applicable — A-leg has no cross-sectional/industry-relative step.
8. **NaN/tie/ranking semantics:** not applicable at this leg's own level (A-leg produces a single scalar `total_score` per stock-date; ranking happens only in the shared oracle's `dual_confirm_mask`, §8's "reused verbatim" clause).
9. **Formula:** `real_composite = InvestmentAdvisor.advise(ScoringManager.calculate_score(FundamentalEngine.evaluate(...), ValuationEngine.evaluate(...), ...)).total_score` — the internal engine math is out of this study's 6-field lineage scope (§7.1 targets the *raw dataset family and cutoff semantics* feeding the score, not the scoring formula's internal weights, which are unchanged, frozen, out-of-scope production code per §1's non-claims).

**Freeze status:** COMPLETE for items 1–4, 6–9. Item 5 (window) is thin (only the PE/PB history-start constant is a real "window" parameter at this leg's boundary). **Gate R3-P for this leg's `revenue`/`income`/`balance`/`cashflow`/`shareholding` inputs: FAIL (§3)** — the freeze record itself is complete, but the leg cannot proceed to Phase C regardless (§7.0).

### 4.2 Decision-time universe (`listed_ok`, `adv20`) — not a "leg" but frozen alongside per §8

1. **Callable chain:** `scripts/alpha_gate_lab.py::build()`, DuckDB SQL (§1.1).
2. **Code SHA256:** `alpha_gate_lab.py`, `lab_paths.py` (§1.1).
3. **Input fields:** `price_valuation.close`, `.Trading_Volume`, `.date`, `.stock_id`.
4. **Constants:** grandfather-clause cutoff `"2004-01-15"`; listing-age threshold `365` days.
5. **Window:** 20-row trailing DuckDB frame (`ROWS BETWEEN 19 PRECEDING AND CURRENT ROW`).
6. **Merge/join:** left-merge of `liq[["stock_id","date","adv20","listed_ok"]]` onto `obs` on `(stock_id, as_of)=(stock_id, date)` (`alpha_gate_lab.py:113-115`).
7. **Fallback:** not applicable.
8. **NaN/tie:** not applicable (boolean/numeric, no ranking at this step).
9. **Formula:** §1.1.

**Freeze status:** COMPLETE.

### 4.3 B-leg `value_ind`

1. **Callable chain:** §1.3.
2. **Code SHA256:** `tej_universe_screen_validation.py`, `alpha_gate_lab.py` (§1.3).
3. **Input fields:** `price_valuation.PER_TEJ`, `industry_map.tej_ind_name`.
4. **Constants:** `MIN_PCT_SAMPLES = 60` (`tej_universe_screen_validation.py:53`); industry-fallback threshold `size >= 5` (`alpha_gate_lab.py:125`).
5. **Window:** expanding, per-stock, from data start to `i0` inclusive (own-history PE percentile) — not a fixed-length rolling window.
6. **Merge/join key + direction:** `industry_map` merged on `stock_id` only (static, no date dimension) (`alpha_gate_lab.py:118-119`).
7. **Industry fallback rule:** exact, §1.3 (`vind.where(size>=5, mkt)`).
8. **NaN/tie/ranking semantics:** `pandas.DataFrame.groupby(...).rank(pct=True)` — pandas' **default** tie-break (`method="average"`), NOT `core/canonical_universe.py`'s stable-sort convention. This applies only to the *raw factor construction* of `value_ind` itself; the oracle's own final top-20%/percentile step over `value_ind` (among the 4 B-legs) is a separate, later operation that does use the stable-sort convention (§8's "reused verbatim" clause, unaffected).
9. **Formula:** §1.3, verbatim.

**Freeze status:** COMPLETE. **Gate R3-P: PASS** for this leg's own input (`price_valuation`+`industry_map`, both `genuine_field`).

### 4.4 B-leg `revenue_yoy`

1. **Callable chain:** §1.4.
2. **Code SHA256:** `tej_universe_screen_validation.py` (§1.4).
3. **Input fields:** `revenue_growth.revenue_yoy_pct`, `.date`.
4. **Constants:** `MONTHLY_ANNOUNCE_LAG_DAYS = 10` (`tej_universe_screen_validation.py:58`).
5. **Window:** none (point value per known-date).
6. **Merge/join key + direction:** `pd.merge_asof(price_dates, revenue.sort_values("known_date"), left_on="_dt", right_on="known_date", direction="backward")` (`tej_universe_screen_validation.py:121`).
7. **Fallback:** not applicable.
8. **NaN/tie:** `merge_asof` backward-nearest; no tie scenario (single time series per stock).
9. **Formula:** §1.4, verbatim.

**Freeze status:** COMPLETE. **Gate R3-P: FAIL (§3)** — `fixed_offset_proxy`, unconditional.

### 4.5 B-leg `high52_prox`

1. **Callable chain:** §1.5.
2. **Code SHA256:** `tej_universe_screen_validation.py`.
3. **Input fields:** `price_valuation.close`, `.date`.
4. **Constants:** window length `240`, `min_periods=120`.
5. **Window:** `g["close"].rolling(240, min_periods=120).max()`, right-anchored (includes current row).
6. **Merge/join:** none (single-series rolling).
7. **Fallback:** none.
8. **NaN:** `None` when `hi` is `NaN` or falsy (`tej_universe_screen_validation.py:198`).
9. **Formula:** §1.5, verbatim.

**Freeze status:** COMPLETE. **Gate R3-P: PASS.**

### 4.6 B-leg `momentum`

1. **Callable chain:** §1.6.
2. **Code SHA256:** `tej_universe_screen_validation.py`.
3. **Input fields:** `price_valuation.close`, `.date`.
4. **Constants:** `momentum_window = 20` (trading days).
5. **Window:** fixed 20-row lookback, `i0 - momentum_window`.
6. **Merge/join:** none.
7. **Fallback:** none; `continue` (row dropped) if `i0 < momentum_window` or price missing.
8. **NaN:** row-drop, not NaN-fill.
9. **Formula:** §1.6, verbatim.

**Freeze status:** COMPLETE. **Gate R3-P: PASS.**

---

## 5. Gate verdicts summary

| Gate | Status | Scored in |
|---|---|---|
| R3-L | **PASS** (scoped to approved committed baseline; live working tree `NOT_EVALUATED`, §1.7) | Phase B (this document) |
| R3-S | **FAIL** — coverage: `monthly_revenue`, `institutional_gross`, `tdcc_weekly` (§2.1–2.3); schema drift: `financial_statements`, `monthly_revenue` (§2.4); durable identity not established for any D\* dataset (§2.7); duplicate-key integrity `NOT_FULLY_EVALUATED` (§2.5) | Phase B |
| R3-P | **FAIL** — `revenue_growth`, `monthly_revenue`, `financial_statements`, `institutional_gross`, `tdcc_weekly` (`fixed_offset_proxy`/`unresolved`, §3); durable identity not established (§2.7) | Phase B |
| R3-F, R3-U, R3-B, R3-Q, R3-I, R3-N | `NOT_EVALUATED` | — (Phase C blocked, §6.1) |

## 6. Disposition (§7.0 / AC-R3-23)

### 6.1 Phase C does not proceed.

Per the prereg's §7.0 admission rule ("Phase C may begin only if all three... Gate R3-S PASSes... Gate R3-P PASSes") and AC-R3-23 ("Given Gate R3-S or Gate R3-P FAILs in Phase B... Phase C does not proceed; the study files a null/blocked result naming the failed gate and dataset/field, with no snapshot, no qualification claim, and no further phase"):

- **Failed gate(s):** Gate R3-S, Gate R3-P.
- **Failed datasets:** `monthly_revenue` (R3-S coverage + R3-S schema drift + R3-P), `institutional_gross` (R3-S coverage + R3-P), `tdcc_weekly` (R3-S coverage + R3-P), `financial_statements` (R3-S schema drift + R3-P), `revenue_growth` (R3-P). **All 5 non-`price_valuation`/`industry_map`/`institutional_flow` D\* datasets fail at least one gate.** Additionally, `DURABLE_IDENTITY_NOT_ESTABLISHED` (§2.7) applies across all 8 D\* datasets on both gates, and duplicate-key integrity is `NOT_FULLY_EVALUATED` (§2.5).
- **Affected fields:** A-leg `real_composite` (blocked on grounds spanning all 4 of its non-`price_valuation`/`institutional_flow` raw datasets: `monthly_revenue` coverage+schema+PIT, `institutional_gross` coverage+PIT, `tdcc_weekly` coverage+PIT, `financial_statements` schema+PIT); B-leg `revenue_yoy` (blocked on 1 ground: `revenue_growth` PIT). Decision-time universe (`listed_ok`/`adv20`) and B-legs `value_ind`/`high52_prox`/`momentum` have **no** failing dependency of their own (all three of their PASS-verdict datasets are `price_valuation`/`revenue_growth`(lineage only)/`industry_map`) — but per AC-R3-24, **the five legs are qualified as one unit; Phase C does not proceed for any leg while any one leg's dependency fails.**
- **No snapshot, no qualification claim, no adapter, no tests, and no further phase attempted this round**, consistent with this round's user-scoped authorization.
- **The sole permitted continuation** is a separately, explicitly approved `DIAGNOSTIC_ONLY — NOT QUALIFICATION-ELIGIBLE` snapshot (§7.0) — not requested, not authorized, not built this round.

### 6.2 Sanity cross-check performed (read-only, no computation)

`data/research_base/realbody_scores_adv100w.parquet::real_composite` (the existing A-leg output, built 2026-07-30, predating this study) was read (metadata + `as_of`/`stock_id`/`real_composite` columns only) to confirm the coverage-gap finding does not silently crash or null out the panel: **100% non-null `real_composite` at every sampled `as_of`, including 2005-01-31 (737/737 stocks)** — confirming the neutral-default degradation mechanism (`tej_bundle.py`'s own docstring: "缺任一資料集 → 該欄回 None；build_pit 對缺欄有中性預設") produces full-population output even where genuine historical revenue/shareholding data does not exist, which is precisely why this gap was not previously visible to a parity-only check (P0-R2's Gate C-R oracle-vs-adapter parity, §0, would reproduce the same degraded values on both sides and PASS, since both sides run the identical, equally-degraded computation).

### 6.3 What this Phase B round did **not** do (explicit, per user scope)

No `SnapshotManifest`, no byte copy of any `tej_cache` dataset file, no test file, no adapter code, no parity/membership/raw-score computation, no write to `~/tej_cache`, `market_cache`, `data/runtime_cache`, or any production/cache/Scheduler path. The `pyarrow` tool installation (§0 header) touched only a session-local scratchpad directory outside the repository.

---

## 7. Durable-identity ledger (§5)

All committed-baseline code hashes above were independently recomputed this round (`sha256sum` on the working tree for clean files; `git show HEAD:<path> | sha256sum` for `core/data_provider.py`/`tej_importer.py`, whose working-tree copies are uncommitted) and Windows-Git-scoped status was re-run (`git.exe status --short`, `git.exe diff --stat 497a03ee04d676aa44f5948dcfc69d9c8edd3ebf..HEAD`) to reconfirm the prereg's own §4 finding: all lineage-relevant files except `core/data_provider.py` and `tej_importer.py` are clean and byte-identical between the prereg's approved baseline (`497a03ee...`) and current HEAD (`b97d3160...`, itself only 2 docs-only commits ahead). No new commit was made by this round; no file was staged.

**Code vs. data-corpus identity — not the same claim.** The paragraph above establishes durable identity for **code** evidence only (git-committed blobs). It does **not** extend to the **D\* dataset corpus** (`~/tej_cache/*`), which per §2.7 has **no** durable identity established this round — no byte copy, no NFR-R3-3-compliant frozen corpus reference. Readers must not infer data-corpus durability from this section's code-hash confirmation.
