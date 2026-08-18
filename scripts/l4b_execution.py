# -*- coding: utf-8 -*-
"""l4b_execution.py — L4b 執行帳本:OrderIntent → 成交回報 → PositionState。

規格:`docs/規格_部署層MVP_L4ab.md` §4-§7。只消費 L4a 已產生的 `OrderIntent`,
**不重算目標名單、不改動選股邏輯**。

決策與結果分離(規格 §2,不可妥協):`PositionState` 只在本檔收到「可驗證的執行回報」
(這裡 = TEJ 歷史種子 ∪ market_cache 每日快照 的執行日實際 open/Trading_Volume)
後才更新——L4a 不寫這個狀態,本檔也不讀 L4a 以外的任何選股輸入。

用法:
    python scripts/l4b_execution.py --decision-date 2026-08-06 --exec-date 2026-08-07 --dry-run
    python scripts/l4b_execution.py --decision-date 2026-08-06 --exec-date 2026-08-07
    # 首次執行(搭配 L4a 的 --init-empty 起點):
    python scripts/l4b_execution.py --decision-date 2026-08-06 --exec-date 2026-08-07 \
        --init-empty --capital 10000000
================================================================================
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for p in (str(_HERE), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from l4a_decision import PositionState, LEDGER_DIR, POSITION_STATE_PATH, LOT_SIZE  # noqa: E402

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"

# ============================================================================
# 凍結參數(規格 §4.3-1:「合計比照 H1-H5 驗證用的假設,不得引入新成本假設而不重新
# 對照 H4」——這裡逐字沿用 scripts/portfolio_simulator_lab.py 的 BUY_COST/SELL_COST,
# 那是實際產生 22.79% CAGR / 夏普1.20 這組驗證數字的假設,不是規格文字描述四捨五入後
# 的版本(0.47%手續費+0.25%滑價 是文字摘要,不是逐位元相同的常數)。
# ============================================================================
BUY_COST = 0.001585
SELL_COST = 0.001585 + 0.003          # 0.004585


@dataclass
class ExecutionReceipt:
    """不可變快照(規格 §6.2)。"""
    stock_id: str
    name: str
    decision_date: str
    exec_date: str
    direction: str                 # buy / sell / none / carried_reject
    status: str                    # filled / rejected / not_submitted
    reject_reason: Optional[str]
    order_lots: int
    filled_lots: int
    open_price: Optional[float]
    cost_amount: float
    cash_delta: float


# ============================================================================
# 1. 執行日市場資料(規格 §4.2:當日開盤價 + 當日成交量)
# ============================================================================
def _load_exec_day_market(exec_date: str) -> pd.DataFrame:
    """回傳 columns=[stock_id, open, Trading_Volume]。

    資料源與 `scripts/universe_screen_daily.py` 的 `load_union()` 同一份 TEJ 歷史種子
    ∪ market_cache 每日快照(接縫已在別處實測一致),差別只在這裡多取 `open` 欄
    (`load_union()` 只取 close,不夠 L4b 用——L4b 依規格 §4.3-2 用開盤價成交)。

    §7 fail-closed:當日完全查不到資料 → 整批中止(不是逐股 reject),因為這代表
    資料管線本身有問題,不是單一個股停牌。
    """
    con = duckdb.connect()
    parts = [
        f"SELECT stock_id, open, Trading_Volume FROM "
        f"read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true) "
        f"WHERE date = '{exec_date}'"
    ]
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    if has_snap:
        parts.append(
            f"SELECT stock_id, open, Trading_Volume FROM "
            f"read_parquet('{str(SNAP_DIR / '*.parquet')}', union_by_name=true) "
            f"WHERE date = '{exec_date}'"
        )
    df = con.execute(" UNION ALL BY NAME ".join(parts)).df()
    con.close()
    if df.empty:
        raise SystemExit(
            f"❌ {exec_date} 在 TEJ_CACHE/market_cache 都查不到任何市場資料。"
            f"規格 §7:資料管線層級的缺失視同整批中止,不得逐股 reject 蓋過去"
            f"(那會掩蓋『資料根本沒更新到這天』這種更嚴重的問題)。")
    df["stock_id"] = df["stock_id"].astype(str)
    df = df.drop_duplicates(subset="stock_id", keep="last")
    return df


def load_order_intent(decision_date: str) -> dict:
    p = LEDGER_DIR / f"order_intent_{decision_date}.json"
    if not p.exists():
        raise SystemExit(f"❌ 找不到 {p}。L4b 只消費 L4a 已產生的 OrderIntent,"
                         f"不得自行重算目標名單(規格 §4.2)。")
    return json.loads(p.read_text(encoding="utf-8"))


# ============================================================================
# 2. 執行(規格 §4.3,依序不可跳步)
# ============================================================================
def execute(decision_date: str, exec_date: str, pos: PositionState
           ) -> tuple[list[ExecutionReceipt], PositionState]:
    payload = load_order_intent(decision_date)
    orders = payload["orders"]
    market = _load_exec_day_market(exec_date)
    market_lookup = dict(zip(market["stock_id"],
                             zip(market["open"], market["Trading_Volume"])))

    receipts: list[ExecutionReceipt] = []
    new_holdings = {k: dict(v) for k, v in pos.holdings.items()}
    cash = pos.cash
    realized_pnl = pos.realized_pnl

    for o in orders:
        sid, name = o["stock_id"], o["name"]
        direction, status = o["direction"], o["status"]

        # --- 這筆單在 L4a 就已經被拒絕(無參考價/ADV20缺失)→ 不送單,原樣留痕 ---
        if status == "rejected":
            receipts.append(ExecutionReceipt(
                stock_id=sid, name=name, decision_date=decision_date, exec_date=exec_date,
                direction="carried_reject", status="rejected",
                reject_reason=f"L4a 已拒絕:{o['reject_reason']}",
                order_lots=0, filled_lots=0, open_price=None,
                cost_amount=0.0, cash_delta=0.0))
            continue

        # --- 這筆不需要任何動作(維持原張數,或資金不足一張)→ 不送單 ---
        if direction == "none" or o["order_lots"] == 0:
            receipts.append(ExecutionReceipt(
                stock_id=sid, name=name, decision_date=decision_date, exec_date=exec_date,
                direction="none", status="not_submitted",
                reject_reason=o.get("reject_reason"),
                order_lots=0, filled_lots=0, open_price=None,
                cost_amount=0.0, cash_delta=0.0))
            continue

        # --- 規格 §5.2:成交判斷規則式(不模擬逐筆委託簿) ---
        row = market_lookup.get(sid)
        if row is None:
            receipts.append(ExecutionReceipt(
                stock_id=sid, name=name, decision_date=decision_date, exec_date=exec_date,
                direction=direction, status="rejected",
                reject_reason="執行日無市場資料(可能停牌)",
                order_lots=o["order_lots"], filled_lots=0, open_price=None,
                cost_amount=0.0, cash_delta=0.0))
            continue

        open_price, vol = row
        if pd.isna(open_price) or open_price <= 0 or pd.isna(vol) or vol <= 0:
            receipts.append(ExecutionReceipt(
                stock_id=sid, name=name, decision_date=decision_date, exec_date=exec_date,
                direction=direction, status="rejected",
                reject_reason="執行日無成交量(停牌/無交易)",
                order_lots=o["order_lots"], filled_lots=0, open_price=None,
                cost_amount=0.0, cash_delta=0.0))
            continue

        lots = o["order_lots"]
        amount = lots * LOT_SIZE * float(open_price)

        if direction == "buy":
            cost = amount * BUY_COST
            cash_delta = -(amount + cost)
            cash += cash_delta
            h = new_holdings.get(sid, {"lots": 0, "avg_cost": 0.0, "name": name})
            # avg_cost 是「每股」均價(對齊 PositionState.holdings_value() 的用法),
            # 累加時要用總成本基礎(股數 × 每股均價)相加,不能直接拿張數 × 每股均價相加
            # (那會把單位搞錯,均價膨脹 LOT_SIZE 倍——這裡曾經是個 bug,測試時抓到)。
            old_total_cost = h["lots"] * LOT_SIZE * h["avg_cost"]
            new_lots = h["lots"] + lots
            h["avg_cost"] = (old_total_cost + amount + cost) / (new_lots * LOT_SIZE)
            h["lots"] = new_lots
            h["name"] = name
            h["last_update"] = exec_date
            new_holdings[sid] = h
        else:  # sell
            h = new_holdings.get(sid)
            if h is None or h["lots"] < lots:
                raise SystemExit(
                    f"❌ {sid} 賣出張數({lots})超過帳上持倉({(h or {}).get('lots', 0)})。"
                    f"規格 §7:買賣後持倉對不上 → 中止並報錯,不得靜默調整平帳。")
            cost = amount * SELL_COST
            proceeds = amount - cost
            cash_delta = proceeds
            cash += cash_delta
            realized_pnl += (float(open_price) - h["avg_cost"]) * lots * LOT_SIZE - cost
            h["lots"] -= lots
            h["last_update"] = exec_date
            if h["lots"] == 0:
                del new_holdings[sid]
            else:
                new_holdings[sid] = h

        receipts.append(ExecutionReceipt(
            stock_id=sid, name=name, decision_date=decision_date, exec_date=exec_date,
            direction=direction, status="filled",
            reject_reason=None, order_lots=lots, filled_lots=lots,
            open_price=float(open_price), cost_amount=float(cost), cash_delta=float(cash_delta)))

    new_pos = PositionState(as_of=exec_date, holdings=new_holdings, cash=cash,
                            realized_pnl=realized_pnl)
    return receipts, new_pos


# ============================================================================
# 3. 輸出(append-only,不可覆寫;PositionState 例外——見函式內註解)
# ============================================================================
def write_receipts(exec_date: str, receipts: list[ExecutionReceipt], meta: dict) -> Path:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    out = LEDGER_DIR / f"execution_receipt_{exec_date}.json"
    if out.exists():
        raise SystemExit(f"❌ {out} 已存在——成交回報是不可變快照,不得覆寫"
                         f"(規格 §6.2)。如需重算請先確認上一份是否已用於更新 PositionState。")
    payload = {
        "_what": "L4b 成交回報(不可變快照,規格 docs/規格_部署層MVP_L4ab.md §4)",
        "exec_date": exec_date, "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "receipts": [asdict(r) for r in receipts],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"✅ 已寫 {out}(sha256={sha[:16]}…)")
    return out


def write_position_state(pos: PositionState, position_state_path: Path) -> None:
    """PositionState 有兩份輸出:
    - `position_state_{as_of}.json`:當日凍結存證(append-only,不可覆寫,供事後對帳)
    - `position_state.json`(或呼叫端指定路徑):**唯一可變**的「目前」指標檔,
      下一輪 L4a 讀的就是這份。這是本規格中 PositionState 允許被覆寫的唯一檔案
      (規格 §6.1:只有 L4b 收到成交回報才能寫這個狀態)。
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    snap = LEDGER_DIR / f"position_state_{pos.as_of}.json"
    if snap.exists():
        raise SystemExit(f"❌ {snap} 已存在——PositionState 每日快照是不可變存證,不得覆寫。")
    text = json.dumps(asdict(pos), ensure_ascii=False, indent=2)
    snap.write_text(text, encoding="utf-8")
    Path(position_state_path).write_text(text, encoding="utf-8")
    print(f"✅ 已寫快照 {snap} 並更新指標檔 {position_state_path}")


# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="L4b 執行帳本:OrderIntent → 成交回報 → PositionState")
    ap.add_argument("--decision-date", required=True, help="對應 L4a 的決策日(讀 order_intent_{date}.json)")
    ap.add_argument("--exec-date", required=True,
                    help="實際執行日(YYYY-MM-DD)。§3.1 的執行日提示不排班——"
                         "由呼叫端明確指定,L4b 不自行猜測交易日曆")
    ap.add_argument("--position-state", default=str(POSITION_STATE_PATH))
    ap.add_argument("--init-empty", action="store_true",
                    help="首次執行:視 PositionState 為全現金起點(僅在檔案不存在時可用,"
                         "需搭配 --capital)")
    ap.add_argument("--capital", type=float, default=None, help="搭配 --init-empty 使用的起始資金")
    ap.add_argument("--dry-run", action="store_true", help="只印結果,不寫檔")
    args = ap.parse_args()

    pos_path = Path(args.position_state)
    if args.init_empty:
        if pos_path.exists():
            raise SystemExit(f"❌ {pos_path} 已存在,--init-empty 只能用於檔案不存在時。")
        if args.capital is None:
            raise SystemExit("❌ --init-empty 需要同時給 --capital。")
        pos = PositionState.empty(args.decision_date)
        pos.cash = args.capital
        print(f"[INFO] --init-empty:視為全現金起點,cash={args.capital}")
    else:
        pos = PositionState.load(pos_path)

    print(f"執行中(decision_date={args.decision_date}, exec_date={args.exec_date})…")
    receipts, new_pos = execute(args.decision_date, args.exec_date, pos)

    n_filled = sum(1 for r in receipts if r.status == "filled")
    n_rej = sum(1 for r in receipts if r.status == "rejected")
    n_ns = sum(1 for r in receipts if r.status == "not_submitted")
    total_cost = sum(r.cost_amount for r in receipts)
    print(f"\n{len(receipts)} 筆回報:{n_filled} 成交、{n_rej} 拒絕、{n_ns} 免送單")
    print(f"總成本(手續費+證交稅):{total_cost:,.0f}")
    print(f"現金:{pos.cash:,.0f} → {new_pos.cash:,.0f}")
    if new_pos.cash < 0:
        print(f"⚠️  現金為負({new_pos.cash:,.0f})——目標金額是用決策日收盤價 × 目標權重算的,"
              f"沒有預留成本與執行日跳空緩衝,這是全額投入下的預期內小額超支,不是帳務錯誤,"
              f"但規模若持續放大應回頭檢視 §6.3 的 100% 投入裁決。")
    for r in receipts:
        if r.status == "filled":
            print(f"  {r.direction:<5}{r.stock_id} {r.name}  {r.filled_lots}張 @ {r.open_price:.2f}"
                  f"  成本 {r.cost_amount:,.0f}")
        elif r.status == "rejected":
            print(f"  ❌ {r.stock_id} {r.name}  拒絕:{r.reject_reason}")
        else:
            note = f"  ℹ️{r.reject_reason}" if r.reject_reason else ""
            print(f"  --   {r.stock_id} {r.name}  免送單{note}")

    if args.dry_run:
        print("\n(--dry-run,未寫檔)")
        return 0

    meta = {"decision_date": args.decision_date, "buy_cost": BUY_COST, "sell_cost": SELL_COST}
    write_receipts(args.exec_date, receipts, meta)
    write_position_state(new_pos, pos_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
