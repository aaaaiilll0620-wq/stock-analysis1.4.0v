"""訊號可信度稽核 — 逐檔檢查「這檔的分數是不是建立在有效輸入上」
================================================================================
**這不是選股工具。** 本檔所有檢查回答的都是量測有效性問題,不是報酬預測問題:

    ✅ 「這檔的 revenue_yoy 分母是不是一個壞掉的月份?」
    ❌ 「這檔會不會漲?」

差別很要緊。專案已三次量到「在 67 檔交集內再排序」是負值
(docs/預註冊_TOP15濃縮.md H4 否定;BasketDispersionLab R1/R2/R3 三條判準全敗;
docs/預註冊_流動性資格門檻V1.md 三 arm 全滅)。因此本工具**刻意不輸出任何
隱含報酬預期的排名**——只輸出旗標與證據數值,由人判讀。

排除一檔「輸入壞掉」的股票不是下注,是拒絕對量測誤差採取行動;
排除一檔「我不喜歡」的股票是下注,而那個賭注已被量到是 −2.3 ~ −2.6pp/年。
**本工具只提供前者的證據,不提供後者的藉口。**

--------------------------------------------------------------------------------
邊界(不得逾越)
--------------------------------------------------------------------------------
- 不改任何分數、不改 core/、不寫任何凍結件、不改 frozen strategy。
- 唯讀:tej_cache / market_cache / outputs/universe_pool 的既有凍結 CSV。
- 決定性:同 as_of + 同快取 → 同輸出。無亂數、無 wall-clock 依賴。
- 每個旗標都附證據數值。**不得只給布林值**——沒有證據的旗標無法覆核,
  等於把「靜默改變口徑」搬到稽核層。

--------------------------------------------------------------------------------
七項檢查
--------------------------------------------------------------------------------
| 代號 | 檢查              | 為什麼這是量測問題而不是選股問題                    |
|------|-------------------|-----------------------------------------------------|
| X0   | 稽核資料缺漏      | 查不到證據就不能發通過證明(fail-closed,見下)      |
| R0   | 營收基期無法驗證  | 有 yoy 值卻查不到基期 → R1 這關等於沒做              |
| R1   | 營收基期塌陷      | yoy = 今年/去年,去年若是故障月則 yoy 無經濟意義     |
| R2   | 營收資料過期      | 這檔吃到的是比同儕舊的月份,不是同一個時點的比較     |
| L1   | c2 腿缺失         | c2 用 mean(skipna=True),缺腿會靜默變成三腿平均      |
| V1   | PE 分位樣本薄     | expanding 分位的樣本數決定分位本身的穩定度          |
| H1   | 52週窗不足        | 樣本不足 240 日時,「52週高」其實是 6~9 個月高       |
| A1   | ADV20 單日集中    | 均值被單日撐起 → 名目流動性不代表可成交量           |
| P1   | 近期停牌/缺交易   | 缺交易日代表價格類因子的窗口與同儕不對齊            |

**fail-closed**:每一項檢查的證據值若算不出來(該檔不在價格聯集、營收快取無列、
中位數是空切片…),一律標記為 X0/R0 而**不是靜默視為通過**。
`NaN < 門檻` 在 pandas 回傳 `False`——若不特別處理,缺資料的股票會拿到一張
乾淨的通過證明。這正是本專案史上四次靜默污染的同一種形狀,稽核工具自己犯
等於稽核失效。

**門檻性質**:下列常數是「偵測門檻」,決定什麼東西被標記給人看,
**不決定買什麼**。它們不進任何分數、不影響 c2/composite/交集,因此不受單發射擊制
約束。但一經設定即不得為了讓某檔過關而調整——那會讓稽核本身失去意義。

用法:
  python scripts/signal_integrity_audit.py                          # 稽核 c2 Top-20%
  python scripts/signal_integrity_audit.py --from-ledger beat_0050/results/l4_ledger/order_intent_2026-08-07.json
  python scripts/signal_integrity_audit.py --stocks 1808,2330 --as-of 2026-08-07
  python scripts/signal_integrity_audit.py --all                    # 全池
輸出:outputs/universe_pool/signal_integrity_{as_of}.csv + stdout 摘要
================================================================================
"""
import os
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"
POOL_DIR = Path(project_root) / "outputs" / "universe_pool"

REVENUE_LAG_DAYS = 10          # 月營收約次月 10 日前公佈 (同 universe_screen_daily)
PE_HISTORY_START = "2019-01-01"  # PE expanding 窗起點 (同 universe_screen_daily)

# --- 偵測門檻 (見檔頭「門檻性質」) ---
R1_BASE_RATIO = 0.20      # 去年同月營收 < 自身近13月營收中位數的 20% → 基期塌陷
R2_STALE_MONTHS = 2       # 這檔最新已知營收月落後全池最新月 >= 2 個月 → 過期
V1_MIN_PE_OBS = 250       # 2019 起有效 PE 觀測 < 250 (約1年) → 分位樣本薄
                          #   (< 60 者 value_ind 本來就是 NaN,會被 L1 抓到,不重複計)
H1_MIN_CLOSES = 180       # 近 240 交易日有效收盤 < 180 → 52週窗不足
                          #   (生產下限是 120,120~180 這段會通過生產卻名不副實)
A1_MAX_DAY_SHARE = 0.35   # 近 20 日單日成交金額最大值 / 20 日合計 > 35% → 單日集中
P1_MIN_TRADE_DAYS = 20    # 近 20 個全市場交易日內,本檔實際有交易的日數 < 20 → 缺交易

SEVERITY = {"X0": "HIGH", "R0": "HIGH", "R1": "HIGH", "L1": "HIGH",
            "R2": "MED", "V1": "MED", "H1": "MED",
            "A1": "LOW", "P1": "LOW"}
FLAG_DESC = {
    "X0": "稽核資料缺漏(fail-closed)",
    "R0": "營收基期無法驗證",
    "R1": "營收基期塌陷",
    "R2": "營收資料過期",
    "L1": "c2 腿缺失(分數為部分平均)",
    "V1": "PE 分位樣本薄",
    "H1": "52週窗不足",
    "A1": "ADV20 被單日撐起",
    "P1": "近期缺交易日",
}
C2_LEGS = ("value_ind_pct", "revenue_yoy", "high52_prox", "momentum20")


def load_price_union(con) -> pd.DataFrame:
    """TEJ 種子 ∪ 官方每日快照,接縫同 universe_screen_daily.load_union。"""
    tej_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
    """).fetchone()[0]
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    snap_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, close, Trading_Volume, PER_TSE
        FROM read_parquet('{SNAP_DIR / "*.parquet"}', union_by_name=true)
        WHERE date > '{tej_max}'""" if has_snap else ""
    return con.execute(f"""
        SELECT stock_id, date, close, Trading_Volume, PER_TSE
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        {snap_sql}
        ORDER BY stock_id, date
    """).df()


def check_revenue(con, as_of: str) -> pd.DataFrame:
    """R1 基期塌陷 + R2 資料過期。PIT:月底+10天 <= as_of 才算已知(同生產)。"""
    rev = con.execute(f"""
        SELECT stock_id, date, revenue, revenue_last_year
        FROM read_parquet('{TEJ_CACHE}/monthly_revenue/*.parquet', union_by_name=true)
    """).df()
    rev["known"] = (pd.to_datetime(rev["date"]) + pd.offsets.MonthEnd(0)
                    + pd.Timedelta(days=REVENUE_LAG_DAYS))
    rev = rev[rev["known"] <= pd.Timestamp(as_of)].sort_values(["stock_id", "date"])

    g = rev.groupby("stock_id")
    latest = g.tail(1).set_index("stock_id")

    def _median13(s: pd.Series) -> float:
        """自身近 13 個月營收中位數 = 「這檔正常一個月做多少」。
        全 NaN 切片直接回 NaN(不進 np.nanmedian,避免空切片警告與假中位數)。"""
        v = s.tail(13).dropna()
        return float(v.median()) if len(v) else np.nan

    out = pd.DataFrame({
        "rev_month": latest["date"],
        "rev_base": latest["revenue_last_year"],
        "rev_self_median13": g["revenue"].apply(_median13),
    })
    out["rev_base_ratio"] = out["rev_base"] / out["rev_self_median13"].replace(0, np.nan)
    # R0 先判:基期算不出來 → 這關等於沒做,不得當成通過
    out["R0"] = out["rev_base_ratio"].isna()
    out["R1"] = out["rev_base_ratio"] < R1_BASE_RATIO

    newest = pd.to_datetime(out["rev_month"]).max()
    lag = (newest.to_period("M") - pd.to_datetime(out["rev_month"]).dt.to_period("M"))
    out["rev_lag_months"] = lag.apply(lambda x: x.n if pd.notna(x) else np.nan)
    out["R2"] = out["rev_lag_months"] >= R2_STALE_MONTHS
    return out


def check_price_windows(px: pd.DataFrame, as_of: str) -> pd.DataFrame:
    """V1 PE 樣本 / H1 52週窗 / A1 ADV 集中度 / P1 缺交易日。"""
    px = px[px["date"] <= as_of]
    market_days = sorted(px["date"].unique())[-P1_MIN_TRADE_DAYS:]
    mdays = set(market_days)
    g = px.groupby("stock_id")

    pe = px[px["date"] >= PE_HISTORY_START]
    pe_obs = pe.groupby("stock_id")["PER_TSE"].apply(lambda s: int((s.dropna() > 0).sum()))

    closes240 = g["close"].apply(lambda s: int(s.tail(240).notna().sum()))

    def _adv_share(sub: pd.DataFrame) -> float:
        dv = (sub["close"] * sub["Trading_Volume"]).tail(20).dropna()
        tot = dv.sum()
        return float(dv.max() / tot) if tot > 0 and len(dv) else np.nan

    adv_share = g[["close", "Trading_Volume"]].apply(_adv_share)
    traded = g["date"].apply(lambda s: int(len(mdays & set(s))))

    out = pd.DataFrame({
        "pe_obs_since2019": pe_obs,
        "closes_in_240": closes240,
        "adv20_max_day_share": adv_share,
        "traded_days_last20": traded,
    })
    # 樣本越薄旗越該掛,0 筆是最薄的一種——不得因「反正 value_ind 會是 NaN」而豁免:
    # value_ind_pct 來自 industry_value_ref,不是這裡的 PE 觀測,兩者可以一有一無。
    out["V1"] = out["pe_obs_since2019"] < V1_MIN_PE_OBS
    out["H1"] = out["closes_in_240"] < H1_MIN_CLOSES
    out["A1"] = out["adv20_max_day_share"] > A1_MAX_DAY_SHARE
    out["P1"] = out["traded_days_last20"] < P1_MIN_TRADE_DAYS
    return out


def resolve_targets(args, pool: pd.DataFrame) -> tuple[list, str]:
    """回傳 (股票代號清單, 來源說明)。"""
    if args.stocks:
        return [s.strip() for s in args.stocks.split(",") if s.strip()], "--stocks 指定"
    if args.from_ledger:
        p = Path(args.from_ledger)
        led = json.loads(p.read_text(encoding="utf-8"))
        return [o["stock_id"] for o in led["orders"]], f"ledger {p.name}"
    if args.all:
        return pool.index.tolist(), f"全池 {len(pool)} 檔"
    cut = int(len(pool) * 0.20)
    top = pool.sort_values("c2_score_full", ascending=False).head(cut)
    return top.index.tolist(), f"c2 Top-20%({cut} 檔)"


def main() -> int:
    ap = argparse.ArgumentParser(description="訊號可信度稽核(逐檔輸入有效性,不是選股)")
    ap.add_argument("--as-of", default=None, help="稽核基準日 (預設:最新可用 c2 全池凍結件)")
    ap.add_argument("--stocks", default=None, help="逗號分隔的股票代號")
    ap.add_argument("--from-ledger", default=None, help="讀 L4a OrderIntent JSON 取名單")
    ap.add_argument("--all", action="store_true", help="稽核 c2 全池")
    ap.add_argument("--out-dir", default=str(POOL_DIR))
    args = ap.parse_args()

    pools = sorted(POOL_DIR.glob("c2_fullpool_*.csv"))
    if not pools:
        print("[ABORT] 找不到 c2_fullpool_*.csv,請先跑 universe_screen_daily.py", file=sys.stderr)
        return 2
    if args.as_of:
        pf = POOL_DIR / f"c2_fullpool_{args.as_of}.csv"
        if not pf.exists():
            print(f"[ABORT] 無 {pf.name}", file=sys.stderr)
            return 2
    else:
        pf = pools[-1]
    as_of = pf.stem.replace("c2_fullpool_", "")

    pool = pd.read_csv(pf, encoding="utf-8-sig")
    pool["stock_id"] = pool["stock_id"].astype(str)
    pool = pool.set_index("stock_id")

    targets, src = resolve_targets(args, pool)
    print(f"稽核基準日 {as_of}｜名單來源:{src}｜{len(targets)} 檔")

    con = duckdb.connect()
    px = load_price_union(con)
    px["stock_id"] = px["stock_id"].astype(str)
    if px["date"].max() < as_of:
        print(f"[ABORT] 價格聯集最新 {px['date'].max()} 早於 as_of={as_of}——"
              f"以陳舊價格稽核會給出假的通過,拒絕執行。", file=sys.stderr)
        return 2

    rev = check_revenue(con, as_of)
    rev.index = rev.index.astype(str)
    win = check_price_windows(px, as_of)
    win.index = win.index.astype(str)

    r = pd.DataFrame(index=pd.Index(targets, name="stock_id"))
    r["name"] = pool["name"].reindex(r.index)
    r["c2_score_full"] = pool["c2_score_full"].reindex(r.index)
    # L1:c2 四腿任一缺失 → c2_score_full 是部分平均,與四腿分數不同尺
    legs = pool[list(C2_LEGS)].reindex(r.index)
    r["c2_legs_present"] = 4 - legs.isna().sum(axis=1)
    r["L1"] = r["c2_legs_present"] < 4

    for col in ["rev_month", "rev_base", "rev_self_median13", "rev_base_ratio",
                "rev_lag_months", "R0", "R1", "R2"]:
        r[col] = rev[col].reindex(r.index)
    for col in ["pe_obs_since2019", "closes_in_240", "adv20_max_day_share",
                "traded_days_last20", "V1", "H1", "A1", "P1"]:
        r[col] = win[col].reindex(r.index)

    # X0 fail-closed:目標檔完全查不到來源(不在評分池 / 不在價格聯集 / 營收快取無列)。
    # 這些情況下其他旗標的 NaN 會被 fillna(False) 洗成「通過」,必須先攔下來。
    r["X0"] = (r["c2_score_full"].isna() | r["pe_obs_since2019"].isna()
               | r["rev_month"].isna())

    codes = list(SEVERITY)
    for c in codes:
        r[c] = r[c].fillna(False).astype(bool)
    r["flags"] = r[codes].apply(lambda row: ";".join(c for c in codes if row[c]), axis=1)
    r["n_flags"] = r[codes].sum(axis=1)
    r["severity"] = r[codes].apply(
        lambda row: next((s for s in ("HIGH", "MED", "LOW")
                          if any(row[c] and SEVERITY[c] == s for c in codes)), "OK"), axis=1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"signal_integrity_{as_of}.csv"
    r.sort_values(["severity", "n_flags"], ascending=[True, False]).to_csv(
        out, encoding="utf-8-sig")

    n = len(r)
    print(f"\n{'旗標':<6}{'說明':<26}{'嚴重度':<8}{'命中'}")
    for c in codes:
        k = int(r[c].sum())
        print(f"{c:<6}{FLAG_DESC[c]:<26}{SEVERITY[c]:<8}{k:>3} / {n}")
    print(f"\n嚴重度分布:{r['severity'].value_counts().to_dict()}")

    flagged = r[r["n_flags"] > 0].sort_values(["severity", "n_flags"], ascending=[True, False])
    if len(flagged):
        print(f"\n== 被標記的 {len(flagged)} 檔(證據值)==")
        for sid, row in flagged.iterrows():
            ev = []
            if row["X0"]:
                miss = [n for n, ok in [("評分池", pd.notna(row["c2_score_full"])),
                                        ("價格聯集", pd.notna(row["pe_obs_since2019"])),
                                        ("營收快取", pd.notna(row["rev_month"]))] if not ok]
                ev.append(f"查無來源:{'、'.join(miss)}——其餘檢查不成立")
            if row["R0"]:
                ev.append("有 yoy 值但基期算不出來(基期或自身中位數缺)")
            if row["R1"]:
                ev.append(f"基期={row['rev_base']:,.0f} 為自身中位 {row['rev_base_ratio']:.4f} 倍")
            if row["R2"]:
                ev.append(f"營收月落後 {row['rev_lag_months']:.0f} 個月({row['rev_month']})")
            if row["L1"]:
                ev.append(f"c2 只有 {row['c2_legs_present']:.0f} 腿")
            if row["V1"]:
                ev.append(f"PE 觀測 {row['pe_obs_since2019']:.0f} 筆")
            if row["H1"]:
                ev.append(f"240日內收盤 {row['closes_in_240']:.0f} 筆")
            if row["A1"]:
                ev.append(f"單日佔 ADV20 {row['adv20_max_day_share']*100:.1f}%")
            if row["P1"]:
                ev.append(f"近20交易日只成交 {row['traded_days_last20']:.0f} 天")
            print(f"  [{row['severity']:<4}] {sid} {row['name']}  c2={row['c2_score_full']:.2f}"
                  f"  {row['flags']}")
            for e in ev:
                print(f"           · {e}")
    else:
        print("\n沒有任何檔被標記。")

    print(f"\n→ {out}")
    print("\n提醒:本報告只說明「分數的輸入是否有效」,不含任何報酬預期。"
          "\n      被標記 = 值得人工覆核,不等於該賣;未標記 = 輸入健康,不等於該買。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
