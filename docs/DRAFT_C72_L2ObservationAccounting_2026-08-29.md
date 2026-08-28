# DRAFT · C-72 · 終局重新分類下的 L2 observation accounting

> **STATUS: DRAFT — NOT NORMATIVE, NOT FROZEN.**
>
> 本檔**不是** Master Preregistration 的一部分。撰寫本檔**未**上版號、
> **未**修改 `research/b0_registry/master_prereg_freeze.json`、
> **未**修改任何 normative module、**未**改動任何 run artefact 的位元組。
>
> 目標版號 **v1.37**、closure 編號 **C-72**。經 Codex 覆核與使用者批准後，
> 方由 §6 的擬議文字落入 `docs/FrozenB0_MasterPreregistration.md`。
> 若被否決，依 C-67 前例保留為 rejected history，版號與編號**不重用**。

---

## §0 · 這份裁決在回答什麼

C-56（v1.22）凍結了「`RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` 在七項條件
全部成立時不消耗 once-only observation」。C-57（v1.23）凍結了「invalid run 永久保留、
不刪除、不覆蓋、**不改標籤**」。

兩者都沒有回答這個情形：

> 一個以 outcome **A** 記錄的 run，事後被證明其根因屬於 outcome **B** 的類別。
> 標籤怎麼辦？額度怎麼算？兩者是同一個問題還是兩個問題？

官方 L2 run `L2-af1b4d90c29b3b5f` 正是這個情形，而且它是**唯一**消耗掉 Frozen B0
once-only observation 的 run。在這個問題有答案之前，「L2 是否已結案」無法回答。

---

## §1 · 事實基礎

本節數字皆於 **2026-08-28 / HEAD `bc1ddd01`** 實測，read-only，未寫入任何檔案。

### §1.1 · 兩次正式開封

| 開封時間 (UTC) | run | 記錄的 outcome | 額度 |
|---|---|---|---|
| 2026-08-19T06:25:31 | `L2-2520c80aa980d681`（legacy pinned） | `RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` | **未消耗**（§9.6a 七條件豁免，attestation 在案） |
| 2026-08-19T10:03:02 | `L2-af1b4d90c29b3b5f` | `NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK` | **已消耗** |

```
effective_observation_count() = 1
effective_observations()      = ('L2-af1b4d90c29b3b5f',)
```

兩列的 `repair_of` 皆為 `None`：至今未登記任何 repair。

### §1.2 · 該 run 的終局現場

```
formal_outcome  NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK   (§6.1.14 F-CA-B)
terminal        seq 2 / 141, period 2014-08
reason          §6.1.12: 1589/stock_dividend on 2012-09-13 is NOT_RECONSTRUCTIBLE
                and B0 is exposed (no admissible official bonus-share ratio (C-51))
code_commit     3256270b   ( = C-59 / Master v1.25 )
```

### §1.3 · 該終局是分類錯置——四項獨立證據

| # | 量測 | 結果 | 推論 |
|---|---|---|---|
| 1 | 該 run 與 B0.7 診斷的 **period 1 `post_state_hash`** | 皆為 `c84c62c4f26a9223743e49081fdda18d1a1e1a5b558538302e32f508fee4239d` | 兩者期 1 執行後狀態逐位元相同 |
| 2 | B0.7 全程（seq 1–66）是否曾對 `1589` 有 CA 或 claim 暴露 | **否** | 該 run 在 seq 2 並未持有 `1589`，卻宣稱 `B0 is exposed` |
| 3 | B0.1 診斷（Master v1.26，**只含 C-60**，早於 C-62／C-63 的 ledger 重建） | 終止於 **seq 3**（2014-09） | 以**同一份資料**越過 seq 2；解除該點的是 C-60，非任何資料變動 |
| 4 | `data/b0/` 20 個 sealed derived artefact 對 freeze pin | **20 / 20 逐位元 MATCH** | 自封存以來無資料變動，故 3 的推論不受污染 |

C-60（v1.26 / Frozen B0.1）的內容正是「corporate-action exposure 取得時間維度」與
「避免舊事件重播到 re-entry 部位」，且其條文自陳 **parent = Frozen B0，由官方 L2 run
`L2-af1b4d90c29b3b5f` 暴露**。

一個 2012-09-13 的事件無法附著於任何 spell —— 首個執行 session 為 2014-08-01，
而 §6.1.7／C-60 凍結的區間規則是 `H.start < E.effective_date <= H.end`。
**該事件從一開始就不該被詢問。**

> **附帶推論（獨立於本裁決，但應一併記錄）：**
> `data/b0/bonus_share_panel.parquet` 的 harvest 地板
> `WINDOW_FROM = 2013-06-29`（`research/b0_materializer/build_bonus_share_panel.py:58`，
> 理由為首個決策月 2014-07 的最深價格錨 P⌄(t−13) = 2013-06 月末，更早的事件同除兩錨相消）
> **自始至終正確**。面板中 `stock_id == '1589'` 為 0 列不是覆蓋缺口。
> ⇒ **不得**以「延伸配股 harvest 至 2012」作為本 run 的 `DataRepair`：
> 該資料缺口不存在，如此登記將構成 §9.6b-R3 所禁止的反向錯置。

### §1.4 · 該 run 實際觀測到了什麼

```
記錄之 period 數            1   ( seq 1, period 2014-07, as_of 2014-07-30 )
post-state 部位數           20
port_value                  2000000.0   ( = 開倉資本，無已實現績效 )
nav_series.json             不存在
```

---

## §2 · 裁決（治理層旁路，2026-08-29）

### §9.6b-R1 · 分類錯置成立，終局類別改判

`L2-af1b4d90c29b3b5f` 之 raw F-CA-B 終局**確為分類錯置**。治理層旁路裁定：
該 run 之**缺陷類別**為 `RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE`
（§6.1.14 F-CA-C）。

### §9.6b-R2 · 額度仍然消耗

改判**不**使該 run 取得 §9.6a 的非消耗豁免。該 run 在錯誤發生前已完成 period 1
的決策與執行並建立 **20 檔投組**（§1.4），故七條件中**至少兩條不成立**：

```
1  zero effective strategy decision observations              ✗ 已形成一次有效決策
2  no strategy-dependent portfolio, NAV, return, performance   ✗ 已產生 strategy-
   metric, benchmark comparison, or other strategy-outcome        dependent portfolio
   information was produced or viewed
```

七條件為連言，一條不成立即全部不成立。

```
effective_observation_count() = 1        （維持不變）
Frozen B0 之 once-only L2 observation ：已消耗，終局
```

### §9.6b-R3 · C-57 與 C-56 分別治理兩件事，並存

| 條款 | 治理對象 | 對本 run 的效果 |
|---|---|---|
| **C-57** | provenance | 原始標籤 `NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK` **原樣保留**，不刪除、不覆蓋、不改寫 |
| **C-56** | observation accounting | 依七條件判定 **消耗** |

**改判之效力僅及於缺陷類別的認定，不及於 provenance 標籤，亦不及於會計結果。**

---

## §3 · 為什麼「重新分類」不得成為復活術

本裁決最重要的一句是 §9.6b-R2 的**理由**，而不是它的結論。

若本案以「標籤是 `NOT_EVALUABLE_*`，而 §9.6a-R2 結語規定該類永遠消耗」結案，
則規則被綁在**標籤**上，於是任何 run 只要事後改判為 F-CA-C 即可主張豁免。
由於任何 reconstruction block 事後都可被敘述為「不該問這個問題」的實作缺陷
（本案即為適例），該讀法會使 once-only 形同虛設。

**故本裁決明文將會計綁在七條件上，而非綁在標籤上：**

> **§9.6b-R4（擬議，規範性）** ——
> 一個 run 之終局類別事後被改判，**本身不改變** once-only observation accounting。
> 會計恆依 §9.6a-R2 之七項條件對**該 run 實際發生之事實**重新評估；
> 改判至多影響第 3 條（defect is implementation / input-conformance）之成立與否，
> 其餘六條不因改判而改變。
>
> 特別地：**第 1、2 條所述之事實一旦發生即不可撤銷** ——
> 已在非空母體上形成的決策、已建立的投組、已產生或檢視的績效資訊，
> 不因該 run 後來被歸為何種缺陷類別而回復為未發生。

§9.6a-R2 既有結語「non-evidential 與 non-consuming 是兩個不同性質」於此獲得第三個
同族命題：**mis-classified 與 non-consuming 亦是兩個不同性質。**

---

## §4 · 被消耗的是什麼：決策觀測，非績效

第 2 條**整體不成立**（已產生 strategy-dependent portfolio），但其列舉項目
並非同時發生。逐項核對 §1.4：

| 第 2 條列舉項 | 是否產生 |
|---|---|
| strategy-dependent portfolio | **是** —— 20 檔部位 |
| NAV | 否 —— 未寫出 `nav_series.json` |
| return / performance metric | 否 —— `port_value` 僅為開倉資本 2,000,000.0 |
| benchmark comparison | 否 —— 該 run 未達 §9.3 階梯 |

**條件 2 不成立與「績效已被觀測」不是同一件事。** 前者足以取消豁免，
後者才決定窗口交出了什麼。故本次消耗之內容應精確記載為：

> **Frozen B0 sealed window 已交出之資訊 = 凍結規格於 decision date 2014-07-30
> （as_of 2014-07-30、execution 2014-08-01）所選出之 20 檔標的名單及其執行後狀態。
> 未交出任何績效資訊。**

此界線為規範性：任何日後引用 Frozen B0 窗口之主張，須揭露此範圍（含「決策已觀測、
績效未觀測」之區分），
且**不得**主張該窗口之績效面仍屬未觀測——once-only 額度已消耗，
窗口不再具備產出 `Supported` / `Not Supported` 之資格（§9.4 之 gate 已無從執行）。

---

## §5 · 殘留項：該標籤的第三個消費者

裁決處理了 provenance 與 accounting 兩個消費者。**尚有第三個。**

```
core/b0_master_prereg.py:927   assert_rerun_admissible(previous, repair)
```

該函式依 `previous.outcome`（即**原始標籤**）分派可接受的 repair kind：

```
previous.outcome == RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE
    → ImplementationConformanceRepair
else
    → DataRepair
```

標籤依 C-57 留在 F-CA-B ⇒ **該閘門將要求 `DataRepair`**，
而治理層已裁定該缺陷屬 implementation。其自身 docstring 寫著：

> Accepting a `DataRepair` for a conformance failure would record an
> implementation defect as a data defect.

即該閘門現於規範模組中執行著與本裁決**相反**的規則。又依 §1.3 附帶推論，
本案並不存在可用之 `DataRepair`，故該路徑同時是死路。

**兩個處置選項，本草稿不預設立場：**

- **(a) 分派改讀已裁決類別。** 新增不可變的 adjudication record，
  `assert_rerun_admissible` 於分派前先查詢之；標籤仍依 C-57 不動。
  代價：新增一個 governance artefact 與其 schema、綁定與測試。
  適用前提：未來仍可能對某個 lineage 嘗試 reopening。
- **(b) 明文宣告本 lineage 不再有 reopening，該分派對 Frozen B0 為 moot。**
  代價：僅文字。適用前提：接受 Frozen B0 之 L2 終局結案，
  日後任何規格變更依 §1.4 no-post-hoc-rescue 走新版本（B1、B2 …）且主證據為 L3。

> 選 (b) 時**必須**明文寫出「該閘門對本 lineage 為 moot」，
> 否則日後閱讀者會將其讀為一扇開著的門。

---

## §6 · 對條文的具體修改建議

**新增 §9.6b「Observation accounting under a re-classified terminal」**，
置於 §9.6a 之後，內容為本檔 §2 之 R1~R3 與 §3 之 R4。

**§9.6a-R2 結語**追加一句（不改動既有七條件、不改動既有任一句）：

> 同理，**mis-classified 與 non-consuming 亦是兩個不同性質**：
> 終局類別之事後改判不重開會計，詳見 §9.6b。

**M-2 · L2 outcome vocabulary** 追加一段（不新增 outcome、不改拼寫）：

> **v1.37 · 標籤與缺陷類別分離。** 一個 run 之**記錄標籤**（C-57，provenance）
> 與其**缺陷類別**（可經治理層裁決改判）自 v1.37 起為兩個獨立概念。
> 詞彙表不因改判而新增或改名任何 outcome。
> 讀取標籤以進行分派之程式須明示其讀的是哪一個（見 §9.6b-R5）。

**§9.6b-R5** 依 §5 之選項擇一寫定。

---

## §7 · 機械強制（**尚未實作**）

本草稿**未**撰寫任何程式。若批准，建議至少一條 declaration conformance binding：

- `l2_reclassification_does_not_reopen_accounting` ——
  以注入之 registry 列證明：一列 outcome 為 F-CA-B、但帶有改判記錄且
  `zero_effective_decision_observations = False` 者，
  `effective_observations()` 仍將其計入；且僅當七條件全部成立時方排除。
  正反兩側皆須施測（比照 C-71 對 `assert_capture_inventory` 的長短集合雙向拒絕）。

另建議一條回歸測試釘住本案事實：`effective_observations()` 恆含
`L2-af1b4d90c29b3b5f`。

---

## §8 · 變更判定

```
runtime semantics changed              false
strategy semantics changed             false
data / state / outcome rules changed   false
sealed artefacts changed               false   ( data/b0 20/20 MATCH )
run artefact bytes changed             false   ( C-57 immutability 未觸及 )
normative module hashes changed        false   ( 本草稿未修改任何模組 )
```

適用範圍限於 L2 observation accounting 之治理層。141 market-side state hash、
L2 spans、歷史 run、L3 §19／§20 契約全部不變。

---

## §9 · 若批准之落地清單

1. §6 之文字落入 `docs/FrozenB0_MasterPreregistration.md`，版本行追加 v1.37 / C-72。
2. §5 選項定案並寫入 §9.6b-R5；若選 (a)，另需 adjudication record 之 schema 與模組。
3. §7 之 declaration binding 與回歸測試落地。
4. 重算 `spec_sha256` / `spec_bytes`，更新 `master_prereg_freeze.json`
   （**本草稿階段不做**）。
5. 全套測試綠燈後單筆 commit，工作樹回到 clean —— 後續 L3 floor capture 之
   repo identity 方能綁定含本裁決之身分。

---

## §10 · 連帶效果（記錄用，非規範）

- **Frozen B0 之 L2 結案。** 主證據轉 L3，與 §1.4 no-post-hoc-rescue 條款所指方向一致。
- **B0.8 降級。** 該 158 筆 holder-side 條款回填幾乎純為 L2 replay 資產；
  L2 結案後，其剩餘用途僅為 L3 前瞻線遭遇重組退場時之單筆即時需求，
  不再需要 158 筆之歷史回填。除非日後開啟 B1 lineage，否則不再投入資源。
  （2026-08-28 實測：158 筆中 66 筆生效日早於首個執行日、2 筆晚於窗口末日，
  結構上永不可及；47 筆落於已觀測區間且**實測 0 筆附著**；43 筆落於未觀測區間，
  其中僅 `8913`、`6514` 落在 B0 曾暴露之證券上。）
- **關鍵路徑轉為 L3 首個 floor capture（A02）。**
