# ISSUE:`core/config.py` 的模組級 `DataLoader()` + 匯入即登入 + 無 token 即 raise

**開單日**:2026-07-31(Codex 第一輪審查 §四-2 指示先查證再列 cleanup issue)
**狀態**:🔍 **已查證,不是完全死碼**。**不刪除**,等 Codex 裁決。

---

## 1. 標的

`core/config.py` 全文只有 16 行,三個副作用全在模組層:

```python
load_dotenv()
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
if not FINMIND_TOKEN:
    raise ValueError("Error: FINMIND_TOKEN is missing in .env file.")   # ← 匯入即 raise
fm = DataLoader()                                                        # ← 匯入即連網
fm.login_by_token(FINMIND_TOKEN)                                         # ← 匯入即登入
```

**這正是 2026-07-31 剛從 `core/data_provider.py` 拔掉的那個 pattern,只是換一個檔案。**
`tests/test_import_hygiene.py` 目前**沒有覆蓋這條路徑**(因為沒有任何測試會匯入它)。

## 2. 搜尋證據(**更正我先前的說法**)

第一輪交付文件 §7 問題 3 我寫「全 repo grep 不到任何 importer」——**那是錯的**。
當時的 pattern 只找了 `from core.config` / `import core.config` / `from config import`,
**漏掉相對匯入**。補完後:

```bash
# 絕對匯入:0 筆
grep -rnE "^\s*(from|import)\s+(core\.)?config\b|from core import .*\bconfig\b" --include=*.py .
→ (無匹配)

# 相對匯入:1 筆  ← 這條是先前漏掉的
grep -rn "from .config import" --include=*.py .
→ core/market_sentiment.py:4:from .config import fm  # 從 config 直接導入已啟動的對象

# 非 .py(spec / bat / ipynb / toml / cfg):0 筆
```

## 3. 但那個唯一的 importer 自己也沒人用

```bash
grep -rn "market_sentiment" --include=*.py .  |  grep -v "^./core/market_sentiment.py"
→ (無匹配)
```

而且 `core/market_sentiment.py` 自己的檔頭就寫著:

> ⚠️ 注意:此模組目前尚未被 main.py 主流程引用,屬於獨立/實驗性籌碼分析工具。
> 底層資料源仍需確認:FinMind 的 DataLoader 並沒有 `get_market_data()` 方法……

**依賴鏈**:`core/config.py` ← `core/market_sentiment.py` ← **(無)**

→ 正確描述是:**兩個檔案構成一段孤立的死鏈,不是「config.py 完全沒有 importer」。**

## 4. 為什麼現在沒有爆炸

沒有任何進入點會匯入 `core.market_sentiment`,所以 `core/config.py` 從來沒被執行過 ——
它的 `raise ValueError` 與匯入即登入都是**潛伏**狀態。
一旦有人 `import core.market_sentiment`(例如未來把它接進主流程,或某支 lab 隨手引用),
會同時發生:

1. 沒設 `FINMIND_TOKEN` → **`ValueError` 在 import 時炸**,而且訊息與資料無關;
2. 有設 → **import 當下連網登入**,把剛修好的匯入衛生again破掉;
3. `tests/test_import_hygiene.py` 不會攔到(它只掃 `core.data_provider` / `core.backtest` / `core.score_store`)。

## 5. 建議(**不在本輪執行**)

| 選項 | 內容 |
|---|---|
| A(建議) | **不刪**,但把 `core/config.py` 的模組級副作用改成與 `DataProvider._get_api()` 同一個 lazy pattern(`def get_fm()`),並把 `core.market_sentiment` 加進 `test_import_hygiene.py` 的掃描清單 |
| B | 兩個檔案一起刪(確認是實驗殘骸) |
| C | 現狀不動,只在檔頭加警語 |

**不建議在本輪動它的理由**:與五維度稽核無關,而且 B 涉及刪檔,依 Codex §四-2「不要立即刪除、
先記錄搜尋證據」的指示,本 issue 只負責留證。

## 6. 附帶提醒

`CLAUDE.md` 的模組地圖仍把 `config` 列為架構的一部分(「Handles environment variables, parameters,
and FinMind API initialization」)。若採 B,文件要同步更新;若採 A/C,建議在該行註明它目前是孤立模組。
