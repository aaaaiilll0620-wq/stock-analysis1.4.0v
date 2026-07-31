# `core/data_provider.py` 在**匯入時**觸發 FinMind 網路登入（class-body 副作用）

## 摘要
`core/data_provider.py` 的 `DataProvider` 類別在 **class-body** 實例化 FinMind SDK：

```python
# core/data_provider.py:21-23
class DataProvider:
    # 使用 SDK 初始化一次,避免重複建立連接
    _api = DataLoader()          # ← 匯入 core.data_provider 就執行,觸發網路登入
```

因此**任何** transitive 匯入 `core.data_provider` 的模組，在 `import` 當下就會打 FinMind
網路登入（實測輸出 `FinMind... login_by_token ... Login success`），即使該次執行根本不需要抓資料。

## 影響範圍
匯入鏈很廣：`core.backtest` → `core.data_provider`（[core/backtest.py:39](core/backtest.py)），
而 `core.score_store` → `core.backtest`，`beat_0050.realbody.build_realbody_scores` → `core.score_store`…
連帶讓下列情境全部在 import 就碰網：

- **單元測試**：測一個純函式（例如建置器的 `_is_canonical_name` / `assert_obs_unique`）也會登入
  → 測試不可在離線／CI／無 token 環境穩定重現。本次研究防禦 PR 已用 **lazy import** 迴避建置器這條路
  （`beat_0050/realbody/build_realbody_scores.py`），但**根因未除**，其他入口仍中。
- **App 啟動**：`app.py` / `main.py` / `portfolio.py` 匯入即登入，拖慢冷啟動、且在無網路時直接噴錯。
- **研究腳本**：任何 `from core...` 的 lab 都被迫在 import 時上網。

> 註:登入實際可能發生在 FinMind SDK 自身 import 或 `DataLoader()` 建構；無論哪個,
> **class-body 實例化把它強制進了每一個 consumer 的 import path**,這是可控的那一環。

## 為什麼另開議題（不併入研究防禦 PR）
它牽動整個 App（`app.py` / `main.py` / `portfolio.py` / 全部 `core.*` consumer），
與「回測研究層防禦架構」耦合度低、影響面大，混進去會讓那個 PR 難以審查與回滾。
研究 PR 已用局部 lazy import 止血，本議題處理**根因**。

## 建議修法（擇一，皆為 lazy 化）
1. **Lazy singleton**：把 `_api` 改成延遲建立——
   ```python
   class DataProvider:
       _api = None
       @classmethod
       def _get_api(cls):
           if cls._api is None:
               from FinMind.data import DataLoader
               cls._api = DataLoader()
           return cls._api
   ```
   所有 `cls._api` 用點改走 `cls._get_api()`。import 不再碰網，第一次真正抓資料才建。
2. **模組級 lazy accessor**：`get_data_provider()` 工廠，呼叫端不再於 import 時取得已登入實例。
3. 若 SDK import 本身就登入，額外用環境變數／設定關掉 SDK 的 auto-login，改由 `DataProvider.login(token)` 顯式登入。

## 驗收
- 在**網路封鎖**下 `import core.data_provider`（及 `core.backtest` / `core.score_store`）不得觸發任何連線。
- 新增測試：socket 全封鎖下 import 這些模組不 raise、且無 `Login success`。
- App / 研究腳本行為不變：第一次真正抓資料時才登入。

## 現況
- 研究防禦 PR（已合併）僅對 `build_realbody_scores` 做 lazy import 止血，未改 `core/data_provider.py`。
- 本議題請指派為**獨立 PR**,不與研究層變更混合。
