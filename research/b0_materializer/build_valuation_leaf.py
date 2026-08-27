# -*- coding: utf-8 -*-
"""W4 · the valuation leaf producer: board + session + payload key.

The only family addressed by a KEY rather than a filename, and the reason is
C-48 / C-49: for 2019+, `per_tse` and `pbr_tse` have a frozen first-party
lineage and `TEJ_SUBSTITUTION_ALLOWED = False`. The exchange payload IS the
source, so its identity has to be exact — which a `*.json` glob cannot express.
One session's valuation is (board, session), and within the payload the ratios
live under named fields whose names are part of the contract.

WHY THE FIELD NAMES ARE DECLARED
--------------------------------
`harvest_official_pbr.parse_twse` / `parse_tpex` resolve columns with

    i_pbr = idx("股價淨值比")        # -> None if the exchange renames it

and then every row does `if i_pbr is not None:`. So a renamed column does not
raise, does not warn, and does not produce a partial answer — it produces an
EMPTY one. A whole session of valuations quietly becomes NA, and NA is a value
the frozen lineage already has a large legitimate class of (C-49), so nothing
downstream finds it surprising either.

Declaring the field names turns that into an abort.

THE TWO BOARDS ARE NOT SYMMETRIC
--------------------------------
Measured on 2026-03-30:

    TWSE  ['證券代號','證券名稱','收盤價','殖利率(%)','股利年度','本益比','股價淨值比','財報年/季']
    TPEx  ['股票代號','公司名稱','本益比','每股股利','股利年度','殖利率(%)','股價淨值比','財報年/季']

TPEx carries NO `收盤價`. That asymmetry is why the priced-universe denominator
is projected from the sealed price panel (`closes_2019plus_route.csv`) rather
than read out of the payloads, and it is declared here so that a future reader
does not "fix" the missing column by inventing one.

    python research/b0_materializer/build_valuation_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError, build_leaf, write_leaf,
)

DATASET = "valuation"

PAYLOAD_DIRECTORY = os.path.join("artifacts", "valuation_lineage_audit")

# Both boards are required. The frozen universe is sii ∪ otc, and a session that
# answered for one board only is not a session that answered.
BOARDS: tuple[str, ...] = ("twse", "tpex")

# The payload key: where the rows live, and which named columns carry the frozen
# ratios. `rows_path` differs because the two APIs differ in shape, not because
# anyone chose it.
BOARD_PAYLOAD_CONTRACT: dict = {
    "twse": {
        "board": "TWSE",
        "rows_path": ("data",),
        "fields_path": ("fields",),
        "id_field": "證券代號",
        "required_fields": ("證券代號", "本益比", "股價淨值比"),
        "optional_fields": ("收盤價", "財報年/季"),
        "carries_close": True,
    },
    "tpex": {
        "board": "TPEx",
        "rows_path": ("tables", 0, "data"),
        "fields_path": ("tables", 0, "fields"),
        "id_field": "股票代號",
        "required_fields": ("股票代號", "本益比", "股價淨值比"),
        "optional_fields": ("財報年/季",),
        # Measured: TPEx publishes no 收盤價 on this endpoint. The priced
        # universe therefore comes from the sealed price panel, never from here.
        "carries_close": False,
    },
}

CLOSE_SOURCE_POLICY = {
    "rule": "PRICED_UNIVERSE_COMES_FROM_THE_PRICE_PANEL_NOT_THE_PAYLOAD",
    "detail": (
        "TWSE publishes 收盤價 on this endpoint and TPEx does not. Taking the "
        "denominator from whichever payload happens to carry it would make the "
        "universe board-dependent, so both boards' denominators are projected "
        "from the sealed price panel (closes_2019plus_route.csv)."),
}

SUBSTITUTION_POLICY = {
    "rule": "TEJ_SUBSTITUTION_FORBIDDEN_FOR_2019_PLUS",
    "detail": (
        "C-48 / C-49: `value_pbr_tej_substitution_allowed` is False. The "
        "exchange payload is the lineage, so a missing session is a missing "
        "session — never a TEJ fill-in."),
}


def _dig(doc, path):
    cur = doc
    for step in path:
        cur = cur[step] if isinstance(step, int) else cur.get(step)
        if cur is None:
            return None
    return cur


def read_payload_key(path: str, board_key: str) -> dict:
    """Open one payload and resolve its declared key. Aborts on any drift."""
    spec = BOARD_PAYLOAD_CONTRACT[board_key]
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError("abort: %s is not readable JSON: %s" % (path, exc))

    fields = _dig(doc, spec["fields_path"])
    rows = _dig(doc, spec["rows_path"])
    if fields is None or rows is None:
        raise ManifestError(
            "abort: %s does not have the declared payload shape (fields at %s, "
            "rows at %s). The endpoint changed shape, which is a source change."
            % (os.path.basename(path), ".".join(map(str, spec["fields_path"])),
               ".".join(map(str, spec["rows_path"]))))

    missing = [f for f in spec["required_fields"] if f not in fields]
    if missing:
        raise ManifestError(
            "abort: %s is missing declared field(s) %s.\n"
            "  fields present: %s\n"
            "A renamed column does NOT raise in the parser — `idx()` returns "
            "None and every row is skipped, so the whole session silently "
            "becomes NA. That is why the names are declared here."
            % (os.path.basename(path), missing, list(fields)))

    if not rows:
        raise ManifestError(
            "abort: %s carries zero rows. An empty answer and a missing answer "
            "are different facts and must not share a representation."
            % os.path.basename(path))

    return {"fields": list(fields), "rows": len(rows),
            "field_index": {f: fields.index(f)
                            for f in spec["required_fields"]
                            + tuple(f for f in spec["optional_fields"]
                                    if f in fields)}}


def build(run_id: str, as_of: str, payload_dir: str = "") -> dict:
    """One leaf for ONE session: both boards' payloads at `as_of`."""
    directory = payload_dir or os.path.join(REPO, PAYLOAD_DIRECTORY)
    if not os.path.isdir(directory):
        raise ManifestError("abort: valuation payload store not found: %s"
                            % directory)
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    entries, absent = [], []
    for board_key in BOARDS:
        spec = BOARD_PAYLOAD_CONTRACT[board_key]
        name = "%s_%s.json" % (board_key, as_of)
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            absent.append(name)
            continue
        key = read_payload_key(path, board_key)
        entries.append({
            "locator": name,
            "format": "json:exchange_payload",
            "raw_sha256": file_sha256(path),
            "export_vintage": as_of,
            "observed_at": observed_at,
            "source_family": "TEJ",       # first-party exchange = the authority
            "authority": "AUTHORITATIVE",
            "disposition": "consumed",
            # The payload key. This is the addressing, not the filename.
            "board": spec["board"],
            "session": as_of,
            "rows_path": list(spec["rows_path"]),
            "fields_path": list(spec["fields_path"]),
            "id_field": spec["id_field"],
            "required_fields": list(spec["required_fields"]),
            "carries_close": spec["carries_close"],
            "resolved_fields": key["fields"],
            "rows": key["rows"],
        })

    if absent:
        raise ManifestError(
            "abort: %d board payload(s) for session %s have not been harvested: "
            "%s\n  store: %s\n"
            "Both boards are required — the frozen universe is sii ∪ otc, and a "
            "session that answered for one board only is not a session that "
            "answered. C-48/C-49 forbid a TEJ substitute, so this is harvested "
            "or it is missing." % (len(absent), as_of, absent, directory))

    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=PAYLOAD_DIRECTORY.replace("\\", "/"),
        accepted_extensions=(".json",),
        policies={"close_source": CLOSE_SOURCE_POLICY,
                  "substitution": SUBSTITUTION_POLICY})


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: build_valuation_leaf.py <run_dir> <run_id> <as_of>")
        return 2
    record = write_leaf(argv[1], build(argv[2], argv[3]))
    for k, v in record.items():
        print("%-15s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
