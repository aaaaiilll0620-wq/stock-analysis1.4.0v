import sys
import os
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from FinMind.data import DataLoader
from core.models import StockData
from core.technical_analysis import TechnicalEngine
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# TEJ 本機歷史庫 (tej_importer.py 匯入的 Parquet;與 finmind_cache 分開存放)
TEJ_CACHE_DIR = os.environ.get("TEJ_CACHE", os.path.join(os.path.expanduser("~"), "tej_cache"))

class DataProvider:
    # 使用 SDK 初始化一次,避免重複建立連接
    _api = DataLoader()
    _tech_engine = TechnicalEngine()
    _logged_in = False
    _name_map: Optional[dict] = None
    _industry_map: Optional[dict] = None       # 產業別一次性快取 {stock_id: industry_category}

    @classmethod
    def _stabilize_price_scale(cls, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        價格尺度穩定器:
        若最新一天出現「單日極端跳價」且與前 20 日尺度明顯脫節,視為未確認的新尺度,
        暫以前一日尺度回推最後一根 K 棒,避免成本區/支撐壓力被單點資料扭曲。
        不增加任何 API 呼叫。
        """
        if price_df is None or price_df.empty or "close" not in price_df.columns:
            return price_df
        d = price_df.copy()
        if "date" in d.columns:
            d = d.sort_values("date").reset_index(drop=True)
        close = pd.to_numeric(d["close"], errors="coerce")
        if len(close) < 25 or pd.isna(close.iloc[-1]) or pd.isna(close.iloc[-2]):
            return d
        curr = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        if curr <= 0 or prev <= 0:
            return d
        ratio = curr / prev
        extreme_gap = (ratio < 0.40) or (ratio > 2.50)
        base = pd.to_numeric(close.iloc[-21:-1], errors="coerce").dropna()
        if base.empty:
            return d
        base_med = float(base.median())
        off_regime = abs(curr - base_med) / max(base_med, 1e-9) > 0.60
        if not (extreme_gap and off_regime):
            return d

        bridge = prev / curr
        px_cols = [c for c in ("close", "open", "max", "min", "high", "low") if c in d.columns]
        for c in px_cols:
            v = pd.to_numeric(pd.Series([d.at[len(d) - 1, c]]), errors="coerce").iloc[0]
            if pd.notna(v):
                d.at[len(d) - 1, c] = float(v) * bridge
        logger.warning(
            f"[price_scale_guard] latest bar extreme gap detected (ratio={ratio:.4f}); "
            f"temporarily bridged last bar to previous scale for stability"
        )
        return d

    # ------------------------------------------------------------------
    # 登入管理
    # ------------------------------------------------------------------
    @classmethod
    def login(cls, token: str):
        """外部顯式登入(main.py 傳 token 時使用)"""
        if token:
            cls._api.login_by_token(api_token=token)
            cls._logged_in = True

    @classmethod
    def _ensure_login(cls):
        """
        【修正】原本主流程完全沒有登入 FinMind:main.py 的 Config.FINMIND_TOKEN 預設
        為空字串,而 config.py 的 fm 物件又沒被主流程 import,導致 data_provider 的
        _api 一直是匿名狀態(每日額度極低,大量呼叫會被擋)。這裡改為自動從 .env
        讀取 FINMIND_TOKEN 登入,找不到時明確警告。
        """
        if cls._logged_in:
            return
        load_dotenv()
        token = os.getenv("FINMIND_TOKEN")
        if token:
            try:
                cls._api.login_by_token(api_token=token)
                cls._logged_in = True
                logger.info("FinMind 登入成功 (透過 .env FINMIND_TOKEN)")
            except Exception as e:
                logger.warning(f"FinMind 登入失敗,將以匿名模式呼叫(額度受限): {e}")
        else:
            logger.warning("未找到 FINMIND_TOKEN,將以匿名模式呼叫 FinMind(每日額度受限)")
        # 讀寫穿透快取:把 _api 包一層,之後所有查詢 (回測 / 個股分析) 自動落地並重用本機快取。
        try:
            from core import data_cache
            if data_cache.CACHE_ENABLED:
                cls._api = data_cache.install(cls._api)
                logger.info(f"已啟用本機快取代理 (FINMIND_CACHE={data_cache.CACHE_DIR})")
        except Exception as e:
            logger.warning(f"本機快取代理啟用失敗,改用直連 (不影響功能): {e}")

    # ------------------------------------------------------------------
    # 股票名稱對照(修正 name=symbol 問題)
    # ------------------------------------------------------------------
    @classmethod
    def _get_name(cls, symbol: str) -> str:
        if cls._name_map is None:
            try:
                info = cls._api.get_data(dataset='TaiwanStockInfo')
                if info is not None and not info.empty and 'stock_id' in info.columns:
                    cls._name_map = dict(zip(info['stock_id'].astype(str), info['stock_name']))
                else:
                    cls._name_map = {}
            except Exception as e:
                logger.warning(f"無法取得股票名稱對照表: {e}")
                cls._name_map = {}
        return cls._name_map.get(str(symbol), symbol)

    # ------------------------------------------------------------------
    # 籌碼:連續買超 / 賣超天數(通用版)
    # ------------------------------------------------------------------
    @classmethod
    def _calculate_consecutive_streak(cls, df: pd.DataFrame, buy_col: str,
                                      sell_col: str, direction: str = "buy") -> int:
        """
        在記憶體內用 Pandas 計算連續買超或賣超天數。

        direction="buy"  → 淨買賣超 (buy - sell) > 0 才累加
        direction="sell" → 淨買賣超 (buy - sell) < 0 才累加

        買超與賣超互斥:同一檔股票最新一天只會落在其中一邊(或持平為 0),
        所以連買 0 天不代表沒事,可能正在連賣 —— 這也是本次新增賣超天數的原因。

        另外外資 name 可能同時包含 'Foreign_Investor' 與 'Foreign_Dealer_Self',
        同一天兩筆,故先依日期 groupby 加總,保證一天只算一筆。
        """
        if df is None or df.empty or buy_col not in df.columns or sell_col not in df.columns:
            return 0

        df_copy = df.copy()
        try:
            df_copy['date'] = pd.to_datetime(df_copy['date'])
        except Exception as e:
            logger.warning(f"籌碼日期轉換失敗: {e}")
            return 0

        for col in (buy_col, sell_col):
            df_copy[col] = pd.to_numeric(
                df_copy[col].astype(str).str.replace(',', ''), errors='coerce'
            ).fillna(0)

        daily = df_copy.groupby('date', as_index=False)[[buy_col, sell_col]].sum()
        daily['net'] = daily[buy_col] - daily[sell_col]
        daily_sorted = daily.sort_values('date', ascending=False)

        streak = 0
        for _, row in daily_sorted.iterrows():
            net = row['net']
            if direction == "buy" and net > 0:
                streak += 1
            elif direction == "sell" and net < 0:
                streak += 1
            else:
                # 最新一天方向不符即刻中斷
                break
        return streak

    # ------------------------------------------------------------------
    # 財報數值萃取工具(同時支援英文 type 與中文 origin_name)
    # ------------------------------------------------------------------
    @classmethod
    def _latest_value(cls, df: Optional[pd.DataFrame],
                      type_keys: List[str], name_keys: Optional[List[str]] = None) -> Optional[float]:
        """
        從 FinMind 財報 DataFrame (欄位: date, stock_id, type, value, origin_name)
        取出指定科目「最新一期」的數值。先比對英文 type,對不上再用中文 origin_name
        做子字串比對,兩者都找不到就回傳 None(讓上層知道真的缺資料,而非硬填假值)。
        """
        if df is None or df.empty:
            return None

        sub = pd.DataFrame()
        if 'type' in df.columns:
            sub = df[df['type'].isin(type_keys)]
        if sub.empty and name_keys and 'origin_name' in df.columns:
            mask = df['origin_name'].astype(str).apply(lambda s: any(k in s for k in name_keys))
            sub = df[mask]
        if sub.empty:
            return None

        if 'date' in sub.columns:
            sub = sub.sort_values('date')
        try:
            raw = sub.iloc[-1]['value']
            return float(str(raw).replace(',', ''))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # TEJ 本機資料 (月營收 / 三大財報):新鮮度夠就用本機,過期退回 FinMind
    # ------------------------------------------------------------------
    @staticmethod
    def _read_tej(dataset: str, symbol: str) -> Optional[pd.DataFrame]:
        """讀 tej_cache/<dataset>/<symbol>.parquet;無檔或壞檔回 None (由上層 fallback)。"""
        p = os.path.join(TEJ_CACHE_DIR, dataset, f"{symbol}.parquet")
        if not os.path.exists(p):
            return None
        try:
            df = pd.read_parquet(p)
            return df if not df.empty else None
        except Exception as e:
            logger.warning(f"[{symbol}] TEJ {dataset} 讀取失敗,退回 FinMind: {e}")
            return None

    @classmethod
    def _read_tej_monthly_revenue(cls, symbol: str) -> Optional[pd.DataFrame]:
        """
        本機 TEJ 月營收 → 補上 FinMind 慣例的 revenue_year / revenue_month 衍生欄,
        讓 _calc_rev_yoy / _calc_rev_momentum / _ttm_revenue 原封不動直接吃。
        新鮮度閘門:月營收次月 10 日前公告 → 最新月份若落後今天超過 70 天,
        代表本機庫漏了至少一個「已公告」的月份 → 回 None 改走 FinMind。
        """
        df = cls._read_tej("monthly_revenue", symbol)
        if df is None or "date" not in df.columns or "revenue" not in df.columns:
            return None
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date")
        if d.empty:
            return None
        if (datetime.now() - d["date"].iloc[-1]).days > 70:
            logger.info(f"[{symbol}] TEJ 月營收最新僅至 {d['date'].iloc[-1]:%Y-%m},過期改走 FinMind。")
            return None
        d["revenue_year"] = d["date"].dt.year
        d["revenue_month"] = d["date"].dt.month
        return d

    @classmethod
    def _fetch_fundamentals_tej(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """
        以本機 TEJ 三大財報 (financial_statements,單季 IFRS) 計算與 _fetch_fundamentals
        完全同一組欄位,0 FinMind API。無檔或過期回 None (由上層退回 FinMind 三支報表 API)。
        新鮮度閘門:財報公告期限 Q1=5/15、Q2=8/14、Q3=11/14、年報=3/31;
        「季末月標籤 → 下一季可取得」最大間隔約 166 天 (Q1 標籤 3/1 → Q2 公告 8/14),
        故最新一季標籤若落後今天超過 175 天,代表漏了已公告的季度 → 過期。
        """
        df = cls._read_tej("financial_statements", symbol)
        if df is None or "date" not in df.columns:
            return None
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date")
        if d.empty:
            return None
        if (datetime.now() - d["date"].iloc[-1]).days > 175:
            logger.info(f"[{symbol}] TEJ 財報最新僅至 {d['date'].iloc[-1]:%Y-%m},過期改走 FinMind。")
            return None

        def _v(row, col) -> Optional[float]:
            x = row.get(col)
            if x is None or pd.isna(x):
                return None
            return float(x)

        def _series(col) -> Optional[pd.DataFrame]:
            """(date, value) 時序,格式同 _value_series,供 _yoy_growth 直接使用。"""
            if col not in d.columns:
                return None
            out = d[["date", col]].rename(columns={col: "value"}).dropna(subset=["value"])
            return out if not out.empty else None

        q = d.iloc[-1]
        revenue = _v(q, "revenue")
        gross = _v(q, "gross_profit")
        op_income = _v(q, "operating_income")
        net_inc = _v(q, "net_income")
        total_assets = _v(q, "total_assets")
        total_liab = _v(q, "total_liabilities")
        curr_assets = _v(q, "current_assets")
        curr_liab = _v(q, "current_liabilities")
        equity = _v(q, "equity")
        ocf = _v(q, "operating_cash_flow")
        capex = _v(q, "capex")

        result: Dict[str, Optional[float]] = {
            "roe": None, "net_margin": None, "gross_margin": None,
            "debt_to_asset": None, "current_ratio": None,
        }
        extra: Dict[str, Any] = {
            "net_income": None, "net_income_growth": None, "eps_growth": None,
            "operating_income": None, "operating_profit_ratio": None,
            "gross_margin_trend": None,
            "operating_cash_flow": None, "capex": None,
            "free_cash_flow": None, "ocf_to_net_income": None,
            # TEJ 年月標籤為季末月 1 號 → 轉成季末「日」,與 FinMind 路徑口徑一致
            # (此欄供上層判斷「近期動能是否已領先財報」的時間差)
            "financials_asof": str((q["date"] + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")),
        }

        if revenue and gross is not None:
            result["gross_margin"] = gross / revenue * 100
        if revenue and net_inc is not None:
            result["net_margin"] = net_inc / revenue * 100
        if total_assets and total_liab is not None:
            result["debt_to_asset"] = total_liab / total_assets * 100
        if curr_liab and curr_assets is not None:
            result["current_ratio"] = curr_assets / curr_liab * 100
        if equity and net_inc is not None:
            result["roe"] = net_inc / equity * 100   # 近似 ROE(單季),同 FinMind 路徑
        if total_assets and revenue:
            extra["asset_turnover"] = revenue * 4.0 / total_assets

        # 毛利率季度趨勢:最新季 vs 前數季平均 (同 FinMind 路徑演算法)
        if "revenue" in d.columns and "gross_profit" in d.columns:
            m = d.dropna(subset=["revenue", "gross_profit"])
            m = m[m["revenue"] != 0]
            if len(m) >= 2:
                gm = (m["gross_profit"] / m["revenue"] * 100.0).tolist()
                prior = gm[-4:-1] if len(gm) >= 4 else gm[:-1]
                if prior:
                    extra["gross_margin_trend"] = float(gm[-1] - sum(prior) / len(prior))

        if op_income is not None:
            extra["operating_income"] = op_income
            if net_inc not in (None, 0):
                extra["operating_profit_ratio"] = float(op_income) / float(net_inc)
        if net_inc is not None:
            extra["net_income"] = net_inc
            extra["net_income_growth"] = cls._yoy_growth(_series("net_income"))
        eps_growth = cls._yoy_growth(_series("eps"))
        if eps_growth is None and extra["net_income_growth"] is not None:
            eps_growth = extra["net_income_growth"]
        extra["eps_growth"] = eps_growth

        if ocf is not None:
            extra["operating_cash_flow"] = ocf
        if capex is not None:
            extra["capex"] = capex
        if ocf is not None and capex is not None:
            extra["free_cash_flow"] = ocf + capex if capex < 0 else ocf - capex
        if ocf is not None and net_inc not in (None, 0):
            extra["ocf_to_net_income"] = ocf / net_inc

        logger.info(f"[{symbol}] 基本面走本機 TEJ 財報 (至 {extra['financials_asof']},0 API)。")
        return cls._finalize_fundamentals(symbol, result, extra)

    # ------------------------------------------------------------------
    # 真實基本面(修正:原版每檔股票都套用同一組寫死的假財務數據)
    # ------------------------------------------------------------------
    @classmethod
    def _value_series(cls, df: Optional[pd.DataFrame],
                      type_keys: List[str], name_keys: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        """
        回傳某科目跨期的 (date, value) 時序 (已依日期排序),供年增率 (YoY) 計算。
        找不到回傳 None。與 _latest_value 使用相同的英文 type / 中文 origin_name 雙比對。
        """
        if df is None or df.empty:
            return None
        sub = pd.DataFrame()
        if 'type' in df.columns:
            sub = df[df['type'].isin(type_keys)]
        if sub.empty and name_keys and 'origin_name' in df.columns:
            mask = df['origin_name'].astype(str).apply(lambda s: any(k in s for k in name_keys))
            sub = df[mask]
        if sub.empty or 'date' not in sub.columns:
            return None
        out = sub[['date', 'value']].copy()
        out['date'] = pd.to_datetime(out['date'], errors='coerce')
        out['value'] = pd.to_numeric(out['value'].astype(str).str.replace(',', ''), errors='coerce')
        out = out.dropna(subset=['date']).sort_values('date')
        return out if not out.empty else None

    @classmethod
    def _yoy_growth(cls, series: Optional[pd.DataFrame]) -> Optional[float]:
        """
        以「最新一期 vs 約一年前同期」計算年增率 (%)。
        台股財報多為 YTD 累計,故取最接近 (最新日期 - 365 天) 的那一期比對,方向正確即可。
        """
        if series is None or len(series) < 2:
            return None
        latest = series.iloc[-1]
        target = latest['date'] - pd.Timedelta(days=365)
        prior = series.iloc[:-1].copy()
        prior['gap'] = (prior['date'] - target).abs()
        cand = prior.sort_values('gap').iloc[0]
        # 只接受落在 ±60 天內的同期比對,避免拿季度亂比
        if cand['gap'] > pd.Timedelta(days=60):
            return None
        prev_val = cand['value']
        if prev_val is None or pd.isna(prev_val) or prev_val == 0:
            return None
        try:
            return float((latest['value'] - prev_val) / abs(prev_val) * 100.0)
        except Exception:
            return None

    @classmethod
    def _fetch_fundamentals(cls, symbol: str) -> Dict[str, Any]:
        """
        從損益表 + 資產負債表 + 現金流量表計算真實的獲利、安全、估值與現金流指標。
        無法解析的「比率型」欄位套用中性 fallback (避免流程中斷);
        「現金流/淨利年增率」等無法安全捏造的欄位則保持 None,並記入 missing 以降低信心分數。

        本方法只新增 1 支 API 呼叫 (現金流量表),淨利年增率沿用已抓的損益表計算,不額外耗 token。

        ⚠️ 已知限制:
          1. ROE 為「單季淨利 / 權益」近似值,非年化。
          2. 現金流量表 type/origin_name 版本間可能不同,若大量 fallback 警告,
             請印出實際 type 清單並補進下方 type_keys / name_keys。
        """
        # 本機優先:TEJ 三大財報有檔且新鮮 → 0 API 直接算完;否則走下面 FinMind 三支報表
        tej = cls._fetch_fundamentals_tej(symbol)
        if tej is not None:
            return tej

        result: Dict[str, Optional[float]] = {k: None for k in cls._NEUTRAL_FUND}
        # 非比率型欄位:缺就是缺,不套 fallback (交由 confidence 反映)
        extra: Dict[str, Optional[float]] = {
            "net_income": None, "net_income_growth": None,
            "eps_growth": None,                          # 真實 EPS 年增率 (YoY)
            "operating_income": None, "operating_profit_ratio": None,  # 本業獲利占比 (漏洞一)
            "gross_margin_trend": None,                  # 毛利率季度趨勢 (百分點,供增收是否增利)
            "operating_cash_flow": None, "capex": None,
            "free_cash_flow": None, "ocf_to_net_income": None,
            "financials_asof": None,                     # 財報資料截止日 (季報,供時間差判斷)
        }

        # ---- 損益表(季)----
        inc_df = None
        try:
            inc_df = cls._api.get_data(
                dataset='TaiwanStockFinancialStatements',
                data_id=symbol, start_date='2023-01-01'
            )
        except Exception as e:
            logger.warning(f"[{symbol}] 損益表抓取失敗: {e}")

        # 記錄財報資料截止日 (最新一筆 date),供上層判斷「近期動能是否已領先財報」
        try:
            if inc_df is not None and not inc_df.empty and 'date' in inc_df.columns:
                extra["financials_asof"] = str(inc_df['date'].astype(str).max())
        except Exception:
            pass

        revenue = cls._latest_value(inc_df, ['Revenue'], ['營業收入'])
        gross = cls._latest_value(inc_df, ['GrossProfit'], ['營業毛利'])
        op_income = cls._latest_value(inc_df, ['OperatingIncome'], ['營業利益'])
        net_keys = ['IncomeAfterTaxes', 'ProfitLossAttributableToOwnersOfParent', 'ProfitLoss']
        net_names = ['本期淨利', '綜合損益總額', '母公司業主']
        net_inc = cls._latest_value(inc_df, net_keys, net_names)

        if revenue and gross is not None:
            result["gross_margin"] = gross / revenue * 100

        # ---- 毛利率季度趨勢 (供「增收是否增利」交叉檢查) ----
        # 各季 毛利率 = 營業毛利 / 營業收入;取最新季 vs 前數季平均的差 (百分點,+升 −降)。
        try:
            rev_s = cls._value_series(inc_df, ['Revenue'], ['營業收入'])
            gp_s = cls._value_series(inc_df, ['GrossProfit'], ['營業毛利'])
            if rev_s is not None and gp_s is not None:
                merged = rev_s.merge(gp_s, on='date', suffixes=('_rev', '_gp'))
                merged = merged[merged['value_rev'] != 0]
                if len(merged) >= 2:
                    merged['gm'] = merged['value_gp'] / merged['value_rev'] * 100.0
                    gm_series = merged.sort_values('date')['gm'].tolist()
                    latest_gm = gm_series[-1]
                    prior = gm_series[-4:-1] if len(gm_series) >= 4 else gm_series[:-1]
                    if prior:
                        extra["gross_margin_trend"] = float(latest_gm - sum(prior) / len(prior))
        except Exception as e:
            logger.info(f"[{symbol}] 毛利率趨勢計算略過: {e}")

        if revenue and net_inc is not None:
            result["net_margin"] = net_inc / revenue * 100
        if op_income is not None:
            extra["operating_income"] = op_income
            # 本業獲利占比 = 營業利益 / 稅後淨利 (>=0.80 表獲利主要來自本業,供營運槓桿判斷)
            if net_inc not in (None, 0):
                extra["operating_profit_ratio"] = float(op_income) / float(net_inc)
        if net_inc is not None:
            extra["net_income"] = net_inc
            # 淨利年增率 (沿用已抓的 inc_df,零額外 API)
            extra["net_income_growth"] = cls._yoy_growth(cls._value_series(inc_df, net_keys, net_names))

        # ---- EPS 年增率 (YoY):沿用已抓的 inc_df,零額外 API ----
        # FinMind 損益表 EPS 科目:type 常見 'EPS' / 'BasicEarningsLossPerShare';
        # 中文 origin_name 常見 '基本每股盈餘' / '每股盈餘'。
        eps_keys = ['EPS', 'BasicEarningsLossPerShare', 'BasicEarningsPerShare']
        eps_names = ['基本每股盈餘', '每股盈餘', '每股稅後盈餘']
        eps_growth = cls._yoy_growth(cls._value_series(inc_df, eps_keys, eps_names))
        if eps_growth is None and extra["net_income_growth"] is not None:
            # 找不到 EPS 科目時,以淨利年增率作為近似 (股本變動不大時 EPS YoY ≈ 淨利 YoY)
            eps_growth = extra["net_income_growth"]
            logger.info(f"[{symbol}] 損益表無獨立 EPS 科目,EPS 年增率改以淨利年增率近似。")
        extra["eps_growth"] = eps_growth

        # ---- 資產負債表(季)----
        bs_df = None
        try:
            bs_df = cls._api.get_data(
                dataset='TaiwanStockBalanceSheet',
                data_id=symbol, start_date='2023-01-01'
            )
        except Exception as e:
            logger.warning(f"[{symbol}] 資產負債表抓取失敗: {e}")

        total_assets = cls._latest_value(bs_df, ['TotalAssets'], ['資產總計', '資產總額'])
        total_liab = cls._latest_value(bs_df, ['Liabilities', 'TotalLiabilities'], ['負債總計', '負債總額'])
        curr_assets = cls._latest_value(bs_df, ['CurrentAssets'], ['流動資產'])
        curr_liab = cls._latest_value(bs_df, ['CurrentLiabilities'], ['流動負債'])
        equity = cls._latest_value(
            bs_df,
            ['Equity', 'EquityAttributableToOwnersOfParent'],
            ['權益總計', '權益總額', '歸屬於母公司業主之權益']
        )

        if total_assets and total_liab is not None:
            result["debt_to_asset"] = total_liab / total_assets * 100
        if curr_liab and curr_assets is not None:
            result["current_ratio"] = curr_assets / curr_liab * 100
        if equity and net_inc is not None:
            result["roe"] = net_inc / equity * 100  # 近似 ROE(單季)
        # 總資產週轉率 (v4.4):年化季營收 ÷ 總資產,與回測 PIT 同一套算法
        if total_assets and revenue:
            extra["asset_turnover"] = revenue * 4.0 / total_assets

        # ---- 現金流量表(季)---- 只多這一支 API
        cf_df = None
        try:
            cf_df = cls._api.get_data(
                dataset='TaiwanStockCashFlowsStatement',
                data_id=symbol, start_date='2023-01-01'
            )
        except Exception as e:
            logger.warning(f"[{symbol}] 現金流量表抓取失敗: {e}")

        ocf = cls._latest_value(
            cf_df,
            ['CashFlowsProvidedFromUsedInOperatingActivities',
             'NetCashProvidedByUsedInOperatingActivities',
             'CashProvidedByUsedInOperatingActivities'],
            ['營業活動之淨現金流', '營業活動之現金流量', '營業活動現金流']
        )
        # 資本支出:取得不動產、廠房及設備 (報表上多為負值的流出)
        capex = cls._latest_value(
            cf_df,
            ['AcquisitionOfPropertyPlantAndEquipment',
             'PaymentsToAcquirePropertyPlantAndEquipment',
             'PropertyAndPlantAndEquipment'],
            ['取得不動產、廠房及設備', '購置不動產、廠房及設備', '取得不動產廠房及設備']
        )
        if ocf is not None:
            extra["operating_cash_flow"] = ocf
        if capex is not None:
            extra["capex"] = capex
        if ocf is not None and capex is not None:
            # capex 若已是負流出則 FCF = OCF + capex;若抓到的是正絕對值則 FCF = OCF - capex
            extra["free_cash_flow"] = ocf + capex if capex < 0 else ocf - capex
        if ocf is not None and net_inc not in (None, 0):
            try:
                extra["ocf_to_net_income"] = ocf / net_inc
            except Exception:
                pass

        return cls._finalize_fundamentals(symbol, result, extra)

    # 比率型欄位的中性 fallback 值 (TEJ 與 FinMind 兩條路徑共用)
    _NEUTRAL_FUND = {
        "roe": 12.0, "net_margin": 10.0, "gross_margin": 25.0,
        "debt_to_asset": 45.0, "current_ratio": 150.0,
    }

    @classmethod
    def _finalize_fundamentals(cls, symbol: str, result: Dict[str, Optional[float]],
                               extra: Dict[str, Any]) -> Dict[str, Any]:
        """比率型欄位套中性 fallback、非比率型保持真實 (含 None),並回傳缺漏清單。"""
        final: Dict[str, Any] = {}
        missing = []
        for k, v in result.items():
            if v is None:
                final[k] = cls._NEUTRAL_FUND[k]
                missing.append(k)
            else:
                final[k] = round(float(v), 2)
        if missing:
            logger.warning(f"[{symbol}] 以下基本面比率欄位無法解析,已套用中性 fallback: {missing}")

        # 非比率型欄位:保持真實 (含 None),數值四捨五入;字串型 (如財報截止日) 原樣保留
        cf_missing = [k for k, v in extra.items() if v is None]
        for k, v in extra.items():
            if v is None:
                final[k] = None
            elif isinstance(v, str):
                final[k] = v
            else:
                final[k] = round(float(v), 2)
        if cf_missing:
            logger.warning(f"[{symbol}] 以下現金流/成長欄位無法解析 (將降低信心分數): {cf_missing}")

        # 回傳缺漏清單供上層計算 data_confidence
        final["_missing_fields"] = missing + cf_missing
        return final

    @classmethod
    def _calc_rev_yoy(cls, rev_df: Optional[pd.DataFrame]) -> float:
        """
        計算月營收年增率 (YoY)。
        【修正】原版檢查 'revenue_year_growth' 欄位,但 FinMind TaiwanStockMonthRevenue
        並沒有這個欄位,導致年增率永遠回傳 0。改為用 revenue_year / revenue_month
        對齊「去年同月」自行計算。
        """
        if rev_df is None or rev_df.empty or 'revenue' not in rev_df.columns:
            return 0.0
        if 'revenue_year' not in rev_df.columns or 'revenue_month' not in rev_df.columns:
            return 0.0

        df = rev_df.copy().sort_values(['revenue_year', 'revenue_month'])
        latest = df.iloc[-1]
        ry, rm, rev_now = latest['revenue_year'], latest['revenue_month'], latest['revenue']
        prev = df[(df['revenue_year'] == ry - 1) & (df['revenue_month'] == rm)]
        if prev.empty or not rev_now:
            return 0.0
        rev_prev = prev.iloc[-1]['revenue']
        if not rev_prev:
            return 0.0
        try:
            return float((rev_now - rev_prev) / rev_prev * 100)
        except Exception:
            return 0.0

    @classmethod
    def _calc_rev_momentum(cls, rev_df: Optional[pd.DataFrame]) -> dict:
        """
        月營收即時動能 (台股最即時的成長領先指標,每月10號更新,零額外 API)。
        回傳:
          mom      月增率 (最新月 vs 前一月, %)
          cum_yoy  累計營收年增率 (今年 YTD vs 去年同期, %)
          accel    營收動能加速度 (近3月平均YoY − 前3月平均YoY, 百分點;>0 動能增溫)
          streak   連續 YoY 正成長月數
          asof     最新月營收所屬年月 (YYYY-MM)
        """
        empty = {"mom": None, "cum_yoy": None, "accel": None, "streak": 0, "asof": None}
        if rev_df is None or rev_df.empty or 'revenue' not in rev_df.columns:
            return empty
        if 'revenue_year' not in rev_df.columns or 'revenue_month' not in rev_df.columns:
            return empty
        df = rev_df.copy()
        df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
        df = df.dropna(subset=['revenue']).sort_values(['revenue_year', 'revenue_month'])
        if df.empty:
            return empty
        latest = df.iloc[-1]
        ly, lm = int(latest['revenue_year']), int(latest['revenue_month'])
        asof = f"{ly}-{lm:02d}"

        mom = None
        if len(df) >= 2:
            prev = df.iloc[-2]['revenue']
            if prev:
                mom = float((latest['revenue'] - prev) / prev * 100.0)

        def _yoy_at(row):
            y, m, rev = int(row['revenue_year']), int(row['revenue_month']), row['revenue']
            p = df[(df['revenue_year'] == y - 1) & (df['revenue_month'] == m)]
            if p.empty or not rev:
                return None
            pv = p.iloc[-1]['revenue']
            return float((rev - pv) / pv * 100.0) if pv else None

        # 連續 YoY 正成長月數 (由最新往回數)
        streak = 0
        for _, row in df.iloc[::-1].iterrows():
            v = _yoy_at(row)
            if v is not None and v > 0:
                streak += 1
            else:
                break

        # 動能加速度:近3月平均 YoY − 前3月平均 YoY
        yoys = [v for v in (_yoy_at(r) for _, r in df.iterrows()) if v is not None]
        accel = None
        if len(yoys) >= 6:
            accel = float(sum(yoys[-3:]) / 3 - sum(yoys[-6:-3]) / 3)

        # 累計 YTD 年增:今年 1..lm 月 vs 去年同期
        cum_yoy = None
        cur = df[(df['revenue_year'] == ly) & (df['revenue_month'] <= lm)]['revenue'].sum()
        prv = df[(df['revenue_year'] == ly - 1) & (df['revenue_month'] <= lm)]['revenue'].sum()
        if prv:
            cum_yoy = float((cur - prv) / prv * 100.0)

        return {"mom": mom, "cum_yoy": cum_yoy, "accel": accel, "streak": streak, "asof": asof}

    @classmethod
    def _calc_rev_yoy_smoothed(cls, rev_df: Optional[pd.DataFrame], months: int = 3) -> Optional[float]:
        """
        近 N 個月「平均月營收年增率」,作為營收成長趨勢 (rev_cagr),
        與 _calc_rev_yoy 的「最新單月 YoY」(revenue_growth) 區隔,避免兩欄位數字完全相同。
        沿用已抓的 rev_df,零額外 API。資料不足回傳 None。
        """
        if rev_df is None or rev_df.empty or 'revenue' not in rev_df.columns:
            return None
        if 'revenue_year' not in rev_df.columns or 'revenue_month' not in rev_df.columns:
            return None
        df = rev_df.copy().sort_values(['revenue_year', 'revenue_month'])
        yoys: List[float] = []
        for _, row in df.tail(months).iterrows():
            ry, rm, rev_now = row['revenue_year'], row['revenue_month'], row['revenue']
            prev = df[(df['revenue_year'] == ry - 1) & (df['revenue_month'] == rm)]
            if prev.empty or not rev_now:
                continue
            rev_prev = prev.iloc[-1]['revenue']
            if not rev_prev:
                continue
            try:
                yoys.append(float((rev_now - rev_prev) / rev_prev * 100))
            except Exception:
                continue
        if not yoys:
            return None
        return float(sum(yoys) / len(yoys))

    # ------------------------------------------------------------------
    # 籌碼面量化工具
    # ------------------------------------------------------------------
    @staticmethod
    def _net_buy_lots(df: Optional[pd.DataFrame], buy_col: str, sell_col: str,
                      cutoff_date: str) -> float:
        """
        指定法人自 cutoff_date 起的「淨買超張數」(買-賣,股數 ÷1000)。
        正值=買超,負值=賣超。沿用已抓的 chip_df,零額外 API。
        """
        if df is None or df.empty or buy_col not in df.columns or sell_col not in df.columns:
            return 0.0
        sub = df[df['date'].astype(str) >= str(cutoff_date)]
        if sub.empty:
            return 0.0
        buy = pd.to_numeric(sub[buy_col], errors='coerce').fillna(0).sum()
        sell = pd.to_numeric(sub[sell_col], errors='coerce').fillna(0).sum()
        return float((buy - sell) / 1000.0)

    @staticmethod
    def _gross_trade_shares(df: Optional[pd.DataFrame], buy_col: str, sell_col: str,
                            cutoff_date: str) -> float:
        """指定法人自 cutoff_date 起的總成交股數 (買+賣),供法人成交占比計算。"""
        if df is None or df.empty or buy_col not in df.columns or sell_col not in df.columns:
            return 0.0
        sub = df[df['date'].astype(str) >= str(cutoff_date)]
        if sub.empty:
            return 0.0
        buy = pd.to_numeric(sub[buy_col], errors='coerce').fillna(0).sum()
        sell = pd.to_numeric(sub[sell_col], errors='coerce').fillna(0).sum()
        return float(buy + sell)

    @staticmethod
    def _percentile_rank(series, value, positive_only: bool = True) -> Optional[float]:
        """
        當前值在自身歷史分布的百分位 (0-100)。需足夠樣本 (>=60 筆,約一季)。
        positive_only=True 時排除 <=0 的異常 (PER/PBR 虧損期)。樣本不足或值無效回傳 None。
        """
        if value is None:
            return None
        s = pd.to_numeric(pd.Series(series), errors='coerce').dropna()
        if positive_only:
            s = s[s > 0]
            if value <= 0:
                return None
        if len(s) < 60:
            return None
        return float((s < float(value)).mean() * 100.0)

    _market_regime = None    # 大盤位階一次性快取 (每次執行算一次)

    @classmethod
    def _ensure_market_regime(cls) -> str:
        """
        推斷當前大盤位階 (多頭/中性/空頭 + 位階),供估值情境參考。
        以 TAIEX 報酬指數的長短期均線 + 近一年位階判斷。一次性快取,失敗回空字串。
        """
        if cls._market_regime is not None:
            return cls._market_regime
        regime = ""
        try:
            cls._ensure_login()
            start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
            idx = cls._api.get_data(dataset='TaiwanStockTotalReturnIndex', data_id='TAIEX', start_date=start)
            if idx is not None and not idx.empty and 'price' in idx.columns:
                p = pd.to_numeric(idx['price'], errors='coerce').dropna().reset_index(drop=True)
                if len(p) >= 60:
                    cur = float(p.iloc[-1])
                    ma60 = float(p.tail(60).mean())
                    ma200 = float(p.tail(200).mean()) if len(p) >= 200 else float(p.mean())
                    lo, hi = float(p.min()), float(p.max())
                    pos = (cur - lo) / (hi - lo) * 100.0 if hi > lo else 50.0
                    if cur > ma60 > ma200:
                        trend = "多頭"
                    elif cur < ma60 < ma200:
                        trend = "空頭"
                    else:
                        trend = "中性"
                    level = "高檔" if pos >= 80 else ("低檔" if pos <= 20 else "中段")
                    regime = f"{trend}·近一年{level} ({pos:.0f}百分位)"
        except Exception as e:
            logger.info(f"大盤位階計算略過: {e}")
        cls._market_regime = regime
        return regime

    @staticmethod
    def _ttm_revenue(rev_df: Optional[pd.DataFrame], months: int = 12) -> Optional[float]:
        """近 12 個月營收合計 (TTM),供市值/營收 的 P/S 計算。單位同 rev_df 的 revenue (元)。"""
        if rev_df is None or rev_df.empty or 'revenue' not in rev_df.columns:
            return None
        df = rev_df.copy()
        if 'revenue_year' in df.columns and 'revenue_month' in df.columns:
            df = df.sort_values(['revenue_year', 'revenue_month'])
        vals = pd.to_numeric(df['revenue'], errors='coerce').dropna()
        if vals.empty:
            return None
        ttm = float(vals.tail(months).sum())
        return ttm if ttm > 0 else None

    @staticmethod
    def _market_volume_shares(price_df: Optional[pd.DataFrame], window: int = 10) -> float:
        """近 window 日總成交股數 (TaiwanStockPrice Trading_Volume 單位為股)。"""
        if price_df is None or price_df.empty:
            return 0.0
        vcol = 'Trading_Volume' if 'Trading_Volume' in price_df.columns else \
               ('volume' if 'volume' in price_df.columns else None)
        if vcol is None:
            return 0.0
        vols = pd.to_numeric(price_df.tail(window)[vcol], errors='coerce').fillna(0)
        return float(vols.sum())

    @staticmethod
    def _calc_volume_concentration(price_df: Optional[pd.DataFrame], window: int = 20) -> float:
        """
        成交量集中度:近 window 日「上漲日成交量」佔總成交量比重(%)。
        >50% 表量能集中於上漲日(買方主導);<50% 集中於下跌日(賣壓主導)。
        沿用已抓的 price_df,零額外 API。
        """
        if price_df is None or price_df.empty or 'close' not in price_df.columns:
            return 0.0
        vcol = 'Trading_Volume' if 'Trading_Volume' in price_df.columns else \
               ('volume' if 'volume' in price_df.columns else None)
        if vcol is None:
            return 0.0
        recent = price_df.tail(window + 1)
        closes = pd.to_numeric(recent['close'], errors='coerce').reset_index(drop=True)
        vols = pd.to_numeric(recent[vcol], errors='coerce').reset_index(drop=True)
        up_vol = tot_vol = 0.0
        for i in range(1, len(recent)):
            v = vols.iloc[i]
            if pd.isna(v) or pd.isna(closes.iloc[i]) or pd.isna(closes.iloc[i - 1]):
                continue
            tot_vol += v
            if closes.iloc[i] > closes.iloc[i - 1]:
                up_vol += v
        return float(up_vol / tot_vol * 100.0) if tot_vol > 0 else 0.0

    # ------------------------------------------------------------------
    # 對外入口
    # ------------------------------------------------------------------
    @classmethod
    def _ensure_industry_map(cls) -> dict:
        """
        一次性載入全市場產業別 (TaiwanStockInfo,免費,不帶 data_id → 整批一次到位)。
        優先讀本機快取 (data/industry_map.json,30 天內視為新鮮),否則抓一次並存檔。
        失敗回傳空 dict (分類器會退回外資持股+波動度判斷),不中斷流程。
        """
        if cls._industry_map is not None:
            return cls._industry_map

        # 快取目錄:PyInstaller 打包 (--onefile) 時 __file__ 指向唯讀暫存區,
        #   改用 exe 所在目錄,確保快取可寫入且跨次保留。
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_dir = os.path.join(base, "data")
        cache_path = os.path.join(cache_dir, "industry_map.json")

        # 1) 讀本機快取 (30 天內)
        try:
            if os.path.exists(cache_path):
                age_days = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 86400.0
                if age_days < 30:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cls._industry_map = json.load(f)
                        logger.info(f"產業別快取載入 {len(cls._industry_map)} 檔 (快取 {age_days:.1f} 天)")
                        return cls._industry_map
        except Exception as e:
            logger.warning(f"讀取產業別快取失敗,改為重新抓取: {e}")

        # 2) 抓一次全市場 TaiwanStockInfo
        m: dict = {}
        try:
            cls._ensure_login()
            info = cls._api.get_data(dataset='TaiwanStockInfo')
            if info is not None and not info.empty and 'stock_id' in info.columns:
                for _, r in info.iterrows():
                    sid = str(r.get('stock_id', '')).strip()
                    ind = str(r.get('industry_category', '')).strip()
                    if sid and ind and ind.lower() != 'nan':
                        m[sid] = ind
            logger.info(f"TaiwanStockInfo 產業別抓取 {len(m)} 檔")
        except Exception as e:
            logger.warning(f"TaiwanStockInfo 抓取失敗,產業別以空表計: {e}")

        # 3) 存檔 (即使空表也快取,避免每檔重試;空表 age 到期會再抓)
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"產業別快取寫入失敗 (不影響執行): {e}")

        cls._industry_map = m
        return m

    @classmethod
    def get_all_data(cls, symbols: Optional[List[str]] = None) -> list:
        """從 main.py 呼叫的統一入口,回傳多檔自選股的 StockData 列表。
        symbols 若提供則優先使用 (供使用者自行輸入代號);否則回退 Config.TARGET_STOCKS。"""
        cls._ensure_login()
        from main import Config

        if not symbols:
            symbols = getattr(Config, "TARGET_STOCKS", ["2330", "8016", "2454", "3037", "2317"])

        # TDCC 週更資料:整份全市場一次抓好存快照 (若本週已快取則自動跳過網路)
        try:
            if getattr(Config, "USE_TDCC_CHIP", False):
                from core.tdcc_provider import TDCCProvider
                d = TDCCProvider.update()
                logger.info(f"TDCC 股權分散最新資料日期: {d}")
        except Exception as e:
            logger.warning(f"TDCC 週資料更新略過 (不影響日線評分): {e}")

        stock_list = []
        for sym in symbols:
            data = cls.fetch_full_stock_data(sym)
            if data is not None:
                stock_list.append(data)
        return stock_list

    @classmethod
    def fetch_full_stock_data(cls, symbol: str) -> Optional[StockData]:
        """
        【旗艦版數據整合】
        單次運行只呼叫必需的 API,並將三大法人籌碼放在記憶體內由 Pandas 交叉計算天數。
        """
        cls._ensure_login()
        try:
            # 1. 抓取基本股價歷史 (365天)
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            price_df = cls._api.get_data(dataset='TaiwanStockPrice', data_id=symbol, start_date=start_date)

            if price_df is None or price_df.empty:
                logger.error(f"無法取得股票 {symbol} 的價格數據")
                return None

            price_df = cls._stabilize_price_scale(price_df)

            close_series = pd.to_numeric(price_df['close'], errors='coerce')

            # 2. 技術指標(統一走 TechnicalEngine,避免與手刻版公式漂移)
            ma5_series = cls._tech_engine.calculate_ma(price_df.copy(), 5)
            ma20_series = cls._tech_engine.calculate_ma(price_df.copy(), 20)
            ma5_val = float(ma5_series.iloc[-1]) if not ma5_series.empty else 0.0
            ma20_val = float(ma20_series.iloc[-1]) if not ma20_series.empty else 0.0

            # 乖離率 (bias) 與量能爆發倍數 (volume spike) —— 動態動能所需
            ma5_bias_val = cls._tech_engine.calculate_bias(price_df.copy(), 5)
            ma20_bias_val = cls._tech_engine.calculate_bias(price_df.copy(), 20)
            # 中期價格動能 (近6月/近3月報酬%,略過最近5日) —— 與回測 PIT 同一套算法
            mom_6m_val = cls._tech_engine.calculate_trailing_return(close_series, 120, skip=5)
            mom_3m_val = cls._tech_engine.calculate_trailing_return(close_series, 60, skip=5)
            # 相對強弱 RS (v4.4):個股動能 − 大盤 (0050 快取) 同期;無快取/歷史不足留 None 不計分
            rs_3m_val = rs_6m_val = None
            try:
                from core.backtest import benchmark_trailing_return  # 延遲載入避免循環匯入
                _today = datetime.now().strftime("%Y-%m-%d")
                _n_close = int(close_series.dropna().shape[0])
                if _n_close >= 66:
                    _b3 = benchmark_trailing_return(_today, 60)
                    if _b3 is not None:
                        rs_3m_val = float(mom_3m_val) - _b3
                if _n_close >= 126:
                    _b6 = benchmark_trailing_return(_today, 120)
                    if _b6 is not None:
                        rs_6m_val = float(mom_6m_val) - _b6
            except Exception as e:
                logger.info(f"[{symbol}] RS 相對強弱計算略過 (無 0050 快取?): {e}")
            volume_spike_val = 1.0
            try:
                vp_df = price_df.rename(columns={'Trading_Volume': 'volume'}) \
                    if 'Trading_Volume' in price_df.columns and 'volume' not in price_df.columns \
                    else price_df.copy()
                volume_spike_val = cls._tech_engine.calculate_volume_spike(vp_df, 20)
            except Exception as e:
                logger.warning(f"[{symbol}] 量能爆發計算失敗: {e}")

            rsi_res = cls._tech_engine.calculate_rsi(price_df.copy())
            rsi_val = rsi_res.get('val', 50.0)
            if rsi_val is None or (isinstance(rsi_val, float) and np.isnan(rsi_val)):
                rsi_val = 50.0

            weekly_ma20_val = cls._tech_engine.calculate_weekly_ma20(price_df.copy())
            if not weekly_ma20_val:
                weekly_ma20_val = float(close_series.iloc[-1])

            # ATR(14) 波動度 —— 供產業分類與類別B防守區間(漏洞二、三)
            atr_val = cls._tech_engine.calculate_atr(price_df.copy(), 14)
            last_close = float(close_series.iloc[-1]) if len(close_series) else 0.0
            atr_pct_val = float(atr_val / last_close * 100.0) if last_close > 0 else 0.0

            # MACD / 布林狀態(供評分細分,取代原本算了卻沒用的引擎輸出)
            macd_status, macd_golden, bb_status = "neutral", False, ""
            macd_val, bb_upper, bb_lower = 0.0, 0.0, 0.0
            bb_pctb = None
            try:
                macd_res = cls._tech_engine.calculate_macd(price_df.copy())
                if 'error' not in macd_res:
                    macd_status = macd_res.get('status', 'neutral')
                    macd_golden = (macd_res.get('cross') == 'golden')
                    macd_val = float(macd_res.get('val', 0.0))
            except Exception as e:
                logger.warning(f"[{symbol}] MACD 計算失敗: {e}")
            try:
                bb_res = cls._tech_engine.calculate_bb(price_df.copy())
                bb_status = bb_res.get('status', '')
                bb_upper = float(bb_res.get('upper', 0.0))
                bb_lower = float(bb_res.get('lower', 0.0))
                _pctb = bb_res.get('percent_b')
                if _pctb is not None and not pd.isna(_pctb):
                    bb_pctb = float(_pctb)
            except Exception as e:
                logger.warning(f"[{symbol}] 布林帶計算失敗: {e}")

            # 新接入訊號:KD(J值) / MA20-60 交叉 / OBV 量價 (算了卻沒用的引擎輸出)
            # FinMind 欄位為 max/min/Trading_Volume,但引擎需要 high/low/volume → 先正規化。
            tdf = price_df.copy()
            if 'Trading_Volume' in tdf.columns and 'volume' not in tdf.columns:
                tdf['volume'] = pd.to_numeric(tdf['Trading_Volume'], errors='coerce')
            if 'max' in tdf.columns and 'high' not in tdf.columns:
                tdf['high'] = pd.to_numeric(tdf['max'], errors='coerce')
            if 'min' in tdf.columns and 'low' not in tdf.columns:
                tdf['low'] = pd.to_numeric(tdf['min'], errors='coerce')
            kd_j_val = 50.0
            kd_k_val = kd_d_val = 50.0
            ma_cross_status = "neutral"
            obv_rising_val = None
            obv_above_ma20_val = None
            volume_divergence_val = False
            try:
                kd_res = cls._tech_engine.calculate_kd(tdf.copy())
                if kd_res.get("J") is not None and not pd.isna(kd_res.get("J")):
                    kd_j_val = float(kd_res["J"])
                if kd_res.get("K") is not None and not pd.isna(kd_res.get("K")):
                    kd_k_val = float(kd_res["K"])
                if kd_res.get("D") is not None and not pd.isna(kd_res.get("D")):
                    kd_d_val = float(kd_res["D"])
            except Exception as e:
                logger.debug(f"[{symbol}] KD 計算略過: {e}")
            try:
                mc = cls._tech_engine.calculate_ma_cross(tdf.copy(), 20, 60)
                ma_cross_status = mc.get("status", "neutral")
            except Exception as e:
                logger.debug(f"[{symbol}] MA20/60 交叉計算略過: {e}")
            try:
                vol_res = cls._tech_engine.calculate_volume_analysis(tdf.copy())
                obv_rising_val = bool(vol_res.get("obv_rising"))
                obv_above_ma20_val = vol_res.get("obv_above_ma20")   # bool 或 None(資料不足)
                volume_divergence_val = bool(vol_res.get("divergence_warning"))
            except Exception as e:
                logger.debug(f"[{symbol}] OBV/量價計算略過: {e}")
            # 籌碼成本區 (Volume Profile):大戶成本區 / 買進區間
            vp = {"poc": None, "val": None, "vah": None, "price_vs_poc_pct": None, "status": ""}
            try:
                vp = cls._tech_engine.calculate_volume_profile(tdf.copy())
            except Exception as e:
                logger.debug(f"[{symbol}] 成本區計算略過: {e}")

            # 3. 籌碼面:抓 90 天,交由記憶體計算連續買/賣超
            chip_start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            chip_df = cls._api.get_data(
                dataset='TaiwanStockInstitutionalInvestorsBuySell',
                data_id=symbol,
                start_date=chip_start
            )

            trust_days = foreign_days = 0
            trust_sell_days = foreign_sell_days = 0
            foreign_flow = trust_flow = large_holder_activity = 0.0
            institutional_participation = 0.0
            flow_acceleration = 1.0
            trust_net20_shares = 0.0
            foreign_net_ratio: dict = {}     # 外資多天期淨參與率 {1,3,5,10,20}
            trust_net_ratio: dict = {}       # 投信多天期淨參與率 {1,3,5,10,20}
            if chip_df is not None and not chip_df.empty:
                name_series = chip_df['name'].astype(str).str.strip()
                trust_df = chip_df[name_series.isin(['Investment_Trust', 'Investment Trust', '投信'])]
                foreign_df = chip_df[name_series.isin([
                    'Foreign_Investor', 'Foreign_Dealer_Self',
                    'Foreign Investor', '外資'
                ])]

                if trust_df.empty or foreign_df.empty:
                    logger.warning(
                        f"[{symbol}] 籌碼 name 欄位比對可能有缺漏,實際出現的名稱: {name_series.unique().tolist()}"
                    )

                # 自動尋找 buy / sell 欄位(排除比例欄位)
                buy_col, sell_col = 'buy', 'sell'
                for col in chip_df.columns:
                    col_lower = col.lower()
                    if 'buy' in col_lower and col != 'buy_share_per':
                        buy_col = col
                    if 'sell' in col_lower and col != 'sell_share_per':
                        sell_col = col

                # 同時計算連買與連賣
                trust_days = cls._calculate_consecutive_streak(trust_df, buy_col, sell_col, "buy")
                trust_sell_days = cls._calculate_consecutive_streak(trust_df, buy_col, sell_col, "sell")
                foreign_days = cls._calculate_consecutive_streak(foreign_df, buy_col, sell_col, "buy")
                foreign_sell_days = cls._calculate_consecutive_streak(foreign_df, buy_col, sell_col, "sell")

                # === 籌碼量化 (剔除自營商避險雜訊;僅取外資+投信) ===
                dates_sorted = sorted(chip_df['date'].astype(str).unique())

                def _cut(n):
                    return dates_sorted[-n] if len(dates_sorted) >= n else dates_sorted[0]
                cut5, cut10, cut20 = _cut(5), _cut(10), _cut(20)

                # 外資 / 投信 近10日淨買超(張)——同步訊號
                foreign_flow = cls._net_buy_lots(foreign_df, buy_col, sell_col, cut10)
                trust_flow = cls._net_buy_lots(trust_df, buy_col, sell_col, cut10)

                # 主力動態:外資+投信 近5日淨買超(張)——短天期領先訊號,已剔除自營商
                f5 = cls._net_buy_lots(foreign_df, buy_col, sell_col, cut5)
                t5 = cls._net_buy_lots(trust_df, buy_col, sell_col, cut5)
                large_holder_activity = f5 + t5

                # 買超力道放大:近5日日均淨買 vs 近20日日均淨買 (>1 力道增溫)
                f20 = cls._net_buy_lots(foreign_df, buy_col, sell_col, cut20)
                t20 = cls._net_buy_lots(trust_df, buy_col, sell_col, cut20)
                main5_daily = (f5 + t5) / 5.0
                main20_daily = (f20 + t20) / 20.0
                if main20_daily > 0 and main5_daily > 0:
                    flow_acceleration = float(main5_daily / main20_daily)
                elif main5_daily > 0 >= main20_daily:
                    flow_acceleration = 2.0          # 由賣轉買,視為明顯放大
                else:
                    flow_acceleration = 1.0

                # 法人成交占比:外資+投信近10日(買+賣)股數 / (2 × 同期總成交股數)
                inst_gross = (cls._gross_trade_shares(foreign_df, buy_col, sell_col, cut10)
                              + cls._gross_trade_shares(trust_df, buy_col, sell_col, cut10))
                mkt_vol = cls._market_volume_shares(price_df, 10)
                institutional_participation = float(inst_gross / (2.0 * mkt_vol) * 100.0) \
                    if mkt_vol > 0 else 0.0

                # 投信近20日淨買超「股數」(供吸籌比,需搭配流通股數)
                trust_net20_shares = t20 * 1000.0

                # === 多天期法人淨參與率 (whale 重構基底):net(張) ÷ 同期總量(張),signed、市值中性 ===
                _vser = pd.to_numeric(price_df['Trading_Volume'], errors='coerce') \
                    if 'Trading_Volume' in price_df.columns else None
                for _n in (1, 3, 5, 10, 20):
                    _cn = _cut(_n)
                    _vn = float(_vser.tail(_n).sum()) / 1000.0 if _vser is not None else 0.0
                    if _vn > 0:
                        foreign_net_ratio[_n] = cls._net_buy_lots(foreign_df, buy_col, sell_col, _cn) / _vn
                        trust_net_ratio[_n] = cls._net_buy_lots(trust_df, buy_col, sell_col, _cn) / _vn

            # 成交量集中度:近20日上漲日量佔比(%)——零額外 API,沿用 price_df
            volume_concentration = cls._calc_volume_concentration(price_df, 20)

            # 投信吸籌比 = 投信近20日淨買超 ÷ 流通股數(%):中小型股「籌碼正在集中」的免費領先訊號。
            #   流通股數取自 TaiwanStockShareholding 的 NumberOfSharesIssued(免費;每檔 +1 API)。
            #   註:改用投信吸籌比而非外資持股比率,因後者對外資<5%的中小型飆股會嚴重失真。
            whale_concentration = 0.0
            foreign_hold_ratio = 0.0
            shares_outstanding = 0.0
            try:
                sh_df = cls._api.get_data(dataset='TaiwanStockShareholding',
                                          data_id=symbol, start_date=chip_start)
                if sh_df is not None and not sh_df.empty:
                    if 'NumberOfSharesIssued' in sh_df.columns:
                        shares = pd.to_numeric(sh_df.iloc[-1]['NumberOfSharesIssued'], errors='coerce')
                        if not pd.isna(shares) and shares > 0:
                            shares_outstanding = float(shares)
                            whale_concentration = float(trust_net20_shares / shares * 100.0)
                    if 'ForeignInvestmentSharesRatio' in sh_df.columns:
                        fr = pd.to_numeric(sh_df.iloc[-1]['ForeignInvestmentSharesRatio'], errors='coerce')
                        if not pd.isna(fr):
                            foreign_hold_ratio = float(fr)
            except Exception as e:
                logger.warning(f"[{symbol}] 外資持股表抓取失敗,投信吸籌比以 0 計: {e}")

            # 融資融券:融資餘額近10日變化率(散戶退場偵測,漏洞二)。免費;每檔 +1 API。
            margin_balance = margin_change_pct = 0.0
            try:
                mg_df = cls._api.get_data(dataset='TaiwanStockMarginPurchaseShortSale',
                                          data_id=symbol, start_date=chip_start)
                if mg_df is not None and not mg_df.empty and 'MarginPurchaseTodayBalance' in mg_df.columns:
                    bal = pd.to_numeric(mg_df['MarginPurchaseTodayBalance'], errors='coerce').dropna()
                    if len(bal) >= 2:
                        margin_balance = float(bal.iloc[-1])
                        ref = bal.iloc[-11] if len(bal) >= 11 else bal.iloc[0]
                        if ref and ref > 0:
                            margin_change_pct = float((bal.iloc[-1] - ref) / ref * 100.0)
            except Exception as e:
                logger.warning(f"[{symbol}] 融資融券抓取失敗,以 0 計: {e}")

            # 產業分流 (漏洞三):手動覆寫優先,否則以「市值為主 + 外資持股/波動/產業別」分類。
            from core.sector import SectorClassifier
            industry = cls._ensure_industry_map().get(str(symbol))
            _lp = float(close_series.iloc[-1]) if len(close_series) else 0.0
            market_cap = (_lp * shares_outstanding) if (_lp > 0 and shares_outstanding > 0) else None
            sector_category = SectorClassifier.classify(
                symbol, industry=industry, foreign_ratio=foreign_hold_ratio,
                atr_pct=atr_pct_val, market_cap=market_cap
            )
            # 金融股識別:銀行/保險/證券的現金流/毛利/資本支出等工業指標結構性 N/A
            is_financial = bool(industry and any(k in industry for k in ("金融", "保險", "銀行", "證券")))

            # TDCC 千張大戶 (週更;獨立於 FinMind)。預設關閉 → 純參考;
            #   開啟 (Config.USE_TDCC_CHIP=True) 時填值,週變化可進入籌碼分 (背離警示)。
            big_holder_ratio = big_holder_weekly_change = 0.0
            try:
                from main import Config as _Cfg
                if getattr(_Cfg, "USE_TDCC_CHIP", False):
                    from core.tdcc_provider import TDCCProvider
                    m = TDCCProvider.get_chip_metrics(symbol)
                    if m.get("available"):
                        big_holder_ratio = float(m.get("thousand_lot_ratio", 0.0))
                        big_holder_weekly_change = float(m.get("thousand_lot_wchange", 0.0))
                        if m.get("is_stale"):
                            logger.info(f"[{symbol}] TDCC 資料為 {m.get('data_date')},可能尚未更新至最新週。")
            except Exception as e:
                logger.warning(f"[{symbol}] TDCC 籌碼讀取失敗,以 0 計: {e}")

            # 4. 真實基本面(損益表 + 資產負債表)
            fundamental_data = cls._fetch_fundamentals(symbol)

            # 4-1. 月營收年增率 + 即時動能 (最即時的成長領先指標)
            #   本機優先:TEJ monthly_revenue 有檔且新鮮 → 0 API;否則 FinMind
            rev_mom = {"mom": None, "cum_yoy": None, "accel": None, "streak": 0, "asof": None}
            try:
                rev_df = cls._read_tej_monthly_revenue(symbol)
                if rev_df is not None:
                    logger.info(f"[{symbol}] 月營收走本機 TEJ (至 {rev_df['date'].iloc[-1]:%Y-%m},0 API)。")
                else:
                    rev_df = cls._api.get_data(dataset='TaiwanStockMonthRevenue', data_id=symbol, start_date='2024-01-01')
                rev_growth = cls._calc_rev_yoy(rev_df)              # 最新單月 YoY → revenue_growth
                rev_trend = cls._calc_rev_yoy_smoothed(rev_df)      # 近3月平均 YoY → rev_cagr (趨勢)
                rev_mom = cls._calc_rev_momentum(rev_df)            # 月增/累計年增/加速度/連續成長月數
            except Exception:
                rev_growth = 0.0
                rev_trend = None

            # 4-2. PER / PBR / 殖利率 + 相對估值分位 (河流圖)
            #   抓近3年歷史,計算「當前值在自身歷史的分位」,牛熊皆能判斷相對便宜/貴。
            pe_val, pb_val, dy_val = 15.0, 2.0, 3.0
            pe_percentile = pb_percentile = dy_percentile = None
            valuation_basis = "絕對"
            try:
                per_start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
                per_df = cls._api.get_data(dataset='TaiwanStockPER', data_id=symbol, start_date=per_start)
                if per_df is not None and not per_df.empty:
                    pe_col = 'PER' if 'PER' in per_df.columns else ('PE' if 'PE' in per_df.columns else None)
                    pb_col = 'PBR' if 'PBR' in per_df.columns else ('PB' if 'PB' in per_df.columns else None)
                    dy_col = 'dividend_yield' if 'dividend_yield' in per_df.columns else \
                             ('DividendYield' if 'DividendYield' in per_df.columns else None)
                    last = per_df.iloc[-1]
                    if pe_col:
                        pe_val = float(last[pe_col])
                        pe_percentile = cls._percentile_rank(per_df[pe_col], pe_val, positive_only=True)
                    if pb_col:
                        pb_val = float(last[pb_col])
                        pb_percentile = cls._percentile_rank(per_df[pb_col], pb_val, positive_only=True)
                    if dy_col:
                        dy_val = float(last[dy_col])
                        dy_percentile = cls._percentile_rank(per_df[dy_col], dy_val, positive_only=False)
                    if pe_percentile is not None or pb_percentile is not None:
                        valuation_basis = "相對"
            except Exception:
                pass

            # 4-2b. 產業內估值位階 (v4.5,0 API 讀本機參考表;過舊/查無回 None → 估值引擎退回現行配方)
            industry_value_percentile = None
            try:
                from core.industry_value import industry_value_pct
                industry_value_percentile = industry_value_pct(symbol)
            except Exception:
                pass

            # (5) 成本區信心與現有籌碼資料交叉驗證 (零新增 API):
            #   法人參與度、近端主力淨流、TDCC 週變化(若已啟用)僅作信心微調,不影響成本帶主體。
            vp_conf = vp.get("confidence")
            if vp_conf is not None and not pd.isna(vp_conf):
                chip_adj = 0.0
                if institutional_participation >= 30.0:
                    chip_adj += 6.0
                elif institutional_participation < 10.0:
                    chip_adj -= 4.0
                if large_holder_activity > 0:
                    chip_adj += 4.0
                elif large_holder_activity < 0:
                    chip_adj -= 4.0
                if (foreign_flow + trust_flow) > 0:
                    chip_adj += 3.0
                elif (foreign_flow + trust_flow) < 0:
                    chip_adj -= 3.0
                if big_holder_ratio > 0:
                    if big_holder_weekly_change > 0:
                        chip_adj += 2.0
                    elif big_holder_weekly_change < 0:
                        chip_adj -= 2.0
                vp["confidence"] = float(max(0.0, min(100.0, float(vp_conf) + chip_adj)))

            # 5. 封裝並回傳結果
            latest_row = price_df.iloc[-1]
            change_pct = ((close_series.iloc[-1] - close_series.iloc[-2]) / close_series.iloc[-2] * 100) \
                if len(price_df) > 1 and close_series.iloc[-2] else 0.0

            # 成交量統一轉「張」(FinMind Trading_Volume 單位為股,1 張 = 1000 股)
            raw_vol = latest_row.get('Trading_Volume', 0) or 0
            volume_lots = int(float(raw_vol) // 1000)

            # 4-3. P/S 估算 (不額外呼叫 API):
            #   主法:市值 ÷ 近12月營收 = (股價 × 流通股數) ÷ TTM營收。
            #        對虧損股/無 PER 的股票 (如 8046 南電) 仍算得出,較正確。
            #   備援:P/S = P/E × 淨利率 (僅在流通股數或營收缺失時使用)。
            net_margin_val = fundamental_data.get("net_margin")
            price_to_sales = None
            last_price = float(close_series.iloc[-1]) if len(close_series) else 0.0
            ttm_rev = cls._ttm_revenue(rev_df, 12)
            if shares_outstanding > 0 and ttm_rev and last_price > 0:
                ps = (last_price * shares_outstanding) / ttm_rev
                price_to_sales = round(ps, 2) if ps > 0 else None
            if price_to_sales is None and pe_val and net_margin_val not in (None, 0):
                ps = pe_val * (float(net_margin_val) / 100.0)
                price_to_sales = round(ps, 2) if ps > 0 else None

            # 5. 資料信心:綜合基本面缺漏 + 關鍵價格指標是否有效
            missing_fields = list(fundamental_data.get("_missing_fields", []))
            if price_to_sales is None:
                missing_fields.append("price_to_sales")
            if not rev_growth:
                missing_fields.append("revenue_growth")
            if fundamental_data.get("eps_growth") is None:
                missing_fields.append("eps_cagr")
            # 金融股:現金流/毛利/資本支出等工業指標結構性 N/A,不列入缺失、不扣信心分
            if is_financial:
                na_for_financials = {
                    "operating_cash_flow", "free_cash_flow", "capex", "operating_income",
                    "operating_profit_ratio", "ocf_to_net_income", "gross_margin",
                    "gross_margin_trend", "price_to_sales",
                }
                missing_fields = [m for m in missing_fields if m not in na_for_financials]
            data_confidence = max(0.0, 100.0 - len(set(missing_fields)) * 8.0)

            # 現金流欄位(可能為 None)
            ocf = fundamental_data.get("operating_cash_flow")
            fcf = fundamental_data.get("free_cash_flow")
            capex_v = fundamental_data.get("capex")
            net_income_v = fundamental_data.get("net_income")
            ocf_ni = fundamental_data.get("ocf_to_net_income")
            op_income_v = fundamental_data.get("operating_income")
            op_ratio_v = fundamental_data.get("operating_profit_ratio")
            ni_growth = fundamental_data.get("net_income_growth") or 0.0

            return StockData(
                symbol=symbol,
                name=cls._get_name(symbol),                 # 真實股票名稱
                current_price=float(latest_row.get('close', 0.0)),
                volume=volume_lots,                          # 單位:張
                change_percent=float(change_pct),
                ma5=ma5_val,
                ma20=ma20_val,
                ma5_bias=float(ma5_bias_val),                # 新增
                ma20_bias=float(ma20_bias_val),              # 新增
                volume_spike=float(volume_spike_val),        # 新增
                mom_3m=float(mom_3m_val),                    # 新增:近3月中期動能
                mom_6m=float(mom_6m_val),                    # 新增:近6月中期動能
                rs_3m=rs_3m_val,                             # v4.4:近3月相對大盤 (RS)
                rs_6m=rs_6m_val,                             # v4.4:近6月相對大盤 (RS)
                rsi=float(rsi_val),
                macd=macd_val,
                macd_status=macd_status,
                macd_golden_cross=macd_golden,
                bb_status=bb_status,
                kd_j=kd_j_val,
                kd_k=kd_k_val,
                kd_d=kd_d_val,
                bb_percent_b=bb_pctb,
                ma_cross_status=ma_cross_status,
                obv_rising=obv_rising_val,
                obv_above_ma20=obv_above_ma20_val,
                volume_divergence=volume_divergence_val,
                cost_zone_poc=vp.get("poc"),
                value_area_low=vp.get("val"),
                value_area_high=vp.get("vah"),
                price_vs_poc_pct=vp.get("price_vs_poc_pct"),
                cost_zone_status=vp.get("status", ""),
                cost_zone_support=vp.get("support"),
                cost_zone_resistance=vp.get("resistance"),
                cost_zone_confidence=vp.get("confidence"),
                cost_zone_hvn_levels=(vp.get("hvn_levels") or []),
                cost_zone_lvn_levels=(vp.get("lvn_levels") or []),
                bollinger_band_upper=bb_upper,
                bollinger_band_lower=bb_lower,
                weekly_ma20=float(weekly_ma20_val),
                institutional_buy_days=trust_days,
                institutional_sell_days=trust_sell_days,
                foreign_buy_days=foreign_days,
                foreign_sell_days=foreign_sell_days,
                volume_concentration=float(volume_concentration),      # 成交量集中度(上漲日量佔比%)
                whale_concentration=float(whale_concentration),        # 投信吸籌比(投信20日淨買超佔流通股%)
                large_holder_activity=float(large_holder_activity),    # 主力動態(外資+投信近5日淨買超張)
                foreign_flow=float(foreign_flow),                      # 外資近10日淨買超張
                trust_flow=float(trust_flow),                          # 投信近10日淨買超張
                institutional_participation=float(institutional_participation),  # 法人成交占比%
                flow_acceleration=float(flow_acceleration),            # 買超力道放大倍數
                foreign_net_ratio=foreign_net_ratio,                   # 外資多天期淨參與率 {1,3,5,10,20}
                trust_net_ratio=trust_net_ratio,                       # 投信多天期淨參與率 {1,3,5,10,20}
                big_holder_ratio=float(big_holder_ratio),              # 千張大戶佔比% (TDCC,週更)
                big_holder_weekly_change=float(big_holder_weekly_change),  # 大戶佔比週變化(百分點)
                operating_income=op_income_v,                          # 營業利益 (本業獲利)
                operating_profit_ratio=op_ratio_v,                     # 本業獲利占比
                gross_margin_trend=fundamental_data.get("gross_margin_trend"),  # 毛利率季度趨勢
                financials_asof=fundamental_data.get("financials_asof"),  # 財報截止日
                revenue_mom=rev_mom.get("mom"),
                revenue_cum_yoy=rev_mom.get("cum_yoy"),
                revenue_accel=rev_mom.get("accel"),
                revenue_growth_streak=int(rev_mom.get("streak") or 0),
                revenue_asof=rev_mom.get("asof"),
                atr=float(atr_val),                                    # ATR(14)
                atr_pct=float(atr_pct_val),                            # ATR/價 (%)
                margin_balance=float(margin_balance),                  # 融資餘額(張)
                margin_change_pct=float(margin_change_pct),            # 融資10日變化率%
                sector_category=sector_category,                       # 產業分類 A/B
                industry=(industry or ""),                             # 產業別
                is_financial=is_financial,                             # 金融保險業旗標
                pe_ratio=pe_val,
                pb_ratio=pb_val,
                price_to_sales=price_to_sales,               # 新增
                dividend_yield=dy_val,
                pe_percentile=pe_percentile,                 # 本益比歷史分位 (相對估值)
                pb_percentile=pb_percentile,                 # 股價淨值比歷史分位
                dividend_yield_percentile=dy_percentile,     # 殖利率歷史分位
                industry_value_percentile=industry_value_percentile,  # 產業內估值位階 (v4.5)
                valuation_basis=valuation_basis,             # 相對 / 絕對
                market_regime=cls._ensure_market_regime(),   # 當前大盤位階
                roe=fundamental_data["roe"],
                net_margin=fundamental_data["net_margin"],
                gross_margin=fundamental_data["gross_margin"],
                debt_to_asset=fundamental_data["debt_to_asset"],
                current_ratio=fundamental_data["current_ratio"],
                asset_turnover=fundamental_data.get("asset_turnover"),  # v4.4:總資產週轉率
                rev_cagr=(rev_trend if rev_trend is not None else rev_growth),  # 近3月平均年增 (趨勢)
                revenue_growth=rev_growth,                   # 最新單月年增,供獲利一致性檢查
                eps_cagr=fundamental_data.get("eps_growth"), # 真實 EPS 年增率 (缺則 None,由 fundamentals 中性化)
                net_income_growth=float(ni_growth),          # 新增
                pe_vs_industry=pe_val,                       # 餵入原始 PE,由 fundamentals 評分
                operating_cash_flow=ocf,                     # 新增
                free_cash_flow=fcf,                          # 新增
                capex=capex_v,                               # 新增
                net_income=net_income_v,                     # 新增
                ocf_to_net_income=ocf_ni,                    # 新增
                data_confidence=float(round(data_confidence, 1)),  # 新增
                missing_fields=sorted(set(missing_fields)),  # 新增
            )
        except Exception as e:
            logger.error(f"完整抓取流程失敗 {symbol}: {e}")
            return None
