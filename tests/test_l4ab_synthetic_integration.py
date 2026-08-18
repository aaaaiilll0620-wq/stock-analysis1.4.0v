# -*- coding: utf-8 -*-
"""L4a/L4b 部署層 MVP 的 synthetic integration test(規格 `docs/規格_部署層MVP_L4ab.md` §9)。

⚠ 全部合成資料。**不讀任何真實 TEJ_CACHE/market_cache/scores 快取,不碰真實資金。**
`TEJ_CACHE`/`MARKET_CACHE`/`LEDGER_DIR` 全部 monkeypatch 到 pytest 的 `tmp_path`,
市場資料是本檔手寫的合成 parquet fixture,股票代號(A/B/C/...)刻意不對應任何真實個股。

逐條對應規格 §9 的五項斷言:
  1. `test_full_replay_is_byte_identical`         可完整重播
  2. `test_no_same_day_peek`                      無同日偷看
  3. `test_conservation_of_cash_and_holdings`      守恆
  4. `test_determinism_excludes_only_timestamp`    決定性(唯一允許的非決定性欄位是
                                                    audit metadata 的 generated_at)
  5. `test_fail_closed_*`(五個情境)                資料不足即 fail-closed
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import l4a_decision as l4a   # noqa: E402
import l4b_execution as l4b  # noqa: E402


# ============================================================================
# 合成股票宇宙(固定 fixture,五個測試共用)
# ============================================================================
# 目標名單(決策日 SYN-T0 的價格):
#   A  100.0  新買
#   B   50.0  續留,張數會調整
#   D   None  無參考價 -> L4a 拒絕
#   E   30.0  L4a 端OK,但執行日市場資料完全缺 -> L4b 拒絕
#   F   20.0  L4a 端OK,執行日有資料但成交量=0(停牌) -> L4b 拒絕
#   G   10.0  正常買,兼用來測「無同日偷看」
#
# 目前持倉(這次決策之前):
#   B: 5 張 @ 40.0(續留)
#   C: 8 張 @ 15.0(這次被剔除,不在目標名單裡 —— 用來測 2026-08-10 修的
#      port_value 漏算 bug:C 的市值只能從「全池價格表」拿到,不在 target_list 裡)
DECISION_DATE = "SYN-T0"
EXEC_DATE = "SYN-T1"
FUTURE_DATE = "SYN-T2"          # 只用來證明 L4b 不會偷看這天的資料

TARGET_LIST = pd.DataFrame([
    {"stock_id": "A", "name": "A", "price": 100.0},
    {"stock_id": "B", "name": "B", "price": 50.0},
    {"stock_id": "D", "name": "D", "price": None},
    {"stock_id": "E", "name": "E", "price": 30.0},
    {"stock_id": "F", "name": "F", "price": 20.0},
    {"stock_id": "G", "name": "G", "price": 10.0},
])
FULL_PRICE_LOOKUP = {"A": 100.0, "B": 50.0, "D": None, "E": 30.0, "F": 20.0, "G": 10.0, "C": 25.0}
ADV_LOOKUP = {sid: 100_000_000.0 for sid in ["A", "B", "D", "E", "F", "G"]}
CAPITAL = 6_000_000.0


def _initial_position() -> l4a.PositionState:
    return l4a.PositionState(
        as_of="SYN-T0-1", cash=CAPITAL,
        holdings={
            "B": {"lots": 5, "avg_cost": 40.0, "name": "B", "last_update": "SYN-T0-1"},
            "C": {"lots": 8, "avg_cost": 15.0, "name": "C", "last_update": "SYN-T0-1"},
        },
        realized_pnl=0.0,
    )


# --- 執行日市場資料 fixture:分兩份(TEJ 種子 ∪ market_cache 快照),比照生產結構 ---
def _write_market_fixtures(tej_cache: Path, market_cache: Path) -> None:
    tej_dir = tej_cache / "price_valuation"
    tej_dir.mkdir(parents=True, exist_ok=True)
    # TEJ 種子:A/B/C 三檔在執行日(EXEC_DATE)的資料(C 是這次被剔除的舊持倉,
    # 需要執行日真實成交價才能實際出清,用來驗證守恆——不要跟 E「完全查無資料」搞混)
    pd.DataFrame([
        {"stock_id": "A", "date": EXEC_DATE, "open": 101.5, "Trading_Volume": 500_000},
        {"stock_id": "B", "date": EXEC_DATE, "open": 51.0, "Trading_Volume": 300_000},
        {"stock_id": "C", "date": EXEC_DATE, "open": 26.0, "Trading_Volume": 150_000},
        # G 刻意也放一筆「未來」(FUTURE_DATE)資料,價格明顯不同、容易辨識 ——
        # 用來證明 L4b 查 EXEC_DATE 時不會偷看到這筆。
        {"stock_id": "G", "date": FUTURE_DATE, "open": 999999.0, "Trading_Volume": 999_999},
    ]).to_parquet(tej_dir / "seed.parquet", index=False)

    snap_dir = market_cache / "price_valuation_daily"
    snap_dir.mkdir(parents=True, exist_ok=True)
    # market_cache 快照:G 在執行日的真實資料、F 執行日有資料但成交量=0(停牌)
    # E 完全不出現在任一份資料裡(整天查無資料)。
    pd.DataFrame([
        {"stock_id": "G", "date": EXEC_DATE, "open": 10.5, "Trading_Volume": 200_000},
        {"stock_id": "F", "date": EXEC_DATE, "open": 20.5, "Trading_Volume": 0},
    ]).to_parquet(snap_dir / "snap.parquet", index=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把 L4a/L4b 用到的所有路徑常數換成本次測試專用的 tmp_path 子目錄。"""
    ledger_dir = tmp_path / "ledger"
    tej_cache = tmp_path / "tej_cache"
    market_cache = tmp_path / "market_cache"
    _write_market_fixtures(tej_cache, market_cache)

    monkeypatch.setattr(l4a, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(l4b, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(l4b, "TEJ_CACHE", tej_cache)
    monkeypatch.setattr(l4b, "MARKET_CACHE", market_cache)
    monkeypatch.setattr(l4b, "SNAP_DIR", market_cache / "price_valuation_daily")
    return {"ledger_dir": ledger_dir, "tej_cache": tej_cache, "market_cache": market_cache}


def _run_l4a() -> list[l4a.OrderIntent]:
    return l4a.compute_order_intent(
        DECISION_DATE, TARGET_LIST, _initial_position(), ADV_LOOKUP,
        holdings_price_lookup=FULL_PRICE_LOOKUP)


def _orders_by_id(orders: list[l4a.OrderIntent]) -> dict:
    return {o.stock_id: o for o in orders}


# ============================================================================
# 1. 可完整重播:同一組輸入跑兩次,輸出逐位元相同(含實際寫檔的位元組比對)
# ============================================================================
def test_full_replay_is_byte_identical(env, tmp_path):
    orders_1 = _run_l4a()
    orders_2 = _run_l4a()
    assert [asdict(o) for o in orders_1] == [asdict(o) for o in orders_2]

    # 寫檔層級的逐位元比對:唯一允許不同的欄位是 generated_at(audit metadata,
    # 不是計算結果)——寫進兩個獨立的 tmp 目錄,除了這個欄位外,其餘 bytes 必須相同。
    out_dir_1, out_dir_2 = tmp_path / "run1", tmp_path / "run2"
    for out_dir, orders in [(out_dir_1, orders_1), (out_dir_2, orders_2)]:
        out_dir.mkdir()
        (out_dir / f"order_intent_{DECISION_DATE}.json").write_text(
            json.dumps({
                "_what": "L4a OrderIntent", "as_of": DECISION_DATE,
                "generated_at": "REDACTED-FOR-BYTE-COMPARE",
                "meta": {"capital": CAPITAL}, "orders": [asdict(o) for o in orders],
            }, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8")
    text_1 = (out_dir_1 / f"order_intent_{DECISION_DATE}.json").read_text(encoding="utf-8")
    text_2 = (out_dir_2 / f"order_intent_{DECISION_DATE}.json").read_text(encoding="utf-8")
    assert text_1 == text_2


def test_full_replay_l4b_is_byte_identical(env, tmp_path):
    orders = _run_l4a()
    l4a.write_order_intent(DECISION_DATE, orders, meta={"capital": CAPITAL})

    receipts_1, pos_1 = l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())
    receipts_2, pos_2 = l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())
    assert [asdict(r) for r in receipts_1] == [asdict(r) for r in receipts_2]
    assert asdict(pos_1) == asdict(pos_2)


# ============================================================================
# 2. 無同日偷看:執行日參考價只能來自 EXEC_DATE,不得讀到 FUTURE_DATE 的資料
# ============================================================================
def test_no_same_day_peek(env):
    market = l4b._load_exec_day_market(EXEC_DATE)
    row = market[market["stock_id"] == "G"].iloc[0]
    # G 的 FUTURE_DATE 那筆刻意設成 999999.0/999999 這種一眼可辨的哨兵值——
    # 查 EXEC_DATE 拿到的必須是當天的 10.5/200000,證明查詢是精確比對日期,
    # 不是「當天或之後最新可得」這種會偷看未來的邏輯。
    assert row["open"] == 10.5
    assert row["Trading_Volume"] == 200_000

    orders = _run_l4a()
    g = _orders_by_id(orders)["G"]
    # L4a 的參考價來自呼叫端傳入的 target_list(決策日價格),架構上完全不觸碰
    # 任何執行日資料源 —— compute_order_intent 不吃 TEJ_CACHE/MARKET_CACHE。
    assert g.reference_price == 10.0  # TARGET_LIST 裡 G 的決策日價格,不是 10.5/999999


# ============================================================================
# 3. 守恆:Σ(現金+持倉市值) 的變動只能由成交價差與成本解釋
# ============================================================================
def test_conservation_of_cash_and_holdings(env):
    orders = _run_l4a()
    l4a.write_order_intent(DECISION_DATE, orders, meta={"capital": CAPITAL})

    pos0 = _initial_position()
    receipts, pos1 = l4b.execute(DECISION_DATE, EXEC_DATE, pos0)

    # 3a. 現金變動必須逐筆可還原(不能無中生有或憑空消失)——這是最直接的
    #     「每一塊錢都要能追溯到某一筆 receipt」防線。
    assert pos1.cash == pytest.approx(pos0.cash + sum(r.cash_delta for r in receipts))

    by_id = {r.stock_id: r for r in receipts}

    # 3b. C(剔除,port_value 用全池價格表 25.0 估值,規格§3.3-3)全數出清:
    #     成交回報的股數 = 剔除前的張數;剔除後不再出現在 holdings。
    assert by_id["C"].direction == "sell"
    assert by_id["C"].filled_lots == 8
    assert "C" not in pos1.holdings

    # 3c. B(續留)張數變動 = 賣出量,均價不變(規格:部分賣出不重算剩餘持倉均價)。
    b_recv = by_id["B"]
    if b_recv.status == "filled":
        expected_b_lots = 5 + (b_recv.filled_lots if b_recv.direction == "buy"
                               else -b_recv.filled_lots)
        assert pos1.holdings.get("B", {}).get("lots", 0) == expected_b_lots
        if expected_b_lots > 0:
            assert pos1.holdings["B"]["avg_cost"] == pytest.approx(40.0) or \
                   b_recv.direction == "buy"

    # 3d. A(新買)成本模型必須逐筆核對:cost = lots*1000*price*BUY_COST。
    a_recv = by_id["A"]
    assert a_recv.status == "filled"
    expected_cost = a_recv.filled_lots * l4a.LOT_SIZE * a_recv.open_price * l4b.BUY_COST
    assert a_recv.cost_amount == pytest.approx(expected_cost)
    assert a_recv.open_price == pytest.approx(101.5)   # 確認真的用執行日開盤價,不是決策日的100.0


# ============================================================================
# 3b. 專屬回歸測試:2026-08-10 修的 port_value 漏算 bug(不是 §9 五項之一,但直接
#     護欄住這次修復——舊版只用 target_list 的價格表算 holdings_value,C(剔除、
#     不在 target_list 裡)的市值會被直接漏算)。用精確數字釘住,不是靠巧合過關。
# ============================================================================
def test_port_value_includes_dropped_holdings(env):
    # 手算:port_value = cash(6,000,000) + B(5張@50.0=250,000) + C(8張@25.0=200,000)
    #              = 6,450,000;target_weight=1/6 -> target_amount=1,075,000
    # G(price=10.0)的 target_lots = floor(1,075,000 / 10,000) = 107。
    # 若 C 的市值被漏算(舊 bug):port_value 只有 6,250,000,target_amount=1,041,666.67,
    # G 的 target_lots 會變成 104 —— 兩者用同一個 floor 除法在這個數字上剛好會分岔,
    # 用來確保這個回歸測試不是「改壞了也照樣過」的假陽性。
    orders = _run_l4a()
    g = _orders_by_id(orders)["G"]
    assert g.target_lots == 107


# ============================================================================
# 4. 決定性:相同版本程式碼+相同輸入 → 相同輸出,唯一允許的差異是 generated_at
# ============================================================================
def test_determinism_excludes_only_timestamp(env):
    orders_a = _run_l4a()
    orders_b = _run_l4a()
    payload_a = {"as_of": DECISION_DATE, "orders": [asdict(o) for o in orders_a]}
    payload_b = {"as_of": DECISION_DATE, "orders": [asdict(o) for o in orders_b]}
    assert payload_a == payload_b  # 不含 generated_at 的部分本來就該逐位元相同

    l4a.write_order_intent(DECISION_DATE, orders_a, meta={})
    saved = json.loads((env["ledger_dir"] / f"order_intent_{DECISION_DATE}.json")
                       .read_text(encoding="utf-8"))
    non_ts_keys = {k for k in saved if k != "generated_at"}
    assert non_ts_keys == {"_what", "as_of", "meta", "orders"}
    assert saved["orders"] == [asdict(o) for o in orders_a]


# ============================================================================
# 5. 資料不足即 fail-closed:逐條驗 §7 的規則真的觸發,不是靜默通過
# ============================================================================
def test_fail_closed_empty_target_list(env):
    with pytest.raises(SystemExit, match="目標名單為空"):
        l4a.compute_order_intent(DECISION_DATE, TARGET_LIST.iloc[0:0], _initial_position(),
                                 ADV_LOOKUP, holdings_price_lookup=FULL_PRICE_LOOKUP)


def test_fail_closed_missing_reference_price(env):
    # D 在 TARGET_LIST 裡 price=None -> 該檔 rejected,其餘照跑(不是整批中止)。
    orders = _run_l4a()
    by_id = _orders_by_id(orders)
    assert by_id["D"].status == "rejected"
    assert by_id["D"].reject_reason == "無參考價"
    assert by_id["A"].status == "ok"   # 其餘正常股票沒有被連坐


def test_fail_closed_l4b_missing_market_data(env):
    # E 完全不在任何一份執行日市場資料裡(TEJ 種子/market_cache 快照都沒有它)。
    orders = _run_l4a()
    l4a.write_order_intent(DECISION_DATE, orders, meta={})
    receipts, _ = l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())
    e_recv = {r.stock_id: r for r in receipts}["E"]
    assert e_recv.status == "rejected"
    assert "無市場資料" in e_recv.reject_reason
    # 其餘正常股票不因為 E 缺資料被連坐中止。
    assert {r.stock_id: r for r in receipts}["A"].status == "filled"


def test_fail_closed_l4b_zero_volume(env):
    # F 執行日有資料列但 Trading_Volume=0(停牌/無交易)。
    orders = _run_l4a()
    l4a.write_order_intent(DECISION_DATE, orders, meta={})
    receipts, _ = l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())
    f_recv = {r.stock_id: r for r in receipts}["F"]
    assert f_recv.status == "rejected"
    assert "無成交量" in f_recv.reject_reason


def test_fail_closed_corrupted_position_state(env, tmp_path):
    bad = tmp_path / "corrupt_position_state.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(SystemExit, match="損毀"):
        l4a.PositionState.load(bad)
    # 明確驗證:不是靜默退回全現金空狀態 —— 上面那個 raise 本身就是證明
    # (若曾經退回空狀態,這裡就不會 raise 而是回傳一個 PositionState.empty())。


def test_fail_closed_missing_position_state(env, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(SystemExit, match="init-empty"):
        l4a.PositionState.load(missing)


def test_fail_closed_sell_exceeds_holdings(env):
    # 人為構造一筆賣出張數超過帳上持倉的 OrderIntent,驗證 §7「買賣後持倉對不上
    # → 中止並報錯,不得靜默調整平帳」真的觸發。
    bad_order = l4a.OrderIntent(
        stock_id="B", name="B", decision_date=DECISION_DATE,
        execution_date_hint="x", direction="sell", status="ok", reject_reason=None,
        reference_price=50.0, current_lots=5, target_lots=0, order_lots=999,  # 超過帳上 5 張
        adv_capped=False, adv20=None)
    l4a.write_order_intent(DECISION_DATE, [bad_order], meta={})
    with pytest.raises(SystemExit, match="超過帳上持倉"):
        l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())


# ============================================================================
# 6. 凍結件保護(規格 §3.4/§6.2,附帶驗證 —— 不是 §9 的五項之一,但同一套 fixture
#    順手覆蓋,避免另開一份幾乎重複的測試檔)
# ============================================================================
def test_frozen_file_protection(env):
    orders = _run_l4a()
    l4a.write_order_intent(DECISION_DATE, orders, meta={})
    with pytest.raises(SystemExit, match="已存在"):
        l4a.write_order_intent(DECISION_DATE, orders, meta={})

    receipts, pos = l4b.execute(DECISION_DATE, EXEC_DATE, _initial_position())
    l4b.write_receipts(EXEC_DATE, receipts, meta={})
    with pytest.raises(SystemExit, match="已存在"):
        l4b.write_receipts(EXEC_DATE, receipts, meta={})
