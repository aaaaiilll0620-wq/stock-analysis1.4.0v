"""FR-10/11 exact-date capture + edge cases EC-1/EC-2/EC-3. Collector never
reads a live production source directly here -- callers pass in already-read
rows (from a real read-only production call, OR, in every Phase C test, a
synthetic fixture). This module only enforces the identity/consistency rules;
it performs no I/O of its own.
"""


class SourceDateMismatch(Exception):
    """FR-11: P-A/P-B latest available dates differ -- no nearest-fill."""


class SourceDateConflict(Exception):
    """EC-1/EC-2: internal date inconsistency within one source."""


class DuplicateKey(Exception):
    """EC-3: same (as_of, stock_id, mode) twice -- abort, no keep-last."""


def resolve_common_as_of(p_a_available_dates: list, p_b_available_dates: list) -> str:
    if not p_a_available_dates or not p_b_available_dates:
        raise SourceDateMismatch("one or both sources have zero available dates")
    latest_a, latest_b = max(p_a_available_dates), max(p_b_available_dates)
    if latest_a != latest_b:
        raise SourceDateMismatch(f"P-A latest={latest_a!r} != P-B latest={latest_b!r}")
    return latest_a


def check_uniform_as_of(rows: list, date_field: str = "as_of") -> str:
    """EC-1: P-A rows across different stocks must share one as_of."""
    dates = {r[date_field] for r in rows}
    if len(dates) != 1:
        raise SourceDateConflict(f"rows have inconsistent {date_field} values: {sorted(dates)}")
    return next(iter(dates))


def check_filename_matches_content_date(filename_date: str, content_date: str) -> None:
    """EC-2: P-B filename date must equal content date."""
    if filename_date != content_date:
        raise SourceDateConflict(f"filename date {filename_date!r} != content date {content_date!r}")


def check_no_duplicate_keys(rows: list, key_fields=("as_of", "stock_id", "mode")) -> None:
    """EC-3: abort on any duplicate key -- never silently keep-last."""
    seen = set()
    for r in rows:
        key = tuple(r.get(f) for f in key_fields)
        if key in seen:
            raise DuplicateKey(f"duplicate key {key} -- abort, no keep-last")
        seen.add(key)
