"""Item 5 fix: REAL read-only P-A/P-B source adapters (FR-17/18, FR-43).

Every function here is READ-ONLY against real production paths/modules --
never writes, never rebuilds a cache, never invokes a producer (FR-43: "MUST
NOT 主動呼叫、重跑或修復 producers"). P-B genuinely reads real committed files
(`outputs/universe_pool/c2_fullpool_{as_of}.csv`) that already exist in this
repository for the three NFR-7 dates. P-A calls the REAL
`core.score_store.screen_by_composite_at`.

Docstring note (round 3 fix): earlier text here asserted "this sandboxed
session has no populated FinMind score cache" as if that were a structural
property of this adapter -- it was only ever a fact about one particular host
at one particular time, and reads exactly like the "assumes no score cache"
bug the round-2 review caught in this module's OWN tests. Whether P-A is
present or missing on any given host is not this module's concern: it always
attempts the real read and turns "no data" into `SourceReadError`, on every
host, present-cache or not. Tests exercise both branches deterministically
via `core.data_cache.set_store()` injection (see
tests/test_identity_collector_blockers_round2.py), never via an assumption
about this or any other host's real cache.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UNIV_DIR = REPO_ROOT / "outputs" / "universe_pool"


class SourceReadError(Exception):
    """-> MISSING_P_A / MISSING_P_B at the caller's discretion."""


def read_p_b_fullpool(as_of: str, universe_pool_dir=None):
    """Real, read-only read of outputs/universe_pool/c2_fullpool_{as_of}.csv.

    Round 3 fix (P1): the source is read from disk EXACTLY ONCE, via
    `Path.read_bytes()`. The DataFrame is then parsed from THOSE SAME
    in-memory bytes via `io.BytesIO` -- never a second `pd.read_csv(path)`
    call against the path. The round-2 version called `pd.read_csv(path)`
    (physical read #1) and then, in `fusion.run_real_dual_fusion`,
    `Path(path).read_bytes()` (physical read #2) -- two independent reads of
    a live, external file, with no guarantee the source was unchanged between
    them. A rename/rewrite landing in that window would have produced a
    DataFrame and a "frozen" byte copy describing two DIFFERENT snapshots,
    silently violating FR-19 exactly the way this function's whole purpose is
    to prevent. Returns (dataframe, frozen_bytes, source_path) -- callers that
    need the parsed form and callers that need the raw bytes (freezing a copy
    for l4a_decision.py to read, in `fusion.py`) now always see the identical
    snapshot by construction, not by two reads that merely usually agree."""
    import io

    import pandas as pd

    p = Path(universe_pool_dir or UNIV_DIR) / f"c2_fullpool_{as_of}.csv"
    if not p.exists():
        raise SourceReadError(f"P-B file not found: {p}")
    frozen_bytes = p.read_bytes()  # THE single physical read of this source
    df = pd.read_csv(io.BytesIO(frozen_bytes), dtype={"stock_id": str})
    if "c2_score_full" not in df.columns:
        raise SourceReadError(f"{p} missing required column c2_score_full")
    return df, frozen_bytes, p


def read_p_a_composite(as_of: str, mode: str = "balanced", top: int = 3000):
    """Real, read-only call to core.score_store.screen_by_composite_at.
    score_store itself returns an EMPTY DataFrame when there is no cache or no
    rows for as_of (its own documented behavior, `_has_scores()` gate) -- this
    adapter is what turns that into a hard SourceReadError (MISSING_P_A) for
    the collector, since a collector run must never treat "no data" as "empty
    universe, proceed anyway" (EC-1's sibling concern for P-A).

    Testability note: `core.data_cache` ALREADY provides a production-
    sanctioned dependency-injection point for exactly this purpose --
    `data_cache.set_store(store)` / `get_store()` ("供測試注入記憶體 store",
    its own docstring). Tests should use that (see
    tests/test_identity_collector_blockers_round2.py) rather than assuming
    anything about whichever real cache happens to exist on the host running
    this suite."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from core import score_store

    df = score_store.screen_by_composite_at(as_of, mode=mode, top=top)
    if df is None or df.empty:
        raise SourceReadError(f"P-A composite snapshot empty for as_of={as_of} mode={mode} (no score cache populated, or no rows for this date)")
    return df


def canonical_dataframe_records(df, sort_by) -> list:
    """Item 2 fix: fixed key/column-order canonicalization BEFORE hashing a
    DataFrame's content. `df.to_dict("records")` alone preserves whatever row
    order the source (a SQL query with `ORDER BY composite DESC`, or a CSV's
    on-disk order) happened to return -- for TIED values, that order is not
    guaranteed stable across two otherwise-identical query executions, so
    hashing raw `to_dict("records")` output could report a false "changed"
    between two reads of byte-identical logical data. Rows are sorted by
    `sort_by` (a stable tiebreaker key, e.g. stock_id) and each row's own keys
    are alphabetized, before conversion to records."""
    import pandas as pd

    ordered = df.sort_values(list(sort_by) if not isinstance(sort_by, str) else [sort_by], kind="stable").reset_index(drop=True)
    records = ordered.to_dict("records")
    return [dict(sorted(r.items())) for r in records]


def canonical_dataframe_hash(df, sort_by) -> str:
    from identity_collector.hashing import obj_hash

    return obj_hash(canonical_dataframe_records(df, sort_by))
