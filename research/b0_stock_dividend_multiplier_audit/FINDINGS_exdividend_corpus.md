# Stock Dividend Holder-Multiplier Source Audit — `除權息2004-20260806`

**Scope.** Does the already-held ex-dividend corpus carry a field from which the
C-50/R3 holder multiplier `old_holder_shares × m = new_holder_shares` can be read
DIRECTLY, without reconstructing `新股股數 / 流通在外股數`?

**Verdict: NO.** The corpus is a cash-dividend record. It contains no share
quantity, no share ratio, and no per-1,000-share allotment, in any year.
No ruling is made here and no M-3 item is closed.

READ-ONLY. No decision layer, no momentum, no portfolio, no performance quantity
was computed, and no price series was used to infer a formula.

## 1. Raw provenance

Six xlsx files, one sheet each, one identical 11-column schema across all of them.

| folder | rows | sha256 |
|---|---|---|
| 除權息2004-2007 | 3,574 | `88613dcad20834080598f177d86e5ff7efefdf04d678186aedc49915a53e8443` |
| 除權息2008-2011 | 3,915 | `70d127ed691836d1302eeac07de03cfe9c1dc35b573a4763c277767927052bd5` |
| 除權息2012-2015 | 4,717 | `8cf1687592476f8ddaa08bf6a63b5aeaa58c6697d44543c267b1029f4ee352da` |
| 除權息2016-2019 | 5,356 | `3f14cb4f2764c1b184d7c6289f568795a39fd369347d5b34ff4d180e41ccee2c` |
| 除權息2020-2023 | 6,015 | `3edc6cf8c0509222af8dc0c4f6a59f1114c621a8e34a5013c0c9231a5e1aaf11` |
| 除權息2024-20260806 | 4,435 | `b3111591a6aa53ed4c994ec286d2021f8aa66b4dc59abd93795ea35edfefb919` |

Total 28,012 rows. Distinct schemas across the six files: **1**.

The corpus is not imported by any current code path: the corporate-action ledger
is built solely from `配股相關2004-20260817`
(`research/p0_v1b_stock_dividend/build_corporate_action_ledger.py`).

## 2. Schema — every column, and what it is

| # | column | kind |
|---|---|---|
| 0 | `證券代碼` | id + name |
| 1 | `年月日` | ex-date |
| 2 | `盈餘分派_迄日` | earnings period end |
| 3 | `息值(元)` | **cash** per share, total |
| 4 | `除息(權)參考價(元)` | ex reference **price** |
| 5 | `現金股利(元)_盈餘` | **cash** per share, from earnings |
| 6 | `現金股利(元)_公積` | **cash** per share, from capital reserve |
| 7 | `股息發放日` | cash payment date |
| 8 | `除息公告日` | announcement date |
| 9 | `融券最後回補日` | short-cover deadline |
| 10 | `最後過戶日` | last transfer date |

Columns screened for `配股 / 股票股利 / 無償 / 增資配股 / 盈餘轉增資 / 公積轉增資 /
認股 / 股數 / 千股 / 比率 / 配率 / 換股 / 權值` — **no column matches any of them.**

## 3. Unit semantics (audit item 5), proved rather than assumed

The two component columns are `盈餘` / `公積` splits of a **cash** amount, not
earnings-capitalisation and reserve-capitalisation **stock**. The additivity test
settles it:

```
息值 == 現金股利_盈餘 + 現金股利_公積   within 1e-6
  all rows           27,984 / 28,012   (99.90%)
  matched to a registered stock dividend   6,708 / 6,708   (100.00%)
```

The 28 exceptions are entirely foreign/TDR issuers (`910069 910322 910801 910861
911619 912000 9188`) and **none** falls on a registered stock-dividend ex-date.

So on a stock-dividend ex-date the two components exhaust the total exactly, which
means the total is wholly cash and there is no residual stock leg hiding inside it.
There is no `base` to which a `m = 1 + (盈餘 + 公積)/base` reading could apply,
because neither term is a share quantity.

Ranges are consistent with per-share cash in NTD: `息值` p50 = 1.30, max = 144.39;
`現金股利_公積` p50 = 0, max = 60.

## 4. Coverage

- ex-date range **2004-01-13 … 2026-08-06**, zero null ex-dates, every year 2004–2026 populated (795–1,610 rows/yr).
- **2,164** distinct securities; 28,006 distinct `(stock_id, ex_date)` keys.
- 12 rows form 6 duplicate keys (`2236 2505×2 2542 2756 4912`) — two separate cash distributions on one day; all cash, no stock leg.

## 5. Cross-source alignment with the 9,120 registered `stock_dividend` events

```
registered stock_dividend events              9,120
events with ANY row in this corpus            6,707  (73.54%)
events with NO row at all                     2,413
matched rows carrying a cash amount           6,708 / 6,708
matched rows carrying a share quantity/ratio      0   (no such column exists)
```

Even at full coverage the corpus would not answer the question; at 73.5% it does
not even cover the population.

## 6. Sample verification (audit item: do not read column names only)

Largest and median registered stock dividends, against the matched corpus row:

| stock_id | ex-date | ledger `new_shares_thousands` | corpus `息值` | `盈餘` | `公積` | `參考價` |
|---|---|---|---|---|---|---|
| 2330 | 2004-06-14 | 2,837,327 | 0.6037 | 0.6037 | 0 | 43.33 |
| 2412 | 2008-10-17 | 2,007,133 | 4.26 | 4.26 | 0 | 48.48 |
| 2303 | 2005-08-02 | 1,758,736 | 0.1029 | 0.1029 | 0 | 20.28 |
| 5848 | 2025-06-05 | 2,428,246 | — no row — | | | |
| 5841 | 2016-08-26 | 2,409,211 | — no row — | | | |
| 5847 | 2025-05-20 | 1,639,100 | — no row — | | | |
| 3416 | 2008-07-24 | 6,697 | 3.00 | 3.00 | 0 | 88.32 |
| 1477 | 2015-08-04 | 6,696 | 7.69575 | 7.69575 | 0 | 252.47 |
| 2399 | 2008-08-18 | 6,692 | 1.00 | 1.00 | 0 | 13.71 |
| 2722 | 2023-06-29 | 6,691 | 0.60 | 0.60 | 0 | 97.07 |
| 3029 | 2004-09-16 | 6,700 | — no row — | | | |
| 1454 | 2011-09-15 | 6,681 | — no row — | | | |

No row anywhere in the sample carries anything that could be read as
"100 shares per 1,000 held". The magnitude spread of `息值` across these
(0.10 … 7.70) tracks cash dividend size and is uncorrelated with the ledger's
new-share count, as it must be if the two describe different legs.

## 7. Boundary alignment with C-50/R4

The key `年月日` IS the ex-date and joins directly to the ledger's
`ex_or_effective_date` (that is how the 6,707 matches above were formed), so if a
ratio existed here it would align with R4 without translation. The failure is not
one of date semantics.

## 8. Historical event data, not a current snapshot

- Every row carries its own `除息公告日` and `股息發放日`.
- 62 securities appear here that the corporate-action ledger does not carry at all; 206 securities have their last ex-date before 2015 (long-delisted issuers are retained).
- Row counts grow year by year rather than repeating one vintage.

## 9. PIT / availability semantics

`除息公告日` is present on 28,012 / 28,012 rows.

```
announced strictly BEFORE the ex-date   27,731  (99.00%)
announced ON or AFTER the ex-date          281
announcement lead (days)  p05=15  p50=20  p95=49  min=-462
```

The file itself is a single 2026-08-06 pull with no vintage column, so any PIT use
would have to rest on the per-row announcement date, and the 281 non-conforming
rows plus the negative minimum lead would need their own disposition. Moot here.

## 10. The one near-miss, recorded and NOT adopted

`除息(權)參考價(元)` is the only field whose NAME acknowledges a rights component,
and it is a **price**, not a ratio. Backing a stock ratio out of it would require
the prior close and would make the multiplier a price-derived quantity. That is a
third path, distinct from both branches C-50/R8 offers, and it is recorded here
only so that the ruling knows it exists. It is not used, not tested, and not
recommended by this audit.

## Conclusion

`除權息2004-20260806` **cannot** serve as the canonical
`stock_dividend holder_multiplier` source for C-50. The item
`stock_dividend_holder_multiplier_source` stays OPEN and unruled.

Per the instruction governing this audit: the fallback to
`新股股數 / 流通在外股數` was NOT taken.
