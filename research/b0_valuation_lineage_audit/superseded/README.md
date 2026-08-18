# Superseded first-pass audit pipeline — kept as evidence, not as result

Nothing here may be cited as the audit result. The canonical result is
`../FINDINGS_full_harvest.md` with the artifacts it names. These four files are
retained because they are what a second, concurrently-running session actually
committed at `72ceee55` (2026-08-18 22:39), and deleting them would erase the
record of a discrepancy a ruling has to know about — not because their numbers
are usable.

| file | why it is superseded |
|---|---|
| `fetch_official_pbr.py` | returns the same `None` when the host REFUSES a connection and when the host ANSWERS "no data for this date". Those are opposite facts, and conflating them is how a rate-limit refusal gets read as absent history. Replaced by `../harvest_official_pbr.py`, which terminates every session in exactly one of `OK` / `NO_DATA` / `TRANSPORT_FAIL` and caches only the first two. |
| `analyse_coverage.py` | its NA token list is `("", "-", "NA", "N/A", "0.00")`, which does not contain `null`. TPEx returned the literal string `null` as the ratio for 21 security-months in 2021-07 .. 2022-02, and every one of them was counted as a published ratio. Replaced by `../analyse_87month_coverage.py`. |
| `official_pbr_coverage_raw.json` | the ledger of the superseded harvest. |
| `official_pbr_coverage_report.json` | **contains four months that are simply wrong**, see below. |

## The specific defect in `official_pbr_coverage_report.json`

```
coverage_rate_min : 0.4253          <- reported minimum
fetch_failures    : 4
2020-04 / 2020-06 / 2021-02 / 2021-12   covered_twse_listed = 0
```

The TWSE payloads for all four months exist, parse, and were already on disk when
that report was written — 942, 943, 945 and 954 rows, each with its sha256
recorded in `artifacts/valuation_lineage_audit/norm/`. The zero is a bookkeeping
gap in that pipeline (it reads a `*_ids_*.json` sidecar that its own fetch step
never wrote for sessions harvested by the other pipeline), not missing data.

Note that the prose committed one minute later (`428e56c0`) states 87/87 and a
93.85% minimum. **The committed document and the committed artifact underneath it
do not agree with each other**, and neither agrees with the corrected result.

## Corrected canonical figures

```
TWSE 87/87   TPEx 87/87   TRANSPORT_FAIL = 0   NO_DATA = 0
coverage 93.69% .. 98.42%, median 94.60%
```

Reproduced by `../analyse_87month_coverage.py` from the cached payloads.
