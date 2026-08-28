# -*- coding: utf-8 -*-
"""Canonical intermediate: quarterly financials WITH the real announcement date.

Why this exists. §2.2 freezes the availability rule for quarterly fundamentals:

    財報：`financial_statements` 2005-12 起 100% 真實公告日
    任何以固定 lag 代替真實公告日的做法，在 B0 一律禁止。

The raw export carries that date (`財報發布日`), and the frozen importer spec in
`tej_importer.DATASETS["financial_statements"]` already maps it to `release_date`.
The per-security cache under `~/tej_cache/financial_statements` does NOT carry it —
it was written by an older path. Materializing PIT quarterly inputs from that cache
would therefore have required inventing an availability rule, which §2.2 forbids.

So this reads the RAW export and applies the FROZEN importer spec. It introduces no
mapping, no unit convention and no filtering of its own: every rename, every
thousand-scaling and both accepted period formats come from `DATASETS`.

Measured on the sealed export (not assumed):
  * 138,731 rows, and 138,731 distinct (stock_id, 年月) keys — every security-period
    appears exactly ONCE, so no consolidated-vs-individual choice is ever made here.
    124,682 rows are 合併=Y and 14,049 are 合併=N, but never both for one key.
  * `drop_duplicates` is consequently a guard, not a selector. It is kept, and it
    raises rather than silently dropping if that measured fact ever stops holding.

READ-ONLY with respect to strategy. No feature, score, ranking or portfolio quantity
is computed here.

    python research/b0_materializer/build_financials_pit.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

import tej_importer as ti                                    # noqa: E402
from core.b0_master_prereg import spec as frozen_spec         # noqa: E402

SPEC = ti.DATASETS["financial_statements"]
# The last decision date L2 can ever stand on. Read from the frozen registry.
WINDOW_END = str(frozen_spec("window_end"))
SOURCE_DIR = str(SPEC["source_dir"])
OUT_PARQUET = os.path.join(REPO, "data", "b0", "financials_pit.parquet")
OUT_RECEIPT = os.path.join(HERE, "financials_pit_receipt.json")

# The identity columns the frozen spec does not rename but this panel needs.
PERIOD_COL = SPEC["date_col"]                                 # 年月
ID_COL = "證券代碼"
CONSOLIDATION_COL = "合併(Y/N)"


# --- O-H · the source directory is enumerated before it is read ---------------
#
# `load_raw` globs `*.xlsx`. A glob does not report what it did NOT match, so a
# data file the importer cannot read is indistinguishable from a directory that
# does not contain one: the build succeeds, the receipt looks complete, and the
# rows are simply absent.
#
# This is not hypothetical. On 2026-08-26 the export directory gained
# `2026 0826 2385家.csv` (UTF-16, 1,879 rows of period 202606) and lost the
# workbook `202606 財報583家 8-10.xlsx` that the previous receipt names. The
# glob absorbed both events without a word. It happened to be harmless — every
# in-window row was already carried by the surviving workbook — but harmlessness
# was established by hand afterwards, which is exactly the property a builder is
# supposed to establish for itself.
#
# Same class as D6.5's Big5 bodies and D6.4's empty `receiver=`: the source
# answered, and the client did not hear it. So the rule is stated as presence,
# not as absence — the directory must contain ONLY entries this builder accepts,
# and anything else stops the build rather than being skipped.
#
# A SUBDIRECTORY is rejected for the same reason a `.csv` is, not as tidiness.
# The export surface is expected to be flat; an unexpected subtree is precisely
# where an exporter would deposit a new data file, and a non-recursive glob would
# never mention it. "There is a subtree here and nobody has said what is in it"
# is an unknown, and the builder does not proceed on unknowns.

ACCEPTED_SOURCE_EXTENSIONS: tuple[str, ...] = (".xlsx", ".csv")

# --- A3 · the frozen source contract ------------------------------------------
#
# Two formats, and a declared owner for every period.
#
# The two exports OVERLAP and DISAGREE. Measured 2026-08-26 on period 202606:
# the workbook carries 318 securities, the csv carries 1,879 (a strict superset —
# `only-xlsx` is 0), and on the 318 they share, 16 of 57 columns differ. Some of
# that is formatting (利息費用: 31 string diffs, 0 numeric), but some is real
# restatement — 加權平均股數 differs on 201 rows by up to 106,846 shares, and
# 每股盈餘 on 15 rows by up to 0.16. The later export simply carries more
# finalised numbers.
#
# So "abort on any key collision" would abort every build, and "last writer wins"
# would silently pick a winner for a canonical input. The contract instead makes
# ownership DECLARED:
#
#   owns    the periods this file is the canonical source for
#   yields  periods this file CONTAINS but does not own — dropped, by declaration
#
# Nothing is dropped silently: a period present in a file but in neither list
# aborts, and the yielded row counts go into the receipt. A declared file that is
# not present also aborts — which is exactly the event that went unnoticed on
# 2026-08-26, when `202606 財報583家 8-10.xlsx` disappeared and only the previous
# receipt remembered it.

SOURCE_OWNERSHIP: dict = {
    "20260806090633.xlsx": {
        "owns": "<= 202603",
        # Contains 318 rows of 202606. The csv is a strict superset for that
        # period and carries the later restatement, so this file yields it.
        "yields": ("202606",),
    },
    "2026 0826 2385家.csv": {
        "owns": ("202606",),
        "yields": (),
    },
}

# The csv is a csv only by extension. Measured: BOM ff fe, zero commas, 26 tabs
# in the header line. Reading it with the default separator silently produces a
# one-column frame, so both are pinned rather than sniffed.
CSV_ENCODING = "utf-16"
CSV_DELIMITER = "\t"


class SourceContractError(SystemExit):
    """Fail-loud: the source set does not conform to the frozen contract."""


def _norm_period(value) -> str:
    """`年月` -> canonical 'YYYYMM'. Both frozen formats, nothing else."""
    s = str(value).strip().replace("/", "")
    if len(s) != 6 or not s.isdigit():
        raise SourceContractError(
            "abort: period value %r is not one of the frozen formats %s"
            % (value, SPEC["date_format"]))
    return s


def _owns_predicate(spec_value):
    """`('202606',)` or `'<= 202603'` -> a predicate over canonical periods."""
    if isinstance(spec_value, (tuple, list)):
        owned = {_norm_period(p) for p in spec_value}
        return (lambda p: p in owned), sorted(owned)
    if isinstance(spec_value, str) and spec_value.startswith("<="):
        bound = _norm_period(spec_value[2:])
        return (lambda p: p <= bound), ["<= %s" % bound]
    raise SourceContractError(
        "abort: ownership declaration %r is not a supported form. Use a tuple of "
        "periods or '<= YYYYMM'. An unparsed declaration is an undeclared one."
        % (spec_value,))


def _entry_kind(path: str) -> str:
    """A short label for a directory entry that is NOT an accepted workbook.

    `islink` is tested FIRST because `isfile`/`isdir` follow the link and would
    report the target's type, hiding the indirection — and a symlink is exactly
    the case where what the builder reads and what the receipt names can come
    apart later without either changing.
    """
    if os.path.islink(path):
        # `exists` FOLLOWS the link, so it is the dangling test. `isdir` cannot
        # serve here: on a broken link it returns False without raising, which
        # would report a dangling link as "-> file" — a target that is not there
        # described as one that is.
        if not os.path.exists(path):
            target = "unresolved"
        elif os.path.isdir(path):
            target = "directory"
        else:
            target = "file"
        return "<symlink -> %s>" % target
    if os.path.isdir(path):
        return "<directory>"
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1]
        return repr(ext) if ext else "<no extension>"
    return "<other entry type>"                          # fifo, socket, device


def assert_source_dir_holds_only_accepted_files(source_dir: str) -> list:
    """Fail loud on anything in `source_dir` the importer would not read.

    Accepts only regular files with an accepted extension. Every other entry —
    other extensions, subdirectories, symlinks, and anything else — is rejected
    and named.

    Returns the accepted paths, sorted. The caller reads exactly this list rather
    than enumerating again, so one enumeration produces one answer. That is NOT a
    guarantee about the directory itself: there is no snapshot or lock here, so a
    process that adds a `.csv` or rewrites a workbook AFTER this returns is still
    a TOCTOU window this guard does not close.
    """
    if not os.path.isdir(source_dir):
        raise SystemExit(f"abort: source directory does not exist: {source_dir}")

    accepted, rejected = [], []
    for name in sorted(os.listdir(source_dir)):
        path = os.path.join(source_dir, name)
        if (os.path.isfile(path) and not os.path.islink(path)
                and os.path.splitext(name)[1].lower()
                in ACCEPTED_SOURCE_EXTENSIONS):
            accepted.append(path)
        else:
            rejected.append((name, _entry_kind(path)))

    if rejected:
        listed = "\n".join("    %s   (%s)" % (n, k) for n, k in rejected)
        raise SystemExit(
            "abort: %d entr(y/ies) in the financials source directory are not "
            "something this builder accepts, and a glob would have skipped them "
            "SILENTLY:\n%s\n"
            "  directory:          %s\n"
            "  accepted:           regular file with extension %s\n"
            "A source the importer cannot read is not the same fact as no "
            "source, and a subtree nobody has described is not the same fact as "
            "an empty one. Convert it to an accepted format, move it out of the "
            "source directory, or extend the frozen importer spec deliberately — "
            "but the build does not proceed while the answer is unknown."
            % (len(rejected), listed, source_dir,
               ", ".join(ACCEPTED_SOURCE_EXTENSIONS)))
    return accepted


def assert_every_file_is_declared(files, ownership=None) -> None:
    """Structural half of the contract — checked before a byte is parsed.

    Three of the four abort conditions live here; the fourth needs the files'
    actual periods and is in `assert_periods_conform`.
    """
    ownership = SOURCE_OWNERSHIP if ownership is None else ownership
    present = {os.path.basename(f) for f in files}
    declared = set(ownership)

    undeclared = sorted(present - declared)
    if undeclared:
        raise SourceContractError(
            "abort: %d source file(s) are present but not declared in "
            "SOURCE_OWNERSHIP:\n%s\n"
            "A file nobody has assigned periods to is a file whose contribution "
            "to the panel is undefined. Declare what it owns (and what it "
            "yields), or take it out of the source directory."
            % (len(undeclared), "\n".join("    %s" % n for n in undeclared)))

    missing = sorted(declared - present)
    if missing:
        raise SourceContractError(
            "abort: %d declared source file(s) are NOT PRESENT:\n%s\n"
            "  directory: %s\n"
            "This is the 2026-08-26 event: a declared source vanished from the "
            "export directory and only the previous receipt remembered it. A "
            "source that disappears must be noticed, not absorbed."
            % (len(missing), "\n".join("    %s" % n for n in missing),
               os.path.dirname(files[0]) if files else "<none>"))

    # No period may be owned twice. Compared pairwise on the explicit members;
    # a bound form is expanded against the other file's explicit periods, which
    # is enough because two bound forms would both have to be `<=` and the
    # narrower is then wholly inside the wider.
    owns = {n: _owns_predicate(d["owns"]) for n, d in ownership.items()}
    names = sorted(ownership)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, _ = owns[a]
            pb, _ = owns[b]
            probes = set()
            for d in (ownership[a], ownership[b]):
                for key in ("owns", "yields"):
                    v = d.get(key, ())
                    if isinstance(v, (tuple, list)):
                        probes |= {_norm_period(p) for p in v}
                    elif isinstance(v, str) and v.startswith("<="):
                        probes.add(_norm_period(v[2:]))
            clash = sorted(p for p in probes if pa(p) and pb(p))
            if clash:
                raise SourceContractError(
                    "abort: period(s) %s are declared as OWNED by both %s and "
                    "%s. Exactly one file may be canonical for a period; two "
                    "owners is the conflict this contract exists to refuse."
                    % (", ".join(clash), a, b))


def assert_periods_conform(name: str, periods, ownership=None) -> tuple:
    """Content half: every period in the file is owned or explicitly yielded.

    Returns (owned, yielded) as sorted tuples.
    """
    ownership = SOURCE_OWNERSHIP if ownership is None else ownership
    decl = ownership[name]
    owns, _ = _owns_predicate(decl["owns"])
    yields = {_norm_period(p) for p in decl.get("yields", ())}

    seen = sorted({_norm_period(p) for p in periods})
    owned = [p for p in seen if owns(p)]
    yielded = [p for p in seen if p in yields and not owns(p)]
    stray = [p for p in seen if not owns(p) and p not in yields]
    if stray:
        raise SourceContractError(
            "abort: %s contains period(s) %s that it neither OWNS nor YIELDS.\n"
            "  owns:   %s\n"
            "  yields: %s\n"
            "Dropping them would be the silent skip this contract replaces; "
            "keeping them would make two files canonical for one period. Declare "
            "which it is."
            % (name, ", ".join(stray), decl["owns"],
               decl.get("yields", ()) or "()"))
    return tuple(owned), tuple(yielded)


def _read_source(path: str) -> pd.DataFrame:
    """Dispatch on extension. Both readers, no sniffing."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")
    if ext == ".csv":
        return pd.read_csv(path, encoding=CSV_ENCODING, sep=CSV_DELIMITER)
    raise SourceContractError(
        "abort: no reader for %r. `ACCEPTED_SOURCE_EXTENSIONS` and this dispatch "
        "must be extended together, or the guard admits a file nothing can read."
        % ext)


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_period(series: pd.Series) -> pd.Series:
    """Both formats the frozen spec accepts, and nothing else."""
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    raw = series.astype(str).str.strip()
    for fmt in SPEC["date_format"]:
        need = out.isna()
        if not need.any():
            break
        out.loc[need] = pd.to_datetime(raw[need], format=fmt, errors="coerce")
    if out.isna().any():
        bad = sorted(raw[out.isna()].unique())[:5]
        raise SystemExit(
            f"abort: {int(out.isna().sum())} period values match neither frozen "
            f"format {SPEC['date_format']}: {bad}. A third format is a source "
            f"change, not something this builder may absorb.")
    return out


def load_raw() -> pd.DataFrame:
    # O-H: enumerate before reading, and read exactly what the enumeration
    # returned rather than globbing a second time. (This narrows the gap to a
    # single listing; it does not close the TOCTOU window — see the guard's
    # docstring.)
    files = assert_source_dir_holds_only_accepted_files(SOURCE_DIR)
    if not files:
        raise SystemExit(f"abort: no source workbook under {SOURCE_DIR}")
    assert_every_file_is_declared(files)

    frames, sources = [], []
    owned_by = {}
    for f in files:
        name = os.path.basename(f)
        df = _read_source(f)
        # The sources differ in header layout (merged vs split id column,
        # 年月 vs 年/月). Both normalisations are the frozen importer's own, so
        # this builder inherits them rather than inventing a second convention.
        df = ti._normalize_source_column_aliases(df, name)
        df = ti._split_id_name(df)
        missing = [c for c in SPEC["required_cols"]
                   if c != ID_COL and c not in df.columns]
        if missing:
            raise SystemExit(
                f"abort: {name} is missing frozen required column(s) "
                f"{missing}. A source that cannot supply them cannot be imported "
                f"under the frozen spec.")

        # A3: keep only the periods this file OWNS. The yielded rows are counted
        # into the receipt rather than vanishing.
        periods = df[PERIOD_COL].map(_norm_period)
        owned, yielded = assert_periods_conform(name, periods.unique())
        keep = periods.isin(set(owned))
        n_yielded = int((~keep).sum())
        df = df[keep].copy()

        for p in owned:
            if p in owned_by and owned_by[p] != name:
                raise SourceContractError(
                    "abort: period %s was contributed by both %s and %s. The "
                    "declaration check should have caught this; that it did not "
                    "means the declaration and the data disagree."
                    % (p, owned_by[p], name))
            owned_by[p] = name

        frames.append(df)
        sources.append({
            "file": os.path.relpath(f, REPO),
            "sha256": _file_sha(f),
            "rows": int(len(df)),
            "rows_yielded_to_another_source": n_yielded,
            "periods_owned": list(owned),
            "periods_yielded": list(yielded),
            "declared_owns": str(SOURCE_OWNERSHIP[name]["owns"]),
        })

    raw = pd.concat(frames, ignore_index=True)

    # Every period that reached the panel is owned by exactly one file — asserted
    # against the DATA, not re-read from the declaration that produced it.
    dupes = raw.groupby([raw[PERIOD_COL].map(_norm_period),
                         raw["stock_id"].astype(str).str.strip()]).size()
    collided = dupes[dupes > 1]
    if len(collided):
        raise SourceContractError(
            "abort: %d (period, security) key(s) appear more than once after "
            "ownership filtering, e.g. %s. Ownership did not partition the "
            "sources." % (len(collided), list(collided.index[:5])))
    return raw, sources


def build() -> tuple[pd.DataFrame, dict]:
    raw, sources = load_raw()
    n_raw = len(raw)

    df = raw.rename(columns=SPEC["rename"]).copy()
    df["stock_id"] = raw["stock_id"].astype(str).str.strip()
    df["date"] = _parse_period(raw[PERIOD_COL])
    df["release_date"] = pd.to_datetime(
        raw["財報發布日"], format=SPEC["extra_date_cols"]["release_date"],
        errors="coerce")

    # §2.2: a row whose announcement date cannot be read has no availability, and
    # a fixed-lag substitute is forbidden. Such rows are dropped from the PIT panel
    # and counted, never back-filled.
    no_release = int(df["release_date"].isna().sum())
    df = df[df["release_date"].notna()].copy()

    # A statement announced after the last decision date is unusable by the frozen
    # availability rule (release_date <= decision_date) at EVERY decision date in
    # the window, so it is dropped rather than carried. This is the frozen window
    # plus the frozen rule, not a new one — and it is what removes the only source
    # overlap in the export: the 2026-08 re-export of period 2026-06, which no L2
    # decision could ever have seen.
    unusable = int((df["release_date"] > pd.Timestamp(WINDOW_END)).sum())
    df = df[df["release_date"] <= pd.Timestamp(WINDOW_END)].copy()

    for src, dst in SPEC["thousand_cols"].items():
        df[dst] = pd.to_numeric(df[src], errors="coerce") * 1000.0
    for c in SPEC["numeric_cols"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["consolidated"] = raw.loc[df.index, CONSOLIDATION_COL].astype(str).str.strip()

    keep = (["stock_id", "date", "release_date", "quarter", "consolidated", "eps"]
            + sorted(SPEC["thousand_cols"].values()))
    df = df[keep].sort_values(["stock_id", "date"]).reset_index(drop=True)

    # The measured invariant, enforced rather than trusted.
    dupes = int(df.duplicated(subset=["stock_id", "date"]).sum())
    if dupes:
        raise SystemExit(
            f"abort: {dupes} duplicate (stock_id, period) rows INSIDE the usable "
            f"window. Which of two competing statements for one security-period wins "
            f"is NOT specified by the master preregistration, and must not be decided "
            f"here (M-3). Register it and stop.")

    receipt = {
        "artefact": "data/b0/financials_pit.parquet",
        "builder": "research/b0_materializer/build_financials_pit.py",
        "importer_spec": "tej_importer.DATASETS['financial_statements'] (frozen)",
        "availability_rule": "real 財報發布日 -> release_date; fixed-lag proxies forbidden (§2.2)",
        "sources": sources,
        # A3: the contract this source set was admitted under, recorded beside
        # the set itself so a later reader can check the two against each other
        # rather than trusting that they matched at build time.
        "source_contract": {
            "accepted_extensions": list(ACCEPTED_SOURCE_EXTENSIONS),
            "csv_encoding": CSV_ENCODING,
            "csv_delimiter": "TAB",
            "ownership": {k: {"owns": str(v["owns"]),
                              "yields": list(v.get("yields", ()))}
                          for k, v in sorted(SOURCE_OWNERSHIP.items())},
            "rows_yielded_total": sum(
                s["rows_yielded_to_another_source"] for s in sources),
            "conflict_rule": (
                "declared period ownership; overlapping ownership, an "
                "undeclared file, a declared file that is absent, or a period "
                "neither owned nor yielded all abort"),
        },
        "rows_raw": int(n_raw),
        "rows_kept": int(len(df)),
        "rows_dropped_no_release_date": no_release,
        "rows_dropped_released_after_window_end": unusable,
        "window_end": WINDOW_END,
        "securities": int(df["stock_id"].nunique()),
        "period_min": str(df["date"].min().date()),
        "period_max": str(df["date"].max().date()),
        "release_min": str(df["release_date"].min().date()),
        "release_max": str(df["release_date"].max().date()),
        "consolidation_basis_counts": {
            str(k): int(v) for k, v in df["consolidated"].value_counts().items()},
        "columns": list(df.columns),
        "schema_sha256": _sha_bytes("|".join(df.columns).encode("utf-8")),
        "performance_computed": False,
    }
    return df, receipt


def main() -> None:
    df, receipt = build()
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    receipt["content_sha256"] = _file_sha(OUT_PARQUET)
    receipt["bytes"] = os.path.getsize(OUT_PARQUET)
    with open(OUT_RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    for k in ("rows_raw", "rows_kept", "rows_dropped_no_release_date", "securities",
              "period_min", "period_max", "release_min", "release_max",
              "consolidation_basis_counts", "content_sha256"):
        print(f"  {k:32} {receipt[k]}")
    print(f"wrote {os.path.relpath(OUT_PARQUET, REPO)}")


if __name__ == "__main__":
    main()
