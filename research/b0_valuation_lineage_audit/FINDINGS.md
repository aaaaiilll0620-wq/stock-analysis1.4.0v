# Official Exchange Valuation Lineage Audit — findings

**Date:** 2026-08-18 · **Status:** 84 of 87 months enumerated end-to-end;
3 awaiting a TWSE re-fetch (rate limit, harvest is idempotent and resuming).
**Nothing was ruled on.** `value_pbr_lineage_2019plus` remains OPEN.

Not used: PBR_TEJ, the quarantined corpus (`aeda65b9…ea49c1`). Not done: any B0
change, any decision/selection/performance computation.

---

## 1. Do the official exchanges have 2019+ historical PBR?

**Yes, both.**

| Exchange | Board | Endpoint | Verified sessions |
|---|---|---|---|
| TWSE | 上市 | `/rwd/zh/afterTrading/BWIBBU_d` | 2019-01-30, 02-27, 03-29, 04-30; 2021-01-29, 02-26, 03-30; 2022-03-31; 2026-03-31 |
| TPEx | 上櫃 | `/www/zh-tw/afterTrading/peQryDate` | 2019-01-30, 02-27, 03-29, 04-30, 06-28, 12-31; 2020-01-31, 02-27, 03-31; 2021-03-31; 2023-03-31; 2026-03-31 |

Both publish 股價淨值比 directly. TWSE returns ~926–961 securities per session,
TPEx ~766–881.

> **A false negative to avoid.** An early probe read 2019-01-31 as "no history".
> It is not a trading session — the last session before Lunar New Year 2019 was
> 2019-01-30 — and both exchanges correctly return an empty payload for a
> non-session date. Every session in this audit is resolved from the FROZEN
> trading calendar. Several "2020 is missing" readings were likewise rate-limit
> refusals (curl reports HTTP 000), not absent history.

## 2. Coverage vs what B0 needs

NEEDED = securities with an observed price on the as-of session in the
**admissible** 2019+ corpus. COVERED = a usable official PBR from either board.

| Session | needed | TWSE 上市 | TPEx 上櫃 | covered | gap | rate |
|---|---|---|---|---|---|---|
| 2019-01-30 | 1793 | 926 | 766 | 1692 | 101 | 94.37% |
| 2019-02-27 | 1793 | 926 | 767 | 1693 | 100 | 94.42% |
| 2019-03-29 | 1795 | 930 | 768 | 1698 | 97 | 94.60% |
| 2019-04-30 | 1793 | 931 | 768 | 1699 | 94 | 94.76% |

**All 84 fully-harvested months** (2019-01 … 2026-03):

| | value |
|---|---|
| coverage min / median / max | **93.85% / 94.59% / 98.42%** |
| gap min / median / max | 31 / 100 / 114 |
| months at or above the pre-2019 lineage FLOOR (93.04%) | **84 / 84** |
| months at or above its CEILING (94.21%) | 79 / 84 |

Yearly medians are flat, then improve — there is no decay and no era where the
official series thins out:

| year | months | median | min |
|---|---|---|---|
| 2019 | 12 | 94.67% | 94.28% |
| 2020 | 11 | 94.55% | 94.38% |
| 2021 | 10 | 94.44% | 93.85% |
| 2022 | 12 | 94.55% | 94.05% |
| 2023 | 12 | 94.54% | 94.25% |
| 2024 | 12 | 94.67% | 94.26% |
| 2025 | 12 | 95.85% | 95.28% |
| 2026 | 3 | 98.16% | 98.01% |

**The bar is not 100%.** The existing admissible pre-2019 PBR_TSE lineage carries
its own NA rate — measured across the twelve 2018 month-ends, 1,657–1,692 of
1,781–1,796 priced securities, i.e. **93.03%–94.21%**.

⇒ **Every one of the 84 enumerated months clears the frozen lineage's own floor**,
and 79 of 84 clear its ceiling. §4.1 complete-case already absorbs an NA rate of
this size, so official coverage is not merely adequate — it is at least as
complete as what B0 reads today for the pre-2019 era.

## 3. PIT / availability semantics

| | TWSE | TPEx |
|---|---|---|
| Query key | trading session (YYYYMMDD) | trading session (ROC) |
| Echoes queried date | yes (`date=20190130`) | yes (`108/01/30`) |
| Discloses statement vintage | **yes — `財報年/季`** | **2019: no; 2026: yes (`114Q4`)** |
| Non-session date | empty payload | empty payload |

The TWSE vintage field is direct PIT evidence: on 2019-01-30 it reports **107/3
(2018 Q3)** for 922 of 927 rows, 107/4 for 4, 106/4 for 1 — the most recently
ANNOUNCED statement at that date, not a later restatement.

**Asymmetry worth a ruling:** TPEx's 2019 response does not carry the statement
vintage, so for the 上櫃 side the book-value period underlying each early ratio is
not stated by the source itself. It is present by 2026.

## 4. Residual gap, characterised

The ~94–101 uncovered securities per session are **not** an exchange failure. Two
components, both mirroring NA classes the frozen lineage already has:

- securities not on either official board at that date (emerging board / 興櫃),
  which have no official PE-PBR report at all;
- securities on a board whose PBR the exchange publishes as `-` (no meaningful
  ratio, e.g. non-positive book value).

By CURRENT 上市別 the 2019-04-30 gap splits OTC 46 / TSE 41 / UNPUB 7 — but that
is a **current snapshot** classification and therefore look-ahead-contaminated in
exactly the way §2.3 describes; several are likely later promotions from 興櫃. A
PIT board classification would be needed to settle it, and board membership is
already available point-in-time from the exchange files themselves.

## 5. What is NOT yet established

- Three months (2020-06-30, 2021-02-26, 2021-12-30) still lack the TWSE side.
  TPEx succeeded for all three; only TWSE refused, and it refused with a
  TCP-level rate limit, not an empty result. They are not evidence of a gap —
  the same endpoint served the months either side of each. `fetch_official_pbr.py`
  is idempotent and is re-fetching them.
- Value-level agreement between official PBR and the pre-2019 PBR_TSE lineage on
  overlapping dates. Coverage was audited; per-security value reconciliation was
  not, and it should be done on pre-2019 sessions where BOTH the admissible
  yearly export and the official sources exist.

## 6. Conclusion offered to the ruling (not a decision)

Official exchange sources are **not insufficient**. They exist for both boards
across the affected era, they are keyed to trading sessions, TWSE states its
statement vintage, and their combined coverage matches or exceeds the frozen
lineage's own. What remains is a ruling on whether an official-exchange series
may serve as the 2019+ TSE PBR lineage, plus the TPEx vintage-disclosure
asymmetry — and, if admitted, a complete harvest and value reconciliation.
