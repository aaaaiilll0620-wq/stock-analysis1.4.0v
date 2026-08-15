# P0-R4 — Historical Raw-Source Remediation, PIT Semantics, and Live Identity Resolution

**Status: APPROVED — Phase A (document) approved; Phase B (read-only) authorized. Phase C+ and all production/cache/Scheduler writes remain unauthorized (§15).**
**Study code:** P0-R4
**Author:** Claude, per user instruction 2026-08-16 (initial draft — document-only prereg, three-track specification: A/Historical-oracle reconstruction, B/PIT-correct successor dataset, C/Current live identity)
**Approval event:** Phase A approved by user instruction, 2026-08-16, of the round-3 revision unchanged (approved draft SHA256 recorded in §15). This approval authorizes Phase B (read-only diagnosis, §11, per-track gates R4-L/R4-A/R4-V/R4-H/R4-P/R4-S/R4-D-existence-check/R4-X-continuous) only; it does not authorize any Phase C+ action (§15, §12).
**User approval:** APPROVED — 2026-08-16 (full scope in §15; external receipt at `docs/prereg_P0_R4_approval_receipt_2026-08-16.json`)
**Implementation authorized:** NO — Phase B is read-only diagnosis, not implementation; no download, login/paid-service access, data import/backfill, byte copy (of any kind — code or data, created or copied), snapshot, code modification, test, or production/Scheduler operation is authorized by this approval (§15)
**Drafting scope this round:** prereg document only, document-only drafting. No Phase B, no diagnosis, no download, no import, no backfill, no transform, no snapshot, no code, no tests, no adapter, no production/cache/Scheduler modification, no staging, no commit. Nothing beyond this single new file was created or modified this round.
**Round 2 correction:** (1) removed Phase B's code-byte-copy exception entirely — Phase B is now unconditionally read-only for both code and data, modified/untracked files record path/SHA256/bytes/git state only, durable identity `NOT_ESTABLISHED` (§8, §11, AC-R4-17, AC-R4-35); (2) replaced the single blurred `R4-L,R4-A → R4-V,H,P,S → R4-D` graph with an explicit per-track dependency matrix — Track A `R4-A→R4-V→R4-D`, Track B `R4-A→{R4-H,R4-P,R4-S}→R4-D`, Track C `R4-L→R4-D`, R4-X continuous (§3, §10.0, §10.9, AC-R4-27/28/29); (3) clarified Gate R4-D as existence-check-only in Phase B (never creation), and added the binding asymmetry rule that observed-current-corpus evidence may support a FAIL but never a PASS — any PASS resting on evidence lacking durable identity is downgraded to FAIL (§5, §10.7, AC-R4-21/22/23); (4) added formal **AC-R4-36** (traceability-audit blocking rule) and remapped NFR-R4-6 to it (§13.10, §14.2, §14.4, §14.7); (5) added an explicit external-document access boundary for Phase B (§11.1).
**Round 3 correction (this revision):** (1) distinguished "Phase B **creates** a byte copy" (still, and forever, prohibited in Phase B) from "Phase B **read-only verifies** a byte copy that already existed before Phase B began" (now explicitly permitted) — Gate R4-D's PASS basis is now `REACHABLE_COMMITTED_BLOB` **or** `PREEXISTING_DOCUMENTED_BYTE_COPY` (verified path/SHA256/bytes/verify-command/source-correspondence/content match); `DOCUMENTED_BYTE_COPY` is retained solely as the generic type a **future, separately-approved Phase C+** action would create, never something Phase B's own records may claim (§5, §8, §10.7, §11, AC-R4-17/21/22/23/35, `LiveIdentityRecord`, `DurableIdentityRecord`); (2) corrected Edge case 5 to match — a modified/untracked file with no durable identity still supports only a FAIL (never a PASS), but a file backed by an already-existing, read-only-verified `PREEXISTING_DOCUMENTED_BYTE_COPY` may support a PASS; Phase B still never creates a copy to manufacture that outcome (§14.5). Round 1/2's substantive gate structure, tracks, and every other AC are otherwise unchanged; Status remains `IN REVIEW`, User approval remains `PENDING`.

---

## 0. Relationship to P0-R3 — explicit non-modification

This document does not modify, reinterpret, reopen, or supersede any P0-R3 artifact, conclusion, gate result, or commit. P0-R3's Phase B result (archived at `f5dc275ef320c63e76b5cac49279f68cff286793`) is a fixed, external, read-only input:

- **Gate R3-L:** PASS — scoped strictly to the approved committed baseline (`497a03ee04d676aa44f5948dcfc69d9c8edd3ebf` and its docs-only descendants). The **live working tree** for `core/data_provider.py` and `tej_importer.py` (and the `TEJ_RUNTIME_OVERLAY_DIR` merge mechanism they carry) was explicitly `NOT_EVALUATED` by that PASS.
- **Gate R3-S:** **FAIL** — `COVERAGE_INSUFFICIENT` (`monthly_revenue`, `institutional_gross`, `tdcc_weekly`), `SCHEMA_DRIFT_UNRESOLVED` (`financial_statements`, `monthly_revenue`), `DURABLE_IDENTITY_NOT_ESTABLISHED` (all 8 D\* datasets). Duplicate-key integrity `NOT_FULLY_EVALUATED` (fail-fast/short-circuit; no full-corpus sweep performed).
- **Gate R3-P:** **FAIL** — `FIXED_OFFSET_PROXY_UNCONDITIONAL` (`revenue_growth`, `monthly_revenue`, `financial_statements`, `institutional_gross`, `tdcc_weekly`), `DURABLE_IDENTITY_NOT_ESTABLISHED`.
- **Gates R3-F, R3-U, R3-B, R3-Q, R3-I, R3-N:** `NOT_EVALUATED` (Phase C never admitted).
- **Disposition:** `NULL_BLOCKED_RESULT` (§7.0/AC-R3-23). No snapshot, no adapter, no tests, no parity computation exist from P0-R3.

**P0-R4 exists to investigate — never to assume — whether the deficiencies P0-R3 found are remediable.** Nothing in this document reopens P0-R3's own D\* (§6 of P0-R3's prereg), its per-field lineage records, or its `NULL_BLOCKED_RESULT`. Where P0-R4 needs the same raw datasets P0-R3 examined, it treats P0-R3's findings as the evidentiary starting point (§2.2), not as something this study re-litigates from zero.

---

## 1. Context and non-claims

P0-R3 Phase B (archived, §0) found that 5 of the 8 datasets it identified as required for A-leg `real_composite` and B-leg `revenue_yoy` fail either source-sufficiency (coverage/schema) or PIT-validity (genuine-evidence) requirements, and that **none** of the 8 have an established durable corpus identity. Separately, P0-R3 found the actual **live** production code path (as opposed to the git-committed baseline it anchored its evidence to) has diverged in ways it explicitly declined to evaluate. P0-R4 is chartered to determine, for each of these three problem classes, whether and how they could be remediated — **as a diagnosis-only study first**, with no presumption that remediation is achievable, sufficient, or will ever be authorized.

**Non-claims (binding on every phase, every gate, every report this study produces):**

1. **First-vintage discipline.** Any historical reconstruction claim must distinguish the value as it was knowable **at the historical decision date** (first-vintage) from the value as it reads **today** (current/latest-revised). A later-revised value substituting for an unavailable first-vintage value is a genuine future-input violation under this study's own rules (§6), never disclosed as an acceptable equivalent, regardless of how small the revision or how inconvenient its absence.
2. **"Exists now" ≠ "was available then."** A dataset, column, or record existing in today's `tej_cache` (or any successor location) is never, by itself, evidence that the same information was knowable to a decision-maker on the historical `as_of` date it purports to describe.
3. **"Sync succeeded" ≠ "PIT-correct."** A successful data import, collector run, or reconciliation between two datasets proves only that bytes moved correctly — it proves nothing about whether the resulting timestamp/value reflects genuine historical public availability. These are independent claims and must never be conflated in any report this study produces.
4. **No reverse-engineering from derived outputs.** `obs_alpha.parquet`, `exec_ret.parquet`, `realbody_scores*.parquet`, or any other computed/derived panel may never be used, under any name or transformation, to reconstruct, validate, infer, or stand in for raw historical source data. This is a named, binding prohibition (feeds Gate R4-X, §10.8) — not merely a style preference.
5. **P0-R3 (and P0-R2, P0-R1, P0-U1) are not reopened.** Nothing in this document, at any phase, modifies, recomputes, or reinterprets any prior study's gate result, conclusion, or archived artifact.
6. **No factor/formula/weight/fusion/performance-threshold change, ever, in any phase of this study.** P0-R4's entire scope is raw-source provenance, coverage, PIT semantics, and code/data identity — never the scoring mathematics that consumes them. Any output that also happens to touch factor definitions, engine weights, fusion logic, or backtest performance gates is out of scope by construction, not merely deprioritized.
7. **No pre-commitment to remediability.** This document does not assume, promise, or imply that any of the three tracks (§3) will succeed. A track's own gates may terminate in a declared "not reconstructible" / "not remediable" finding, which is itself a valid, complete, non-blocking-of-the-study result — not a defect requiring the study to keep searching for a workaround.
8. **Phase A approval authorizes read-only diagnosis only.** Approving this document authorizes Phase B (§11) — read-only source/vintage feasibility diagnosis — and nothing beyond it. Any download, import, backfill, transformation, production/cache/Scheduler code modification, or data snapshot requires its own separate, explicit, future approval, on top of and independent from this document's approval.

---

## 2. Frozen identities

### 2.1 Repository baseline

`f5dc275ef320c63e76b5cac49279f68cff286793` — `research(P0-R3): archive Phase B blocked source-lineage result`. Parent `b97d31602ff21b150f2f8e0abc3d3ad527f32241`. This is a **commit identity anchor only** — per §5's durable-identity rule (restated from P0-R3 §5), it does not by itself stand in for the identity of any file this study needs to evaluate but which is not reachable from this commit (in particular, the live working-tree files named in §8).

### 2.2 P0-R3 result identity (restated, not reopened)

All committed at `f5dc275e...`, read-only inputs, not recomputed here:

| artifact | SHA256 |
|---|---|
| `docs/prereg_P0_R3_SourceLineage_RawSnapshot_RfwdQualification_2026-08-15.md` | `bfcac322368c3639253482cdecd0786a0ce98010796ed80e2f61da4eb6404dca` |
| `docs/prereg_P0_R3_approval_receipt_2026-08-15.json` | `76447e331c7503d3ade90e6c7483a32c304dd68098aa74b356518578a788755c` |
| `research/p0_r3_source_lineage/phase_b_design_freeze.md` | `928e273c8d84b959e444c3714f2ac934dc821bd63dbb62823810ddc9a0fde6af` |
| `research/p0_r3_source_lineage/gate_report.json` | `0d25bb424e53e890f3f487a8d384f906533626b287b26452cbb16ea90c7b5aa4` |

**P0-R3's frozen D\* (the 8 datasets this study's Track B/C work concerns):** `price_valuation`, `revenue_growth`, `industry_map`, `monthly_revenue`, `financial_statements`, `institutional_flow`, `institutional_gross`, `tdcc_weekly` (all TEJ). Per-dataset P0-R3 findings this study treats as its evidentiary starting point (§6/§7 give the binding rules built on top of these facts):

| dataset | R3-S | R3-P | key finding |
|---|---|---|---|
| `price_valuation` | SUFFICIENT | PASS | full 2004-01-02→2026-07-14 coverage, same-day genuine field |
| `institutional_flow` | SUFFICIENT | PASS | full 2004-01-02→2026-07-14 coverage, same-day genuine field |
| `industry_map` | SUFFICIENT | PASS w/ disclosed risk | static current-snapshot, retroactively applied across all history (non-classic look-ahead, not a lag issue) |
| `revenue_growth` | SUFFICIENT | **FAIL** | full 2004-01-01→2026-06-01 coverage, but **no disclosure-date field exists in this dataset at all** |
| `monthly_revenue` | **FAIL** (coverage + schema) | **FAIL** | actual on-disk range 2019-01-01→2026-06-01 — **168/255 canonical months missing** (2005-01-31→2018-12-28); genuine `release_date` present 2019+ only, proxy fallback elsewhere; 8/1952 per-stock files have an all-null `release_date` column |
| `financial_statements` | **FAIL** (schema) | **FAIL** | near-full 2005-06-01→2026-03-01 coverage; 187/2287 files have `int64`-vs-`double` numeric-column drift; a genuine per-row `release_date` now exists in the raw dataset (2026-08-06 re-export) but is **not consumed** by the producing chain (`core.tej_bundle._to_long` drops it) — a uniform 45-day fixed lag is applied instead |
| `institutional_gross` | **FAIL** (coverage) | **FAIL** | actual on-disk range **2026-04-01→2026-07-16 only** — **255/255 canonical months missing** (the entire target range); contradicts the (uncommitted) `tej_importer.py`'s own docstring claim of 2004-01-02+ coverage; zero PIT lag applied by the A-leg's consuming code with no confirmed genuine per-row availability evidence |
| `tdcc_weekly` | **FAIL** (coverage) | **FAIL** | actual on-disk range 2019-01-04→2026-07-09 — **168/255 canonical months missing**; zero PIT lag applied by the A-leg's consuming code (`core.tej_bundle._tej_shareholding`), while a separate consumer (`scripts/alpha_gate_lab.py`) applies an explicit 4-day lag to the same dataset for a different field — internal inconsistency, unresolved |

**Live-identity divergence (P0-R3 §1.2.2, explicitly `NOT_EVALUATED` by Gate R3-L's PASS):** the working-tree copies of `core/data_provider.py` (69 changed lines) and `tej_importer.py` (2,272 changed lines, 434→2,156) are uncommitted as of P0-R3's archival. The working-tree `data_provider.py` adds a third merge layer, `TEJ_RUNTIME_OVERLAY_DIR` (default `data/runtime_cache/dataexport0806/{dataset}.parquet`), inside `_read_tej()`; this mechanism does not exist in the committed baseline at all. `data/runtime_cache/dataexport0806/receipt.json` (read by P0-R3) records this overlay's actual content as `financial_statements: date_min=date_max=2026-06-01` (596 stocks) and `monthly_revenue: date_min=date_max=2026-07-01` (406 stocks) — both single-month snapshots. Separately, the git-committed baseline's own `DataProvider._read_local_price_valuation`/`_read_local_chip` merge `tej_cache` with a **live production collector snapshot** (`market_cache/{price_valuation_daily,monthly_revenue,institutional_flow_daily}/*.parquet`), empirically confirmed by P0-R3 to hold data no earlier than 2026-06/07 — i.e. after the 255-canonical-month target range ends (2026-03-31) — as observed 2026-08-15.

### 2.3 P0-R2 / P0-U1 identities (restated, not reopened)

- `497a03ee04d676aa44f5948dcfc69d9c8edd3ebf` — P0-R2 Phase D Round 2 archive commit (P0-R3's own approved baseline, §2.1 of P0-R3's prereg).
- **255 canonical `as_of` dates**, `2005-01-31 → 2026-03-31`, monthly — the frozen denominator for every coverage claim this study makes, sourced from `research/p0_r2_identity_collector/a_leg_parity_result.json::a_leg_parity_result.per_date` (255 keys, read-only, not recomputed here; first `2005-01-31`, last `2026-03-31`).
- P0-U1 canonical oracle callable: `beat_0050.strategies.high52_lab.Panel` + `dual_confirm_mask(P, "100萬", top_pct=20, source="real", min_cov=1.0, canonical=False)` — restated for continuity; **this study does not touch the oracle or its consumers** (non-claim 6).

---

## 3. Three-track specification overview

This study is structured as three **independent, differently-gated** tracks, each with its **own** dependency chain (§10.9's per-track matrix — there is no single shared upstream gate across all three). They may progress, stall, or terminate at different points; a FAIL (blocking sense) in one track's own upstream gate does not, by itself, block another track's diagnosis. The only things all three tracks share are the downstream Gate R4-D (durable identity, evaluated separately per track's own evidence) and the continuous cross-cutting Gate R4-X (forbidden derived-output substitution).

- **Track A — Historical-oracle reconstruction** (§6, Gate R4-V, gated by `R4-A → R4-V → R4-D`): can the **original** raw sources' first-vintage historical values, as they were knowable on each historical decision date, actually be recovered? This track may legitimately terminate in "no" for some or all datasets — that is a complete, valid finding, not a failure requiring further searching.
- **Track B — PIT-correct successor dataset** (§7, Gates R4-H/R4-P/R4-S, gated by `R4-A → {R4-H, R4-P, R4-S} → R4-D`): independent of whether the *original* vintage is recoverable, can a **PIT-correct** dataset (original or successor) be identified/built that satisfies coverage, genuine-evidence, and integrity requirements going forward? A successor dataset is never the same "oracle identity" as an original — §7.4 makes this a first-class, binding distinction.
- **Track C — Current live identity** (§8, Gate R4-L, gated by `R4-L → R4-D`): independent of both A and B, what does the **actual, currently-running** production code read, right now — and is that determinable at all, given the uncommitted divergence P0-R3 flagged but did not evaluate? **Track C has no dependency on Gate R4-A, and Tracks A/B have no dependency on Gate R4-L** — a FAIL in either does not block the other (AC-R4-27/§10.9).

---

## 4. Windows-Git-scoped identity method (binding, for Gate R4-L)

Per P0-R3 §4's corrected finding (WSL git's CRLF-driven status is unreliable evidence), any git-state claim this study makes **must** use native Windows Git (`git.exe`, verified present this environment as `/mnt/c/Program Files/Git/cmd/git.exe`, version `2.54.0.windows.1` at P0-R3 drafting time — re-verify the actual version at Phase B execution time, do not assume it is unchanged), scoped to the exact file paths under evaluation. **WSL Git's status output is not admissible as git-state evidence anywhere in this study's reports**, restated as binding here (not merely inherited by reference).

---

## 5. Durable identity rule (binding, restated from P0-R3 §5)

> A file's identity is durably frozen if, and only if, **either** (a) it is a reachable committed blob (verified via `git rev-parse <commit>:<path>` matching a blob that `git merge-base --is-ancestor` or equivalent confirms is reachable from a live ref), **or** (b) an independent durable byte copy exists outside `.git/objects` together with its SHA256, byte count, and a documented, reproducible verify command. A `git hash-object -w` loose blob **MAY** be recorded as auxiliary, supporting evidence, but **MUST NOT**, by itself, satisfy the freeze requirement for any file that is not otherwise reachable-committed or byte-copied.

This rule applies to **both** code files (Gate R4-L, R4-D) and dataset files (Gate R4-D) alike. It is the same rule P0-R3 used to correctly decline to treat the uncommitted `core/data_provider.py`/`tej_importer.py` as durable evidence (§2.2) — P0-R4 does not weaken it.

**"Established" ≠ "created" — round 3 clarification.** §5(b)'s independent byte copy may already exist **before** Phase B begins — e.g. created for an unrelated purpose in an earlier round/phase, shipped as part of a vendor deliverable, or otherwise present on disk without Phase B having made it. Its pre-existence requires no authorization Phase B lacks. What Phase B may **never** do, under any circumstance, is **create, copy, or modify** a byte copy itself (§8, §11, AC-R4-17, AC-R4-35). Where a byte copy already exists, Phase B's job with respect to it is the same in kind as for a committed blob: **read-only verify** it — confirm the copy's documented path, SHA256, byte count, and that its documented verify command actually reproduces the stated hash when re-run, **and** confirm the copy genuinely corresponds to the exact file/dataset being cited (same source content, not merely a similarly-named file). A copy that passes this read-only verification **does** satisfy §5(b) and is recorded `PREEXISTING_DOCUMENTED_BYTE_COPY` (§8, §14.3) — distinct from `DOCUMENTED_BYTE_COPY`, which remains reserved for a copy a **future, separately-approved Phase C+ action creates**; Phase B's own records may never use that label for anything, since Phase B creates nothing.

**Existence-check (and read-only verification of what already exists) only, never creation, in Phase B.** Phase B's role with respect to this rule is limited to **checking whether durable identity already exists** for a file/dataset, and — only where an independent byte copy is found to already exist — **read-only verifying** it as above. It does **not**, and under no circumstance may, **create** one (no byte copy of any kind, code or data, is ever made *by* Phase B — §8, §11, AC-R4-17, AC-R4-35). Where no reachable committed blob already exists **and** no independent byte copy already exists (the common case for `core/data_provider.py`/`tej_importer.py`'s current modified state, and for the entire external `tej_cache`/`market_cache`/`TEJ_RUNTIME_OVERLAY_DIR` corpus, none of which is git-tracked, and for which no pre-existing byte copy is currently known to this study), Phase B records `NOT_ESTABLISHED` and stops there — establishing new durable identity where none already exists is a Phase C+-shaped action requiring its own separate, explicit future approval.

**PASS/FAIL asymmetry — binding across every gate in this study.** `OBSERVED_CURRENT_CORPUS`-basis evidence (metadata inspection, a single read of a file's current bytes, a hash computed once with no corresponding durable copy) is **sufficient to support a FAIL finding** for any gate (it genuinely proves a deficiency exists right now) but **is never sufficient to support a PASS finding** for any gate. **Any gate result that would otherwise PASS on the strength of such non-durable evidence MUST be downgraded to FAIL** — a clean-looking result computed from non-durable evidence is not "provisionally PASS pending durability," it is FAIL until durable identity is established. **This asymmetry does not apply to a `REACHABLE_COMMITTED_BLOB` or a read-only-verified `PREEXISTING_DOCUMENTED_BYTE_COPY`** (above) — both are genuine durable identity, established before and independently of Phase B's own actions, and either may support a PASS once Phase B's read-only verification confirms it. This mirrors, and is stated here as independently binding (not merely inherited by reference from), the discipline P0-R3's own `research/p0_r3_source_lineage/phase_b_design_freeze.md` §2.7 already modeled for its own coverage/schema findings.

---

## 6. Track A — Historical-oracle reconstruction (feeds Gate R4-V)

**Purpose:** determine, per D\* dataset (and per affected field, where a dataset mixes genuine and proxy rows, e.g. `monthly_revenue`'s pre-/post-2019 split, §2.2), whether the **first-vintage** value — the value as it was knowable to a decision-maker at each historical `as_of` — is actually recoverable from any real, evidenced source (TEJ's own revision history if it exists, an archived collector snapshot, a third-party point-in-time vendor, or equivalent).

**Binding rules:**

1. **First-vintage or nothing.** If a dataset/provider only exposes the **current, latest-revised** value for a historical period (no revision history, no point-in-time archive), that period's first-vintage value is **not reconstructible** from that source. The study MUST declare this explicitly, per affected date range, and MUST NOT substitute the current value while describing it as historical.
2. **No fixed-lag manufacture.** A fixed-offset lag (e.g. "assume it was knowable N days after period-end") is a **PIT-availability-timing** proxy (Track B's concern, §7.3), never a substitute for **vintage/value** reconstruction. Track A's question is "what was the *value*," not "when might it have become known" — conflating the two is prohibited; a dataset that lacks first-vintage values cannot be made whole by asserting a lag on its current values.
3. **No derived-output backfill.** Per non-claim 4/§10.8, `obs_alpha.parquet`, `exec_ret.parquet`, or any score/derived panel may never be used to infer or reconstruct a first-vintage raw value.
4. **Explicit per-dataset, per-range declaration.** Track A's output is a `VintageAvailabilityRecord` (§14.3) per dataset (or per dataset+field where mixed), classifying each affected historical range as `RECONSTRUCTIBLE` (with the evidenced source named) or `NOT_RECONSTRUCTIBLE` (with the reason — no revision history exists, no archive covers the range, etc.). A `NOT_RECONSTRUCTIBLE` finding for any range is a complete, terminal answer for that range — Track A does not retry with a different, weaker standard.

---

## 7. Track B — PIT-correct successor dataset (feeds Gates R4-A / R4-H / R4-P / R4-S)

**Purpose:** independent of Track A's vintage-recoverability answer, determine whether a dataset — the original TEJ dataset, a different TEJ dataset covering the same underlying phenomenon, or an external authoritative source — can satisfy this study's coverage, genuine-evidence, and integrity bar **going forward**, for use as (or in place of) each of P0-R3's failing D\* members.

### 7.1 `monthly_revenue`, `institutional_gross`, `tdcc_weekly` — coverage remediation (feeds Gate R4-H)

For each of these three datasets (P0-R3's coverage-FAIL set, §2.2), Track B must determine: does TEJ (or the collector pipeline) hold, anywhere, a **historical backfill** covering the missing canonical months (2005-01-31→2018-12-28 for `monthly_revenue`/`tdcc_weekly`; the entire 2005-01-31→2026-03-31 range for `institutional_gross`, whose on-disk data currently postdates the target range entirely)? This is a **provenance/availability question** (does the data exist anywhere, obtainable through a real, named channel), explicitly **not** an authorization to actually download/import it (§11 — that remains Phase D+, separately approved). `institutional_gross`'s specific, already-documented contradiction (§2.2 — its own importer's docstring claims 2004+ coverage that does not match what is actually on disk) must be resolved as a factual finding (which claim, if either, is accurate, and why) before any coverage-remediation plan can even be scoped.

### 7.2 `revenue_growth` — real disclosure-date requirement (feeds Gate R4-P)

`revenue_growth` has full structural coverage (§2.2) but **no disclosure-date field exists in the dataset at all** — this is not a code-consumption gap (contrast §7.3) but an absence in the raw data itself. Track B must determine:

1. Whether TEJ (or an equivalent authoritative vendor) offers **any** dataset for the same underlying phenomenon (monthly revenue YoY growth) that carries a genuine, evidenced, per-row disclosure/availability date. `monthly_revenue` (§2.2's finding: genuine `release_date` present 2019+) is one candidate already known to this study, but its own coverage gap (§7.1) and any structural difference from `revenue_growth`'s specific field (`revenue_yoy_pct`) must be evaluated, not assumed compatible.
2. **If no such dataset can be obtained, this must be declared, not silently substituted.**
3. **If a successor dataset is identified and later adopted, it is a *new data definition*, not a continuation of `revenue_growth`'s "oracle identity."** Any report describing the successor must say so explicitly — e.g. "B-leg `revenue_yoy` reconstructed from `<successor dataset>`, a different raw source than the one `scripts/tej_universe_screen_validation.py` currently reads" — and must never claim this satisfies P0-R3's or P0-U1's original lineage/oracle definitions unchanged. This is a binding, permanent labeling requirement (feeds AC-R4-13).

### 7.3 `financial_statements` — actual consumption of `release_date` (feeds Gate R4-P)

P0-R3 found that `financial_statements` **now contains** a genuine per-row disclosure date (`財報發布日`/`release_date`, added in TEJ's 2026-08-06 re-export) but that the actual producing chain (`core.tej_bundle._to_long`) does not read it — a uniform 45-day fixed lag (`PUBLISH_LAG_DAYS`) is applied instead. **Track B's binding rule for this dataset: a PIT-PASS claim requires demonstrating that the producing chain's code actually reads and uses the `release_date` field for cutoff computation — the field's mere presence in the raw parquet schema is never sufficient.** This closes the exact gap AC-R3-7 (of P0-R3's prereg) already established for the qualification track and restates it here as a binding design constraint for any remediation code this study might, in a later phase, consider writing (not authorized this round, §11).

### 7.4 `institutional_gross` / `tdcc_weekly` — provable availability semantics (feeds Gate R4-P)

P0-R3 found both datasets consumed with **zero PIT lag** and **no confirmed genuine per-row availability evidence** — an unresolved, unverified assumption, not a documented proxy. Track B's binding rule: **no zero-lag (or any-lag) assumption may be adopted without a named, evidenced source for the claim** — e.g. TDCC's own published data-release schedule, a vendor's documented collection-to-availability delay, or an equivalent authoritative statement. `scripts/alpha_gate_lab.py`'s own, separate 4-day lag for `tdcc_weekly` (used for a non-target field) is **evidence that a lag may be warranted**, not proof of the correct lag value — Track B must resolve this with real evidence, not by picking whichever existing number in the codebase is more convenient.

### 7.5 Full-corpus schema/duplicate/missingness integrity (feeds Gate R4-S)

P0-R3 explicitly performed only a **single-file sample** for duplicate-key checking (`NOT_FULLY_EVALUATED`, its §2.5) and did not attempt revision-policy checks at all. Any dataset entering Track B's qualification path must receive the **full** integrity check the prereg's own D\* record requires (schema fingerprint, first/last structural date over the **full corpus** — not a sample, duplicate-key policy over **every** file, missingness rules, revision policy) — Gate R4-S may not PASS on a sampled basis, mirroring the discipline P0-R3 already modeled by declining to claim completeness from its own sample.

---

## 8. Track C — Current live identity (feeds Gate R4-L)

**Purpose:** precisely determine — not assume, not infer from the committed baseline — whether the modified `core/data_provider.py`, the rewritten `tej_importer.py`, and the `TEJ_RUNTIME_OVERLAY_DIR` mechanism they introduce are **actually used by the current live/production runtime**, right now.

**Binding requirements (`LiveIdentityRecord`, §14.3):**

1. **Path.** The exact filesystem path(s) actually loaded by whatever process constitutes "production" for this study's purposes (to be identified in Phase B — this document does not assume there is a single obvious "the production process"; identifying it is itself part of Gate R4-L's job).
2. **SHA256 + byte count** of the file(s) as found at that path, at the time of inspection.
3. **Git state**, Windows-Git-scoped (§4) — `M`/`??`/clean, and if clean, the exact commit the content matches.
4. **Runtime configuration** — is `TEJ_RUNTIME_OVERLAY_DIR`/`TEJ_CACHE`/`MARKET_CACHE` actually set to a non-default value in whatever environment production runs under (`.env`, OS environment, service manifest, scheduled-task definition, or equivalent)? Default values assumed by reading source code are not evidence of what a running process actually resolves — this must be checked against the actual runtime environment, not inferred.
5. **Environment resolution.** For every environment-variable-driven path (`TEJ_CACHE`, `MARKET_CACHE`, `TEJ_RUNTIME_OVERLAY`), the actual resolved absolute path in the production context, with the resolution method documented (env var found? default applied? overridden by a config file read before these variables are consulted?).

**Binding rule on baseline substitution:** **the approved repository baseline commit (§2.1) may never be used as a stand-in for actual live identity.** P0-R3 already established the discipline of anchoring gate evidence to the committed baseline *when the live working tree is not being evaluated* — Gate R4-L's entire purpose is the opposite: to evaluate the live working tree, precisely because P0-R3 declined to. A report that says "the committed baseline shows X, therefore production does X" **fails** Gate R4-L outright; only direct evidence of what is actually running satisfies it.

**Binding rule on durable identity for modified/untracked files — Phase B verifies what already exists; it never creates, copies, or modifies anything.** Per §5, any file found to be `M`(modified)/`??`(untracked) relative to any commit **requires durable identity** (a reachable committed blob is not applicable, by definition, for a modified/untracked file — so this means an independent durable byte copy: SHA256 + bytes + documented verify command) before it may be used to support a gate PASS. Two distinct situations, both read-only:

1. **No pre-existing byte copy is found.** Phase B's `LiveIdentityRecord` (§14.3) records **only** `target_path`, `sha256`, `bytes`, and `git_state` — computed read-only, in place, without copying the file anywhere — and sets `durable_identity_status: NOT_ESTABLISHED`. This record supports a **FAIL** finding (§5's PASS/FAIL asymmetry rule) but **may never be cited as supporting a PASS**.
2. **A byte copy already exists, independent of anything Phase B does** (created in an earlier round/phase, or present for an unrelated reason — Phase B *discovers*, never *makes*, it). Phase B **may** read-only verify it: confirm the copy's documented path/SHA256/byte count, re-run its documented verify command and confirm the result matches, and confirm the copy genuinely corresponds to the exact file being cited. If this verification succeeds, `durable_identity_status: PREEXISTING_DOCUMENTED_BYTE_COPY` is recorded and the file's evidence **may** support a PASS (§10.7). If verification fails (hash mismatch, no working verify command, unclear correspondence), the record reverts to `NOT_ESTABLISHED` and supports only a FAIL.

**In neither situation does Phase B create, copy, or modify any byte copy** of `core/data_provider.py`, `tej_importer.py`, or any other file. Making a **new** byte copy — the only route by which a currently-`NOT_ESTABLISHED` file could ever reach a PASS — is a Phase C+-shaped action requiring its own separate, explicit, future approval (§11); it is not authorized, in any form, by this document's Phase A approval.

---

## 9. Cross-cutting: forbidden derived-output substitution (feeds Gate R4-X)

Restated from non-claim 4 as a formal, testable gate: **no report, evidence record, or remediation design this study produces may use `obs_alpha.parquet`, `exec_ret.parquet`, any `realbody_scores*.parquet`, any other computed/derived panel, or any output of `beat_0050`/`scripts/*_lab.py` as a raw-source stand-in, validation reference, or reconstruction aid for historical raw data.** This applies to all three tracks equally — Track A's vintage question, Track B's coverage/PIT question, and Track C's live-identity question must each be answered from **raw, original-provider evidence** (TEJ exports, TDCC publications, vendor documentation, collector run logs) — never from what a downstream computed panel happens to contain.

---

## 10. Gates

### 10.0 Phase C+ (remediation) admission rule

No download, import, backfill, transformation, production/cache/Scheduler code modification, or data snapshot may begin for a given **track** until **that track's own** gates (per §10.9's per-track matrix) have all been scored, **and** Gate R4-D has been separately evaluated for whatever evidence those gates relied on, **and** the user has granted a **separate, explicit, future approval** for that specific remediation action. This document's Phase A approval does not extend to any of it (§1 non-claim 8, restated here as the binding admission test, mirroring P0-R3's own §7.0/§11 pattern).

**Per-track blocking (no single shared upstream gate — §10.9):**

- **Track A** (`R4-A → R4-V → R4-D`): if Gate R4-A FAILs (or is left unresolved), Track A's `R4-V` is `NOT_EVALUATED`, and no remediation implementation for Track A may be scoped. **Track A does not depend on Gate R4-L** — a Gate R4-L FAIL never blocks Track A.
- **Track B** (`R4-A → {R4-H, R4-P, R4-S} → R4-D`): if Gate R4-A FAILs (or is left unresolved), Track B's `R4-H`/`R4-P`/`R4-S` are all `NOT_EVALUATED`, and no remediation implementation for Track B may be scoped. **Track B does not depend on Gate R4-L** — a Gate R4-L FAIL never blocks Track B.
- **Track C** (`R4-L → R4-D`): if Gate R4-L FAILs (or is left unresolved), Track C's `R4-D` evaluation for Track C's own evidence is `NOT_EVALUATED`, and no remediation implementation for Track C may be scoped. **Track C does not depend on Gate R4-A** — a Gate R4-A FAIL never blocks Track C.

### 10.1 Gate R4-L — Current live identity uniquely resolved

**Purpose:** per §8. **PASSes** only when every item in §8's `LiveIdentityRecord` is complete for `core/data_provider.py`, `tej_importer.py`, and the `TEJ_RUNTIME_OVERLAY_DIR` mechanism, **and** the record resolves to a single, unambiguous statement of what the current live/production runtime actually reads — not a plausible guess, not an inference from the committed baseline. **FAILs** if production's actual identity cannot be determined at all (e.g. no accessible running instance, no accessible deployment/service configuration) — a genuine `NOT_EVALUATED`-shaped outcome is recorded as FAIL for this gate's PASS-eligibility purposes, mirroring P0-R3's AC-R3-27-style "absence of evidence is scored as a FAIL, never PASS-by-silence" discipline.

### 10.2 Gate R4-A — Authoritative raw-source provenance

**Purpose:** the shared upstream gate for **both** Track A and Track B (§10.9 — Track A: `R4-A → R4-V`; Track B: `R4-A → {R4-H,R4-P,R4-S}`; **not** Track C, which depends only on R4-L). For every dataset either track considers (original or successor), confirm the dataset's actual vendor/provider identity, official product name, and licensing/access terms are documented from the provider's own materials (not inferred from a filename or a prior study's casual description), obtained only through §11.1's read-only browsing boundary (`ProvenanceCitation`, §14.3) — no download, no importer invocation. **PASSes** per dataset once this is established with a citable source; **FAILs** for any dataset where provenance cannot be confirmed from authoritative material, including where confirmation is `BLOCKED`/`UNAVAILABLE` per §11.1 item 3 (a blocked check is a valid terminal finding, but it is not a PASS).

### 10.3 Gate R4-H — Full historical coverage

**Purpose:** 255/255 canonical months (§2.3), full-market, structurally present for a dataset — mirrors P0-R3's own coverage standard (NFR-R3-2-equivalent, no general waiver). **PASSes** only at 255/255; any missing month FAILs the gate for that dataset, named explicitly (never a shrunk denominator, mirroring P0-R3's AC-R3-13/AC-R3-29 discipline, adopted here as binding for R4 from the start).

### 10.4 Gate R4-V — Historical vintage/revision availability

**Purpose:** per §6. **PASSes** per dataset/range once a `VintageAvailabilityRecord` classifies it `RECONSTRUCTIBLE` with a named, evidenced source. A `NOT_RECONSTRUCTIBLE` classification is a **valid, complete, terminal** finding for that range — it does not itself "FAIL" the gate in the sense of an error; it is recorded as `DECLARED_NOT_RECONSTRUCTIBLE` and treated as a hard boundary no later phase may quietly route around (§6 rule 1/2).

### 10.5 Gate R4-P — Genuine per-row PIT availability semantics

**Purpose:** per §7.2–7.4. **PASSes** per dataset only with 100% genuine, evidenced, per-row disclosure/availability data actually consumed by whatever code would use it — zero fixed-offset or zero-lag proxies in the qualification track, mirroring P0-R3's AC-R3-7 discipline exactly (partial genuine coverage does not cure the classification for the un-cured portion; a genuine field's mere presence in a raw schema does not cure a producing chain that does not read it, §7.3).

### 10.6 Gate R4-S — Schema/duplicate/missingness integrity

**Purpose:** per §7.5. **PASSes** per dataset only on a **full-corpus** check (every file, not a sample) covering schema-fingerprint uniformity (or an explicitly documented, approved variant structure), duplicate-key policy, and missingness rules. A sampled check, however clean, does not qualify for a PASS — recorded at most as `NOT_FULLY_EVALUATED`, mirroring the discipline P0-R3 itself used for its own single-file sample.

### 10.7 Gate R4-D — Durable corpus identity

**Purpose:** per §5. **In Phase B, this gate is evaluated in existence-check-and-read-only-verify mode only — it confirms whether durable identity already exists (and, where a byte copy already exists, read-only verifies it), and never creates, copies, or modifies anything.** **PASSes** per file/dataset only when the identity basis is `REACHABLE_COMMITTED_BLOB` (already exists in git history) **or** `PREEXISTING_DOCUMENTED_BYTE_COPY` (an independent byte copy that already existed **before** Phase B began, read-only verified this round — path/SHA256/bytes/verify-command/source-correspondence all confirmed to match, §5/§8) — these are the **only two** bases on which Phase B may ever record a PASS for this gate, since Phase B makes no byte copies of its own (§8, §11). **FAILs** — and blocks every gate whose evidence depended on that file/dataset, per §5's PASS/FAIL asymmetry rule — for any file/dataset with neither a reachable committed blob nor a verified pre-existing byte copy, recorded `NOT_ESTABLISHED`, mirroring P0-R3's AC-R3-30 exactly. Establishing a **new** byte copy that would convert a `NOT_ESTABLISHED` finding into a future PASS is a Phase C+-shaped action, not something Gate R4-D itself does in Phase B.

### 10.8 Gate R4-X — Forbidden derived-output substitution

**Purpose:** per §9. A **cross-cutting compliance gate**, not a per-dataset sufficiency gate: it audits every other gate's evidence trail for any reliance on `obs_alpha.parquet`/`exec_ret.parquet`/score outputs/other derived panels. **FAILs** — for the specific finding that relied on the forbidden source, and by extension for any gate whose PASS depended on that finding — if any such reliance is found. **PASSes** (i.e., is clean) only when every other gate's full evidence trail is confirmed free of derived-output reliance.

### 10.9 Dependency order (binding — per-track matrix, no shared upstream gate)

**There is no single dependency graph covering all three tracks.** Each track has its own, independent chain:

```
Track A:  R4-A  ──►  R4-V              ──►  R4-D
Track B:  R4-A  ──►  { R4-H, R4-P, R4-S } ──►  R4-D
Track C:  R4-L  ──►  R4-D
```

`R4-X` (§10.8) runs **continuously** across all three chains and all gates within them, not at a fixed point in any sequence — any finding, at any gate, at any time, that turns out to rely on a forbidden derived output invalidates that specific finding immediately, regardless of what other gates it had already fed into.

**Binding rules:**

1. **Within Track A:** `R4-A` must resolve (PASS or a definitively recorded FAIL) before `R4-V` is scored. `R4-V` must resolve (PASS, `DECLARED_NOT_RECONSTRUCTIBLE`, or FAIL) before `R4-D` is scored for Track A's evidence.
2. **Within Track B:** `R4-A` must resolve before `R4-H`/`R4-P`/`R4-S` are scored. Each of `R4-H`/`R4-P`/`R4-S` must resolve before `R4-D` is scored for Track B's evidence.
3. **Within Track C:** `R4-L` must resolve before `R4-D` is scored for Track C's evidence.
4. **No cross-track dependency exists.** Gate `R4-L` (Track C's sole upstream gate) has **no bearing** on Track A or Track B — a Gate R4-L FAIL never blocks `R4-V`, `R4-H`, `R4-P`, or `R4-S`. Gate `R4-A` (Track A/B's shared upstream gate) has **no bearing** on Track C — a Gate R4-A FAIL never blocks Track C's `R4-D` evaluation. Each track's diagnosis proceeds and is reported independently of the others' status (AC-R4-29).
5. **Within-track upstream FAIL blocks only that track's downstream gates and that track's remediation-implementation phase** (§10.0) — never the other two tracks'.
6. **`R4-D` is evaluated separately per track**, against that track's own evidence — a Track A `R4-D` finding says nothing about Track B's or Track C's durable-identity status, and vice versa.

---

## 11. Execution phases

- **Phase A — Document review / manual approval.** This document only. Ends when Status changes to `APPROVED`. Authorizes Phase B only (§1 non-claim 8).
- **Phase B — Read-only source/vintage feasibility diagnosis.** Authorized by Phase A approval **only**. Scope: evaluate Gates R4-L, R4-A, R4-V, R4-H, R4-P, R4-S per §10.9's **per-track** dependency matrix (not a single shared sequence — Track A/B's chain starts at R4-A, Track C's chain starts at R4-L, independently) and Gate R4-X (continuously), using only already-existing files, already-existing configuration, and already-existing documentation (provider materials, git history, on-disk parquet metadata, environment/config inspection, and read-only vendor-website browsing per §11.1). **Phase B is unconditionally read-only — it MUST NOT, under any circumstance**: download or import any new data; back-fill or transform any dataset; modify any production, cache, or Scheduler configuration or code; create a data snapshot; write any test or adapter code; **or create, copy, or modify a byte copy of anything — code or data.** There is **no exception** for Phase B *creating* a byte copy (removed round 2, §5/AC-R4-17/AC-R4-35). **This is distinct from Phase B *read-only verifying* a byte copy that already existed before Phase B began** (§5, §8, round 3): where no pre-existing copy is found, modified/untracked code is recorded path/SHA256/bytes/git-state only, durable identity `NOT_ESTABLISHED`; where a pre-existing copy is found and its read-only verification (path/SHA256/bytes/verify-command/source-correspondence) succeeds, durable identity `PREEXISTING_DOCUMENTED_BYTE_COPY` is recorded and may support a Gate R4-D PASS (§10.7) — Phase B still creates nothing in either case. If Phase B's findings leave a track's own upstream gate (`R4-A` for Track A/B, `R4-L` for Track C) unresolved in the blocking sense, that track's diagnosis stops there and reports a terminal, honest finding — it does not proceed to guess at its downstream gates, and this does not affect the other tracks' diagnosis (§10.9 rule 4).
- **Phase C onward — deliberately unspecified by this document.** Any actual remediation action — downloading, importing, backfilling, transforming raw data; modifying `core/data_provider.py`, `tej_importer.py`, or any production/cache/Scheduler code; building a data snapshot; making **any** byte copy (code or data) toward establishing durable identity; writing tests or an adapter — is **entirely out of this document's authorization**, requires its **own**, separate, explicit, future approval (§10.0), and is **not designed here**. Per non-claim 7, this document does not commit to there being a "Phase C" in any particular shape — the shape of any future remediation phase depends entirely on what Phase B actually finds, which may include finding that no further phase is warranted for one, several, or all three tracks.

### 11.1 External document access boundary (binding for Phase B)

Gate R4-A's provenance evidence (§10.2) and Track B's remediation-channel findings (§7.1/§7.2) will typically require consulting TEJ/TDCC/vendor official documentation. Phase B's unconditionally-read-only constraint (above) applies to this activity with the following explicit boundary:

1. **Permitted:** read-only browsing of TEJ/TDCC/vendor official websites, product documentation pages, and already-published access/licensing terms. Every such reference cited in a Phase B report MUST record the URL, the access date, and the exact quoted/paraphrased content relied upon (`ProvenanceCitation`, §14.3).
2. **Forbidden, without exception:** downloading any raw dataset, data export, file attachment, sample file, or bulk archive from any such site; initiating, running, or otherwise triggering `tej_importer.py` or any other importer/collector tool, in whole or in part, under any flag, dry-run, or "just checking" mode.
3. **Paywalled/login/download-gated evidence.** If confirming a provenance or coverage/access-terms claim would require logging into a vendor portal, paying for access, or downloading data to verify, Phase B MUST record that specific finding as `BLOCKED` / `UNAVAILABLE` (with the reason) rather than attempting to obtain the access itself. **Phase B does not self-expand its own authorization to clear a blocker it encounters** — a blocked provenance check is itself a valid, complete Gate R4-A finding for that item (feeds AC-R4-31's "terminal findings are valid" discipline).
4. **No durable copy of web content without separate approval.** If a webpage's content needs to be preserved as durable evidence (§5) rather than merely cited, that preservation is a Phase C+-shaped action requiring its own separate, explicit approval. Phase B may cite, briefly quote for evidentiary purposes, and record a hash/metadata description of what it observed (`ProvenanceCitation`, §14.3) — it MUST NOT save, download, mirror, or otherwise locally archive a copy of the page or its assets.

**This document does not authorize Phase B.** No diagnosis beyond what already exists in P0-R3's archived record (§2.2, read as a fixed input) may be performed, no lineage-tracing, no data inspection of any kind, no vendor-website browsing, until Status is `APPROVED`.

---

## 12. Out of scope

Production writes; live collector modification; evidence-root activation; Task Scheduler changes; back-filling production evidence or labeling any P0-R4 output as contemporaneous production evidence; strategy/factor/weight/threshold tuning (non-claim 6); new ADV-floor research; any performance/CAGR/Sharpe metric; P0-R2/P0-R3 reopening or Stage-2-equivalent activation; modifying any P0-R1/P0-R2/P0-R3/P0-U1 artifact; using `obs_alpha.parquet`/`exec_ret.parquet`/any derived score panel as a raw-source input or validation reference under any name (§9); designing, committing to, or pre-approving any remediation-implementation phase (§11); **any byte copy of any code or data file, in any phase this document itself authorizes (§5, §8, §11, AC-R4-35)**; downloading any raw dataset, export, attachment, or bulk archive from a TEJ/TDCC/vendor site, or invoking any importer/collector tool in any mode (§11.1); saving or mirroring a local copy of any web page or document read for provenance purposes (§11.1 item 4).

---

## 13. Acceptance criteria

Given/When/Then, self-sufficient — none depends on a file this document does not itself cite with a full path.

### 13.1 Track A — Historical-oracle reconstruction (feeds Gate R4-V)

- **AC-R4-1 (no revision history → declare, don't substitute).** *Given* a dataset/provider exposes only the current, latest-revised value for a historical period, with no accessible revision history or point-in-time archive. *When* Track A evaluates that period. *Then* the period is classified `NOT_RECONSTRUCTIBLE` in the `VintageAvailabilityRecord`, and the current value is never substituted while being described as the historical first-vintage value, under any label.
- **AC-R4-2 (fixed-lag does not cure a missing vintage).** *Given* a dataset's first-vintage value for a period cannot be recovered. *When* a report considers whether applying a fixed publication-lag assumption to the current value would resolve the gap. *Then* this is explicitly rejected — a lag assumption addresses *timing*, never *value*, and the period remains `NOT_RECONSTRUCTIBLE`.
- **AC-R4-3 (no derived-output vintage inference).** *Given* `obs_alpha.parquet`, `exec_ret.parquet`, or any derived panel appears to contain a value consistent with what a historical first-vintage figure might have been. *When* Track A considers using it as evidence. *Then* this is prohibited (§9/Gate R4-X) — the value must be struck from consideration as vintage evidence regardless of apparent consistency.
- **AC-R4-4 (per-range granularity).** *Given* a dataset has genuine vintage evidence for part of its historical range and none for another part (e.g. a hypothetical dataset with real revision history from year X onward only). *When* the `VintageAvailabilityRecord` is written. *Then* it records `RECONSTRUCTIBLE`/`NOT_RECONSTRUCTIBLE` **per range**, never a single dataset-wide verdict that would either overstate the reconstructible portion or understate the reconstructible one.

### 13.2 Track B — Coverage remediation (feeds Gate R4-H)

- **AC-R4-5 (named channel or declare absent).** *Given* `monthly_revenue`, `institutional_gross`, or `tdcc_weekly`'s missing canonical months (§2.2, §7.1). *When* Track B evaluates whether a historical backfill exists. *Then* the finding names a specific, real, citable channel (TEJ product name, archive location, vendor contact path) if one exists, or explicitly states none was found — never a vague "may be available."
- **AC-R4-6 (institutional_gross contradiction resolved as fact, not assumption).** *Given* `tej_importer.py`'s own documentation claims `institutional_gross` covers 2004-01-02+ while the actual on-disk corpus covers only 2026-04-01→2026-07-16 (§2.2). *When* Track B reports on this dataset. *Then* the report states, with evidence, which claim (if either) is accurate and why the discrepancy exists — it does not proceed to a coverage-remediation recommendation while this contradiction remains unresolved.
- **AC-R4-7 (255/255 or explicit gap list, never a shrunk denominator).** *Given* any coverage claim this study makes about a dataset. *When* that claim is reported. *Then* it states the true denominator (255) and the true numerator/gap list explicitly — mirroring P0-R3's AC-R3-13/AC-R3-29 discipline, binding here from the outset.

### 13.3 Track B — PIT-evidence remediation (feeds Gate R4-P)

- **AC-R4-8 (revenue_growth successor named or absence declared).** *Given* `revenue_growth` has no disclosure-date field (§2.2, §7.2). *When* Track B evaluates a successor. *Then* it either names a specific candidate dataset with genuine, evidenced per-row availability data covering the same phenomenon, or explicitly declares no such candidate was found.
- **AC-R4-9 (successor is a new data definition, always labeled as such).** *Given* a successor dataset is identified for `revenue_growth` (or any other failing dataset). *When* any report or design document refers to it. *Then* it is explicitly labeled as a distinct data definition from the original, never described as continuing the original's "oracle identity" unchanged — a permanent labeling requirement, not a one-time disclosure.
- **AC-R4-10 (financial_statements: consumption, not presence, governs).** *Given* `financial_statements` contains a genuine `release_date` field. *When* any future remediation code (not authorized this round) is designed to consume it. *Then* the design must show the code actually reads and applies `release_date` for cutoff computation — a design that merely notes the field's existence in the schema does not satisfy Gate R4-P.
- **AC-R4-11 (institutional_gross/tdcc_weekly: evidenced lag or explicit non-resolution).** *Given* neither dataset currently has confirmed genuine per-row availability evidence (§7.4). *When* Track B proposes any lag value (including zero). *Then* the proposal must cite a named, authoritative source for the collection-to-availability delay it assumes — an existing lag value used elsewhere in the codebase for a *different* field of the *same* dataset (e.g. `alpha_gate_lab.py`'s `TDCC_LAG_DAYS=4`) is evidence worth investigating, never proof, and may not be adopted without independent confirmation.
- **AC-R4-12 (no partial-coverage cure).** *Given* a dataset has genuine per-row evidence for only part of its historical range (mirroring `monthly_revenue`'s 2019+-only `release_date`, §2.2). *When* Gate R4-P is scored for that dataset. *Then* the un-cured portion's absence of genuine evidence is not cured by the cured portion's presence — mirroring P0-R3's AC-R3-7 item 1 exactly, binding here without qualification.
- **AC-R4-13 (successor labeling is permanent, not a one-time footnote).** *Given* a successor dataset (AC-R4-9) is adopted in any later, separately-approved phase. *When* any subsequent report, gate result, or design document references the field it feeds. *Then* every such reference must carry the same successor-labeling disclosure — a later document dropping the label because "it was already established" is a violation, mirroring the spirit of P0-R3's AC-R3-28 inherited-annotation discipline.

### 13.4 Track B — Integrity (feeds Gate R4-S)

- **AC-R4-14 (full-corpus, not sample).** *Given* a dataset is being evaluated for schema/duplicate-key/missingness integrity. *When* the check is scored for Gate R4-S PASS-eligibility. *Then* it must cover every file in the corpus (not a single-file or otherwise partial sample) — a sampled result, however clean, is recorded `NOT_FULLY_EVALUATED`, never `SUFFICIENT`, mirroring P0-R3's own §2.5 discipline.
- **AC-R4-15 (schema drift ruled on, not silently accepted).** *Given* a dataset shows more than one distinct per-file schema variant (mirroring `financial_statements`'/`monthly_revenue`'s findings, §2.2). *When* Gate R4-S is scored. *Then* each variant is either explained by a demonstrated legitimate structure (written into the relevant design document) or is recorded as an unresolved FAIL — no self-judged "benign drift" exception, mirroring P0-R3's AC-R3-2.

### 13.5 Track C — Current live identity (feeds Gate R4-L)

- **AC-R4-16 (baseline is not a substitute for live evidence).** *Given* a report needs to state what code path production actually executes. *When* that statement is written. *Then* it must be based on direct inspection of the live environment (§8) — citing only the committed baseline's content as if it answered the question is a Gate R4-L FAIL for that finding, regardless of how confident the citation reads.
- **AC-R4-17 (modified/untracked files: verify what already exists, create nothing; PASS requires a verified pre-existing copy).** *Given* `core/data_provider.py`, `tej_importer.py`, or any other file relevant to Gate R4-L is found `M`/`??` under Windows-Git-scoped status (§4). *When* Phase B records that file's `LiveIdentityRecord` and cites its content as evidence for any gate. *Then* Phase B computes `target_path`/`sha256`/`bytes`/`git_state` read in place with **no byte copy created** (§5, §8, §11), and: (a) if no independent byte copy is found to already exist, sets `durable_identity_status: NOT_ESTABLISHED` — that record may support a **FAIL** but **must never** be cited as satisfying a PASS; (b) if an independent byte copy is found to **already exist** (created before Phase B began, discovered not made), Phase B **may** read-only verify its path/SHA256/bytes/verify-command/source-correspondence, and — only if that verification succeeds — records `durable_identity_status: PREEXISTING_DOCUMENTED_BYTE_COPY`, which **may** support a PASS. Creating a **new** byte copy to manufacture case (b) is prohibited without exception and is a Phase C+-shaped action requiring separate approval.
- **AC-R4-18 (environment resolution is checked, not assumed).** *Given* a path is resolved via an environment variable with a coded default (e.g. `TEJ_RUNTIME_OVERLAY`, `TEJ_CACHE`, `MARKET_CACHE`). *When* Gate R4-L records the resolved path. *Then* it must state whether the actual production environment sets that variable (and to what) or relies on the coded default — inferring the default is in effect from source code alone, without checking the actual environment, is insufficient.
- **AC-R4-19 (no running/accessible instance → FAIL, not silence).** *Given* no accessible running production instance or deployment/service configuration can be found to inspect. *When* Gate R4-L is scored. *Then* the gate is recorded FAIL (not `NOT_EVALUATED`-and-ignored) — absence of evidence is a scored outcome, mirroring P0-R3's AC-R3-27's "absence of evidence is scored as a FAIL, never PASS-by-silence."
- **AC-R4-20 (overlay/collector inertness is re-verified, not inherited).** *Given* P0-R3 found the `market_cache` collector layer and the (uncommitted) `TEJ_RUNTIME_OVERLAY_DIR` layer both empirically inert for the 255-month target range **as observed 2026-08-15** (§2.2). *When* Gate R4-L or Gate R4-P relies on this inertness finding. *Then* it must be re-verified against the current state of those directories at the time of P0-R4's own inspection, not cited as still-true by reference to P0-R3's earlier observation date.

### 13.6 Gate R4-D — Durable corpus identity

- **AC-R4-21 (code durable identity — reachable blob, or a pre-existing byte copy verified read-only).** *Given* any code file this study's gates rely on. *When* Gate R4-D is scored for it. *Then* it must be either (a) a reachable committed blob, or (b) an independent byte copy that **already existed before Phase B began** and whose path/SHA256/bytes/verify-command/source-correspondence Phase B has read-only verified this round (`identity_basis: PREEXISTING_DOCUMENTED_BYTE_COPY`) — no exceptions, mirroring P0-R3's AC-R3-30, extended with the round-3 pre-existing-copy clarification. A copy Phase B itself created, copied, or modified never qualifies — Phase B creates none.
- **AC-R4-22 (data-corpus durable identity — Phase B checks and verifies existence only, never creates it).** *Given* any dataset this study's Gate R4-A/H/P/S findings rely on (e.g. `tej_cache`, `market_cache`, `TEJ_RUNTIME_OVERLAY_DIR` contents, none of which are git-tracked). *When* Gate R4-D is scored for it in Phase B. *Then* the finding must state explicitly whether a durable byte copy **already existed before Phase B began** — if not, record `identity_basis: NOT_ESTABLISHED` (metadata inspection alone — row counts, date ranges, schema — is `OBSERVED_CURRENT_CORPUS` evidence, valid to support a FAIL per P0-R3's own §2.7 precedent, but not durable identity, and must not be described as such); if a pre-existing copy is found, Phase B **may** read-only verify it and, if verification succeeds, record `identity_basis: PREEXISTING_DOCUMENTED_BYTE_COPY`. **In neither case does Phase B create the copy itself** (§5, §8, §11).
- **AC-R4-23 (durable-identity gap forces the dependent gate to FAIL; a verified pre-existing copy is the one basis that avoids the downgrade).** *Given* a gate's status would otherwise be PASS but the evidence it rests on has `identity_basis: NOT_ESTABLISHED` per AC-R4-21/22. *When* that gap is found. *Then* the dependent gate's status is recorded **FAIL** (not "provisional PASS," not "PASS pending durability") until durable identity is separately established — either by a future, approved Phase C+ action, or (if applicable) already-existing and not yet located/verified. **A gate resting on `REACHABLE_COMMITTED_BLOB` or read-only-verified `PREEXISTING_DOCUMENTED_BYTE_COPY` evidence is not subject to this downgrade** — those are durable identity, not a gap — mirroring P0-R3's AC-R3-30 "the referencing gate FAILs until the durable identity is established" and §5's PASS/FAIL asymmetry rule exactly.

### 13.7 Gate R4-X — Forbidden derived-output substitution

- **AC-R4-24 (any reliance found invalidates the specific finding immediately).** *Given* any gate's evidence trail, at any point in this study, is found to rely on `obs_alpha.parquet`/`exec_ret.parquet`/any derived score panel. *When* this is discovered. *Then* the specific finding is struck immediately, and every gate result that depended on it is reopened and re-evaluated without that finding — this is not deferred to a periodic audit.
- **AC-R4-25 (derived outputs may be read for unrelated diagnostic purposes, never as source evidence).** *Given* a derived output (e.g. `realbody_scores_adv100w.parquet`, as P0-R3's own §6.2 read it once, read-only, purely to confirm a *downstream effect* of a coverage gap, not to establish the gap itself). *When* a future report does something similar. *Then* it must clearly distinguish "read to observe a downstream symptom" from "used as raw-source evidence" — the former remains permitted (mirroring P0-R3's own precedent), the latter is prohibited (§9).
- **AC-R4-26 (Gate R4-X audits continuously, not once).** *Given* Gate R4-X's cross-cutting nature (§10.8, §10.9). *When* any of the other 7 gates produces a new finding. *Then* that finding is checked against Gate R4-X's prohibition before being recorded as final — Gate R4-X is not a one-time end-of-study pass.

### 13.8 Dependency order and phase-gating

- **AC-R4-27 (each track's own upstream gate blocks only that track's downstream gates — no shared upstream gate).** *Given* Gate R4-A has not resolved (PASS or a definitive terminal finding) for Track A or Track B, **or** Gate R4-L has not resolved for Track C. *When* the corresponding downstream gates are considered — `R4-V` for Track A; `R4-H`/`R4-P`/`R4-S` for Track B; the Track-C-scoped `R4-D` evaluation for Track C. *Then* those downstream gates (and only those) are recorded `NOT_EVALUATED` — never scored ahead of their track's own upstream dependency, per §10.9's per-track matrix. **Gate R4-L's status has no bearing on Track A/B's downstream gates, and Gate R4-A's status has no bearing on Track C's** — a report that treats R4-L and R4-A as jointly gating every track's downstream work is itself a violation of this AC.
- **AC-R4-28 (R4-V/H/P/S block R4-D, per track).** *Given* `R4-V` (Track A) or `R4-H`/`R4-P`/`R4-S` (Track B) or `R4-L` (Track C) have not resolved for the evidence a Gate R4-D check would cover. *When* Gate R4-D is considered for that track's evidence. *Then* it is recorded `NOT_EVALUATED` for that track's evidence specifically — Gate R4-D is evaluated separately per track (§10.9 rule 6), never as one shared verdict across all three.
- **AC-R4-29 (upstream FAIL blocks remediation implementation for that track only, not the whole study, and never crosses tracks).** *Given* one track's own upstream gate FAILs (in the blocking sense) while another track's own upstream gate PASSes or reaches a definitive terminal finding. *When* §10.0's per-track admission rule is applied. *Then* only the FAILing track's remediation implementation is blocked — a Gate R4-L FAIL (Track C) never blocks Track A or Track B's diagnosis or remediation-implementation eligibility, and a Gate R4-A FAIL (Track A/B) never blocks Track C's, because no cross-track dependency exists in the first place (§10.9 rule 4) — this is a structural fact, not merely a favorable outcome that happens to hold.
- **AC-R4-30 (Phase B is read-only; any write requires separate approval).** *Given* Phase B is underway (once approved). *When* any action is considered that would download, import, backfill, transform, modify production/cache/Scheduler code, or create a data snapshot. *Then* that action does not proceed under this document's approval — it requires a separate, explicit, future approval, per §10.0/§11.
- **AC-R4-31 (terminal "not reconstructible"/"not remediable" findings are valid, complete results).** *Given* Track A, B, or C's diagnosis concludes that some or all of a dataset/track cannot be remediated (vintage unrecoverable, no successor found, live identity indeterminate). *When* this is reported. *Then* it is recorded as a complete, valid, non-blocking-of-the-study finding — the study does not treat this as an incomplete or failed deliverable requiring further searching beyond what §6/§7/§8's rules already require.

### 13.9 Cross-cutting prohibitions

- **AC-R4-32 (no P0-R3/P0-R2/P0-R1/P0-U1 reopening).** *Given* any phase of this study. *When* any report or design document is written. *Then* it must not modify, recompute, or reinterpret any prior study's archived gate result or conclusion — restated as testable per non-claim 5.
- **AC-R4-33 (no factor/formula/weight/fusion/performance-threshold change, ever).** *Given* any phase of this study, including any future remediation-implementation phase. *When* a design or code change is proposed. *Then* if it touches factor definitions, engine weights, fusion logic, or backtest performance thresholds, it is out of scope by construction and must be rejected or spun out to a separate, unrelated study — never bundled into P0-R4's own deliverables.
- **AC-R4-34 (no pre-commitment to remediability in any report).** *Given* any interim or final report this study produces. *When* it summarizes findings. *Then* it must not state or imply that remediation "will" succeed, is "expected" to succeed, or is merely "pending execution" — only what has actually been diagnosed, per the gates' actual PASS/FAIL/terminal-finding status, may be reported.
- **AC-R4-35 (Phase B creates zero byte copies — code or data, no exception; read-only verification of a pre-existing copy is the sole permitted interaction).** *Given* Phase B is underway. *When* any byte copy — of `core/data_provider.py`, `tej_importer.py`, any other code file, any TEJ/`market_cache`/`TEJ_RUNTIME_OVERLAY_DIR` data file, or any web page/document content read per §11.1 — is considered for **creation**. *Then* it does not proceed under this document's Phase A approval, **without exception**. Round-1 of this document carried a "code-evidence byte copy" exception under Phase B; **that exception is removed** (round 2) and remains removed. **The sole permitted interaction with a byte copy in Phase B is read-only verification of one that already existed before Phase B began** (§5, §8, AC-R4-17/21/22, round 3) — confirming its path/SHA256/bytes/verify-command/source-correspondence, never writing, copying, or modifying it. Every act of **creating** a byte copy, of every kind, for every purpose, remains a Phase C+-shaped action requiring its own separate, explicit, future approval — Phase B's evidentiary output is limited to path/SHA256/bytes/git-state records, read-only verification results, and citations (§8, §11, §11.1), never a copy of the underlying bytes that Phase B itself produced.

### 13.10 Traceability enforcement (feeds NFR-R4-6)

- **AC-R4-36 (0 orphan / 0 mapped-without-live, or the report does not finalize).** *Given* any `FR-R4-\*`, `NFR-R4-\*`, or `AC-R4-\*` lacks a bidirectional mapping — an FR/NFR with no covering AC in §14.4's tables, or an AC cited nowhere in §14.4 despite having a live definition in §13, or (the converse) an AC appearing in §14.4 with no corresponding live Given/When/Then definition in §13 (`mapped-without-live`) — at the time a Phase B completion report is assembled. *When* the traceability audit (the §14.7-style mechanical enumeration, re-run against that specific report's content, not merely against this prereg) is performed. *Then* `NFR-R4-6` **FAILs**, and the report **MUST NOT be finalized or archived** until the count reaches **0 orphan FR, 0 orphan NFR, 0 orphan AC, and 0 mapped-without-live** — this is a hard blocking condition on the report's own completion, not an advisory note or a "fix in the next round" item.

§14.4 maps every FR-R4-\*/NFR-R4-\* to the AC-R4-\* that verifies it, in both directions, with an explicit orphan check.

---

## 14. Mechanical specification

### 14.1 Functional requirements (FR-R4-\*)

| ID | Requirement | Feeds gate |
|---|---|---|
| FR-R4-1 | Resolve current live identity (path, SHA256, git state, runtime config, environment resolution) for `core/data_provider.py`, `tej_importer.py`, and `TEJ_RUNTIME_OVERLAY_DIR`. | R4-L |
| FR-R4-2 | Establish authoritative raw-source provenance (vendor/provider, official product name, access terms) for every dataset Track A/B considers, via read-only vendor-document browsing only (§11.1) — no download, no importer invocation, login/payment/download-gated evidence recorded `BLOCKED`/`UNAVAILABLE`. | R4-A |
| FR-R4-3 | Determine and, where separately authorized in a later phase, remediate full 255-canonical-month coverage for `monthly_revenue`, `institutional_gross`, `tdcc_weekly`. | R4-H |
| FR-R4-4 | Classify, per dataset and per affected sub-range, whether first-vintage historical values are reconstructible from a named, evidenced source. | R4-V |
| FR-R4-5 | Establish genuine, evidenced, actually-consumed per-row PIT availability semantics for `revenue_growth`(-or-successor), `financial_statements`, `institutional_gross`, `tdcc_weekly`. | R4-P |
| FR-R4-6 | Perform full-corpus (not sampled) schema/duplicate-key/missingness integrity checks for every dataset entering the qualification path. | R4-S |
| FR-R4-7 | Establish durable identity (reachable blob or documented byte copy) for every code/data file any gate's PASS relies on. | R4-D |
| FR-R4-8 | Continuously audit every gate's evidence trail for reliance on forbidden derived outputs. | R4-X |
| FR-R4-9 | Enforce first-vintage-only reconstruction discipline; never substitute a current/revised value for an unrecoverable first-vintage value. | R4-V |
| FR-R4-10 | Permanently and explicitly label any successor dataset as a new data definition, distinct from the original oracle identity it replaces. | R4-P |
| FR-R4-11 | Enforce phase-gating — Phase B is unconditionally read-only, zero byte copies of any kind (code or data); any write, transformation, or byte copy requires separate future approval, per the per-track admission rule. | §10.0/§11/§11.1 |
| FR-R4-12 | Enforce non-modification of P0-R3/P0-R2/P0-R1/P0-U1 results and of factor/formula/weight/fusion/performance-threshold logic, across all phases. | non-claims 5, 6 |

### 14.2 Non-functional requirements (NFR-R4-\*, measurable)

| ID | Requirement | Threshold |
|---|---|---|
| NFR-R4-1 | Full historical coverage. | 0 missing required months across the 255-canonical-month/full-market target, for every dataset in the qualification path. No general/blanket waiver. |
| NFR-R4-2 | Genuine PIT evidence. | 0 fixed-offset or zero-lag proxy datasets/fields in the qualification path; partial-coverage genuine evidence does not cure the un-cured portion. |
| NFR-R4-3 | Durable-identity coverage. | 100% of code/data files referenced by any gate's PASS have durable identity per §5 — no loose-hash-only identities. |
| NFR-R4-4 | Derived-output exclusion. | 0 uses of `obs_alpha.parquet`/`exec_ret.parquet`/any derived score panel as raw-source evidence, across every gate, continuously audited. |
| NFR-R4-5 | First-vintage integrity. | 0 substitutions of a current/revised value for an unrecoverable first-vintage value, across every historical reconstruction claim. |
| NFR-R4-6 | Traceability completeness. | 0 orphan FR, 0 orphan NFR, 0 orphan AC, 0 mapped-without-live at the time of any Phase B completion report — enforced as a hard blocking condition on that report's finalization/archival (AC-R4-36), not merely an advisory check. |

### 14.3 Data models

```
VintageAvailabilityRecord {
  dataset_name: str
  affected_range: { start: date, end: date }        # sub-range granularity, per AC-R4-4
  classification: "RECONSTRUCTIBLE" | "NOT_RECONSTRUCTIBLE"
  evidenced_source: str | null                       # named channel; null iff NOT_RECONSTRUCTIBLE
  reason_if_not_reconstructible: str | null
}

LiveIdentityRecord {
  target_path: str                                    # actual filesystem path inspected, read in place — never copied
  sha256: str                                          # computed by reading the file at target_path; no copy made
  bytes: int
  git_state: "clean_at_<commit>" | "modified" | "untracked"
  git_state_method: "windows_git_scoped"               # per §4, binding — never WSL-git-derived
  runtime_config: { env_var: str, resolved_value: str | null, source: "env" | "default" | "config_file" }[]
  production_instance_identified: bool
  production_instance_evidence: str | null             # how the "live" instance was identified; null iff not identified
  durable_identity_status: "REACHABLE_COMMITTED_BLOB" | "PREEXISTING_DOCUMENTED_BYTE_COPY" | "NOT_ESTABLISHED"
  preexisting_copy_verification: { path: str, sha256: str, bytes: int, verify_command: str,
                                    verify_command_reproduced_hash: bool,
                                    source_correspondence_confirmed: bool } | null
  # required (non-null), with both booleans true, iff durable_identity_status == PREEXISTING_DOCUMENTED_BYTE_COPY
  #
  # Phase B NEVER CREATES a byte copy (§5, §8, §11, AC-R4-17/35) — "DOCUMENTED_BYTE_COPY" (a copy Phase B or any
  # later phase actively makes) is not a value this record can ever take in Phase B. If git_state !=
  # "clean_at_<commit>" AND no independent byte copy is found to already exist, durable_identity_status MUST be
  # NOT_ESTABLISHED, and this record may support a FAIL finding but never a PASS (§5's asymmetry rule). If an
  # independent byte copy IS found to already exist and Phase B's read-only verification (above) succeeds,
  # durable_identity_status MUST be PREEXISTING_DOCUMENTED_BYTE_COPY, and this record MAY support a PASS —
  # this is verification of something that predates Phase B, never something Phase B produced.
}

ProvenanceCitation {
  url: str
  access_date: date
  quoted_or_paraphrased_content: str                   # brief citation only — not a saved copy of the page
  access_status: "ACCESSIBLE" | "BLOCKED_LOGIN_REQUIRED" | "BLOCKED_PAYMENT_REQUIRED" | "BLOCKED_DOWNLOAD_REQUIRED"
  # per §11.1: a BLOCKED_* status is a valid, terminal finding, not something Phase B attempts to work around.
}

DatasetSuccessorRecord {
  original_dataset: str
  successor_dataset: str | null                        # null iff no successor found
  successor_provenance: ProvenanceCitation[] | null      # feeds Gate R4-A; each citation per §11.1
  is_new_data_definition: true                          # always true when successor_dataset is non-null; permanent per AC-R4-9/13
  labeling_disclosure_text: str | null                  # the exact disclosure string to be reused verbatim in every future reference
}

CoverageRecord {
  dataset_name: str
  total_canonical_months: 255
  present_months: int
  missing_months: [date]                                # explicit list, never a shrunk denominator
  verdict: "SUFFICIENT" | "INSUFFICIENT"
}

PitEvidenceRecord {
  dataset_name: str
  field_name: str | null                                 # null if dataset-wide
  genuine_evidence_fraction: float                        # 0.0-1.0, fraction of rows/range with confirmed genuine evidence
  cutoff_semantics: { kind: "genuine_field" | "fixed_offset_proxy" | "unresolved", detail: str }
  consumed_by_producing_chain: bool                        # per AC-R4-10 — field presence alone is insufficient
  verdict: "PASS" | "FAIL"
}

IntegrityRecord {
  dataset_name: str
  files_checked: int
  files_total: int
  coverage_basis: "FULL_CORPUS" | "SAMPLE"                 # SAMPLE never yields SUFFICIENT, per AC-R4-14
  schema_variants: [{ n_files: int, columns: [[str,str]] }]
  duplicate_key_findings: str
  verdict: "SUFFICIENT" | "INSUFFICIENT" | "NOT_FULLY_EVALUATED"
}

DurableIdentityRecord {
  target: str                                             # code path or dataset name
  target_type: "code" | "data"
  identity_basis: "REACHABLE_COMMITTED_BLOB" | "PREEXISTING_DOCUMENTED_BYTE_COPY" | "DOCUMENTED_BYTE_COPY" | "NOT_ESTABLISHED"
  # Four distinct values, not three — round 3 splits the original "DOCUMENTED_BYTE_COPY" in two:
  #   REACHABLE_COMMITTED_BLOB        — a git-committed blob; Phase B may find and cite this directly.
  #   PREEXISTING_DOCUMENTED_BYTE_COPY — an independent byte copy that already existed BEFORE Phase B began,
  #                                      read-only verified by Phase B this round (§5, §8). Phase B MAY record
  #                                      this and MAY use it to support a PASS.
  #   DOCUMENTED_BYTE_COPY            — reserved exclusively for a byte copy a FUTURE, separately-approved
  #                                      Phase C+ action actively CREATES. A Phase B-authored record may NEVER
  #                                      use this value — doing so would misrepresent verification as creation.
  #   NOT_ESTABLISHED                 — neither of the above exists/verifies; supports FAIL only (§5).
  sha256: str | null
  bytes: int | null
  verify_command: str | null
  authored_in_phase: "B" | "C+"                            # Phase B records MUST NOT be "C+"; enforces the split above
}

# Per-track dependency (§10.9 — no single shared upstream gate across tracks):
#   Track A:  R4-A -> R4-V               -> R4-D
#   Track B:  R4-A -> {R4-H, R4-P, R4-S} -> R4-D
#   Track C:  R4-L -> R4-D
#   R4-X runs continuously across all of the above and is not itself downstream of anything.
GateResult {
  gate_id: "R4-L" | "R4-A" | "R4-V" | "R4-H" | "R4-P" | "R4-S" | "R4-D" | "R4-X"
  status: "PASS" | "FAIL" | "DECLARED_NOT_RECONSTRUCTIBLE" | "NOT_EVALUATED"
  track: "A" | "B" | "C" | "cross-cutting"
  depends_on: [gate_id]                                   # this track's own upstream gate(s) only, per the matrix above —
                                                           # e.g. R4-V's depends_on = ["R4-A"], never ["R4-A","R4-L"]
  evidence_refs: [str]
  reason_code: str | null
  scored_in_phase: "B" | null
  scored_at: iso8601
}
```

### 14.4 FR/NFR ↔ AC traceability (complete in both directions, no orphans)

**FR-R4-\* → covering AC-R4-\***

| FR | Covering AC(s) |
|---|---|
| FR-R4-1 | AC-R4-16, AC-R4-17, AC-R4-18, AC-R4-19 |
| FR-R4-2 | AC-R4-5, AC-R4-6, AC-R4-8 |
| FR-R4-3 | AC-R4-5, AC-R4-6, AC-R4-7 |
| FR-R4-4 | AC-R4-1, AC-R4-2, AC-R4-3, AC-R4-4 |
| FR-R4-5 | AC-R4-8, AC-R4-9, AC-R4-10, AC-R4-11, AC-R4-12 |
| FR-R4-6 | AC-R4-14, AC-R4-15 |
| FR-R4-7 | AC-R4-21, AC-R4-22, AC-R4-23 |
| FR-R4-8 | AC-R4-24, AC-R4-25, AC-R4-26 |
| FR-R4-9 | AC-R4-1, AC-R4-2 |
| FR-R4-10 | AC-R4-9, AC-R4-13 |
| FR-R4-11 | AC-R4-27, AC-R4-28, AC-R4-29, AC-R4-30 |
| FR-R4-12 | AC-R4-32, AC-R4-33 |

**NFR-R4-\* → covering AC-R4-\***

| NFR | Covering AC(s) |
|---|---|
| NFR-R4-1 | AC-R4-7 |
| NFR-R4-2 | AC-R4-12 |
| NFR-R4-3 | AC-R4-21, AC-R4-22, AC-R4-23 |
| NFR-R4-4 | AC-R4-24, AC-R4-25, AC-R4-26 |
| NFR-R4-5 | AC-R4-1, AC-R4-2 |
| NFR-R4-6 | AC-R4-36 |

**Reverse check:** every `AC-R4-1` through `AC-R4-36` appears in at least one FR/NFR row above except AC-R4-20, AC-R4-31, AC-R4-34, AC-R4-35, which are process/discipline criteria not tied to a single FR/NFR deliverable — they are covered directly by non-claims 3/7/8 and §11's phase-gating text, restated here rather than left as silent orphans: **AC-R4-20** (re-verification discipline) traces to FR-R4-1 (live identity must be current, not inherited); **AC-R4-31** (terminal findings are valid) traces to FR-R4-4/FR-R4-5 (the classification schemes themselves define terminal outcomes as first-class); **AC-R4-34** and **AC-R4-35** trace to FR-R4-11 (phase-gating discipline). **AC-R4-36** is directly mapped (NFR-R4-6, above) — it is the one AC in this document that formalizes an FR/NFR unmapped in round 1's draft, closing that gap rather than joining the process-criteria exception list. §14.7 performs the full mechanical count.

### 14.5 Edge cases

1. **A dataset is `RECONSTRUCTIBLE` (Track A) but still fails coverage (Track B).** Both findings are recorded independently and in full — Track A's success does not imply Track B's, and neither track's finding is suppressed or summarized away because the other track's answer differs.
2. **The live production instance cannot be identified at all (Track C).** Recorded as Gate R4-L FAIL (AC-R4-19), not as `NOT_EVALUATED`-and-silently-dropped. This does not block Track A/B's diagnosis from proceeding and being reported (AC-R4-29).
3. **A successor dataset is found for one field of a multi-field dataset but not others** (e.g. a hypothetical successor covering `revenue_yoy_pct`'s replacement but not some other `revenue_growth` column, if one existed). Each field is tracked in its own `DatasetSuccessorRecord`; a partial successor for one field never implies the dataset as a whole has been remediated.
4. **`market_cache`/`TEJ_RUNTIME_OVERLAY_DIR` content changes between P0-R3's 2026-08-15 observation and this study's own Phase B inspection.** Per AC-R4-20, the inertness finding must be re-verified, not inherited — if the content now overlaps the 255-month target range, this is a new, material finding requiring its own disclosure, not a silent update to an old footnote.
5. **A file is `git_state: modified`/`untracked`, with no durable identity established.** §5's rule does not carve out a "trivial diff" exception — any non-clean git state with no reachable committed blob still requires a documented byte copy before the content may be used to support a **PASS** (AC-R4-17/21), regardless of how small a diff might appear. The `OBSERVED_CURRENT_CORPUS`-basis path/SHA256/bytes/git-state record Phase B computes in this situation **remains valid, sufficient evidence to support a FAIL** finding (§5's asymmetry rule) — it is never discarded, only barred from supporting a PASS. **If a compliant `PREEXISTING_DOCUMENTED_BYTE_COPY` is separately found to already exist for that same file** — created before Phase B began, for whatever reason — Phase B **may** read-only verify it (path/SHA256/bytes/verify-command/source-correspondence), and if that verification succeeds, the file's evidence **may** then support a PASS (§8, §10.7, AC-R4-17/22/23). **Phase B never creates a copy itself to manufacture this outcome** — the PASS path exists only when the copy's pre-existence and correspondence are independently, read-only confirmed, never as something Phase B produces on demand to unblock a FAIL it would otherwise have to report.
6. **Track B identifies a successor dataset, and a later, separately-approved phase adopts it, but a still-later report forgets the labeling disclosure.** AC-R4-13 makes this a violation each time it recurs, not merely at first adoption — every reference requires the disclosure, checked at Gate R4-X-adjacent review, not assumed carried forward automatically.
7. **A dataset's schema drift (Gate R4-S) is later explained by a legitimate structure** (e.g. distinct `report_type` columns restoring key uniqueness, mirroring P0-R3's own AC-R3-3 pattern). This requires the explanation to be **written into an approved design document** (AC-R4-15) — an informal explanation in conversation or a code comment does not, by itself, resolve the FAIL.

### 14.6 API/CLI contract

**HTTP API: N/A.** This study has no network-facing service component at any phase.

**Offline CLI contract: deferred to Phase B.** This document does not fabricate command names, flags, or argument shapes for any lineage-tracing, coverage-checking, vintage-diagnosis, or live-identity-inspection tool — none has been designed yet. Phase B must specify and freeze the actual CLI/tooling contract (mirroring P0-R2's precedent of explicit `--` flags for frozen paths, never a tool resolving a live path itself) before any such tool may be implemented in a later, separately-approved phase.

### 14.7 Self-sufficiency check

**Full enumeration.** FR-R4-1 through FR-R4-12 (12 total): all 12 appear as rows with a non-empty covering-AC list in §14.4's FR table — **0 orphan FRs**. NFR-R4-1 through NFR-R4-6 (6 total): all 6 appear as rows in §14.4's NFR table, **each with a real covering AC** (NFR-R4-6 → AC-R4-36, added this round — round 1's draft had left this row self-referential/uncovered, now closed) — **0 orphan NFRs**. AC-R4-1 through AC-R4-36 (36 total, §13, including the new AC-R4-36 in §13.10): every one appears in at least one FR/NFR row in §14.4, or in the explicit reverse-check paragraph immediately following that table (AC-R4-20, 31, 34, 35) — **0 orphan ACs, 0 mapped-without-live** (no AC-R4-\* is cited in §14.4 without a live Given/When/Then definition in §13, confirmed by direct cross-read of both sections while drafting this document). This same enumeration method is what AC-R4-36 requires be re-run against any future Phase B completion report before that report may finalize.

**Generic spec-validator compatibility.** This document was not run through any external `spec_validator.py`-style tool this round (none was invoked). Per P0-R3's own §13.7.3 precedent, this document's actual completeness verification is §14.7's own mechanical FR/NFR/AC enumeration and its reverse mapping — a manual, item-by-item cross-check performed directly against this document's own text while drafting, not an unearned tool-reported "PASS" claim. If the user needs a generic validator to score this document, a future Phase B step (once approved) would be the point to transcribe these requirements into whatever machine-readable format that validator needs — out of scope for this drafting-only round.

---

## 15. Approval fields (avoiding self-reference)

```text
Status: APPROVED — Phase A (this document) approved; Phase B (read-only diagnosis, per §11) authorized. Phase C+ is NOT authorized by this approval.
User approval: APPROVED — 2026-08-16.
Approved scope (Phase B, read-only only):
  1. Read-only investigation of whether historical vintage (first-vintage values) exists for each dataset — Track A / Gate R4-V (§6).
  2. Read-only verification of authoritative raw-source provenance and PIT/availability documentation — Gate R4-A / Gate R4-P provenance evidence (§7.2-7.4, §10.2, §10.5), obtained only through §11.1's read-only browsing boundary.
  3. Read-only confirmation of 255-canonical-month coverage, schema, duplicate-key, and missingness integrity — Gate R4-H / Gate R4-S (§7.1, §7.5, §10.3, §10.6), full-corpus per AC-R4-14 (never sample-only for a SUFFICIENT verdict).
  4. Read-only confirmation of the actual live process, code, and environment-variable resolution — Track C / Gate R4-L (§8, §10.1), Windows-Git-scoped per §4.
  5. Checking whether durable identity already exists for code/data this study's gates rely on — Gate R4-D in existence-check-and-read-only-verify mode only (§5, §10.7) — reachable committed blob, or read-only verification of a byte copy that ALREADY EXISTED before Phase B began (`PREEXISTING_DOCUMENTED_BYTE_COPY`). Phase B does NOT create, copy, or modify any byte copy under any circumstance (§5, §8, §11, AC-R4-17/21/22/23/35).
Explicitly NOT authorized by this approval:
  - Downloading any raw dataset, export, attachment, or bulk archive from any TEJ/TDCC/vendor site, or invoking any importer/collector tool in any mode (§11.1 item 2).
  - Logging into, or paying for access to, any vendor/paid service — a login/payment/download-gated evidence item is recorded BLOCKED/UNAVAILABLE, never obtained (§11.1 item 3).
  - Any data import, backfill, or transformation of any dataset.
  - Any byte copy CREATION or MODIFICATION — of code or data, for any purpose, including "just to establish durable identity" (§5, §8, AC-R4-35). Read-only verification of an already-existing copy remains the sole permitted interaction (item 5 above).
  - Any data snapshot of any kind.
  - Any modification to `core/data_provider.py`, `tej_importer.py`, or any other production/cache/Scheduler code or configuration.
  - Any test or adapter code.
  - Any production or Task Scheduler operation.
  - Any other, unnamed Phase C+ remediation action of any kind — this document does not enumerate an exhaustive list of everything Phase C+ might eventually contain (§11 deliberately leaves its shape unspecified); anything not explicitly listed under "Approved scope" above remains unauthorized by default, not merely the items named here.
  Each of these requires its own separate, explicit, future user approval per §10.0/§11 — this approval does not extend to them.
Implementation authorized: NO. Phase B is read-only diagnosis, not implementation. No code, test, byte copy, snapshot, or production/cache/Scheduler write is authorized by this approval.
Approved repository baseline commit: f5dc275ef320c63e76b5cac49279f68cff286793 (confirmed at approval — verified as the current HEAD at approval time, §2.1).
Approved draft SHA256: 9ffd6a9b79ad932df8d94b7b36f34759c357ce3af9ab2c8ecdd649f6557f31a7 — the round-3 revision content exactly as it stood immediately before this approval-stamping edit; this is the exact content the user reviewed and approved.
Approval receipt: recorded externally in `docs/prereg_P0_R4_approval_receipt_2026-08-16.json` — per the self-reference-avoidance convention this section already establishes, this document does not, and must not, compute or embed its own post-stamp SHA256; that value (the SHA256 of this file as it exists on disk immediately after this approval edit) is recorded only in that external receipt file, together with the approved-draft SHA256 above and the repository baseline commit.
```

An `approval_receipt.json` was created as part of this approval event (`docs/prereg_P0_R4_approval_receipt_2026-08-16.json`), recording this document's post-stamp SHA256, byte count, line count, and git blob identity externally per the rule stated above. No research output directory, snapshot, manifest, test, byte copy, or any Phase B work product was created this round — Phase B has not begun. This approval event consists of document-stamping plus one external receipt file, precisely committed together (only these two files — see the receipt and the accompanying commit for the exact commit identity; this document does not embed its own commit SHA, to avoid the same self-reference this section already declines for its own content hash).

---

## 16. Drafting-round integrity statement

This document was produced by document editing only: a new prereg file, `docs/prereg_P0_R4_HistoricalRawSourceRemediation_PITIdentity_2026-08-16.md`, specifying a three-track (A: historical-oracle reconstruction, B: PIT-correct successor dataset, C: current live identity) investigation into the deficiencies P0-R3 archived as a `NULL_BLOCKED_RESULT` at commit `f5dc275ef320c63e76b5cac49279f68cff286793`. **No code tracing beyond re-citing P0-R3's own already-archived findings, no new corpus scan, no data execution, no download, no import, no backfill, no transform, no production/cache/Scheduler modification, and no snapshot of any kind occurred this round.** P0-R3's `NULL_BLOCKED_RESULT` and every artifact under `research/p0_r3_source_lineage/` remain exactly as archived — unread beyond what §2.2 cites verbatim from their already-known content, unmodified, uncommitted-to by this round. Only this one file was created (round 1) and then edited in place (round 2, this revision); no existing repository file outside it was modified.

**Round 2 summary:** removed Phase B's code-byte-copy exception entirely (§5, §8, §11, AC-R4-17, AC-R4-35 — Phase B is now unconditionally read-only, zero byte copies of any kind); replaced the single blurred cross-track dependency graph with an explicit per-track matrix (§3, §10.0, §10.2, §10.9, AC-R4-27/28/29, `GateResult.depends_on`); clarified Gate R4-D as an existence-check-only gate in Phase B with a binding PASS/FAIL asymmetry rule (§5, §10.7, AC-R4-22/23); added formal AC-R4-36 and closed NFR-R4-6's prior self-referential mapping (§13.10, §14.2, §14.4, §14.7); added an explicit external-document access boundary for Phase B, including the new `ProvenanceCitation` data model (§11.1, §14.3).

**Round 3 (this revision) summary:** distinguished Phase B *creating* a byte copy (still absolutely prohibited) from Phase B *read-only verifying* a byte copy that already existed before Phase B began (now explicitly permitted, and the only way a Phase B-scored gate may reach a durable-identity-backed PASS besides a reachable committed blob) — Gate R4-D's PASS basis is now `REACHABLE_COMMITTED_BLOB` or a verified `PREEXISTING_DOCUMENTED_BYTE_COPY`; `DOCUMENTED_BYTE_COPY` is reserved exclusively for a copy a future, separately-approved Phase C+ action creates, and a new `authored_in_phase` field on `DurableIdentityRecord` enforces that a Phase B record can never claim it (§5, §8, §10.7, §11, AC-R4-17/21/22/23/35, `LiveIdentityRecord`, `DurableIdentityRecord`). Edge case 5 (§14.5) rewritten to match: a modified/untracked file with no durable identity still supports only a FAIL; a verified pre-existing byte copy may support a PASS; Phase B never creates a copy to manufacture that outcome. This round remains document-only: no approval, no Phase B, no research artifacts, no byte copies (created or otherwise), no snapshot, no code/tests, no data download/import, no staging, no commit.
