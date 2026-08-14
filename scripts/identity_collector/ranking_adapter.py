"""Frozen module path (collector_schema.json's `code_hashes.ranking_adapter_sha256`
comment: "Module path fixed: scripts/identity_collector/ranking_adapter.py").
P-A raw rows -> parity-screened rows (FR-17, AC-5). Fail-closed on NULL
composite -- a missing score means production genuinely produced no score for
that row, which MUST surface as a hard error, never a silent skip or 0-fill.

Field name note (corrected for real integration, item 5): the P-A source for
this collector is `core/score_store.py::screen_by_composite_at`, whose real
output column is named `composite` (see its SQL: `SELECT stock_id, ...,
composite, ROUND(_pct*100,1) AS pct_rank, ...`). `real_composite` is a
DIFFERENT, unrelated term from docs/研究紀律_ResearchDiscipline.md's
`lab_paths.load_real_panel()` -- that names the RESEARCH backtest panel's
真身/替身 composite distinction, a different data source entirely. Using that
term here would have been a real column-name mismatch against the actual
production adapter; fixed to match `score_store`'s real schema.
"""

REQUIRED_FIELDS = ("as_of", "stock_id", "mode", "composite")


def screen_by_composite_parity(rows: list) -> list:
    out = []
    for r in rows:
        for f in REQUIRED_FIELDS[:3]:
            if r.get(f) in (None, ""):
                raise ValueError(f"P-A row missing required field {f!r}: {r!r}")
        composite = r.get("composite")
        if composite is None:
            raise ValueError(f"NULL composite for stock_id={r.get('stock_id')} as_of={r.get('as_of')} -- fail-closed")
        out.append(dict(r))
    return out


def top_limit_screen(rows: list, top_limit: int) -> list:
    """p_a_top_limit (frozen constant, epoch.py IDENTITY_DEFINING_CONSTANTS).
    Raw-vs-parity overflow guard: parity output MUST NOT exceed the raw row
    count, and MUST NOT silently exceed top_limit either."""
    if len(rows) > top_limit:
        ranked = sorted(rows, key=lambda r: r["composite"], reverse=True)
        return ranked[:top_limit]
    return list(rows)


def require_unique_weights_version(rows: list) -> str:
    versions = {r.get("weights_version") for r in rows}
    if len(versions) != 1 or None in versions:
        raise ValueError(f"weights_version not uniform across P-A snapshot: {sorted(v for v in versions if v is not None)}")
    return next(iter(versions))


def rows_from_score_store_dataframe(df) -> list:
    """Real integration bridge: core.score_store.screen_by_composite_at
    returns a DataFrame; this collector's own functions operate on row dicts.
    weights_version is not one of score_store's own columns (it is a
    collector-side identity-defining constant, epoch.py's
    IDENTITY_DEFINING_CONSTANTS has no such key either -- it is supplied by
    the caller, e.g. from CollectorConfig.frozen_constants, not read off the
    DataFrame)."""
    return df.to_dict("records")
