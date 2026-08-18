"""F0-R7 · the one canonical serialization + hash primitive for Frozen B0.

Before this module there were two. `b0_route._hash` normalised through
`_stable()` and then serialised; `b0_provenance._h` serialised directly with
`default=str`. On the frozen registry they agreed, and F-0 measured that they
agreed — but agreement measured on one payload is not equivalence, and the two
functions differ on inputs neither had met yet:

    {("a", "b"): 1}      _stable stringifies the tuple key; json.dumps raises
    {1: "x"}             json coerces the int key to "1" either way, but only
                         _stable makes that coercion visible in the payload
    {frozenset()}        default=str renders a repr that depends on iteration
                         order; _stable never reaches it because sets are not
                         part of any canonical payload

Two provenance records for one run, differing because one path took the route's
hash and the other took the manifest's, is exactly the class of defect a
provenance system exists to make impossible. So there is one primitive, both
call it, and a test asserts there is no second implementation.

The encoding is the ruling, not an implementation detail:

    None            -> JSON null, never the string "None"
    bool            -> JSON true/false, never 0/1
    int / float     -> JSON number, no rounding, no normalisation
    str             -> JSON string, ensure_ascii=False (Chinese stays Chinese)
    tuple           -> JSON array (so tuple/list cannot hash differently)
    dict            -> object with str keys, sorted; sorted AGAIN by json
    anything else   -> str(), which is lossy on purpose: an object that wants
                       to be hashed has to say how, rather than smuggling its
                       repr into a provenance record

Separators carry no whitespace, so reformatting cannot change a hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CANONICAL_HASH_VERSION = "b0_canonical_hash@1"

# The JSON settings ARE the contract. They are named so a diff shows a change to
# them, rather than the change hiding inside a call.
JSON_SORT_KEYS = True
JSON_ENSURE_ASCII = False
JSON_SEPARATORS = (",", ":")


def canonicalise(value: Any) -> Any:
    """Normalise to the JSON subset B0 hashes over."""
    if isinstance(value, tuple):
        return [canonicalise(v) for v in value]
    if isinstance(value, list):
        return [canonicalise(v) for v in value]
    if isinstance(value, dict):
        return {str(k): canonicalise(v) for k, v in sorted(
            value.items(), key=lambda kv: str(kv[0]))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(payload: Any) -> str:
    return json.dumps(canonicalise(payload), sort_keys=JSON_SORT_KEYS,
                      ensure_ascii=JSON_ENSURE_ASCII, separators=JSON_SEPARATORS)


def canonical_sha256(payload: Any) -> str:
    """The single hash function. Route and provenance both end up here."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    """Raw-byte identity of a file (F0-R2 / F0-R3).

    Deliberately NOT routed through `canonical_sha256`: a document's identity is
    its bytes, and normalising them would let a whitespace-only edit to the
    frozen master preregistration keep the same hash.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
