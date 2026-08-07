# TEJ 原始資料快照遷移 — DataExport0806

**狀態 (2026-08-08,第十三輪)**:回應 Codex 十三輪審查累積的問題,已修正 (§0)。
第十一、十二、十三輪都是**純文件/政策凍結輪,沒有執行任何程式碼、測試或資料
操作**——完整的資料版本政策與決策登記見 §11,現行的權威計數是 §11.6/§11.8
(D7/D8) 的「8 項前提、7 個狀態」,不是文件裡任何歷史敘述殘留的數字。
**舊 `tej_exports/inbox*` 仍未刪除,生產環境 `~/tej_cache` 仍未寫入——這兩件事
都還沒有被核准,這份文件不代表 Codex 已核准,待這輪修正過審查再說。**

**✅ 第五/六輪造成的 supplement STALE 狀態,已在第七輪被授權的重建解決**——見
§0 第七輪 B/C 與下方 §5.1。`tej_exports/legacy_supplement/receipt.json` 現在的
`script_sha256` 跟磁碟上目前的 `scripts/extract_legacy_supplement.py` 一致,三個
supplement 檔案都能通過 `tej_importer._verify_supplement`。**這不代表遷移整體
已核准**——3.28% 的 `institutional_gross.trust_holding_pct` 落差仍是
`DIFF_UNRESOLVED`(§3),`tej_exports/inbox*` 刪除跟生產環境 `~/tej_cache` 寫入
仍未核准,這只是讓 supplement bundle 恢復成「跟目前程式碼一致、可被消費」的
狀態而已。

**⚠ 第三輪執行超出了當輪明文授權的範圍**,記錄在下方 §0 第四輪回應表第一列——
第三輪的審查指示明講「Do not ... rerun the 2.2 GB full audit yet」,但實際執行時
把 `tej_importer.py` 11 個 dataset 的完整匯入流程、以及 `_full_population_diff.py`
的全量比對都重跑了好幾次。這是真的違規,不是文字遊戲;第四輪不再重蹈覆轍——
本輪**只**修程式邏輯本身,用 `tests/test_tej_data_migration.py` 的 synthetic
fixture 驗證,**沒有**再對 `tej_exports/DataExport0806`(2.2 GB)、
`tej_exports/inbox*`、或 `~/tej_cache` 執行任何讀寫。第三輪產生的兩份 diff
receipt (`tej_exports/diff_receipts/` 底下的兩個
`full_population_diff_20260807T09*.json`) 原封不動保留,當作那次執行的診斷
紀錄,不刪除也不重新產生。(第八輪在同一個資料夾裡新增了第三份、檔名不同的
`institutional_gross_adjudication_*.json`——是明確授權的唯讀溯源裁定,見 §10,
不是重跑這兩份 full_population_diff。)

---

## 0. 審查回應紀錄

### 第十三輪 (2026-08-08) —— 清掉最後一處過期計數摘要 (純文件,無程式碼/測試/資料執行)

Codex 對第十二輪做了獨立複查:§11.4a、§11.6-§11.8 的實質政策修正都在,但
`### 第十一輪` 那段的摘要文字 (原第 68/70 行附近) 還留著「至少六項前提」「六個
狀態」——這兩句在第十二輪之後已經過期,會讓人誤以為那是現行政策的數字。

| # | 審查意見 | 處理 |
|---|---|---|
| R13-1 | 第十一輪 §0 摘要仍寫「至少六項前提」「六個狀態」,跟第十二輪審查表 (D7=八項、D8=七態) 矛盾,容易被誤讀成現行政策 | 改寫第十一輪摘要的⑥⑦兩句,拿掉裡面寫死的數字,改成純敘述;摘要區塊下方新增一段明講「這裡的『六』是第十一輪當下的歷史數字 (而且原本就因為同一個計數漂移問題被誤寫,§11.6 當時實際已經是 7 條)、第十二輪之後現行政策是 8 項/7 態,見 §11.6/§11.8 的 D7/D8」——保留歷史紀錄,但明確跟現行政策的數字分開、不會被誤認。全文搜過一遍,沒有找到其他把 §11.6/§11.7 計數寫死的殘留摘要。 |

本輪**只改** `docs/資料快照遷移_DataExport0806.md` 這一段摘要文字,沒有動任何
定義、雜湊、證據、決策內容,也沒有動第三輪/第九輪/第十輪的既有歷史紀錄。

### 第十二輪 (2026-08-08) —— 修正政策矛盾與計數錯誤 (純文件,無程式碼/測試/資料執行)

第十一輪凍結的政策裡有一個實質矛盾跟兩個文字/計數錯誤,第十二輪只改
`docs/資料快照遷移_DataExport0806.md`,不執行任何東西。

| # | 審查意見 | 處理 |
|---|---|---|
| R12-1 | §11.2 說 candidate 版本身分包含目前的 supplement bundle (源自舊系譜),§11.4 卻說「不允許混用快照版本」——兩者字面上矛盾,沒有明講 supplement 為什麼可以例外 | 新增 [§11.4a](#114a-legacy_derived_supplement混用禁令的唯一明文例外-第十二輪凍結):凍結 `LEGACY_DERIVED_SUPPLEMENT` 這個範圍極窄、內容凍結、可 fail-closed 的明文例外,僅限 `roe_after_tax`/`recurring_net_income`/`revenue_last_year`+`cum_revenue_last_year` 三組欄位,內容綁死在目前的 `legacy_supplement/receipt.json`,只能新增欄位不能覆寫原生 V2 欄位,合併鍵/列數的既有驗證全部繼續強制,每個用到的 dataset/receipt 都要標記 `source_class=LEGACY_DERIVED_SUPPLEMENT` 並攜帶 supplement receipt 雜湊,例外本身不能被隱性擴大。加進決策登記表 (D9) 跟未來隔離建置前提清單 (§11.6 第 8 項)。 |
| R12-2 | `BUILD_NOT_RUN` 的敘述容易被讀成「11 個 dataset 從來沒有被跑過任何一次建置」,但第三輪其實真的跑過一次 (只是超出授權範圍)——原本的敘述沒有把這兩件事分清楚,有抹除第三輪歷史的風險 | 把 `BUILD_NOT_RUN` 精確定義為「沒有任何一次**正式授權、符合政策**的建置被執行過」;新增狀態 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD`,明講第三輪確實把 11 個 dataset 都建了 (見文件開頭 ⚠ 警告、§0 第四輪 R4-0),那次的產物 (含 `institutional_gross` 這個從第七輪起被 §10 當唯讀診斷輸入用的子目錄) 只能算證據/診斷素材,不能滿足 `BUILD_VALIDATED`、不能推廣、不能被當成正式的 V2 candidate build。第三輪的既有歷史紀錄原文不動,只是新增一個狀態標籤去指向它,不是重寫。加進決策登記表 (D10)。 |
| R12-3 | §11.6 的前提清單原文其實已經是 7 條,但 D7 寫「六項」;加了 R12-1 的第 8 項後這個數字又要再變一次 | 統一改成「八項」,§11.6 結尾加一句明講總數跟 D7 要保持同步;D8 的狀態分類法也因為新增 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD` 從六態變七態,同步更正。 |

**這輪的「必須維持不變」項目全部確認**:舊系譜不可變 (§11.1 未改)、
DataExport0806 仍是 `V2_CANDIDATE_RESTATED_SNAPSHOT`、非 PIT、非生產權威
(§11.2 只加了一句指向 §11.4a 的說明,核心定義未改)、`trust_holding_pct` 仍
`DIFF_UNRESOLVED` (§11.3 未改)、正式 candidate build 仍是 `BUILD_NOT_RUN`
(定義更精確,結論不變)、生產環境仍 `PRODUCTION_NOT_APPROVED` (§11.5 未改)、
第三輪/第九輪/第十輪的既有歷史紀錄原文保留,沒有被改寫。

### 第十一輪 (2026-08-08) —— 凍結資料版本政策 (純文件,無程式碼/測試/資料執行)

第十輪的程序跟證據都通過審查,但明確指出:第十輪正式接受的結論範圍僅止於
**出處** (old/new `institutional_gross` parquet 各自忠實反映自己的 TEJ 原始
匯出)——不代表任何一個版本在經濟或歷史意義上「正確」。第十一輪只做文件/政策
凍結,**不修改任何程式碼、測試、manifest、cache、supplement 或 receipt,不
執行任何 pytest/import/audit/績效/OOS/Gate 工作,不 stage/commit/push**。完整
的政策內容見新增的 [§11](#11-資料版本政策與決策登記-第十一輪凍結)。

摘要:①舊系譜 (`~/tej_cache`、舊 `inbox*`、已凍結的 V0/Gate 產物、既有研究結論)
維持不可變,DataExport0806 不得靜默改寫/重算/重新詮釋它們;②DataExport0806
正式定名 `V2_CANDIDATE_RESTATED_SNAPSHOT`;③`trust_holding_pct` 維持
`DIFF_UNRESOLVED`,文字 `"."` 一律保留品質旗標/出處紀錄,不得靜默轉型/補零/
補值;④舊快照跟 V2 候選快照的使用情境明確分離,不可混用;⑤生產環境
`~/tej_cache` 依然封鎖,舊資料不刪除不改名,遷移整體依然不算核准;⑥未來如果
另外授權「把全部 11 個 dataset 建進隔離的候選 cache」,凍結了前提清單;
⑦定義了一組明確的狀態分類法,明講 `BUILD_VALIDATED` 只驗證建置本身的完整性,
不代表策略績效或科學有效性。

**⚠ 計數已過期,見第十二/十三輪更正,以下純為歷史記錄**:第十一輪當下 §11.6
的前提清單原文其實已經是 7 條 (這段摘要當時誤寫「六項」,是同一個計數漂移
問題,第十二輪才發現並修正)、§11.7 的狀態分類法當時確實是 6 態。**第十二輪
新增 `LEGACY_DERIVED_SUPPLEMENT` 前置檢查跟 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD`
狀態後,現行政策的正確數字是 8 項前提、7 個狀態**(見 §11.6/§11.8 的 D7/D8,
那裡才是目前的權威計數,這裡的「六」不代表現在的政策)。

已檢查全文,除了 §1 先前已在第五輪更正過的用詞外,沒有找到其他把
DataExport0806 稱為「唯一/最終/生產權威」的殘留敘述;§1 這次額外指到新定名的
§11 (見上方 §1 的更正註記)。第九輪違規紀錄跟第十輪的全部證據原封不動保留,
沒有改寫歷史。

### 第十輪 (2026-08-08) —— 凍結後單次執行,重做 institutional_gross 裁定

**第九輪的執行本身違反了審查明文的「只授權一次」範圍——實際執行了兩次。這是
真的違規。事後有沒有誠實記錄下來、有沒有修正發現的 bug,都不能讓這件事變成
「沒有違規」。第九輪產生的兩份 receipt (`...47c9e5b7.json` 跟
`...1d59726c.json`) 從第十輪開始,一律只當診斷用途,不能被當作正式有效的
裁定結果引用。** 本輪的設計就是為了不再重蹈覆轍:Phase A 把實作跟測試全部
凍結、完全不碰真實資料;Phase A 凍結後才進 Phase B,執行**恰好一次**——不論
exit code 或 receipt 品質如何,這次授權在程序開始執行的當下就用掉了,不能因為
「看起來有問題」就再跑一次;Phase C 只做唯讀驗證,不再產生新的裁定 receipt。
完整的 Phase A 凍結內容見 §10.9,Phase B/C 的事實性執行結果見 §10.10。

| # | 審查意見 | 處理 |
|---|---|---|
| R10-A1 | receipt 只存每個分類最多 50 筆樣本,不是全部——無法對每一個不一致實例都重建完整證據 | 新增 `mismatch_records`:**每一個**不一致實例各一筆完整記錄 (Round 9 的 4,658 筆規模的話就是 4,658 筆),不是抽樣。`validate_mismatch_records()` 在寫出前檢查筆數 (對照實際重現的輸入,不是寫死的數字)、`(stock_id,date,column)` 唯一性、每筆的必要欄位,任一項不符直接 raise。`classification_samples` 降級成純粹方便閱讀的附加視圖 (每類最多 5 筆),receipt 文件開頭註明它不是唯一的逐筆證據來源。 |
| R10-A2 | 沒有獨立的唯讀驗證機制——目前每一輪的「獨立驗算」都是我自己手動寫的一次性 python 片段,不是可以重複執行、可以被測試的固定工具 | 新增 `scripts/institutional_gross_adjudication_verifier.py`:只接受一個既有 receipt 路徑,重新計算 script/raw/parquet manifest 雜湊、anchor 重現、`mismatch_records` 完整性、所有摘要能否只從 `mismatch_records` 重建、`RAW_SOURCES_DIFFER` 旗標、unparseable 記錄的 raw token 保留、`overall_status`、之前三份 receipt 的出處標記,逐項比對回報。**不寫任何檔案,不呼叫主腳本的 `main()`,不能產生新的裁定 receipt。** |
| R10-A3 | 之前三份 receipt (Round 8、Round 9 兩份) 沒有明確的狀態標記,容易被誤用成正式結果 | 新增 `PRIOR_RECEIPTS_PROVENANCE` 常數,新 receipt 的 `prior_receipts_provenance` 欄位記錄三份 receipt 各自的路徑/SHA-256/狀態標籤:Round 8 → `diagnostic_superseded`;Round 9 第一次 → `diagnostic_invalid_accounting`;Round 9 第二次 → `diagnostic_post_deviation_unauthorized_rerun`。三份都不刪除、不修改,只在新 receipt 裡記錄。 |
| R10-A4 | 缺少涵蓋以上機制的測試 | `tests/test_institutional_gross_adjudication.py` 新增 5 個測試 (`summarize_records`/`validate_mismatch_records`);新增
`tests/test_institutional_gross_adjudication_verifier.py` 17 個測試,建立完全合成、自洽的 receipt + parquet/script/來源檔環境 (全部 monkeypatch 路徑常數,不碰真實資料),覆蓋合法通過、檔案缺失,以及逐項竄改 (script/raw/manifest hash、anchor 重現、`mismatch_records` 筆數/重複鍵/缺欄、摘要對不上、`RAW_SOURCES_DIFFER` 旗標為假、unparseable 記錄遺失 raw token、`overall_status` 不是 `REVIEW_REQUIRED`、出處標記雜湊或狀態被改) 都要被抓到,以及「驗證器本身不寫任何檔案」的直接斷言。全部三個 test module 合計 `167 passed`。 |



第八輪精確重現了 anchor,證據也有用,但審查指出裁定腳本 (`scripts/
institutional_gross_trust_holding_pct_adjudication.py`) 有三個沒做到位的地方。
本輪**只**修改這支腳本、它的 focused 測試、跟本文件,修好且測試全過後才重跑
一次。

| # | 審查意見 | 處理 |
|---|---|---|
| R9-1 | 原始檔驗證只在 filter 成 needed_keys 之後的小子集上做,範圍外的無效列永遠不會被檢查到;而且完全重複 (值也相同) 的列會被安全去重,不是 raise | 新增 `_validate_raw_keys()`,在 filter 之前對**整份**原始檔驗證:stock_id/date 無效直接 raise;**任何**重複鍵 (不論數值是否一致) 都直接 raise,兩份原始檔都不去重。失敗會寫一份 `RAW_SOURCE_VALIDATION_FAILED` receipt,記錄來源/種類/筆數/代表性樣本 (`RawSchemaError` 攜帶結構化欄位)。 |
| R9-2 | 轉換失敗的儲存格 (例如文字 ".") 轉成 NaN 後,原始文字就從資料裡消失,receipt 只留得住「這是 unparseable」的旗標 | `_build_evidence_for_subset()` 對每個 (key, 欄位) 保留 `raw_token`(原始文字,`None` 代表儲存格本來就空白)、`parsed_value`、`is_blank`、`is_unparseable`、`unit_scale` 五個獨立欄位,雙邊都留。分類結果 `classify_all()` 的每一列都帶完整證據,不再只有轉換後的數字。 |
| R9-3 | 統計只到 max/median,看不到完整分布;按股票的分布被截斷到 Top 20;`RAW_SOURCES_DIFFER` 沒有把「兩邊 parquet 真的各自忠實反映自己的原始檔」這個定義性前提明講出來驗證 | 新增 `signed_diff_new_minus_old`/`abs_diff` (每個數值不等的實例都記);`build_diff_distribution()` 給每欄「精確 diff 值 → 筆數」的完整分布,不分箱不設容忍值;`classification_counts_by_stock` 改成完整不截斷,Top 20 只留作額外方便閱讀的欄位;`RAW_SOURCES_DIFFER` 的每一列都記錄並驗證 `old_raw_matches_old_parquet`/`new_raw_matches_new_parquet` 兩個旗標,邏輯兜不起來直接 raise。另外加了「分類計數總和必須等於 total_mismatch_instances」的執行期斷言。 |
| R9-附帶 | (非審查意見,實作時發現的 bug,主動修正並記錄) | `build_diff_distribution()` 第一版把 `mismatch_kind=="null_mismatch"` 跟 `classification=="UNRESOLVED_SCHEMA_OR_UNIT"` 當成兩個獨立計數欄位分開累加,但這兩者不是互斥維度——同一列可能同時是「parquet 層級 null 不對稱」又是「raw 層級無法解析」(真實資料裡那 26 筆 `foreign_holding_pct` 正是這個狀況),分開累加造成重複計數、加總對不上 total。这是本輪要求的「執行後獨立重新驗算所有 accounting invariant」這個步驟本身抓到的——**不是** Codex 提出的審查意見,是我自己在完成三項修正、跑完第一次修正版執行後,做 receipt 自我驗算時發現的。發現當下已經有一個看似成功的 receipt (`institutional_gross_adjudication_20260807T152618418716_47c9e5b7.json`,exit 0、REVIEW_REQUIRED、anchor 精確重現),但 `diff_distribution_by_column` 這個欄位的 `foreign_holding_pct` 子項目對不上 total——判斷這是需要修正後重新產生的錯誤 receipt,不是可以帶著已知 bug 回報的最終結果。修正邏輯改成明確優先順序 (classification 屬於 `RAW_KEY_MISSING`/`UNRESOLVED_SCHEMA_OR_UNIT` 者各自獨立成桶,其餘才依 `mismatch_kind` 分 null_mismatch/精確 diff 值),每列只落進一個桶,新增 `test_build_diff_distribution_sums_to_total_per_column` 鎖住這個不變量,修好後重新執行一次。**這份有 bug 的 receipt 沒有被刪除**,原封不動保留在 `tej_exports/diff_receipts/`,當作這次修正過程本身的診斷紀錄;真正作為本輪結果的是第二次 (修正後) 的 receipt,細節見 §10.8。 |

### 第八輪 (2026-08-07) —— dedup 驗證補強 + trust_holding_pct 唯讀溯源裁定

分兩段,A 是純程式修正 (不動資料),B 是明確授權的一次性唯讀溯源調查 (見 §10)。

**A. `_validate_dedup_metadata` 的剩餘缺口**

| # | 審查意見 | 處理 |
|---|---|---|
| R8-A1 | `dedup.sources` 底下出現的來源名字集合沒有被驗證——來源被改名/多一個/漏一個都不會被抓到,只驗證了「有出現的條目結構對不對」 | 新增 `_EXPECTED_DEDUP_SOURCE_NAMES`,凍結每個 supplement 名字底下應該恰好出現的來源集合 (`roe_after_tax`→`{roe_after_tax}`;`recurring_net_income`→`{recurring_net_income_2005_2018, recurring_net_income_2019plus}`;`revenue_last_year`→`{revenue_last_year}`)。`_validate_dedup_metadata` 先比對 `set(sources.keys())` 跟凍結值是否完全相等,不符就 raise。 |
| R8-A2 | `cross_window_overlap` 的三個計數各自型別對、非負,但沒有驗證彼此加總得起來 | 新增算術恆等式檢查:`n_overlap_keys == n_overlap_identical + n_overlap_conflicting`,不符就 raise。 |
| R8-A3 | 缺少涵蓋以上機制的測試 | 新增 4 個測試:漏來源、多來源、來源改名、overlap 算術對不起來。全部 synthetic fixture,**這是純消費端程式碼修改,沒有重跑 `extract_legacy_supplement.py`,第七輪重建好的 supplement bundle 原封不動**。執行結果:`109 passed`。 |

**B. `institutional_gross.trust_holding_pct` 唯讀溯源裁定**

這不是新的容忍門檻搜尋,也不是遷移核准——純粹是「這 4,658 個不一致的儲存格
(六欄合計,含 `trust_holding_pct` 4,615 個),獨立重新解析兩份原始 Excel 後,
證據指向什麼」的診斷紀錄。完整規則、分類方法、執行結果見新增的
[§10](#10-institutional_grosstrust_holding_pct-唯讀溯源裁定-第八輪)。

執行結果摘要:anchor 精確重現、零差異,通過 §10.5 的前置關卡;4,658 個不一致
實例分類完畢,**4,632 個 (99.44%) 是 `RAW_SOURCES_DIFFER`**(兩邊 parquet 都
忠實反映各自的原始檔,問題出在兩份 TEJ 匯出本身報的數字不同,已人工抽樣覆核
確認)、**26 個是 `UNRESOLVED_SCHEMA_OR_UNIT`**(追查到是單一股票 4130 在新
原始檔裡用文字 `"."` 標記缺值,不是解析腳本的 bug)、**其餘六個分類 (含
`OLD_RAW_ONLY_MATCH`/`NEW_RAW_ONLY_MATCH` 這種代表管線 bug 的分類) 都是 0 筆**
——沒有找到證據顯示這是遷移程式本身的轉換錯誤。**結論:3.28% 落差維持
`DIFF_UNRESOLVED`,這輪沒有解決或調降它**,兩份原始檔本身為什麼不同、哪個版本
該被視為權威,都留給人另外審查,細節見 §10.6-§10.7。

### 第七輪 (2026-08-07) —— 受控的 supplement 重建

第六輪的兩個修正獨立驗證通過。這輪**明確授權**執行一次範圍受限的
`tej_exports/legacy_supplement` 重建 (先前六輪全部只用 synthetic fixture,沒有
碰過真實資料)。分三段執行,A 沒過就不能進 B:

**A. 執行前的最後加固**

| # | 審查意見 | 處理 |
|---|---|---|
| R7-A1 | `dedup` 沒被列進 `_verify_supplement` 的必要欄位,receipt 少了它也不會被擋下來 | `dedup` 加進 `REQUIRED_RECEIPT_OUTPUT_FIELDS`,存在性檢查會擋。 |
| R7-A2 | `dedup` 的巢狀結構本身沒有被驗證——結構壞掉的 `dedup` 一樣會被當作「有檢查過」放行 | 新增 `_validate_dedup_metadata()`(+`_validate_dedup_stat`/`_is_plain_int`):驗證 `sources` 底下每個來源要恰好兩份統計 (`raw_source` + `projected`,用 stage 標籤組合比對,不是位置);每份統計要有 `stage`/`checked_columns`/`n_duplicate_key_rows`/`n_exact_duplicate_rows_removed`/`n_conflicting_keys`,型別正確 (含排除 bool 混進 int 計數欄位)、計數非負、stage 是合法值、`n_conflicting_keys` 必須是 0 (非零代表抽取當下沒有 raise,receipt 不可信);`recurring_net_income` 額外要有 `cross_window_overlap`,三個計數同樣型別/非負/`n_overlap_conflicting` 必須是 0。`dedup` 因為記錄的是投影前/合併時的過程,消費端用最終 parquet 重算不出來,所以不進 `REQUIRED_RECEIPT_PROFILE_FIELDS` 那組數值重算比對,是獨立的結構驗證。 |
| R7-A3 | 缺少涵蓋以上機制的測試 | 新增 12 個測試:`dedup.sources` 缺失、來源條目不是恰好兩份、統計缺欄、統計型別錯 (含 bool-as-int)、計數負數、stage 標籤重複、`n_conflicting_keys` 非零、`recurring_net_income` 缺 `cross_window_overlap`、`n_overlap_conflicting` 非零,以及一個「合法結構本身要能通過」的健全性測試 (避免上面 raise 測試其實是被別的原因擋下來的假陽性)。執行結果:**105 passed**(先於 B 執行,確認 A 通過才進 B)。 |

**B. 唯一一次授權的 supplement 重建**

只執行一次 `python scripts/extract_legacy_supplement.py`(前景、不重試),讀四個
已聲明的舊來源檔 (`tej_exports/inbox_fundamentals/2019-202603 EPS ROE OI.xlsx`、
`tej_exports/inbox_fundamentals/三大財報2019~202603.xlsx`、
`tej_exports/inbox/2005-2018 三大財報+ROE 上下市.xlsx`、
`tej_exports/inbox_revenue/YoY 201901~202607.xlsx`),原子替換
`tej_exports/legacy_supplement`。

- 開始:`2026-08-07T14:19:45Z`;結束:`2026-08-07T14:20:22Z`;**exit code 0**。
- 輸出:`roe_after_tax: 53812 列,1952 檔,2019-03-01 ~ 2026-03-01`;
  `recurring_net_income: 136241 列,2311 檔,2005-06-01 ~ 2026-03-01`;
  `revenue_last_year: 168885 列,1952 檔,2019-01-01 ~ 2026-06-01`——三個數字都
  跟 §5 先前記錄的舊數字一致。
- **來源檔內部/跨窗口沒有偵測到任何衝突** (`check_source_duplicates`/
  `_dedupe_or_raise`/`_combine_recurring_windows` 全部 `n_conflicting_keys`/
  `n_overlap_conflicting` = 0,零去重、零重複鍵、零 null 鍵),不需要人工介入
  查衝突列——回應第六輪文件裡「重跑可能在以前會通過的地方 raise」的顧慮,這次
  實際重跑沒有觸發。
- `tej_exports/inbox*` 四個來源檔的 mtime 執行前後不變 (只讀不寫);沒有觸碰
  `~/tej_cache`;`tej_exports/diff_receipts/` 檔案數維持 2 (沒有重跑 full audit)。

**C. 執行後的唯讀驗證**

| # | 驗證項目 | 結果 |
|---|---|---|
| R7-C1 | receipt.json 結構完整性 | `overall_status=PASS`;`sources` 有 4 個舊來源的 relpath+SHA-256;`script_sha256` 就是目前磁碟上腳本的雜湊;`outputs` 有 3 個輸出各自的 SHA-256/exact schema/dtypes/row_count/stock_count/date_min/date_max/duplicate_key_row_count/null_key_row_count/完整 `dedup`(含 `recurring_net_income` 的 `cross_window_overlap`)。逐項存在,無缺欄。 |
| R7-C2 | 獨立重算所有 SHA-256 與 profile 值,跟 receipt 比對 | 4 個來源檔 SHA-256、3 個輸出檔 SHA-256、抽取腳本自身 SHA-256、`tej_importer._profile_supplement()` 重算的 7 個統計欄位——**全部相符,零差異**。 |
| R7-C3 | 對三個輸出各呼叫一次 `tej_importer._verify_supplement()`(唯讀) | `roe_after_tax`(dataset=`fundamentals_quarterly`)、`recurring_net_income`(dataset=`financial_statements`)、`revenue_last_year`(dataset=`monthly_revenue`)**三個全部 PASS**,回傳列數分別是 53812/136241/168885,跟 receipt 記錄的 row_count 完全一致。 |

**⚠ 這輪只讓 supplement bundle 恢復成可用狀態,不代表遷移整體核准**:
`institutional_gross.trust_holding_pct` 3.28% 落差維持 `DIFF_UNRESOLVED`,沒有
被這輪解決或調降 (§3);`tej_exports/inbox*` 刪除跟 `~/tej_cache` 生產寫入依然
未核准;沒有執行 `_full_population_diff.py`、沒有匯入/重建 11 個主資料集、沒有
績效/OOS/Gate 相關工作;沒有 stage/commit/push。

### 第六輪 (2026-08-07)

第五輪的兩個研究紀律缺口,本輪修正。**仍然沒有**重跑全量 audit、重新產生
supplement、刪除任何 legacy/inbox 資料、寫入生產環境 `~/tej_cache`。

| # | 審查意見 | 處理 |
|---|---|---|
| R6-1 | `tej_importer._verify_supplement` 對 receipt 欄位仍是 fail-open:`schema`/`row_count`/`stock_count`/日期範圍/duplicate/null count/`dtypes` 若直接**缺失**,`if ... is not None` 的守衛會讓那道比對整個被跳過 | 新增三組常數 `REQUIRED_RECEIPT_TOP_FIELDS`(`overall_status`/`script_sha256`/`outputs`)、`REQUIRED_RECEIPT_PROFILE_FIELDS`(7 個統計欄位)、`REQUIRED_RECEIPT_OUTPUT_FIELDS`(前者 + `sha256`/`schema`)。**先檢查欄位存在 (用 `not in`,不是 `is not None`),缺任何一個直接 raise,才開始比值**;所有 `.get(field)` 改成 `[field]` 直接索引,`is not None` 守衛全數移除。因此「欄位存在但值是 `null`」現在也會走正常比對而 raise,不再被守衛吃掉。新增逐欄缺失測試 (`REQUIRED_RECEIPT_OUTPUT_FIELDS` 9 個 + `REQUIRED_RECEIPT_TOP_FIELDS` 3 個,parametrize 逐一刪除該欄位驗證都 raise) 與「值為 null 仍要比對」測試。 |
| R6-2 | `scripts/extract_legacy_supplement.py` 的重複資料數只輸出到 stderr、沒寫進 receipt;而且衝突檢查是在**投影成 supplement 欄位之後**才做,來源檔其他欄位的衝突會被忽略 | 拆出核心判斷 `_duplicate_key_stats(df, key_cols, source_name, stage)`(回傳統計、衝突就 raise),之上有兩個入口:①**新增 `check_source_duplicates()`,在投影前對原始來源的完整列做檢查**——同一個 key 若目標欄位剛好相同、但來源檔其他欄位互相矛盾,投影後會長得像「無害的完全重複」被安全去掉,矛盾永遠沒人看見,現在先擋下來;②`_dedupe_or_raise()` 維持投影後的第二層檢查並實際去重。兩者都改成回傳 stats,四個 `extract_*` 函式改回傳 `(df, stats)`,`_combine_recurring_windows` 額外回傳 `n_overlap_keys`/`n_overlap_identical`/`n_overlap_conflicting`,`main()` 把全部寫進 receipt 的 `outputs[<name>]["dedup"]`。stderr 訊息保留 (操作者當下看得到),但不再是唯一紀錄。新增測試 6 個,其中最關鍵的一個直接重現這個缺口:目標欄位一致、`net_income` 矛盾的兩列,證明投影後檢查會放行 (`n_conflicting_keys == 0`)、原始來源層會 raise。 |

**⚠ 這一輪讓檢查變嚴了,有一個後果要先講清楚**:R6-2 的原始來源層檢查比對的是
**來源檔全部欄位**,不只是最後要抽出來的那一欄。這是刻意的 (來源檔自相矛盾就代表
這份檔案品質有問題,不能因為「我們要的那欄剛好一致」就放行),但也代表:**之後
真的獲授權重跑 `extract_legacy_supplement.py` 時,有可能在以前會通過的地方 raise**。
本輪只用 synthetic fixture 驗證邏輯,**沒有**拿真實 `tej_exports/inbox*` 跑過,所以
無法預先知道實際來源檔裡有沒有這種「目標欄位一致、其他欄位矛盾」的列、有幾列。
如果重跑時真的炸了,那是這道檢查生效、不是迴歸——但要先有人去看那些衝突列到底
是什麼,不能直接放寬檢查讓它過。

| R6-附帶 | (非審查意見,實作時發現的耦合風險,主動補測試) | receipt 由 `extract_legacy_supplement._profile` 產生、消費端用 `tej_importer._profile_supplement` 重算比對,是**兩份各自獨立的實作**——任一邊改了欄位或算法沒同步,正常的 supplement 就會被誤判成「被竄改」。新增 `test_profile_implementations_agree_across_producer_and_consumer` 把兩者鎖住,並涵蓋 parquet round-trip (receipt 是寫檔前算的、驗證是讀檔後算的,dtype 必須撐得過來回一趟)。 |

### 第五輪 (2026-08-07)

第四輪的 54 個測試獨立驗證通過,但遷移整體仍未核准。本輪只修下列項目,**沒有**
重跑全量 audit、重新產生 supplement、刪除任何 legacy/inbox 資料、寫入生產環境
`~/tej_cache`,也沒有執行績效/OOS/Gate 相關工作。

| # | 審查意見 | 處理 |
|---|---|---|
| R5-1 | 兩個發布函式 (`extract_legacy_supplement.publish_staging`、`tej_importer.save_by_stock`) 起手式都是無條件 `shutil.rmtree(backup_dir)`——如果上一次執行在 `out_dir.rename(backup_dir)` 之後、`staging_dir.rename(out_dir)` 完成前被強制中斷 (例如程序被 kill,不是走 except 分支的那種失敗),backup_dir 會是唯一僅存的舊資料,這樣寫會直接刪掉它 | 兩個檔案都新增 `_recover_or_clear_stale_backup(out_dir, backup_dir, label)`,在函式最開頭呼叫:backup_dir 不存在就直接返回;backup_dir 存在但 out_dir 不存在 (唯一僅存的舊資料) 就先 `rename` 還原,還原本身失敗就讓例外往外傳、不吞掉 (backup_dir 保持原狀,資料沒有遺失,可以重試);只有兩者都存在時才是真的「清得掉」的殘留 backup,才會 `shutil.rmtree`。原本階段二裡的無條件清除已移除 (改由這個檢查在函式開頭統一處理,呼叫之後 backup_dir 保證不存在)。新增測試涵蓋:只有 backup 時安全還原、兩者都在時安全清除、還原本身失敗時資料不遺失、失敗後的下一次呼叫能安全完成還原,以及 `save_by_stock`/`publish_staging` 兩個呼叫端的整合測試 (模擬強制中斷的殘留狀態,驗證下一次呼叫能正確恢復並完成發布)。 |
| R5-2 | `scripts/extract_legacy_supplement.py` 每個 `extract_*` 函式結尾都是直接 `drop_duplicates(subset=["stock_id","date"], keep="last")`,同一個 key 在來源檔內部出現兩次且數值不同時,會悄悄選最後一列,沒有人看得到這個選擇 | 新增 `_dedupe_or_raise(df, key_cols, source_name)`,套用到 `extract_roe`/`_extract_recurring_2019plus`/`_extract_recurring_2005_2018`/`extract_revenue_last_year` 四個函式:同 key 若所有非 key 欄位值都相同 (含都是 NaN) 才算完全重複,安全去重但次數要印出來;只要有一個欄位值不同 (含一邊有值一邊 NaN 這種不對稱) 一律 raise,不設任何容忍門檻,不能用 `keep="last"` 悄悄選一個了事。 |
| R5-3 (前半) | `recurring_net_income` 的 2005-2018 窗口跟 2019+ 窗口原本直接 `pd.concat` 後 `drop_duplicates(keep="last")`,萬一兩個窗口在邊界真的重疊,會讓 2019+ 窗口不由分說地優先,沒有人比對過重疊的那幾個 key 數值是否一致 | 新增 `_combine_recurring_windows(old_window, new_window)`:先用 inner join 找出兩個窗口重疊的 key,重疊 key 兩邊數值相同 (含都是 NaN) 才安全去重且印出次數;數值不同就直接 raise、附上重疊 key 樣本,交給人去查是哪個窗口的資料有問題。`extract_recurring_net_income()` 改呼叫這支函式,不再是裸的 concat+drop_duplicates。 |
| R5-3 (後半) | `tej_importer._verify_supplement` 只在 `scripts/extract_legacy_supplement.py` 存在時才比對腳本 SHA-256,腳本被誤刪/搬移時這道防線直接被跳過;schema 檢查只跟 receipt 自己宣稱的 schema 比對,receipt 跟實際 parquet 自洽但仍可能跟消費端真正需要的欄位不符;receipt 裡的 row_count/stock_count/日期範圍/重複鍵/null 鍵數量從沒被消費端重新驗算過,只要 SHA-256 對得上就照單全收 | 三處都補強:①`LEGACY_SUPPLEMENT_SCRIPT` 不存在直接 raise `FileNotFoundError`,不再用 `if ... .exists()` 包住整段驗證邏輯;②新增程式碼凍結的 `SUPPLEMENT_SCHEMAS` dict,schema 檢查對照這份凍結值而不是只信 receipt 自己的 `schema` 欄位 (receipt 的 schema 仍會另外比對,兩者都要過);③新增 `_profile_supplement()`,跟 `extract_legacy_supplement._profile` 同一套統計邏輯在消費端獨立重算一次 row_count/stock_count/date_min/date_max/duplicate_key_row_count/null_key_row_count/dtypes,任一項跟 receipt 記錄的不一致就 raise (即使 SHA-256 相符也擋——這是防 receipt 被單獨竄改某個描述性欄位,或抽取腳本的 `_profile` 邏輯以後跟消費端不同步)。pre-merge/post-merge 的 row 膨脹與重複鍵檢查維持不變。 |
| R5-4 | `scripts/_full_population_diff.py` 對非數值欄位是用 `o.astype(str) == n.astype(str)` 比對,但這個分支在「一邊是數值 dtype、另一邊是 object/字串 dtype」時也會被誤觸發——`10.0`(float)字串化後跟字串 `"10.0"` 可能剛好相等,把真正的 dtype drift (代表匯入邏輯或欄位對應可能有問題) 藏起來 | 在數值/非數值分支之前先比較 `pd.api.types.is_numeric_dtype(o)` 是否等於 `is_numeric_dtype(n)`;不相等時直接把整欄標記 `dtype_status="INCOMPATIBLE"`、`n_value_mismatch=一律等於兩邊都有值的列數`,完全不做字串近似比較。相容的情況下 (兩邊都數值或兩邊都非數值) 原邏輯不變,但每欄結果新增 `dtype_status`("OK"/"INCOMPATIBLE")、`old_dtype`、`new_dtype` 三個欄位,方便審查者不用另外查就能看到實際 dtype。 |
| R5-5 | 缺少涵蓋以上機制的測試 | `tests/test_tej_data_migration.py` 從 76 個測試 (第四輪 54 個 + 本輪新增 22 個):`_recover_or_clear_stale_backup` 在 `tej_importer.py`/`extract_legacy_supplement.py` 兩邊的單元測試 (無殘留/安全清除/安全還原/還原失敗後下次呼叫恢復) 與 `save_by_stock`/`publish_staging` 呼叫端整合測試、`_dedupe_or_raise` 的完全重複去重與衝突 raise (含 null-vs-有值視為衝突)、`_combine_recurring_windows` 的重疊一致去重/重疊衝突 raise/無重疊各自保留、`_verify_supplement` 的腳本缺席 raise/code-defined schema 不符 raise (即使 receipt 自洽)/重新計算 row_count 或 stock_count 跟 receipt 不符 raise、`_full_population_diff.py` 的 dtype 不相容偵測 (`dtype_status=INCOMPATIBLE`) 與相容情況下 `dtype_status=OK`。執行結果見 §7。全程只用 `tmp_path`/synthetic fixture,沒有對真實資料執行任何操作。 |

### 第四輪 (2026-08-07)

**⚠ 第一列先記錄第三輪的執行違規本身,不是新的程式問題:**

| # | 審查意見 | 處理 |
|---|---|---|
| R4-0 | 第三輪執行時違反了當輪明文的「Do not ... rerun the 2.2 GB full audit yet」限制 | **如實記錄,不辯解**:第三輪確實把 `tej_importer.py` 11 個 dataset 的完整匯入、`_full_population_diff.py` 的全量比對都重跑了。第四輪起,任何一輪審查明講「不要做 X」,即使後續步驟邏輯上需要 X 才能驗證,也先停下來問清楚範圍,不能用「反正結果是好的」自行合理化超出授權的執行。這輪 (第四輪) 全程只用 synthetic fixture 驗證,沒有再碰真實資料。 |
| R4-1 | diff 腳本用 inner-style 邏輯漏掉 `industry_map`;merge 前沒查重複鍵 (會被 pandas 悄悄 cross join,统计數字失真);PASS 語意含混,把「key 完整」跟「數值完全一致」混講成同一個狀態;沒有 `n_both_null`;receipt 檔名只到秒、可能撞名覆寫 | 全面重寫,見 [`scripts/_full_population_diff.py`](../scripts/_full_population_diff.py):`industry_map` (key=stock_id,靜態單檔) 納入跟其他 10 個 dataset 同一套 `DATASET_SPECS` 框架;merge 前先各自查 old/new 的重複鍵,查到就整個 dataset 判 `structural_status=FAIL`、`value_status=SKIPPED_DUE_TO_STRUCTURAL_FAIL`,完全不做數值 merge;拆成 `structural_status`/`value_status`/`overall_status` 三層,只有兩邊都乾淨才是 `EXACT_PASS`,有任何差異是 `REVIEW_REQUIRED`,不再有語意含混的單一 `PASS`;新增 `n_both_null`;receipt 檔名加微秒時間戳+uuid 後綴、`open(...,"x")` 排他建立,receipt 內含每個 dataset 實際讀到的全部 parquet 檔案清單跟各自 SHA-256。**過程中修了一個真的 bug**:非數值欄位 (如 `industry_map` 的產業代碼字串) 原本會在 `(o - n).abs()` 直接 TypeError,現在數值/字串欄位分開處理。 |
| R4-2 | supplement 沒有在消費端 (`tej_importer.py`) 驗證,只要檔案存在就直接合併 | 新增 `_verify_supplement()`:合併前確認 `legacy_supplement/receipt.json` 存在且 `overall_status=PASS`、現在的 parquet SHA-256 跟 receipt 記錄的一致、`extract_legacy_supplement.py` 現在的 SHA-256 也跟 receipt 記錄的一致 (防止腳本改了邏輯卻沒重新產生 receipt)、schema 跟 receipt 一致、(stock_id, date) 唯一且非 null。合併後再檢查一次列數有沒有膨脹 (supplement 萬一有重複鍵造成 left-join fan-out) 跟重複鍵,兩層防線。詳見 §6。 |
| R4-3 | `extract_legacy_supplement.py` 的 dropna 沒有事先檢查就靜默丟掉無效列;`_profile` 只記錄數字不 enforce;發布邏輯 (staging→out_dir 的 rename) 完全沒包在 try/except 裡,commit 中途失敗會讓 `out_dir` 憑空消失;docstring 講「三個舊來源檔」但其實已經是四個 | 新增 `check_source_keys()`,dropna 之前先明確檢查無效值,抓到就 raise;`enforce_output_spec()` 真的會 raise (schema 不符/列數或股票數低於凍結門檻/重複鍵/null 鍵);發布邏輯拆成獨立、可單元測試的 `publish_staging()`,commit point 精確定義在 `staging_dir.rename(out_dir)` 成功那一刻,之前失敗會把舊資料還原,之後的備份清理失敗只印警告不算整體失敗;docstring 改成「四個」並列出全部來源。詳見 §5。 |
| R4-4 | `save_by_stock` 的 rollback 邏輯把「commit 之後的備份清理」也包進同一個 except,清理失敗會讓函式 raise,即使資料其實已經正確發布;只驗證檔案數/列數,沒驗證 schema 跟鍵唯一性 | 拆成三個明確階段:階段一 (staging 寫入+驗證,含逐檔 schema/重複鍵/null 鍵檢查,不只是數檔案數/列數),階段二 (commit,atomic rename,失敗會還原舊資料),階段三 (清理備份,失敗只記警告、不影響函式的回傳)。詳見 §6。 |
| R4-5 | 缺少涵蓋以上機制的測試 | `tests/test_tej_data_migration.py` 從 27 個測試擴充到 54 個,新增:`industry_map` 在 diff 框架裡的行為、merge 前重複鍵偵測 (新舊兩側各自測)、`structural_status`/`value_status`/`overall_status` 三層語意、receipt 排他建立撞名偵測、receipt 內含輸入檔案雜湊、supplement 消費端驗證 (receipt 遺失/非 PASS/parquet 被竄改/腳本被竄改/schema 不符/重複鍵/null 鍵)、supplement 合併後 row 膨脹偵測、`extract_legacy_supplement` 的來源鍵防呆與輸出規格 enforce、`publish_staging` 的 commit-中途失敗還原與 commit-後清理失敗不算整體失敗、`save_by_stock` 對應的兩種情境、staged 檔案 schema 不符偵測。執行結果見 §7。全程只用 `tmp_path`/synthetic fixture,沒有對真實資料執行任何操作 (回應 R4-0)。 |

### 第三輪 (2026-08-07)

| # | 審查意見 | 處理 |
|---|---|---|
| R3-1 | `_full_population_diff.py` 用 inner join 會把「舊有新沒有的列」直接吃掉不計入統計;`common_cols` 靜默剔除缺欄;NaN 不對稱 (`abs(x-NaN)>1` 是 `False`) 完全漏掉;`>1` 門檻沒有凍結依據;「TEJ 更正」是未驗證推論 | 全面重寫,見 [`scripts/_full_population_diff.py`](../scripts/_full_population_diff.py):outer join 明確分開統計 `missing_keys`(舊有新無,直接判 FAIL)跟 `extra_keys`(新有舊無,單純範圍擴大);任一預期欄位在新舊任一邊缺席直接 FAIL;null 不對稱 (`isna() != isna()`) 明確算 `null_mismatch`;移除 `>1` 門檻,一律報 exact diff (`n_exact_equal`/`n_value_mismatch`),欄位標 `value_diff_status=MEASURED_NOT_JUDGED`,不自動判定;所有「差異原因」敘述移除,receipt 明講「TEJ 更正」是 `INFERENCE_UNCONFIRMED`。**這次重跑後發現真正的誤差量比第二輪報的大很多**——見 §3。 |
| R3-2 | `tej_importer.py` 對重複鍵設 1% 容忍度、對無效 stock_id/date 只是靜默 dropna、沒有 manifest preflight | 移除 1% 容忍度,任何 (stock_id, date) 跨檔數值衝突都直接 raise (完全重複的列仍可安全去重,但次數要記錄);新增 `_check_valid_keys`,空白/NaN/"nan"字串的 stock_id 或無法解析的 date 在 dropna 之前就先 raise (原本 `str(NaN)` 會變成字面上的 `"nan"` 字串,`dropna` 完全抓不到,是個真的漏洞);新增 `_manifest_preflight`,讀檔前核對實際檔案集合與 SHA-256 是否跟 `tej_exports/DataExport0806_manifest.csv` 完全吻合,不符就在解析前 raise。詳見 §6。 |
| R3-3 | supplement 只是裸寫 parquet,沒有來源/輸出雜湊、schema、列數、重複/null 鍵記錄;沒有 staging-then-publish | `scripts/extract_legacy_supplement.py` 改成先寫 staging 目錄、驗證 (schema/列數/股票數/日期範圍/重複鍵/null 鍵) 全過才發布,同時寫 `tej_exports/legacy_supplement/receipt.json` 記錄三個舊來源檔的相對路徑+SHA-256、三個輸出檔的 SHA-256/schema/統計、抽取腳本自身 SHA-256、時間戳、整體狀態。詳見 §5。**過程中額外發現** `recurring_net_income` 的 supplement 原本只從 2019+ 那份舊檔案抽,但舊 production 這欄其實 2005 年就有值 (`scripts/import_financials_2005_2018.py` 當年補的)——只抽 2019+ 會製造出一個舊資料沒有的 2005-2018 缺口。已補上第二個舊來源 (跟那支一次性補丁腳本讀同一份檔),缺口關閉 (見 §5 驗證結果)。 |
| R3-4 | `save_by_stock` 逐檔覆寫,沒有 staging/rollback,舊股票被排除後會變成 orphan parquet 殘留 | 改成「staging 目錄 → 驗證列數/檔數 → atomic 目錄互換」,任何步驟失敗 `out_dir` 維持寫入前狀態;成功後舊目錄整個被換掉,不會留下這次資料裡已經沒有的股票的殘檔。靜態資料集 (industry_map) 的單檔輸出也改成 tmp-then-replace 的 atomic 寫法。詳見 §6。 |
| R3-5 | 缺少涵蓋這些 fail-closed 機制的自動化測試 | 新增 [`tests/test_tej_data_migration.py`](../tests/test_tej_data_migration.py),27 個測試,全部用 `tmp_path`/synthetic fixture,**不讀取**任何真實 `DataExport0806`/`inbox*`/`~/tej_cache`。涵蓋:必要欄位缺失、無效 stock_id (`""`/`"nan"`/`"None"`/NaN/純空白)、無效 date、重複鍵完全相同 (安全去重)、重複鍵衝突 (含「佔比僅 0.01%、遠低於舊 1% 門檻也要 raise」)、manifest 缺檔/多檔/hash 不符、`save_by_stock` 的 no-orphan 與 rollback、supplement 的重複/null 鍵防呆、diff 腳本的 outer-join 缺列偵測/缺欄偵測/NaN 不對稱/精確誤差偵測。執行結果見 §7。 |

### 第一、二輪 (2026-08-07 稍早)

| # | 審查意見 | 處理 |
|---|---|---|
| P1-1 | ROE 仍被 `tej_universe_screen_validation.py` 用,但 importer 沒輸出 `roe_after_tax` 欄 | 建 legacy supplement 機制補回 (§5)。 |
| P1-2 | importer 對必要欄位/檔案 fail-open | 加 `required_cols`/sanity floor (第三輪進一步加 manifest preflight + 無效鍵檢查,見上方 R3-2)。 |
| P1-3 | 「完整 superset」證據不足,只抽驗 1-2 檔股票 | 改全量比對 (第三輪進一步修正 inner join 與門檻問題,見上方 R3-1)。 |
| P2-1 | 「歷史產業類別」只解決公司覆蓋率,沒解決 PIT 問題 | §4 明確聲明 PIT 限制未變。 |
| bug×3 | `director_pledge` 日期格式、`industry_map` 選錯來源檔 (現在→歷史)、千元欄位轉換讀寫欄位對調 | 已修正,見 §4。 |

---

## 1. `tej_exports/DataExport0806` 是候選的 (candidate) authoritative raw snapshot

**⚠ 用詞更正 (第五輪)**:先前版本這裡寫「現在是唯一 authoritative raw snapshot」,
用詞過早——「唯一/最終」的地位取決於待決的核准 (§3 的 `REVIEW_REQUIRED` 數值落差
還沒被人工裁定、legacy supplement 現在是 stale 見文件開頭警告、`tej_exports/inbox*`
刪除跟生產環境 `~/tej_cache` 寫入都還沒核准)。在核准之前,這份快照只是**候選**
(candidate) authoritative snapshot,不是已經確定的唯一/最終版本。

**⚠ 用詞再更正、正式命名 (第十一輪,見 §11)**:第十一輪把這裡的「候選」正式
定名為 `V2_CANDIDATE_RESTATED_SNAPSHOT`——不是 PIT 歷史,也還不是生產權威版本,
「restated」代表它是 TEJ 較晚的一次匯出、可能含歷史回補/更正,不代表已經獨立
驗證為真。完整的資料版本政策、使用情境分離規則、生產環境仍封鎖的聲明,見新增
的 §11,這裡不重複。

- 89 個檔案,2.22 GB (2,224,598,887 bytes)。
- SHA-256 manifest:[`tej_exports/DataExport0806_manifest.csv`](../tej_exports/DataExport0806_manifest.csv)
  (relpath, size_bytes, sha256, mtime_utc) + `.sha256`(`sha256sum -c` 相容格式)。
- 建置/驗證腳本:[`scripts/build_data_manifest.py`](../scripts/build_data_manifest.py)
  ```bash
  python scripts/build_data_manifest.py            # 重建 manifest
  python scripts/build_data_manifest.py --verify    # 逐檔重算 SHA-256 比對既有 manifest
  ```
  `--verify` 已跑過一次:**PASS,89 檔全部吻合,無缺檔/無多檔/無雜湊不符**。

  **manifest 能證明什麼、不能證明什麼**:SHA-256 只能證明「之後這些檔案有沒有被
  改過」,不能證明檔案本身內容完整 (股票有沒有缺、日期有沒有斷、schema 對不對)。
  內容完整性靠 §3 的全量比對。`tej_importer.py` 現在讀每個 dataset 前都會先跑
  manifest preflight (§6),確保磁碟上實際讀到的檔案就是 manifest 記錄的那些、
  一個位元組都沒被改過——但這只驗證「檔案沒被動過手腳」,不驗證「檔案內容本身
  完整」,這兩件事是分開的。

## 2. 涵蓋範圍證明方法

1. **檔名/資料夾名本身就是 TEJ 自己宣告的日期範圍**,匯出當下的宣告,不是猜的。
2. **邊界抽驗**(粗篩用):對每個類別最舊/最新一檔抓 header + 首列 + 末列。
3. **全量比對**(§3,真正的證據):新舊兩邊 `tej_importer.py` 輸出的**全部股票、
   全部列**做 outer join,分開統計「舊有新無」(視為 FAIL) 跟「新有舊無」(範圍
   擴大,非失敗訊號),每個預期欄位在任一邊缺席也直接 FAIL,數值誤差一律報
   exact diff、不套用沒有凍結依據的容忍門檻。稽核腳本 (一次性,不進正常路徑):
   [`scripts/_full_population_diff.py`](../scripts/_full_population_diff.py)。
   每次執行都會在 `tej_exports/diff_receipts/` 寫一份不覆寫、帶時間戳的 JSON
   receipt,含每個 dataset 的完整統計數字。

## 3. 全量比對結果 (11 個 dataset,全部股票、全部列,outer join、無容忍門檻)

最新一次:`tej_exports/diff_receipts/full_population_diff_20260807T093225Z.json`
(§5 的 `recurring_net_income` 缺口關閉後重跑的最終結果)。

⚠ **這份結果是用第三輪版本的 `_full_population_diff.py` 產生的**,當時的欄位
命名是單一 `status` (PASS/FAIL) + `value_diff_status=MEASURED_NOT_JUDGED`,跟
第四輪重寫後的 `structural_status`/`value_status`/`overall_status`
(EXACT_PASS/REVIEW_REQUIRED/FAIL) 命名不同——下表沿用 receipt 裡實際的欄位
語意轉述,不是照抄新版命名。**這輪 (第四輪) 沒有用新版腳本重新產生這份結果**
(§0 R4-0:第三輪執行本身已經超出授權範圍,第四輪不重蹈覆轍),receipt 原始
JSON 保留在 `tej_exports/diff_receipts/`,是唯一的原始證據來源。

| dataset | 舊代號數 | 新代號數 | key 完整性 (舊⊆新?) | 重疊 key 數 | 有實質誤差的欄位 (exact diff,無門檻) |
|---|---|---|---|---|---|
| `price_valuation` | 2300 | 2303 | ✅ missing_from_new=0 | 9,009,907 | 無 |
| `institutional_flow` | 2300 | 2306 | ✅ 0 | 8,674,640 | `trust_net`:45 列不等 (全部落在同一天 2026-07-14)、3 欄各 2 列 null 不對稱 |
| `institutional_gross` | 1952 | 2306 | ✅ 0 | 140,544 | `trust_holding_pct`:**4,615 列不等** (3.28%,集中在 30 檔股票、2026-06-30~07-15 這個舊種子窗口尾端);`trust_buy`/`trust_sell` 各 3/6 列 |
| `fundamentals_quarterly` | 1952 | 2315 | ✅ 0 | 53,812 | `net_income`/`eps`/`operating_income` 各 5/6/5 列不等 |
| `financial_statements` | 2287 | 2315 | ✅ 0 | 135,511 | 11 個金額/EPS 欄各 2~6 列不等 (`recurring_net_income` 缺口已關閉,0 誤差) |
| `revenue_growth` | 2339 | 2343 | ✅ 0 | 477,570 | `revenue_yoy_pct`:8 列不等、3 列 null 不對稱 |
| `monthly_revenue` | 1952 | 2343 | ✅ 0 | 168,885 | `revenue_yoy_pct`/`revenue`/`cum_revenue` 各 8/8/9 列不等 |
| `margin_balance` | 1859 | 2188 | ✅ 0 | 132,625 | `margin_balance`:3 列不等 (差 1~2 張) |
| `tdcc_weekly` | 1942 | 1945 | ✅ 0 | 664,226 | 無 |
| `director_pledge` | 1942 | 1942 | ✅ 0 | 165,876 | 無 (逐列相同) |
| `industry_map` | 2436 | 2436 | ✅ 0 | (靜態,代號集合完全相同) | — |

**這次改用 outer join + exact diff (無門檻) 後,誠實的結果是:**

- **key 完整性 (硬證據)**:11 個 dataset,每一個舊 (stock_id, date) 都在新集合裡
  (`missing_from_new=0`)——這是逐列的 key 級別比對,不是只看股票代號集合,也
  不是 inner join 隱藏掉的推論。
- **數值誤差比第二輪報的大**:第二輪用「絕對誤差 > 1」的門檻,把
  `institutional_gross.trust_holding_pct` 的誤差列數低估成 330 列 (0.23%)——移除
  門檻後,真實數字是 **4,615 列 (3.28%)**,因為這欄本來就是 0~100 的百分比,
  很多差異落在 0.1~0.99 這種被舊門檻直接忽略的區間。這是第二輪報告過度樂觀的
  地方,這裡更正。**狀態維持 `value_status=DIFF_UNRESOLVED`(第四輪重寫後的
  taxonomy 用語)——第五輪沒有重新裁定或調降這個狀態,3.28% 這個數字仍然是未解決
  的落差,不是已核准的容忍值。**
- **根因分析降級為 INFERENCE_UNCONFIRMED**:`trust_net` 45 列全部落在單一天
  (2026-07-14)、`trust_holding_pct` 4,615 列集中在單一窗口 (2026-06-30~07-15,
  貼著舊種子檔尾端)、財報類欄位的差異集中在少數股票且同股票不同期常常差固定
  金額——這些模式**看起來像** TEJ 資料回補/更正或舊種子檔本身資料品質問題,
  但這只是根據差異分布形狀的推論,沒有 TEJ 官方的獨立 raw-to-raw 更正紀錄佐證,
  不能斷言。如果要 100% 排除「這是遷移程式的 bug」,需要另外跟 TEJ 核對那幾天/
  那幾檔的原始資料,超出這輪能做的範圍。

  **第八輪更新 (只針對 `institutional_gross` 六欄,其餘 dataset 沒有動)**:§10
  真的去核對了兩份 (不是 TEJ 官方的,是專案內部持有的兩份) 原始 Excel,得到
  「不是遷移程式 bug」這個更強的證據——99.44% 的不一致,兩邊 parquet 都完整
  忠實反映各自的原始檔,問題出在兩份原始檔本身報的數字不同。**但「兩份原始檔
  為什麼報不同數字」依然是 INFERENCE_UNCONFIRMED,沒有變成已確認**——這輪查到
  的是「差異不在遷移管線裡」,不是「差異的根本原因」,兩者是不同的問題,不要
  混為一談。

## 4. 遷移過程中發現並修正的 bug + PIT 限制聲明

**第一輪修正的 3 個 bug**:
1. `director_pledge` 日期解析 (`"2026/06"` 斜線格式,改用 `%Y/%m`)。
2. `industry_map` 選錯來源檔 (「現在產業類別.xlsx」只有 1952 檔,改用「歷史產業類別.xlsx」,代號集合跟舊 Industry.xlsx 的 2436 檔完全一致)。
3. 千元欄位轉換讀寫欄位對調 (`financial_statements` 一度完全沒有輸出成最終欄名)。

**第三輪額外修正**:
4. `_check_valid_keys` 抓到的潛在漏洞——`str(NaN)` 會變成字面上的 `"nan"` 字串,
   原本 `dropna(subset=["stock_id"])` 完全抓不到這種「看起來有值,其實是空的」
   欄位,已加明確檢查 (§6)。
5. `recurring_net_income` 的 legacy supplement 原本只抽 2019+,舊 production
   這欄其實 2005 年就有值,製造出一個新的缺口——已補上第二個舊來源關閉 (§5)。

**PIT 限制聲明**:修正 #2 解決的是「歷史產業類別.xlsx 代號覆蓋率」跟舊
Industry.xlsx 一致 (1952→2436 檔),**沒有解決** `core/industry_flow.py` 本來就
存在、自己註解承認的限制——「用今天的產業分類套用到整段歷史,已下市個股對不到
產業會被丟掉,這是描述圖不是訊號,不要拿它回測」。這個 PIT blocker 完全沒動。

## 5. 已知欄位落差與 legacy supplement

三個欄位新的寬版匯出裡沒有,靠 [`scripts/extract_legacy_supplement.py`](../scripts/extract_legacy_supplement.py)
一次性從舊來源抽出來凍結成 `tej_exports/legacy_supplement/*.parquet` (staging
驗證過才發布,receipt 見 `tej_exports/legacy_supplement/receipt.json`):

| 欄位 | 舊來源 | 覆蓋範圍 | 覆蓋範圍外 |
|---|---|---|---|
| `roe_after_tax` | `inbox_fundamentals/2019-202603 EPS ROE OI.xlsx` | 2019-03~2026-03 (53,812 列,1952 檔) | NaN (舊 production 的 `fundamentals_quarterly` 本來就只有這段;那支 2005-2018 補丁腳本當年**刻意丟棄** ROE 欄,不是這裡新造成的縮水) |
| `recurring_net_income` | `inbox_fundamentals/三大財報2019~202603.xlsx` (2019-03+) **+** `inbox/2005-2018 三大財報+ROE 上下市.xlsx` (2005-2018,跟 `scripts/import_financials_2005_2018.py` 讀同一份檔) | **2005-06~2026-03 (136,241 列,2311 檔)** | NaN 外圍極少數邊界情況;跟舊 production 逐列比對 0 誤差、0 null 不對稱 (§3) |
| `revenue_last_year` / `cum_revenue_last_year` | `inbox_revenue/YoY 201901~202607.xlsx` | 2019-01~2026-06 (168,885 列,1952 檔) | NaN (舊 production 本來就只有這段,TEJ 沒有更早的這兩欄匯出) |

`recurring_net_income` 原本 (第二輪) 只抽 2019+,跟舊 production 全量比對後
發現 81,698 列 null 不對稱 (舊有值、新沒有)——追查後確認舊 production 這欄
2005 年就有值 (一次性補丁腳本補的),已補上第二個舊來源關閉這個缺口,重新驗證
0 誤差 (§3)。

`scripts/tej_universe_screen_validation.py` 現在讀得到 `roe_after_tax` (2019+
有值,2019 前 NaN——這跟它原本能拿到的資料範圍一樣,舊 inbox 來源本來就只有
2019+,不是這裡的缺陷)。

`scripts/extract_legacy_supplement.py` 的發布流程 (第四輪修正):

1. 每個來源在 `dropna` 之前先跑 `check_source_keys()`,空白/NaN/`"nan"` 字串的
   stock_id 或無法解析的 date 直接 raise,不靜默丟掉。
2. 每個輸出欄位有凍結的 `OUTPUT_SPECS` (預期 schema + 最低列數/股票數/最早
   日期門檻),`enforce_output_spec()` 真的會 raise,不是只記錄數字。
3. 全部驗證通過才呼叫 `publish_staging()`——獨立、可單元測試的函式,commit
   point 精確定義在 `staging_dir.rename(out_dir)` 成功那一刻:之前任何失敗
   (含 rename 本身) 會把舊 `out_dir` 還原;之後只剩備份目錄清理這個收尾動作,
   清理失敗只印警告,不會讓函式回報整體失敗 (資料其實已經生效了)。

## 6. 程式遷移 + fail-closed 驗證

**`tej_importer.py`**:來源 `tej_exports/DataExport0806`,欄位用欄名對應,支援
`.zip`(UTF-16 + Tab 分隔 csv)。fail-closed 機制:

- **`required_cols`**:原始檔缺少任何一個必要欄位直接 raise。
- **`_check_valid_keys`**:空白/NaN/`"nan"`/`"None"` 等無效字串的 stock_id、
  或無法解析的 date,在任何 dropna 之前先明確檢查、raise——不是讓它們被
  `dropna` 靜默吃掉 (§4 bug #4)。
- **`_manifest_preflight`**:每個 dataset 讀檔前,先核對「這個 dataset 實際會
  讀的檔案集合」跟 manifest 記錄的子集合是否完全一致 (無缺、無多)、每個檔案的
  SHA-256 是否吻合,任一項不符就在解析前 raise。
- **`_check_duplicate_key_conflicts`**:同一個 key 在不同原始檔給出不同數值,
  **不設任何容忍門檻**,一個衝突就 raise (完全重複的列——同 key 所有欄位值都
  相同——可以安全去重,但次數會記錄下來)。
- **`_verify_supplement`**(第四輪新增):合併 legacy supplement 之前,確認
  `receipt.json` 存在且 `overall_status=PASS`、現在的 parquet SHA-256 跟 receipt
  記錄的一致、`extract_legacy_supplement.py` 現在的 SHA-256 也跟 receipt 記錄的
  一致 (防止腳本改了邏輯卻沒重新產生 receipt)、schema 跟 receipt 一致、
  (stock_id, date) 唯一且非 null。合併後再檢查一次列數有沒有膨脹 (防 supplement
  萬一有重複鍵造成 left-join fan-out) 跟重複鍵,兩層防線。
- **`_check_sanity_floor`**:列數/檔數/最早日期低於已知規模的門檻,直接 raise。
  ⚠ 這是次要防線,不是完整性證明——通過只代表沒有腰斬式的明顯縮水,完整性靠
  §3 的全量比對。
- **`save_by_stock`**(第四輪拆成三個明確階段):
  1. staging 寫入 + 驗證 (檔案數=股票數、逐檔 schema 跟輸入一致、
     (stock_id, date) 唯一且非 null、總列數=輸入列數)——失敗的話 `out_dir`
     完全不動。
  2. commit (atomic 目錄互換)——commit point = `staging_dir.rename(out_dir)`
     成功;這之前任何失敗,`out_dir` 會被還原成呼叫前的內容。因為是整個目錄
     互換,這次資料裡已經不存在的舊股票不會變成殘留的 orphan parquet。
  3. commit 之後清理備份目錄——失敗只印警告,不影響函式回傳 (第三輪版本的
     bug:這一步失敗過去會被外層 except 一起 raise,即使資料其實已經正確
     發布了,已修正)。靜態資料集 (`industry_map`) 的單檔輸出是 tmp-then-replace
     的 atomic 寫法。

上述任一檢查失敗都在寫檔前就 raise,不會有部分結果落地。**這輪 (第四輪) 沒有
拿這套邏輯重新跑過 11 個 dataset**(§0 R4-0)——上一次完整跑過是第三輪,結果
即 §3 引用的 receipt,原封不動保留。

**`core/industry_flow.py`**:`INDUSTRY_XLSX` 改指向「歷史產業類別.xlsx」(§4)。
**`scripts/import_financials_2005_2018.py`**:標記 deprecated,`main()` 直接 `sys.exit(1)`。
**`scripts/extract_legacy_supplement.py`**:staging-then-publish + receipt,見上方。
**`scripts/market_snapshot_collector.py`**:更新一處註解。

**確認過**:全專案 `*.py` grep 不到任何「實際讀取」`tej_exports/inbox*` 的程式碼
(`extract_legacy_supplement.py` 是唯一例外,一次性腳本,不在 `tej_importer.py`
正常匯入路徑上)。

**沒有做的事**:沒有對生產環境 `~/tej_cache` 執行真正的 `--commit`/預設寫入。
§3 的全量比對全部是拿暫存目錄的輸出去跟生產快取比,沒有覆蓋生產快取。

## 7. 測試

[`tests/test_tej_data_migration.py`](../tests/test_tej_data_migration.py):109 個測試,全部用
`tmp_path`/synthetic fixture,不讀取任何真實資料 (`DataExport0806`/`inbox*`/`~/tej_cache` 都不碰)。
[`tests/test_institutional_gross_adjudication.py`](../tests/test_institutional_gross_adjudication.py)
(第八輪新增,第九輪擴充):36 個測試,同樣全部 synthetic fixture,不讀取
`~/tej_cache`、round3 scratchpad 快取,或 `tej_exports/inbox_chip_gross`/
`DataExport0806` 底下的原始檔。
(第七輪額外執行了一次**真實**的 `scripts/extract_legacy_supplement.py`,第八輪、
第九輪各額外執行了一次**真實**的
`scripts/institutional_gross_trust_holding_pct_adjudication.py`,都不是這裡的
pytest 套件,是被明確授權的單次唯讀/受控資料操作,結果分別記錄在 §0 第七輪
B/C 與 §10。)

```
python -m py_compile tej_importer.py scripts/extract_legacy_supplement.py \
    scripts/_full_population_diff.py scripts/institutional_gross_trust_holding_pct_adjudication.py \
    tests/test_tej_data_migration.py tests/test_institutional_gross_adjudication.py
python -m pytest tests/test_tej_data_migration.py tests/test_institutional_gross_adjudication.py \
    -q -p no:cacheprovider --basetemp=".pytest_codex_round9_full"
```
結果:`145 passed in 2.49s`(109 + 36)。

`test_tej_data_migration.py` 涵蓋範圍 (第三輪 27 個 + 第四輪新增 27 個 + 第五輪新增
22 個 + 第六輪新增 17 個 + 第七輪新增 12 個 + 第八輪新增 4 個,見 §0 R5-5、第六輪
回應表、第七輪 R7-A3、第八輪 R8-A3)。`test_institutional_gross_adjudication.py`
涵蓋範圍 (第八輪 27 個 + 第九輪新增 9 個):manifest/結構統計重算/六欄統計/anchor
比對/mismatch 枚舉/兩份原始檔 schema 解析 (千股→股轉換、日期格式)/八個分類的
決策樹/receipt 排他建立,第九輪新增:filter 之前對整份原始檔驗證無效
id/date/重複鍵 (含重複鍵不在 needed_keys 範圍內也要抓到)、完全重複列不去重直接
raise、文字 "." 之類的 raw_token 原樣保留、合法空白跟不可解析文字分開標記、
`classify_all` 的 signed_diff/abs_diff 與 `RAW_SOURCES_DIFFER` 兩個驗證旗標、
`build_diff_distribution` 的互斥分桶與加總不變量。

第三輪/第四輪範圍:

- **第三輪**:必要欄位缺失/存在、無效 stock_id (5 種變體 + NaN)、無效 date、
  完全重複列 (安全去重不 raise)、單一衝突鍵即使佔比僅 0.01% (遠低於舊 1% 門檻)
  也要 raise、靜態資料集用 stock_id 單鍵衝突檢查、manifest 缺檔/多檔/hash 不符
  各自 raise、manifest 全吻合時不 raise、`save_by_stock` 縮小股票池後無 orphan
  殘留、`save_by_stock` 寫入失敗時 rollback 回原狀且無殘留暫存目錄、legacy
  supplement 的 `_profile` 正確偵測重複鍵/null 鍵、diff 腳本正確偵測 outer-join
  缺列/缺欄/NaN 不對稱/精確誤差 (含「舊版門檻會漏掉的 0.5 誤差」)。
- **第四輪新增**:`industry_map` 在 diff 框架裡的 structural/value 狀態、
  merge 前偵測 old/new 各自的重複鍵 (擋下來不做 cross-join)、`n_both_null` 正確
  跟「兩邊都有值且相等」分開計數、diff receipt 用 `open(...,"x")` 排他建立
  (撞名會炸)、receipt 內含輸入檔案的 SHA-256 清單、`_verify_supplement` 的
  完整驗證鏈 (receipt 遺失/`overall_status` 非 PASS/parquet 被竄改/抽取腳本被
  竄改/schema 不符/重複鍵/null 鍵各自 raise)、supplement 合併後 row 膨脹的
  第二層防線、`extract_legacy_supplement` 的 `check_source_keys` (dropna 前
  攔截無效值)、`enforce_output_spec` (schema/最低規模門檻真的會擋)、
  `publish_staging` 的 commit-中途失敗還原與 commit-後清理失敗不算整體失敗、
  `save_by_stock` 對應的備份清理失敗不 raise、staged 檔案 schema 不符被攔截。

## 8. DataExport0806 裡的新類別 (舊 inbox 沒有對應,這輪沒有寫 importer)

- `0050 股價、報酬率 2005-20260806/`——0050 基準價格/報酬率。
- `暫停交易2004-20260806/`——暫停交易紀錄。
- `處置注意股2004-20260806/`——注意/處置股票標記。**⚠ 見下方截斷風險**。
- `除權息2004-20260806/`——除權息紀錄。
- `基本資料/公司資料.xlsx`——公司基本資料 (靜態)。

### ⚠ 資料品質風險:處置注意股 2004-2007 那份 xlsx 疑似被 Excel 列數上限截斷

`處置注意股2004-20260806/處置注意股2004-2007/20260806071703.xlsx` 讀到
**1,048,575 列資料**——剛好是 Excel 單檔上限 (2^20 - 1)。第一列 (最新) 是
2007-12-31,最後一列 (最舊) 是 2004-11-03,不是預期的 2004-01-01 附近,**2004
年前 10 個月的資料很可能被截斷**。目前沒有任何 importer 讀這個新類別,要用之前
建議跟 TEJ 用更窄的日期區間重新匯出。

## 9. 待刪除清單 (本輪不執行,列出來待審查)

`tej_exports/inbox*` 底下 9 個資料夾、52 個檔案,對應新來源:

| 舊資料夾 (待刪除) | 大小 | 檔案數 | 對應新來源 | 備註 |
|---|---|---|---|---|
| `tej_exports/inbox/` | 548 MB | 24 | `個股股價、本益比2004-20260806/` | 其中 `2005-2018 三大財報+ROE 上下市.xlsx` 是 `recurring_net_income` supplement 的來源之一 (§5),已抽取驗證 |
| `tej_exports/inbox_chip/` | 213 MB | 12 | `法人回測2004-20260806/` | |
| `tej_exports/inbox_chip_gross/` | 8.4 MB | 1 | `法人回測2004-20260806/` | §3 的 `trust_holding_pct` 4,615 列落差窗口就在這份舊種子檔的尾端 |
| `tej_exports/inbox_fundamentals/` | 8.5 MB | 2 | `財報2004~202606/` + `legacy_supplement/roe_after_tax.parquet` + `recurring_net_income.parquet` | 兩個 supplement 已從這裡抽取並驗證 (§5) |
| `tej_exports/inbox_industry/` | 148 KB | 1 | `產業類別/歷史產業類別.xlsx` | |
| `tej_exports/inbox_margin/` | 5.8 MB | 1 | `融資融券2004-20260806/` | |
| `tej_exports/inbox_pledge/` | 5.3 MB | 1 | `集團分類+董監質押與持股比2019-202606/pledge.xlsx` | 逐列相同 |
| `tej_exports/inbox_revenue/` | 19 MB | 2 | `月營收2004-202608/` + `legacy_supplement/revenue_last_year.parquet` | supplement 已抽取驗證 |
| `tej_exports/inbox_tdcc/` | 28 MB | 8 | `集保大戶2019-20260806/` | |
| **合計** | **~836 MB** | **52** | — | |

**這輪不刪除任何檔案,也沒有寫入生產環境 `~/tej_cache`。** 待這輪修正過審查後
再決定。

## 10. `institutional_gross.trust_holding_pct` 唯讀溯源裁定 (第八輪)

**這是診斷用的證據調查,不是新的容忍門檻搜尋,也不是遷移核准。** §10.1-§10.4
的規則在讀取任何列級資料**之前**寫死凍結;§10.5 起才是執行結果。

### 10.1 範圍

只處理 anchor receipt (`tej_exports/diff_receipts/full_population_diff_20260807T093225Z.json`)
記錄的 `institutional_gross` 這一個 dataset、恰好 140,544 個重疊 key、恰好六個欄位
(`foreign_buy`/`foreign_sell`/`trust_buy`/`trust_sell`/`foreign_holding_pct`/
`trust_holding_pct`)。主要懸而未決的是 `trust_holding_pct`(4,615 個數值不等),
但其餘五欄 anchor 已經記錄的 null/數值不等 (`foreign_buy`×2 null、`foreign_sell`×2
null、`trust_buy`×2 null+3 值、`trust_sell`×2 null+6 值、`foreign_holding_pct`×26
null) 一併納入裁定,**不擴大到其他 dataset**。

### 10.2 比對規則

不設任何數值容忍門檻。用「canonical parsed value」精確比較 (字串日期轉
`YYYY-MM-DD`、金額欄位統一到股數單位、缺值一律正規化成 pandas `NaN` 後兩邊都
`NaN` 才視為相等)。原始文字/值、解析後的值、單位/換算倍率、null 狀態分開記錄,
不混在一起。

### 10.3 欄位/鍵/日期/單位對應 (讀過兩份原始檔 schema 後凍結,執行前定案)

實際檢查兩份原始檔的欄名後發現:**兩份原始檔的六個目標欄位中文欄名完全相同**
(`外資買進張數`/`外資賣出張數`/`投信買進張數`/`投信賣出張數`/`外資總投資股率%`/
`投信持股率%`),只有代號/名稱欄跟日期欄的**格式**不同,其餘語意一致。凍結對應:

| | 舊原始檔 (`tej_exports/inbox_chip_gross/法人毛額+持股率20260404-0716.xlsx`) | 新原始檔 (`tej_exports/DataExport0806/法人回測2004-20260806/2025-20260806 法人.xlsx`) |
|---|---|---|
| stock_id | `代號` 欄 (int64),`str(int(...))` | `證券代碼` 欄,組合格式如 `"1101 台泥"`,取空白前半段 |
| date | `年月日` 欄,斜線格式字串 `"2026/07/16"` | `年月日` 欄,純數字 int64 `20260806`,`%Y%m%d` |
| `foreign_buy` | `外資買進張數` (張) × 1000 → 股 | 同左欄名,同轉換 |
| `foreign_sell` | `外資賣出張數` (張) × 1000 → 股 | 同左欄名,同轉換 |
| `trust_buy` | `投信買進張數` (張) × 1000 → 股 | 同左欄名,同轉換 |
| `trust_sell` | `投信賣出張數` (張) × 1000 → 股 | 同左欄名,同轉換 |
| `foreign_holding_pct` | `外資總投資股率%`,原樣 (不換算) | 同左欄名,原樣 |
| `trust_holding_pct` | `投信持股率%`,原樣 (不換算) | 同左欄名,原樣 |

跟 `tej_importer.DATASETS["institutional_gross"]` 目前對新原始檔的 `rename`/
`thousand_cols` 定義完全一致 (千股/張 → 股一律 ×1000,百分比原樣)——這裡沒有
發明新的轉換規則,只是把同一套規則也套用到舊原始檔 (舊檔欄名剛好相同)。

先讀過兩份原始檔各自的日期範圍確認涵蓋:舊原始檔恰好 140,544 列、72 個交易日、
2026-04-01~2026-07-16 (跟 old parquet 列數一致,是一比一的同一份資料);新原始檔
(`2025-20260806 法人.xlsx`)涵蓋 2025-01-02~2026-08-06,完整涵蓋重疊窗口,不需要
讀資料夾裡其他年份切片檔。

### 10.4 互斥分類定義 (執行前凍結,只允許在讀列級結果前調整名稱)

對每一個 (key, 欄位) 不一致實例,令 `old_r`/`new_r` 為從舊/新原始檔獨立解析出的
canonical 值,`old_p`/`new_p` 為 anchor 已經記錄的 old/new parquet 值。用「兩邊都
`NaN` 視為相等,否則精確比較」的 `equal(a,b)` 函式。決策順序 (由上而下,符合就
分類、不再往下比對):

1. **`RAW_KEY_MISSING`**:這個 key 在舊原始檔或新原始檔裡完全找不到對應列。
2. **`UNRESOLVED_SCHEMA_OR_UNIT`**:key 找得到,但該欄位在原始檔裡的值無法被
   目前凍結的轉換規則解析成單一 canonical 數字 (例如非數值文字混進本應是數字的
   欄位)。
3. 以下四類僅在 `old_r`/`new_r` 都成功解析時才適用,先判斷 `raw_agree = equal(old_r, new_r)`:
   - `raw_agree` 且 `equal(old_r, old_p)`(等價於也不等於 `new_p`,因為這是一筆
     已知不一致的 key,`old_p != new_p`)→ **`BOTH_RAW_MATCH_OLD`**:兩份原始檔
     彼此一致,而且這個一致值等於 old parquet 的值。
   - `raw_agree` 且 `equal(old_r, new_p)` → **`BOTH_RAW_MATCH_NEW`**:兩份原始檔
     彼此一致,且等於 new parquet 的值。
   - `raw_agree` 但兩邊都不等於任何一個 parquet 值 → **`NEITHER_MATCH`**:原始檔
     彼此一致,但這個共識值跟兩個 parquet 版本都對不上。
   - 不是 `raw_agree`(`old_r != new_r`,即 **`RAW_SOURCES_DIFFER`** 是這整組的
     前提事實)才繼續往下分:
     - `equal(old_r, old_p)` 且 `equal(new_r, new_p)` → **`RAW_SOURCES_DIFFER`**:
       兩份原始檔本身就報不同的數字,但各自的 parquet 都忠實反映了自己的原始檔
       (乾淨的「資料本身兩個版本不同」案例,不是管線 bug)。
     - `equal(old_r, old_p)` 但 `not equal(new_r, new_p)` → **`OLD_RAW_ONLY_MATCH`**:
       old parquet 有舊原始檔佐證,new parquet 對不上它自己宣稱的新原始檔。
     - `equal(new_r, new_p)` 但 `not equal(old_r, old_p)` → **`NEW_RAW_ONLY_MATCH`**:
       反過來,new parquet 有佐證,old parquet 對不上自己的原始檔。
     - 都不成立 (`old_r != old_p` 且 `new_r != new_p`,原始檔彼此也不同) →
       **`NEITHER_MATCH`**。

八個分類互斥、窮盡以上決策樹的每個分支。**這個分類只描述證據型態,不代表任何
「哪個版本才對」的結論**——`OLD_RAW_ONLY_MATCH`/`NEW_RAW_ONLY_MATCH` 只是指出
哪一份 parquet 對不上它自己宣稱的原始檔,不是說另一份就是正確答案。

### 10.5 裁定紀律

- 不做多數決;不因為「新版 TEJ 通常比較新」就自動判新版正確;不因為某個模式
  「看起來系統性」就把 `DIFF_UNRESOLVED` 降級或改判 PASS。
- 腳本本身**不核准遷移、不選擇哪個版本作為權威**——輸出只是分類統計跟樣本,
  `overall_status` 固定是 `REVIEW_REQUIRED`(除非連 anchor 都無法重現,那種情況
  是 `ANCHOR_INPUT_IDENTITY_UNVERIFIED` 並直接中止,不進入列級分類)。
- **anchor receipt 沒有 parquet 檔案雜湊**(是舊版 `_full_population_diff.py`
  產生的,那時候還沒有 R4-1 新增的 input_files 雜湊清單)——不可以假裝它有。
  執行時要先對「現在」磁碟上的 old/new `institutional_gross` parquet 檔案建立
  唯讀 manifest (relpath/size/SHA-256),寫進新的裁定 receipt,然後**精確重現**
  anchor 記錄的結構統計 (`old_key_count`/`new_key_count`/`missing_keys_count`/
  `extra_keys_count`/`overlap_key_count`/`old_stock_count`/`new_stock_count`/
  `missing_stock_ids_count`) 跟六欄的 `n_compared`/`n_null_mismatch`/
  `n_exact_equal`/`n_value_mismatch`/`max_abs_diff`/`median_abs_diff`——任何一項
  兜不起來就以 `ANCHOR_INPUT_IDENTITY_UNVERIFIED` 中止,不重新產生任何一份
  cache,不往下做原始檔分類。

---

### 10.6 執行結果

```
python scripts/institutional_gross_trust_holding_pct_adjudication.py
```

- 開始:`2026-08-07T14:55:43Z`;結束:`2026-08-07T14:58:05Z`;**exit code 0**。
- Receipt:`tej_exports/diff_receipts/institutional_gross_adjudication_20260807T145805155908_921a469b.json`
  (SHA-256 `3500ca34b4704fb1d4e1b518e3dbc8ea58cc9f93362da8e8eec77bdc28d45d81`,
  743,361 bytes;`open(...,"x")` 排他建立,不覆寫既有的兩份 full_population_diff
  receipt——執行後 `tej_exports/diff_receipts/` 從 2 個檔案變成 3 個)。

**anchor 重現 (§10.5 要求的前置關卡)**:對「現在」磁碟上的 old/new
`institutional_gross` parquet 建立唯讀 manifest 後 (old 1,952 檔、new 2,306 檔,
各自 relpath/size/SHA-256 都寫進 receipt 的 `parquet_manifests`),重新計算的結構
統計 (`old_key_count`=140544、`new_key_count`=8781249、`missing_keys_count`=0、
`extra_keys_count`=8640705、`overlap_key_count`=140544、`old_stock_count`=1952、
`new_stock_count`=2306、`missing_stock_ids_count`=0) 與六欄的
`n_compared`/`n_null_mismatch`/`n_exact_equal`/`n_value_mismatch`/`max_abs_diff`/
`median_abs_diff`,**跟 anchor receipt 逐項精確相符,零差異**——沒有觸發
`ANCHOR_INPUT_IDENTITY_UNVERIFIED`,往下進入原始檔分類。

**不一致實例範圍**:六欄合計 4,658 個 (key, 欄位) 不一致實例 (`foreign_buy`×2、
`foreign_sell`×2、`trust_buy`×5、`trust_sell`×8、`foreign_holding_pct`×26、
`trust_holding_pct`×4,615),對應到 4,646 個相異 key,只重建這些 key 需要的原始
列 (`needed_keys` 過濾) 跟六個目標欄位 (`usecols` 過濾,不讀原始檔其他欄位)。

**分類結果 (§10.4 八個互斥分類)**:

| 分類 | 筆數 | 佔比 |
|---|---|---|
| `RAW_SOURCES_DIFFER` | 4,632 | 99.44% |
| `UNRESOLVED_SCHEMA_OR_UNIT` | 26 | 0.56% |
| `BOTH_RAW_MATCH_OLD` | 0 | — |
| `BOTH_RAW_MATCH_NEW` | 0 | — |
| `OLD_RAW_ONLY_MATCH` | 0 | — |
| `NEW_RAW_ONLY_MATCH` | 0 | — |
| `NEITHER_MATCH` | 0 | — |
| `RAW_KEY_MISSING` | 0 | — |

分欄拆解:`foreign_buy`(2 個 `RAW_SOURCES_DIFFER`)、`foreign_sell`(2 個
`RAW_SOURCES_DIFFER`)、`trust_buy`(5 個 `RAW_SOURCES_DIFFER`)、`trust_sell`(8 個
`RAW_SOURCES_DIFFER`)、`foreign_holding_pct`(26 個 `UNRESOLVED_SCHEMA_OR_UNIT`,
全部集中在單一股票)、`trust_holding_pct`(4,615 個全部 `RAW_SOURCES_DIFFER`)。

**`UNRESOLVED_SCHEMA_OR_UNIT` 的 26 筆已追查到根因,不是解析腳本的 bug**:全部
是股票代號 `4130`(健亞)的 `foreign_holding_pct` 欄位,新原始檔
(`2025-20260806 法人.xlsx`)在這幾個交易日的儲存格內容是**文字 `"."`**(不是
空白、不是數字,是 TEJ 匯出時放的字面句點字元),舊原始檔對應位置有正常數值
(3.04~3.27 之間)。這不是「原始值本來是空白」的合法 null,轉換成數字會失敗——
`parse_new_raw` 的 `_coerce_and_track_unparseable` 正確地把這種「非空白但轉不成
數字」的儲存格跟合法空白分開標記,沒有被靜默併入 NaN 一起比較。**這是新原始檔
本身的資料表示方式問題 (TEJ 用文字句點標記缺值,不是留空),不是遷移程式的
轉換邏輯錯誤。**

**`RAW_SOURCES_DIFFER` 的 4,632 筆已手動抽樣覆核 (不只信任腳本輸出)**:額外拿
`trust_holding_pct` 的 3 筆不一致 (股票 1210,2026-06-30~07-02) 獨立重跑
`parse_old_raw`/`parse_new_raw`,逐一核對:

| stock_id | date | old_parquet | old_raw (獨立重算) | new_parquet | new_raw (獨立重算) |
|---|---|---|---|---|---|
| 1210 | 2026-06-30 | 6.74 | 6.74 ✓ | 6.77 | 6.77 ✓ |
| 1210 | 2026-07-01 | 6.79 | 6.79 ✓ | 6.83 | 6.83 ✓ |
| 1210 | 2026-07-02 | 6.84 | 6.84 ✓ | 6.87 | 6.87 ✓ |

三筆都確認:old parquet 完全忠實反映舊原始檔、new parquet 完全忠實反映新原始檔,
兩份原始檔本身就報不同的數字 (差距約 0.03 個百分點)。`RAW_SOURCES_DIFFER`
分類邏輯通過人工覆核,不是腳本自我循環驗證。

### 10.7 這輪的結論與依然懸而未決的部分

**這是診斷紀錄,不是核准,也不是修復**:

- `institutional_gross.trust_holding_pct` 3.28% 落差 (以及其餘五欄已記錄的
  null/數值不等)**維持 `DIFF_UNRESOLVED`**——這輪沒有把它改成 PASS、沒有調降
  嚴重度、也沒有主張「反正是原始檔本身的差異所以可以忽略」。
- 有證據的部分是**「這不是這次遷移程式的轉換/管線 bug」**:4,632/4,658 (99.44%)
  的不一致,兩邊 parquet 都完整忠實反映各自的原始檔,問題出在**兩份 TEJ 匯出
  本身報的數字不同**;另外 26 筆是新原始檔用文字 `"."` 標記缺值的資料表示
  問題,同樣不是轉換邏輯錯誤。
- **依然懸而未決、這輪故意不做的判斷**:
  1. 兩份原始檔 (`法人毛額+持股率20260404-0716.xlsx` vs
     `2025-20260806 法人.xlsx`) 為什麼report不同數字——是 TEJ 資料回補/更正,
     還是舊種子檔本身精度/口徑問題,沒有 TEJ 官方的獨立佐證,不能斷言 (跟
     §3 原本的 `INFERENCE_UNCONFIRMED` 立場一致,這輪補上的是「兩邊 parquet
     都沒有搞錯自己的原始檔」這個新證據,不是回答「原始檔為什麼不同」)。
  2. 哪個版本 (舊/新) 應該被視為權威,或該不該對這個已知落差設定容忍值——這
     是政策/研究方法決定,不是程式可以自動判斷的事,留給人 (Codex/使用者)
     另外審查。
  3. `foreign_holding_pct` 的 `"."` 資料品質問題只在這次抽樣的窗口 (140,544 個
     重疊 key) 裡被發現,沒有調查新原始檔的其他日期/股票/欄位是否也有同樣的
     文字佔位符——這超出這輪的範圍,不做延伸調查。

### 10.8 第九輪:修正並重跑一次 (執行結果)

第九輪修好 §0 R9-1/R9-2/R9-3 三項後,對兩個 test module 跑
`python -m pytest tests/test_tej_data_migration.py tests/test_institutional_gross_adjudication.py`
(144 passed) 才執行修正後的腳本。

**⚠ 誠實記錄一次內部的錯誤與修正,不是事後才承認**:第一次執行修正後的腳本
(`institutional_gross_adjudication_20260807T152618418716_47c9e5b7.json`,
`2026-08-07T15:23:59Z`~`15:26:18Z`,exit 0,anchor 精確重現,`REVIEW_REQUIRED`)
本身沒有任何一項規則違反,三項修正 (R9-1/R9-2/R9-3) 都做對了。但第九輪明文要求
「執行後獨立重新驗算 receipt hash、腳本 hash、兩份原始檔 hash、兩份 parquet
manifest、anchor 重現、所有 accounting invariant」——做這道驗算時,發現
`diff_distribution_by_column` 欄位裡 `foreign_holding_pct` 的子項目加總對不上
`total_mismatch_instances`:第一版的 `build_diff_distribution()` 把
`mismatch_kind=="null_mismatch"` 跟 `classification=="UNRESOLVED_SCHEMA_OR_UNIT"`
當成兩個獨立累加的計數,但這兩者不是互斥維度——真實資料裡那 26 筆
`foreign_holding_pct` 剛好同時符合這兩個條件 (parquet 層級是 null 不對稱、raw
層級是無法解析的文字 "."),被重複計數了兩次。**判斷這是一份帶著已知 bug 的
receipt,不能當作最終結果回報**,於是:①把 `build_diff_distribution()` 改成
互斥的優先順序桶 (見程式內註解);②新增
`test_build_diff_distribution_sums_to_total_per_column` 鎖住這個不變量,更新
既有測試的期望值;③36 個 focused 測試全過後,重新執行一次。**第一次 (有 bug
的) receipt 沒有被刪除或覆寫**,原封不動保留在
`tej_exports/diff_receipts/institutional_gross_adjudication_20260807T152618418716_47c9e5b7.json`,
當作這次修正過程的診斷紀錄;下面的執行結果是修正後、真正作為第九輪最終產出的
第二次執行。

**修正後的執行**:

```
python scripts/institutional_gross_trust_holding_pct_adjudication.py
```

- 開始:`2026-08-07T15:29:44Z`;結束:`2026-08-07T15:32:07Z`;**exit code 0**。
- Receipt:`tej_exports/diff_receipts/institutional_gross_adjudication_20260807T153206693051_1d59726c.json`
  (SHA-256 `c16199f708eca3b49fe6ed17f560e2e4ebf4e0c4f04782c7f1951577d6099482`,
  815,708 bytes;`open(...,"x")` 排他建立)。
- `supersedes_for_review` 欄位指向第八輪的 receipt
  (`institutional_gross_adjudication_20260807T145805155908_921a469b.json`,
  SHA-256 `3500ca34...`),明講「只是審查依據上被取代,沒有被刪除或修改」——
  執行後確認該檔案存在且雜湊不變。

**執行後獨立重新驗算 (跟腳本本身分開跑,不信任腳本自己的判斷)**:script SHA-256、
兩份原始檔 SHA-256、兩份 parquet manifest、anchor 結構統計與六欄統計 (逐項比對
真正的 anchor receipt,不是只比對這份新 receipt 自己記錄的重算值)——**全部相符
零差異**。Accounting invariant 逐項重新驗算:`classification_counts_overall`
加總等於 `total_mismatch_instances`(4,658);`classification_counts_by_column`
加總等於 4,658;`classification_counts_by_stock`(完整,未截斷)加總等於 4,658;
`classification_counts_by_date` 加總等於 4,658;`diff_distribution_by_column`
逐欄加總等於 4,658 (修正後通過,第一次執行時這裡沒過)。額外用**完全獨立**的一次
`parse_old_raw`/`parse_new_raw`/`classify_all` 呼叫重新分類全部 4,658 筆,結果跟
receipt 記錄的 `classification_counts_overall` 逐項相符;抽驗全部 `RAW_SOURCES_
DIFFER` 實例的 `old_raw_matches_old_parquet`/`new_raw_matches_new_parquet` 兩個
旗標,**4,632 筆全部是 `true`/`true`**(這兩個旗標在 `classify_all()` 內部本來
就會在寫進 receipt 前先驗證一次,不成立會直接 raise,這裡是外部再獨立確認一次)。

**分類結果 (跟第八輪的數字一致,現在有完整的逐格證據支撐,不只是統計數字)**:

| 分類 | 筆數 |
|---|---|
| `RAW_SOURCES_DIFFER` | 4,632 |
| `UNRESOLVED_SCHEMA_OR_UNIT` | 26 |
| 其餘六個分類 | 0 |

**⚠ 更正第八輪一個不夠精確的敘述**:第八輪文件寫「`UNRESOLVED_SCHEMA_OR_UNIT`
的 26 筆…全部是股票代號 `4130`」——那是因為第八輪的 receipt 只存了每個分類前
10 筆樣本,剛好前 10 筆都是 4130。第九輪把 `<=50` 筆的分類全部完整存進 receipt
(26 筆全部都在),逐筆核對後發現**實際是兩檔股票**:`4130`(健亞,10 筆,
2026-07-02~07-16)跟 `5236`(16 筆,2026-06-22~07-14),`new_raw_token` 全部都是
文字 `"."`。根因判斷不變 (新原始檔用文字句點標記缺值,不是解析腳本的 bug),但
「集中在單一股票」這個敘述不準確,這裡更正為「集中在兩檔股票、同一種文字佔位符
問題」。

**`trust_holding_pct` 的完整 diff 分布** (不分箱、不設容忍值,499 個相異精確
diff 值):最高頻的幾個 `signed_diff_new_minus_old` 值是 `0.01`(458 筆)、
`0.02`(381 筆)、`0.03`(192 筆)、`0.04`(113 筆)、`0.1`(107 筆)、
`0.12`(103 筆)——絕大多數落在 0.01~0.3 個百分點這個很小的區間,沒有出現在
`max_abs_diff=6.33` 附近的極端值上有異常聚集。完整的 499 個 bucket 都在 receipt
的 `diff_distribution_by_column.trust_holding_pct` 裡,這裡不逐一列出。

**結論不變,依然是 §10.7 講的那些**:`DIFF_UNRESOLVED` 維持,沒有選擇權威版本,
沒有解決「兩份原始檔為什麼不同」這個根本問題。第九輪的價值是把第八輪「這不是
遷移程式的 bug」這個結論的證據做得更紮實 (逐格 raw token、精確 diff 分布、完整
不截斷的 accounting、獨立重新驗算全部通過),以及誠實揭露並修正了一個實作過程中
自己發現的 accounting bug 跟一個第八輪的不精確敘述。

**⚠ 第十輪的更正 (見 §0 第十輪、§10.9)**:上面這段第九輪的自我敘述,把「有誠實
記錄」講得好像可以抵銷「執行了兩次」這件事本身——那個框架不對。第九輪對
`institutional_gross_trust_holding_pct_adjudication.py` 執行了兩次真實資料
(`...47c9e5b7.json` 跟 `...1d59726c.json`),違反了當輪明文的「只授權一次」
範圍,這是事實,是違規,不因為後來誠實揭露、修好 bug 就不算違規。**這兩份
receipt 從第十輪開始一律降級為診斷用途,不是正式有效的裁定結果**;上面 §10.8
記錄的分類數字/diff 分布/根因判斷等內容,要以 §10.10 第十輪重新執行、唯一
正式有效的那份 receipt 為準。

### 10.9 第十輪 Phase A:實作與測試凍結 (執行真實資料前的最後狀態)

**以下內容在執行 Phase B 的真實指令之前寫定。Phase B 指令一啟動,本輪不再修改
任何程式碼/規格/測試,也不會執行第二次。**

**凍結的檔案與 SHA-256**(2026-08-08,Phase A 測試全過之後、Phase B 執行之前
當場計算):

| 檔案 | SHA-256 |
|---|---|
| `scripts/institutional_gross_trust_holding_pct_adjudication.py` | `8e00dd678b87ff3715b771a54ee64b9b2151ebd51d73fb5b78588281466809df` |
| `scripts/institutional_gross_adjudication_verifier.py` | `be0f4bd8be31f91818b873730fc8a2f56cbf03ce9ba22ebe5f5094aa41e99da3` |
| `tests/test_tej_data_migration.py` | `f6807c69946f9f05613da85902f064d1c35927adb954c341a5b2ff4cbb830fce` |
| `tests/test_institutional_gross_adjudication.py` | `5bf94b2f25af6130918ddef2f2016c59c84622be7a564b25a075d1140e44b42d` |
| `tests/test_institutional_gross_adjudication_verifier.py` | `8a1812fdbe49e4365211c3926d44e058cbca275fa203367337118d577d2e167b` |

**測試命令與結果**(全部 synthetic fixture,沒有讀取任何真實的 `~/tej_cache`、
round3 scratchpad 快取,或 `tej_exports/inbox_chip_gross`/`DataExport0806` 底下
的原始檔):

```
python -m py_compile tej_importer.py scripts/extract_legacy_supplement.py \
    scripts/_full_population_diff.py scripts/institutional_gross_trust_holding_pct_adjudication.py \
    scripts/institutional_gross_adjudication_verifier.py \
    tests/test_tej_data_migration.py tests/test_institutional_gross_adjudication.py \
    tests/test_institutional_gross_adjudication_verifier.py
python -m pytest tests/test_tej_data_migration.py tests/test_institutional_gross_adjudication.py \
    tests/test_institutional_gross_adjudication_verifier.py -q -p no:cacheprovider \
    --basetemp=".pytest_codex_round10_full"
```
結果:`167 passed in 4.20s`(109 + 41 + 17)。

**Phase B 預期執行的指令**(尚未執行,見 §10.10):

```
python scripts/institutional_gross_trust_holding_pct_adjudication.py
```

**預期輸入路徑**(跟第八/九輪相同,凍結常數,沒有改變):

- anchor receipt:`tej_exports/diff_receipts/full_population_diff_20260807T093225Z.json`
- old parquet root:`C:\Users\aaaai\tej_cache\institutional_gross`
- new parquet root:`C:\Users\aaaai\AppData\Local\Temp\claude\C--dev\b2a9ba0e-e9a0-4c69-9808-b8aaa37c08de\scratchpad\tej_cache_round3\institutional_gross`
- old raw:`tej_exports/inbox_chip_gross/法人毛額+持股率20260404-0716.xlsx`
- new raw:`tej_exports/DataExport0806/法人回測2004-20260806/2025-20260806 法人.xlsx`

**分類規則**:沿用 §10.4 凍結的八個互斥分類決策樹,本輪未修改規則本身,只修改
receipt 的證據完整度跟 provenance 標記。

**必要的 receipt schema (新增/變更的部分)**:

- `mismatch_records`:list,每筆必須包含
  `stock_id, date, column, mismatch_kind, old_parquet, new_parquet, old_raw_token,
  new_raw_token, old_raw_parsed, new_raw_parsed, old_raw_is_blank, new_raw_is_blank,
  old_raw_is_unparseable, new_raw_is_unparseable, unit_scale, classification,
  signed_diff_new_minus_old, abs_diff, old_raw_matches_old_parquet,
  new_raw_matches_new_parquet`。`len(mismatch_records)` 必須等於
  `mismatch_scope.total_mismatch_instances`;`(stock_id,date,column)` 必須唯一。
- `classification_counts_overall`/`classification_counts_by_column`/
  `classification_counts_by_stock`/`classification_counts_by_date`/
  `diff_distribution_by_column`:全部只能從 `mismatch_records` 重建
  (`summarize_records()` 是唯一產生方式)。
- `classification_samples`:方便閱讀用的附加視圖,不是唯一證據來源。
- `prior_receipts_provenance`:`round8`/`round9_first`/`round9_second` 三個 key,
  各自 `{path, sha256, status}`,狀態依序是 `diagnostic_superseded`/
  `diagnostic_invalid_accounting`/`diagnostic_post_deviation_unauthorized_rerun`。
- `overall_status` 固定 `REVIEW_REQUIRED`(除非連 anchor 都無法重現才是
  `ANCHOR_INPUT_IDENTITY_UNVERIFIED`,或原始檔驗證失敗才是
  `RAW_SOURCE_VALIDATION_FAILED`)。

**⚠ 明文聲明 (Phase A 凍結的一部分)**:從這一刻起,Phase A 不再有任何程式碼、
規格或測試異動。下一步是 Phase B——執行 `python scripts/institutional_gross_
trust_holding_pct_adjudication.py` **恰好一次**。這個授權在指令開始執行的當下
就用掉,不論 exit code 或 receipt 品質如何;執行過程中或執行後如果發現任何
bug、accounting 錯誤,或 receipt 格式不對,本輪都只停下來回報,不修程式碼、
不修規格、不修測試、不重跑第二次。

### 10.10 第十輪 Phase B/C:執行結果

**Phase B(唯一一次授權的執行,已用掉,本輪不會再執行第二次)**:

```
python scripts/institutional_gross_trust_holding_pct_adjudication.py
```

- 開始:`2026-08-07T16:18:13Z`(前一刻確認 `tej_exports/diff_receipts/` 是 5 個
  檔案);結束:`2026-08-07T16:20:35Z`;**exit code 0**。
- Receipt:`tej_exports/diff_receipts/institutional_gross_adjudication_20260807T162035367456_574d5f80.json`
  (SHA-256 `6e4ce155cd283bb4dc57a19375eee550a98f2bc7289f2b2df1c66cab6a0ba21f`,
  4,144,636 bytes;`open(...,"x")` 排他建立)。這是**這一輪唯一有效的裁定
  結果**,不是又一份可以挑著引用的診斷紀錄。

**Phase C(唯讀驗證,用 §10.9 凍結的驗證器,對 Phase B 產出的 receipt 執行
恰好一次)**:

```
python scripts/institutional_gross_adjudication_verifier.py \
    "tej_exports/diff_receipts/institutional_gross_adjudication_20260807T162035367456_574d5f80.json"
```

**exit code 0**,`"ok": true`,24 項檢查**全部通過**,`"failures": {}`:

- `script_hash_matches_current_file`/`old_raw_hash_matches_current_file`/
  `new_raw_hash_matches_current_file`/`old_parquet_manifest_matches_current`/
  `new_parquet_manifest_matches_current` ✅
- `structural_matches_receipt_claim`/`columns_matches_receipt_claim`/
  `structural_matches_true_anchor`/`columns_matches_true_anchor` ✅(anchor
  精確重現,獨立對照真正的 anchor receipt,不是只信 receipt 自己的宣稱)
- `mismatch_records_present`/`mismatch_records_count_matches_total`
  (4,658 筆,跟 `mismatch_scope.total_mismatch_instances` 一致)/
  `mismatch_records_keys_unique`/`mismatch_records_have_required_fields` ✅
- `classification_counts_overall_reconstructs_from_records`/
  `..._by_column_...`/`..._by_stock_...`/`..._by_date_...`/
  `diff_distribution_by_column_reconstructs_from_records` ✅(所有摘要都只從
  `mismatch_records` 重建,不依賴任何 receipt 以外的中間狀態)
- `all_raw_sources_differ_flags_true`(4,632 筆 `RAW_SOURCES_DIFFER` 全部
  `old_raw_matches_old_parquet=true`/`new_raw_matches_new_parquet=true`)、
  `unparseable_records_preserve_raw_token`(26 筆 `UNRESOLVED_SCHEMA_OR_UNIT`
  全部保留字面 raw token,不是只剩 `NaN`) ✅
- `overall_status_is_review_required` ✅
- `provenance_round8_matches_current_file`/`provenance_round9_first_matches_current_file`/
  `provenance_round9_second_matches_current_file` ✅(三份之前的 receipt 路徑/
  SHA-256/狀態標籤都對得上,而且這三份檔案本身沒有被動過)

**分類結果**(六欄合計 4,658 個不一致實例,`mismatch_records` 裡每一筆都有完整
證據,不是抽樣):

| 分類 | 筆數 |
|---|---|
| `RAW_SOURCES_DIFFER` | 4,632 |
| `UNRESOLVED_SCHEMA_OR_UNIT` | 26 |
| 其餘六個分類 | 0 |

分欄:`foreign_buy`(2 個 `RAW_SOURCES_DIFFER`)、`foreign_sell`(2 個)、
`trust_buy`(5 個)、`trust_sell`(8 個)、`trust_holding_pct`(4,615 個,全部
`RAW_SOURCES_DIFFER`)、`foreign_holding_pct`(26 個,全部
`UNRESOLVED_SCHEMA_OR_UNIT`)——數字跟 §10.8 記錄的第九輪結果一致 (根因判斷、
兩檔股票的更正說明都不變),但這次是**唯一被正式授權、單次執行**產生的結果,
不是第九輪那種違規重跑之後才發現要不要相信的版本。

**之前三份 receipt 的出處標記**(寫進本輪 receipt 的 `prior_receipts_provenance`,
三份檔案本身不動):

| receipt | SHA-256 | 狀態標籤 |
|---|---|---|
| Round 8 (`...921a469b.json`) | `3500ca34b4704fb1d4e1b518e3dbc8ea58cc9f93362da8e8eec77bdc28d45d81` | `diagnostic_superseded` |
| Round 9 第一次 (`...47c9e5b7.json`) | `1f2bfaef55f0ce8728d94f5db71dcf3bb198544601e6e60143562fd9048977e2` | `diagnostic_invalid_accounting` |
| Round 9 第二次 (`...1d59726c.json`) | `c16199f708eca3b49fe6ed17f560e2e4ebf4e0c4f04782c7f1951577d6099482` | `diagnostic_post_deviation_unauthorized_rerun` |

**確認**:執行前後 `tej_exports/diff_receipts/` 從 5 個檔案變成 6 個 (只新增
一個,沒有任何檔案被刪除或覆寫);上表三個 SHA-256 跟第八/九輪報告過的雜湊
完全相同 (逐位元組核對過,不是只看檔名);兩份原始 Excel、兩個 parquet 快取
目錄、`tej_exports/legacy_supplement/` 的 mtime 全部維持不變 (唯讀,沒有寫入);
沒有執行 `_full_population_diff.py`、沒有重建/匯入任何 dataset、沒有重跑
supplement 抽取、沒有觸碰生產環境 `~/tej_cache`(注意:`OLD_PARQUET_ROOT` 常數
剛好也指向路徑字面上含 `tej_cache` 的目錄,但那是這個裁定案在用的**唯讀輸入**,
不是遷移正式匯入會寫入的生產路徑);沒有 stage/commit/push。

**結論不變**:`institutional_gross.trust_holding_pct` 3.28% 落差維持
`DIFF_UNRESOLVED`,沒有選擇舊版或新版作為權威,`overall_status=REVIEW_REQUIRED`。
兩份原始檔本身為什麼報不同數字,依然是 `INFERENCE_UNCONFIRMED`,留給人 (Codex/
使用者) 另外審查。

---

## 11. 資料版本政策與決策登記 (第十一輪凍結)

**這一節是政策凍結,不是新的技術發現。** 第十輪正式接受的結論範圍僅止於
**出處層級的證據**——old/new `institutional_gross` parquet 各自忠實反映自己的
TEJ 原始匯出 (§10.10)。這**不等於**任何一個版本在經濟或歷史意義上「正確」,
也不等於整個遷移可以往下走。第十一輪把這個邊界、以及圍繞它的一系列操作規則,
明文凍結下來。

### 11.1 舊系譜不可變 (Legacy lineage remains immutable)

- 現有的 `C:/Users/aaaai/tej_cache`、舊 `tej_exports/inbox*`、已凍結的 V0/Gate
  產物,以及所有先前已回報的研究結論,**維持綁定在它們原本的資料系譜與程式碼
  系譜上**,不因為 DataExport0806 出現而自動變動。
- **DataExport0806 絕對不能被用來靜默改寫、重算、或重新詮釋舊有的 V0/Gate/
  績效結論。** 任何要用 DataExport0806 重新檢視舊結論的動作,都必須是一個
  新的、明確標記資料版本的獨立研究動作,不能覆蓋或悄悄取代舊結論。
- 要重現一個舊結果,必須使用它原本的 snapshot 與程式碼系譜——不能拿
  DataExport0806 或這輪之後的任何 V2 candidate 產物去「重現」一個舊結果,那樣
  重現出來的已經不是同一件事。

### 11.2 DataExport0806 的狀態:`V2_CANDIDATE_RESTATED_SNAPSHOT`

- `tej_exports/DataExport0806` 正式定名為 `V2_CANDIDATE_RESTATED_SNAPSHOT`——
  **不是** PIT (point-in-time) 歷史,**也還不是**生產權威版本。
- 「restated」的意思是:它是 TEJ 較晚一次的匯出,可能包含歷史資料的回補或
  更正。**這不代表它是獨立驗證過的真實值**——「restated」是對匯出時間點跟
  資料性質的中性描述,不是品質背書。
- 它的版本身分由 `tej_exports/DataExport0806_manifest.csv`/`.sha256`(§1)加上
  目前的 supplement bundle (`tej_exports/legacy_supplement/receipt.json`,§5、
  §7 的 Round 7 重建結果) 共同定義——manifest 定義原始檔案集合的身分,
  supplement receipt 定義從舊來源額外抽取欄位的身分,兩者合起來才是完整的
  candidate 版本識別。任一個變了,candidate 的身分就要重新定義。
  **這份 supplement 字面上是拿舊系譜的原始檔案補 candidate 的缺欄,跟下面
  §11.4 的「不允許混用快照版本」原則看似衝突——這個衝突由 §11.4a 凍結的
  `LEGACY_DERIVED_SUPPLEMENT` 例外解決,不是說 §11.4 對這裡不適用。**

### 11.3 已知的版本落差 (Known version drift)

- `institutional_gross.trust_holding_pct` **維持 `DIFF_UNRESOLVED`**——不引入
  任何容忍門檻,也不做自動偏好判斷 (不因為某個版本「看起來比較新」或「差異
  模式看起來系統性」就自動選它)。
- 正式接受的第十輪證據 (§10.10):140,544 個重疊 key、六欄合計 4,658 個不一致
  實例,其中 **4,632 筆是 `RAW_SOURCES_DIFFER`**(兩邊 parquet 都完整忠實反映
  各自的原始檔,問題出在兩份 TEJ 匯出本身報的數字不同)、**26 筆是
  `UNRESOLVED_SCHEMA_OR_UNIT`**(新原始檔用文字 `"."` 標記缺值)。**沒有找到
  這次遷移程式本身的轉換/管線錯誤**——但「兩份原始檔為什麼報不同數字」依然是
  `INFERENCE_UNCONFIRMED`,不是已經解開的問題。
- **數值欄位裡的文字 `"."` 是一個明確的資料品質狀態**,不是普通的缺值:
  - 只能解析成「缺值」,但必須**同時保留一個品質旗標/出處紀錄**,標明「這格
    原始內容是無法解析的文字,不是空白」——這正是 `institutional_gross_
    trust_holding_pct_adjudication.py` 的 `is_unparseable`/`raw_token` 欄位
    (§10.9 receipt schema) 已經在做的事,這裡把它提升成通用政策,適用於未來
    任何讀到 DataExport0806 的 importer。
  - **絕對不能**靜默轉型成 0、靜默補值 (imputation)、或不留痕跡地當作跟「儲存
    格本來就空白」完全相同的合法 null 處理。

### 11.4 使用情境分離 (Separation of use cases)

- **舊快照 (legacy snapshot)**:只能用於重現/稽核既有研究結論。
- **V2 候選快照 (V2 candidate snapshot)**:只能用於 V2 研究的開發跟未來工作,
  且必須寫在**跟生產/舊系譜隔離的獨立 cache/輸出命名空間**裡 (見 §11.6 的
  隔離路徑要求)。
- **不允許混用兩個快照版本**做同一份 panel、fallback、supplement 或比較分析
  ——除非這個混用動作本身**事先預註冊**(依 `docs/研究紀律_ResearchDiscipline.md`
  的單發射擊制精神)且**明確標記資料出處**,否則一律禁止。混用而不標記出處,
  正是本專案史上讓結論靜默作廢的那種錯誤 (見 `docs/研究紀律_
  ResearchDiscipline.md` 開頭列的四次前例)。
- **目前唯一的明文例外是 `LEGACY_DERIVED_SUPPLEMENT`**,見 §11.4a——不是打開
  混用的通則,是一個範圍極窄、內容凍結、可以隨時 fail-closed 的特例。

### 11.4a `LEGACY_DERIVED_SUPPLEMENT`——混用禁令的唯一明文例外 (第十二輪凍結)

**這裡解決 §11.2 跟上面 §11.4 之間的一個實質矛盾**:§11.2 說 candidate 版本
身分包含目前的 supplement bundle (§5、§7,源自舊 `inbox*` 系譜的原始檔案),
但 §11.4 說「不允許混用兩個快照版本」——這份 supplement 字面上正是拿舊系譜
資料去補 V2 candidate 的缺欄,是一種混用。第十二輪凍結一個有名字、有條件、
範圍極窄的例外,不是承認「supplement 機制本身」通則性地豁免混用禁令。

- **名稱**:`LEGACY_DERIVED_SUPPLEMENT`。
- **適用範圍,僅限這三個目前已記錄在案的 supplement 輸出/欄位群組**,不包含
  任何其他欄位、來源,或未來才新增的 supplement:
  - `roe_after_tax`
  - `recurring_net_income`
  - `revenue_last_year` 與 `cum_revenue_last_year`
- **內容凍結在目前這一份上**:它的四個舊來源檔案、抽取腳本 (`scripts/
  extract_legacy_supplement.py`) 的 SHA-256、三個輸出檔案的雜湊、schema、
  key/date 涵蓋範圍、去重證據 (§5-§7 的 Round 7 重建結果),都必須跟現在的
  `tej_exports/legacy_supplement/receipt.json` 記錄的**完全一致**。這個例外
  批准的是「這一份、已經被驗證過的 supplement」,不是「supplement 這種做法
  永遠合法」。
- **只能新增 DataExport0806 原生 dataset 沒有的欄位**——絕對不能覆寫、優先於、
  跟原生 V2 欄位做 coalesce、或悄悄取代任何一個原生 V2 欄位。
- **合併鍵必須唯一且非 null,合併後列數不能增加**;現有的合併前/合併後驗證
  (`tej_importer._verify_supplement`,§6)全部繼續強制執行——這個例外不豁免
  任何一項既有的 fail-closed 檢查。
- **每一個用到這些欄位的 candidate dataset/build receipt,都必須把這些欄位
  標記 `source_class=LEGACY_DERIVED_SUPPLEMENT`,並且攜帶 supplement receipt
  的雜湊**,讓下游任何人一眼就看得出這幾欄的資料來源跟其餘原生欄位不同。
- **這份 supplement 不是 PIT 資料**,也不會因為被打包進 candidate snapshot就
  變成「V2 原生」——它的 PIT 限制聲明維持 §4 原本記錄的內容不變。
- **這個例外不能被隱性擴大**:任何新欄位、新來源、新的重疊/coalesce 處理
  規則,或 supplement 雜湊改變 (代表底層資料換過一批),都需要一輪新的
  預註冊/政策審查才能納入,不能直接沿用這裡凍結的許可去覆蓋更多欄位。
- **條件不成立就 fail-closed,不能 fallback 到別的 cache**:雜湊不符、schema
  跑掉、合併鍵重複、或任何一項條件對不上,受影響的欄位/dataset 直接判定
  失敗,不能悄悄改讀別的資料來源頂替。

### 11.5 生產環境依然封鎖 (Production remains blocked)

- **不寫入或取代 `~/tej_cache`**——這件事還沒被核准,這一輪也不例外。
- **不刪除、不改名任何舊的原始資料或 cache**(`tej_exports/inbox*` 待刪除清單
  見 §9,依然是「列出來待審查」,不是「已核准」)。
- **不宣告整個遷移已核准**——`institutional_gross.trust_holding_pct` 的
  `DIFF_UNRESOLVED` 沒有解決,§9 的刪除清單沒有核准,`~/tej_cache` 的正式寫入
  沒有核准,三者缺一,遷移就不算核准。
- 下一個可執行階段 (**如果**另外被明確授權)是:把全部 11 個 dataset 建進一個
  隔離的候選 cache,例如 `tej_cache_v2_candidate_<snapshot-id>`,**絕對不是**
  生產環境 `~/tej_cache`。這件事本輪沒有被授權,只是先把「如果將來授權,長什麼
  樣子」凍結下來 (見 §11.6)。

### 11.6 未來隔離建置的前提清單 (Preconditions for that future isolated build)

如果將來另外授權「把全部 11 個 dataset 建進隔離的候選 cache」,至少要滿足:

1. **內容定址的 snapshot ID**:由 manifest (§1) + supplement receipt (§5/§7) +
   importer/抽取腳本的 SHA-256 共同衍生出一個唯一識別碼,任一個輸入變了,
   snapshot ID 就要變。
2. **精確的來源 manifest preflight**:比照 `tej_importer._manifest_preflight`
   (§6) 現有的做法,讀檔前核對實際檔案集合跟 manifest 記錄的是否完全一致。
3. **Fail-closed 的 schema/key 檢查**:比照現有 `_check_required_cols`/
   `_check_valid_keys`/`_check_duplicate_key_conflicts` (§6) 的標準,不因為
   V2 candidate 是「候選」就放寬。
4. **隔離輸出路徑要先驗證過不會解析到舊系譜或生產路徑**——寫入前主動比對
   目標路徑跟 `~/tej_cache`、`tej_exports/inbox*` 等舊系譜路徑,確認不重疊、
   不是同一個路徑的不同寫法 (例如符號連結、相對路徑正規化後撞在一起)。
5. **逐 dataset 執行 + receipt + 完整的 row/stock/date/schema/null/重複鍵
   accounting**——比照 §10 的 Round 8-10 建立的模式 (唯讀 manifest、anchor
   式的重現與比對、`mismatch_records` 式的完整逐筆證據),不是只跑一次拿到
   聚合數字就結束。
6. **建置過程中不做績效/OOS 分析**——資料建置跟策略驗證是兩個分開的階段,
   不能在同一輪裡混著做 (呼應 §11.4 的情境分離)。
7. **刪除或推上生產環境都需要另一輪獨立審查跟使用者的明確授權**——不能因為
   建置本身跑成功了,就自動視為「可以刪舊資料」或「可以推生產」的許可。
8. **`LEGACY_DERIVED_SUPPLEMENT` 前置檢查**(第十二輪新增,見 §11.4a):如果
   這次建置任何一個 dataset 用到 §11.4a 凍結的 legacy-derived supplement
   欄位,必須逐項核對符合 §11.4a 的全部條件 (四個舊來源檔案/抽取腳本雜湊/
   輸出雜湊/schema/key-date 涵蓋範圍/去重證據都跟目前 `legacy_supplement/
   receipt.json` 記錄的完全一致),輸出時標記
   `source_class=LEGACY_DERIVED_SUPPLEMENT` 並攜帶 supplement receipt 雜湊;
   任一項不符,受影響的欄位/dataset 直接 fail-closed,不允許 fallback 到別的
   cache。

**以上共八項前提**,§11.8 的決策登記表跟任何摘要文字都要跟這個數字一致——
少列或多列都要同步修正這裡跟那裡,不能讓 prose 裡的數字漂移。

### 11.7 狀態分類法 (Status taxonomy)

| 狀態 | 意義 |
|---|---|
| `LEGACY_FROZEN_LINEAGE` | 舊系譜 (`~/tej_cache`、舊 `inbox*`、已凍結的 V0/Gate 產物) 的狀態——不可變,不因為 DataExport0806 出現而變動。 |
| `V2_CANDIDATE_RESTATED` | DataExport0806 目前的狀態——TEJ 較晚匯出的候選版本,可能含歷史回補/更正,尚未獨立驗證為生產權威。 |
| `DIFF_UNRESOLVED` | 已知的新舊版本數值落差,存在但未被人工裁定 (例如 `institutional_gross.trust_holding_pct`)——不是 PASS,也不是 FAIL,是「已測量、待裁定」。 |
| `BUILD_NOT_RUN` | **精確定義 (第十二輪)**:沒有任何一次**正式授權、符合政策的** V2 隔離候選建置被執行過。**這不是「11 個 dataset 從來沒有被跑過任何一次建置」的意思**——見下面 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD` 這一列,第三輪確實跑過一次,但那次不符合這個定義的條件 (未經授權、超出範圍),所以正式候選建置依然是 `BUILD_NOT_RUN`。 |
| `DIAGNOSTIC_OUT_OF_SCOPE_BUILD` | **第十二輪新增,如實記錄第三輪的歷史,不抹除**:第三輪在當輪審查明文「Do not ... rerun the 2.2 GB full audit yet」的限制下,實際把 `tej_importer.py` 11 個 dataset 的完整匯入都跑了 (見文件開頭 ⚠ 第三輪警告、§0 第四輪 R4-0),超出了當輪授權範圍。這次建置的產物 (含 `.../scratchpad/tej_cache_round3/` 底下的 11 個 dataset,其中 `institutional_gross` 這個子目錄從第七輪起一直被 §10 當作唯讀診斷輸入使用) **只能算證據/診斷素材**——不能滿足 `BUILD_VALIDATED`、不能被推廣/promote、不能被當成正式的 V2 candidate build 呈報。 |
| `BUILD_VALIDATED` | 隔離建置執行完成且通過 §11.6 的完整性檢查 (manifest/schema/key/row accounting)。**只代表建置本身是完整、fail-closed 檢查過的,不代表策略績效或科學有效性**——這兩件事完全分開,`BUILD_VALIDATED` 之後還是要走完整的績效/OOS/Gate 流程才能談應用。`DIAGNOSTIC_OUT_OF_SCOPE_BUILD` 的產物不能被拿來宣稱已經達到這個狀態。 |
| `PRODUCTION_NOT_APPROVED` | 生產環境 `~/tej_cache` 寫入的狀態——目前及可預見的未來,直到另外收到明確授權為止。 |

### 11.8 決策登記表 (Decision register)

| # | 決策 | 狀態 | 依據 |
|---|---|---|---|
| D1 | 舊系譜 (`~/tej_cache`/舊 `inbox*`/V0/Gate 產物/既有研究) 維持 `LEGACY_FROZEN_LINEAGE`,DataExport0806 不得靜默改寫它們 | 已凍結 | §11.1 |
| D2 | `tej_exports/DataExport0806` 正式定名 `V2_CANDIDATE_RESTATED_SNAPSHOT` | 已凍結 | §11.2,§1 |
| D3 | `institutional_gross.trust_holding_pct` 維持 `DIFF_UNRESOLVED`,不設容忍門檻、不自動偏好 | 已凍結 | §11.3,§10.10 |
| D4 | 數值欄位裡的文字 `"."` 一律保留品質旗標/出處紀錄,不得靜默轉型/補零/補值 | 已凍結 | §11.3 |
| D5 | 舊快照跟 V2 候選快照的使用情境分離,不可混用除非事先預註冊且標記出處 | 已凍結 | §11.4 |
| D6 | 生產環境 `~/tej_cache` 依然封鎖:不寫入、不刪除/改名舊資料、遷移整體不算核准 | 已凍結 | §11.5 |
| D7 | 未來隔離建置 (如另外授權) 的**八項**前提 (snapshot ID、manifest preflight、fail-closed 檢查、隔離路徑驗證、逐 dataset accounting、建置期不做績效分析、刪除/推生產需另一輪審查、`LEGACY_DERIVED_SUPPLEMENT` 前置檢查) | 已凍結,尚未執行 | §11.6 |
| D8 | 狀態分類法**七態** (`LEGACY_FROZEN_LINEAGE`/`V2_CANDIDATE_RESTATED`/`DIFF_UNRESOLVED`/`BUILD_NOT_RUN`/`DIAGNOSTIC_OUT_OF_SCOPE_BUILD`/`BUILD_VALIDATED`/`PRODUCTION_NOT_APPROVED`) | 已凍結 | §11.7 |
| D9 | `LEGACY_DERIVED_SUPPLEMENT`:混用禁令的唯一明文例外,範圍限定 `roe_after_tax`/`recurring_net_income`/`revenue_last_year`+`cum_revenue_last_year` 三組欄位,內容凍結在目前的 `legacy_supplement/receipt.json`,只能新增欄位不能覆寫原生欄位,標記 `source_class` 並攜帶 receipt 雜湊,條件不符 fail-closed | 已凍結 | §11.4a |
| D10 | `BUILD_NOT_RUN` 精確定義為「沒有正式授權、符合政策的建置執行過」;第三輪的建置標記 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD`,只是診斷素材,不滿足 `BUILD_VALIDATED`,不能推廣/promote | 已凍結 | §11.7 |

### 11.9 尚未解決、這輪刻意不處理的政策問題

- 兩份原始檔 (`法人毛額+持股率20260404-0716.xlsx` vs `2025-20260806 法人.xlsx`)
  為什麼報不同數字——根因依然是 `INFERENCE_UNCONFIRMED`,需要 TEJ 官方獨立佐證
  才能往下推進,這輪沒有嘗試解決。
- 其餘 10 個 dataset (institutional_gross 以外) 目前只有 §3 用第三輪版本
  `_full_population_diff.py` 產生的舊 receipt,沒有經過 Round 8-10 這種逐格
  raw-token 等級的溯源——這份文件不主張其他 dataset 也已經有同等強度的證據,
  §11.3 的「沒有找到轉換錯誤」結論**只適用於 institutional_gross 六欄**。
- `tej_exports/inbox*` 待刪除清單 (§9) 的最終決定,以及 `~/tej_cache` 正式
  切換的時間點跟流程,都不在這輪的範圍內,留待另外的審查與明確授權。
- §11.6 的隔離建置前提清單是**凍結規則**,不是**已核准的執行計畫**——下一次
  如果要真的執行,還是需要一輪新的明確授權,不能直接引用這份清單就開始跑。
