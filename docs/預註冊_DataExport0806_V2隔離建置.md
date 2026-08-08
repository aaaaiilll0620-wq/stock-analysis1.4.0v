# 預註冊:DataExport0806 → V2 隔離候選建置

**狀態:`PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED`(見 §F——使用者已於
2026-08-08 核准完整 64 碼 `snapshot_id_v1` + `<run_id>` 隔離輸出根目錄
路徑,這是本文件唯一剩下的阻塞項,核准後解除;`BLOCKED_BEFORE_
IMPLEMENTATION` 維持空。這個狀態**只代表預註冊文件本身已經完整、可以
凍結**,**不代表** Phase A 程式碼實作或 Phase B 執行獲得授權——§F
`MISSING_BEFORE_BUILD` 底下每一項仍然明確是 `MISSING`,一個都沒有變成
已實作)。**

這份文件依 `docs/研究紀律_ResearchDiscipline.md` §2 的單發射擊制寫成:在任何
一次真正的隔離建置執行之前,先把驗收標準、失敗語意、輸出路徑規則寫死。

**Checkpoint 23(本次)是一次文件勘誤,不是新一輪設計、不執行任何東西、
不代表 Phase A/B 獲得授權**:Checkpoint 22 把 `preregistration_commit`
定義成 `git rev-parse HEAD` 是一個具體的 git 身分語意錯誤(§C.1 有完整
修正說明)——不匯入、不建 cache、不跑 pytest、不修改
`tej_importer.py`/`scripts/*`/任何 requirements/lock/manifest/來源
資料/supplement/cache/receipt/已提交的政策文件、不建立已核准的輸出目錄
本身。這次唯一的動作,是修正 §C.1 的 `preregistration_commit` 定義跟
§F 的對應敘述,以及依 Codex 指示做另一次範圍精確限定在本文件的 scoped
git commit(不 amend Checkpoint 22 的 commit,見文末 git 紀錄)。

依據:`AGENTS.md`、`docs/研究紀律_ResearchDiscipline.md`、已提交的
`docs/資料快照遷移_DataExport0806.md`(commit `d46d45c96d738c2fe60497ddba2aa9f1fc5a009c`,
下稱「政策文件」)、`tej_importer.py`、`scripts/extract_legacy_supplement.py`、
`tej_exports/DataExport0806_manifest.csv`/`.sha256`、
`tej_exports/legacy_supplement/receipt.json`。

## 版本紀錄

- **第 15 輪**:建立本文件,§A-§F 完整初稿,結論
  `ROUND15_STATUS=DESIGN_COMPLETE_BUILD_NOT_AUTHORIZED`。
- **第 16 輪**:修狀態機自我認證問題、輸出契約、身分模型、C.2/C.8 矛盾,
  新增 C.9(品質證據 sidecar)/C.10(supplement provenance)兩份 schema。
  結論 `ROUND16_STATUS=DESIGN_BLOCKED`(架構選擇 + 7 個欄位 dtype 未決)。
- **第 17 輪(本次)**:Codex 獨立複查第 16 輪後指出六個必須修的技術缺陷,
  逐一修補:
  1. **凍結混合架構**(§D)——不再讓「改 `tej_importer.py` 本體 vs 獨立
     orchestrator」當二選一懸案:`tej_importer.py` 只管確定性解析/型別轉換/
     驗證/產生記憶體內品質證據紀錄,新的獨立 builder 腳本管路徑守衛/身分
     計算/循序執行/receipt/sidecar 寫入,獨立 verifier 腳本不 import 也不
     呼叫 builder、也不呼叫 `tej_importer.load_source()`。**這個決定直接
     解除第 16 輪 §F 的架構 `BLOCKED_BEFORE_IMPLEMENTATION`。**
  2. **修正 dtype 契約**(§B/§C.1)——`pd.to_numeric(errors="coerce")` 在
     全部值都是整數且沒有 NaN 時可能留在 `int64`,原文「一律 float64」的
     描述是錯的;改成「顯式凍結目標型別,不依賴推斷」,同時把 industry
     code/`group_name` 等 7 個欄位凍結成顯式字串型別(不能被誤轉數字,
     因為前導零有意義)。**這解除第 16 輪 §F 的
     `DESIGN_BLOCKED_SCHEMA_CONTRACT`。**
  3. **精確化最終 schema**(§B)——「選用欄位可能消失」不是精確契約;改成
     11 個 dataset 各自的欄位集合**永遠固定**(`rename`/單位轉換/已核准
     supplement 全部欄位都進最終 schema),歷史原始檔缺欄位變成「值缺席」
     用 receipt 裡的逐檔逐欄位覆蓋矩陣表示,不是 schema 本身變動;新增
     「一個欄位在全部原始檔裡都缺席時 fail-closed」規則。
  4. **修品質 sidecar 的 accounting**(§C.9)——拿掉「sidecar 列數直接等於
     最終 NaN 數」這個錯誤等式(在完全重複去重、欄位整檔缺席、supplement
     未覆蓋這三種情況下都不成立),改成分階段 accounting(去重前的來源
     cell 分類 vs. 去重/合併後的最終 null 原因分類,兩組各自獨立可重建);
     locator 補上 `source_container_member`/實體列號/來源檔雜湊;`raw_token`
     語意講清楚。
  5. **落實單發驗證**(§D)——原文允許同一個 build 被驗證器跑很多次、只要
     有任何一次 PASS 就採計,這是可以挑結果的漏洞;改成一個 `run_id` +
     `verifier_identity` 只有一次有約束力的驗證執行,授權在驗證器**開始
     執行**當下就消耗掉,不論結果。
  6. **加入依賴/執行環境身分**(§C.1)——Python/pandas/pyarrow/openpyxl
     版本不同,即使原始碼跟來源檔案雜湊都沒變,候選 parquet 的位元組跟
     解析行為都可能不同;新增 `dependency_lock_identity` 進
     `build_implementation_identity`。
  結論改為 `ROUND17_STATUS=DESIGN_BLOCKED`——但現在**只剩**輸出根目錄路徑
  這一項使用者決定尚未核准(§F),不再有任何技術性設計缺口。
- **第 18 輪(本次)**:Codex 獨立複查第 17 輪後指出四個內部不一致跟一個
  需要收斂的決定,逐一修補:
  1. **修正最終 schema 公式**(§B)——原文「`rename` 全部值」會把
     `_volume_thousand_shares`/`_foreign_net_thousand` 這類 `_load_one`
     轉換完就丟棄的中繼欄名算進最終 schema,是文字描述本身的錯誤(表格
     本身原本就是照程式碼邏輯算對的,只有公式敘述沒跟上);改成精確集合
     公式,明確排除 `thousand_cols` 的中繼 key。
  2. **把單發驗證改成「整個 run 只有一次」**(§D)——原本的 `.claim` 鎖檔
     檔名含 `verifier_identity`,代表換一支驗證器程式碼就能對同一個
     `run_id` 拿到第二次 binding 機會,文字上禁止不夠,改成鎖檔路徑只用
     `run_id` 命名,結構上就不可能有第二次;新增 crash 持久性規則:鎖檔
     存在但沒有 receipt,直接判定 `BUILD_VERIFICATION_FAILED`,不能停在
     「還在等驗證」。
  3. **要求驗證器獨立重讀原始 cell**(§D)——原本驗證器只重讀雜湊/候選
     parquet/receipt,沒有要求真的重新打開原始檔案逐格核對 sidecar 的
     `raw_token`/覆蓋矩陣/locator 是否屬實;改成明確要求獨立解析路徑重建
     每一格證據。
  4. **sidecar key 改用真正無歧義的序列化**(§C.9)——原本
     `SHA-256(f"a|b|c")` 只是把有歧義的分隔字串拿去雜湊,雜湊本身不會
     消除歧義;改成凍結版本的 canonical JSON 陣列序列化。
  5. **收斂依賴鎖定決定**(§C.1)——確認專案已有的 `requirements.txt` 是
     給 Streamlit 雲端 app 用的,沒蓋到 openpyxl 等 Excel/parquet 完整
     相依鏈,也不是 hash 鎖定;凍結一個新的、專門給資料建置用的鎖定檔
     名稱跟角色。
  結論維持 `ROUND18_STATUS=DESIGN_BLOCKED`——**只因為**輸出根目錄路徑仍未
  核准,五項修正後已經沒有殘留的內部不一致。
- **第 19 輪(本次)**:Codex 獨立複查第 18 輪後指出兩個身分/路徑缺陷,
  逐一修補:
  1. **路徑改用完整內容位址**(§C.4/§F)——原本建議的輸出根目錄用
     `snapshot_id_v1` 的「前 12 碼」當子目錄名稱,12 碼十六進位不能宣稱
     無碰撞、也不是完整的內容位址,截斷之後目錄名稱反推不出完整身分;
     改成用完整 64 碼小寫十六進位當目錄名稱,path 守衛核對的是「目錄
     名稱逐字元等於 receipt 記錄的完整值」,不是核對前綴或長度。
  2. **加入執行環境身分**(§C.1)——`requirements-v2-data-build.lock` 只
     鎖套件版本,沒有把「實際執行的直譯器/作業系統/CPU 架構」這件事本身
     變成身分的一部分,理論上兩台環境不同但套件版本聲明相同的機器,可以
     產生同一個 `snapshot_id_v1` 卻不保證位元組完全相同的候選 parquet;
     新增凍結版本的 `runtime_environment_identity_v1`(跟 §C.9
     `dedup_key_v1` 同一套 canonical JSON 序列化紀律),納入
     `build_implementation_identity` 第二層;釐清 verifier 要重新驗證
     builder 宣告的環境身分是否算對,跟記錄 verifier 自己的執行環境
     指紋,是兩件不能混的事。
  結論維持 `ROUND19_STATUS=DESIGN_BLOCKED`——**只因為**輸出根目錄路徑
  仍未核准,兩項修正後身分模型跟建議路徑已經沒有殘留的精確性缺口。
- **第 20 輪(本次)**:Codex 獨立複查第 19 輪後指出一個窄化缺口,修補:
  1. **完整鎖定/安裝相符性契約**(§C.1/§C.5/§D)——原本 builder 端的
     fail-closed 規則只比對 `pandas`/`numpy`/`pyarrow`/`openpyxl` 四個
     具名套件的版本,但 `requirements-v2-data-build.lock` 定義成涵蓋
     「完整遞移相依鏈」,只比對四個名字證明不了整個環境真的相符;改成
     專用隔離環境 + marker 解析 + PEP 503 名稱正規化 + 完整清單比對
     (缺席/版本不符/多出未宣告套件都 fail-closed)+ 精確凍結的 bootstrap
     工具(`pip`/`setuptools`/`wheel`)例外清單,並釐清「安裝時 hash 驗證」
     跟「安裝後清單比對」是兩種不同語意的檢查,不能混為一談。彙總 build
     receipt 新增 `lock_selected_inventory`/`installed_inventory` 等
     欄位,verifier 新增第三項獨立重建職責。明確澄清這是 Phase B 的額外
     前置關卡,不取代原有的 `runtime_environment_source`/`dependency_
     lock_identity`。
  結論維持 `ROUND20_STATUS=DESIGN_BLOCKED`——**只因為**輸出根目錄路徑仍未
  核准,這項修正後鎖定/安裝相符性的定義已經沒有殘留的窄化缺口。
- **第 21 輪(本次)**:Codex 獨立複查第 20 輪後指出兩個定義還不夠精確到
  能被實作跟獨立重建,修補:
  1. **凍結精確的 PEP 508 marker 環境**(§C.1)——原文說 marker 解析套用
     `python_version_full`/`os_system`/`machine_arch` 三個欄位,但
     `sys.version` 不是 `packaging.markers` 定義的 `python_full_version`,
     三個欄位也蓋不到完整 marker 命名空間;改成凍結
     `marker_environment_v1`——直接捕捉
     `packaging.markers.default_environment()` 的完整 11 鍵回傳值,
     canonical JSON 物件 + `sort_keys=True` 序列化,雜湊
     `marker_environment_identity_v1` 收進 `runtime_environment_source`
     (13 個元素變 14 個);verifier 用 receipt 記錄的這個物件重新解析
     marker,不是用自己機器的 marker。
  2. **凍結精確的 `environment_creation_identity`**(§C.5)——原文只說
     「隔離環境建立+安裝過程本身的 receipt/雜湊」一句話,沒有精確 schema;
     改成完整定義 `environment_creation_receipt_v1`(schema tag/run_id/
     `preregistration_commit`/鎖定檔路徑+雜湊/marker 環境物件+雜湊/
     安裝工具身分/bootstrap 清單/安裝指令陣列/起訖時間戳/exit code/
     安裝報告的檔案雜湊(若有)/stdout·stderr 雜湊/兩份 inventory+雜湊/
     相符判定結果),canonical 序列化排除自身 `environment_creation_
     identity` 欄位後雜湊;必須在解析候選資料前排他建立完成;彙總 build
     receipt 記錄檔案路徑+檔案雜湊+內部身分值三者;verifier 核對檔案
     雜湊、重算內部身分、核對被引用證據,不宣稱能重建已銷毀的環境。
  結論維持 `ROUND21_STATUS=DESIGN_BLOCKED`——**只因為**輸出根目錄路徑
  仍未核准,這兩項修正後執行環境相關的定義已經沒有殘留的精確性缺口。
- **Checkpoint 22(本次,2026-08-08)**:**使用者明確核准**§C.4 建議的
  隔離輸出根目錄布局——`C:\dev\Project 1\tej_exports\v2_candidate\<完整
  64 碼小寫 snapshot_id_v1>\<run_id>\`,含 `cache/`/`build_receipts/`/
  `quality_sidecars/`/`verification_receipts/` 四個子目錄,路徑本身的
  拼寫、64 碼要求、子目錄佈局、path 守衛、保護路徑排除清單**全部維持第
  17-21 輪已經寫定的內容,一個字元都沒有改**——這次只改「這項還在等核准」
  變成「這項已經核准」的**狀態標記**。把這一項從 §F
  `PROPOSED_NOT_AUTHORIZED` 移到 `FROZEN`(標記
  `AUTHORIZED_PATH`,含核准日期 2026-08-08)。同時修正
  `preregistration_commit`(§C.1)敘述裡潛藏的循環論證:文件內文**不能**
  寫死「這次 commit 自己的 hash」這種自我指涉的字面值(commit 產生之前
  不可能知道它自己的 hash),改成明確要求「這是 builder 在 Phase B 執行
  當下,對 git repository 現場查詢(`git rev-parse HEAD` 或等價指令)
  得到的值,查不到/工作目錄髒/HEAD 有歧義,三種情況都要 fail-closed」
  ——不改身分公式的意圖,只是把「怎麼取得這個值」講清楚,拿掉自我指涉。
  結論改為 `PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED`——`BLOCKED_
  BEFORE_IMPLEMENTATION` 維持空,`PROPOSED_NOT_AUTHORIZED` 因為唯一一項
  已經核准而變成空,但 `MISSING_BEFORE_BUILD` 底下每一項依然明確
  `MISSING`,這個狀態**只**代表文件本身可以凍結,不構成 Phase A 實作或
  Phase B 執行的授權。這次 checkpoint 依 Codex 指示對本文件做一次範圍
  精確限定的 scoped git commit(見文末 git 紀錄,commit message
  `docs: freeze DataExport0806 V2 isolated build preregistration`)。
- **Checkpoint 23(本次)**:Codex 獨立複查 Checkpoint 22 後指出
  `preregistration_commit` 被定義成 `git rev-parse HEAD` 是一個具體的
  git 身分語意錯誤,不是新一輪設計、也不構成 Phase A 授權,純粹是
  勘誤,修補:
  1. **`preregistration_commit` 改成 path-scoped 查詢**(§C.1)——
     `HEAD` 代表整個 repository 現在指到哪裡,不是「這份文件最後一次被
     凍結在哪個 commit」;只要未來發生任何其他不相干的 commit(含 Phase
     A 實作本身的 commit),`HEAD` 就會前進,但這份文件沒有變。改成
     `git log -1 --format=%H -- <這份文件的路徑>`,並加上「現場位元組
     等於該 commit 的 blob」+「這個路徑沒有 staged/unstaged/untracked
     替代版本」+「文件維持追蹤狀態」三項額外驗證。
  2. **拿掉錯誤的「detached HEAD 是歧義」範例**——detached HEAD 只要能
     解析成單一完整 commit 就不是歧義,第一版本的例子是錯的,已刪除。
  3. **把「整個工作目錄必須乾淨」換成 scoped 乾淨度檢查**(§C.1)——這個
     repository 長期存在大量跟這次隔離建置無關的既有修改/未追蹤檔案
     (唯讀核對過,Checkpoint 22 commit 前的 `git status --short` 有
     100 行以上跟這次建置無關的既有差異),要求整個工作目錄乾淨在這個
     專案裡不可行也不必要;改成精確列舉「這次建置會用到的凍結建構/裁決
     輸入」(本文件本身、importer、extractor、builder、verifier、依賴
     鎖定檔、任何被明確 import 的共用 build 模組)清單,只檢查這份清單
     裡的路徑,repository 其他地方的既有工作不受影響、也不會卡住建置。
  4. **修正 §F MISSING_BEFORE_BUILD 最後一項**——Phase A 完整實作(含
     builder/verifier 程式碼+測試)那次未來的 commit,是另一個獨立的
     實作複查 checkpoint,**不是** `preregistration_commit`;個別程式碼
     的位元組身分已經由 `importer_identity`/`extractor_identity`/
     `builder_identity`/`verifier_identity`/`dependency_lock_identity`
     各自涵蓋,彙總 receipt 可以另外把那次 Phase A 實作 commit 的 hash
     當稽核用的中繼資料記錄下來,但不能被誤標成 `preregistration_
     commit`。
  維持 `PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED`/`FROZEN`/
  `AUTHORIZED_PATH`/`BUILD_NOT_RUN`/`PRODUCTION_NOT_APPROVED`/
  `trust_holding_pct=DIFF_UNRESOLVED`、所有不執行的禁止事項——這次只是
  修正一個具體的 git 身分定義錯誤,不是重新設計、也不解除任何禁止事項。

---

## A. 建置邊界凍結

*(第 17 輪未修改本節;內容跟第 15/16 輪版本逐字相同,唯讀複查後確認仍然
成立。)*

1. **這是建置完整性工作,不是績效/OOS/Gate/科學有效性驗證。** 任何一次隔離
   建置,不論成功與否,都不能被拿來回答「這個資料能不能用來賺錢」——那是
   `BUILD_VALIDATED` 之後、完全獨立的另一個階段 (政策文件 §11.7)。
2. **舊系譜、`tej_exports/inbox*`、已凍結的 V0/Gate 產物、生產環境
   `~/tej_cache` 全部是不可變、禁止的寫入/修改目標。** 隔離建置只能新增
   一個全新的、跟這些路徑不重疊的輸出根目錄 (見 §C.4)。
3. **第三輪的 scratchpad 快取維持 `DIAGNOSTIC_OUT_OF_SCOPE_BUILD`
   (政策文件 §11.7)**,不能被重用、推廣、改名,或當成正式候選建置呈報。
   `institutional_gross` 這個子目錄從第七輪起一直被 §10 系列的唯讀溯源裁定
   當診斷輸入使用,這份預註冊不改變它的地位,也不會把它升級成任何其他狀態。
4. **DataExport0806 維持 `V2_CANDIDATE_RESTATED_SNAPSHOT`;
   `institutional_gross.trust_holding_pct` 維持 `DIFF_UNRESOLVED`。** 就算
   未來的隔離建置成功執行、通過 `BUILD_VALIDATED`,這兩個狀態都不會因此改變
   ——建置成功只證明「資料被正確地、fail-closed 地搬進了隔離 cache」,不證明
   「兩份原始檔為什麼報不同數字」這個懸而未決的問題已經解決,也不構成生產
   核准。
5. **這輪文件結束後,正式候選建置依然是 `BUILD_NOT_RUN`。** 沒有任何程式碼
   被修改、沒有任何 import 被執行,狀態不會、也不應該因為寫了這份預註冊就
   往前推進。

---

## B. 完整建置範圍與精確輸出契約 (11 個 dataset,凍結順序;第 17 輪重寫)

順序**逐一核對** `tej_importer.py::DATASETS`(第 269-487 行)的字典定義順序,
兩者完全一致,不是另外發明的排序。

**第 17 輪核心修正:schema 精確化**——第 16 輪版本把欄位分成「必要」跟
「選用(來源缺席就跳過)」,Codex 指出這不是精確契約:同一個 dataset 在
不同時期的原始檔,選用欄位有沒有出現會不一樣,「schema 隨來源檔案而變」
本身就是缺陷。改成:

- **11 個 dataset 各自的最終欄位集合是固定的,精確公式(第 18 輪修正)**:

  ```
  final_columns = standard_keys + sorted(
      (rename_targets - thousand_intermediate_keys) ∪ thousand_final_targets
  ) + approved_supplement_columns
  ```

  其中 `standard_keys = ["stock_id", "stock_name", "date"]`(非 `static`
  dataset;`industry_map` 另有專屬順序,見下)、`rename_targets =
  DATASETS[dataset]["rename"]` 的**全部**值、`thousand_intermediate_keys =
  DATASETS[dataset]["thousand_cols"]` 的**鍵**集合(例如
  `_volume_thousand_shares`/`_foreign_net_thousand`/`_revenue_thousand`
  這類 `_load_one` 542-548 行轉換完就 `drop(columns=[src])` 丟棄的中繼
  欄名)、`thousand_final_targets = thousand_cols` 的**值**集合(例如
  `Trading_Volume`/`foreign_net`/`revenue`)。**第 17 輪版本的文字敘述
  (「等於 `rename` 的全部值」)沒有扣掉 `thousand_intermediate_keys`,
  這是文字本身的錯誤——下方 §B 表格從第 16 輪起就是直接照 `_load_one`
  的實際邏輯算出來的,結果本身沒有錯,只是敘述公式跟表格對不上。這裡把
  公式修到跟表格一致,不改表格數值。** 已核對:11 個 dataset 逐一套用這條
  公式,結果都跟下方表格逐字相符,候選輸出**不會**出現任何底線開頭的中繼
  欄名。
  這個集合**不因為某個原始檔缺了某欄就變動**。
- 某個原始檔缺了某個 `rename` 對應的來源欄位時(516-519 行目前的
  「跳過對應,不補值」行為),正確語意不是「這一批資料就沒有這一欄」,而是
  「這個目標欄位在這個原始檔涵蓋的列上,值是 `null`,原因是
  `SOURCE_COLUMN_ABSENT`」——**欄位本身永遠在最終 schema 裡**,程式碼必須
  改成明確補一欄全 `null`(dtype 仍照 §C.1 的契約),而不是讓 `keep = [c
  for c in keep if c in df.columns]`(558/526 行現況)直接讓整個目標欄位
  從輸出裡消失。**這是需要修改 `tej_importer.py`/新 builder 的具體行為
  變更,不只是文件描述,列進 §F MISSING_BEFORE_BUILD。**
- 如果一個 `rename` 目標欄位在**這個 dataset 涵蓋的所有原始檔**裡通通缺席
  (不是某幾個檔案缺、是全部檔案都缺),代表 `DATASETS` 裡這條 `rename`
  映射已經不對應任何真實來源欄位——這不能被靜默接受成「全部都是
  `SOURCE_COLUMN_ABSENT` 的 null」,必須在 builder 彙總完 11 個 dataset
  各自的逐檔覆蓋矩陣後 fail-closed(§C.9 的逐檔逐欄位 presence 矩陣是這個
  檢查的資料來源)。

**日期語意(跟第 16 輪相同,重新列一次不變的部分)**:`_parse_dates`
(256-266 行)對主 `date` 欄位,若 `date_format` 是 `"%Y%m"` 或 `"%Y/%m"`
(只有月無日),`pd.to_datetime` 補當月 1 號,輸出固定是 `YYYY-MM-01`
——只影響 #3/#4/#5/#6/#11 的**主 `date` 欄**。其餘情況(含所有
`extra_date_cols` 如 `release_date`)是真正的日級日期。

**輸出路徑契約**:非 `static` 的 10 個 dataset,輸出是
`<candidate_root>/<dataset>/<stock_id>.parquet`;`static=True` 的
`industry_map` 是單一檔案 `<candidate_root>/industry_map.parquet`。
`<candidate_root>` 的確切路徑見 §C.4(第 17 輪已給出建議、待核准)。

**dtype 契約**:見 §C.1「顯式型別凍結」——所有數值目標欄位(含 `quarter`)
顯式轉 `float64`;`stock_id`/`stock_name`/`date`/`release_date`/industry
code 與 name 欄位/`group_name` 顯式轉字串,不受 `pd.to_numeric` 影響。

### 逐 dataset 最終欄位契約(第 17 輪:欄位集合固定,不再標「選用」)

欄位順序規則(第 18 輪修正成跟上面的精確公式一致):除 #9 外都是
`["stock_id", "stock_name", "date"] + sorted((rename 全部值 −
thousand_cols 中繼 key) ∪ thousand_cols 目標值)`,supplement 欄位(若有)
以 `SUPPLEMENT_SCHEMAS`(604-608 行)凍結的順序接在後面(merge 附加,
不進 `sorted()`;例如 `revenue_last_year` 的 supplement 固定是
`["revenue_last_year", "cum_revenue_last_year"]` 這個順序,不是 merge
之後再排序一次)。`#9 industry_map` 是插入順序(526 行),不排序。

| # | dataset | 主 `date` 語意 | **最終欄位(永遠存在,可能為 null)** | supplement 欄位(可能因覆蓋窗口而 null) |
|---|---|---|---|---|
| 1 | `price_valuation` | 日級 | `PBR_TEJ`, `PBR_TSE`, `PER_TEJ`, `PER_TSE`, `Trading_Volume`, `close`, `dividend_yield_TEJ`, `dividend_yield_TSE`, `max`, `min`, `open` | 無 |
| 2 | `institutional_flow` | 日級 | `dealer_net`, `foreign_net`, `trust_net` | 無 |
| 3 | `fundamentals_quarterly` | 月初 | `eps`, `net_income`, `operating_income` | `roe_after_tax`(`LEGACY_DERIVED_SUPPLEMENT`,2019-03~2026-03 外為 null,原因 `SUPPLEMENT_KEY_NOT_COVERED`) |
| 4 | `revenue_growth` | 月初 | `revenue_yoy_pct` | 無 |
| 5 | `monthly_revenue` | 月初;`release_date` 日級 | `cum_revenue`, `release_date`, `revenue`, `revenue_yoy_pct` | `revenue_last_year`, `cum_revenue_last_year`(同上) |
| 6 | `financial_statements` | 月初;`release_date` 日級 | `capex`, `current_assets`, `current_liabilities`, `eps`, `equity`, `gross_profit`, `net_income`, `operating_cash_flow`, `operating_income`, `quarter`, `release_date`, `revenue`, `total_assets`, `total_liabilities` | `recurring_net_income`(同上) |
| 7 | `institutional_gross` | 日級 | `foreign_buy`, `foreign_holding_pct`, `foreign_sell`, `trust_buy`, `trust_holding_pct`, `trust_sell` | 無;**`trust_holding_pct` 維持 `DIFF_UNRESOLVED`(§A.4)** |
| 8 | `margin_balance` | 日級 | `margin_balance`, `margin_buy`, `margin_change`, `margin_sell`, `margin_usage_rate`, `short_balance`, `short_margin_ratio` | 無 |
| 9 | `industry_map` | 無(靜態,單一檔案,插入順序不排序) | `stock_id`, `stock_name`, `tse_ind_code`, `tse_ind_name`, `tej_ind_code`, `tej_ind_name`, `tej_subind_code`, `tej_subind_name` | 無 |
| 10 | `tdcc_weekly` | 日級 | `holders`, `ratio_1000up`, `ratio_1to5`, `ratio_5to10`, `ratio_le1`, `total_lots_thousand` | 無 |
| 11 | `director_pledge` | 月初,`%Y/%m`(跟 #3-6 的 `%Y%m` 不同,476 行註解) | `director_holding_pct`, `group_name`, `pledge_pct` | 無 |

**逐檔覆蓋矩陣(取代第 16 輪的「選用/必要」二分法)**:每個 dataset 的
build receipt 必須含一個矩陣,列是這個 dataset 實際讀到的每一個原始檔,
欄是上表列出的每一個最終欄位,值是四選一:`PRESENT`(該檔有這欄且至少
有一格非 null)、`SOURCE_COLUMN_ABSENT`(該檔完全沒有這個來源欄位)、
`PRESENT_ALL_NULL`(該檔有這欄但全部是空白/無法解析)、`NOT_APPLICABLE`
(該欄是 supplement 欄位,不屬於這個原始檔案的責任範圍)。精確 schema 見
§C.9。

**「共用管線」的意思**:所有 11 個 dataset 都經過同一支
`tej_importer.load_source()`(927-970 行),依序呼叫
`_manifest_preflight`(173-202 行,manifest 集合完全相等 + SHA-256 逐檔核對)、
`_load_one`→`_check_required_cols`(499-508 行)+`_check_valid_keys`
(205-220 行)、`_check_duplicate_key_conflicts`(564-597 行)、
`_check_sanity_floor`(901-924 行)。這是**同一套邏輯**,不是 11 份各自獨立
維護的檢查——驗證一次共用函式,等於同時驗證 11 個 dataset 的這一層防護。
3 個有 supplement 的 dataset (#3/#5/#6) 額外經過 `_verify_supplement`
(781-898 行)。**第 17 輪的架構決定(§D)明確要求:這支函式的職責維持在
「確定性解析、顯式型別轉換、key/schema 驗證、supplement 合併斷言、產生
品質證據紀錄」,不擴充成多 dataset 協調或自我驗證——那是新 builder 腳本
的職責。**

**這份表格不主張「現在的原始檔跟程式碼假設一致」**:這輪是唯讀檢查,沒有
執行任何一次真正的匯入,所以無法確認 `required_cols`/`rename` 列出的中文
欄名,今天在磁碟上的 DataExport0806 檔案裡是否還存在。如果連 `required_
cols` 都不存在,`_check_required_cols` 會在讀檔當下直接 raise(設計上刻意
的 fail-closed 行為);如果是非 `required_cols` 的 `rename` 欄位缺席,依
上面新規則記 `SOURCE_COLUMN_ABSENT` 而不是讓欄位消失——但在真的執行
Phase B 之前,實際覆蓋率本身是未知數,不能假裝已經驗證過。

---

## C. 八項政策前提 → 可執行驗收標準

對應政策文件 §11.6 的八項前提 (D7)。每項給:輸入、判定公式/邏輯、PASS 證據
寫進哪裡、fail-closed 條件與退出行為、現有實作是否已滿足。

### C.1 內容定址的身分模型(第 17 輪擴充:builder 身分 + 依賴身分)

**輸入身分(每一項都是對應檔案**位元組本身**的 SHA-256,用
`tej_importer._sha256_of`(131-139 行)同一套 8 MiB 串流演算法)**:

```
manifest_identity              = SHA-256(tej_exports/DataExport0806_manifest.csv 位元組)
manifest_sha256_file_identity  = SHA-256(tej_exports/DataExport0806_manifest.sha256 位元組)
supplement_identity            = SHA-256(tej_exports/legacy_supplement/receipt.json 位元組)
importer_identity              = SHA-256(tej_importer.py 位元組)                       # 確定性解析/驗證函式庫,建置當下
extractor_identity             = SHA-256(scripts/extract_legacy_supplement.py 位元組)   # 建置當下
builder_identity                = SHA-256(新 builder/orchestrator 腳本位元組)            # 建置當下;第 17 輪從
                                                                                          # 「orchestrator_identity」改名,
                                                                                          # 語意更精確(見 §D 職責劃分)
dependency_lock_identity        = SHA-256(requirements-v2-data-build.lock 位元組)      # 建置當下;第 17 輪新增
                                                                                          # 概念,第 18 輪凍結精確檔名
                                                                                          # 跟角色(見下方說明)
runtime_environment_identity_v1 = 見下方「執行環境身分」專節                            # 建置當下;第 19 輪新增,
                                                                                          # 不是檔案雜湊,是一組 canonical
                                                                                          # 序列化後的環境觀測值雜湊
preregistration_commit         = 見下方「`preregistration_commit` 的取得方式」——建置當下由 builder
                                  對 git repository 現場查詢得到,不是寫死在本文件裡的字面值
candidate_schema_version       = "dataexport0806_v2_candidate_schema_v1"   # 字面常數,綁死本文件 §B 的輸出契約版本
```

**`preregistration_commit` 的取得方式(Checkpoint 22 拿掉了自我指涉的
循環論證,但誤把它定義成 `git rev-parse HEAD`;Checkpoint 23 修正這個
具體錯誤)**——Codex 指出 `git rev-parse HEAD` 是錯的:`HEAD` 代表**整個
repository 現在指到哪個 commit**,不是「這份預註冊文件最後一次被凍結
在哪個 commit」。這兩者在這個專案裡**必然**會分岔——未來只要發生任何
其他 commit(例如 Phase A 實作程式碼的 commit、甚至任何跟這次建置完全
無關的其他工作的 commit),`HEAD` 就會往前移動,但這份文件的內容(跟它
被凍結的那個時間點)完全沒變。如果 `preregistration_commit` 綁定
`HEAD`,`snapshot_id_v1` 會在文件根本沒被改過的情況下,因為專案裡任何
其他不相干的 commit 而跟著改變——這既不是內容定址該有的行為,也違背了
「這個身分只跟這份文件的凍結狀態有關」的原始意圖。**正確定義**:

- `preregistration_commit` = **最後一次改動這份文件這個路徑的 commit**,
  用一個明確 path-scoped、不含糊的 git 查詢取得,等價於:

  ```
  git log -1 --format=%H -- "docs/預註冊_DataExport0806_V2隔離建置.md"
  ```

  **不是** `git rev-parse HEAD`,也不是任何跟 `HEAD` 目前指向哪裡有關的
  查詢——查詢對象永遠是**這個檔案路徑自己的最新一筆 commit 歷史**,不受
  repository 裡其他路徑之後又發生了多少次不相干 commit 影響。
- **額外的證據完整性檢查(Checkpoint 23 新增,不只查出一個 hash 就算數)**:
  builder 除了查出上面的 commit hash,還必須驗證:
  1. **現場檔案位元組等於該 commit 裡同一個路徑的 blob**——這個檔案在
     磁碟上現在的內容,必須逐位元組等於 `preregistration_commit` 那個
     commit 記錄的版本,不能是「查到了某個 commit hash,但磁碟上這個檔
     案其實已經被繼續編輯過又沒有再 commit」這種脫節狀態。
  2. **這個路徑沒有任何 staged/unstaged/untracked 的替代版本**——工作區
     跟索引裡,這個特定路徑必須乾淨(沒有待commit的修改、沒有暫存的
     修改、也沒有另一個未追蹤的同名檔案冒充)。
  3. **這份文件必須維持在 git 追蹤狀態**——不能是已經被 `git rm` 從索引
     移除、只留在磁碟上的孤兒檔案。
  任一項不成立,直接 fail-closed,不產生 `snapshot_id_v1`。
- **Fail-closed 條件精確化(Checkpoint 23 修正,移除第一版本錯誤地要求
  「整個工作目錄乾淨」跟「detached HEAD 視為歧義」這兩條規則)**——只在
  以下情況 fail-closed:
  1. git 無法對這個路徑解析出唯一一筆 commit/blob(例如根本不是 git
     repository、這個路徑從來沒被 commit 過、查詢指令本身失敗)。
  2. 上面「額外的證據完整性檢查」三項裡任何一項不成立。
  **detached HEAD 本身不是歧義**——只要它能解析成單一一個完整 commit,
  就是明確的,不需要額外標記成 fail-closed 條件;第一版本把「detached
  HEAD」直接當成歧義範例是錯的,已經拿掉,不再出現在這份文件裡。**這條
  規則刻意不检查 repository 其他路徑乾不乾淨**——那是下方「Phase B 前置
  的 scoped 乾淨度檢查」的職責,兩者故意分開,見下一段。
- 這條規則**只是把「怎麼取得這個值」講清楚,不改變 `preregistration_
  commit` 這個身分成分原本的意圖**——它指的是「這份預註冊文件本身最後
  一次被審查、凍結的那個 commit」,不是 Phase A 完整實作(builder/
  verifier 程式碼+測試)那次未來的 commit——兩者是不同的 commit、不同的
  概念,§F MISSING_BEFORE_BUILD 最後一項的敘述也已經修正,不再把兩者
  混為一談(見 §F)。
- **本文件不會、也不能在文件內文任何地方寫出任何一次 commit 的 hash
  字面值**——要查 `preregistration_commit` 的實際值,查 `git log` 本身,
  不是查這份文件。

**Phase B 前置的 scoped 乾淨度檢查(Checkpoint 23 新增,取代第一版本
誤植的「整個工作目錄必須乾淨」要求)**——這個專案的工作目錄裡,長期存在
大量跟這次隔離建置完全無關的既有修改/未追蹤檔案(§E.1 表格以外的,例如
`beat_0050/`、`core/`、其他 `docs/*.md` 研究文件——唯讀核對過,Checkpoint
22 commit 前的 `git status --short` 有 100 行以上跟這次建置無關的既有
差異)。**Phase B 的前置檢查範圍必須是精確列舉的「這次建置會用到的凍結
建構/裁決輸入」清單,不是整個 repository**:

- 這份預註冊文件(`docs/預註冊_DataExport0806_V2隔離建置.md`)。
- `tej_importer.py`(importer)。
- `scripts/extract_legacy_supplement.py`(extractor)。
- 新 builder 腳本。
- 獨立 verifier 腳本。
- `requirements-v2-data-build.lock`(依賴鎖定檔)。
- 任何被上述任一支程式**明確 import** 的共用 build 模組(如果實作階段
  真的拆出這種共用模組的話)。

以上**每一個**都要求:必須是 git 追蹤狀態、磁碟上現在的位元組必須等於
它被審查/凍結的那個 commit 裡的版本(逐一對應 §C.1 各自的 identity 欄位
——`importer_identity`/`extractor_identity`/`builder_identity`/
`verifier_identity`/`dependency_lock_identity`/`preregistration_
commit`)——任一項不符,Phase B 直接 fail-closed。**Repository 裡任何
不在這份清單上的路徑,不管是已修改還是未追蹤,都不能、也不會進入這個
判定,也不能讓建置卡住**——`beat_0050/`/`core/` 之類的既有研究工作繼續
在同一個工作目錄裡進行,不受這次資料建置的 fail-closed 規則影響,兩者
互不干擾。

`verifier_identity`(獨立驗證器腳本的位元組 SHA-256)**依然刻意不進這個
公式的任何一層**——第 16 輪就已凍結這個原則,第 17 輪的架構決定(§D)進一步
強化理由:verifier 是裁決者,連 import builder 都不行,當然不能反過來讓
builder 用的身分公式依賴 verifier。

**組合公式(三層不變,只有第二層新增兩個輸入;UTF-8 編碼、`"\n"` 分隔、
最後一行不含結尾換行、欄位順序固定如下、雜湊值一律小寫十六進位)**:

```
# 第一層:來源資料身分(不變)
source_data_identity = SHA256(
    f"manifest_sha256={manifest_identity}\n"
    f"manifest_sha256_file_sha256={manifest_sha256_file_identity}\n"
    f"supplement_receipt_sha256={supplement_identity}"
).hexdigest()

# 第二層:建置實作身分(第 17 輪新增 builder_sha256、dependency_lock_sha256;
# 第 19 輪新增 runtime_environment_identity_v1——沒有這一項,兩次用同一套
# 原始碼/鎖定檔、但在不同 Python/OS/架構上執行的建置,會得到同一個
# snapshot_id_v1,卻可能產生不同的 candidate parquet 位元組,身分公式就
# 不再是真正的內容定址)
build_implementation_identity = SHA256(
    f"importer_sha256={importer_identity}\n"
    f"extraction_script_sha256={extractor_identity}\n"
    f"builder_sha256={builder_identity}\n"
    f"dependency_lock_sha256={dependency_lock_identity}\n"
    f"runtime_environment_identity_v1={runtime_environment_identity_v1}\n"
    f"preregistration_commit={preregistration_commit}\n"
    f"candidate_schema_version={candidate_schema_version}"
).hexdigest()

# 第三層:對外呈現的組合識別碼(不變)
snapshot_id_v1 = SHA256(
    f"source_data_identity={source_data_identity}\n"
    f"build_implementation_identity={build_implementation_identity}"
).hexdigest()
```

**依賴/執行環境身分的補充規則(第 17 輪新增,回應「就算原始碼跟來源檔案
雜湊都沒變,Python/pandas/pyarrow/openpyxl 版本不同,candidate parquet 的
位元組甚至解析行為都可能不同」)**:

- `dependency_lock_identity` 只雜湊**委任鎖定檔本身**,不雜湊「當下環境
  實際裝了什麼」——鎖定檔是聲明。

**PEP 508 marker 環境 `marker_environment_v1`(第 21 輪新增,修正第 20
輪「marker 解析套用 `python_version_full`/`os_system`/`machine_arch`」這
句話本身的錯誤)**:Codex 指出 `sys.version` 根本不是 PEP 508 的
`python_full_version` marker 變數(`sys.version` 含編譯器/位元資訊等
非 marker 語彙的內容,`python_full_version` 是 `packaging` 套件自己定義
的精簡格式),而且光憑三個欄位(`python_version_full`/`os_system`/
`machine_arch`)蓋不到 PEP 508 完整的 marker 命名空間——鎖定檔裡的
environment marker(例如 `; python_version >= "3.9"`、
`; sys_platform == "win32"`)如果解析用的環境變數不精確,`lock-selected
inventory`(§C.1 下方「完整鎖定/安裝相符性契約」)算出來的結果就可能
是錯的,而錯誤本身還沒有一個可以精確重現、獨立核對的定義。第 21 輪凍結:

```
marker_environment_v1 = {
    # 鍵集合逐一對應 packaging.markers.default_environment() 回傳的鍵,
    # 也是 packaging.markers.Marker.evaluate() 實際會查詢的 marker 命名空間
    "implementation_name": ...,               # 例如 "cpython"
    "implementation_version": ...,            # 例如 "3.11.9"
    "os_name": ...,                           # 例如 "nt"
    "platform_machine": ...,                  # 例如 "AMD64"
    "platform_python_implementation": ...,    # 例如 "CPython"
    "platform_release": ...,
    "platform_system": ...,                   # 例如 "Windows"
    "platform_version": ...,
    "python_full_version": ...,               # packaging 定義的精簡版本字串,不是 sys.version
    "python_version": ...,                    # 例如 "3.11"
    "sys_platform": ...,                      # 例如 "win32"
}
```

**凍結規則**:上面 11 個鍵**逐一對應**、**只能對應**
`packaging.markers.default_environment()` 這個函式在建置當下實際回傳
的鍵值——**捕捉這個函式的回傳值,不是自己另外拼湊一套等價欄位**,這樣
才能保證跟 `Marker.evaluate()` 真正使用的命名空間完全一致。**每個值都
必須是字串**(`packaging.markers.default_environment()` 的回傳值本來就
全是字串)——出現非字串、`null`、缺鍵或多出鍵,直接 fail-closed,不猜測
或補預設值。**Canonical 序列化**:轉成 canonical JSON **物件**(不是像
`dedup_key_v1`/(舊)`runtime_environment_source` 那樣用陣列——這裡刻意
用物件,因為 marker 環境的鍵名本身就是規格定義好的固定集合,用物件的
`key: value` 語意比陣列位置語意更不容易在維護時對錯位置),鍵順序固定
為上面 11 個鍵**依英文字母排序**(`ensure_ascii=True`, `separators=(",",
":")`, `sort_keys=True`——用 `sort_keys=True` 而不是手動維護插入順序,
避免未來新增 `packaging` 版本多出欄位時忘記同步調整順序凍結),UTF-8
編碼,`hashlib.sha256(...).hexdigest()` 小寫輸出:

```
payload = json.dumps(
    marker_environment_v1,
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
marker_environment_identity_v1 = hashlib.sha256(payload).hexdigest()
```

`marker_environment_v1`(完整物件)跟 `marker_environment_identity_v1`
(雜湊)兩者都要逐一寫進彙總 build receipt——跟 `runtime_environment_
source` 的先例一樣,只記雜湊沒用,獨立驗證器要有原始物件才能重算。

**執行環境身分 `runtime_environment_identity_v1`(第 19 輪新增,取代第
17/18 輪「只把版本字串記進 receipt,不進身分公式」的作法;第 21 輪把
`marker_environment_identity_v1` 收進來當第 14 個輸入)**:Codex 指出
單純把 `sys.version`/`pandas.__version__` 等字串記錄進 receipt,而不讓它們
參與 `build_implementation_identity`/`snapshot_id_v1` 的計算,是不夠的
——兩次執行只要來源資料、程式碼、鎖定檔位元組都沒變,但剛好在不同
Python/OS/CPU 架構的機器上跑,現行公式會算出**同一個** `snapshot_id_v1`,
即使實際產生的 candidate parquet 位元組或解析行為可能不同,這違反
「同一個身分等於同一份內容」的內容定址精神。第 19 輪凍結、第 21 輪擴充:

```
runtime_environment_source = [
    "runtime_environment_identity_v1",   # schema/version tag,固定字面值
    python_implementation,               # platform.python_implementation(),例如 "CPython"
    python_version_full,                 # sys.version 完整字串(含編譯器/位元資訊,不只是 "3.11.9")——
                                          # 這是機器可讀的完整直譯器辨識資訊,跟 marker 解析用的
                                          # python_full_version 是兩個不同語意的欄位,不能互相取代
    os_system,                           # platform.system(),例如 "Windows"
    os_release,                          # platform.release()
    machine_arch,                        # platform.machine(),例如 "AMD64"
    pandas_version,                      # pandas.__version__
    numpy_version,                       # numpy.__version__
    pyarrow_version,                     # pyarrow.__version__
    openpyxl_version,                    # openpyxl.__version__
    parquet_engine,                      # 固定字面值 "pyarrow"(to_parquet 預設引擎,凍結避免未來偷換)
    excel_engine,                        # 固定字面值 "openpyxl"(read_excel 讀 .xlsx 用的引擎)
    dependency_lock_identity,            # 把 §C.1 已經算出來的鎖定檔雜湊也收進來,環境身分跟宣告的鎖定內容綁在一起
    marker_environment_identity_v1,      # 第 21 輪新增(第 14 個元素)——不同的 marker 解析環境
                                          # 不能共用同一個 build 身分,即使前 13 個元素完全相同
]
payload = json.dumps(
    runtime_environment_source,
    ensure_ascii=True,        # 跟 §C.9 的 dedup_key_v1 同一套規則:非 ASCII 一律轉義,位元組序不隨系統設定變動
    separators=(",", ":"),    # 緊湊分隔,不允許可選空白
).encode("utf-8")
runtime_environment_identity_v1 = hashlib.sha256(payload).hexdigest()   # 小寫十六進位
```

跟 §C.9 `dedup_key` 同一套 canonical 序列化紀律(第 19 輪凍結項目,逐一
對應,第 21 輪把「13 個元素」更新成「14 個元素」):**schema/version
tag** = 字面值 `"runtime_environment_identity_v1"`,固定放陣列第一個
元素;**欄位順序** = 上面 **14 個**元素的固定順序;**null
表示法** = 任何欄位真的無法取得時(理論上不該發生,`platform`/套件的
`__version__` 都是同步呼叫、不該失敗)用 JSON 原生 `null`,不是空字串或
字面文字 `"null"`,而且這種情況本身要另外 fail-closed(見下);**UTF-8
編碼**/**JSON escaping/分隔符號**/**小寫 SHA-256 輸出**跟 `dedup_key_v1`
完全一致,不重複列一次規則。

`runtime_environment_identity_v1` 進入 §C.1 上方 `build_implementation_
identity` 公式的第二層(新增第 5 個輸入),因此:**兩次建置只要宣告的
執行環境指紋不同,即使來源資料/程式碼/鎖定檔位元組完全相同,
`snapshot_id_v1` 也必須不同**——這是第 19 輪要修的核心缺口,舊版公式
做不到這件事。

- **builder 端的 fail-closed 規則(第 20 輪重寫:從「只比對四個套件」改成
  「完整鎖定/安裝相符性契約」)**——第 19 輪版本只比對
  `runtime_environment_source` 裡四個具名套件(`pandas_version`/
  `numpy_version`/`pyarrow_version`/`openpyxl_version`)的版本,Codex
  指出這跟 `requirements-v2-data-build.lock`「涵蓋完整遞移相依鏈」的
  定義(§C.1 下方「精確凍結的鎖定檔名稱跟角色」)不一致——只比對四個
  頂層套件,不能證明「整個環境」真的跟鎖定檔一致,任何一個沒被列進這四
  個名字的遞移相依套件版本漂移,現行規則完全抓不到。第 20 輪凍結完整
  契約:

  1. **專用隔離環境**:Phase B 必須在**專門為這次資料建置新建的隔離
     環境**裡執行(例如一個乾淨的 venv),用
     `pip install --require-hashes -r requirements-v2-data-build.lock`
     (或等價的 hash 校驗安裝方式)安裝——**不能沿用**專案既有的一般
     開發/`requirements.txt` 環境,否則「剛好裝著相容版本」可能只是巧合,
     不是鎖定檔真的被遵守。
  2. **marker 解析 + 套件名稱正規化(第 21 輪修正:解析用的環境是精確
     凍結的 `marker_environment_v1`,不是 `python_version_full`/
     `os_system`/`machine_arch` 這三個粗略欄位)**:鎖定檔裡可能有依
     PEP 508 environment marker 才生效的項目(例如
     `; python_version >= "3.9"`、`; sys_platform == "win32"`)——
     「lock-selected inventory」定義為:用上方凍結的
     `marker_environment_v1`(`packaging.markers.default_environment()`
     捕捉下來的完整 11 鍵 marker 命名空間)當 `packaging.markers.Marker.
     evaluate(environment=marker_environment_v1)` 的 `environment` 參數,
     解析鎖定檔每一條目的 marker 之後,實際會被選中安裝的套件名稱+版本
     集合。**不能用 `sys.version`/`platform.system()`/`platform.
     machine()` 這類臨時拼湊的欄位子集去頂替**——那三個欄位涵蓋不了
     PEP 508 完整命名空間,`python_version_full` 也不是
     `packaging.markers` 定義的 `python_full_version`。套件名稱一律先做
     PEP 503 正規化(小寫、`-`/`_`/`.` 視為等價,合併成單一 `-`)再比較,
     避免 `PyYAML` vs `pyyaml`、`typing_extensions` vs
     `typing-extensions` 這類字面不同但實際同一個套件的假陽性不符。
  3. **完整清單比對,不是抽樣比對四個名字**:builder 列出隔離環境裡
     **全部**第三方套件(例如用 `importlib.metadata.distributions()`),
     正規化名稱後,跟上面算出的 `lock-selected inventory` 做**完整集合
     比對**——鎖定檔裡有但環境裡缺席、版本不符、或環境裡有但鎖定檔沒
     宣告過的「多出來的第三方套件」,三種情況都直接 fail-closed,不設
     白名單以外的例外。
  4. **bootstrap 工具的例外是精確凍結的清單,不是開放式的**:`pip`/
     `setuptools`/`wheel`(正規化名稱後)這三個、也**僅**這三個,允許不
     參與上面的完整比對(全新 venv 建立時它們本來就會存在,鎖定檔通常
     不會、也不需要把它們釘死);它們的實際版本仍然要記錄進 receipt 的
     獨立欄位(`bootstrap_tool_inventory`),不是被忽略,只是不算進
     「相符/不符」的判定裡。
  5. **釐清雜湊驗證跟清單比對是兩件不同的事**:鎖定檔裡的 hash(`--
     require-hashes`)驗證的是**安裝當下下載到的安裝檔案**(wheel/sdist)
     位元組是否等於鎖定檔宣告的雜湊——這是**安裝時**的來源真實性檢查。
     安裝完成之後,已經解壓/安裝進環境的套件目錄**沒有「wheel 檔案雜湊」
     這種東西可以重新算**(檔案已經不是那個 wheel 了)——**安裝後**要
     確認「環境現在的狀態是否符合鎖定」,靠的是上面第 3 點的正規化完整
     名稱+版本清單比對,不是假裝可以對已安裝的套件重新算出一個「wheel
     檔案雜湊」來比。
  6. **建置在完整比對通過之前,不能計算 `runtime_environment_identity_
     v1`/`snapshot_id_v1`**——任一項不符,直接 raise,不算出一個「跟
     鎖定檔矛盾」的身分值再繼續往下跑(跟第 19 輪原本的精神一致,只是
     把「不一致」的判定範圍從四個套件擴大成完整清單)。
- **獨立驗證器的三個分開的職責(第 19 輪先訂了前兩個,第 20 輪加第三個,
  避免搞混『builder 的執行環境』跟『verifier 自己的執行環境』,也避免
  verifier 假裝能穿越回去重新觀測一台可能已經不存在的建置機器)**:
  1. **重新驗證 builder 宣告的執行環境身分**:從彙總 build receipt 裡
     記錄的、**不可變**的 `runtime_environment_source` 原始欄位值(不是
     builder 算好的 `runtime_environment_identity_v1` 雜湊值本身)出發,
     verifier 自己**獨立**照上面同一套 canonical 序列化規則重新計算一次
     雜湊,核對是否等於 receipt 裡記錄的 `runtime_environment_identity_
     v1`,再核對這個值是否正確參與了 receipt 記錄的 `build_
     implementation_identity` 組合公式——這是在查「builder 聲稱的環境
     指紋,有沒有真的算對、有沒有真的被算進最終身分」,**不是**在查
     「builder 執行當下的環境是不是真的長這樣」(那件事在建置當下已經
     由 builder 自己的 fail-closed 規則把關,verifier 事後沒有辦法穿越
     回去重新觀測一台可能已經不存在的建置機器)。
  2. **記錄 verifier 自己的執行環境指紋**:verifier 用**同一套**
     `runtime_environment_identity_v1` canonical 序列化規則,獨立觀測
     並記錄**它自己執行環境**的版本字串,寫進驗證 receipt 的獨立欄位
     (例如 `verifier_runtime_environment_identity_v1`)——**這個值不
     參與 `snapshot_id_v1` 或 `build_implementation_identity` 的計算,
     單純是驗證過程本身的稽核紀錄**,不能跟 builder 的
     `runtime_environment_identity_v1` 混用或互相取代;兩者本來就是兩台
     可能不同的機器、不同的時間點,語意上不是同一件事。
  3. **獨立重建 lock-selected inventory 並核對完整相符判定(第 20 輪
     新增,第 21 輪修正 marker 環境的來源)**:verifier **自己獨立解析**
     `requirements-v2-data-build.lock`(讀委任提交的鎖定檔本身,不透過
     builder 的任何函式),**用彙總 build receipt 記錄的
     `marker_environment_v1` 這個確切物件**(不是 verifier 自己執行環境
     的 marker,兩者可能是不同機器)當 `Marker.evaluate()` 的
     `environment` 參數,套用跟 builder 端相同、但獨立實作的 marker
     解析 + PEP 503 名稱正規化規則,從零重新算出 `lock-selected
     inventory`,核對是否等於彙總 build receipt 記錄的
     `lock_selected_inventory`/`lock_selected_inventory_sha256`;順便
     核對 `marker_environment_v1` 的 canonical 序列化重新雜湊一次是否
     等於 receipt 記錄的 `marker_environment_identity_v1`。再核對 receipt
     記錄的 `installed_inventory`/`installed_
     inventory_sha256` 兩者的 canonical 序列化跟雜湊本身內部一致(序列化
     `installed_inventory` 陣列重新雜湊一次,確認等於記錄的
     `installed_inventory_sha256`);最後核對 receipt 記錄的「完整相符
     判定」(equality decision)確實是從這兩份記錄下來的清單正確比較出來
     的結果。**這件事的本質是「核對 receipt 內部的記錄跟推論有沒有自洽、
     有沒有算對」,不是「重新裝一次那個隔離環境、實際去看當時真的裝了
     什麼」**——builder 的隔離環境可能執行完就銷毀了,verifier 沒有辦法
     也不需要穿越回去重新觀測它,跟第 19 輪對 `runtime_environment_
     identity_v1` 的驗證立場完全一致。
- **完整鎖定/安裝相符性契約不是身分公式的替代品(第 20 輪新增澄清)**:
  上面的完整清單比對是 **Phase B 執行前的一道額外前置關卡**(builder
  fail-closed 檢查),`runtime_environment_source` 原本就有的必要欄位
  (`python_implementation`/`python_version_full`/.../`pandas_version`/
  `numpy_version`/`pyarrow_version`/`openpyxl_version` 等)跟 `build_
  implementation_identity` 裡的 `dependency_lock_identity` 都**維持不變、
  照樣存在**——完整清單比對只是多加一層「確認環境真的乾淨、真的完整照
  鎖定檔裝」的前置檢查,不是拿掉或取代原本兩個身分欄位。
- **精確凍結的鎖定檔名稱跟角色(第 18 輪,回應「`git ls-files | grep -i
  lock` 沒東西,但專案根目錄其實已經有 `requirements.txt`,兩者關係要講
  清楚」)**:唯讀核對過 `requirements.txt`(已追蹤,64 行,內容開頭明講
  「Streamlit Community Cloud 依賴」)——這份檔案是給 Streamlit 雲端 app
  用的執行環境鎖定(`streamlit`/`pandas==2.2.2`/`numpy==1.26.4`/
  `pyarrow==16.1.0` 等,附註解釋鎖 `numpy` 1.x 是為了避開 ABI 相容性
  segfault),**不覆蓋** `tej_importer.py`/新 builder 讀 `.xlsx` 需要的
  `openpyxl`(`requirements.txt` 完全沒提到這個套件)、也沒覆蓋這些套件的
  完整遞移相依鏈,而且是單純 `==` 版本釘選,不是有 hash 的鎖定檔——不能
  直接拿來當 `dependency_lock_identity` 的輸入。**凍結一份新的、專門給
  這次資料建置用的鎖定檔:`requirements-v2-data-build.lock`**,放在專案
  根目錄(跟 `requirements.txt`/`requirements-d2-timing.txt` 同一層,
  用不同檔名區分用途,不是取代或合併既有檔案),Phase A 實作時產生,內容
  是資料建置實際用到的套件(至少 `pandas`/`pyarrow`/`openpyxl`)加上它們
  的完整遞移相依鏈,每一個都釘選精確版本**並附雜湊**(例如
  `pip-compile --generate-hashes`/`uv pip compile --generate-hashes`/
  `poetry export --with-hashes` 其中一種工具的輸出格式——**這份文件不
  代為決定用哪個工具**,工具選擇是實作細節,但「產出的鎖定檔內容本身
  被提交、其 SHA-256 進 `dependency_lock_identity`、Phase B 建置前比對
  執行環境實際版本」這三件事是強制的,不是工具怎麼選的問題)。
- **現況**:**MISSING**。`requirements-v2-data-build.lock` 目前不存在
  (`git ls-files | grep -i lock` 唯讀查詢無結果——`requirements.txt` 本身
  不含 "lock" 字樣所以不會被這個查詢誤判成同一份東西),是 §F
  MISSING_BEFORE_BUILD 的新增項目;`runtime_environment_identity_v1` 的
  canonical 序列化/雜湊函式、以及第 20 輪新增的完整 lock-selected/
  installed inventory 比對邏輯(marker 解析 + PEP 503 正規化 + bootstrap
  例外清單)同樣**完全不存在**,都是各自獨立的 MISSING_BEFORE_BUILD 項目
  (見 §F)。

**PASS 證據**:寫進未來的 aggregate build receipt (§C.5) 頂層欄位
`snapshot_id_v1`,同時逐一記錄上面列出的每一個輸入雜湊、三層中間值
(`source_data_identity`/`build_implementation_identity`/以及
`runtime_environment_identity_v1` 本身跟它的 canonical 序列化來源物件
`runtime_environment_source`——後者必須逐欄位原樣記錄,不能只寫雜湊值,
否則獨立驗證器沒有東西可以重新算),以及第 20 輪新增的
`lock_selected_inventory`/`lock_selected_inventory_sha256`/
`installed_inventory`/`installed_inventory_sha256`/
`bootstrap_tool_inventory`/`environment_creation_identity`(§C.5 有完整
欄位定義)。

**Fail-closed 條件(第 20 輪擴充,Checkpoint 23 修正 `preregistration_
commit` 的取得方式跟 fail-closed 判定)**:任一個輸入檔案不存在、
`preregistration_commit` 依上方「取得方式」查不到唯一的 path-scoped
commit/blob、上方「額外的證據完整性檢查」三項有任一項不成立、上方
「Phase B 前置的 scoped 乾淨度檢查」清單裡任一項不符、或建置當下**完整**的
`installed_inventory`(不只四個具名套件)跟 `requirements-v2-data-build.
lock` 解析出的 `lock_selected_inventory` 不完全相符(缺席/版本不符/多出
未宣告套件,三種情況都算不符,bootstrap 例外清單以外的任何差異都不能
放行),直接 raise,不生成部分或暫時的 `snapshot_id_v1`。

**現況**:**MISSING**。`tej_importer.py`、`scripts/extract_legacy_supplement.py`
現在都沒有 `snapshot_id_v1` 這個概念,也沒有任何函式做這個組合雜湊、也沒有
manifest.csv vs .sha256 的交叉驗證、也沒有依賴鎖定檔。需要新增(§F
MISSING_BEFORE_BUILD)。

**顯式型別凍結(第 17 輪新增,取代第 16 輪「dtype 契約」段落裡不準確的
描述)**:

- 原本文件說「`pd.to_numeric(errors="coerce")` 的結果一律是 `float64`」
  是不準確的——如果一批值全部能成功解析成整數、且這次讀到的原始檔剛好
  沒有任何一格觸發 `coerce`(沒有 NaN),pandas 會把結果留在 `int64`,不是
  `float64`。這代表輸出 dtype 目前**是不確定的、依賴這次讀到的資料內容**,
  不是程式碼保證的契約。
- **修正**:所有數值目標欄位(含 `financial_statements` 的 `quarter`,
  394 行放在 `numeric_cols` 裡)在 `pd.to_numeric(...)` 之後,**必須再顯式
  `.astype("float64")` 一次**——不管這次資料剛好有沒有觸發 NaN,輸出型別
  永遠固定,不受資料內容影響。除非未來有文件明確記錄的下游消費者需要別的
  型別(目前沒有),否則一律 `float64`。這是對 `_load_one`(511-561 行)
  數值轉換路徑的具體修改需求,列進 §F MISSING_BEFORE_BUILD。
- `stock_id`/`stock_name`/`date`/`release_date`/`industry_map` 的六個
  代碼/名稱欄位/`director_pledge` 的 `group_name`:**顯式轉字串**(pandas
  nullable `"string"` dtype 或等價的一致字串型別),永遠不進
  `pd.to_numeric` 或任何數值轉換路徑。**industry code 尤其不能被誤轉成
  數字**——前導零(例如某些 TEJ 產業代碼)在數字型別下會被吃掉,語意上
  跟字串是不同的值。這解除第 16 輪標記的 7 個
  `DESIGN_BLOCKED_SCHEMA_CONTRACT` 欄位。
- `date`/`release_date` 維持 §B 已經凍結的 `YYYY-MM-DD` 字串格式,除非
  未來另外凍結別的邏輯型別。
- **receipt 必須同時記錄「邏輯契約型別」跟「實際寫入 Parquet/Arrow 的物理
  型別」兩個欄位**(例如 `{"target_column": "eps", "logical_type":
  "float64_nullable", "written_arrow_type": "double"}`),獨立驗證器讀出
  候選 parquet 的實際 schema 後,兩者不符就是 `BUILD_VERIFICATION_FAILED`
  ——不能只信 receipt 自己宣稱的型別,要跟磁碟上真正寫出來的型別交叉核對。
- **現況**:**MISSING**——`_load_one`(511-561 行)目前對 `thousand_cols`
  (542-548 行)/`numeric_cols`(554-556 行)都只呼叫 `pd.to_numeric`,沒有
  後續顯式 `.astype`;對字串欄位也沒有顯式轉型,型別完全依賴
  `pd.read_excel` 推斷。

### C.2 精確的來源 manifest preflight

*(第 17 輪未修改;內容跟第 16 輪相同。)*

- **11 個主 dataset**:**IMPLEMENTED**。`tej_importer._manifest_preflight`
  (173-202 行)在讀檔前核對「這個 dataset 實際會讀的檔案集合」跟 manifest
  記錄的子集合是否完全一致 (無缺、無多),每個檔案的 SHA-256 是否吻合,任一項
  不符直接 raise、不解析。從 `load_source`(932 行)呼叫,11 個 dataset 都
  經過這一關。有測試 (`tests/test_tej_data_migration.py` 第 4 節)。**目前
  只讀 `manifest.csv`,完全不讀 `manifest.sha256`**——見 §C.1 的
  `manifest.csv` vs `.sha256` 逐 relpath 交叉驗證,現況同樣是 **MISSING**
  (§F MISSING_BEFORE_BUILD 的一部分,不是獨立項目)。
- **`LEGACY_DERIVED_SUPPLEMENT` 的四個舊來源檔**:**PARTIAL**——見 §C.8。

### C.3 Schema、null-key、重複鍵、衝突重複鍵的 fail-closed 規則

*(第 17 輪未修改。)*

**IMPLEMENTED**,11 個 dataset 共用:

- `_check_required_cols`(499-508 行):必要欄位缺席直接 raise。
- `_check_valid_keys`(205-220 行):stock_id 空白/NaN/`"nan"` 字串、date
  解析失敗,在 `dropna` 之前就先擋下來。
- `_check_duplicate_key_conflicts`(564-597 行):完全重複安全去重並記錄次數;
  衝突重複 (同 key 不同值) 不設容忍門檻,一個都不行。
- `_check_sanity_floor`(901-924 行):列數/股票數/最早日期低於已知規模的
  次要防線 (不是完整性證明)。

全部有對應測試 (`tests/test_tej_data_migration.py`)。

### C.4 隔離輸出根目錄 + path-identity 檢查(第 17 輪:給出具體建議路徑;第 19 輪:改用完整 64 碼識別碼;Checkpoint 22:使用者已核准)

**FROZEN / AUTHORIZED_PATH(使用者已於 2026-08-08 明確核准——第 17 輪
要求「narrow 到只剩這一項真正的使用者決定」給出的具體建議,Checkpoint 22
記錄使用者核准的決定,下方路徑本身的拼寫/64 碼要求/子目錄佈局/path 守衛/
保護路徑排除清單,自第 17-21 輪凍結後**一個字元都沒有再改過**,這次
只是把狀態標記從「待核准」改成「已核准」)**:

**建議的具體布局(第 19 輪修正:目錄名稱用完整 64 碼小寫 `snapshot_id_v1`,
不是任何長度的截斷前綴)**——完整絕對路徑:

```
C:\dev\Project 1\tej_exports\v2_candidate\<snapshot_id_v1 完整 64 碼小寫十六進位>\<run_id>\
  ├── cache/                          # 候選 parquet 本體
  │     ├── price_valuation/<stock_id>.parquet
  │     ├── ... (其餘 9 個逐股目錄 dataset)
  │     └── industry_map.parquet
  ├── build_receipts/                 # builder 寫的逐 dataset + 彙總 receipt(不可覆寫)
  ├── quality_sidecars/                # §C.9 的 sidecar(不可覆寫)
  └── verification_receipts/          # verifier 寫的驗證 receipt(不可覆寫,§D 單發規則)
```

- 放在 `tej_exports/` 底下而不是專案根目錄散落,是為了跟現有
  `tej_exports/legacy_supplement/`、`tej_exports/diff_receipts/` 的既有
  慣例一致(同一個父目錄底下,職責用子目錄名稱區分)。
- **第 19 輪修正:目錄名稱改用完整 `snapshot_id_v1`(64 碼小寫十六進位),
  不再用任何長度的截斷前綴**。第 17/18 輪版本用「前 12 碼」當子目錄名稱,
  Codex 指出這是錯的:12 碼十六進位只有 2^48 種可能,不能宣稱「不會撞」,
  更不是完整的內容位址(content address)——內容定址的精神是「位址本身
  完整表示內容身分」,截斷之後位址跟身分不再是一對一,理論上存在(即使
  機率極低)兩個不同 `snapshot_id_v1` 截斷後撞在同一個目錄名稱的可能性,
  而且從目錄名稱**反推不出**完整身分,任何要核對「這個目錄底下的內容
  是不是真的對應到聲稱的那個 snapshot_id_v1」的人,還要另外去 receipt
  裡找完整值才能確認——直接用完整 64 碼當目錄名稱,目錄名稱本身就是
  可驗證的完整身分,不需要間接查證。
- **path 守衛必須核對目錄名稱這個字串,逐字元等於每一份 receipt 記錄的
  完整 `snapshot_id_v1` 值**(不是核對前綴、不是核對長度、不是核對雜湊
  的雜湊)——這個檢查列進 §F MISSING_BEFORE_BUILD 的隔離根目錄驗證器
  範圍。
- **第 18 輪加入、第 19 輪保留的 `<run_id>/` 這一層**——同一個
  `snapshot_id_v1`(來源資料跟建置實作都沒變)底下可以有多次 Phase B
  執行嘗試(例如上一次 `BUILD_FAILED_PARTIAL` 之後,另外被授權重跑),
  §D「不可覆寫命名 + 重跑的 run_id」規定每次執行都是新的 `run_id`、不
  覆寫前一次的證據——如果 `cache/`/`build_receipts/` 等子目錄直接掛在
  `<snapshot_id_v1>/` 底下而不分 `run_id`,兩次執行會寫進同一個目錄,
  產生實際的檔案覆寫/衝突風險(`cache/` 底下的逐股 parquet 檔名是
  `<stock_id>.parquet`,不含 `run_id`,兩次執行會直接覆寫彼此的候選
  資料)。加上 `<run_id>/` 這一層之後,每次 Phase B 執行天然對應一個
  獨立的完整子目錄,不需要再另外設計檔案層級的跨 run 衝突偵測。
- **Checkpoint 22(2026-08-08):使用者已明確核准這個布局**,§F 把這一項
  從 `PROPOSED_NOT_AUTHORIZED` 移到 `FROZEN`(標記
  `AUTHORIZED_PATH`)——路徑本身的內容(拼寫/64 碼要求/子目錄佈局/上面
  的 path 守衛規則/下面的保護路徑排除清單)完全沒有變動,只有授權狀態
  改變。**核准路徑本身不構成 Phase A 實作或 Phase B 執行的授權**——
  §F `MISSING_BEFORE_BUILD` 底下的每一項(含這裡的隔離根目錄 path-
  identity 驗證器)依然是 `MISSING`,一個都還沒有被實作,下方的
  「現況:MISSING」照舊維持不變。

**必須在寫入前**,對解析過的絕對路徑 (`Path.resolve()`,處理符號連結/
junction 之後的真實路徑) 逐一核對,確認**不等於、不是子路徑、也不解析到**
以下任何一個:

- 生產環境 `TEJ_CACHE_DIR`(預設 `~/tej_cache`,`tej_importer.py` 121 行)
- 舊 `tej_exports/inbox*`(9 個資料夾)
- 第三輪 scratchpad (`DIAGNOSTIC_OUT_OF_SCOPE_BUILD`,政策文件 §11.7)
- 原始 `tej_exports/DataExport0806/`
- supplement 輸入 (`tej_exports/inbox_fundamentals`/`inbox_revenue`/`inbox`,
  `scripts/extract_legacy_supplement.py::SOURCES` 用到的三個資料夾)
- `tej_exports/legacy_supplement/`(現有 supplement 輸出,不能被候選建置
  覆寫)
- `tej_exports/diff_receipts/`(既有的、跟這次隔離建置無關的 receipt 目錄)
- 任何已凍結的研究輸出目錄 (V0/Gate 產物)

**現況**:**MISSING**。`tej_importer.main()`(1104-1123 行)的
`--cache-dir` 參數**沒有任何驗證**,直接把使用者傳入的字串當輸出目的地;
`save_by_stock`(999-1101 行)、`main()` 的靜態分支 (1111-1118 行) 也都沒有
再檢查一次。**更嚴重的是:`--cache-dir` 不給的話,`TEJ_CACHE_DIR` 預設就是
生產環境 `~/tej_cache`(121 行)**——這件事本身就是 §C.7 (刪除/推生產需
另一輪審查) 的一個具體風險來源。**根據第 17 輪的架構決定(§D),這個路徑
守衛屬於新 builder 腳本的職責,不是 `tej_importer.py` 本體要改的地方
(`tej_importer.main()`/`--cache-dir` 這條 CLI 路徑本身在混合架構下會變成
`tej_importer.py` 僅供人工單一 dataset 診斷用的次要入口,不是 Phase B 正式
建置流程會呼叫的路徑——正式流程走新 builder,只呼叫 `tej_importer.
load_source()` 這個函式,不透過 CLI/`main()`)。**

### C.5 逐 dataset 不可覆寫 receipt + 彙總 build receipt + 驗證 receipt(第 17 輪:加入單發約束跟依賴身分欄位)

**現況**:**MISSING**,`tej_importer.py` 完全沒有 receipt 機制——`main()`
只寫 parquet,不寫任何 JSON 紀錄。跟本專案其他腳本比較:

- `scripts/extract_legacy_supplement.py`(452-500 行)**有** receipt,但是
  `open(..., "w")` 覆寫模式寫進固定檔名 `receipt.json`(490/496 行),每次
  重跑整份取代——是「目前狀態」語意,不是「不可覆寫的歷史紀錄」語意。
- `scripts/_full_population_diff.py`、
  `scripts/institutional_gross_trust_holding_pct_adjudication.py` **才是**
  正確的先例:`_write_receipt()` 用微秒時間戳 + uuid 後綴組檔名、
  `open(..., "x")` 排他建立(撞名直接炸掉,不會靜默覆寫)。

**需要的規格(沿用後者的模式,不是前者)——三份 receipt,職責跟 §D 的
架構角色一一對應**:

1. **逐 dataset build receipt**(**由新 builder 腳本寫,不是
   `tej_importer.py`**):每個 dataset 一份,排他建立,檔名含
   `snapshot_id_v1`(前綴)+ dataset 名稱 + 時間戳 + uuid 後綴。內容至少含:
   輸入檔案清單+SHA-256、`_load_one`/`_check_*` 的逐項結果、
   row/stock/date/schema/dtype(邏輯+實際物理型別,§C.1)/null/重複鍵
   accounting、§B 的逐檔覆蓋矩陣、(若有 supplement)`supplement_
   provenance` 結構(§C.10)、開始/結束時間戳、exit code、狀態、若失敗則
   附錯誤證據。
2. **彙總 build receipt**(builder 寫):一份跨 11 個 dataset 的頂層
   receipt,排他建立,含 `snapshot_id_v1`(連同 §C.1 三層中間值 + 執行環境
   版本一起記錄)、11 份逐 dataset receipt 的路徑+雜湊、`run_id`、**
   `authorized_verifier_identity`(第 18 輪新增——Phase A 凍結的唯一合法
   驗證器雜湊,建置器只是照抄這個凍結值寫進 receipt,不是自己決定)**、
   **第 20 輪新增的完整鎖定/安裝相符性欄位**:`lock_selected_inventory`
   (canonical 排序後的 `[正規化套件名, 版本]` 陣列,§C.1 的 marker 解析
   + PEP 503 正規化規則算出來的)、`lock_selected_inventory_sha256`
   (前者 canonical 序列化後的小寫 SHA-256)、`installed_inventory`(隔離
   環境裡實際安裝的第三方套件完整清單,同樣格式)、`installed_inventory_
   sha256`、`bootstrap_tool_inventory`(`pip`/`setuptools`/`wheel` 三個
   的實際版本,不參與相符判定但仍要記錄)、**`environment_creation_
   receipt_path`/`environment_creation_receipt_sha256`/
   `environment_creation_identity`**(指向下方精確定義的
   `environment_creation_receipt_v1`——第 20 輪只寫「隔離環境建立+安裝
   過程本身的 receipt/雜湊」這句話,第 21 輪把它變成精確 schema)、整體
   `overall_status`。**`overall_status` 只能是
   `BUILD_COMPLETE_AWAITING_VERIFICATION` 或 `BUILD_FAILED_PARTIAL` 這兩個
   值之一——建置器絕對不能把 `BUILD_VALIDATED`/`BUILD_VERIFICATION_FAILED`
   寫進這份 receipt,即使 11 個 dataset 全部成功。**(§D 有完整狀態機定義)

   **`environment_creation_receipt_v1` 精確 schema(第 21 輪新增)**:
   獨立、不可覆寫的一份 receipt,**必須在候選資料解析(呼叫
   `tej_importer.load_source()`)開始之前**排他建立完成——順序上是
   Phase B 的第一步,不是事後補記。內容(單一物件,鍵集合固定):

   ```
   environment_creation_receipt_v1 = {
       "schema": "environment_creation_receipt_v1",
       "run_id": ...,
       "preregistration_commit": ...,        # 「run authorization」——這個 run 是在哪一次
                                              # 已審查、已凍結的 Phase A commit 之下被授權執行的
       "lock_path": "requirements-v2-data-build.lock",
       "lock_sha256": ...,                   # 等於 §C.1 的 dependency_lock_identity
       "marker_environment_v1": {...},       # 上方 §C.1 定義的完整 11 鍵物件
       "marker_environment_identity_v1": ...,
       "installer_identity": ...,            # 例如正規化字串 "pip==24.0",識別實際執行安裝的工具本身
       "bootstrap_tool_inventory": [...],    # [[正規化名稱, 版本], ...],canonical 排序
       "install_command": [...],             # 實際執行的安裝指令,依參數順序原樣記錄的字串陣列,
                                              # 例如 ["pip","install","--require-hashes","-r",
                                              # "requirements-v2-data-build.lock"],用來佐證
                                              # hash 校驗真的被開啟,不是事後宣稱
       "start_timestamp_utc": ...,
       "end_timestamp_utc": ...,
       "exit_code": ...,
       "installer_report_artifact_hashes": [...],   # 若安裝工具的報告機制(例如 pip 的
                                                      # --report JSON)有提供逐套件安裝檔案雜湊,
                                                      # 原樣記錄;沒有這個機制就明確填 JSON null,
                                                      # 不是省略欄位
       "stdout_log_sha256": ...,             # 安裝過程 stdout 完整輸出另存成檔案後的雜湊
       "stderr_log_sha256": ...,             # 同上,stderr
       "lock_selected_inventory": [...],
       "lock_selected_inventory_sha256": ...,
       "installed_inventory": [...],
       "installed_inventory_sha256": ...,
       "equality_result": {"equal": true_or_false, "discrepancies": [...]},
   }
   ```

   **canonical 序列化跟自身身分計算**:`environment_creation_identity =
   SHA256(json.dumps({k: v for k, v in environment_creation_receipt_v1.items() if k != "environment_creation_identity"}, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()`
   ——**排除的只有 `environment_creation_identity` 這個欄位本身**(這個
   欄位在雜湊計算當下根本還不存在,雜湊算完才附加寫進最終落地的 JSON 檔
   裡),其餘所有欄位(含 `schema`/`run_id`/所有 inventory/所有雜湊)都要
   參與序列化;鍵順序用 `sort_keys=True`(跟 `marker_environment_v1` 同一
   套紀律,不手動維護插入順序)。

   **Fail-closed 條件**:這份 receipt 缺席、格式不合法讀不出來、
   `exit_code != 0`、`install_command` 裡沒有出現 hash 校驗證據(例如
   `--require-hashes` 或等價旗標)、或 `equality_result.equal != true`,
   任一項都必須在**繼續往下解析候選資料之前**直接 raise——不能先跳過
   環境檢查、之後再回頭補寫這份 receipt。

   **彙總 build receipt 記錄**:這份 receipt 的檔案路徑
   (`environment_creation_receipt_path`)、其**檔案位元組本身**的
   SHA-256(`environment_creation_receipt_sha256`,偵測檔案有沒有被
   事後竄改)、以及檔案內部欄位 `environment_creation_identity` 的值
   (前者是「檔案完整性」,後者是「內容可被獨立重算驗證」,兩者語意不同,
   都要記,不能只留一個)。

   **獨立驗證器**:核對 `environment_creation_receipt_v1` 檔案本身雜湊
   等於彙總 build receipt 記錄的 `environment_creation_receipt_sha256`;
   從檔案內容(排除 `environment_creation_identity` 欄位)重新算一次
   canonical 雜湊,核對等於檔案裡記錄的 `environment_creation_identity`
   值,也等於彙總 build receipt 引用的那個值;核對 `stdout_log_sha256`/
   `stderr_log_sha256` 等被引用的證據檔案(若隨附保留)雜湊相符。**這是
   核對 receipt 記錄本身有沒有被竄改、算式對不對,不是宣稱能重建/重跑
   出那個當時已經可能被銷毀的隔離環境**——跟 §D 對
   `runtime_environment_identity_v1`/`lock_selected_inventory` 的驗證
   立場完全一致。
3. **驗證 receipt**(獨立於上面兩份,由獨立 verifier 腳本寫;**受 §D 的
   單發驗證規則約束**):排他建立,**絕不覆寫或修改**彙總 build receipt 或
   任何逐 dataset receipt。內容至少含:被驗證的彙總 build receipt 的檔案
   路徑 + 其**當下位元組 SHA-256**(`build_receipt_sha256`)、對應的
   `run_id`、`verifier_identity`(§C.1,必須等於彙總 build receipt 記錄的
   `authorized_verifier_identity`,否則這份 receipt 本身就不合法)、驗證器
   自己觀測到的執行環境版本、§D 第 18 輪新增的獨立原始 cell 重建結果
   (逐 dataset 的 raw locator/token/分類重建、去重映射、post-dedup null
   原因 accounting、supplement provenance 獨立核對)、第 20 輪新增的
   `lock_selected_inventory` 獨立重建結果 + receipt 記錄的 `installed_
   inventory`/相符判定內部一致性核對結果、`overall_status`
   (只能是 `BUILD_VALIDATED` 或 `BUILD_VERIFICATION_FAILED` 這兩個值之
   一)、驗證時間戳、`binding: true` 欄位(區分正式驗證跟 §D 允許的非約束
   力診斷重跑)。

### C.6 建置過程中不做績效/OOS/Gate 讀寫

*(第 17 輪未修改。)*

**現況**:目前 `tej_importer.py` 的 import 清單 (98-112 行) 只有
`csv/fnmatch/hashlib/io/json/os/re/shutil/sys/logging/argparse/zipfile/
pathlib/pandas`,**沒有**匯入任何 `core.*`/`beat_0050.*`/backtest/scoring
模組——目前的程式碼**沒有能力**讀寫績效/OOS/Gate 相關資料,這條規則目前是
「因為沒有這個功能所以無法違反」,不是「有主動擋下來的機制」。

**這算 PARTIAL,不是 IMPLEMENTED**:沒有主動的 import 白名單/lint 檢查去
**防止未來的修改**意外加入這類 import。§F 的 MISSING_BEFORE_BUILD 清單建議
補一個簡單的靜態檢查 (例如測試裡 grep import 清單,出現不在白名單裡的模組
就 fail)——這條檢查應該同時涵蓋 `tej_importer.py` 跟新 builder 腳本兩份
檔案。

### C.7 刪除/推生產需另一輪獨立審查跟使用者的明確授權

*(第 17 輪未修改。)*

**現況**:**MISSING (程式面)**。這條規則目前完全是流程/政策約束
(政策文件 §11.5/§11.6),沒有任何程式碼機制去攔截「不小心對生產路徑執行了
刪除或寫入」。跟 §C.4 直接相關:`TEJ_CACHE_DIR` 預設指向生產環境,沒有任何
`--i-understand-this-writes-production` 之類的明確旗標門檻 (對照
`scripts/portfolio_v2_phase1_audit.py` 等其他腳本已經採用的「雙旗標」模式,
見政策文件與更早的 audit 執行紀錄)。

### C.8 完整的 `LEGACY_DERIVED_SUPPLEMENT` 前置檢查

*(第 17 輪未修改;內容跟第 16 輪相同。)*

對應政策文件 §11.4a 凍結的條件,逐項核對現況:

| §11.4a 條件 | 現況 |
|---|---|
| supplement **輸出/腳本/schema/profile/dedup** 驗證(消費端) | **IMPLEMENTED**(僅限這幾項子檢查)—— `tej_importer._verify_supplement`(781-898 行)驗證 `overall_status=PASS`、supplement parquet SHA-256、抽取腳本 SHA-256(腳本不存在也 raise)、`SUPPLEMENT_SCHEMAS`(604-608 行,程式碼凍結,不只信 receipt)、重算 profile 統計比對、`dedup` 巢狀結構驗證。 |
| 四個**舊原始檔**雜湊回溯比對 | **MISSING/PARTIAL**——雜湊有被記錄進 receipt 的 `sources` 欄位,但候選建置前沒有任何程式碼重新計算這四個檔案「現在」的雜湊去比對「當時」的雜湊。 |
| 整體 `LEGACY_DERIVED_SUPPLEMENT` 內容身分前置檢查 | **PARTIAL**——直到上一項也實作完成才算完整。 |
| 只能新增原生欄位、不能覆寫 | **PARTIAL**——結構上不重疊,但沒有明確執行期斷言(見 §C.10)。 |
| 合併鍵唯一/非 null,合併後列數不能增加 | **IMPLEMENTED**——`_verify_supplement`(890-897 行)+ `load_source`(961-967 行)兩層防線。 |
| `source_class=LEGACY_DERIVED_SUPPLEMENT` + receipt 雜湊標記 | **MISSING**——卡在 §C.5 receipt 機制;精確 schema 見 §C.10。 |
| 非 PIT 標籤 | **文件層級 IMPLEMENTED,機器可讀層級 MISSING**——精確 schema 見 §C.10。 |
| 條件不符 fail-closed | **IMPLEMENTED**——`_verify_supplement` 任一項不符直接 raise。 |

### C.9 品質證據 sidecar 精確 schema(第 17 輪重寫:分階段 accounting + 強化 locator)

回應「文字 `.` 被靜默吃掉」跟「sidecar 列數直接等於最終 NaN 數」這個第 16
輪版本裡的錯誤等式(在完全重複去重、欄位整檔缺席、supplement 未覆蓋三種
情況下都不成立)。

**分階段 accounting(第 17 輪核心修正,取代第 16 輪的單一等式)**:

**階段一:去重前的來源 cell 分類(每個原始檔 × 每個目標欄位一組)**

| 分類 | 定義 |
|---|---|
| `source_row_count` | 這個原始檔對應到這個目標欄位的**來源列總數**(即這個檔案的總列數,分母) |
| `column_present_row_count` | 來源欄位存在、且這一列有這個來源欄位的原始儲存格 |
| `column_absent_row_count` | 來源欄位在這個檔案裡整欄不存在(`SOURCE_COLUMN_ABSENT`) |
| `parsed_numeric_cell_count` | 來源欄位存在、儲存格成功解析成合法數字 |
| `blank_cell_count` | 來源欄位存在、儲存格是空白(原生 NaN 或純空白字串) |
| `unparseable_cell_count` | 來源欄位存在、儲存格非空白但無法解析成數字(例如文字 `"."`) |

上表除 `source_row_count`(分母,不是分類本身)外,其餘分類必須**互斥**,且
`column_present_row_count = parsed_numeric_cell_count + blank_cell_count
+ unparseable_cell_count`,
`source_row_count = column_present_row_count + column_absent_row_count`
——兩個等式都必須在逐 dataset build receipt 裡可核對,不成立就是建置本身
的 bug,fail-closed。

**sidecar 本身只收 `blank_cell_count`/`unparseable_cell_count` 這兩類的
明細**(不是全部列都進 sidecar,避免膨脹),而且是**去重前**的來源 cell
——即使兩個原始檔剛好有完全重複的 (stock_id, date, 目標欄位) 都是文字
`.`,去重前的兩筆證據都要各自留一列在 sidecar 裡,`sidecar 列數` 因此
**只跟階段一的 `blank_cell_count + unparseable_cell_count` 加總對帳**,
不直接跟任何「最終」數字比對。

**階段二:去重/合併後的最終 null 原因分類(每個目標欄位一組,對帳到
merge 完成後、寫入 parquet 前的 combined DataFrame)**

| 最終 null 原因 | 對應的來源 |
|---|---|
| `RETAINED_BLANK` | 去重後保留下來的那一列,原始是空白儲存格 |
| `RETAINED_UNPARSEABLE` | 去重後保留下來的那一列,原始是無法解析的文字 |
| `SOURCE_COLUMN_ABSENT` | 這個 (stock_id, date) 落在一個整欄缺席的原始檔裡(§B 新規則) |
| `SUPPLEMENT_KEY_NOT_COVERED` | 這欄是 supplement 欄位,這個 (stock_id, date) 不在 supplement 覆蓋範圍(left join 沒配對到) |
| `OTHER_UNEXPLAINED` | 以上都不適用——**這個分類正常情況下必須是 0**,非零代表 accounting 本身有漏洞,verifier 必須在這裡直接判定 `BUILD_VERIFICATION_FAILED`,不能放行 |

`RETAINED_BLANK + RETAINED_UNPARSEABLE + SOURCE_COLUMN_ABSENT +
SUPPLEMENT_KEY_NOT_COVERED + OTHER_UNEXPLAINED = 該目標欄位在最終輸出
parquet 裡的 null 總數`——這個等式取代第 16 輪版本裡「sidecar 列數 = 最終
NaN 數」的錯誤等式,是彙總 build receipt 必須記錄、獨立驗證器必須重建的
對帳項目。

**去重映射(第三個必須記錄的 accounting)**:`_check_duplicate_key_
conflicts`(564-597 行)目前只記錄「完全重複去重掉幾列」的**總數**
(587-589 行 log),第 17 輪要求進一步記錄**每一個被保留下來的候選 key,
對應了幾筆來源 cell 證據**(例如同一個 (stock_id, date) 因為出現在兩個
重疊年份的原始檔裡,兩筆數值完全相同,去重後只留一列,但 sidecar 如果
這個值剛好是 unparseable,兩筆證據都要留著、且都要能追溯到同一個最終保留
下來的 key)。衝突重複(同 key 不同值)維持現有行為,不設容忍門檻,直接
raise。

**強化後的 locator 契約(第 17 輪:RangeIndex 不夠,補三個欄位)**:

| 欄位 | 型別 | 說明 |
|---|---|---|
| `dataset` | string | 11 個 dataset 名稱之一 |
| `source_relpath` | string | 相對 `DATA_ROOT` 的來源檔案路徑 |
| `source_file_sha256` | string | 來源檔案的 `_sha256_of` 結果(第 17 輪新增到 locator 本身,不只在檔案層級記一次——每一列都自帶,方便單列稽核不用回頭查外部索引) |
| `source_container_member` | string \| null | **第 17 輪新增**——Excel 檔案的工作表名稱,或 `.zip` 內實際被讀取的成員檔名(對照 `_read_raw_table`,220-234 行,`.zip` 分支解出的是壓縮包內的 csv 成員);單一 sheet 的 `.xlsx` 可以是固定值,但欄位本身不能省略,不然跨格式(zip vs xlsx)的 locator 語意不一致 |
| `source_row_number` | int | **第 17 輪修正**——「實體、已對齊表頭」的來源列號(即這一列在原始檔案裡,人工用 Excel/文字編輯器打開後數到的實際行號,不是 pandas 內部的 0-based `RangeIndex`;`RangeIndex` 在跳過表頭列、多工作表拼接後會失真,不是足夠的跨格式定位子) |
| `stock_id` | string | 該列解析後的 stock_id |
| `date` | string | 該列解析後的 `date`(`YYYY-MM-DD`) |
| `source_column` | string | 原始中文欄名 |
| `target_column` | string | 轉換後的目標欄名 |
| `raw_token` | string | **第 17 輪澄清**:對**任何非空白儲存格**(不論最後能不能解析成數字),都保留該儲存格值 `str().strip()` 後的字面 token——`"."` 這種 unparseable 文字一定有 `raw_token`;`raw_token` 是 `null` **只保留給**真正空白的儲存格(原生 `NaN` 或純空白字串,即 `is_blank=true` 的情況)。不使用「先轉字串再怎樣」這種暗示順序的說法——`raw_token` 就是「這格內容的字串表示」,跟解不解析得出數字是兩件事。 |
| `is_blank` | bool | 原始儲存格是空白/`NaN`/純空白字串 |
| `is_unparseable` | bool | 原始儲存格有內容,但不是空白也不是合法數字——跟 `is_blank` 互斥,不能同時 `true` |
| `parser` | string | 固定值 `"pd.to_numeric"` |
| `unit_scale_applied` | float | `thousand_cols` 欄位填 `1000.0`,否則 `1.0` |
| `resulting_value` | float \| null | 最終寫進候選 parquet 的值(`is_blank`/`is_unparseable` 為 `true` 時必為 `null`) |
| `dedup_key` | string | 見下方「canonical 序列化」專節(第 18 輪重寫) |

**`dedup_key` 的 canonical 序列化(第 18 輪重寫,取代第 17 輪的
`SHA-256(f"a|b|c")` 寫法)**:第 17 輪版本雖然把拼接字串拿去雜湊,但拼接
本身還是用 `|` 當分隔符號——如果某個欄位值(例如未來允許的 `source_
container_member`)剛好含有字面 `|` 字元,兩組不同的欄位值可能拼出同一個
字串、雜湊出同一個 `dedup_key`,「先雜湊過」不會讓分隔符號歧義消失,只是
把歧義藏起來。改成凍結版本的 canonical JSON 陣列序列化:

```
canonical_array = [
    "dedup_key_v1",             # schema/version tag,固定字面值,未來序列化規則變動就換版本號,
                                 # 保證新舊 dedup_key 不會意外撞在一起
    dataset,
    source_relpath,
    source_container_member,    # 沒有的話用 JSON null(不是字串 "null"),見下
    source_row_number,          # JSON number,不是字串
    target_column,
]
payload = json.dumps(
    canonical_array,
    ensure_ascii=True,          # 非 ASCII 字元 (中文路徑) 一律轉義成 \uXXXX,
                                 # 避免不同系統/編碼設定下的位元組序不一致
    separators=(",", ":"),      # 緊湊分隔,不允許任何可選空白
    sort_keys=False,            # 陣列本身順序已經固定,不適用/不需要排序
).encode("utf-8")
dedup_key = hashlib.sha256(payload).hexdigest()   # 小寫十六進位
```

凍結項目(逐一對應 Codex 第 18 輪要求的五點):**schema/version tag** =
字面值 `"dedup_key_v1"`,固定放在陣列第一個元素;**欄位順序** = 上面
`canonical_array` 列出的六個元素,固定不變;**null 表示法** =
`source_container_member` 缺席時用 JSON 原生 `null`,不是字串 `"null"`
或空字串;**UTF-8 編碼** = `payload` 一律先編碼成 UTF-8 位元組再雜湊;
**JSON escaping/分隔符號** = Python `json.dumps` 預設跳脫規則、
`separators=(",", ":")` 緊湊格式(逗號/冒號後不留空白,序列化結果因此
是位元組級決定性的,不會因為換一個 JSON library 的預設縮排設定就得到
不同雜湊);**輸出** = `hashlib.sha256(...).hexdigest()` 小寫十六進位,
跟本文件其他雜湊值的慣例一致。**獨立驗證器必須用同一套規則,從自己
獨立重建的 locator 欄位(§D 第 18 輪新增的獨立原始 cell 重建要求)重新
算出每一個 `dedup_key`,逐一比對 sidecar 裡的值**——這是「驗證 sidecar
記錄本身有沒有造假/算錯」的其中一項具體檢查,不是只信 sidecar 檔案裡
已經寫好的值。

**現況**:**MISSING**——`_load_one`(511-561 行)完全沒有這個機制,是
§F MISSING_BEFORE_BUILD 的實作範圍。**在這個 schema 被實作跟測試覆蓋
之前,`_load_one` 目前的 `pd.to_numeric(errors="coerce")` 呼叫繼續違反
政策文件 §11.3。**

### C.10 supplement provenance receipt 精確 schema

*(第 17 輪未修改 schema 本身;只更新「誰來寫」以符合 §D 的架構決定。)*

三個受影響 dataset(#3/#5/#6)各自的逐 dataset build receipt(§C.5,**由
builder 寫,不是 `tej_importer.py` 寫**——`tej_importer.load_source()` 只
負責在記憶體裡產生合併後的 DataFrame + 這個結構需要的原始素材,實際寫入
receipt 檔案是 builder 的職責)裡,必須包含的巢狀物件 `supplement_
provenance`:

```json
{
  "supplement_provenance": {
    "source_class": "LEGACY_DERIVED_SUPPLEMENT",
    "supplement_receipt_path": "tej_exports/legacy_supplement/receipt.json",
    "supplement_receipt_sha256": "<建置當下重算的 SHA-256,必須等於 §C.1 的 supplement_identity>",
    "is_pit": false,
    "affected_columns": ["<例如 fundamentals_quarterly 的 [\"roe_after_tax\"]>"],
    "non_overlap_assertion": {
      "checked": true,
      "native_columns": ["<merge 前 combined 的非鍵欄位清單>"],
      "supplement_columns": ["<merge 前 supp 的非鍵欄位清單>"],
      "overlap": []
    },
    "row_counts": {
      "pre_merge_rows": "<combined merge 前列數>",
      "post_merge_rows": "<combined merge 後列數,必須等於 pre_merge_rows>",
      "rows_with_supplement_value": "<merge 後,supplement 欄位至少一個非 null 的列數>",
      "rows_supplement_key_not_covered": "<merge 後,supplement 欄位全為 null 且原因是 SUPPLEMENT_KEY_NOT_COVERED 的列數,對應 §C.9 階段二分類>"
    }
  }
}
```

`non_overlap_assertion.overlap` 若非空陣列,建置必須在合併當下直接 raise;
`row_counts.post_merge_rows != pre_merge_rows` 同樣直接 raise(已經是
`load_source` 961-966 行的現有行為,這裡要求把數字也寫進 receipt)。這個
結構屬於 receipt,不是逐列 parquet 欄位(不在候選 cache 的市場資料 parquet
裡重複加 `source_class`/`is_pit` 欄位,除非未來明確另外核准)。

**現況**:**MISSING**——同樣卡在 §C.5 沒有 receipt 機制,是 §F
MISSING_BEFORE_BUILD 的實作範圍。

---

## D. 執行協定與失敗語意凍結(第 17 輪:凍結混合架構 + 單發驗證)

**這一節凍結未來執行的規則,不是現在執行。**

### 混合架構(第 17 輪新增,解除第 16 輪的架構 `BLOCKED_BEFORE_IMPLEMENTATION`)

三個元件,職責互斥,不能越界:

1. **`tej_importer.py`(確定性解析函式庫)**——擁有:單一原始檔的解析
   (`_read_raw_table`/`_split_id_name`/`_parse_dates`)、顯式輸出型別轉換
   (§C.1 的顯式 `.astype`)、key/schema fail-closed 驗證
   (`_check_required_cols`/`_check_valid_keys`/`_check_duplicate_key_
   conflicts`/`_check_sanity_floor`)、supplement 合併與合併斷言
   (`_verify_supplement`/合併後列數檢查)、**在記憶體內產生 §C.9 要求的
   品質證據紀錄**(隨著轉換過程一起收集,回傳給呼叫端,不是自己寫檔)。
   **不擁有**:跨 11 個 dataset 的協調、任何形式的自我驗證/自我認證、
   receipt/sidecar 檔案的實際寫入、路徑安全檢查、身分計算。`load_source()`
   維持是這支函式庫對外唯一的高階入口。
2. **新 builder/orchestrator 腳本(§F MISSING_BEFORE_BUILD)**——擁有:
   §C.4 的隔離根目錄 path-identity 檢查、§C.1 的 `snapshot_id_v1` 計算、
   依 §B 凍結順序逐一呼叫 `tej_importer.load_source()`、stop-on-first-
   failure 協調、把 `load_source()` 回傳的 DataFrame 用 `save_by_stock()`
   (或等價邏輯)發布、把 `tej_importer.py` 回傳的品質證據紀錄寫成 §C.9
   的 sidecar 檔案、寫逐 dataset + 彙總 build receipt(§C.5)。**不擁有**:
   自己判定 `BUILD_VALIDATED`——它能寫的最高狀態是
   `BUILD_COMPLETE_AWAITING_VERIFICATION`。
3. **獨立驗證器腳本(§F MISSING_BEFORE_BUILD;第 18 輪大幅擴充職責範圍)**
   ——**不 import、不呼叫** builder/orchestrator 腳本的任何函式,**也不
   呼叫** `tej_importer.load_source()`(不能重新觸發一次解析當「驗證」,
   那樣只是 builder 的重複執行,不是獨立重建)。擁有:獨立讀取來源身分
   (manifest/supplement receipt 檔案本身)、獨立讀取候選輸出 parquet
   (直接用 `pyarrow`/`pandas` 讀,不透過 builder 的任何函式)、獨立讀取
   sidecar 跟 receipt,**自己重新計算**§C.9 兩階段 accounting、§C.1 的
   `snapshot_id_v1`(從 receipt 記錄的輸入雜湊重算,並且獨立重新雜湊來源
   檔案本身核對一致)、dtype 契約(§C.1)是否符合聲明,寫獨立的驗證
   receipt。**唯一允許共用的東西是「已經提交/凍結的預註冊文件跟 receipt
   schema 本身」**(這份文件、`SUPPLEMENT_SCHEMAS` 這類程式碼凍結常數的
   *定義*,不是 builder 執行當下產生的任何可變狀態)——這樣 verifier 才能
   知道要驗證哪些欄位、哪些等式,但不會信任 builder 執行過程中產生的任何
   中繼判斷。

   **第 18 輪新增,回應「目前的 verifier 職責只重讀雜湊/候選 parquet/
   receipt,沒有真的重新打開原始檔案逐格核對——sidecar 的 `raw_token`/
   覆蓋矩陣/locator 是否屬實,沒有任何獨立管道可以查」**:verifier 必須
   用**自己獨立實作、不跟 `tej_importer._read_raw_table`/`_parse_dates`
   共用程式碼的解析路徑**(否則 `_load_one` 解析邏輯本身如果有 bug,
   builder 跟 verifier 會用同一套錯誤邏輯得出一致的錯誤結論,驗證形同
   虛設),對每一個 dataset:

   - 重新打開 manifest 記錄過的**每一個**原始檔/工作表/zip 成員(不是
     只信 builder 記錄的檔案清單,是從 manifest.csv 出發自己列出應該有
     哪些);
   - 獨立重建每一格的 `source_row_number`/`source_container_member`/
     `raw_token`/`is_blank`/`is_unparseable` 分類;
   - 把重建結果逐筆比對 sidecar 裡的紀錄,以及 §C.9 階段一的 pre-dedup
     分類計數(`column_present_row_count`/`blank_cell_count`/
     `unparseable_cell_count` 等六個分類);
   - 獨立重建「完全重複去重」/「衝突重複」分組,以及每個被保留下來的候選
     key 對應了哪幾筆來源 cell 證據(§C.9 的去重映射);
   - 拿獨立重建的結果去核對候選 parquet 裡的 post-dedup/輸出 null 原因
     accounting(§C.9 階段二的五個分類);
   - 從凍結的 `legacy_supplement/receipt.json` 跟候選輸出的實際欄位,
     獨立驗證 §C.10 的 supplement provenance(而不是隻信 builder 寫的
     `supplement_provenance` 物件本身)。

   **如果對全部 11 個 dataset 做完整獨立重建的執行成本太高,允許在實作
   階段做效能最佳化(例如平行化、串流處理),但不能用抽樣取代完整覆蓋、
   也不能在正式 `BUILD_VALIDATED` 判定時直接信任 builder 產生的彙總數字
   ——抽樣或信任彙總數字或許可以當作 §D 之後允許的非約束力診斷用途,但
   不能構成 `BUILD_VALIDATED` 需要的正式證據。**

**這個劃分直接決定 §C.1 的身分公式**:`importer_identity` 跟
`builder_identity` 現在**永遠是兩個不同的雜湊**(不會因為架構選擇而
重合),`verifier_identity` 獨立於兩者之外——第 16 輪 §F 留的「如果選擇
直接改本體,兩者會是同一個雜湊」這個伏筆,第 17 輪的架構決定讓它不再成立,
公式不需要處理這個特例。

### 單發驗證規則(第 17 輪新增,第 18 輪修正成「整個 run 只有一次」而不是
「每個 verifier_identity 各一次」)

第 16 輪的版本只規定「驗證 receipt 不可覆寫」,但**沒有限制驗證器可以對
同一個 build 跑幾次**,理論上可以一直重跑直到出現一次 PASS,再宣稱「正式
狀態 = 存在至少一份 `BUILD_VALIDATED` 的驗證 receipt」——這等於允許挑結果。
第 17 輪凍結了「一個 `(run_id, verifier_identity)` 只有一次」,但 Codex
在第 18 輪指出這個鎖是**用 `verifier_identity` 也一起當鎖檔命名的一部分**
(`f"{run_id}.{verifier_identity[:12]}.claim"`),代表只要修改驗證器程式碼
(不管是修 bug 還是刻意調鬆某個檢查),`verifier_identity` 就變了、鎖檔
路徑就跟著變,同一個 `run_id` 因此可以拿到**另一次**binding 機會——文字
上寫「不能這樣做」不足以阻止,鎖的機制本身要讓這件事在結構上不可能發生。
第 18 輪修正:

- **Phase A 必須先凍結唯一一個 `authorized_verifier_identity`,寫進§C.5
  的彙總 build receipt(在 Phase B 執行、彙總 receipt 被 builder 寫出的
  當下就已經包含這個欄位——不是驗證時才決定,是建置前就已經跟建置器一起
  凍結、一起 scoped commit 的值)。**
- **一個 `run_id`(不是 `(run_id, verifier_identity)` 這個組合),只有
  一次有約束力(binding)的驗證執行**——`.claim` 鎖檔的排他建立路徑
  **只用 `run_id` 命名**,不含 `verifier_identity`:
  `f"{run_id}.binding_verification.claim"`。這樣不管換幾次驗證器程式碼,
  同一個 `run_id` 永遠只對應**一個**鎖檔路徑,結構上不可能有第二次
  binding 嘗試,不需要再靠文字禁止。
- **驗證器啟動時,先比對自己現在的位元組雜湊 (`verifier_identity`) 跟
  彙總 build receipt 記錄的 `authorized_verifier_identity` 是否相符
  ——不符就必須直接失敗、退出,連 `.claim` 鎖檔都不能建立**(如果連鎖檔
  都建了才發現身分不符,會白白燒掉這個 `run_id` 唯一的一次驗證機會)。
- **身分核對通過後,才對 `.claim` 鎖檔做排他建立**(`open(claim_path,
  "x")`,**在做任何實際驗證工作之前**,而且必須是**原子、durable**的
  寫入(排他建立本身在檔案系統層級是原子的;寫入內容後視平台情況呼叫
  `os.fsync`,避免程序在寫入完成前當掉導致鎖檔內容不完整)。鎖檔內容
  記錄:`authorized_verifier_identity`(等於這次驗證器自己的雜湊)、被
  驗證的彙總 build receipt 路徑+雜湊、開始時間戳、`run_id`。如果排他
  建立失敗(檔案已存在,代表這個 `run_id` 已經有人跑過一次 binding 驗證,
  不管是哪一個 `verifier_identity` 跑的),驗證器必須立刻中止、不產生
  任何驗證 receipt——這個 `run_id` 的正式驗證機會已經用掉了。**一旦
  `run_id` 層級的 `.claim` 鎖檔存在,不會有任何 `verifier_identity`
  能再幫這個 `run_id` 建立第二份 binding 驗證 receipt。**
- **第一份正式(binding)驗證 receipt/結果是唯一有效的**,不能被後續任何
  執行取代或補充。
- **不自動重試**。
- 驗證器 crash、寫出格式錯誤的 receipt、或任何一項重建檢查沒過,結果都是
  `BUILD_VERIFICATION_FAILED`,一樣是這個 `run_id` 唯一、有約束力的結果。
- **Crash 持久性規則(第 18 輪新增)**:`.claim` 鎖檔的存在**本身**就代表
  這個 `run_id` 的驗證機會已經用掉——如果驗證器在鎖檔建立成功之後、驗證
  receipt 寫出之前 crash(沒有任何 receipt 被產生),這個 `run_id` 的
  正式狀態是 `BUILD_VERIFICATION_FAILED`,**不能**回退成
  `BUILD_COMPLETE_AWAITING_VERIFICATION`(「還在等驗證」)——因為那樣等於
  允許事後再排一次隊、變相繞過單發限制。判定邏輯只看「`.claim` 鎖檔存在
  嗎」跟「有沒有對應的 binding 驗證 receipt」,不看「這次驗證到底有沒有
  真的跑完」。
- **修正驗證器程式碼本身會改變 `verifier_identity`**,但因為 `.claim`
  鎖檔已經跟 `run_id` 綁死,修改驗證器不會讓舊的 `run_id` 起死回生——
  要用修好的驗證器,必須走 Phase B 的重跑流程,產生一個**全新的
  `run_id`**,不能沿用舊的 `run_id`。
- **診斷用的重跑**(如果未來另外被核准):必須用不同的檔名前綴(例如
  `diagnostic_` 而非直接進 `verification_receipts/`,也不佔用
  `<run_id>.binding_verification.claim` 這個鎖檔路徑)明確標記
  `binding: false`,永遠不能取代或凌駕上面定義的正式結果。這份文件**不
  核准**診斷重跑機制本身,只預留這個區分,真的要用需要另一輪明確授權。

**正式狀態的判定規則(第 18 輪修正:只認凍結在彙總 receipt 裡的那一個
`authorized_verifier_identity`,不能再「挑一份 PASS」,也把 crash 持久性
規則納入判定邏輯)**:一個 `run_id` 的正式狀態:

1. 若不存在對應的 `.claim` 鎖檔(`<run_id>.binding_verification.claim`)
   ——正式狀態是 `BUILD_COMPLETE_AWAITING_VERIFICATION`(前提是彙總 build
   receipt 本身 `overall_status=BUILD_COMPLETE_AWAITING_VERIFICATION`,
   否則就是 `BUILD_FAILED_PARTIAL`,連驗證階段都還沒到)。
2. 若 `.claim` 鎖檔存在,但**沒有**對應的、`verifier_identity` 等於
   `.claim` 鎖檔裡記錄值的 binding 驗證 receipt——正式狀態是
   `BUILD_VERIFICATION_FAILED`(涵蓋「驗證器 crash 沒寫出 receipt」跟
   「receipt 寫出但格式不合法讀不出來」兩種情況)。
3. 若 `.claim` 鎖檔存在,且存在對應的 binding 驗證 receipt,其
   `verifier_identity` 等於彙總 build receipt 記錄的
   `authorized_verifier_identity`、其 `build_receipt_sha256` 欄位等於
   **現在**重新讀取、重新雜湊那份彙總 build receipt 的結果——正式狀態
   看該驗證 receipt 的 `overall_status`:`BUILD_VALIDATED` 或
   `BUILD_VERIFICATION_FAILED`。

**規則裡不存在「只要有任何一份 PASS 就採計」這個選項**——因為 `.claim`
鎖檔路徑只用 `run_id` 命名,結構上不可能存在第二份 binding 驗證 receipt
可以挑;也不存在「驗證器身分自己說了算」這個漏洞——只有等於
`authorized_verifier_identity` 的那一個雜湊寫出的 receipt 才算數。

### Phase A(實作 + 測試 + 獨立複查 + 凍結雜湊)

沿用第八至十輪對 `institutional_gross_trust_holding_pct_adjudication.py` 已
經走過、被 Codex 驗證有效的模式:先寫程式碼跟 synthetic 測試 (不碰真實資料)
→ 全部測試通過 → 把要執行的腳本/測試檔案雜湊寫進文件凍結 → 只有在這之後才
進 Phase B。§E 額外要求:Phase A 的實作**必須先經過 scoped git commit**,
而且**建置器跟驗證器必須是兩份獨立審查的實作**(第 17 輪的架構決定讓這件
事變成結構性要求,不只是建議),因為兩者的雜湊分別是 `build_
implementation_identity` 跟獨立的 `verifier_identity`——審查時要能個別
確認「builder 有沒有不小心 import 到 verifier 的東西」跟反過來的方向都
沒有。**Phase A 結束的當下,驗證器的雜湊值就此凍結成
`authorized_verifier_identity`(第 18 輪新增,見上方「單發驗證規則」)——
這個值是 Phase A scoped commit 的一部分,不是 Phase B 執行時才決定,之後
每一次 Phase B 執行寫出的彙總 build receipt 都照抄這個凍結值。**

### Phase B(另外授權後,逐 dataset 依凍結順序建置)

*(第 17 輪未修改。)*

- 嚴格依照 §B 凍結的 11 個 dataset 順序執行,**不平行**。
- **不自動重試**。
- **第一個失敗的 dataset 之後,整個 Phase B 立刻停止**,不繼續嘗試剩下的
  dataset。
- 失敗定義:`load_source` 內任何一個 fail-closed 檢查 raise、receipt 寫入
  失敗、或 accounting 斷言不成立。

### `BUILD_FAILED_PARTIAL`

*(第 17 輪未修改。)*

- 如果 Phase B 在第 N 個 dataset 失敗(N 可以是 1),前面已經成功寫出的
  1..N-1 個 dataset 的 parquet + receipt **保留在磁碟上,當作診斷證據**,
  不刪除。
- 整個 run 的彙總 receipt 標記 `overall_status=BUILD_FAILED_PARTIAL`,明確
  記錄失敗在哪個 dataset、原始錯誤訊息。
- **`BUILD_FAILED_PARTIAL` 永遠不能變成 `BUILD_VALIDATED`**——即使後續另一次
  被授權的執行補完了剩下的 dataset,那是**一個新的 run_id**,`BUILD_VALIDATED`
  的判定要求全部 11 個 dataset 的 receipt + 彙總 receipt **在同一個 run_id
  底下**通過獨立重建。

### `BUILD_VALIDATED` 的完成定義

全部 11 個 dataset 的 receipt + 彙總 receipt(狀態必須是
`BUILD_COMPLETE_AWAITING_VERIFICATION`),能被**唯一一次有約束力的**獨立
驗證執行(上面的單發驗證規則)重新計算並逐項比對通過。這支驗證器目前
**不存在**,是 §F 的 `MISSING_BEFORE_BUILD` 項目之一。`BUILD_VALIDATED`
只代表建置本身完整、fail-closed 檢查過,不代表策略績效或科學有效性
(政策文件 §11.7 已經講過,這裡不重複放寬)。

### 不可覆寫命名 + 重跑的 run_id

*(第 17 輪未修改。)*

- 每一次 Phase B 執行 (不論成不成功) 都是一個獨立的 `run_id`
  (時間戳 + uuid)。
- 如果將來一次執行失敗、需要另外授權重跑,新的 run_id 底下的 receipt/輸出
  是**全新的檔案**,不覆寫、不刪除前一個 run_id 的任何東西。
- 驗證器的 `.claim` 鎖檔跟正式驗證 receipt,跟著 `(run_id,
  verifier_identity)` 組合走,不是跟著「每次執行」走——這是第 17 輪單發
  規則的核心,見上方專節。

---

## E. Dirty-worktree 與實作缺口稽核

### E.1 目前的工作目錄狀態(唯讀核對,本輪重新核對過,結果跟第 15/16 輪一致)

**核心問題**:`tej_importer.py` 有 SHA-256(可以被算出來),但那不代表它是
一份「已凍結、已審查的實作」——**目前的 SHA-256 對應的是一份從未被審查、
從未被提交的工作目錄狀態**。逐一核對:

| 路徑 | git 狀態 | 未提交的範圍 |
|---|---|---|
| `tej_importer.py` | **已追蹤但工作目錄已修改** (`git diff --stat`: 959 insertions(+), 267 deletions(-)) | 目前 HEAD 提交的版本只有 434 行 (`git show HEAD:tej_importer.py \| wc -l`);工作目錄版本 1126 行。差距**幾乎就是整個 Round 3-8 補上的 fail-closed 邏輯**。這些全部只存在於工作目錄,沒有 commit。第 17 輪的架構決定後,這份檔案**應該維持在確定性解析函式庫的職責範圍**(§D),不會再被擴充成協調/自我驗證邏輯——所以這份既有的未提交內容,審查範圍不會再擴大,只需要補上 §C.1 的顯式型別轉換跟 §C.9 的品質證據收集。 |
| `scripts/extract_legacy_supplement.py` | **完全未追蹤** (`git ls-files` 無輸出) | 整份檔案從未進過 git |
| `scripts/_full_population_diff.py` | 完全未追蹤 | 整份檔案 |
| `scripts/build_data_manifest.py` | 完全未追蹤 | 整份檔案 |
| `scripts/institutional_gross_trust_holding_pct_adjudication.py` | 完全未追蹤 | 整份檔案 |
| `scripts/institutional_gross_adjudication_verifier.py` | 完全未追蹤 | 整份檔案 |
| `tests/test_tej_data_migration.py` | 完全未追蹤 | 整份檔案 |
| `tests/test_institutional_gross_adjudication.py` | 完全未追蹤 | 整份檔案 |
| `tests/test_institutional_gross_adjudication_verifier.py` | 完全未追蹤 | 整份檔案 |
| `docs/資料快照遷移_DataExport0806.md` | **已提交** (`d46d45c96d738c2fe60497ddba2aa9f1fc5a009c`) | 無 |
| `docs/預註冊_DataExport0806_V2隔離建置.md`(本文件) | **未追蹤**(第 15/16/17 輪都還沒進 git) | 整份檔案 |
| 新 builder/orchestrator 腳本(§D) | **不存在** | 尚未動筆 |
| 獨立驗證器腳本(§D) | **不存在** | 尚未動筆 |
| `requirements-v2-data-build.lock`(§C.1,第 18 輪凍結精確檔名) | **不存在**(`git ls-files \| grep -i lock` 無結果;既有的 `requirements.txt`/`requirements-d2-timing.txt` 是另外兩份不同用途的檔案,已唯讀核對過內容,見 §C.1) | 尚未建立 |

**結論**:除了政策文件本身,**沒有任何一份跟這次遷移相關的程式碼或測試被
提交過**。§C.1 的 `importer_identity`/`extractor_identity` 今天可以被算出來,
但那個雜湊值背後是一份沒有版本控制歷史、隨時可能被繼續編輯而不留痕跡的工作
目錄狀態——不能被當成「Phase A 已凍結的實作」。

### E.2 逐項判定:現有程式碼是否已支援

| 能力 | 判定 | 依據 |
|---|---|---|
| 決定性的 `snapshot_id_v1` 產生(含依賴身分、第 19 輪新增的執行環境身分) | **MISSING** | 全專案 grep 不到 `snapshot_id` 這個詞;也沒有依賴鎖定檔 |
| `runtime_environment_identity_v1` canonical 序列化+雜湊(第 19 輪新增判定項) | **MISSING** | 全專案沒有任何程式碼觀測/序列化執行環境版本字串,更沒有把它雜湊進 `build_implementation_identity` |
| `manifest.csv` vs `.sha256` 逐 relpath 交叉驗證 | **MISSING** | `_manifest_preflight`(173-202 行)只讀 `MANIFEST_CSV` |
| 安全的隔離根目錄驗證(第 19 輪修正:核對完整 64 碼,不是截斷前綴) | **MISSING** | `main()`(1104-1123 行)的 `--cache-dir` 沒有任何路徑驗證;屬於新 builder 職責,不修 `tej_importer.py` 本體的這個 CLI 分支 |
| 顯式數值/字串型別凍結(第 17 輪新增判定項) | **MISSING** | `_load_one`(511-561 行)的 `thousand_cols`/`numeric_cols` 分支只呼叫 `pd.to_numeric`,沒有後續 `.astype`;字串欄位完全沒有顯式轉型 |
| 「欄位整檔缺席補 null 而非消失」的 schema 精確化(第 17 輪新增判定項) | **MISSING** | 516-519/558/526 行現況是「跳過對應,欄位從輸出消失」,跟第 17 輪 §B 凍結的新規則相反 |
| 逐 dataset + 彙總的不可覆寫 build receipt(builder) | **MISSING** | `tej_importer.py` 完全沒有 receipt 寫入邏輯,新 builder 腳本也還不存在 |
| 獨立的驗證 receipt + run 層級單發 `.claim` 鎖機制(第 17 輪新增、第 18 輪修正成 run 層級) | **MISSING** | 建置器的 receipt 都不存在,驗證器跟它的鎖機制更不存在;鎖檔路徑規則(只用 `run_id` 命名,不含 `verifier_identity`)也還沒有任何程式碼實作 |
| 驗證器獨立重讀原始 cell 的解析路徑(第 18 輪新增判定項,不能跟 `tej_importer` 共用解析程式碼) | **MISSING** | 全專案沒有第二套獨立於 `_read_raw_table`/`_parse_dates` 的 Excel/zip 解析實作;這是第 18 輪新增到 verifier 職責範圍的能力,目前完全不存在 |
| `requirements-v2-data-build.lock` 資料建置專用依賴鎖定檔(第 18 輪新增判定項) | **MISSING** | `requirements.txt` 已存在但只服務 Streamlit app、不含 `openpyxl`、非 hash 鎖定(見 §C.1);專用鎖定檔完全不存在 |
| 完整鎖定/安裝相符性契約:專用隔離環境 + marker 解析 + PEP 503 正規化 + 完整清單比對(第 20 輪新增判定項) | **MISSING** | 全專案沒有任何隔離 venv 建立腳本、沒有 `importlib.metadata` 完整清單列舉邏輯、沒有 marker 解析/名稱正規化實作;目前完全不存在對「整個環境是否符合鎖定檔」的檢查,只有第 19 輪版本裡已經判定 MISSING 的四套件比對構想 |
| `marker_environment_v1` canonical 捕捉 + 雜湊(第 21 輪新增判定項) | **MISSING** | 全專案沒有呼叫過 `packaging.markers.default_environment()`,也沒有任何 canonical 序列化實作;`packaging` 是否已在專案相依範圍內本身也待 §F MISSING_BEFORE_BUILD 的鎖定檔一併確認 |
| `environment_creation_receipt_v1` writer + 自身身分計算(第 21 輪新增判定項) | **MISSING** | 全專案沒有任何隔離環境建立/安裝過程的 receipt 寫入邏輯,也沒有排除自身欄位再雜湊的實作先例(先例都是雜湊整個 receipt,不排除任何欄位) |
| `dedup_key` canonical JSON 序列化(第 18 輪新增判定項) | **MISSING** | 同樣卡在 sidecar 機制不存在,且第 17 輪的分隔符號拼接寫法已在第 18 輪判定為不夠精確,需要照新規則重做 |
| supplement 衍生欄位的 `supplement_provenance` metadata(§C.10) | **MISSING** | 卡在沒有 receipt 機制 |
| 品質證據 sidecar(§C.9 兩階段 accounting + 強化 locator) | **MISSING(關鍵)** | `_load_one` 完全沒有 raw_token/is_blank/is_unparseable/container_member/實體列號追蹤;政策文件 §11.3 明講文字 `.` 必須保留品質旗標,目前只在一次性診斷腳本裡實作過,主要匯入器完全沒有 |
| 逐 dataset stop-on-first-failure 的建置協調 | **MISSING** | `--dataset` CLI 一次只能處理一個,沒有跨 11 個 dataset 的協調層;屬於新 builder 職責 |
| 獨立的 receipt 驗證/重建工具 | **MISSING(對這個建置而言);PATTERN 已驗證過** | `scripts/institutional_gross_adjudication_verifier.py` 是已驗證的先例模式,但沒有等價的東西存在於 11-dataset 建置,也還沒有單發鎖機制的先例 |
| 以上機制的測試 | **MISSING** | 上述能力都不存在,自然也沒有對應測試;`_manifest_preflight`/`_check_*`/`_verify_supplement` 這些**已經存在**的機制則都有測試 |

**這裡不主張「敘述有描述某個功能就代表它存在」**——每一項判定都附上函式名
+ 行號 (已實作) 或明確寫 `MISSING`,沒有第三種「大概有」的說法;第 17 輪
之後,**已經沒有任何一項是 `DESIGN_BLOCKED_SCHEMA_CONTRACT`**——dtype 契約
在 §C.1 已經明確凍結。

---

## F. 決策登記與授權關卡(Checkpoint 22 更新)

### FROZEN(已由既有已提交政策或本文件的精確檢查支持)

- **`AUTHORIZED_PATH`(Checkpoint 22 新增,2026-08-08 使用者核准,從
  `PROPOSED_NOT_AUTHORIZED` 移入)**:隔離候選 cache/receipt 的確切輸出
  根目錄——完整絕對路徑
  `C:\dev\Project 1\tej_exports\v2_candidate\<snapshot_id_v1 完整 64 碼
  小寫十六進位>\<run_id>\{cache,build_receipts,quality_sidecars,
  verification_receipts}\`(§C.4 有完整布局圖、path 守衛規則、保護路徑
  排除清單,內容自第 17-21 輪凍結後未再變動)。**這是本文件目前唯一一項
  從「待核准」轉成「已核准」的決定**——核准的是路徑本身,**不是** Phase A
  程式碼實作或 Phase B 執行的授權,§F `MISSING_BEFORE_BUILD` 底下每一項
  依然明確 `MISSING`。
- §B 的 11-dataset 凍結順序、逐 dataset 精確最終欄位契約(第 18 輪修正
  公式:排除 `thousand_cols` 中繼 key,不再分必要/選用,欄位集合固定,
  值缺席用覆蓋矩陣表示)。
- §C.1 的 `snapshot_id_v1` 三層公式(含 `builder_identity`/
  `dependency_lock_identity`/`runtime_environment_identity_v1`,第 18
  輪把 `dependency_lock_identity` 的輸入凍結成具體檔名
  `requirements-v2-data-build.lock`)、顯式數值(`float64`)/字串型別
  凍結。
- **PEP 508 marker 環境 `marker_environment_v1`(第 21 輪新增 FROZEN
  項,修正第 20 輪對 marker 解析環境的錯誤描述)**:直接捕捉
  `packaging.markers.default_environment()` 的完整 11 鍵回傳值(不是
  自行拼湊 `sys.version`/`platform.system()`/`platform.machine()` 這類
  不完整/不精確的子集),canonical JSON **物件**(`sort_keys=True`)+
  小寫 SHA-256 → `marker_environment_identity_v1`;是 §C.1 完整鎖定/
  安裝相符性契約裡 marker 解析用的**唯一**環境來源,也是
  `runtime_environment_source` 的第 14 個輸入(原 13 個元素擴充);
  verifier 用 receipt 記錄的這個物件重新解析,不是用自己機器的 marker。
- **執行環境身分 `runtime_environment_identity_v1`(第 19 輪新增 FROZEN
  項,第 21 輪擴充成 14 個元素)**:versioned canonical JSON 陣列
  (`"runtime_environment_identity_v1"` 起頭,涵蓋 Python/OS/CPU 架構/
  四個套件版本/Parquet 引擎/Excel 引擎/鎖定檔雜湊/`marker_environment_
  identity_v1`)+ 跟 `dedup_key_v1` 同一套序列化紀律(`ensure_ascii=True`
  /緊湊分隔/UTF-8/小寫 SHA-256),是 `build_implementation_identity` 的
  第五個輸入;verifier 從 receipt 記錄的不可變原始欄位重新計算並核對
  (不是重新觀測建置機器),另外獨立記錄自己的執行環境指紋,兩者不混用。
- **`environment_creation_receipt_v1` 精確 schema(第 21 輪新增 FROZEN
  項,取代第 20 輪「隔離環境建立+安裝過程本身的 receipt/雜湊」這句模糊
  描述)**:固定鍵集合的一份 receipt(schema tag/run_id/
  `preregistration_commit`/鎖定檔路徑+雜湊/marker 環境物件+雜湊/安裝
  工具身分/bootstrap 清單/安裝指令陣列/起訖時間戳/exit code/安裝報告
  雜湊(若有,否則明確 `null`)/stdout·stderr 雜湊/兩份 inventory+雜湊/
  相符判定),`sort_keys=True` canonical 序列化並**排除自身
  `environment_creation_identity` 欄位**後雜湊;必須在候選資料解析開始
  前排他建立完成;彙總 build receipt 同時記錄檔案路徑、檔案位元組雜湊、
  內部身分值三者;verifier 核對檔案雜湊、重算內部身分、核對被引用證據,
  不宣稱能重建已銷毀的環境。
- **完整鎖定/安裝相符性契約(第 20 輪新增 FROZEN 項,取代第 19 輪「只比對
  四個具名套件」的窄化規則)**:Phase B 在專用隔離環境執行(`pip install
  --require-hashes` 安裝 `requirements-v2-data-build.lock`,不沿用一般
  開發環境);marker 解析 + PEP 503 套件名稱正規化算出 `lock-selected
  inventory`;跟隔離環境裡**完整**的第三方套件清單(僅 `pip`/
  `setuptools`/`wheel` 這三個 bootstrap 工具例外,例外清單精確凍結、不
  開放式)做完整集合比對,任何缺席/版本不符/未宣告多餘套件都 fail-closed;
  安裝時 hash 驗證(認證下載的安裝檔案)跟安裝後清單比對(認證環境現狀)
  是兩種不同語意的檢查,不能互相取代;彙總 build receipt 記錄
  `lock_selected_inventory`/`installed_inventory` 兩份 canonical 清單
  + 各自雜湊 + bootstrap 工具清單 + 環境建立身分,verifier 獨立重建
  `lock_selected_inventory` 並核對 receipt 記錄內容自洽(不宣稱能重新
  觀測已銷毀的建置環境);這是 Phase B 的**額外**前置關卡,不取代原有的
  `runtime_environment_source`/`dependency_lock_identity`。
- **完整內容位址路徑(第 19 輪新增 FROZEN 項)**:隔離候選輸出根目錄的
  子目錄名稱一律用完整 64 碼小寫 `snapshot_id_v1`,不使用任何長度的
  截斷前綴;path 守衛核對目錄名稱字串逐字元等於 receipt 記錄的完整值。
- **混合架構(第 17 輪新增 FROZEN 項)**:`tej_importer.py` = 確定性解析
  函式庫;新 builder 腳本 = 協調/身分/路徑守衛/receipt/sidecar 寫入;獨立
  verifier 腳本 = 不 import 任何一方、獨立重建,且**必須用自己獨立的
  Excel/zip 解析路徑重讀原始 cell**(第 18 輪新增,不能跟 `tej_importer`
  共用解析程式碼)。三者身分互相獨立。
- **單發驗證規則(第 17 輪新增,第 18 輪修正成 run 層級 FROZEN 項)**:
  一個 `run_id`(不是 `(run_id, verifier_identity)`)只有一次 binding
  驗證機會;`authorized_verifier_identity` 在 Phase A 凍結、寫進彙總
  build receipt;`.claim` 鎖檔路徑只用 `run_id` 命名
  (`<run_id>.binding_verification.claim`);鎖檔存在但沒有對應 receipt
  時,正式狀態直接判定 `BUILD_VERIFICATION_FAILED`(crash 持久性規則),
  不會回退成「還在等驗證」。
- **`dedup_key` canonical 序列化(第 18 輪新增 FROZEN 項)**:versioned
  canonical JSON 陣列(`"dedup_key_v1"` 起頭)+ 固定欄位順序 + `ensure_
  ascii=True` + 緊湊分隔符號 + UTF-8 編碼 + 小寫 SHA-256,取代第 17 輪
  的分隔符號拼接寫法。
- `BUILD_NOT_RUN`/`DIAGNOSTIC_OUT_OF_SCOPE_BUILD`/
  `BUILD_COMPLETE_AWAITING_VERIFICATION`/`BUILD_FAILED_PARTIAL`/
  `BUILD_VERIFICATION_FAILED`/`BUILD_VALIDATED`/`PRODUCTION_NOT_APPROVED`
  的定義與單向轉移規則。
- `LEGACY_DERIVED_SUPPLEMENT` 的範圍與條件、§C.10 的 supplement provenance
  receipt schema、§C.9 的品質證據 sidecar 兩階段 accounting schema(第 18
  輪擴充:verifier 必須從獨立重讀的原始 cell 重建這些 accounting,不是
  只跟候選 parquet/sidecar 檔案內容互相比對)。
- `trust_holding_pct=DIFF_UNRESOLVED`。

### PROPOSED_NOT_AUTHORIZED(尚待使用者/Codex 核准的選擇)

**Checkpoint 22 後:空**——本文件從第 17 輪開始只剩輸出根目錄路徑這唯一
一項提案,2026-08-08 已經被使用者明確核准,移到上面的 `FROZEN` /
`AUTHORIZED_PATH`。目前沒有任何一項還停在「已有建議、待核准」狀態。

### BLOCKED_BEFORE_IMPLEMENTATION

**第 17 輪後就是空,Checkpoint 22 後依然是空——原本的架構選擇跟 7 個
欄位的 dtype 契約兩項都已經解除(分別見 §D 的混合架構凍結、§C.1 的顯式
型別凍結)。第 18 輪修的五個內部不一致、第 19 輪修的兩個身分/路徑缺陷、
第 20 輪修的鎖定/安裝相符性窄化缺口、第 21 輪修的兩個執行環境精確性
缺口(marker 環境、環境建立 receipt),全部屬於「把已經凍結的設計講
精確」,沒有引入新的未決架構矛盾。Checkpoint 22 只記錄使用者對輸出路徑
的核准,同樣不是設計矛盾,也不會讓本節從空變成非空。**

### MISSING_BEFORE_BUILD(需要實作 + 審查的程式碼/測試/receipt;Checkpoint 22 後每一項依然明確 MISSING,內容未變)

1. `tej_importer.py` 補上 §C.1 的顯式型別轉換(數值 `.astype("float64")`、
   字串欄位顯式轉型)+ §B 第 18 輪修正後的精確 schema 公式(欄位整檔缺席
   補 null 而非消失,且不含 `thousand_cols` 中繼 key)+ §C.9 要求的品質
   證據紀錄收集(回傳給呼叫端,不寫檔)+ 對應測試。
2. 新 builder/orchestrator 腳本(§D 職責範圍):`snapshot_id_v1` 計算
   (含 manifest.csv vs `.sha256` 交叉驗證、`runtime_environment_
   identity_v1`/**第 21 輪新增的 `marker_environment_v1`** canonical
   序列化+雜湊)、完整鎖定/安裝相符性檢查(專用隔離環境建立、**用
   `marker_environment_v1` 解析 marker**、PEP 503 名稱正規化、
   `lock_selected_inventory`/`installed_inventory` 完整清單比對、
   bootstrap 工具例外處理,全部在計算 `runtime_environment_identity_
   v1`/`snapshot_id_v1` 之前 fail-closed 完成)、**第 21 輪新增的
   `environment_creation_receipt_v1` writer**(必須在候選資料解析前
   排他建立完成)、隔離根目錄 path-identity 驗證器(核對目錄名稱逐字元
   等於完整 64 碼 `snapshot_id_v1`)、11-dataset stop-on-first-failure
   協調、逐 dataset/彙總 build receipt writer(§C.5,含
   `authorized_verifier_identity`/`runtime_environment_source`/
   `runtime_environment_identity_v1`/`lock_selected_inventory`/
   `installed_inventory`/`bootstrap_tool_inventory`/第 21 輪修正精確的
   `environment_creation_receipt_path`/`environment_creation_receipt_
   sha256`/`environment_creation_identity` 欄位)、品質 sidecar writer
   (§C.9,含 canonical `dedup_key` 序列化)、`supplement_provenance`
   writer(§C.10)+ 測試。
3. 獨立驗證器腳本(§D 職責範圍):不 import builder/`tej_importer.
   load_source()`;**自己獨立實作一套 Excel/zip 原始檔解析路徑**(不跟
   `tej_importer._read_raw_table`/`_parse_dates` 共用程式碼),重讀
   manifest 列出的每一個原始檔/工作表/zip 成員,獨立重建 locator/
   raw_token/blank/unparseable 分類、去重映射、post-dedup null 原因
   accounting、supplement provenance,並拿獨立重建結果逐項比對 sidecar/
   receipt/候選 parquet;啟動時核對自身雜湊等於彙總 build receipt 記錄的
   `authorized_verifier_identity`,不符就不建立 `.claim` 鎖檔直接失敗;
   從 build receipt 的 `runtime_environment_source` 原始欄位獨立重算
   `runtime_environment_identity_v1` 並核對其正確參與 `build_
   implementation_identity`、另外獨立記錄自己的執行環境指紋(不進
   `snapshot_id_v1`,只進驗證 receipt 稽核用);**用 receipt 記錄的
   `marker_environment_v1`**(不是自己機器的 marker)自己獨立解析
   `requirements-v2-data-build.lock` 重建 `lock_selected_inventory`,
   核對跟 receipt 記錄的相符,並核對 `installed_inventory`/相符判定的
   內部一致性;**第 21 輪新增**:核對 `environment_creation_receipt_v1`
   檔案雜湊、重算排除自身欄位後的 canonical 身分、核對被引用證據雜湊;
   run 層級單發 `.claim` 鎖機制(`<run_id>.binding_verification.claim`)
   + 驗證 receipt writer(§D 單發驗證規則,含 crash 持久性判定)+ 測試。
4. `requirements-v2-data-build.lock`(§C.1 `dependency_lock_identity` 的
   輸入,精確檔名已凍結)——選定工具(`pip-compile --generate-hashes`/
   `uv pip compile --generate-hashes`/`poetry export --with-hashes` 之
   一,這份文件不代為決定工具選擇)產生含精確版本+雜湊的鎖定內容,涵蓋
   `pandas`/`pyarrow`/`openpyxl` 及其完整遞移相依鏈;建立資料建置專用
   隔離環境(venv 或等價機制)的腳本/流程本身,以及 marker 解析(基於
   `packaging.markers`)+ PEP 503 正規化 + 完整清單比對 + bootstrap
   例外的實作 + 測試。
5. import 白名單靜態檢查(§C.6),涵蓋 `tej_importer.py` 跟新 builder 腳本
   兩份檔案 + 測試。
6. 上述 1-5 的實作完成後,對**整批**受影響檔案(含 §E.1 表格列出的、現在
   就已經未提交的既有實作)執行一次 scoped git commit + 獨立複查——不能讓
   Phase A 的「凍結雜湊」建立在一個從未被審查過的工作目錄狀態上。**這是
   一次獨立的實作複查 checkpoint,它的 commit hash 不是 §C.1 的
   `preregistration_commit`(Checkpoint 23 修正——`preregistration_
   commit` 專指這份預註冊文件自己最後一次被改動的 commit,用
   `git log -1 --format=%H -- <本文件路徑>` 查,不會因為之後任何其他
   commit——含這裡講的 Phase A 實作 commit 本身——而改變)。**這次 Phase
   A 實作 commit 涉及的每一支程式碼,身分已經各自由 `importer_identity`/
   `extractor_identity`/`builder_identity`/`verifier_identity`/
   `dependency_lock_identity` 涵蓋(§C.1);彙總 build receipt **可以**
   額外把這次 Phase A 實作 commit 的 hash 記錄成稽核用的中繼資料(例如
   `phase_a_implementation_commit` 這樣的獨立欄位),但**不能**把它寫成
   或誤標成 `preregistration_commit`——兩者是不同語意、不同時間點的
   commit。這次 Phase A 實作 commit 也是 `authorized_verifier_identity`
   (§D)正式凍結的時間點。

### 最終狀態

```
PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED
```

**跟第 15/16 輪的 `DESIGN_BLOCKED` 性質不同,跟第 17/18/19/20/21 輪的
`DESIGN_BLOCKED` 性質也不同**:第 15/16 輪是因為還有未解的技術性設計
矛盾(架構二選一、dtype 契約缺失);第 17 輪解除了那些矛盾,但留下四個
內部不一致跟一個需要收斂的決定(依賴鎖定檔);第 18 輪逐一修掉,但又
留下兩個身分/路徑缺陷;第 19 輪逐一修掉,但留下鎖定/安裝相符性判定的
窄化缺口;第 20 輪修掉,但留下 marker 解析環境跟
`environment_creation_identity` 兩個精確性缺口;第 21 輪修掉,**確認
之後已經沒有殘留的技術性設計缺口**,唯一剩下的阻塞項是輸出根目錄路徑
的使用者核准——**Checkpoint 22(2026-08-08)這項核准已經發生**,§F
`PROPOSED_NOT_AUTHORIZED` 因此清空,狀態才第一次能離開
`DESIGN_BLOCKED`,改為 `PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED`。

**這個狀態名稱裡的 `IMPLEMENTATION_NOT_AUTHORIZED` 要照字面讀**:預註冊
文件本身已經完整、內部一致、唯一的使用者決定也已經核准,**但這完全不
構成 Phase A 程式碼實作或 Phase B 執行的授權**——§F `MISSING_BEFORE_
BUILD` 六個項目、§E 整份 dirty-worktree 稽核,全部維持不變,一個字都
沒有因為這次 checkpoint 而改成「已完成」。要往下走,需要另一輪明確的
Phase A 實作授權。

`BUILD_NOT_RUN` 維持不變;`PRODUCTION_NOT_APPROVED` 維持不變;
`trust_holding_pct` 維持 `DIFF_UNRESOLVED`;§D 的單發驗證規則、
績效/OOS/Gate 存取的全部禁止事項,都原封不動延續下去。這次 checkpoint
**沒有**、也**不能**宣告 `BUILD_VALIDATED`,甚至沒有讓 `BUILD_NOT_RUN`
往前推進一步——推進的只有「這份文件本身可以被凍結、被審查」這件事。
