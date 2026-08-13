# P0-R2 Phase H — History Gap Diagnosis Report

**Status:** Phase H complete (read-only diagnosis only). Phase B/C/D/E/F/G NOT started.
**Run date:** 2026-08-13
**Repository baseline commit:** `0337af0ce27a9c9781bb901ee6c7701e6afb016f`
**Approval commit (Stage 1 freeze):** `4e99e2fbd55d44c3c96bceb4a3607fdf5b9202de`
**Companion files:** `history_gap_timeline.csv`, `history_gap_findings.json` (this report summarizes them; the JSON is authoritative for exact evidence refs).

---

## 0. Scope and method

This diagnosis is read-only per FR-7/AC-2. All evidence was gathered via `git log`/`git show`/`git log -S` (pickaxe), filesystem mtimes, read-only `pandas`/`pyarrow` reads of committed and working-tree Parquet/CSV content, and `grep` across tracked source. No Scores, c2_fullpool, `cloud_cache/`, scheduling configuration, or production state file was created, moved, deleted, or modified. Two protected files (`core/score_store.py`, `scripts/universe_screen_daily.py`) were hash-verified against **independent** hashes recorded by P0-R1 one day earlier (`research/p0_r1_research_production_identity/preflight.json`, 2026-08-12) — both match exactly, confirming no drift.

---

## 1. Headline finding

**P-A and P-B's short production history is explained by `NOT_PRODUCED`, with high confidence, for both sources.** The code that produces each dataset simply did not exist before the dates already known from P0-R1:

- **P-A** (`core/score_store.py`, the composite-score cache): introduced in commit `50abd0dd` (2026-07-11, "deploy: streamlit app + scores snapshot"). `git log --follow` finds no ancestor. The very first committed snapshot — from that same commit — already contains only `as_of=2026-07-09` (one row per mode). There is no period where the mechanism ran and was later deleted; it simply began existing on 2026-07-11 and its first output was already the "recent history so far" (2026-07-09).
- **P-B** (`c2_fullpool_{as_of}.csv`, the full-pool c2 percentile output): the code has **never been committed to git** — `git log -S"c2_fullpool"` returns zero matching commits across the entire history of `scripts/universe_screen_daily.py`. It exists only in the current **uncommitted** working-tree diff. The diff's own comment self-dates it: *"全池 c2(2026-08-10 新增,附加輸出,不影響上面既有的 pool/shortlist)"*. The script's filesystem mtime (2026-08-10 21:09) agrees. Even the earliest output file (`as_of=2026-08-07`) was demonstrably **backfilled on 2026-08-10** — its own mtime is 2026-08-10, and the job log for the actual scheduled run that executed on 2026-08-07 contains zero mentions of `c2_fullpool`/`全池`.

Neither gap is a mystery requiring further investigation to close the main question P0-R1 raised (`comparable_dates=0` against a 255-month research baseline). The production mechanisms for both P-A and P-B are recent (July 11 and August 10, 2026 respectively); there is no lost history to recover because none was ever produced before those dates.

---

## 2. Secondary finding: partial truncation inside the P-A deployment mirror

`cloud_cache/Scores/` (the git-tracked, Streamlit-Cloud-facing mirror of P-A) is **not an independent archive** — `deploy_scores.py` performs a full `shutil.rmtree` + `shutil.copytree` of the entire directory on every successful scheduled run, i.e. a same-day wholesale mirror of whatever the local `finmind_cache/Scores/` cache currently contains. It cannot preserve history the local source doesn't have, which is why its date range matches P-A's exactly.

Within that short window, three specific tickers — `0050`, `1101`, `1201` — had their `cloud_cache/Scores/*.parquet` files reduced to **exactly 0 bytes** in a single commit (`817b9d59`, 2026-07-23, "重同步 cloud_cache/Scores 為新 schema"), while other tickers were resized (schema-migrated, content preserved) in the same commit. This is a genuine, well-evidenced `OVERWRITTEN_OR_TRUNCATED` event at the artifact level. Two candidate upstream mechanisms exist in the surrounding evidence and were **not** fully disambiguated:

1. A same-day scheduled-task crash (`exit 255`, documented in commit `f5d2e42f`'s message, "排程建分成功但 wscript 中途死於 255, 手動補 deploy"), or
2. A universe redefinition two days earlier (2026-07-21: switched from a 45-stock watchlist to an ~900-stock TEJ pool), under which `0050` (a benchmark, never a stock-selection candidate) and possibly `1101`/`1201` would legitimately fall out of the locally-scored universe and thus out of the next mirror refresh.

This does not change the primary conclusion and is reported for completeness per FR-1's per-source granularity requirement.

---

## 3. P-B has no deployment mirror

`cloud_cache/UniversePool/` looks superficially similar (it holds `pool_*.csv`) but is a **different artifact**: its percentiles (`*_pool_pct`) are computed over the L0–L2-filtered (PE-valid, non-trap) population, not the unfiltered ADV≥100萬 population that `c2_fullpool_*.csv` (`*_full_pct`) uses. `deploy_scores.py`'s sync scope (read directly from source) only ever touches `Scores` and `UniversePool` (shortlist/pool/digest) — `c2_fullpool` is never referenced. There is no "elsewhere" copy of P-B anywhere in the repository or its history.

---

## 4. Operational risk note (not a cause code, but material)

The P-B production code is **currently uncommitted**. If this working tree were ever reset, cleaned, or freshly re-cloned, `c2_fullpool` generation would stop entirely on that copy — there is exactly one machine-state in existence where this capability currently works. This is independent of the history-gap question but directly relevant to the Collector's durability requirements (NFR-2, NFR-9) and worth surfacing before Stage 2 designs around P-B as a source.

---

## 5. Scheduling record

Two Windows Scheduled Tasks are defined in-repo: `FinMind_DailyUpdate` (weekdays 18:00, `scripts/register_daily_task.ps1`) and a separate market-snapshot collector (17:30). Job logs (`outputs/logs/daily_update_*.log`) and marker logs (`%LOCALAPPDATA%\FinMind\daily_update_*.marker.log`) survive under a 30-day retention window and cover 2026-07-15 through 2026-08-12 without further gaps besides the documented 2026-07-17 manual-run day and the 2026-07-22 crash. A previously-undiagnosed 5-day silent cloud-deployment stall (2026-08-03–08-07, wrong git push branch) is also documented in `deploy_scores.py`'s own comments and has since been fixed with a fail-closed branch check.

Live Windows Task Scheduler run-history (beyond what these logs capture) was **not** queried — this session's environment is not confirmed to be the same physical machine that executes the registered task, and a direct `schtasks` query failed with a tooling error rather than a meaningful result. Marked `NOT_AVAILABLE` per FR-2/EC-15, not inferred as absence.

---

## 6. Cleanup/pruning risk to future Collector evidence roots (FR-9)

A repository-wide, read-only search found **exactly two** active, currently-running cleanup mechanisms:

1. `scripts/daily_auto_update.bat` (lines 123–128): 30-day `forfiles` prune, narrowly scoped to `outputs\logs\daily_update_*.log` and `%LOCALAPPDATA%\FinMind\daily_update_*.marker.log`.
2. `deploy_scores.py`: daily wipe-and-recopy of two named, git-tracked directories, `cloud_cache/Scores/` and `cloud_cache/UniversePool/`.

No generic, wildcard, or path-independent cleanup routine exists anywhere else in the tracked codebase.

**Finding: `active_cleanup_or_pruning_affecting_evidence_roots = FALSE`**, conditioned on Stage 2's eventual Primary/Mirror evidence roots avoiding those three specific locations/patterns — which they already must, structurally, under FR-37/FR-40 (new, independent, gitignored paths, outside `cloud_cache/`). This condition is cheap to mechanically re-verify once concrete paths are proposed in Stage 2, and Gate C-A should do so explicitly before Activation. As a related, non-binding recommendation: the project already has an established convention (`core/data_cache.py:29`, `build_cache.py:16`) of keeping the live production cache **outside** OneDrive sync specifically to avoid the kind of file-locking interference that was an open suspect in the 2026-07-22/23 scheduling crashes — the same siting choice is worth following for evidence roots.

---

## 7. Unresolved items (explicitly listed, not guessed)

- Exact causal mechanism for the 2026-07-23 zeroing of `cloud_cache/Scores/{0050,1101,1201}.parquet` (crash vs. universe redefinition vs. both).
- Live Task Scheduler run-history beyond job/marker logs — `NOT_AVAILABLE`.
- Whether any `daily_update_*.log`/`marker.log` before 2026-07-15 ever existed and was pruned by the 30-day retention job, versus never having existed — cannot be determined, because the retention job is itself evidence-destroying by design. `NOT_AVAILABLE` per EC-15; **not** treated as proof of non-production for that earlier window (none was claimed there in any case, since P-A's own code didn't exist before 2026-07-11).

---

## 8. Gate H-D verdict

**PASS.**

| Requirement | Status |
|---|---|
| Fixed cause taxonomy used for every source/date-range | Yes — `NOT_PRODUCED` (P-A, P-A mirror, P-B, P-B mirror) and `OVERWRITTEN_OR_TRUNCATED` (P-A mirror secondary finding), all from §1.1's closed enum |
| Evidence refs provided | Yes — every finding cites specific commits, file mtimes, job logs, or code comments (see `history_gap_findings.json` and `history_gap_timeline.csv`) |
| Protected inputs unchanged | Yes — `git status` scoped to protected paths shows only the same pre-existing dirty state noted in P0-R1's preflight; two files independently hash-cross-checked against P0-R1's 2026-08-12 record, exact match |
| All unknowns explicitly listed | Yes — see §7 `unresolved_items`; none were assumed or guessed |

Per FR-9, Gate C-A's own `active_cleanup_or_pruning_affecting_evidence_roots` condition is answered `FALSE` (§6), conditional on Stage 2's root choice — Phase H does not itself gate on this (Gate H-D is unaffected), but Gate C-A must re-confirm once concrete paths exist.

---

## 9. What this does NOT establish

Per §1.3 of the prereg: this diagnosis does not restore pre-2026-07 production history, does not claim any backfilled/recalculated result is equivalent to contemporaneous production output, and does not reopen R1. It also does not modify, and was not permitted to modify, any Scores/c2_fullpool/scheduling/production artifact. Phase B (collector design freeze) has not started.
