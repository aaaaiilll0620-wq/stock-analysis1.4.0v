# -*- coding: utf-8 -*-
"""W4 · the bonus-shares leaf: harvested payload keys, not filenames.

Ruled as a harvested-payload locator like valuation, not a flat directory. The
corpus is 1,383 envelopes in three canonical key forms, produced by
`b0_stock_dividend_multiplier_audit/harvest_official_bonus_rate.py`:

    twse_range_<startYYYYMMDD>_<endYYYYMMDD>      52
    tpex_range_<startYYYYMMDD>_<endYYYYMMDD>      52
    twse_detail_<stock_id>_<exRightDateYYYYMMDD>  1,279

Why this family matters: C-51 makes the exchange's own 每千股無償配股 the ONLY
admissible source for the holder multiplier `m = 1 + 每千股無償配股/1000`, and
that multiplier drives the share-unit-adjusted price series momentum reads.
Omitting it does not raise — it silently changes momentum.

THE KEY IS NOT THE TRUTH
------------------------
A filename is a claim, and a claim that names itself cannot be checked. So each
entry carries the STRUCTURED request — exchange, endpoint, parameters — and the
validator RECOMPUTES the key from it, then requires

    recomputed key == envelope["key"] == filename stem

Three independent statements of the same fact; any disagreement aborts. A
renamed file, a hand-edited envelope, or a key that no longer follows from its
own parameters are all caught by the same check.

⚠ `observed_at` IS NOT `retrieved_at`. These envelopes carry `key`, `url`,
`sha256`, `bytes` and `payload` — and no retrieval timestamp. File mtime is not
one either: it records when the bytes last touched this filesystem, which a copy
or a restore changes. So `observed_at` is defined as WHEN W6a READ AND HASHED
THE ENVELOPE, and a real `retrieved_at` has to come from a future harvester that
records it at fetch time.

    python research/b0_materializer/build_bonus_shares_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError, build_leaf, write_leaf,
)

DATASET = "bonus_shares"
PAYLOAD_DIRECTORY = os.path.join("artifacts", "stock_dividend_multiplier_audit",
                                 "raw")

OBSERVED_AT_SEMANTICS = {
    "rule": "OBSERVED_AT_IS_WHEN_W6A_READ_AND_HASHED_THE_ENVELOPE",
    "detail": (
        "these envelopes carry no retrieval timestamp, and file mtime is not a "
        "substitute — it changes on copy or restore. A real `retrieved_at` must "
        "be recorded by the harvester at fetch time; until then this field says "
        "only when the bytes were read here."),
    "retrieved_at_available": False,
}

MULTIPLIER_POLICY = {
    "rule": "C51_OFFICIAL_BONUS_RATE_IS_THE_ONLY_ADMISSIBLE_MULTIPLIER_SOURCE",
    "detail": (
        "m = 1 + 每千股無償配股/1000 drives the share-unit-adjusted price "
        "series that momentum reads. Omitting this family does not raise; it "
        "silently changes momentum."),
}

# The three canonical key forms, as the producer generates them.
KEY_PATTERNS = {
    "twse_range": re.compile(r"^twse_range_(\d{8})_(\d{8})$"),
    "tpex_range": re.compile(r"^tpex_range_(\d{8})_(\d{8})$"),
    "twse_detail": re.compile(r"^twse_detail_([0-9A-Za-z]+)_(\d{8})$"),
}


def parse_key(key: str) -> dict:
    """key -> structured request. The inverse of how the harvester built it."""
    for layer, pattern in KEY_PATTERNS.items():
        m = pattern.match(key)
        if not m:
            continue
        if layer.endswith("_range"):
            return {"layer": layer,
                    "exchange": "TWSE" if layer.startswith("twse") else "TPEx",
                    "params": {"start_date": m.group(1), "end_date": m.group(2)}}
        return {"layer": layer, "exchange": "TWSE",
                "params": {"stock_id": m.group(1),
                           "scheduled_ex_right_date": m.group(2)}}
    raise ManifestError(
        "abort: %r is not one of the frozen bonus payload key forms %s. A key "
        "nobody defined addresses nothing." % (key, sorted(KEY_PATTERNS)))


def recompute_key(request: dict) -> str:
    """structured request -> key. Must reproduce what the envelope claims."""
    layer, p = request["layer"], request["params"]
    if layer.endswith("_range"):
        return "%s_%s_%s" % (layer, p["start_date"], p["end_date"])
    return "twse_detail_%s_%s" % (p["stock_id"], p["scheduled_ex_right_date"])


def read_envelope(path: str) -> dict:
    """Open one envelope and check the key three ways."""
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, encoding="utf-8") as fh:
            env = json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError("abort: %s is not readable JSON: %s" % (path, exc))

    for field in ("key", "url", "sha256", "bytes"):
        if field not in env:
            raise ManifestError(
                "abort: envelope %s has no %r. An envelope that cannot identify "
                "its own request is not provenance." % (stem, field))

    request = parse_key(env["key"])
    recomputed = recompute_key(request)
    if not (recomputed == env["key"] == stem):
        raise ManifestError(
            "abort: envelope key disagrees with itself.\n"
            "  filename stem: %s\n  envelope key:  %s\n  recomputed:    %s\n"
            "The key is not the truth — it must follow from the structured "
            "request, and all three must agree." % (stem, env["key"], recomputed))
    return {"envelope": env, "request": request}


def build(run_id: str, as_of: str, payload_dir: str = "") -> dict:
    directory = payload_dir or os.path.join(REPO, PAYLOAD_DIRECTORY)
    if not os.path.isdir(directory):
        raise ManifestError("abort: bonus payload store not found: %s"
                            % directory)
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    # Closed world: every entry named, no glob standing in for a contract.
    names, unknown = [], []
    for name in sorted(os.listdir(directory)):
        p = os.path.join(directory, name)
        if (os.path.isfile(p) and not os.path.islink(p)
                and name.lower().endswith(".json")):
            names.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise ManifestError(
            "abort: %d entr(y/ies) in the bonus payload store are not envelopes:"
            "\n%s\n  store: %s"
            % (len(unknown), "\n".join("    %s" % n for n in unknown[:20]),
               directory))
    if not names:
        raise ManifestError("abort: bonus payload store %s is empty" % directory)

    entries, counts = [], {k: 0 for k in KEY_PATTERNS}
    for name in names:
        p = os.path.join(directory, name)
        got = read_envelope(p)
        env, request = got["envelope"], got["request"]
        counts[request["layer"]] += 1
        entries.append({
            "locator": name,
            "format": "json:harvested_envelope",
            "raw_sha256": file_sha256(p),
            "export_vintage": as_of,
            "observed_at": observed_at,
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed",
            # The payload key, and the structured request it must follow from.
            "payload_key": env["key"],
            "layer": request["layer"],
            "exchange": request["exchange"],
            "request_params": request["params"],
            "url": env["url"],
            "payload_sha256": env["sha256"],
            "payload_bytes": env["bytes"],
            "parser_contract_version": "b0_bonus_share_source@1",
        })

    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=PAYLOAD_DIRECTORY.replace("\\", "/"),
        accepted_extensions=(".json",),
        policies={"observed_at_semantics": OBSERVED_AT_SEMANTICS,
                  "multiplier": MULTIPLIER_POLICY,
                  "corpus_census": {"rule": "ENVELOPE_COUNTS_BY_LAYER",
                                    "counts": counts,
                                    "total": len(entries)}})


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: build_bonus_shares_leaf.py <run_dir> <run_id> <as_of>")
        return 2
    rec = write_leaf(argv[1], build(argv[2], argv[3]))
    for k, v in rec.items():
        print("%-15s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
