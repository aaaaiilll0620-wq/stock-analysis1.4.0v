# ISSUE:`fetch_history()` 繞過 `data_cache` 讀寫穿透代理

**開單日**:2026-07-31(Codex 第一輪審查 §四-1 指示另列獨立 issue)
**狀態**:🔍 已量測、**未修**。等 Codex 另行審查後再決定。
**不得混入**:五維度血緣稽核 / 預註冊驗證的任何 PR。

---

## 1. 現象

`core/backtest.py:175-186`:

```python
def fetch_history(symbol, start_date=HISTORY_START):
    api = DataProvider._get_api()      # ← 取到「還沒包快取代理」的底層 loader
    DataProvider._ensure_login()       # ← 這一行才會把 cls._api 換成 CachingDataLoader
    def _get(dataset):
        return api.get_data(...)       # ← 用的是上面那個底層 loader
```

`_ensure_login()` 內 `cls._api = data_cache.install(cls._get_api())`,**但 `api` 這個區域變數
已經綁在包裝前的物件上**。登入本身有生效(同一個底層物件),只有快取代理沒生效。

對照 `cached_fetch_history()`(:220-223)是**先登入再取**,所以會走代理:

```python
if refresh:
    DataProvider._ensure_login()
    api = DataProvider._get_api()      # ← 此時已是 CachingDataLoader
```

同一個檔案裡兩種行為。

> **這不是 2026-07-31 lazy 修復造成的。** 舊碼 `api = DataProvider._api` 同樣在 `_ensure_login()`
> 之前取值,取到的也是未包裝的物件。lazy 修復用 `_get_api()` **精確複製了舊語意**並加註解,
> 行為零改變。

## 2. 兩個函式的預期差異(目前是什麼、應該是什麼)

| | `fetch_history()` | `cached_fetch_history()` |
|---|---|---|
| **定位(docstring)** | 「抓取單檔回測所需的資料集完整歷史」 | 「優先讀本機 Parquet 快取重建 HistoryBundle」 |
| **資料來源** | **一律直打 FinMind API** | `refresh=False`:純讀快取(0 API);`refresh=True`:走代理補增量 |
| **快取讀** | ❌ 不讀 | ✅ |
| **快取寫**(write-through) | ❌ **不寫** —— 打回來的資料不落地 | ✅ |
| **新鮮度判斷** | 無(永遠最新) | `STALE_DAYS=2`;`APPEND_ONLY` 以外的資料集「有就用」 |
| **API 次數 / 每檔** | **9 次**(price / PER / revenue / income / balance / cashflow / chip / shareholding,`USE_ADJUSTED_PRICE` 再 +1) | 0(`refresh=False`)或僅增量 |

**它到底是 bug 還是刻意**:兩種讀法都說得通 ——
(a) bug:寫早了一行,作者本意是走代理;
(b) 刻意:`fetch_history` 的定位就是「不吃快取的原始抓取」,`build_cache.py:113` 也刻意用
`data_cache.unwrap()` 拿底層 loader 建庫,顯示「繞過代理」在本專案是一種**存在的意圖**。
差別是 `build_cache` 用 `unwrap()` **明寫**,`fetch_history` 是靠取值順序**隱含**。
→ **最小修法可能不是改行為,而是把隱含改成明寫**(`api = data_cache.unwrap(DataProvider._get_api())` + 註解)。

## 3. 量測:會不會造成資料新鮮度 / API 次數 / **研究結果**差異

### 3-1 誰會呼叫到它(全 repo grep)

| 呼叫點 | 情境 | 受影響嗎 |
|---|---|---|
| `core/backtest.py:255` `load_benchmark()` 的 fallback | 只有在 `cached_fetch_history()` 讀不到價格時才走 | 見 3-2 |
| `core/backtest.py:714` `Backtester.load()` 的預設 fetcher | 本機跑 `Backtester` 的完整回測 | 是(API 次數) |

**沒有其他呼叫點。**

### 3-2 對**研究結論**的影響:**零**

研究建置路徑是

```
build_realbody_scores → bt_bundle.bt_fetch_history → core.tej_bundle → TEJ 本機 parquet
```

**完全不經過 `fetch_history`**(`bt_fetch_history` 是 `tej_fetch_history` 的包裝,0 次 FinMind)。
`realbody_scores*.parquet` 的任何一列都不受此問題影響。

唯一的間接接觸是 `load_benchmark("0050")`,但它**先走 `cached_fetch_history`**,
而本機快取 `~/finmind_cache/TaiwanStockPrice/0050.parquet` 有 1,827 列(2019-01-02 起)→
**非空 → 直接 return,不會落到 fallback**。實測確認。

> ⚠ 這裡有一個**相關但獨立**的問題:那份 0050 快取只有 2019 起,而 repo 內
> `beat_0050/data/benchmark/0050_raw.parquet` 有 2003 起的完整序列。
> 這是「2019 三個定義斷裂點」的根因,已另記於
> `docs/五維度修正工作計畫_2026-07-31.md`,**不屬於本 issue**。

### 3-3 對 API 次數與新鮮度的影響:有,但只在 live 路徑

- **API 次數**:`fetch_history` 每檔固定 9 次直打且**不落地** → 同一檔連續跑兩次 `Backtester.load()`
  是 18 次 API;若走代理,第二次是 0 次(`STALE_DAYS=2` 內)。
- **新鮮度**:`fetch_history` 反而「更新鮮」(永遠現抓),代價是額度。
  對**當日**分析沒有正確性差異;對回測沒有差異(資料相同,只是來源不同)。
- **落地**:繞過代理表示這些 API 的結果**永遠不進快取**,下次還要再打一次。這是最實質的損失。

## 4. 建議(**不在本輪執行**)

| 選項 | 內容 | 風險 |
|---|---|---|
| A. 明寫繞過 | `api = data_cache.unwrap(DataProvider._get_api())`,行為不變,意圖從隱含變明寫 | 最低。但保留了「不落地」的浪費 |
| B. 改走代理 | `DataProvider._ensure_login()` 移到取值之前 | 改變 live 抓資料語意;`Backtester` 的行為會變成吃快取,需重測 |
| C. 加參數 | `fetch_history(..., use_cache: bool)`,呼叫端顯式選 | 介面變動,兩個呼叫點都要改 |

**建議 A**(先把意圖寫清楚,行為零改變),B 另行評估。等 Codex 裁決。

## 5. 驗收條件(修的時候要滿足)

- `realbody_scores*.parquet` 的任何一列不得改變(本問題本來就不影響它,修完要再確認一次)。
- `tests/` 全綠。
- 若選 B,需量出 `Backtester` 在同一組 symbols 上修前/修後的分數逐列一致。
