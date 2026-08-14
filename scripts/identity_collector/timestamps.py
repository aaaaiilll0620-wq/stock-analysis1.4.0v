"""TaipeiUtcTimestampPair — EC-13: receipts always carry both Asia/Taipei local
time and UTC. Schema can only check the two are date-time-shaped strings
(collector_schema.json note: "JSON Schema cannot verify same-instant+8:00
offset -- semantic validator"); that same-instant check lives here, real for
both construction (`now_pair`) and validation (`check_same_instant`, semantic
check #2).
"""
from datetime import datetime, timedelta, timezone

TAIPEI_TZ = timezone(timedelta(hours=8))
LIVE_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"  # matches LiveReceiptProjectionPlaceholderPolicy.live_timestamp_format's %:z intent


def _fmt(dt: datetime) -> str:
    s = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    off = dt.strftime("%z")  # +0800 / +0000
    return f"{s}{off[:3]}:{off[3:]}"


def pair_from_utc(dt_utc: datetime) -> dict:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)
    dt_taipei = dt_utc.astimezone(TAIPEI_TZ)
    return {"utc": _fmt(dt_utc), "local_taipei": _fmt(dt_taipei)}


def now_pair(clock=None) -> dict:
    """`clock` is an injectable zero-arg callable returning a tz-aware UTC
    datetime -- tests MUST inject a fixed clock (NFR-3 determinism; no
    synthetic fixture may depend on wall-clock `datetime.now()`)."""
    if clock is None:
        raise ValueError("now_pair() requires an explicit clock in this offline collector -- no implicit datetime.now()")
    return pair_from_utc(clock())


def check_same_instant(pair: dict) -> bool:
    """Semantic check #2: utc/local_taipei must name the same instant at
    exactly +8:00. Returns False (never raises) so callers can fold this into
    a receipt's own list of validation failures."""
    try:
        utc = datetime.strptime(pair["utc"], LIVE_TIMESTAMP_FORMAT)
        taipei = datetime.strptime(pair["local_taipei"], LIVE_TIMESTAMP_FORMAT)
    except (KeyError, ValueError):
        return False
    if taipei.utcoffset() != timedelta(hours=8):
        return False
    return utc.astimezone(timezone.utc) == taipei.astimezone(timezone.utc)
