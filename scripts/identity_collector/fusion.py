"""FR-19/20, AC-6 — P-app and P-L4a fusion membership computed on the SAME
frozen input copies, exact-set compared. `compute_dual_fusion` never touches
Streamlit, OrderIntent, PositionState, or L4b (AC-6's other half, FR-21).

Item 5 fix -- real integration: `tab_fusion` in app.py is confirmed to be a
`with tab_fusion:` Streamlit tab-context block (NOT a `def`, verified by
direct inspection), so there is no pure function there to import without
editing app.py itself -- forbidden this phase (production file). Per EC-7
("若會改 public behavior，停止修訂規格") that edit is out of scope here, and
per scripts/l4a_decision.py's OWN module docstring, this project has already
solved this exact problem once: l4a_decision.py is a deliberate SECOND,
INDEPENDENT reimplementation of app.py's tab_fusion formula, specifically
because app.py "是 Streamlit 頁面,不適合當函式庫用" -- the same discipline
docs/研究紀律_ResearchDiscipline.md §3 requires project-wide (two independent
paths, reconciled). `compute_app_path_fusion` below applies that identical
discipline one level down: it is the collector's own independent
reimplementation (formula copied verbatim from app.py:1650,1696-1701, cited
inline below), cross-checked against a REAL call to
scripts/l4a_decision.py::compute_target_list (`compute_l4a_path_fusion_frozen`)
-- not a synthetic stand-in.
"""
import contextlib
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ProductionInternalDivergence(Exception):
    pass


class FrozenInputMutatedDuringComputation(Exception):
    """FR-19 safety net -- see run_real_dual_fusion."""


def compute_dual_fusion(frozen_universe: list, app_fusion_fn, l4a_fusion_fn) -> tuple:
    """Generic contract, exercised in tests with two injected callables.
    Runs both fusion paths against the identical frozen_universe object
    (never re-reading a live/mutable source mid-computation, FR-19) and
    returns (app_membership: set, l4a_membership: set). Raises
    ProductionInternalDivergence on any mismatch -- caller decides whether to
    still persist raw evidence (FR-20 requires it)."""
    app_membership = set(app_fusion_fn(frozen_universe))
    l4a_membership = set(l4a_fusion_fn(frozen_universe))
    if app_membership != l4a_membership:
        raise ProductionInternalDivergence(
            f"app-only={sorted(app_membership - l4a_membership)} l4a-only={sorted(l4a_membership - app_membership)}"
        )
    return app_membership, l4a_membership


FUSION_PCT = 20  # app.py:1650 `_FUSION_PCT`, scripts/l4a_decision.py:44 `FUSION_PCT` -- frozen, must not drift


def compute_app_path_fusion(p_a_frozen, p_b_frozen, fusion_pct: int = FUSION_PCT) -> set:
    """Independent reimplementation of app.py:1696-1701's tab_fusion formula:
    `_pool["c2_pct"] = _pool["c2_score_full"].rank(pct=True) * 100.0`;
    `_thr = 100 - _FUSION_PCT`; membership = rows where
    `pct_rank >= _thr AND c2_pct >= _thr`. p_a_frozen/p_b_frozen are frozen
    DataFrame copies (never re-read mid-computation, FR-19)."""
    p_b = p_b_frozen.copy()
    p_b["stock_id"] = p_b["stock_id"].astype(str)
    p_b["c2_pct"] = p_b["c2_score_full"].rank(pct=True) * 100.0
    c2_lookup = dict(zip(p_b["stock_id"], p_b["c2_pct"]))

    p_a = p_a_frozen.copy()
    p_a["stock_id"] = p_a["stock_id"].astype(str)
    thr = 100.0 - fusion_pct
    membership = set()
    for _, row in p_a.iterrows():
        c2_pct = c2_lookup.get(row["stock_id"])
        if c2_pct is None or row["pct_rank"] < thr or c2_pct < thr:
            continue
        membership.add(row["stock_id"])
    return membership


@contextlib.contextmanager
def _frozen_l4a_call_context(frozen_p_a, frozen_p_b_bytes: bytes, as_of: str):
    """Item 2 fix (P1, round 2): STRUCTURALLY prevents
    l4a_decision.compute_target_list from re-reading any live source, rather
    than detecting a re-read after the fact. `l4a_decision.py`'s own
    signature has no parameter to accept pre-fetched data, so the two points
    it reads from internally are monkeypatched for the exact duration of one
    call, then unconditionally restored (try/finally, even on exception):
    (a) `core.score_store.screen_by_composite_at` is replaced with a closure
    that returns the ALREADY-FETCHED `frozen_p_a` object directly -- zero
    queries happen; (b) `l4a_decision.UNIV_DIR` (its module-level global,
    read fresh at call time inside `compute_target_list`, per ordinary Python
    scoping) is repointed at a throwaway temp directory holding the EXACT
    bytes already read for P-B -- `pd.read_csv` inside `compute_target_list`
    reads that frozen copy, never the live `outputs/universe_pool/` file a
    second time. Neither monkeypatch edits any file on disk outside the temp
    directory, and both are reverted before this context manager returns."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from core import score_store
    import l4a_decision

    tmp_dir = tempfile.mkdtemp(prefix="p0r2_frozen_l4a_")
    try:
        (Path(tmp_dir) / f"c2_fullpool_{as_of}.csv").write_bytes(frozen_p_b_bytes)

        original_screen_fn = score_store.screen_by_composite_at
        original_univ_dir = l4a_decision.UNIV_DIR

        def _frozen_screen_by_composite_at(_as_of, mode="balanced", top=3000, **kwargs):
            return frozen_p_a.copy()

        score_store.screen_by_composite_at = _frozen_screen_by_composite_at
        l4a_decision.UNIV_DIR = Path(tmp_dir)
        try:
            yield l4a_decision
        finally:
            score_store.screen_by_composite_at = original_screen_fn
            l4a_decision.UNIV_DIR = original_univ_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def compute_l4a_path_fusion_frozen(frozen_p_a, frozen_p_b_bytes: bytes, as_of: str, mode: str = "balanced", fusion_pct: int = FUSION_PCT, top_n=None) -> set:
    """Calls the REAL scripts/l4a_decision.py::compute_target_list -- genuine
    production code, not a reimplementation -- but under `_frozen_l4a_call_context`
    so it operates on the SAME frozen P-A/P-B already fetched for the app
    path, never re-reading a live source. Raises SourceReadError (translated
    from compute_target_list's own SystemExit fail-closed behavior) on
    empty/missing frozen inputs."""
    from identity_collector.source_adapters import SourceReadError

    with _frozen_l4a_call_context(frozen_p_a, frozen_p_b_bytes, as_of) as l4a_decision:
        try:
            target_df, _price_lookup = l4a_decision.compute_target_list(as_of, mode=mode, fusion_pct=fusion_pct, top_n=top_n)
        except SystemExit as e:
            raise SourceReadError(f"l4a_decision.compute_target_list fail-closed for as_of={as_of} mode={mode}: {e}") from e
    return set(target_df["stock_id"].astype(str))


def run_real_dual_fusion(as_of: str, mode: str = "balanced", fusion_pct: int = FUSION_PCT):
    """Item 5/2 fix: end-to-end REAL integration with TRUE single-read FR-19
    compliance. P-A/P-B are each read exactly ONCE (via source_adapters);
    `compute_app_path_fusion` uses those objects directly; `compute_l4a_path_
    fusion_frozen` uses the SAME frozen copies via `_frozen_l4a_call_context`
    -- there is no second read of anything, so there is nothing to
    detect-after-the-fact and no `FrozenInputMutatedDuringComputation` path
    is needed any more (the class is kept for backward-compatible import
    only; nothing raises it now that re-reading is structurally impossible).

    Round 3 fix (P1): P-B's DataFrame and raw bytes previously came from TWO
    separate physical reads (`read_p_b_fullpool`'s own `pd.read_csv(path)`,
    then this function's `Path(path).read_bytes()`) -- a source change in
    that window could desync the app-path's DataFrame from the l4a-path's
    frozen bytes, still violating FR-19 despite P-A already being single-read.
    `read_p_b_fullpool` now performs the one physical read itself and returns
    both derived forms from it; this function no longer reads P-B's bytes
    independently at all.

    Returns (app_membership, l4a_membership, frozen_p_a, frozen_p_b)."""
    from identity_collector.source_adapters import read_p_a_composite, read_p_b_fullpool

    p_a = read_p_a_composite(as_of, mode=mode)
    p_b, p_b_bytes, _p_b_path = read_p_b_fullpool(as_of)

    app_membership = compute_app_path_fusion(p_a, p_b, fusion_pct)
    l4a_membership = compute_l4a_path_fusion_frozen(p_a, p_b_bytes, as_of, mode=mode, fusion_pct=fusion_pct)

    if app_membership != l4a_membership:
        raise ProductionInternalDivergence(
            f"app-only={sorted(app_membership - l4a_membership)} l4a-only={sorted(l4a_membership - app_membership)}"
        )
    return app_membership, l4a_membership, p_a, p_b
