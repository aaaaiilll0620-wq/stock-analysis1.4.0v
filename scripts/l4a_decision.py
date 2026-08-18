# -*- coding: utf-8 -*-
"""l4a_decision.py — L4a 決策層:目標名單 → OrderIntent。

規格:`docs/規格_部署層MVP_L4ab.md`。**只服務 dual100**
(`real_composite` Top20% ∩ `c2` Top20% @ADV≥100萬,等權,月頻全換股,完整交集,
平均 ~48 檔)。`TOP_N=15` 濃縮已於 `docs/預註冊_TOP15濃縮.md` 驗證**否定**
(2026-08-10,H4 滑價穩健不過)——預設不濃縮。

決策與結果分離(規格 §2,不可妥協):本檔只產生 `OrderIntent`,**不改動任何
`PositionState`**——持倉/現金/成本只有 L4b 收到真的成交回報才能更新。

用法:
    python scripts/l4a_decision.py --as-of 2026-08-07 --capital 1000000 --dry-run
    python scripts/l4a_decision.py --as-of 2026-08-07 --capital 1000000
================================================================================
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for p in (str(_HERE), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import score_store                                          # noqa: E402

# ============================================================================
# 凍結參數(docs/規格_部署層MVP_L4ab.md §10,2026-08-10 裁決)
# ============================================================================
ORDER_ADV_CAP = 0.03          # §5.1:單筆訂單金額不得超過 ADV20 的 3%
FUSION_PCT = 20                # 交集門檻:composite/c2 各取前 20%(dual100 驗證定義,不動)
LOT_SIZE = 1000                # 一張股票 = 1000 股

# ❌ TOP_N=15 濃縮已於 `docs/預註冊_TOP15濃縮.md` 驗證**否定**(2026-08-10)。
# H1/H2/H5 通過但 H4(滑價穩健)否定:滑價拉到 0.60% 時夏普從門檻 0.68 崩到 0.53,
# 損益兩平滑價僅 ≈0.26%(dual100 完整交集版是 0.71%)。H3 揭露同時證實濃縮的代價
# 是真的(CAGR −2.57pp、夏普 −0.20、MDD 惡化 3.0pp)。依預註冊 §3 出口2 處置,
# 預設**不得**濃縮,`compute_target_list` 的 `top_n` 預設改回 `None`(完整交集)。
# 使用者最初濃縮的動機(中小資金規模下全張門檻太分散)仍是真問題,只是「取固定前15檔」
# 這個解法被否定——不代表這個問題不需要處理,只是還沒有驗證過的解法,不得繞過去。
TOP_N = None

UNIV_DIR = _ROOT / "outputs" / "universe_pool"
LEDGER_DIR = _ROOT / "beat_0050" / "results" / "l4_ledger"             # §10-3 裁決:進版控
POSITION_STATE_PATH = LEDGER_DIR / "position_state.json"


# ============================================================================
# 資料結構
# ============================================================================
@dataclass
class OrderIntent:
    """不可變快照(規格 §3.3-6)。一旦產生,L4b 不得回頭修改任何欄位。"""
    stock_id: str
    name: str
    decision_date: str
    execution_date_hint: str      # 規格 §3.1:訊號 close(t),執行 open(t+1),這裡只給提示不排班
    direction: str                 # "buy" / "sell" / "none"
    status: str                    # "ok" / "rejected"
    reject_reason: Optional[str]
    reference_price: Optional[float]
    current_lots: int
    target_lots: int
    order_lots: int                # |target - current|,direction 決定加減
    adv_capped: bool
    adv20: Optional[float]


@dataclass
class PositionState:
    as_of: str
    holdings: dict = field(default_factory=dict)   # {stock_id: {"lots": int, "avg_cost": float, "last_update": str}}
    cash: float = 0.0
    realized_pnl: float = 0.0

    @classmethod
    def empty(cls, as_of: str) -> "PositionState":
        return cls(as_of=as_of, holdings={}, cash=0.0, realized_pnl=0.0)

    @classmethod
    def load(cls, path: Path) -> "PositionState":
        if not path.exists():
            raise SystemExit(
                f"❌ 找不到 PositionState:{path}。首次執行請明確加 --init-empty"
                f"(視為全現金起點),不得假設空狀態靜默通過(規格 §7)。")
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise SystemExit(f"❌ PositionState 讀取失敗(可能損毀):{path}:{e}\n"
                             f"   依規格 §7,fail-closed,不得假設空狀態重新開始。") from e
        return cls(as_of=d["as_of"], holdings=d.get("holdings", {}),
                  cash=float(d.get("cash", 0.0)), realized_pnl=float(d.get("realized_pnl", 0.0)))

    def holdings_value(self, price_lookup: dict) -> float:
        """目前持倉市值(用給定的參考價,通常是決策日收盤價)。"""
        total = 0.0
        for sid, h in self.holdings.items():
            px = price_lookup.get(sid)
            if px is not None and px > 0:
                total += h["lots"] * LOT_SIZE * px
        return total


# ============================================================================
# 1. 目標名單(composite Top20% ∩ c2 Top20% @ADV≥100萬)
# ============================================================================
def compute_target_list(as_of: str, mode: str = "balanced",
                        fusion_pct: int = FUSION_PCT,
                        top_n: Optional[int] = TOP_N) -> tuple[pd.DataFrame, dict]:
    """回傳 (目標名單, 全池價格表)。

    目標名單:columns=[stock_id, name, price]。邏輯與 `app.py` 的「雙確認精選」分頁
    一致(composite 用 `screen_by_composite_at`,c2 用 2026-08-10 新增的
    `c2_fullpool_{as_of}.csv`,已對齊 ADV≥100萬 母體)——這裡獨立重寫一份,不從
    app.py import(該檔是 Streamlit 頁面,不適合當函式庫用),但**公式與資料源
    逐字相同**,不得各自漂移。

    全池價格表(2026-08-10 修正):`{stock_id: price}`,涵蓋 `screen_by_composite_at`
    當天算過分數的全部股票(至多 3000 檔),不是只有進了目標名單的那些。用途:
    `compute_order_intent` 算「可投入資本」時,需要幫**這次被剔除、不在新目標名單裡**
    的舊持倉估值(規格 §3.3-3:「可用資金含已實現的持倉市值,不是只算現金」)——
    舊版只拿目標名單的價格表,剔除股的市值會被直接漏算,詳見程式碼內註解與
    `docs/現況總表_2026-08-09.md` §5.4 的記錄。

    `top_n`:交集(dual100 驗證定義)算完後,再依 composite 百分位由高到低取前 N 檔。
    **預設 `None`(= 模組層級 `TOP_N` 常數,不濃縮,回傳完整交集)。**
    `TOP_N=15` 這個濃縮動作已於 `docs/預註冊_TOP15濃縮.md` 驗證**否定**(2026-08-10,
    H4 滑價穩健不過)——如果要傳非 None 的值進來,先讀那份文件的結果,不要憑感覺重試。

    §7 fail-closed:目標名單算不出來(任一輸入缺失/空)→ raise,不回傳空表、
    不得由呼叫端誤用空表當「今天沒有標的」而繼續往下跑。
    """
    dfc = score_store.screen_by_composite_at(as_of, mode=mode, top=3000)
    if dfc is None or dfc.empty:
        raise SystemExit(f"❌ {as_of} 綜合分快取為空,無法算目標名單(規格 §7:整批中止)。")

    pf = UNIV_DIR / f"c2_fullpool_{as_of}.csv"
    if not pf.exists():
        raise SystemExit(f"❌ 找不到 {pf}(c2 全池,2026-08-10 起的產出)。"
                         f"無法算目標名單,整批中止,不得退回舊 pool_*.csv 頂替"
                         f"(那個母體/門檻跟 H1-H5 定義不同,見 docs/現況總表 §9)。")
    pool = pd.read_csv(pf, dtype={"stock_id": str})
    if "c2_score_full" not in pool.columns:
        raise SystemExit(f"❌ {pf} 缺 c2_score_full 欄,無法算目標名單。")

    pool["c2_pct"] = pool["c2_score_full"].rank(pct=True) * 100.0
    dfc = dfc.copy()
    dfc["stock_id"] = dfc["stock_id"].astype(str)
    dfc["c2_pct"] = dfc["stock_id"].map(dict(zip(pool["stock_id"], pool["c2_pct"])))

    full_price_lookup = dict(zip(dfc["stock_id"], dfc["price"]))

    thr = 100.0 - fusion_pct
    fus = dfc[(dfc["pct_rank"] >= thr) & (dfc["c2_pct"] >= thr)].copy()
    if fus.empty:
        raise SystemExit(f"❌ {as_of} 交集為空(規格 §7:目標名單算不出來 → 整批中止,"
                         f"不得用上月名單頂替)。")

    n_full = len(fus)
    if top_n is not None and n_full > top_n:
        fus = fus.sort_values("pct_rank", ascending=False).head(top_n).copy()
        print(f"⚠️  交集 {n_full} 檔 → TOP_N={top_n} 濃縮(依 composite 百分位取前 {top_n})。"
              f"這個動作已於 docs/預註冊_TOP15濃縮.md 驗證否定(H4 滑價穩健不過)——"
              f"若非刻意要重新測試不同的 top_n 數值,不應該傳非 None 進來。")
    return fus[["stock_id", "name", "price"]].reset_index(drop=True), full_price_lookup


# ============================================================================
# 2. OrderIntent(規格 §3.3,依序不可跳步)
# ============================================================================
def compute_order_intent(as_of: str, target_list: pd.DataFrame, pos: PositionState,
                         adv_lookup: dict, order_adv_cap: float = ORDER_ADV_CAP,
                         holdings_price_lookup: Optional[dict] = None) -> list[OrderIntent]:
    """可投入資本完全來自 `pos.cash`(§6.1:PositionState 是唯一權威狀態)。沒有另外的
    `available_capital` 參數——曾經有過,但函式體從未讀它,是死參數,容易誤導成
    「資金從這裡流入」,已移除(2026-08-10)。首次執行的起始資金是透過
    `PositionState.empty()` 後手動設 `pos.cash`(見 main() 的 --init-empty 分支)。
    """
    n = len(target_list)
    if n == 0:
        raise SystemExit("❌ 目標名單為空,規格 §7:整批中止,不產生任何 OrderIntent。")
    target_weight = 1.0 / n
    exec_hint = _next_trading_day_hint(as_of)

    target_ids = set(target_list["stock_id"])
    price_lookup = dict(zip(target_list["stock_id"], target_list["price"]))

    # 規格 §3.3-3:「可用資金含已實現的持倉市值,不是只算現金」——這裡的「已實現持倉」
    # 是指全部目前持倉,不是只有續留進新目標名單的那些。舊版曾經只拿 price_lookup
    # (只含目標名單)去估 holdings_value,這次被剔除、不在新名單裡的舊持倉價值會直接
    # 漏算,導致每次有換股(整月全換股下是常態)就系統性低估可投入資本。用呼叫端傳入的
    # 全池價格表(compute_target_list 回傳的第二個值)補齊;target_list 自己的價格
    # 優先(那是這次決策當下最新算的),全池價格表只補目標名單沒有的部分。
    combined_lookup = dict(holdings_price_lookup or {})
    combined_lookup.update(price_lookup)
    missing_priced = [sid for sid in pos.holdings if combined_lookup.get(sid) is None]
    if missing_priced:
        print(f"⚠️  {len(missing_priced)} 檔目前持倉在計分母體中查無價格,"
              f"port_value 會低估這些檔位的市值(視為單一持倉的資料缺口,不整批中止):"
              f"{missing_priced}")
    port_value = pos.cash + pos.holdings_value(combined_lookup)

    orders: list[OrderIntent] = []

    # --- 剔除:只在目前持倉、不在目標名單 → 全數出清(規格 §3.3-2) ---
    for sid in sorted(set(pos.holdings) - target_ids):
        h = pos.holdings[sid]
        orders.append(OrderIntent(
            stock_id=sid, name=h.get("name", sid), decision_date=as_of,
            execution_date_hint=exec_hint, direction="sell", status="ok",
            reject_reason=None, reference_price=None,
            current_lots=h["lots"], target_lots=0, order_lots=h["lots"],
            adv_capped=False, adv20=None))

    # --- 目標名單(續留+新增):每檔重算目標張數,整月全換股(規格 §3.3-3/4/5) ---
    for _, row in target_list.iterrows():
        sid, name, price = row["stock_id"], row["name"], row["price"]
        current_lots = int(pos.holdings.get(sid, {}).get("lots", 0))

        if price is None or not (price > 0):
            orders.append(OrderIntent(
                stock_id=sid, name=name, decision_date=as_of,
                execution_date_hint=exec_hint, direction="none", status="rejected",
                reject_reason="無參考價", reference_price=None,
                current_lots=current_lots, target_lots=current_lots, order_lots=0,
                adv_capped=False, adv20=None))
            continue

        adv20 = adv_lookup.get(sid)
        if adv20 is None or not (adv20 > 0):
            orders.append(OrderIntent(
                stock_id=sid, name=name, decision_date=as_of,
                execution_date_hint=exec_hint, direction="none", status="rejected",
                reject_reason="ADV20 缺失", reference_price=price,
                current_lots=current_lots, target_lots=current_lots, order_lots=0,
                adv_capped=False, adv20=None))
            continue

        target_amount = target_weight * port_value
        target_lots = int(target_amount // (price * LOT_SIZE))

        # §5.1 薄量股上限:下修,不得把差額分配給其他股票
        cap_amount = adv20 * order_adv_cap
        cap_lots = int(cap_amount // (price * LOT_SIZE))
        capped = target_lots > cap_lots
        if capped:
            target_lots = cap_lots

        delta = target_lots - current_lots
        if delta == 0:
            # 不需要下單,但仍留一筆 direction="none" 紀錄——不能因為「不用動作」就從
            # 稽核軌跡消失,尤其 target_lots=0 有兩種完全不同的原因需要分得清楚:
            # (a) 資金 ÷ N 檔後不夠買一張(見規格§10 零股討論);(b) 現有持倉已經等於目標。
            note = ("資金不足一張(target_amount 除以股價買不到 1 張)"
                    if target_lots == 0 and current_lots == 0 else None)
            orders.append(OrderIntent(
                stock_id=sid, name=name, decision_date=as_of,
                execution_date_hint=exec_hint, direction="none", status="ok",
                reject_reason=note, reference_price=price,
                current_lots=current_lots, target_lots=target_lots, order_lots=0,
                adv_capped=capped, adv20=adv20))
            continue
        orders.append(OrderIntent(
            stock_id=sid, name=name, decision_date=as_of,
            execution_date_hint=exec_hint,
            direction="buy" if delta > 0 else "sell", status="ok",
            reject_reason=None, reference_price=price,
            current_lots=current_lots, target_lots=target_lots, order_lots=abs(delta),
            adv_capped=capped, adv20=adv20))

    return orders


def _next_trading_day_hint(as_of: str) -> str:
    """只是提示用的字串,不是排班依據——真正的執行日由 L4b 收到市場資料時自行判定
    (交易日曆/假日在 L4b 才有意義)。避免這裡算錯反而誤導 L4b。"""
    return f"{as_of}+1個交易日"


# ============================================================================
# 3. 輸出(append-only,不可覆寫,規格 §3.4)
# ============================================================================
def write_order_intent(as_of: str, orders: list[OrderIntent], meta: dict) -> Path:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    out = LEDGER_DIR / f"order_intent_{as_of}.json"
    if out.exists():
        raise SystemExit(f"❌ {out} 已存在——OrderIntent 是不可變快照,不得覆寫"
                         f"(規格 §3.4)。如需重算請先確認上一份是否已被 L4b 消費。")
    payload = {
        "_what": "L4a OrderIntent(不可變快照,規格 docs/規格_部署層MVP_L4ab.md)",
        "as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "orders": [asdict(o) for o in orders],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"✅ 已寫 {out}(sha256={sha[:16]}…)")
    return out


# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="L4a 決策層:目標名單 → OrderIntent")
    ap.add_argument("--as-of", required=True, help="決策日(YYYY-MM-DD),須有當日 scores 快取")
    ap.add_argument("--mode", default="balanced")
    ap.add_argument("--capital", type=float, required=True,
                    help="可用資金(§10 未決項4:使用者自行提供,不預設值)")
    ap.add_argument("--position-state", default=str(POSITION_STATE_PATH))
    ap.add_argument("--init-empty", action="store_true",
                    help="首次執行:視 PositionState 為全現金起點(僅在檔案不存在時可用)")
    ap.add_argument("--dry-run", action="store_true", help="只印結果,不寫檔")
    args = ap.parse_args()

    pos_path = Path(args.position_state)
    if args.init_empty:
        if pos_path.exists():
            raise SystemExit(f"❌ {pos_path} 已存在,--init-empty 只能用於檔案不存在時"
                             f"(避免誤蓋掉真的持倉紀錄)。")
        pos = PositionState.empty(args.as_of)
        print(f"[INFO] --init-empty:視為全現金起點,cash={args.capital}")
        pos.cash = args.capital
    else:
        pos = PositionState.load(pos_path)

    print(f"目標名單計算中(as_of={args.as_of})…")
    target, full_price_lookup = compute_target_list(args.as_of, mode=args.mode)
    print(f"目標名單 {len(target)} 檔")

    pf = UNIV_DIR / f"c2_fullpool_{args.as_of}.csv"
    adv_df = pd.read_csv(pf, dtype={"stock_id": str})
    adv_lookup = dict(zip(adv_df["stock_id"], adv_df["adv20"]))

    orders = compute_order_intent(args.as_of, target, pos, adv_lookup,
                                  holdings_price_lookup=full_price_lookup)

    n_ok = sum(1 for o in orders if o.status == "ok")
    n_rej = sum(1 for o in orders if o.status == "rejected")
    n_capped = sum(1 for o in orders if o.adv_capped)
    n_broke = sum(1 for o in orders if o.reject_reason == "資金不足一張(target_amount 除以股價買不到 1 張)")
    print(f"\n產生 {len(orders)} 筆 OrderIntent:{n_ok} 正常、{n_rej} 拒絕、"
          f"{n_capped} 筆被薄量股上限下修、{n_broke} 檔資金不足一張")
    if n_broke > len(target) * 0.3:
        print(f"⚠️  {n_broke}/{len(target)} 檔資金不足一張——資金相對 {len(target)} 檔全張門檻明顯偏低,"
              f"多數配置實際上會落空,建議檢視 --capital 是否足夠(見規格 §10 未決項4)。")
    for o in orders:
        if o.status == "rejected":
            print(f"  ❌ {o.stock_id} {o.name}  拒絕:{o.reject_reason}")
        elif o.direction == "none":
            note = f"  ℹ️{o.reject_reason}" if o.reject_reason else ""
            print(f"  --   {o.stock_id} {o.name}  維持 {o.current_lots} 張{note}")
        else:
            cap_note = "  ⚠️ADV上限下修" if o.adv_capped else ""
            print(f"  {o.direction:<5}{o.stock_id} {o.name}  "
                  f"{o.current_lots}→{o.target_lots} 張({o.order_lots}張){cap_note}")

    if args.dry_run:
        print("\n(--dry-run,未寫檔)")
        return 0

    meta = {"mode": args.mode, "capital": args.capital,
           "order_adv_cap": ORDER_ADV_CAP, "fusion_pct": FUSION_PCT, "top_n": TOP_N,
           "n_target_list": len(target)}
    write_order_intent(args.as_of, orders, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
