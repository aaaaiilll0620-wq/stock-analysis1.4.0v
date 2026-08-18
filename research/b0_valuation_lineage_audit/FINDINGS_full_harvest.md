# Official exchange PBR — full 87-month harvest, lineage reconciliation, availability semantics

**Date:** 2026-08-18 · **Status:** the four audit tasks are complete.
**Nothing was ruled on.** `value_pbr_lineage_2019plus` remains **OPEN**.

Companion to `FINDINGS.md`. **A second session was auditing the same question in
this repo at the same time** (commits `72ceee55` 22:39 and `428e56c0` 22:40,
`Co-Authored-By: Claude Opus 5`), which is why `FINDINGS.md` now also carries an
87-month coverage claim, and why both harvests were competing for one TWSE rate
budget. That parallel result and this one disagree; §2.1 states where, and which
number survives checking. Everything in §3-§5 — value reconciliation, availability
semantics, point-in-time board membership — is not in the parallel result, whose
own §5 records value reconciliation as still not done.

**Not done, by instruction:** no `run_decision`, no SelectionScore, no Top-20, no
portfolio, no NAV, no CAGR / Sharpe / MDD / IC / win-rate, no benchmark
comparison, no L2 opening, no M-3 item closed, no B0 strategy semantics touched.
**Not read:** `PBR_TEJ` (either vintage), and the D-1 quarantined 2019+ corpus
(`aeda65b9…ea49c1`). The only corpora opened are the ones §2.8.3 makes canonical:
the yearly export for `<= 2018` and the two zips for `>= 2019`, and from the zips
only the close column.

---

## 1. The harvest: 87/87, no unresolved gaps

| | requested | answered | unresolved transport |
|---|---|---|---|
| TWSE 上市 `BWIBBU_d` | 123 sessions | **123** | **0** |
| TPEx 上櫃 `peQryDate` | 123 sessions | **123** | **0** |

123 = the 87 frozen decision months 2019-01 .. 2026-03, plus 36 pre-2019
month-ends 2016-01 .. 2018-12 used for the reconciliation in §3. Every session is
resolved from the FROZEN calendar (`data/b0/trading_calendar.csv`) as the last
session on or before the month end; the resolution reproduces the 87 sessions
used by the earlier probe exactly, 87/87 identical.

**A transport failure is never recorded as history.** The first probe returned
the same `None` when the host refused the connection and when it answered "no
data for this date", which is how "2020 is missing" got read off a rate-limit
refusal. The harvester now ends each session in exactly one state — `OK`,
`NO_DATA` (the host answered and had nothing) or `TRANSPORT_FAIL` (no answer was
obtained) — and **caches only the first two**, so a re-run converges instead of
freezing a refusal into the record. Final state: 246/246 `OK`, 0 `NO_DATA`,
0 `TRANSPORT_FAIL`.

**Operationally** TWSE serves each request in ~0.1-3 s but refuses TCP outright
(curl reports HTTP 000) once a short burst is exceeded, and the refusal clears in
about 70 s — measured, not assumed. A sliding-window limiter of 4 requests / 70 s
with 15 s spacing completed the harvest; TPEx never refused a request at 4 s
spacing. This is why the earlier session read the throttle as absent history.

## 2. Coverage per decision month (87 months)

`required` = securities with an observed price on the as-of session in the
admissible 2019+ corpus. `covered` = a numeric official 股價淨值比 from either
board. Full table: `official_pbr_87month_table.csv` / `…_report.json`.

| | min | median | max |
|---|---|---|---|
| required | 1,793 | — | 1,961 |
| coverage rate | **93.69%** | **94.60%** | **98.42%** |
| explicit NA (`-` / `N/A` on a board) | 0 | — | 4 |
| off-board / unpublished | 31 | — | 113 |
| unresolved transport | 0 | 0 | 0 |

Yearly means:

| year | months | required | covered | off-board | explicit NA | coverage |
|---|---|---|---|---|---|---|
| 2019 | 12 | 1,798 | 1,701 | 96.7 | 0.2 | 94.61% |
| 2020 | 12 | 1,814 | 1,716 | 98.0 | 0.6 | 94.57% |
| 2021 | 12 | 1,840 | 1,735 | 103.2 | 1.4 | 94.31% |
| 2022 | 12 | 1,862 | 1,759 | 102.0 | 1.0 | 94.47% |
| 2023 | 12 | 1,889 | 1,786 | 103.3 | 0.0 | 94.53% |
| 2024 | 12 | 1,929 | 1,825 | 103.7 | 0.2 | 94.62% |
| 2025 | 12 | 1,957 | 1,880 | 76.8 | 0.3 | 96.06% |
| 2026 | 3 | 1,959 | 1,923 | 35.3 | 0.0 | 98.20% |

Coverage sits in a 1.3 pp band for six years and then rises monotonically through
2025 as the off-board class shrinks from ~100 to 31 — the exchanges' reports grow
faster than the priced universe over that stretch (TWSE 1,031→1,070 rows,
TPEx 836→881, while `required` is flat at ~1,958). **The mechanism behind that
last-15-month improvement is not established by this audit** and nothing here
depends on it.

**The gap is not an exchange failure**, and it is now classified from the
exchanges' own reports rather than by inference — 8,355 uncovered
security-months in total:

| kind | security-months | share |
|---|---|---|
| `later_on_board` — the reports first carry it in a later session | 6,304 | 75.5% |
| `never_on_board` — no session in the whole harvest carries it | 1,587 | 19.0% |
| `gap_while_on_board` | 376 | 4.5% |
| `earlier_on_board` — the reports stopped carrying it | 88 | 1.1% |

463 securities are uncovered in at least one month; 39 appear in no report at all
(27 four-digit, 12 five-digit-or-longer). `9110`, `911608`, `911622`, `4169` and
`9136` are priced in every one of the 87 months and listed by neither exchange in
any of the 123 harvested sessions. **The explicit-NA class is nearly empty** (0-4
per month), so almost every uncovered security is a board-membership fact, not a
published `-`.

**Both boards do publish an explicit NA, in different tokens**, and both classes
are tiny across the 123 harvested sessions: TWSE writes `-` (24 rows), TPEx writes
`N/A` (15 rows) and — in 2021-2022 only — the literal string `null` (21 rows).
The `null` form is worth naming because it already caused a miscount: an NA token
list that stops at `""`, `-`, `NA`, `N/A` and `0.00` treats `null` as a published
ratio (§2.1). Separately, no official ratio in the entire harvest is ever `0.00`,
so a zero appearing downstream would always be a parsing artefact, never a source
value.

### 2.1 Where this disagrees with the concurrently committed coverage report

`official_pbr_coverage_report.json` (committed at `72ceee55`) and this run differ
on 14 of the 87 months. Both read the same cached payloads, so the differences are
in the counting, and both causes are one-directional:

1. **Four months lose the TWSE side entirely.** 2020-04, 2020-06, 2021-02 and
   2021-12 are recorded there with `covered_twse_listed = 0`, i.e. 42.5-43.0%
   coverage, and its summary carries `coverage_rate_min = 0.4253` with four
   `fetch_failures`. The TWSE payloads for all four months **exist and parse**
   (`twse_2020-04-30.json` and the rest: 942 / 943 / 945 / 954 rows, sha256
   recorded), so
   this is a bookkeeping gap in that pipeline, not missing data. Note that the
   prose committed one minute later (`428e56c0`) states 87/87 and a 93.85%
   minimum — **the committed document and the committed artifact it rests on do
   not agree**, and a ruling that reads either without the other will be misled.
2. **Literal `"null"` ratios counted as covered.** TPEx returned the string
   `null` for 21 security-months between 2021-07 and 2022-02 (`6840`, `6843`,
   `6870`, `6874`, `6855`). The older parser excludes `""`, `-`, `NA`, `N/A` and
   `0.00` but not `null`, so those rows count as a published ratio; this run
   rejects them. Measured on 2021-07-30: 788 covered vs 787. That inflates eight
   months by 1-3 securities each.

Corrected figures — the ones used throughout this document — are coverage
**93.69%** (2021-11) to **98.42%** (2026-03), median **94.60%**, gap 31 to 113.

## 3. Pre-2019 overlap: the two series are the same number

36 month-ends 2016-01 .. 2018-12, comparing the OFFICIAL published ratio against
the admissible `股價淨值比-TSE` lineage on the same stock and the same session.
Population = priced securities, the same definition `required` uses.

| | comparisons | exact equal | rate | max abs diff | rel diff > 1% | mean signed diff |
|---|---|---|---|---|---|---|
| **TWSE 上市** | 32,284 | 32,284 | **100.00%** | **0.00** | 0 | 0.0 |
| **TPEx 上櫃** | 26,419 | 26,408 | **99.96%** | 0.09 | 8 | −5e−06 |

Both publish at two decimals, so "exact" is judged at the published tick.
**All 11 TPEx disagreements fall in the first two sessions of the window**
(2016-01-30, 2016-02-26) and none occur after 2016-02 — an era-boundary artefact,
not a drift. There is no systematic semantic divergence on either board: the
median signed difference is 0.00 and the mean is within 1e−5.

**Missingness mismatch** (36 sessions):

| | count |
|---|---|
| official has a value, lineage does not (`official_only`) | **0** (both boards) |
| lineage has a value, board published NA | 7 TWSE / 0 TPEx |
| lineage has a value, security on neither board | 178 (0-22 per session) |
| priced but on no board at all | 107-155 per session |
| both missing | 2 TWSE / 6 TPEx |

**Same-session keying is confirmed independently:** where both sources print a
close, 18,963 of 18,963 agree exactly (max diff 0.00). A published close of 0.00
means the security did not trade that session; TWSE substitutes a price determined
under 營業細則 58-3 and still publishes the ratio, and the lineage still carries a
reference close, so those 105 rows are excluded from the close check rather than
counted as disagreement.

**Correction to `FINDINGS.md` §2.** Both its original form and its current one
compare official coverage against a pre-2019 lineage band measured on the twelve
2018 month-ends (93.04-94.21%), and conclude official is "at least as complete as
what B0 reads today". That is a cross-era comparison. Measured in the SAME era on
the SAME population, official is marginally **below** the lineage:

| 2016-2018, 36 sessions | min | median | max |
|---|---|---|---|
| frozen lineage coverage | 91.84% | 92.73% | 94.21% |
| official coverage | 91.03% | 92.49% | 93.99% |
| official − lineage | **−1.27 pp** | **−0.11 pp** | 0.00 pp |

The substantive conclusion survives — the two are within about a point across
36 sessions, and `official_only = 0` says official never adds a security the
lineage lacks — but the direction of the claim is wrong: on identical dates the
official series is at best equal and at worst 1.27 pp thinner. A ruling should
carry the same-era number, not the cross-era one.

## 4. Availability semantics: what the sources say, and what they do

**Documentation.**

| | TWSE 上市 | TPEx 上櫃 |
|---|---|---|
| ratio definition published | yes | yes (`股價淨值比＝收盤價／每股淨值`) |
| statement period named | **yes** — 財報年／季 is defined as the 財務報告年度季別 filed on MOPS | **no**, before 2025 |
| explicit "as published then" | **yes** (quoted below) | not found |
| vintage column in payload | from **1060412 = 2017-04-12**, stated on the page | from **2025-01-02**, measured |

The TWSE report page settles the question in its own words — this is the strongest
single piece of evidence in the audit:

> 以上本網頁所採用之財務相關資料為計算當時公開資訊觀測站已公告申報格式化之資料，
> 而非同期即時資訊，**且不作回溯計算**

— the figures are what had been filed at the time of computation, and **no
retrospective recomputation is performed**. The same page states
`股利年度及財報年/季資訊自民國106年4月12日起提供`, which pins the disclosure
boundary exactly; the payload layout change measured here (5 fields on
2017-03-31, 8 fields on 2017-04-28) brackets that date and does not contradict
it. The page also explains the zero closes seen in §3: when a security has no
close that day, a price determined under 營業細則 58-3 is substituted, and the
ratio is still published.

TPEx changed from 7 to 8 fields between 2024-12-31 (absent) and 2025-01-02
(present) — measured, with no corresponding statement found on the TPEx side. The
current TPEx OpenAPI (`/tpex_mainboard_peratio_analysis`) still publishes seven
fields and no vintage.
**Across the whole 2019+ window under ruling, TWSE discloses the vintage and TPEx
does not until 2025-01** — 72 of the 87 decision months have no 上櫃 vintage
disclosure.

**Measurement.** The denominator is recoverable — `BVPS = close / published PBR` —
so the two hypotheses can be separated. An archived per-session record gives a
piecewise-constant BVPS that steps on the statutory announcement calendar; an
endpoint that recomputes today's ratio and back-dates it gives ONE level for the
whole history. Two-decimal publication is carried as an interval
(`p ± 0.005`), and a step is recorded only when two intervals cannot intersect.

| run | securities | one BVPS level only | steps / security-year | step months (top 4) |
|---|---|---|---|---|
| TWSE 2019+ (calibration) | 1,079 | **0** | 3.02 | 03, 05, 08, 11 |
| TWSE 2016-2018 | 925 | **0** | 3.38 | 03, 05, 08, 11 |
| TPEx 2019+ | 908 | **0** | 3.02 | 03, 05, 08, 11 |
| TPEx 2016-2018 | 772 | **0** | 3.43 | **04**, 05, 08, 11 |

Calibrated against the disclosed vintage where one exists, the estimator agrees
with 財報年/季 on **95.05%** of consecutive TWSE 2019+ session pairs (recall
88.76% on the pairs where the vintage actually changed — a new statement whose
book value barely moves leaves no detectable step), and **96.57%** on TPEx 2025+.

⇒ The back-dated-recomputation hypothesis is refuted everywhere: **0 of 3,684
securities across the four runs show a single constant book value.** The early
上櫃 series behaves like an archived per-session record whose denominator refreshes
on the announcement calendar.

⚠ **Two limitations, recorded rather than resolved.**

1. **This measures behaviour, not documentation.** It cannot show WHICH statement
   vintage stood behind each 上櫃 denominator before 2025, because the source does
   not say, and no official document was found that says it. What can be shown is
   that the value is an official historical daily value keyed to that session and
   consistent with a then-current book value — exactly the weaker claim the task
   anticipated.
2. **The early TPEx refresh timing differs from the modern one.** In 2016-2018 the
   annual step lands in **April** (1,438 steps) rather than March (484), with a
   December bump (654) absent from every other run. From 2019 the TPEx pattern is
   indistinguishable from TWSE's. This concerns only the pre-2019 comparison
   window, not the 87 months under ruling, but it means the early 上櫃 series and
   the early 上市 series were not refreshed on the same clock.

## 5. Point-in-time board membership

Board membership is taken from the exchanges' own reports for that session — a
security is 上市 on `s` because TWSE published it on `s`, 上櫃 because TPEx did.
The current `上市別` label is never read: §2.3 shows it is rewritten on delisting,
so back-filling history from it is look-ahead of exactly the kind D-1 exists to
remove.

Over the 87 months: **84,651** security-months on the TWSE board, **69,977** on
the TPEx board, and **0** on both — the two reports partition cleanly, so "which
board" is never ambiguous and no tie-break rule is needed.

Off-board securities (興櫃 / emerging board, and the never-listed codes in §2)
have **no official PBR to take**. Evidence: the TPEx OpenAPI catalogue (225
endpoints) carries 興櫃 balance sheets, income statements, EPS and capital
rankings, and quotes only as 興櫃股票當日行情表 — **no 興櫃 PE/PBR report appears
anywhere in it**, and none was found on either exchange's after-trading pages.
Those securities therefore stay NA and fall to the frozen §4.1 complete-case rule.
Nothing was substituted for them.

## 6. What a ruling would still have to decide

Stated as open questions, not as recommendations. The facts above are what the
audit can supply; each item below is normative and belongs to a ruling.

1. **May an official-exchange series serve as the B-09 lineage at all?** The
   specification does not say what an admissible 2019+ TSE PBR source is. §3 shows
   the frozen lineage and the exchange series are the same number where they
   overlap; it does not make the substitution legal.
2. **The TPEx vintage-disclosure gap.** 72 of the 87 decision months have no 上櫃
   statement-period disclosure. §4 shows the series behaves as an archive; the
   ruling has to decide whether behavioural evidence substitutes for source
   disclosure, and to say so explicitly if it does.
3. **The residual NA class.** 4-6% of priced securities per month, ~95% of it
   board-membership rather than a published `-`, and materially the same
   population the frozen lineage already leaves NA (`official_only = 0`). The
   ruling has to confirm §4.1 complete-case absorbs it.
4. **Sealing.** If admitted, the derived series presumably needs its own frozen
   contract — content hash, importer version, schema hash, date range, the D1-7
   shape — rather than being materialised from a live endpoint at run time. The
   raw payloads and their sha256 are already cached for that purpose.
5. **The 2025+ coverage shift.** Coverage rises from ~94.5% to 98.4% over the last
   15 months for a reason this audit did not establish. Harmless for a
   complete-case rule, but it should be named in the ruling rather than
   discovered later.

**Is the item ruling-ready?** On the facts, yes: every question the audit was
asked — does the source exist for all 87 months, is it the same number as the
frozen lineage, is it point-in-time, can board membership be established without
look-ahead — now has a measured answer, and the measurements are reproducible from
cached payloads carrying their own hashes. What is missing is not evidence but
five normative decisions, the five above. **This document takes none of them, and
`value_pbr_lineage_2019plus` is left OPEN.**

One measurement was deliberately **not** made: how far `股價淨值比-TEJ` diverges
from `股價淨值比-TSE` in the pre-2019 export, which would say whether B-09's
TSE-vs-TEJ distinction is material in the first place. It is cheap (the admissible
yearly export carries both columns) and it was left undone because it was outside
the four tasks and touches the column the open item forbids substituting. Offered,
not performed.

## 7. Reproduction

```
python research/b0_valuation_lineage_audit/harvest_official_pbr.py        # idempotent
python research/b0_valuation_lineage_audit/build_2019plus_closes.py
python research/b0_valuation_lineage_audit/analyse_87month_coverage.py
python research/b0_valuation_lineage_audit/reconcile_pre2019_overlap.py
python research/b0_valuation_lineage_audit/availability_semantics.py
```

Harvest pacing is environment-controlled (`B0_AUDIT_SOURCE`, `B0_AUDIT_SESSIONS`,
`B0_AUDIT_PAUSE`, `B0_AUDIT_BURST`, `B0_AUDIT_WINDOW`, `B0_AUDIT_TIMEOUT`,
`B0_AUDIT_RETRIES`, `B0_AUDIT_BACKOFF`); the polite rate is a property of the host
on the day, not of this audit. Raw payloads, normalised per-session records and
the derived close/lineage extracts live under
`artifacts/valuation_lineage_audit/` (gitignored); each normalised record carries
the sha256 of the exact bytes the exchange returned.

Reports written by this run:

- `official_pbr_87month_report.json` · `official_pbr_87month_table.csv`
- `pre2019_overlap_reconciliation.json`
- `availability_semantics_report.json`
- `harvest_ledger_all_twse.json` · `harvest_ledger_all_tpex.json`
