# Official Exchange Bonus-Share Ratio Audit

**Question.** Do TWSE and TPEx publish, for the stock-dividend events the frozen
141-period lookback can reach, a direct holder-level 無償配股率 from which
C-50/R3's multiplier follows as `m = 1 + rate`, without reconstructing
`新股股數 / 流通在外股數`?

**Answer: yes, for 2,376 of the 3,215 events (73.90%), with zero unresolved
transport failures.** The residual is 839 events, of which **261 actually reach a
priced momentum window**, and it decomposes into four named classes — none of
which is "the exchange has no such field".

No ruling is made here. `stock_dividend_holder_multiplier_source` stays OPEN.
No fallback to `新股 / 流通在外股數`, current shares outstanding, price-implied
multipliers, cash-dividend fields or total-return adjustment was used or
prepared. No assembler, decision, ranking, portfolio, NAV, performance or L2.

---

## 1. Source identity and provenance

| layer | endpoint | payloads | bytes |
|---|---|---|---|
| `twse_range` | `https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=&endDate=&response=json` | 52 | 2,632,684 |
| `tpex_range` | `https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ?startDate=&endDate=&response=json` (ROC dates) | 52 | 2,396,581 |
| `twse_detail` | `https://www.twse.com.tw/rwd/zh/exRight/TWT49UDetail?STK_NO=&T1=&response=json` | 1,267 | 953,250 |

Every payload is cached with its own sha256. Per-payload hashes are in
`artifacts/stock_dividend_multiplier_audit/source_manifest.txt`; the composed
manifest hashes to

```
5838438b4d490c4dc8e16ebb48c7ab4a5a5f4002a4daa8d427effc2aa78ecfac
1,371 payloads, 5,216,177 raw bytes
```

**Transport failure is never cached as absence.** Each request ends in exactly
one of `OK` / `NO_DATA` / `TRANSPORT_FAIL`; only the first two touch the disk, so
re-running converges. Final count of unresolved transport failures: **0**.

The 除權除息**預告表** (TWSE `TWT48U`) was tested first and **rejected as a
history source**: it carries `無償配股率` explicitly, but it ignores every date
parameter tried (`date`, `startDate/endDate`, `strDate/endDate`) and always
returns the same forward window — at harvest time 2026-08-17 … 2026-10-07, 162
rows. It is a forthcoming-events table with no history. The historical layers
above are the 計算結果表 and its per-event detail.

### Schema and date coverage

`twse_range` — one schema, 15 columns, 2013-07 … 2026-03, quarterly queries,
row counts 7 … 724 per quarter. Carries the 權/息 classifier and the detail key;
**no ratio**.

`twse_detail` — one schema, 12 columns, all 1,267 requests answered with a row:

```
[0] 股票代號              [6]  C. (有償) 現金增資
[1] 股票名稱              [7]  每股認購金額
[2] (每股配發現金股利)除息  [8]  a. 公開承銷
[3] (增資配股) 除權        [9]  b. 員工認購
[4] A. 按普通股股東持股比例每千股無償配股   <-- the field
[5] B. 員工紅利轉增資      [10] c. 原股東認購
                          [11] 按股東持股比例每千股認購
```

Field **A** is the holder-level bonus allotment. Note that the exchange itself
separates it from B (employee bonus) and C (cash capital increase) — exactly the
split C-50/R2 already ruled: A is eligible, B and C are not.

`tpex_range` — **two** schemas, and they are resolved by NAME rather than
position for that reason: 22 columns through 2015-12 (it carried
`員工紅利轉增資`), 21 columns from 2016-01 (that column was dropped). Both carry
`每仟股無償配股` in the range table itself, so OTC needs no second layer. The
dropped column is the employee-bonus leg, ineligible under C-50/R2 either way.

TWSE writes the unit as 每**千**股 and TPEx as 每**仟**股. The two name sets are
kept separate rather than normalised into one guess.

---

## 2. Unit semantics — decided by measurement, not by the column name

The published number is checked against **the exchange's own reference-price
identity**, using only the exchange's own published components:

```
除權息參考價 = (除權息前收盤價 − 現金股利 + 認購價 × 認購率) / (1 + 無償配股率 + 認購率)
```

This does not derive `m` from a price — `m` is published; the price is the
exchange's arithmetic identity, and only one reading of the units satisfies it.

**TPEx**, 1,106 clean rows (bonus > 0, no cash capital increase):

| reading | max abs err | median | within 0.01 |
|---|---|---|---|
| **shares per 1,000 held** (`m = 1 + b/1000`) | **0.0050** | 0.00252 | **1,106 / 1,106 (100.00%)** |
| decimal ratio (`m = 1 + b`) | 2095.1107 | 44.4920 | 0 / 1,106 |
| percent (`m = 1 + b/100`) | 953.1800 | 16.2991 | 0 / 1,106 |

**TWSE**, 1,267 rows, split by whether a cash capital increase coexists:

| subset | n | max abs err | median | within 0.01 |
|---|---|---|---|---|
| pure bonus (no cash increase) | 1,253 | 0.0999 | 0.00488 | 1,227 (97.92%) |
| with a concurrent cash increase | 14 | 0.5845 | 0.15843 | 0 |

against, for the same 1,267 rows, 1527.98 / 1035.86 max error under the
decimal-ratio and percent readings, and **0** rows within 0.01 under either.

So: **the number is shares per 1,000 shares held**, and

```
holder_multiplier m = 1 + bonus_per_1000 / 1000
```

Two honest caveats about the CHECK, neither of which touches field A:

* The 14 misses all have a concurrent cash capital increase, whose subscription
  rate the identity above handles only approximately (the exchange applies it to
  a base this audit did not harvest separately). C-50/R2 makes that leg
  **ineligible**, so it never enters `m`; this is a limit of the verification,
  not of the field.
* Of the 26 pure-bonus rows above 0.01, all but one sit between 0.013 and 0.026
  on high-priced securities (prev close 435 … 1,175) and are consistent with the
  published rate being rounded to one decimal. One row — 2723, 2018-06-21,
  err 0.0999 — is not explained by that rounding and is recorded rather than
  waved off.

Distribution of the matched multiplier:

```
bonus per 1,000   min 2.6    p50 50.0    p95 200.0    max 1,256.6
m = 1 + b/1000    min 1.0026 p50 1.0500  p95 1.2000   max 10.3800
```

---

## 3. Board attribution is contemporaneous by construction

A security is attributed to TWSE for an ex-date because **the TWSE payload for
that date carries it**, and to TPEx for the same reason. No current `上市別`
column is read anywhere in this audit, and no security in the matched set
appears on both boards on the same date.

Matched events by contemporaneous board: **TWSE 1,267 · TPEx 1,109**.

---

## 4. Date semantics vs C-50/R4

2,212 distinct official ex-right dates were harvested. **2,199 of them are
sessions in the frozen trading calendar**; the official date is the
market-effective session R4 requires, and no translation from a credit or
registration date is involved. The exchange key `年月日` / `除權息日期` joins
directly to the ledger's `ex_or_effective_date` — that is how the 2,376 matches
were formed, with no tolerance.

**The 13 exceptions are all the same thing, and it is not a data defect.** Every
one is a scheduled ex-right date on which the market did not open, and in every
case the ledger's ex-date is *exactly the next open session*:

| official (scheduled) date | is a session? | ledger ex-date | next open session | events |
|---|---|---|---|---|
| 2013-08-21 | no | 2013-08-22 | 2013-08-22 | 6 |
| 2014-07-23 | no | 2014-07-24 | 2014-07-24 | 3 |
| 2019-08-09 | no | 2019-08-12 | 2019-08-12 | 3 |
| 2019-09-30 | no | 2019-10-01 | 2019-10-01 | 2 |
| 2023-08-03 | no | 2023-08-04 | 2023-08-04 | 2 |
| 2024-07-25 | no | 2024-07-26 | 2024-07-26 | 7 |

(The full non-session list also includes 2015-07-10, 2016-07-08, 2016-09-28 and
2024-07-24, which carry no canonical stock-dividend event.) These are
market-closure days; the report kept the scheduled date, the ledger kept the
effective one. **C-50/R4 already says which of the two is the boundary** — the
market-effective session — so the ledger's date is the R4-correct one and the
official row for these 23 events exists under the scheduled key.

This audit does **not** absorb them into the matched count. Merging them would
mean adding a date tolerance to a ruling that was frozen without one, and that
is a decision, not a measurement.

---

## 5. Coverage over the L2-required event history

The window is the union every 141-period `momentum_12_1` / `sigma20d` lookback
can reach. `P_{t-13}` for the first decision month 2014-07 is the 2013-06
month-end session (2013-06-28), and an event on or before that session divides
both momentum anchors alike and cannot change the ratio — hence
**`2013-06-29` … `2026-03-31`**, which holds **3,215** canonical `stock_dividend`
events over 996 securities.

This is the point the instruction made: public exchange coverage predates the
frozen L2 start, so coverage is evaluated against this window and not against the
rejected corpus's 2004 origin.

| class | events | share |
|---|---|---|
| **MATCHED_POSITIVE** — official holder-level ratio present and > 0 | **2,376** | **73.90%** |
| LEDGER_NOT_RECONSTRUCTIBLE | 422 | 13.13% |
| OFF_BOARD_BEFORE_FIRST_OFFICIAL_ROW | 246 | 7.65% |
| OFF_BOARD_NEVER_PUBLISHED | 135 | 4.20% |
| DATE_OFFSET_WITHIN_3D (§4 above) | 23 | 0.72% |
| ABSENT_UNEXPLAINED | 13 | 0.40% |
| MATCHED_ZERO | **0** | — |
| transport failure | **0** | — |

`MATCHED_ZERO` is empty: every event the two exchanges carry for a canonical
stock-dividend date carries a strictly positive bonus allotment. 2,376 matched
events span 775 securities.

### What the residual actually is

`LEDGER_NOT_RECONSTRUCTIBLE` is the frozen ledger's own verdict, not the
exchange's silence: **422 of the 423** NOT_RECONSTRUCTIBLE events in the window
are in this class (99.8%). These are the rows the ledger already annotates as
"capitalisation recorded without an ex-right flag: no distribution rate and no
credit date; 年月日 is a registration stamp". The exchanges have no record
because there was no ex-right session to record.

`OFF_BOARD_*` is a listing fact: for 246 events the ex-date **precedes the
security's first official ex-right row on either board**, and 135 belong to
securities that never publish one in 2013–2026. TWSE and TPEx do not compute
ex-right references for securities that are not on their boards.

### Does the residual reach anything priced?

| class | events | reach a priced window |
|---|---|---|
| LEDGER_NOT_RECONSTRUCTIBLE | 422 | 2 (0.47%) |
| OFF_BOARD_BEFORE_FIRST_OFFICIAL_ROW | 246 | 216 (87.80%) |
| OFF_BOARD_NEVER_PUBLISHED | 135 | 20 (14.81%) |
| DATE_OFFSET_WITHIN_3D | 23 | 23 (100%) |
| ABSENT_UNEXPLAINED | 13 | 0 |
| **total residual** | **839** | **261** |

("Reaches a priced window" = the security is quoted in the sealed price panel on
both sides of the ex-date, so an unadjusted jump would land inside some
13-month lookback.)

### Per-period exposure, before and after

Share of the priced universe whose 13-month momentum window contains a
stock-dividend ex-date, across all 141 periods:

```
BEFORE (any stock dividend, i.e. the C-50/R8 NA-branch cost measured earlier)
   min 8.08%   p25 9.23%   median 10.56%   p75 13.03%   max 20.34%

AFTER  (only events with NO official ratio)
   min 0.20%   p25 1.06%   median  1.41%   p75  1.88%   max  2.97%

for comparison, the accepted §2.3 industry-UNRESOLVED exclusion  median 2.303%
```

---

## 6. What this establishes, and what it does not

Established:

1. Both exchanges publish a **direct holder-level bonus-share allotment** — TWSE
   field A `按普通股股東持股比例每千股無償配股`, TPEx `每仟股無償配股` — and it
   is a per-1,000-shares allotment, proved against the exchanges' own
   reference-price identity rather than assumed from the column name.
2. `m = 1 + bonus_per_1000 / 1000` is therefore obtainable **without** shares
   outstanding, without a `新股 / 流通股數` reconstruction, and without any
   price-implied inference.
3. It covers **2,376 / 3,215 (73.90%)** of the L2-required events, with 0
   transport failures and 0 zero-rate matches, and the exchange's own field
   layout separates the eligible leg (A) from the ineligible legs (B employee
   bonus, C cash capital increase) exactly as C-50/R2 already ruled.
4. The official date **is** the R4 market-effective session in 2,199 of 2,212
   cases; the 13 exceptions are market-closure days with a clean, mechanical
   relation to the ledger date.
5. The unresolved share of the priced universe falls from a median of 10.56% to
   **1.41%** per period — below the §2.3 exclusion the specification already
   accepts.

Not established, and deliberately left open:

* Whether this source is **admissible** as the canonical C-50 holder-multiplier
  source. That is the ruling.
* What to do with the **261 residual events that reach a priced window** — in
  particular the 216 pre-listing/off-board ones, which are a listing fact rather
  than a data gap, and the 23 closure-day ones, which need a date-alignment
  sentence C-50 does not currently contain.
* Whether a sealed-source contract of the C-48/C-49 shape (no runtime fetch,
  pinned parser version, pinned payload hashes) should govern it.

`stock_dividend_holder_multiplier_source` remains OPEN and unruled.
