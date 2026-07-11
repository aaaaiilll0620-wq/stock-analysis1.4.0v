# 本機資料快取 + 跨股選股 (Parquet + DuckDB)

## 為什麼

FinMind 的歷史資料是唯讀、只往後追加的時間序列。以前每次重跑回測都要重抓
~45 檔 × 8 個資料集 = **約 360 次 API**,很快就撞每小時上限。

改成本機快取後:每檔完整歷史只抓一次存到 Parquet,之後回測 / 個股分析 **直接讀檔 = 0 次 API**;
每天只補「上次之後」的新資料 (增量極小)。跨股選股用 DuckDB 直接查同一批 Parquet,不用重複匯入。

| 時機 | 舊做法 | 快取後 |
|---|---|---|
| 第一次建庫 (~45 檔) | — | ~360 次 (一次性) |
| 每次重跑回測 | ~360 次 | **0 次** |
| 每天更新 | 重抓 360 次 | 幾十次小增量 |

## 安裝

```bash
pip install pyarrow duckdb
```

`pyarrow` 給 pandas 讀寫 Parquet;`duckdb` 給跨股 SQL 選股。兩者都是本機、免架伺服器。

## 快取放哪

預設在 **家目錄下的 `finmind_cache`**（例如 `C:\Users\aaaai\finmind_cache`），刻意放在
`OneDrive\Desktop` 專案**之外**,避免每次更新都觸發 OneDrive 反覆同步。
要換位置設環境變數即可:`set FINMIND_CACHE=D:\finmind_cache`。

結構:`<快取>/<資料集>/<股號>.parquet`（每檔每資料集一個小檔,並行寫零衝突)。

## 自動快取（讀寫穿透）— 不必記旗標

登入後,`DataProvider._api` 會被包成一層**讀寫穿透快取代理**。之後**回測與 `main.py` 個股分析**
只要打 API,就會自動:

1. **先查本機**:該檔該資料集若已在快取且夠新 → 直接用,**0 次 API**。
2. **缺 / 過期才打 API**:純追加資料集 (股價/PER/籌碼/流通股) 只補增量;財報/月營收有就用。
3. **抓到就落地**:無論誰觸發的查詢,抓回來的**完整歷史**都會寫進快取,下次自動重用。

也就是說,你**平常照舊執行**即可,查過的股票自動進快取、之後自動省 API:

```
python main.py 2330 2454                 # 個股分析:第一次打 API 並落地,之後查同檔幾乎 0 次
python main.py 2330 --refresh            # 強制重抓刷新該次查詢 (刷新舊快取)
python tests\run_backtest.py             # 一般回測也會自動用/補快取
```

新鮮度:純追加資料集本機最後日期距今 `STALE_DAYS`(預設 2 天)內視為新鮮、不再打 API;
要保證抓到當日最新價,用 `--refresh`。想完全關閉自動快取,設環境變數或在
`core/data_cache.py` 把 `CACHE_ENABLED = False`。

> `build_cache.py --full` 仍是最有效率的「一次把整池建滿」;上面的自動快取則讓**臨時查的個股**
> 也一併累積進同一個快取,不必事先列進測試池。

## 三步驟

### 1) 建庫（第一次,或想強制刷新）

```bash
python build_cache.py --full
```

用回測分散化測試池 (~45 檔) 限流並行抓好全部歷史。想指定代號:`python build_cache.py 2330 2454 2317`。
`--workers`（預設 5)控制並行；並行只加快**速度**、不減少 API 次數,必要時加 `--throttle 0.2` 避免撞每小時上限。

### 2) 每天增量更新

```bash
python build_cache.py
```

不加 `--full` 就是增量:純追加資料集 (股價 / PER / 籌碼 / 流通股) 只補最後日期之後的新資料;
財報 / 月營收因為會被事後修正,固定整批覆蓋。每天只花幾十次 API。

### 3) 回測讀本機（0 次 API）

```bash
python tests\run_backtest.py --cache               # 0 次 API,純讀本機快取
python tests\run_backtest.py --cache --attribution # 任何分析都能搭 --cache
python tests\run_backtest.py --cache-refresh       # 讀本機但先補增量到最新 (少量 API)
```

`--cache` 也適用互動選單:一旦帶了旗標,整個 session 都走快取。核心回測邏輯一行沒動——
只是把 `Backtester.load()` 的資料來源換成「先讀本機、缺了才補抓」的 `cached_fetch_history`。

## 跨股選股（DuckDB）

DuckDB 直接查 Parquet,不用重新匯入。示範:

```bash
python build_cache.py --screen     # 全市場最新一日 PER 最低 20 檔 (價值面初篩)
```

自己組查詢:

```python
import core.data_cache as dc

# 全市場最新一日、依殖利率由高到低,篩 PBR < 2
sql = f"""
    SELECT stock_id, date, ROUND(dividend_yield,2) AS yield, ROUND(PBR,2) AS pbr
    FROM {dc.tbl('TaiwanStockPER')}
    WHERE dividend_yield IS NOT NULL AND PBR < 2
    QUALIFY row_number() OVER (PARTITION BY stock_id ORDER BY date DESC) = 1
    ORDER BY yield DESC
    LIMIT 30
"""
print(dc.duck_query(sql))
```

`dc.tbl('<資料集>')` 會展開成跨全部股票的 `read_parquet(...)`;`dc.duck_query(sql)` 回傳 DataFrame。
可查的資料集見 `core/data_cache.ALL_DATASETS`（股價 / PER / 月營收 / 財報 / 資產負債表 / 現金流 / 法人買賣 / 流通股）。

## 一定要守住的原則:PIT vs 即時

- **回測**必須嚴格 PIT:只用 `date ≤ as_of` 的資料。快取只存**原始歷史**,as-of 切片邏輯仍在
  `build_pit_stockdata`,快取不會破壞無未來函數的設計。
- **即時個股分析 / 跨股選股**用「今天最新」的資料——那不算未來函數,因為「現在」就是時間邊界。
  上面的選股 SQL 取每檔最新一列,即是此用途。

## 下一步 (Phase 2:綜合分跨股選股)

目前的 DuckDB 選股是查**原始欄位** (PER / 殖利率 / 法人買超…)。若要用**系統的五維綜合分**做跨股排名,
需要把每檔算好的 composite 落地成一張 `scores` 快取 (每日一列),再用 DuckDB 排序篩選。
這會接上 `ScoringManager` / `InvestmentAdvisor`,是快取層之上的下一個模組——需要時再做。
