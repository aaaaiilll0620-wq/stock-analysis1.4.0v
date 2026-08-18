# D-1 · Price Universe Repair & Closure

**日期:** 2026-08-18
**狀態:** ✅ **`price_universe_survivorship = SATISFIED`** · `S-3a = SATISFIED` · **S-3b 仍 OPEN（新開 O-F）**
**合規:** **未執行 L2、未計算 CAGR / Sharpe / MDD / IC / win rate、未產生或檢視選股名單、未比較 Frozen A、未使用 A0–A3、未修改 feature / eligibility / portfolio / execution / cost 規格。** 未 stage、未 commit。

> 規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.9 §2.8。本文件為 rationale 與稽核紀錄。

---

## 1. 新來源

`tej_exports/DataExport0806/個股股價、本益比2004-20260817/`

該資料夾同時含**舊的逐年 xlsx（7/14–7/15 vintage）**與**兩個 8/18 的新 zip**。新資料只在 zip 裡，涵蓋 2019 之後。

| zip | sha256 | bytes | member | 解壓後 |
|---|---|---:|---|---:|
| `股價 2019-2022.zip` | `9cd41e…`（見 JSON） | 70,810,249 | `20260818033649.csv` | 285,907,334 |
| `股價2023-20260817.zip` | 同上 | 67,936,256 | `20260818033836.csv` | 272,860,926 |

UTF-16 TSV、11 欄、兩個 member schema **完全一致**且符合預期：
`證券代碼 / 年月日 / 開高低收 / 成交量(千股) / 成交值(千元) / 流通在外股數(千股) / 本益比-TEJ / 股價淨值比-TEJ`

**Canonical source 組成（vintage boundary，非 patch）：**

```
<= 2018   既有逐年匯出（從來不是缺陷所在）
>= 2019   20260817 re-export，整批取代
```

**明文不是拼補：** 2019+ 整個時代被全量取代並從頭重新驗證，過程中未查閱任何由舊 corpus 導出的缺失名單。

---

## 2. Hash / coverage

| 項目 | 值 |
|---|---|
| 2019+ 匯出本身 | 2,050 檔 / 3,470,627 列 / 2019-01-02 .. 2026-08-17 |
| **composed canonical source** | **2,306 檔 / 2004-01-02 .. 2026-08-17** |
| `content_sha256` | **`2646356f406a585c53954430eb5ad2967ddebc5c20ef12ea51f4333009d63549`** |
| 舊 quarantined corpus | `aeda65b99ec9d4b4e02f96e20e3d915c5519329d010415f2be3e4cb667ea49c1` |
| **兩者不同** | ✅ |
| `schema_sha256` | `e6c55c6e89486cbbca2452b1b979c2ab25a8e793cf40ab83e911cfe61b1bf062` |
| `audit_sha256` | `29b818f28dec3ebbe6a45747e7670a12bc9ec08e4b5d8289c652ac04adac9c81` |

---

## 3. Annual universe churn

| 年 | expected | observed | missing | (%) | 流出 obs/exp |
|---|---:|---:|---:|---:|---|
| 2012–2018 | — | — | 2–7 | 0.13–0.42 | 14/14 · 11/13 · 16/10 · 14/11 · 20/23 · 18/17 · **19/19** |
| **2019** | 1,747 | 1,827 | **1** | 0.06 | **16/15** |
| **2020** | 1,762 | 1,842 | **2** | 0.11 | **17/18** |
| **2021** | 1,773 | 1,870 | **0** | 0.00 | **15/15** |
| **2022** | 1,805 | 1,890 | **0** | 0.00 | **17/17** |
| **2023** | 1,821 | 1,917 | **0** | 0.00 | **8/8** |
| **2024** | 1,870 | 1,957 | **0** | 0.00 | **11/10** |
| **2025** | 1,933 | 1,965 | **1** | 0.05 | **7/8** |

**2019–2025 的連續 0 流出已消失**，且每年流出量與獨立參照吻合。2018 的 110 也回到 19（與參照的 19 一致）。

---

## 4. `2018-12-28` cluster regression

**群聚已消失** —— 新 canonical source 的終止日群聚中不再有 2018-12-28。

所有殘餘群聚的 `unexplained_terminations_on_date` 皆為 **0**：

| 日期 | n | unexplained |
|---|---:|---:|
| 2018-09-17 | 6 | **0** |
| 2005-09-09 / 2005-07-04 | 3 | **0** |
| 2020-04-06 / 2024-11-18 / 2021-01-05 … | 2 | **0** |

**未以「90 檔全部回來」作為通過條件** —— 判定由 C1/C2/backstop 對資料計算得出。

---

## 5. Security-level completeness

**無法解釋的提前終止：56 → 2。**

剩餘兩筆皆在 2019 之前，且間隔極短：

| 證券 | 最後價格 | 參照下市日 | 間隔 |
|---|---|---|---:|
| `3291` | 2016-09-26 | 2016-10-06 | 10 天 |
| `6159` | 2009-01-21 | 2009-02-06 | 16 天 |

兩者都在未重新匯出的時代，與 D-1 的存活者偏誤無關。

---

## 6. Known-case validation

參照下市日 ≥2019 者 **98 檔，98/98 的價格序列延續到其實際離場**：

| 證券 | 參照下市日 | 新來源最後價格 |
|---|---|---|
| `1704` | 2019-01-30 | 2019-01-23 |
| `1262` | 2019-10-14 | 2019-10-07 |
| `1592` | 2022-01-27 | 2022-01-26 |
| `1258` | 2023-06-09 | 2023-06-08 |
| `1701` | 2024-09-02 | 2024-08-30 |
| `1333` | 2020-11-17 | 2020-04-06（2020-04-07 起停牌，已解釋） |

舊來源這些全部停在 2018-12-28。

---

## 7. 舊來源反向控制

固定為 fixture（`tests/fixtures/d1_contaminated/`），由**同一份程式**（`rebuild_audit_new_source.py old`）產生：

```
OLD  admissible=False
     C1: 7 年零流出（2019 ref=15 … 2025 ref=8）
     C2: 2018-12-28 (n=90, unexplained=54)
     backstop: FAIL — 7 個零流出年份
NEW  admissible=True — 15 years show ordinary entry/exit churn
     backstop: PASS
```

---

## 8. 🔴 兩處判準缺陷（已修正，且修正後仍失敗於舊資料）

**這兩處都是規則本身的缺陷，不是為了讓新資料通過而放寬。**

**(a) C2 原本比對「群聚日當天的下市數」。** 下市日在定義上**晚於**最後交易日 —— 常為隔日，長期停牌後可達數月。所以「當天無下市」是乾淨資料的常態。實測誤報：`2018-09-17` 六檔最後交易日 09-17、`delisted` 狀態 09-18 生效、正式下市 2018-10-01，完全自洽卻被判 FAIL。**舊資料當時也誤報，只是被 `2018-12-28` 的真陽性掩蓋。** 改用與 security-level 相同的 `explained` 判準。

**(b) backstop 的「交易到年末後消失 > 0 即 FAIL」在任何真實 corpus 上都不可能通過。** 實測 16 筆**全部**有參照下市日落在其下一個 session 上或數日內（`8705` 最後 2012-12-25 → 下市 2013-01-01；`6211` 最後 2015-12-31 → 下市 2016-01-04），且每年至少一筆。降為報告項，只保留 structural 的「零流出年份」為 gate。

**修正後舊 corpus 仍然 FAIL**（C2 unexplained=54、backstop 七個零流出年份）。

**另有一個我自己的 bug 被反向控制抓到：** `explained()` 第一版寫成「下市日 ≥ 最後價格日就算解釋」，導致舊 corpus 回報 0 個無法解釋的終止。**下市日遠晚於最後交易日正是矛盾本身。** 已改為在**第一個缺席 session** 判定，與 O-B 語義一致。

---

## 9. 真實資料 adapter 驗證（未跑決策層）

| 項目 | 結果 |
|---|---|
| price source admissibility | ✅ `includes_delisted=True`、未 quarantined |
| PIT（as_of = 前一完成 session） | ✅ 2020-06-30 → `as_of` 2020-06-29；日曆截斷正確 |
| market-state guard（**持倉**） | ✅ 20 檔持倉，`CURRENT` 20 / stale 0 / unexplained 0 |
| corporate-action exposure guard | ✅ 46,275 事件（1,337 不可重建），無持倉暴露 |
| source attestation | ✅ |
| `config_hash` | `27fee343…d13f03` |
| `state_hash` | `56d42ca0…81f13be` |
| route invariants | ✅ G14-4 / B-17 / B-19 各 0 violation；import-time foreign mutations 0；registered overrides 0 |
| B-20 parity mechanics | ✅ 1 route pair、7 欄、5 層（**未在真實資料上跑決策**） |

**決策層未執行** —— `run_decision` 會產生選股名單，本輪禁止。

---

## 10. 🔴 新開 O-F：狀態來源的下市涵蓋缺口

全母體診斷（as-of 2020-06-29，1,838 檔，**僅診斷不強制**）：

| 成因 | 檔數 |
|---|---:|
| 可解釋 | 1,819 |
| **完全沒有狀態紀錄** | **12**（`2475`、`3431`、`3452`、`3519`、`3579`、`4415` …） |
| O-E-1 同日規則不可解釋 | 7（`1333`、`1902`、`2499`、`3562` …） |

`暫停交易` 記錄停牌，**不涵蓋所有下市**。這些名字的下市日只存在於 `公司資料.xlsx`，而那是當期快照（O-E 下 `NOT_PIT_SAFE`），不能當 runtime 狀態來源。

**只有 B0 實際持有時才會 abort**（設計如此，非缺陷），但**擋住 S-3b 真實資料 E2E**。需要一份 PIT-safe 的下市/終止交易狀態來源，或對 O-E-1 同日規則另行裁決。**本輪不自行裁決。**

---

## 11. 產出

| 檔案 | 內容 |
|---|---|
| `research/d1_price_universe/ingest_new_price_export.py` | 盤點 + 指紋 |
| `research/d1_price_universe/rebuild_audit_new_source.py` | 稽核（`new` / `old` 同一程式） |
| `research/d1_price_universe/register_price_source.py` | D1-7 contract + B-21 provenance |
| `research/d1_price_universe/validate_realdata_adapter.py` | 真實資料 adapter 驗證 |
| `tests/fixtures/d1_contaminated/` | 反向控制 fixture |
| `data/b0/price_universe_audit.csv` · `_clusters.csv` · `_churn.csv` · `price_2019plus_new.parquet` | verifier 輸入 |

**變更登錄於 master prereg §11：C-39。** `spec_sha256` (v1.9) = `5055b1e56b0fc7f4dde98f2aab7f99e9760215c94b11d6e263f0ed4fd4cd0f05`。
