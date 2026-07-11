# 上線到 Streamlit Community Cloud — 步驟手冊

把 `app.py`(台股四維度決策系統)部署成「別人隨時都能開」的公開站。
採 **B 模式**:即時分頁由訪客貼**自己的** FinMind token;「綜合分選股」分頁免 token,
讀一份你**打包進 repo 的 scores 快照**。

> 一句話架構:GitHub repo(程式碼 + scores 快照) → Streamlit Cloud 自動安裝依賴、跑 `app.py` →
> 訪客用瀏覽器開網址。你的電腦**不需要**開著。

---

## 前置

- 一個 GitHub 帳號,且已把這個專案推成一個 repo(下面步驟 2 會做)。
- 已經在本機跑過 `python build_cache.py --build-scores`,`Scores` 快取裡有資料
  (選股分頁要靠它)。
- **絕不要**把 `.env`(裡面有你的 FinMind token)推上 GitHub。新版 `.gitignore` 已幫你擋掉。

---

## 步驟 1 — 確認 repo 內該有 / 不該有的檔案

我已放進專案根目錄兩個部署必需檔:

- `requirements.txt` — 雲端據此安裝套件(streamlit / pandas / duckdb / pyarrow / FinMind …)。
- `.gitignore`(已擴充)— 排除 `dist/`、`build/`、`outputs/`、`finmind_cache/`、`data/` 等
  **大體積或本機專用**的東西,只留該上傳的程式碼與 `cloud_cache/` 快照。

> 為什麼要擋 `dist/`、`build/`:那是 PyInstaller 打包產物(數百 MB),推上 GitHub 會又慢又可能超限,
> 雲端也用不到。

---

## 步驟 2 — 把 scores 快照放進 repo(讓選股分頁在雲端有資料)

雲端沒有你本機的 `finmind_cache`,所以要把 `Scores` 這個小資料夾**複製一份到 repo 裡**。

1. 先找出本機快取位置(在專案根目錄執行):

   ```
   python -c "from core import data_cache; print(data_cache.CACHE_DIR)"
   ```

   會印出類似 `C:\Users\aaaai\finmind_cache`。

2. 把其中的 `Scores` 資料夾複製到 repo 的 `cloud_cache\Scores`(PowerShell):

   ```powershell
   # 把 <CACHE_DIR> 換成上一步印出的路徑
   New-Item -ItemType Directory -Force -Path ".\cloud_cache" | Out-Null
   Copy-Item "<CACHE_DIR>\Scores" ".\cloud_cache\Scores" -Recurse -Force
   ```

   完成後 repo 裡會有 `cloud_cache\Scores\*.parquet`(每檔一個,體積很小)。

> `cloud_cache/` 在 `.gitignore` 裡是**特別允許**提交的(唯一的例外)。原始資料快取
> (`TaiwanStockPrice` 等大檔)**不用**放,選股分頁只讀 `Scores`。

---

## 步驟 3 — 推上 GitHub

在專案根目錄:

```bash
git init                     # 若還不是 git repo
git add .
git commit -m "deploy: streamlit app + scores snapshot"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo名>.git
git push -u origin main
```

推完到 GitHub 網頁確認:**看得到** `app.py`、`requirements.txt`、`cloud_cache/Scores/…`;
**看不到** `.env`、`dist/`、`finmind_cache/`。（尤其確認 `.env` 沒被上傳。)

---

## 步驟 4 — 在 Streamlit Community Cloud 部署

1. 開 <https://share.streamlit.io>(或 streamlit.io/cloud),用 **GitHub 登入**、授權讀取你的 repo。
2. 點 **Create app** → 選 **Deploy a public app from GitHub**。
3. 填三個欄位:
   - **Repository**:`<你的帳號>/<repo名>`
   - **Branch**:`main`
   - **Main file path**:`app.py`
4. 展開 **Advanced settings**:
   - **Python version**:選跟你本機相近的版本(先用 `python --version` 看,通常選 **3.12**)。
   - **Secrets**:貼上(這是 `secrets.toml` 格式):

     ```toml
     FINMIND_CACHE = "cloud_cache"
     ```

     這行是根層級 secret,Streamlit 會把它**同時設成環境變數**,於是 `data_cache.CACHE_DIR`
     會指向你剛提交的 `cloud_cache`,選股分頁就讀得到快照。
   - **不要**在這裡放你的 `FINMIND_TOKEN`。B 模式的重點就是讓訪客用自己的 token;
     伺服器放了你的 token 反而會被匿名訪客共用、吃你的額度。
5. 按 **Deploy**。第一次會跑幾分鐘裝套件,右側可看 build log。

---

## 步驟 5 — 部署後驗證

1. **選股分頁(免 token)**:開網址 → 「🎯 綜合分選股」。上方應顯示「名單共 N 檔｜基準日 …」
   並列出排名。若顯示「尚未建 scores 快取」→ 表示 `cloud_cache/Scores` 沒推上去或
   `FINMIND_CACHE` secret 沒設對,回步驟 2/4 檢查。
2. **即時分頁(訪客 token)**:左側「🔑 你的 FinMind API token」貼一組**自己的** token →
   「個股分析」輸入 2330 → 能出四維評分即成功。不貼 token 走匿名,通常會失敗(正常)。
3. 把網址(形如 `https://<你的app名>.streamlit.app`)分享給別人即可。

---

## 之後怎麼維護

- **改程式**:`git push` 到 `main`,Streamlit Cloud 會**自動重新部署**。
- **更新選股資料**(讓雲端排名跟上最新):在本機
  `python build_cache.py --build-scores` → 重新複製 `Scores` 到 `cloud_cache\Scores`
  (步驟 2 的 Copy-Item)→ `git commit` + `git push`。雲端重部署後選股分頁就是新的基準日。
  也可考慮之後我幫你把這步做成一鍵腳本。

---

## 注意事項 / 踩雷點

- **資源上限**:Community Cloud 免費方案每個 app 記憶體約 1 GB。你的依賴(pandas/numpy/duckdb/
  pyarrow/FinMind)裝得下;若 build log 出現記憶體或找不到套件,再依訊息調整
  `requirements.txt`(例如若日後用到回測繪圖才需加 `matplotlib`)。
- **閒置會休眠**:免費 app 一段時間沒人用會「睡著」,下次有人開會自動醒(第一下稍慢),屬正常。
- **要限定對象**:若不想完全公開,可把 app 設為 **private** 並在設定裡加**允許的 email**,
  只有被邀請的人能開。
- **訪客 token 的安全**:B 模式下訪客 token 會存在**伺服器程序記憶體**(不落地、不寫 log)。
  這是「讓訪客提交 token」本質上的取捨;要更嚴謹可日後改成完全 per-session、不共用快取。
- **不要**把 `finmind_cache` 全部(原始資料)塞進 repo——又大又沒必要,選股只需 `Scores`。

---

## 一頁速查

```
本機:  build_cache.py --build-scores      # 產生 Scores 快取
       複製 <CACHE_DIR>\Scores → cloud_cache\Scores
       git add . && git commit && git push
雲端:  share.streamlit.io → Create app → repo/main/app.py
       Advanced → Secrets:  FINMIND_CACHE = "cloud_cache"   (不要放你的 TOKEN)
       Deploy → 分享 https://<app>.streamlit.app
訪客:  免 token → 用「綜合分選股」分頁
       貼自己的 FinMind token → 也能用「個股分析 / 多檔排行」
```
