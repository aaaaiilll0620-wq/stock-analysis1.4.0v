# -*- coding: utf-8 -*-
"""W6b-2 · the L3 readers, and the parity that establishes they are right.

A second implementation of a parsing rule does not fail by crashing. It returns
a slightly different number and every guard downstream accepts it. Several of
those numbers are one keystroke away here:

    UTF-16 + TAB       the wrong pair yields ONE column, silently
    成交量(千股) x1000  the frozen adv20 unit (C-25) against an absolute NTD
                       floor (§4.2) — forget it and every security is illiquid
    m = 1 + b/1000     C-51's holder multiplier silently rescales the price
                       series momentum reads
    a dropped 恢復交易日 row leaves a suspension explaining gaps forever

So the fast tests below drive those directly on synthetic archives, and the full
parity run against the sealed panels is available under an env flag.

FULL PARITY, run 2026-08-27 (opt in with B0_L3_PARITY=1):

    prices             3,288,691 rows  2019-01-01..2026-04-01  all equal
    valuation          3,902 values    as_of 2026-03-30        all equal
    calendar           L2's 5,565 sessions are an exact PREFIX; L3 extends by 7
    security_status    1,375 records / 566 securities           exact
    corporate_actions  46,433 events (158 holder-side exits, 1,242
                       NOT_RECONSTRUCTIBLE)                     exact BYTES
    bonus_shares       3,215 events / 996 securities, 2,399 matched
    financials         136,372 rows / 2,315 securities, 15 columns
    revenue            301,801 rows / 2,168 securities
    industry           4,782 rows / 2,436 securities, 92 UNRESOLVED

The heavy ones are opt-in because they read hundreds of MB, not because they
are optional.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(REPO, "research", "b0_materializer"),
           os.path.join(REPO, "research", "b0_l3")):
    sys.path.insert(0, _p)

from core.b0_l3_lineage_capture import (                          # noqa: E402
    PURPOSE_DIAGNOSTIC,
)
import build_bonus_shares_leaf as B                              # noqa: E402
import build_corporate_actions_leaf as CA                        # noqa: E402
import build_financials_leaf as FIN                              # noqa: E402
import build_flat_leaves as F                                    # noqa: E402
import build_prices_leaf as P                                    # noqa: E402
import build_valuation_leaf as V                                 # noqa: E402
import l3_readers as R                                           # noqa: E402
import verify_reader_parity as VP                                # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    assemble_aggregate, write_aggregate, write_leaf,
)

RUN, AS_OF = "L3-0000000000000001", "2026-03-30"
sources = pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO, P.LANDING_DIRECTORY)),
    reason="TEJ exports not present")
heavy = pytest.mark.skipif(
    os.environ.get("B0_L3_PARITY") != "1",
    reason="set B0_L3_PARITY=1 (reads hundreds of MB of archives)")


@pytest.fixture(scope="session")
def run_dir(tmp_path_factory):
    """One declared source set for the whole module.

    Session-scoped because assembling it hashes every declared file, and doing
    that per test would make the honest checks the slow ones.
    """
    d = str(tmp_path_factory.mktemp("l3run"))
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(d, F.build(ds, RUN, AS_OF))
    for mod in (FIN, P, B, V):
        write_leaf(d, mod.build(RUN, AS_OF))
    write_leaf(d, CA.build(RUN, AS_OF, run_dir=d))
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))
    return d


# --- the silent failure modes ---------------------------------------------------

def _price_archive(tmp_path, rows, encoding="utf-16", sep="\t"):
    header = sep.join(R.PRICE_COLUMNS)
    body = "\n".join(sep.join(r) for r in rows)
    csv_bytes = (header + "\n" + body + "\n").encode(encoding)
    p = os.path.join(str(tmp_path), "prices.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("member.csv", csv_bytes)
    return p


def test_the_volume_unit_is_restored_to_shares(tmp_path):
    """TEJ publishes 成交量(千股). C-25 pins adv20 to close x Trading_Volume and
    §4.2 applies an ABSOLUTE NTD floor, so dropping the x1000 does not raise —
    it makes every security illiquid."""
    import pandas as pd

    path = _price_archive(tmp_path,
                          [["1101 台泥", "2026-03-30", "37.0", "37.5", "1234"]])
    with zipfile.ZipFile(path) as z:
        txt = z.read("member.csv").decode("utf-16")
    d = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str)
    shares = pd.to_numeric(d["成交量(千股)"]) * R.VOLUME_THOUSANDS_TO_SHARES

    assert R.VOLUME_THOUSANDS_TO_SHARES == 1000.0
    assert float(shares.iloc[0]) == 1_234_000.0


def test_the_wrong_dialect_collapses_the_frame_without_raising(tmp_path):
    """Why encoding and separator are pinned rather than sniffed."""
    import pandas as pd

    path = _price_archive(tmp_path,
                          [["1101 台泥", "2026-03-30", "37.0", "37.5", "1"]])
    with zipfile.ZipFile(path) as z:
        txt = z.read("member.csv").decode("utf-16")

    wrong = pd.read_csv(io.StringIO(txt), sep=",", dtype=str)
    assert len(wrong.columns) == 1                    # silently one column
    right = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str)
    assert len(right.columns) == len(R.PRICE_COLUMNS)


def test_the_stock_id_is_split_off_the_name():
    assert R._sid("1101 台泥") == "1101"


def test_the_three_number_rules_are_three_rules():
    """Collapsing them would be the quiet kind of wrong.

    A valuation ratio of 0.0 is an ABSENCE (`valuation_sentinel_zero_is_
    undefined`); a share quantity of 0 is a real zero; an exchange figure may
    arrive with a unit suffix glued to it.
    """
    assert R._num("0") is None and R._num("0.0") is None
    assert R._num("1.23") == 1.23 and R._num("-") is None

    assert R._ca_num("0") == 0.0                      # a real zero, kept
    assert R._ca_num(".") is None and R._ca_num("") is None

    assert R._bonus_num("1,234") == 1234.0
    assert R._bonus_num("50 元/股") == 50.0
    assert R._bonus_num("--") is None


def test_a_zip_with_the_wrong_schema_aborts(tmp_path):
    """A schema change is a source change, not something a reader absorbs."""
    p = os.path.join(str(tmp_path), "bad.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("m.csv", "證券代碼\t年月日\n1101 台泥\t20260330\n".encode("utf-16"))
    with pytest.raises(R.ReaderError, match="schema"):
        R._zip_tsv_rows(p, R.SUSPENSION_COLUMNS)


# --- transcription, not import --------------------------------------------------

def test_the_readers_import_no_l2_builder_and_no_tej_importer():
    """The line the module docstring draws, pinned.

    `core.*` is normative and inside the A2 route closure, so importing the
    reason->status mapping or the multiplier rule from it is importing ONE
    definition. `tej_importer` and `research/b0_materializer/build_*.py` are
    neither: importing them would drag unsealed, actively-edited code into the
    route AND make parity a tautology — a reader that calls L2's parser cannot
    be checked against L2's output.
    """
    import ast

    path = os.path.join(REPO, "research", "b0_l3", "l3_readers.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}

    assert "tej_importer" not in imported
    assert not [m for m in imported if m.startswith("build_")
                and m != "build_leaf"], sorted(imported)
    # and it DOES take its semantics from the normative modules
    assert {"core.b0_market_state", "core.b0_corporate_actions",
            "core.b0_bonus_share_source"} <= imported


def test_the_readers_never_write_to_the_sealed_data_directory():
    import ast

    for name in ("l3_readers.py", "verify_reader_parity.py"):
        path = os.path.join(REPO, "research", "b0_l3", name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                dotted = getattr(fn, "attr", "") or getattr(fn, "id", "")
                assert dotted not in ("to_parquet", "to_csv"), name


@sources
def test_every_family_has_a_reader_and_none_is_undeclared():
    """'Not implemented' must remain a DECLARED state, not something discovered
    at run time — which is why the mapping survives being empty."""
    from source_ownership_manifest import REQUIRED_DATASETS

    covered = set(R.READERS) | set(R.READERS_NOT_IMPLEMENTED)
    assert covered == set(REQUIRED_DATASETS)
    assert not (set(R.READERS) & set(R.READERS_NOT_IMPLEMENTED))
    assert R.READERS_NOT_IMPLEMENTED == {}


# --- the readers obey the manifest, they do not search --------------------------

@sources
def test_a_reader_reads_only_what_the_leaf_marked_consumed():
    """Six of seven for status — 事件+下市.zip is a different source
    (build_market_state.py:52) and must stay unread. For prices, 3 of the 27
    entries in the export directory, plus the whole pre-2019 cache leg, which
    lives in a different tree entirely (§2.8.3).

    The 2019+ leg was 2 of 26 until 股價0817-0828.zip (2026-08-18 .. 2026-08-28)
    was declared. The not_consumed count stays 24 because the new archive
    entered as CONSUMED — it never sat in the rejected pile — so this line is
    the one that must move, not that one.
    """
    import collections

    prices = P.build(RUN, AS_OF)
    legs = collections.Counter(e.get("leg") for e in R.consumed_entries(prices))
    assert legs["2019+"] == 3
    assert legs["pre-2019"] > 2000
    assert sum(1 for e in prices["entries"]
               if e["disposition"] == "not_consumed") == 24
    assert len([e for e in prices["entries"]
                if e.get("leg") != "pre-2019"]) == 27

    status = F.build("security_status", RUN, AS_OF)
    consumed = [e["locator"] for e in R.consumed_entries(status)]
    assert len(consumed) == 6 and len(status["entries"]) == 7
    assert not any("事件" in n for n in consumed)


@sources
def test_a_source_changed_after_declaration_is_caught(run_dir, monkeypatch):
    """The engine checks hashes at declare time; the reader checks again at read
    time, closing the window between the two."""
    monkeypatch.setattr(R, "file_sha256", lambda p: "9" * 64)
    with pytest.raises(R.ReaderError, match="changed between declaration and read"):
        R.read_calendar(run_dir)


@sources
def test_the_calendar_reader_returns_the_declared_series(run_dir):
    sessions = R.read_calendar(run_dir)
    assert sessions[0] == "2004-01-02"
    assert sessions[-1] > "2026-08-17"                 # past L2's frozen end


@sources
def test_the_valuation_reader_treats_a_zero_ratio_as_undefined(run_dir):
    vals = R.read_valuation(run_dir)
    assert vals
    assert all(v["pbr_tse"] != 0.0 for v in vals.values())


# --- security_status ------------------------------------------------------------

@sources
def test_a_resumption_is_emitted_as_its_own_filed_fact(run_dir):
    """Without it a suspension explains missing prices forever."""
    rows = R.read_security_status(run_dir)
    resumes = [r for r in rows if r["reason"] == "resume"]
    assert resumes
    assert all(r["status"] == "listed" for r in resumes)
    # A delisting never resumes.
    for r in rows:
        if r["status"] == "delisted":
            assert r["reason"] != "resume"


@sources
def test_available_from_is_present_on_every_record(run_dir):
    """B0.6 exists because `status_available_from` was absent from the state.
    O-E-1 needs the date a status became KNOWABLE, and a record without one
    cannot satisfy it."""
    rows = R.read_security_status(run_dir)
    assert all(r["available_from"] for r in rows)
    assert all(r["available_from"] == r["effective_from"] for r in rows)


def test_an_uninterpretable_reason_produces_no_status_record():
    """O-F ruling 4, fail closed: a 停止過戶 window or an unreadable reason must
    not be promoted to `suspended`, because a promoted row would then stand over
    a session as an explanation for a missing price."""
    from core.b0_market_state import status_for_event

    assert status_for_event("停止過戶") is None
    assert status_for_event("") is None
    assert status_for_event("合併下市") == "delisted"


# --- corporate_actions ----------------------------------------------------------

@sources
def test_the_ledger_binds_this_runs_status_leaf(run_dir, monkeypatch):
    """The holder-side exits come from security_status and nowhere else, so the
    ledger must be built against THIS run's declared status source."""
    real = R.load_leaf

    def tampered(path):
        leaf = real(path)
        if "security_status" in os.path.basename(path):
            return {**leaf, R.SELF_HASH_FIELD: "9" * 64}
        return leaf

    assert R.assert_status_dependency_holds(run_dir)
    monkeypatch.setattr(R, "load_leaf", tampered)
    with pytest.raises(R.ReaderError, match="not the one"):
        R.assert_status_dependency_holds(run_dir)


@sources
@heavy
def test_not_reconstructible_rows_are_part_of_the_source(run_dir):
    """B0.7 terminates on exactly these rows. A reader that filtered them out
    would make the run look like it had more history than it does."""
    rows = R.read_corporate_actions(run_dir)
    states = {r["reconstructibility"] for r in rows}
    assert "NOT_RECONSTRUCTIBLE" in states
    assert any(r["kind"] == "holder_side_reorganization_exit" for r in rows)
    # B0.3 R4: provenance travels with the event.
    assert all("source_field" in r for r in rows)


# --- bonus_shares ---------------------------------------------------------------

@sources
@heavy
def test_the_bonus_window_is_an_argument_not_a_constant(run_dir):
    """L2's window is a property of L2's frozen 141 periods. Baking it in would
    make a prospective panel that silently stops in March."""
    ledger = R.read_corporate_actions(run_dir)
    sessions = list(R.read_calendar(run_dir))
    wide = R.read_bonus_shares(run_dir, "2013-06-29", "2026-03-31",
                               ledger=ledger, sessions=sessions)
    narrow = R.read_bonus_shares(run_dir, "2020-01-01", "2026-03-31",
                                 ledger=ledger, sessions=sessions)
    assert len(narrow) < len(wide)
    assert narrow["market_effective_session"].min() >= "2020-01-01"


def test_an_official_zero_never_becomes_a_multiplier_of_one():
    """An official row saying 'no bonus' contradicts the ledger's own
    classification of the event; turning it into m = 1 would silently assert
    that no adjustment was needed."""
    from core.b0_bonus_share_source import (
        MATCHED_DISPOSITION, UNRESOLVED_DISPOSITION, assert_no_inferred_multiplier,
        holder_multiplier_from_bonus, resolve_disposition,
    )

    assert holder_multiplier_from_bonus(100.0) == 1.1
    assert resolve_disposition(official_bonus_per_1000=None,
                               pre_listing=False) == UNRESOLVED_DISPOSITION
    assert resolve_disposition(official_bonus_per_1000=100.0,
                               pre_listing=False) == MATCHED_DISPOSITION
    with pytest.raises(Exception):
        assert_no_inferred_multiplier(UNRESOLVED_DISPOSITION, 1.0)


# --- the readers do not inherit L2's frozen window ------------------------------

@sources
@heavy
def test_the_fundamentals_readers_run_past_the_frozen_window(run_dir):
    """§2.2's availability rule belongs to the DECISION, not to the reader. A
    reader that stopped at window_end would be prospective in name only."""
    import pandas as pd

    end = pd.Timestamp(VP.WINDOW_END)
    fin = R.read_financials(run_dir)
    rev = R.read_revenue(run_dir)
    assert (fin["release_date"] > end).any()
    assert (pd.to_datetime(rev["release_date"]) > end).any()


@sources
@heavy
def test_the_later_export_owns_the_overlapping_period(run_dir):
    """Both financials sources carry 2026-06; the csv owns it and the workbook
    yields it, so every 2026-06 row must come from the csv's larger census."""
    fin = R.read_financials(run_dir)
    june = fin[fin["date"].astype(str).str[:7] == "2026-06"]
    assert len(june) > 1000            # the csv's 1,879, not the xlsx's 318


# --- parity: the readers reproduce L2's answer from the same bytes -------------

@sources
def test_the_calendar_is_a_suffix_extension_of_l2s(run_dir):
    """PREFIX, not equality: L2 is frozen at 2026-08-17 and the declared series
    runs past it. What must hold is that no PAST session was re-dated — a
    calendar that moves one re-dates every decision that stood on it."""
    got = VP.verify_calendar(run_dir)
    assert got["l3_sessions"] >= got["l2_sessions"]
    assert got["extension"]


@sources
def test_a_re_dated_past_session_would_fail_parity(run_dir, monkeypatch):
    """Negative control for the prefix rule."""
    real = R.read_calendar(run_dir)
    monkeypatch.setattr(VP, "read_calendar",
                        lambda _d: ("1999-01-01",) + real[1:])
    with pytest.raises(VP.ParityError, match="not a suffix-extension"):
        VP.verify_calendar(run_dir)


@sources
def test_valuation_parity_against_the_sealed_panel(run_dir):
    assert VP.verify_valuation(run_dir, AS_OF)["values_checked"] > 3000


@sources
def test_security_status_parity_against_the_sealed_table(run_dir):
    got = VP.verify_security_status(run_dir)
    assert got["records"] == 1375
    assert got["statuses"] == ["delisted", "listed", "suspended"]


@sources
def test_industry_parity_against_the_sealed_timeline(run_dir):
    """§2.3's step function must have exactly ONE construction."""
    got = VP.verify_industry(run_dir)
    assert got["securities"] == 2436
    assert got["unresolved_securities"] == 92


@sources
def test_a_lost_status_record_would_fail_parity(run_dir, monkeypatch):
    """Negative control: dropping one row must not pass."""
    real = R.read_security_status(run_dir)
    monkeypatch.setattr(VP, "read_security_status", lambda _d: real[1:])
    with pytest.raises(VP.ParityError, match="row counts differ"):
        VP.verify_security_status(run_dir)


@sources
@heavy
def test_revenue_parity_against_the_sealed_panel(run_dir):
    got = VP.verify_revenue(run_dir)
    assert got["rows"] > 300_000
    # §2.1: the window opens at 2014-07 because real release dates begin 2013-01.
    assert got["first_real_release_date"].startswith("2013")


@sources
@heavy
def test_financials_parity_against_the_sealed_panel(run_dir):
    got = VP.verify_financials(run_dir)
    assert got["rows"] > 130_000
    assert got["columns_checked"] == 15


@sources
@heavy
def test_corporate_action_ledger_parity_is_byte_for_byte(run_dir):
    """Byte equality because the ledger IS consumed as a CSV downstream: the
    bonus panel reads it with `csv.DictReader` and compares strings, so a float
    whose repr moved is a real difference to that consumer."""
    got = VP.verify_corporate_actions(run_dir)
    assert got["events"] == 46433
    assert got["holder_side_reorganization_exits"] == 158


@sources
@heavy
def test_bonus_share_parity_against_the_sealed_panel(run_dir):
    got = VP.verify_bonus_shares(run_dir)
    assert got["events"] == 3215
    assert got["matched_official_bonus_rate"] == 2399


@sources
@heavy
def test_price_parity_against_the_sealed_panel(run_dir):
    got = VP.verify_prices(run_dir)
    assert got["rows"] > 3_000_000
    assert got["columns_checked"] == ["open", "close", "volume_shares"]


# --- mixed declared formats within one family -----------------------------------
#
# These three are deliberately NOT @heavy. The defect they cover — read_revenue
# calling pd.read_excel on every consumed entry — shipped precisely because its
# only coverage sat behind B0_L3_PARITY=1, so the default suite was green on the
# day a second format was declared into the family.


def test_an_unregistered_declared_format_aborts_naming_it(tmp_path):
    """Guessing a parser from the extension is how a UTF-16/TAB export becomes a
    silent one-column frame. A declared format with no registered reader must
    therefore abort, and must name both the format and the file so the operator
    knows which of the two to change."""
    path = os.path.join(str(tmp_path), "revenue.parquet")
    open(path, "wb").close()
    entry = {"locator": "revenue.parquet", "format": "parquet:snappy"}

    with pytest.raises(R.ReaderError) as excinfo:
        R._read_declared_table(entry, path)

    message = str(excinfo.value)
    assert "parquet:snappy" in message
    assert "revenue.parquet" in message


@sources
def test_the_revenue_family_reads_both_of_its_declared_formats(tmp_path):
    """The family declares a workbook AND a zip wrapping a UTF-16/TAB csv. The
    completed July export exists only in the archive, and the reader does not
    clip by window_end — that belongs to the panel builder — so July arriving
    here is what the L3 prospective path actually depends on."""
    run = str(tmp_path)
    write_leaf(run, F.build("revenue", RUN, AS_OF))

    formats = {e["locator"]: e.get("format")
               for e in R.consumed_entries(R._leaf_and_landing(run, "revenue")[0])}
    assert set(formats.values()) == {"xlsx", "zip:csv:utf-16:tab"}

    frame = R.read_revenue(run)
    july = frame[frame["date"].astype(str).str.startswith("2026-07")]
    assert len(july) == 2002
    assert july["stock_id"].nunique() == 2002


@sources
def test_the_overlapping_month_is_decided_by_ownership_not_by_order(tmp_path):
    """Both sources carry 202607: the workbook holds a PARTIAL 406 securities
    frozen at its 2026-08-06 export, the archive holds the completed 2,002 and
    OWNS the month. On the 406 they share they also DISAGREE — 3003 was revised
    658,000 -> 657,875 千元 — so that security is the discriminator. If concat
    order, drop_duplicates or a first-wins guard were deciding this, the stale
    figure could win and nothing would raise."""
    run = str(tmp_path)
    write_leaf(run, F.build("revenue", RUN, AS_OF))

    frame = R.read_revenue(run)
    july = frame[frame["date"].astype(str).str.startswith("2026-07")]

    revised = july[july["stock_id"] == "3003"]["revenue"]
    assert len(revised) == 1
    assert float(revised.iloc[0]) == 657_875_000.0
    assert float(revised.iloc[0]) != 658_000_000.0

    # The workbook left these two unpublished ("."); only the owning source has
    # a figure at all, so their presence is a second, independent witness that
    # the archive was read rather than merely declared.
    for stock_id in ("2838", "6020"):
        assert len(july[july["stock_id"] == stock_id]) == 1


# --- P1-3 · a locator may not leave its landing directory -----------------------
#
# `_verified_path` did `os.path.join(landing, entry["locator"])` directly. A
# locator of `..\outside.txt` therefore resolved OUTSIDE the landing directory
# and the raw_sha256 check that follows did not notice — it hashes whatever file
# was reached, so the manifest looked honest about a file its landing surface
# never held.

def _escape_fixture(tmp_path):
    from core.b0_canonical_hash import file_sha256

    root = str(tmp_path)
    landing = os.path.join(root, "landing")
    os.makedirs(landing)
    outside = os.path.join(root, "outside.txt")
    open(outside, "wb").write(b"bytes the manifest never declared\n")
    inside = os.path.join(landing, "declared.txt")
    open(inside, "wb").write(b"legitimate\n")
    return landing, outside, inside, file_sha256


@pytest.mark.parametrize("locator", [
    r"..\outside.txt", "../outside.txt", "..", ".", "", "sub/outside.txt",
])
def test_NEGATIVE_a_locator_cannot_escape_the_landing_directory(
        tmp_path, locator):
    landing, outside, _, file_sha256 = _escape_fixture(tmp_path)
    entry = {"locator": locator, "raw_sha256": file_sha256(outside),
             "disposition": "consumed"}

    with pytest.raises(R.ReaderError):
        R._verified_path(landing, entry)


def test_NEGATIVE_an_absolute_locator_is_refused(tmp_path):
    """The hash MATCHES here — that is the point. Escaping is not caught by
    checking bytes, because the bytes checked are the ones that were reached."""
    landing, outside, _, file_sha256 = _escape_fixture(tmp_path)
    entry = {"locator": outside, "raw_sha256": file_sha256(outside),
             "disposition": "consumed"}

    with pytest.raises(R.ReaderError, match="absolute"):
        R._verified_path(landing, entry)


def test_a_single_component_locator_inside_the_landing_still_reads(tmp_path):
    """The guard must not cost the legitimate case."""
    landing, _, inside, file_sha256 = _escape_fixture(tmp_path)
    entry = {"locator": "declared.txt", "raw_sha256": file_sha256(inside),
             "disposition": "consumed"}

    assert R._verified_path(landing, entry) == inside


def test_NEGATIVE_a_symlinked_source_is_refused(tmp_path):
    """A link is an ADDRESS, not a source: the bytes behind it can be replaced
    without the landing directory changing at all. Containment is therefore
    decided after `realpath`, not on the joined string."""
    landing, outside, _, file_sha256 = _escape_fixture(tmp_path)
    link = os.path.join(landing, "innocent.txt")
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip("this account cannot create symlinks: %s" % exc)

    entry = {"locator": "innocent.txt", "raw_sha256": file_sha256(outside),
             "disposition": "consumed"}
    with pytest.raises(R.ReaderError):
        R._verified_path(landing, entry)


# --- P1-2 · the reader boundary reconciles the landing surface ------------------
#
# `assert_landing_dir_matches` had NO caller anywhere in the tree: every reader
# went from the leaf straight to a join, so at read time nothing compared the
# leaf against the directory it names. A file that appeared after the leaf was
# written was invisible — the silent inclusion `*.zip` was replaced to stop, one
# layer later.

def _enumerated_leaf(tmp_path, dataset="industry"):
    """A leaf that ENUMERATED its surface: it names a file it does not consume,
    which only a producer that ruled on every file can do."""
    from core.b0_canonical_hash import file_sha256
    from source_ownership_manifest import build_leaf

    root = str(tmp_path)
    landing = os.path.join(root, "landing")
    run = os.path.join(root, "run")
    os.makedirs(landing)
    os.makedirs(run)
    for name in ("used.xlsx", "spare.xlsx"):
        open(os.path.join(landing, name), "wb").write(
            ("bytes of %s\n" % name).encode())

    def entry(name, disposition):
        e = {"locator": name, "format": "xlsx",
             "raw_sha256": file_sha256(os.path.join(landing, name)),
             "export_vintage": "2026-08-06",
             "observed_at": "2026-08-26T19:00:00+08:00",
             "source_family": "TEJ", "authority": "AUTHORITATIVE",
             "disposition": disposition}
        if disposition == "not_consumed":
            e["not_consumed_reason"] = "declared and deliberately unused"
        return e

    write_leaf(run, build_leaf(
        dataset=dataset, run_id=RUN, as_of=AS_OF,
        landing_directory=landing, accepted_extensions=(".xlsx",),
        entries=[entry("used.xlsx", "consumed"),
                 entry("spare.xlsx", "not_consumed")]))
    return run, landing


def test_the_reader_boundary_accepts_a_surface_that_still_agrees(tmp_path):
    run, _ = _enumerated_leaf(tmp_path)
    leaf, landing = R._leaf_and_landing(run, "industry")
    assert {e["locator"] for e in leaf["entries"]} == {"used.xlsx", "spare.xlsx"}
    assert len(R._landing_groups(leaf, landing)) == 1


def test_NEGATIVE_a_file_that_joined_the_landing_directory_is_caught(tmp_path):
    """The O-H defect one layer later: the leaf ruled on every file in this
    directory, so one it never ruled on is a source nobody ruled on."""
    run, landing = _enumerated_leaf(tmp_path)
    open(os.path.join(landing, "arrived_later.xlsx"), "wb").write(b"unruled\n")

    with pytest.raises(R.ReaderError, match="not declared by leaf"):
        R._leaf_and_landing(run, "industry")


def test_NEGATIVE_a_replaced_not_consumed_source_is_caught(tmp_path):
    """A not_consumed entry is opened nowhere, so the landing reconciliation is
    the only place its declaration is ever checked against the disk."""
    run, landing = _enumerated_leaf(tmp_path)
    open(os.path.join(landing, "spare.xlsx"), "wb").write(b"replaced in place\n")

    with pytest.raises(R.ReaderError, match="changed between declaration"):
        R._leaf_and_landing(run, "industry")


def test_NEGATIVE_a_declared_source_that_disappeared_is_caught(tmp_path):
    run, landing = _enumerated_leaf(tmp_path)
    os.remove(os.path.join(landing, "spare.xlsx"))

    with pytest.raises(R.ReaderError, match="not present"):
        R._leaf_and_landing(run, "industry")


@sources
def test_every_family_still_passes_the_landing_reconciliation(tmp_path):
    """The check must hold for all nine REAL declarations, not only a fixture.
    Two shapes it deliberately tolerates and one it does not:

        calendar   a SHARED cache root with five sibling subdirectories that
                   belong to other consumers. The leaf does not carry
                   `declared_subdirectories`, so subdirectories are skipped.
        valuation  TWO board payloads named out of a per-session store holding
                   hundreds of files — a NAMED SUBSET, not an enumeration, so
                   the undeclared direction does not run for it.
        prices     TWO landing groups (§2.8.3), reconciled separately.
    """
    run = str(tmp_path)
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(run, F.build(ds, RUN, AS_OF))
    for mod in (FIN, P, B, V):
        write_leaf(run, mod.build(RUN, AS_OF))
    write_leaf(run, CA.build(RUN, AS_OF, run_dir=run))

    groups = {}
    for ds in sorted(F.FLAT_FAMILIES) + ["financials", "prices",
                                         "bonus_shares", "valuation",
                                         "corporate_actions"]:
        leaf, landing = R._leaf_and_landing(run, ds)      # must not raise
        groups[ds] = len(R._landing_groups(leaf, landing))

    assert groups["prices"] == 2                    # 2019+ and the pre-2019 leg
    assert groups["calendar"] == 1
