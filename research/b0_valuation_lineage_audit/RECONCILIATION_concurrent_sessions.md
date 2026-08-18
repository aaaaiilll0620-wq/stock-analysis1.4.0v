# Concurrent-session reconciliation — one canonical audit result

**Date:** 2026-08-18 · **Outcome:** a single canonical result established, no work
discarded, no history rewritten.

Two Claude sessions modified this repository during the official-PBR audit. One
of them committed while the other was still harvesting. This file records what
each produced, which artifact survives as canonical, and why — so that the ruling
on `value_pbr_lineage_2019plus` rests on a result whose provenance is not
ambiguous.

## 1. What the concurrent commits changed

| commit | time | contents |
|---|---|---|
| `72ceee55` | 22:39:20 | 14 files, +9,843 / −9. Swept in the OTHER session's in-flight working tree — `harvest_official_pbr.py`, `analyse_87month_coverage.py`, `reconcile_pre2019_overlap.py`, `availability_semantics.py`, `build_2019plus_closes.py` and their outputs — plus its own `official_pbr_coverage_raw.json` / `official_pbr_coverage_report.json`, plus a rewrite of `FINDINGS.md` §2/§5. |
| `428e56c0` | 22:40:22 | `FINDINGS.md` only, +12 / −13: "84/87" → "87/87". |

Both are ordinary commits on the branch. **Neither is reverted and no history was
rewritten**; `git reset --hard` was not used at any point.

## 2. Comparison against the completed audit outputs

The committed copies of the scripts' OUTPUTS are mid-run snapshots — they were
taken while the harvest was still running:

| artifact | as committed at `72ceee55` | completed |
|---|---|---|
| `official_pbr_87month_report.json` | 87 months listed, **17 fully harvested**, coverage 94.28-94.82% over those 17 | **87 fully harvested**, coverage 93.69-98.42% |
| `pre2019_overlap_reconciliation.json` | **22 of 36** sessions usable; TWSE n=19,500 / TPEx n=15,896 | **36 of 36**; TWSE n=32,284 / TPEx n=26,419 |
| `availability_semantics_report.json` | partial TWSE 2019+ arm | all four arms complete |

So the committed numbers are not wrong in a way that indicts the pipeline — they
are simply earlier. The completed outputs supersede them file-for-file at the same
paths.

## 3. Substantive work preserved

Everything of substance from both sessions is retained:

- both sessions' **raw payloads** stay in `artifacts/valuation_lineage_audit/`;
  they are the same cache and neither session's fetches were thrown away;
- the superseded pipeline's own ledger and report are **moved, not deleted**, to
  `superseded/` with `git mv`, so the record of the discrepancy survives;
- `FINDINGS.md` keeps its qualitative sections — endpoint identification, the
  non-session false-negative warning, the residual-gap characterisation — and is
  corrected in place only where it states numbers that do not hold, with a banner
  pointing at the canonical document.

## 4. What is rejected, and exactly why

`superseded/official_pbr_coverage_report.json` may not be cited. Two independent
defects, both one-directional:

1. **Four months recorded with the TWSE side at zero** — 2020-04, 2020-06,
   2021-02, 2021-12 — producing `coverage_rate_min = 0.4253` and four
   `fetch_failures`. The TWSE payloads for all four exist and parse (942 / 943 /
   945 / 954 rows, sha256 recorded). The zero is a sidecar-file bookkeeping gap in
   that pipeline, not missing data.
2. **The literal string `null` counted as a published ratio.** TPEx returned
   `null` for 21 security-months in 2021-07 .. 2022-02; the superseded parser's NA
   token list stops at `""`, `-`, `NA`, `N/A`, `0.00`. Measured on 2021-07-30:
   788 counted vs 787 actually numeric.

The prose committed at `428e56c0` (87/87, minimum 93.85%) disagrees with the
artifact committed at `72ceee55` (minimum 0.4253) that it was drawn from. Neither
matches the corrected result. Both are retained for the record and neither is
authoritative.

## 5. The canonical result

`FINDINGS_full_harvest.md` and the artifacts it names. Reproduced from the cached
payloads after reconciliation:

```
TWSE            87/87 decision months   (123/123 including the 2016-2018 overlap)
TPEx            87/87 decision months   (123/123 including the overlap)
TRANSPORT_FAIL  0
NO_DATA         0
coverage        93.69% .. 98.42%, median 94.60%
gap             31 .. 113
overlap         TWSE 32,284 @ 100.00% exact · TPEx 26,419 @ 99.96% exact
```

Also fixed while establishing it: `analyse_87month_coverage.py` wrote its CSV with
the `csv` module's default CRLF terminator, against the repo's `* text eol=lf` and
its CRLF→LF migration ledger. Now `lineterminator="\n"`.

## 6. No destructive operation was used

No `git reset --hard`, no force push, no branch deletion, no file deletion. The
only removals from the working set are `git mv` moves into `superseded/`.

## 7. Single-worker requirement

This session is the only one that has modified the repository since 22:42:45 (the
last artifact write of its own harvest). **This cannot be enforced from inside a
session** — if the other session is still open, it must be stopped before the
materializer runs, because the materializer writes sealed inputs whose hashes are
meaningless if a second writer can touch them.
