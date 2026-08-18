# Official Exchange Valuation Lineage Audit — findings

> ## ⚠ SUPERSEDED — read `FINDINGS_full_harvest.md` instead
>
> This file was written by a second session running concurrently with the audit
> (commits `72ceee55` / `428e56c0`). Its qualitative sections stand; **its
> coverage numbers do not**, because the report they were read off counts four
> TWSE months as zero and counts TPEx's literal `"null"` ratio as a published
> value — see `superseded/README.md`. Corrected canonical figures:
> **coverage 93.69% .. 98.42%, median 94.60%, gap 31 .. 113, TWSE 87/87,
> TPEx 87/87, TRANSPORT_FAIL = 0.**
>
> `value_pbr_lineage_2019plus` was subsequently **RULED CLOSED** (R1-R7); this
> file predates the ruling and the "remains OPEN" line below is historical.

**Date:** 2026-08-18 · **Status:** SUPERSEDED by `FINDINGS_full_harvest.md`.
**Nothing was ruled on here.** `value_pbr_lineage_2019plus` was OPEN when this
was written.

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

**All 87 months** (2019-01 … 2026-03): the numbers that stood here
(93.85% / 94.60% / 98.42%, gap 31 / 100 / 114, and a yearly-median table) were
computed from the defective report now in `superseded/`. **Corrected figures live
in `FINDINGS_full_harvest.md` §2** — coverage 93.69% (2021-11) .. 98.42%
(2026-03), median 94.60%, gap 31 .. 113, and a yearly-mean table.

**The bar is not 100%.** The existing admissible pre-2019 PBR_TSE lineage carries
its own NA rate — measured across the twelve 2018 month-ends, 1,657–1,692 of
1,781–1,796 priced securities, i.e. **93.03%–94.21%**.

⇒ The comparison this section drew from that band was **cross-era** (2019+
official against 2018 lineage). Measured in the same era on the same population
(36 sessions, 2016-2018), official coverage is 91.03% / 92.49% / 93.99% against
the lineage's own 91.84% / 92.73% / 94.21% — official is between 1.27 pp thinner
and exactly equal, median −0.11 pp. The substantive point survives (the two are
within about a point, and official never adds a security the lineage lacks); the
direction stated here did not. See `FINDINGS_full_harvest.md` §3.

## 3. PIT / availability semantics

| | TWSE | TPEx |
|---|---|---|
| Query key | trading session (YYYYMMDD) | trading session (ROC) |
| Echoes queried date | yes (`date=20190130`) | yes (`108/01/30`) |
| Discloses statement vintage | **yes — `財報年/季`**, from 2017-04-12 per the page itself | **no until 2025-01-02**, measured (absent 2024-12-31) |
| Non-session date | empty payload | empty payload |

The TWSE vintage field is direct PIT evidence: on 2019-01-30 it reports **107/3
(2018 Q3)** for 922 of 927 rows, 107/4 for 4, 106/4 for 1 — the most recently
ANNOUNCED statement at that date, not a later restatement.

**Asymmetry worth a ruling:** TPEx's 2019 response does not carry the statement
vintage, so for the 上櫃 side the book-value period underlying each early ratio is
not stated by the source itself. It appears from 2025-01-02, i.e. 72 of the 87
decision months have no 上櫃 vintage disclosure. **Ruled** — admissible with the
limitation recorded verbatim (R2); see `FINDINGS_full_harvest.md` §4 for the
documentary and behavioural evidence, including TWSE's own
`且不作回溯計算` statement.

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

- (Resolved.) Three months initially lacked the TWSE side purely because of a
  TCP-level rate limit; a later idempotent pass filled all three, and each landed
  in the same 94% band as its neighbours. No month is missing from either
  exchange.
- (Done, elsewhere.) Value-level agreement between official PBR and the pre-2019
  PBR_TSE lineage was measured over all 36 month-ends 2016-2018: TWSE 32,284
  comparisons at 100.00% exact equality, TPEx 26,419 at 99.96%. See
  `FINDINGS_full_harvest.md` §3.

## 6. Conclusion offered to the ruling (not a decision)

Official exchange sources are **not insufficient**. They exist for both boards
across the affected era, they are keyed to trading sessions, and TWSE states its
statement vintage. (The coverage claim originally made here was cross-era; see the
correction in §2.) What remained was a ruling on whether an official-exchange
series may serve as the 2019+ TSE PBR lineage, plus the TPEx vintage-disclosure
asymmetry — and, if admitted, a complete harvest and value reconciliation.

**Both were subsequently supplied.** The harvest and the value reconciliation are
in `FINDINGS_full_harvest.md`; the ruling is R1-R7, recorded in the master
preregistration, and `value_pbr_lineage_2019plus` is CLOSED.
