"""
綜合分快取層 (scores) — 把五維綜合分物化,支援 DuckDB 跨股排名選股
================================================================================
定位:位於 data_cache (原始 Parquet 快取) 之上的「派生快取」。

  原始層 (core.data_cache)   唯讀原始歷史,0 API
        │  build_pit_stockdata(as_of)  → StockData  (PIT,無未來函數)
        │  FundamentalEngine / ValuationEngine / ScoringManager / InvestmentAdvisor
        ▼
  本層 (core.score_store)    每檔每日每模式一列 composite → Scores/<stock_id>.parquet
        │  data_cache.tbl('Scores') + duck_query()
        ▼
  查詢層 (DuckDB)            latest_scores() / screen_by_composite() 跨股排名

原則:
  · 本模組「不重算分數」。評分邏輯完全複用 ScoringManager + InvestmentAdvisor,
    與 core.backtest._score_one 是同一套 pipeline —— 這裡只負責「落地 + 查詢」。
  · composite 是『模式相依』的 (三個 mode 權重不同) → 每列存 mode;同一張表用 mode 欄區分,
    不拆三張表。查詢時 WHERE mode = '<mode>' 即可。
  · 每列附 weights_version (對 MODES[mode] 取雜湊):一旦權重改版,可辨識哪些歷史列該重算。
  · 儲存沿用 data_cache 的 _ParquetStore:每檔一個 Parquet、append-only、去重鍵 (as_of, mode)。
  · 跨股排名只在「已建 scores 的名單 (universe)」內有意義;名單多大由呼叫端決定
    (觀察清單 → 清單內挑時機;全市場 → 大海撈針)。原始資料已在本機,建 scores 為 0 API。
================================================================================
"""
from __future__ import annotations

import glob as _glob
import json
import hashlib
import logging
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from core import data_cache
from core.backtest import cached_fetch_history, build_pit_stockdata, HistoryBundle, load_benchmark
from core.regime import classify_regime
from core.fundamentals import FundamentalEngine
from core.valuation import ValuationEngine
from core.scoring_manager import ScoringManager
from core.advisor import InvestmentAdvisor

logger = logging.getLogger(__name__)

# 派生資料集名稱:沿用 data_cache 的 <CACHE_DIR>/<dataset>/<stock_id>.parquet 慣例。
DATASET = "Scores"
# 每檔 Parquet 內的去重鍵:同一檔同一天同一模式只留最後一次 (重跑當日覆蓋)。
_DEDUP_KEYS = ["as_of", "mode"]

# scores 一列的欄位順序 (寫檔 / 查詢皆以此為準)。
COLUMNS = [
    "as_of", "stock_id", "name", "mode",
    "composite", "rating",
    "fundamental", "valuation", "technical", "momentum", "whale",
    "valuation_status", "quality_flag",
    "price", "sector", "data_confidence",
    "dyn_weight", "regime", "weights_version", "built_at",
]


# ------------------------------------------------------------------------------
# 引擎與版本
# ------------------------------------------------------------------------------
def _engines(mode: str) -> Tuple[FundamentalEngine, ValuationEngine, ScoringManager, InvestmentAdvisor]:
    """建一套與 core.backtest.Backtester.__init__ 完全相同的評分引擎 (指定模式)。"""
    _check_mode(mode)
    cfg = ScoringManager.MODES[mode]
    return (
        FundamentalEngine(),
        ValuationEngine(),
        ScoringManager(mode=mode),
        InvestmentAdvisor(
            min_score=cfg["min_score"],
            mode_weights=cfg.get("composite_weights"),
            mode_name=mode,
        ),
    )


def _weights_version(mode: str) -> str:
    """對 MODES[mode] 的權重/門檻取短雜湊。權重改版 → 版本變 → 可辨識該重算的歷史列。"""
    cfg = ScoringManager.MODES[mode]
    payload = json.dumps(
        {
            "weights": cfg.get("weights"),
            "composite_weights": cfg.get("composite_weights"),
            "min_score": cfg.get("min_score"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:10]


def _check_mode(mode: str) -> None:
    if mode not in ScoringManager.MODES:
        raise ValueError(f"未知模式 {mode!r};可用:{list(ScoringManager.MODES)}")


# ------------------------------------------------------------------------------
# 市場 Regime (與回測同一套):用 0050 快取逐 as_of 判多空,空頭時 scores 自動轉防守權重。
#   基準快取缺 0050 → 一律回 None (advisor 不調整),不影響建庫。
# ------------------------------------------------------------------------------
_REGIME_BENCHMARK = "0050"
_bench_state: dict = {"bundle": None, "tried": False}
_regime_by_asof: Dict[str, Optional[str]] = {}


def _regime_at(as_of: Optional[str]) -> Optional[str]:
    if not as_of:
        return None
    if not _bench_state["tried"]:
        _bench_state["tried"] = True
        try:
            b = load_benchmark(_REGIME_BENCHMARK)
            if b is not None and getattr(b, "price", None) is not None and not b.price.empty:
                _bench_state["bundle"] = b
        except Exception as e:
            logger.warning(f"regime 基準 {_REGIME_BENCHMARK} 載入失敗,scores 以中性權重建庫: {e}")
    if _bench_state["bundle"] is None:
        return None
    key = str(as_of)
    if key not in _regime_by_asof:
        _regime_by_asof[key] = classify_regime(_bench_state["bundle"].price, key)
    return _regime_by_asof[key]


def _f(x) -> Optional[float]:
    """安全轉 float (None / 轉不動 → None)。"""
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------
# 核心:算一列 (複用評分 pipeline;等同 backtest._score_one 的輸出,轉成 scores 列)
# ------------------------------------------------------------------------------
def score_row(bundle: HistoryBundle, as_of: str, mode: str, engines=None) -> Optional[dict]:
    """
    以 as_of 為基準,對單一 bundle 跑完整評分 pipeline,回傳一列 scores dict (失敗回 None)。
    pipeline 與 core.backtest._score_one 一致:
        build_pit_stockdata → fund.evaluate → val.evaluate → scorer.calculate_score → advisor.advise
    advise 之後 score.total_score 即『五維綜合分』(已含動態權重),為跨股排名主鍵。
    """
    fund, val, scorer, advisor = engines or _engines(mode)
    stock = build_pit_stockdata(bundle, as_of)
    if stock is None:
        return None
    try:
        fund_res = fund.evaluate(vars(stock))
        val_res = val.evaluate(vars(stock))
        score = scorer.calculate_score(stock)
        advisor.current_regime = _regime_at(as_of)        # 與回測同步:空頭自動轉防守權重
        advisor.advise(stock, fund_res, val_res, score)   # in-place 補齊 composite/rating/五維
    except Exception as e:
        logger.warning(f"[{bundle.symbol}] {as_of} {mode} 評分失敗: {e}")
        return None

    return {
        "as_of": str(as_of),
        "stock_id": str(bundle.symbol),
        "name": getattr(bundle, "name", None) or str(bundle.symbol),
        "mode": mode,
        "composite": _f(score.total_score),
        "rating": score.rating,
        "fundamental": _f(fund_res.get("total_score")),
        "valuation": _f(score.valuation_score),
        "technical": _f(score.technical_score),
        "momentum": _f(score.momentum_score),
        "whale": _f(score.whale_score),
        "valuation_status": score.valuation_status,
        "quality_flag": score.quality_flag,
        "price": _f(stock.current_price),
        "sector": getattr(stock, "sector_category", ""),
        "data_confidence": _f(score.data_confidence),
        "dyn_weight": bool(getattr(score, "_dynamic_weight", False)),
        "regime": advisor.current_regime or "neutral",
        "weights_version": _weights_version(mode),
        "built_at": pd.Timestamp.utcnow().isoformat(),
    }


# ------------------------------------------------------------------------------
# 落地:寫入 Scores/<stock_id>.parquet (append + 依 (as_of, mode) 去重,keep last)
# ------------------------------------------------------------------------------
def _write_rows(stock_id: str, rows: List[dict]) -> None:
    if not rows:
        return
    store = data_cache.get_store()
    new = pd.DataFrame(rows)
    old = store.read(DATASET, stock_id)
    combined = pd.concat([old, new], ignore_index=True) if old is not None else new
    if "as_of" in combined.columns:
        combined = combined.sort_values(["as_of", "mode"])
    keys = [k for k in _DEDUP_KEYS if k in combined.columns]
    combined = combined.drop_duplicates(subset=keys or None, keep="last").reset_index(drop=True)
    # 欄位對齊 (容忍舊檔缺欄):補齊已知欄位並排序
    for c in COLUMNS:
        if c not in combined.columns:
            combined[c] = None
    ordered = [c for c in COLUMNS if c in combined.columns]
    extra = [c for c in combined.columns if c not in COLUMNS]
    store.write(DATASET, stock_id, combined[ordered + extra])


def _latest_as_of(bundle: HistoryBundle) -> Optional[str]:
    """bundle 最新可用交易日 (價格 date 的最大值);無價格回 None。"""
    df = getattr(bundle, "price", None)
    if df is None or "date" not in df.columns or df.empty:
        return None
    last = pd.to_datetime(df["date"], errors="coerce").max()
    return None if pd.isna(last) else str(last.date())


def _default_pool() -> List[str]:
    """預設 universe:沿用回測分散化測試池 (與 build_cache._load_pool 一致)。"""
    try:
        from tests.run_backtest import DIVERSIFIED_POOL
        return list(DIVERSIFIED_POOL)
    except Exception:
        return ["2330", "2454", "2317"]


# ------------------------------------------------------------------------------
# 建庫:對一批股票 × 一批模式,算並落地 scores
# ------------------------------------------------------------------------------
def build_scores(symbols: Optional[Sequence[str]] = None,
                 modes: Optional[Sequence[str]] = None,
                 as_of: Optional[str] = None,
                 refresh: bool = False,
                 names: Optional[Dict[str, str]] = None) -> int:
    """
    對 symbols × modes 計算五維綜合分並落地成 Scores 快取。回傳寫入的列數。
      · symbols:預設分散化測試池 (universe = 排名比較的母體)。
      · modes:  預設全部三個模式 (balanced / conservative / aggressive);想只建一個傳 ["balanced"]。
      · as_of:  評分基準日;預設用每檔『最新可用交易日』(各檔可能不同)。
      · refresh:True → 先對各資料集補抓增量再算 (會用 API);False (預設) → 純讀本機快取 (0 API)。
    """
    symbols = list(symbols) if symbols else _default_pool()
    modes = list(modes) if modes else list(ScoringManager.MODES.keys())
    for m in modes:
        _check_mode(m)
    names = names or {}
    eng = {m: _engines(m) for m in modes}

    total = 0
    skipped: List[str] = []
    n = len(symbols)
    print(f"開始建 scores:{n} 檔 × {len(modes)} 模式 {modes}  快取:{data_cache.CACHE_DIR}/{DATASET}")
    for i, sym in enumerate(symbols, 1):
        bundle = cached_fetch_history(sym, refresh=refresh)
        # 名稱優先用傳入的對照表 (build_cache 從 watchlist.txt 解析),再退回 bundle 原名、最後才用代號。
        bundle.name = names.get(sym) or getattr(bundle, "name", "") or sym
        aod = as_of or _latest_as_of(bundle)
        if aod is None:
            skipped.append(sym)
            print(f"  [{i}/{n}] {sym}  ⚠️ 無價格快取,略過 (先跑 build_cache.py 建原始快取)")
            continue
        rows = [r for r in (score_row(bundle, aod, m, eng[m]) for m in modes) if r]
        _write_rows(sym, rows)
        total += len(rows)
        if rows:
            comps = " / ".join(f"{r['mode'][:4]}:{r['composite']:.0f}" for r in rows)
            print(f"  [{i}/{n}] {sym} @ {aod}  {len(rows)} 列  ({comps})")
        else:
            print(f"  [{i}/{n}] {sym} @ {aod}  0 列 (資料不足)")

    print(f"\n✅ scores 完成:寫入 {total} 列。"
          + (f" 略過 {len(skipped)} 檔:{skipped}" if skipped else ""))
    print("   排名查詢:python build_cache.py --screen-composite   或   "
          "core.score_store.screen_by_composite(mode='balanced')")
    return total


# ------------------------------------------------------------------------------
# 查詢層:DuckDB 對 Scores 做跨股排名 (本模組不算分,只排序/篩選已落地的分)
# ------------------------------------------------------------------------------
_SELECT_COLS = (
    "stock_id, name, as_of, mode, composite, rating, "
    "fundamental, valuation, technical, momentum, whale, "
    "valuation_status, quality_flag, price, sector, data_confidence, dyn_weight"
)


def _has_scores() -> bool:
    """Scores 快取是否已有任何 Parquet (避免對空 glob 查 DuckDB 噴 no-files 錯)。"""
    return bool(_glob.glob(data_cache.get_store().glob(DATASET)))


def cached_symbols(mode: Optional[str] = None) -> List[str]:
    """
    回傳 Scores 快取內出現過的股票代號 (排序後、去重)。
    供驗證腳本把 universe 對齊到『網頁選股實際排名的那批股票』。
      · mode=None:跨所有模式的聯集;指定 mode 則只取該模式有分數的股票。
      · 尚未建 scores → 空清單。
    """
    if mode is not None:
        _check_mode(mode)
    if not _has_scores():
        return []
    where = f"WHERE mode = '{mode}'" if mode else ""
    sql = f"SELECT DISTINCT stock_id FROM {data_cache.tbl(DATASET)} {where} ORDER BY stock_id"
    try:
        df = data_cache.duck_query(sql)
    except Exception as e:
        logger.warning(f"cached_symbols 查詢失敗: {e}")
        return []
    return [str(s) for s in df["stock_id"].tolist()]


def universe_info(mode: str = "balanced") -> Optional[dict]:
    """
    回傳該模式 scores 快取概況 (供 UI 顯示):
        {'stocks': 檔數, 'as_of': 最新基準日, 'weights_version': 權重版本}
    尚未建 scores 或該模式無資料 → None。
    """
    _check_mode(mode)
    if not _has_scores():
        return None
    sql = f"""
        WITH latest AS (
            SELECT *, row_number() OVER (PARTITION BY stock_id ORDER BY as_of DESC) AS _rn
            FROM {data_cache.tbl(DATASET)}
            WHERE mode = '{mode}'
        )
        SELECT count(*) AS stocks, max(as_of) AS as_of, max(weights_version) AS weights_version
        FROM latest WHERE _rn = 1
    """
    try:
        df = data_cache.duck_query(sql)
    except Exception as e:
        logger.warning(f"universe_info 查詢失敗: {e}")
        return None
    if df.empty or int(df.iloc[0]["stocks"] or 0) == 0:
        return None
    row = df.iloc[0]
    return {
        "stocks": int(row["stocks"]),
        "as_of": str(row["as_of"]),
        "weights_version": str(row["weights_version"]),
    }


def latest_scores(mode: str = "balanced") -> pd.DataFrame:
    """指定模式下,每檔『最新一筆』綜合分,依 composite 由高到低。無快取回空表。"""
    _check_mode(mode)
    if not _has_scores():
        return pd.DataFrame()
    sql = f"""
        WITH latest AS (
            SELECT *, row_number() OVER (PARTITION BY stock_id ORDER BY as_of DESC) AS _rn
            FROM {data_cache.tbl(DATASET)}
            WHERE mode = '{mode}'
        )
        SELECT {_SELECT_COLS}
        FROM latest
        WHERE _rn = 1
        ORDER BY composite DESC
    """
    return data_cache.duck_query(sql)


def screen_by_composite(mode: str = "balanced",
                        min_composite: Optional[float] = None,
                        ratings: Optional[Sequence[str]] = None,
                        min_confidence: Optional[float] = None,
                        top: int = 30) -> pd.DataFrame:
    """
    跨股綜合分排名選股 (讀 Scores 快取)。
      · min_composite:綜合分下限 (常用 = ScoringManager.MODES[mode]['min_score'])。
      · ratings:      限定評級,如 ['強勢買進','強烈推薦']。
      · min_confidence:資料完整度下限。
      · 另附 pct_rank:該檔綜合分在此 universe 內的橫斷面百分位 (0-100,越高越前面)。
      · 尚未建 scores 快取 → 回空表 (呼叫端據此提示先跑 build_cache.py --build-scores)。
    """
    _check_mode(mode)
    if not _has_scores():
        return pd.DataFrame()
    conds: List[str] = []
    if min_composite is not None:
        conds.append(f"composite >= {float(min_composite)}")
    if min_confidence is not None:
        conds.append(f"data_confidence >= {float(min_confidence)}")
    if ratings:
        vals = ", ".join("'" + str(r).replace("'", "") + "'" for r in ratings)
        conds.append(f"rating IN ({vals})")
    where = (" AND " + " AND ".join(conds)) if conds else ""

    sql = f"""
        WITH latest AS (
            SELECT *, row_number() OVER (PARTITION BY stock_id ORDER BY as_of DESC) AS _rn
            FROM {data_cache.tbl(DATASET)}
            WHERE mode = '{mode}'
        ),
        ranked AS (
            SELECT *, percent_rank() OVER (ORDER BY composite) AS _pct
            FROM latest WHERE _rn = 1
        )
        SELECT stock_id, name, as_of, composite,
               ROUND(_pct * 100, 1) AS pct_rank,
               rating, fundamental, valuation, technical, momentum, whale,
               valuation_status, data_confidence, dyn_weight
        FROM ranked
        WHERE TRUE{where}
        ORDER BY composite DESC
        LIMIT {int(top)}
    """
    return data_cache.duck_query(sql)
