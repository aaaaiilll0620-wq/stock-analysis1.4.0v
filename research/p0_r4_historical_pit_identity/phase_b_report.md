# P0-R4 Phase B — Read-Only Diagnosis Report

**Study:** P0-R4 — Historical Raw-Source Remediation, PIT Semantics, and Live Identity Resolution
**Phase:** B (read-only diagnosis) — authorized by Phase A approval, `docs/prereg_P0_R4_approval_receipt_2026-08-16.json`
**Executed:** 2026-08-16
**Corrected:** 2026-08-16 (two same-day correction passes, no new investigation — see the `correction_note` fields in `gate_results.json` and `live_identity_inventory.json` for the itemized list of what changed and why)
**Phase B execution compliance:** `PROTOCOL_DEVIATION` (reason code `UNAUTHORIZED_VENDOR_DOCUMENT_LOCAL_COPY_SIDE_EFFECT` — see §9). **This report is not a fully compliant Phase B completion.**
**Repository HEAD at execution:** `12c521dc51f3520f9489f0b69ce9714d906837f4` (one commit ahead of the approved baseline `f5dc275ef320c63e76b5cac49279f68cff286793` — the sole intervening commit, `12c521dc`, is the docs-only "freeze Phase A approval" commit; verified via `git.exe log f5dc275e..HEAD`, does not touch any file this study depends on)
**Windows Git used for all git-state claims:** `git.exe` version `2.54.0.windows.1` (re-verified this round, per §4 — version unchanged from P0-R3's citation)

**Binding disposition up front:** this report makes **no** remediation recommendation and commits to **no** future phase. It records what Phase B's read-only inspection actually found, per the prereg's own gates. **It does not claim zero byte copies were created this pass** — one was, as a tool-level side effect, and is disclosed in full in §9 rather than minimized. **Gate findings (R4-A/R4-L/R4-X, §§2–4) and Phase B execution compliance (this note, §9) are two separate questions; a clean or FAIL gate finding does not certify, and is not certified by, execution compliance.** Whether to accept, archive, or require remediation of this deviation is reserved to the human reviewer — this report does not decide it.

---

## 1. Scope actually executed vs. authorized

Executed: read-only inspection of already-existing files/config (local filesystem, Windows Task Scheduler, Windows registry, `git.exe`), and read-only browsing of TEJ/TDCC official public web pages (6 WebFetch/WebSearch calls, §11.1-scoped). No TEJ/TDCC raw dataset was downloaded or imported (`no_dataset_downloads_or_imports = true`); no importer/collector tool was invoked (`no_importer_invocations = true`); no production/cache/Scheduler file was modified; no test/adapter code was written; nothing was staged or committed. **One byte copy WAS created this pass, as an undisclosed-until-now tool-level side effect of a vendor-document web fetch — `no_byte_copies_created_this_phase = false`.** Full detail, known/unknown facts, and the resulting execution-compliance finding are in §9 — this is not folded into the "executed cleanly" framing above.

**Overall Phase B execution compliance: `PROTOCOL_DEVIATION`** (`UNAUTHORIZED_VENDOR_DOCUMENT_LOCAL_COPY_SIDE_EFFECT`, §9). This status is separate from, and does not average out against, the per-gate findings below.

Per-track diagnostic outcome, in one line each (independent of the execution-compliance finding above):

| Track | Upstream gate | Result | Downstream |
|---|---|---|---|
| A (`R4-A→R4-V→R4-D`) | R4-A | **FAIL** (all 8 datasets — licensing/access terms not found on any page reached, `AUTHORITATIVE_LICENSING_TERMS_NOT_ESTABLISHED`) | R4-V, R4-D(A/B) → `NOT_EVALUATED` |
| B (`R4-A→{R4-H,R4-P,R4-S}→R4-D`) | R4-A | **FAIL** (same) | R4-H, R4-P, R4-S, R4-D(A/B) → `NOT_EVALUATED` |
| C (`R4-L→R4-D`) | R4-L | **FAIL** — two independent reasons: durable-identity asymmetry downgrade (§5), and `tej_importer.py`'s live invocation context unresolved | R4-D(C) → **`NOT_EVALUATED`** (per §10.0 — not independently scored once R4-L FAILs) |
| cross-cutting | R4-X | **FAIL** — `DURABLE_IDENTITY_NOT_ESTABLISHED` (§5 asymmetry applies to the audit's own evidence trail); diagnostic content itself is clean (`NO_DERIVED_OUTPUT_RELIANCE_OBSERVED`) | — |

Full machine-readable detail: `gate_results.json`. Live-identity detail: `live_identity_inventory.json`. Web citations: `provenance_citations.csv`.

---

## 2. Track A / Track B — Gate R4-A (shared upstream)

**Method.** Read-only WebSearch + WebFetch against TEJ's official domain (`tejwin.com`) and TDCC's official domain (`tdcc.com.tw`), plus two attempted secondary sources (a university-library-hosted TEJ manual PDF; TEJ's own API catalog page). Every access recorded in `provenance_citations.csv` with URL, access date (2026-08-16), quoted/paraphrased content, and `access_status`. **Every page Phase B attempted this round was, in fact, reachable — `access_status` is `ACCESSIBLE` for all 13 citations.** No login/payment/download wall was ever actually encountered at any URL Phase B visited.

**Finding.** Vendor identity (Taiwan Economic Journal Co., Ltd., `tejwin.com`) is confirmed for all 8 P0-R3 D\* datasets. Official product names were additionally confirmed, directly from TEJ's own Taiwan-market database-solution page, for **7 of 8** datasets:

| dataset | official product name found | status |
|---|---|---|
| `price_valuation` | 上市(櫃)調整/未調整股價(日), 股價報酬(日)-報酬率 | found |
| `institutional_flow` | 三大法人買賣超 | found |
| `institutional_gross` | 三大法人買賣超 (family-level match only, no distinct "gross" name) | found (weak) |
| `tdcc_weekly` | 集保股權分散 / 集保庫存分散 | found |
| `industry_map` | 產業分類屬性 | found |
| `monthly_revenue` | 上市(櫃)月營收盈餘 | found |
| `financial_statements` | IFRS以合併為主簡表(累計)-全產業 | found |
| `revenue_growth` | *(none found)* | **not found — separate, additional gap** |

**Licensing/access terms could not be established from authoritative material for any of the 8 datasets, without exception — but this is not a login block.** TEJ's public pages simply do not contain a licensing/access-terms document; the site references a customer-login portal for services generally, but Phase B never attempted to enter it, and no page Phase B actually reached was itself gated behind login. The honest characterization is `AUTHORITATIVE_LICENSING_TERMS_NOT_ESTABLISHED` — absence of published terms on accessible material — not `BLOCKED_LOGIN_REQUIRED`, which would overclaim that Phase B hit a wall it did not hit.

**`revenue_growth` carries a second, independent gap.** Unlike the other 7 datasets, no distinct official TEJ product name for a per-row revenue-YoY-growth dataset was located on any page reached this round. This is listed separately from the licensing-terms gap that applies uniformly to all 8, because for `revenue_growth` even the product-name component — otherwise satisfied for the other 7 — was not established.

**Gate disposition.** §10.2 requires vendor identity **and** official product name **and** licensing/access terms, each documented from the provider's own materials, before Gate R4-A PASSes for a dataset. Since the licensing/access-terms component is uniformly unestablished, **Gate R4-A = FAIL for all 8 datasets.** This is recorded as a valid, complete, terminal finding (AC-R4-31) — not a defect requiring a workaround, and not a login-blocked outcome it was not.

**Consequence, per §10.9 / AC-R4-27 / AC-R4-28 (binding, and per instruction not to scan ahead of an upstream FAIL):**

- **R4-V (Track A):** `NOT_EVALUATED`. No `VintageAvailabilityRecord` was produced for any dataset/range. AC-R4-1 through AC-R4-4 are `NOT_EVALUATED`.
- **R4-H (Track B):** `NOT_EVALUATED`. No coverage-remediation-channel search was performed for `monthly_revenue`/`institutional_gross`/`tdcc_weekly`. AC-R4-5 through AC-R4-7 are `NOT_EVALUATED`. The `institutional_gross` docstring-vs-on-disk contradiction (AC-R4-6) was **not** resolved as a scored finding — see the one incidental, explicitly-unscored observation in `gate_results.json#R4-H` (surfaced by a single targeted grep while gathering Track C evidence, not a corpus scan; recorded transparently but must not be read as an R4-H result).
- **R4-P (Track B):** `NOT_EVALUATED`. AC-R4-8 through AC-R4-12 are `NOT_EVALUATED`.
- **R4-S (Track B):** `NOT_EVALUATED`. **No full-corpus schema/duplicate-key/missingness sweep of `tej_cache`/`market_cache` was performed.** Beyond the top-level directory-name listing already needed for Track C's `TEJ_RUNTIME_OVERLAY_DIR` evidence (folder names only, no file content read, no per-file counts, no schema inspection), zero per-file inspection occurred, by design, per §10.9's per-track blocking rule and the explicit stop-on-upstream-FAIL instruction. AC-R4-14/AC-R4-15 are `NOT_EVALUATED`.
- **R4-D, Track A/B evidence:** `NOT_EVALUATED` (AC-R4-28 — `NOT_EVALUATED` upstream gates do not count as "resolved", so R4-D is never reached for this evidence).

---

## 3. Track C — Gate R4-L (current live identity)

**Method.** Direct inspection of the actual production environment: Windows Task Scheduler (`schtasks.exe /query`), Windows registry (`reg.exe query` of both `HKCU\Environment` and the machine-wide `Session Manager\Environment`), an interactive `cmd.exe` environment-variable echo, `git.exe`-scoped status/diff/rev-parse, `sha256sum` of the live files read in place, and on-disk existence checks (metadata only) of the resolved default cache paths. No baseline-substitution shortcut was taken anywhere in this chain (§8's binding rule).

**`core/data_provider.py`'s live production consumption path is directly confirmed.** The Windows Scheduled Task `\FinMind_DailyUpdate` is registered, enabled, and its last run (2026-08-14 18:00) succeeded (result code 0). Its action is `powershell.exe run_hidden.ps1 daily_auto_update.bat`, running as user `jamie`. `daily_auto_update.bat` step 1 runs `python build_cache.py --build-scores --source tej ...`, and `build_cache.py` line 38 does `from core.data_provider import DataProvider` — this specific chain is direct, current, confirmed evidence.

**`tej_importer.py`'s live invocation context is a separate, unresolved question — not established either way.** Neither of the two currently-registered scheduled tasks found this phase (`FinMind_DailyUpdate`, `Market_SnapshotCollector`) references `tej_importer.py` by name in its action string. No other scheduled task, service, or deployment manifest was found referencing it. Per §11.1/AC-R4-30, Phase B did not invoke `tej_importer.py` itself to test whether it runs, and this correction pass performed no new search beyond what was already gathered. **This gap is recorded honestly as `TEJ_IMPORTER_LIVE_INVOCATION_UNRESOLVED` — neither confirmed live nor confirmed dormant.** Track C's overall identification of "what production actually reads, right now" (§8's charge, covering `core/data_provider.py`, `tej_importer.py`, and the `TEJ_RUNTIME_OVERLAY_DIR` mechanism together) is therefore **partial, not complete** — this report does not claim otherwise.

**Environment resolution: checked, not assumed (AC-R4-18).** `TEJ_CACHE`, `TEJ_RUNTIME_OVERLAY`, and `MARKET_CACHE` are absent from both the user (`HKCU\Environment`) and machine (`HKLM\...\Session Manager\Environment`) registry hives (both queries succeeded, `RC=0`, both fully enumerated) and are unresolved in an interactive `cmd.exe` shell. All three therefore resolve to their coded defaults:

- `TEJ_CACHE_DIR` → `C:\Users\aaaai\tej_cache` (confirmed to exist on disk)
- `MARKET_CACHE_DIR` → `C:\Users\aaaai\market_cache` (confirmed to exist on disk)
- `TEJ_RUNTIME_OVERLAY_DIR` → `<project_root>\data\runtime_cache\dataexport0806` (confirmed to exist on disk)

**Overlay inertness re-verified, not inherited (AC-R4-20).** `data/runtime_cache/dataexport0806/receipt.json` was re-read this phase: `financial_statements` date_min=date_max=2026-06-01 (596 stocks), `monthly_revenue` date_min=date_max=2026-07-01 (406 stocks) — both single-month, both outside the 255-canonical-month target range (2005-01-31→2026-03-31). Directory mtimes (2026-08-10) are unchanged since P0-R3's 2026-08-15 citation. **Content confirmed unchanged, not merely assumed still true.**

**Git state (Windows-Git-scoped, §4).** Both files are `modified`: `core/data_provider.py` (69 lines changed) and `tej_importer.py` (2,272 lines changed, 434→2,156) — exactly matching P0-R3 §2.2's figures. Live SHA256 (`93f835b6...`, `c237f6a9...`) does **not** match the committed blob at HEAD (`fd197dc4...`, `77306c32...`) — direct, current confirmation that the committed baseline is not what production executes.

**Durable identity: `NOT_ESTABLISHED`.** A repository-wide filename search (`data_provider*.py`, `tej_importer*.py`) found no independent byte copy anywhere outside the two live working-tree files themselves. No `PREEXISTING_DOCUMENTED_BYTE_COPY` exists to verify. Phase B created none.

**Gate disposition — two independent reasons, both stated plainly.** Gate R4-L is recorded **FAIL** for two separate reasons, neither of which alone should be mistaken for the other:

1. **`TEJ_IMPORTER_LIVE_INVOCATION_UNRESOLVED`** — Track C's identification is genuinely incomplete: `tej_importer.py`'s live invocation context was not established. §10.1 requires the `LiveIdentityRecord` to be complete and to resolve to a single, unambiguous statement of what production reads — it does not, for this file.
2. **`LIVE_CONTENT_NONDURABLE_ASYMMETRY_DOWNGRADE`** — even where identification *is* complete (`core/data_provider.py`'s consumption path), §5's binding PASS/FAIL asymmetry rule (restated AC-R4-23, applying to "any gate") requires that a result resting on `OBSERVED_CURRENT_CORPUS`-basis evidence (a single read of the live files' current bytes, `git_state=modified`, no durable copy) be downgraded to FAIL regardless of how complete the identification is.

This report does **not** claim Track C's production identity is "complete and unambiguous" and then merely note a technical downgrade — one real piece of the identification (`tej_importer.py`'s invocation) remains genuinely open, and that alone would independently FAIL the gate even before the durable-identity question is considered.

**Gate R4-D, Track C evidence: `NOT_EVALUATED`, not FAIL.** Per §10.0's explicit Track C rule — "if Gate R4-L FAILs ..., Track C's R4-D evaluation for Track C's own evidence is `NOT_EVALUATED`" — Gate R4-D is **not** independently scored once R4-L has FAILed. The durable-identity gap described above (no reachable committed blob for the live content, no pre-existing byte copy, none created) remains recorded solely as part of Gate R4-L's own finding; it is not re-scored ahead of it as a separate R4-D(C) verdict.

---

## 4. Gate R4-X (continuous, cross-cutting)

Every evidence source this Phase B pass actually used was enumerated and checked (see `gate_results.json#R4-X`): `git.exe` output, `sha256sum` of code/config/manifest files, `reg.exe`/`schtasks.exe`/`cmd.exe` output, top-level directory-name listings of `tej_cache`/`market_cache`, `data/runtime_cache/dataexport0806/receipt.json`, and 6 web accesses to `tejwin.com`/`tdcc.com.tw`/`api.tej.com.tw`/a university mirror. **None references `obs_alpha.parquet`, `exec_ret.parquet`, any `realbody_scores*.parquet`, or any `beat_0050`/`scripts/*_lab.py` output.** This diagnostic result — `NO_DERIVED_OUTPUT_RELIANCE_OBSERVED` — is genuinely clean.

**But the gate's own scored status is `FAIL`, not `PASS`.** §5's binding PASS/FAIL asymmetry rule applies, by its own text, to "any gate" — and Gate R4-X's own audit is itself a single, one-time, non-durably-archived enumeration (`OBSERVED_CURRENT_CORPUS`-basis evidence about this phase's evidence trail, with no committed blob or pre-existing byte copy of that trail). A clean-looking audit computed from such evidence is exactly the case §5 says "is not 'provisionally PASS pending durability,' it is FAIL until durable identity is established." Gate R4-X is therefore recorded **FAIL**, `reason_code: DURABLE_IDENTITY_NOT_ESTABLISHED`, with its clean diagnostic content preserved separately as `diagnostic_observation: NO_DERIVED_OUTPUT_RELIANCE_OBSERVED` — the two fields must be read together, not conflated. Per AC-R4-26, this audit is not a one-time clearance regardless of its status and must be re-run against any future phase's new findings.

---

## 5. Explicit list — what was NOT_EVALUATED and why

| Check | Status | Reason |
|---|---|---|
| `VintageAvailabilityRecord` for any of the 8 datasets (Track A, §6) | NOT_EVALUATED | Upstream R4-A FAIL blocks R4-V (§10.9 rule 1) |
| Coverage-remediation-channel search, `monthly_revenue`/`institutional_gross`/`tdcc_weekly` (§7.1) | NOT_EVALUATED | Upstream R4-A FAIL blocks R4-H (§10.9 rule 2) |
| `institutional_gross` docstring-vs-on-disk contradiction resolution (AC-R4-6) | NOT_EVALUATED (one unscored incidental observation only, see §2 above) | Same |
| `revenue_growth` successor search (§7.2) | NOT_EVALUATED | Upstream R4-A FAIL blocks R4-P |
| `financial_statements` `release_date`-consumption code check (§7.3) | NOT_EVALUATED | Same |
| `institutional_gross`/`tdcc_weekly` evidenced-lag determination (§7.4) | NOT_EVALUATED | Same |
| Full-corpus schema/duplicate-key/missingness sweep, any dataset (§7.5) | NOT_EVALUATED | Upstream R4-A FAIL blocks R4-S; **no premature scan performed** |
| Gate R4-D for Track A/B evidence | NOT_EVALUATED | R4-V/H/P/S all NOT_EVALUATED (AC-R4-28) |
| **Gate R4-D for Track C evidence** | **NOT_EVALUATED** | **Upstream R4-L FAIL blocks R4-D for Track C, per §10.0's explicit rule — not independently pre-scored ahead of R4-L; the durable gap is preserved only as an R4-L finding** |
| `tej_importer.py` live invocation context | NOT_EVALUATED / genuinely unresolved (`TEJ_IMPORTER_LIVE_INVOCATION_UNRESOLVED`) | No registered scheduled task references it by name; not invoked to test this (§11.1/AC-R4-30); this is itself one of Gate R4-L's two FAIL reasons, not merely a footnote |

---

## 6. Traceability audit (AC-R4-36 / NFR-R4-6 — hard blocking condition)

Mechanical re-enumeration, run against **this corrected report's own content**, per AC-R4-36's requirement.

**FR-R4-1 through FR-R4-12 (12 total):**

| FR | Addressed this phase | Covering AC(s) present in this report |
|---|---|---|
| FR-R4-1 | Partially — §3 (live identity resolution attempted; `core/data_provider.py`'s path confirmed, `tej_importer.py`'s invocation unresolved — both outcomes, complete and incomplete, are within this FR's scope of "resolve current live identity") | AC-R4-16, 17, 18, 19 |
| FR-R4-2 | Yes — §2 (R4-A executed, FAIL recorded) | AC-R4-5, 6, 8 |
| FR-R4-3 | NOT_EVALUATED (§5) — requirement itself unreached, not orphaned | AC-R4-5, 6, 7 |
| FR-R4-4 | NOT_EVALUATED (§5) | AC-R4-1, 2, 3, 4 |
| FR-R4-5 | NOT_EVALUATED (§5) | AC-R4-8, 9, 10, 11, 12 |
| FR-R4-6 | NOT_EVALUATED (§5) | AC-R4-14, 15 |
| FR-R4-7 | Yes — §3/§4 (R4-D scored NOT_EVALUATED for Track C per §10.0, NOT_EVALUATED for Track A/B; durable-identity discipline applied throughout, including to R4-X itself) | AC-R4-21, 22, 23 |
| FR-R4-8 | Yes — §4 (R4-X audit run; clean diagnostic result, gate status correctly FAIL per §5) | AC-R4-24, 25, 26 |
| FR-R4-9 | N/A this phase (Track A not reached) — discipline restated in non-claims, not violated | AC-R4-1, 2 |
| FR-R4-10 | N/A this phase (no successor identified — R4-P not reached) | AC-R4-9, 13 |
| FR-R4-11 | Yes — §1/§2/§3 (phase-gating enforced throughout, including the correction that R4-D(C) must not be pre-scored ahead of R4-L) | AC-R4-27, 28, 29, 30 |
| FR-R4-12 | Yes — no prior-study or factor/weight/fusion logic touched anywhere in this report | AC-R4-32, 33 |

12/12 FR rows present with a non-empty covering-AC list → **0 orphan FR.**

**NFR-R4-1 through NFR-R4-6 (6 total):**

| NFR | Status this phase | Covering AC |
|---|---|---|
| NFR-R4-1 | NOT_EVALUATED (R4-H not reached) | AC-R4-7 |
| NFR-R4-2 | NOT_EVALUATED (R4-P not reached) | AC-R4-12 |
| NFR-R4-3 | Evaluated — 0% of the code-identity evidence this phase relied on (R4-L's two files, and R4-X's own audit trail) has durable identity; correctly recorded FAIL/NOT_EVALUATED throughout, never silently passed. R4-D(C) is correctly `NOT_EVALUATED` rather than an independently pre-scored FAIL, per the §10.0 correction in this pass. | AC-R4-21, 22, 23 |
| NFR-R4-4 | Evaluated — 0 derived-output uses found in this phase's evidence trail (`diagnostic_observation: NO_DERIVED_OUTPUT_RELIANCE_OBSERVED`), but per §5's asymmetry rule the gate's own scored status is FAIL, not PASS — a clean diagnostic result is not the same claim as a durably-established PASS, and this report does not conflate the two. | AC-R4-24, 25, 26 |
| NFR-R4-5 | NOT_EVALUATED (R4-V not reached) | AC-R4-1, 2 |
| NFR-R4-6 | Evaluated **by this very audit** | AC-R4-36 |

6/6 NFR rows present with a real covering AC → **0 orphan NFR.**

**AC-R4-1 through AC-R4-36 (36 total):** every AC appears in at least one FR/NFR row above, or in the reverse-check set the prereg itself names as process/discipline criteria (AC-R4-20, 31, 34, 35 — traced to FR-R4-1/FR-R4-4-5/FR-R4-11 respectively, exactly as §14.4's reverse-check paragraph specifies) — all four were actively applied this phase (AC-R4-20 in §3, AC-R4-31 in §1/§2/§5, AC-R4-34 in this report's own framing, AC-R4-35 in §3/§4/§9). **0 orphan AC.**

**Mapped-without-live check:** every AC cited anywhere in this §6 (AC-R4-1 through AC-R4-36, all 36) has a live Given/When/Then definition in the prereg's own §13 — this report defines no new AC and reinterprets none. **0 mapped-without-live.**

**Result: 0 orphan FR, 0 orphan NFR, 0 orphan AC, 0 mapped-without-live.** Per AC-R4-36, this report is eligible to finalize.

---

## 7. New files this round, with SHA256

*(All 4 files were corrected in place this pass — no new files were created; the 4 files below are the same 4 named in the original brief. Hashes reflect the corrected content, computed after all edits — see the assistant's closing turn of this conversation for the exact final values.)*

| file |
|---|
| `research/p0_r4_historical_pit_identity/phase_b_report.md` |
| `research/p0_r4_historical_pit_identity/gate_results.json` |
| `research/p0_r4_historical_pit_identity/live_identity_inventory.json` |
| `research/p0_r4_historical_pit_identity/provenance_citations.csv` |

No other file was created or modified this pass. `git.exe status` confirms these 4 files (already untracked from the original issuance) only; nothing is staged; no commit was made.

---

## 8. Non-claims (binding, restated)

This report does not claim: that any dataset's coverage or PIT-availability gap is remediable or irremediable (Track B was not reached); that any first-vintage value is or is not recoverable (Track A was not reached); that TEJ's licensing terms are favorable, unfavorable, or determinable without an institutional login (they were not determined, and Phase B did not actually test whether login is required — only that terms are absent from what it did reach); that `revenue_growth` has no TEJ successor product (only that none was found on the publicly reachable pages this round); that `tej_importer.py` is or is not invoked by some mechanism outside the two registered scheduled tasks this phase found (only that no evidence of such invocation was found — genuinely unresolved, not resolved-to-false); **that Gate R4-L's FAIL means production is unidentified (identification is partial: `core/data_provider.py`'s path is confirmed; `tej_importer.py`'s invocation is not) — and this report does not claim identification was "complete and unambiguous" anywhere, correcting the original issuance's overstatement on this point**; and that Gate R4-X's FAIL means forbidden derived-output reliance was found (the opposite is true — the diagnostic observation is clean; the FAIL is a durable-identity asymmetry downgrade of the audit's own evidence, not a violation finding. Both must be read together, not conflated). No factor, formula, weight, fusion, or performance-threshold logic was touched, read for its values, or referenced anywhere in this phase (non-claim 6). No P0-R1/R2/R3/U1 artifact was modified, recomputed, or reinterpreted (non-claim 5) — P0-R3's §2.2 figures were re-cited and, where checkable this phase (git diff line counts, overlay receipt content), independently re-confirmed, never taken on faith alone.

---

## 9. Phase B execution compliance — `PROTOCOL_DEVIATION` (not remediated, not minimized)

**This is not a "compliance note" appended to an otherwise-clean pass — it is the headline execution-compliance finding for this Phase B pass, and it is negative.**

While gathering Gate R4-A evidence, a `WebFetch` call to `https://erm.lib.scu.edu.tw/scuerm/userdownload/TEJ+_S_TCHINESE.pdf` — a university-library-hosted mirror of TEJ's own database operation manual — **downloaded that vendor-authored document, and the fetch tool auto-saved a local binary copy of it to a tool-scratch path outside this repository.** This is an actual byte copy of downloaded vendor material that did not exist before this Phase B pass and does now. Phase B's approved scope (§5, §8, §11, §11.1, AC-R4-17/21/22/35) is unconditionally read-only with **zero byte copies of any kind, no exception** — this event is squarely inside what that scope prohibits.

**What does and does not mitigate this:**

- It does **not** change the fact that a byte copy was created. `no_byte_copies_created_this_phase` is recorded `false` in `gate_results.json`, not `true`-with-a-footnote.
- It **does** inform the *impact* assessment: the copy was produced mechanically by a tool call, not by a deliberate Phase B file-write action; and no finding in this study reads, cites, or depends on that copy's content (no legible text was ever extracted from it — see `provenance_citations.csv` row 12). These are genuine, relevant facts — but they belong in the impact/non-claim record, not as a basis for describing this pass as byte-copy-free.

**Known and unknown facts about the saved copy** (recorded, not further inspected — opening, hashing, or deleting the file is out of scope for this correction and was not done):

| field | value |
|---|---|
| URL fetched | `https://erm.lib.scu.edu.tw/scuerm/userdownload/TEJ+_S_TCHINESE.pdf` |
| scratch path (as reported by the fetch tool) | `/home/jamie/.claude/projects/-home-jamie/e3cb5994-9f0b-494f-8ecb-ecf3daa0feac/tool-results/webfetch-1786864423275-tnkz0u.pdf` |
| content type (as reported) | `application/pdf` |
| approximate size (as reported, not re-measured) | `~3.1MB` |
| exact bytes | `UNKNOWN / NOT_INSPECTED` |
| SHA256 | `UNKNOWN / NOT_INSPECTED` |
| currently exists on disk | `UNKNOWN / NOT_INSPECTED` |

**Overall finding:** `phase_b_execution_compliance = "PROTOCOL_DEVIATION"`, `reason_code = "UNAUTHORIZED_VENDOR_DOCUMENT_LOCAL_COPY_SIDE_EFFECT"`.

**This finding is separate from the gate diagnostic findings in §§2–4, in both directions.** Gate R4-A/R4-L/R4-X's FAIL statuses are not evidence of, and do not excuse, this deviation; conversely, this deviation does not invalidate or reopen those gates' own evidentiary findings, which rest on their own separately-cited evidence. **This Phase B pass, taken as a whole, is not reported as a fully compliant Phase B completion.** No further action (deletion, inspection, or otherwise) has been taken on the saved PDF copy this pass, per this correction's own explicit instruction not to add new inspection or deletion. **Whether to accept this deviation, archive this report as-is, require a remediation action, or take any other disposition is reserved entirely to the human reviewer — this report neither recommends nor presumes an answer.**

Separately, on `ProvenanceCitation.access_status`: every citation in `provenance_citations.csv` (13 rows) is expressed using the prereg's existing four-value enum (`ACCESSIBLE` throughout — no citation actually required login, payment, or a gated download at the access-gating level; rows 12–13 were reachable but yielded no extractable content, which is a content-extraction fact, not an access-gating one). No document erratum is being raised on the enum itself.

---

## 10. Disposition

**Execution compliance:** `PROTOCOL_DEVIATION` (§9) — a real, disclosed deviation from Phase B's read-only/zero-byte-copy scope, arising from a vendor-document PDF fetch's tool-level side effect. This is the pass's headline compliance status and is not superseded by the gate findings below.

**Diagnostic findings** (evaluated on their own evidentiary merits, independent of the compliance finding above):

Track A: `DECLARED_NOT_REACHED` (R4-A FAIL blocks it structurally; no per-dataset vintage finding was attempted or produced).
Track B: `DECLARED_NOT_REACHED` (same).
Track C: **terminal — R4-L FAIL for two independent reasons (`TEJ_IMPORTER_LIVE_INVOCATION_UNRESOLVED`, `LIVE_CONTENT_NONDURABLE_ASYMMETRY_DOWNGRADE`); R4-D(C) correctly `NOT_EVALUATED` per §10.0, not independently scored.** This is not an open question awaiting more diagnosis within this phase; it is a complete Phase B finding for Track C (AC-R4-31), though it explicitly leaves `tej_importer.py`'s live invocation status as a genuinely unresolved fact, not a downgraded-but-otherwise-known one.
Cross-cutting: R4-X's diagnostic content is clean, but its scored status is FAIL under §5's asymmetry rule — a finding about the durability of this phase's own evidence trail, not about any forbidden-output violation.

Any Phase C+ action for any track — including, for Track C, creating a durable byte copy of the live `core/data_provider.py`/`tej_importer.py` content, or investigating `tej_importer.py`'s actual invocation context further — requires its own separate, explicit, future user approval (§10.0/§11). This report requests none and assumes none. Any remediation of the §9 deviation likewise requires its own explicit user decision, not an action this report takes on its own initiative.

**Awaiting human review — both of the diagnostic findings and of the disclosed protocol deviation. No further action taken.**
