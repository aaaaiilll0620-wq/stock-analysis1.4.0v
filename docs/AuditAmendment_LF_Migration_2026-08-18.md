# 稽核修訂：CRLF → LF 正規化對既有 hash 紀錄的影響

**日期：** 2026-08-18
**依據：** M-3 裁決（2026-08-18）第 4 項；master preregistration v1.14
**機器可讀帳本：** `research/b0_registry/lf_migration_ledger.json`
**產生器：** `research/b0_registry/build_lf_migration_ledger.py`

---

## 1. 為什麼需要這份修訂

Repo & Provenance Finalization Closure 建立了 `.gitattributes`，把 **LF 定為本倉庫
的正規位元組表示法**。在此之前 `.gitattributes` 是 ABSENT，且有 150 個受版控檔案
在工作區漂移成 CRLF。

把它們還原成 committed 位元組改變了**原始位元組**，而 `sha256` 看的正是原始位元組。

因此有 **3 份 Frozen A 時期的研究 provenance 紀錄**、合計 **9 個 hash 欄位**，
其記載值是對 **CRLF 位元組形式**計算出來的，已不再等於磁碟上的檔案。

> **這不是漂移，是正規化。** 每一筆都經機械驗證：
> `sha256(現行位元組把 LF 換回 CRLF) == 記載的歷史值`。
> 兩值之間的差異因此**只有行尾**，沒有其他。

---

## 2. 裁決要求與本文件的處置

裁決明文：**不得靜默覆寫歷史 hash。**

因此：

| 動作 | 是否採行 |
|---|---|
| 直接把紀錄裡的舊 hash 改成新值 | ❌ **不採行** |
| 保留歷史值，並標示其為「歷史 CRLF 位元組指紋」 | ✅ 採行 |
| 以機器可讀帳本並列 historical / current 兩值 | ✅ 採行 |
| 對仍把歷史值當作現行值呈現的文件發出明示修訂 | ✅ **即本文件** |

---

## 3. 受影響的紀錄（3 份 / 9 筆）

以下紀錄中的 `sha256` 欄位，**應一律理解為「歷史 CRLF 位元組指紋」**，
而**不是**該檔案的現行 hash。現行值見帳本 `current_canonical_lf_sha256`。

### 3.1 `research/p0_r1_research_production_identity/preflight.json`（4 筆）

| 描述的檔案 | 歷史 CRLF 指紋 | 現行正規 LF hash |
|---|---|---|
| `core/score_store.py` | `58de00f7…` | `5b349127…` |
| `app.py` | `2eb834c3…` | `5e1bb182…` |
| `beat_0050/strategies/high52_lab.py` | `09fbe6ef…` | `03fdf377…` |
| `scripts/lab_paths.py` | `8cb132fc…` | `e06b823c…` |

### 3.2 `beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json`（3 筆）

| 描述的檔案 | 歷史 CRLF 指紋 | 現行正規 LF hash |
|---|---|---|
| `scripts/gate1_delta_ic_maxt.py` | `9bcb71ff…` | `8477089a…` |
| `scripts/build_gate1_provenance_overlay.py` | `49dd8711…` | `78c08cd5…` |
| `beat_0050/results/gate1/gate1_preflight.json` | `8429aeb6…` | `cf08ac82…` |

### 3.3 `gate2_preflight.json`（2 筆）

同一份裁決把此產物移到 gitignore 的產物根目錄
（`artifacts/gate2/gate2_preflight.json`），原路徑
`beat_0050/results/gate2/gate2_preflight.json` 已解除版控。

| 描述的檔案 | 歷史 CRLF 指紋 | 現行正規 LF hash |
|---|---|---|
| `beat_0050/results/gate1/GATE1_EXECUTION_MANIFEST.json` | `4ed3b2c9…` | `c2e99553…` |
| `beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json` | `7344424d…` | `5ed30f28…` |

---

## 4. 對 B0 Baseline Seal 的影響：**無**

`blocks_b0_baseline_seal: false`。

理由：**上述 9 個路徑，沒有任何一個是 B0 的消耗性輸入或 normative 實作模組。**
它們全部落在 master preregistration §1 已經降級為
*rationale / evidence / audit trail* 的 Frozen A 時期材料裡。

正規化之後 B0 身分已重新驗證，全數相符：

```
spec 文件              MATCH
normative modules      23 / 23 MATCH
derived artefacts      10 / 10 MATCH
upstream zips          14 / 14 MATCH
```

若日後有任何一個受影響路徑**變成** B0 的消耗性輸入或 normative 模組，
本豁免即失效，該項必須先重新產生紀錄再封存。

---

## 5. 不做的事

- **不重跑 gate1 / gate2 以重新產生紀錄。** 重跑會產生新的研究結果，
  而本輪禁止計算任何績效；為了修 hash 而重跑會把稽核問題換成更嚴重的問題。
- **不回退這些檔案的行尾。** 混合行尾政策會讓 `spec_sha256` 這類
  raw-byte 身分再次依賴平台，那正是 `.gitattributes` 要消除的東西。

---

## 6. 驗證方式

```bash
python research/b0_registry/build_lf_migration_ledger.py
python -m pytest -q tests/test_b0_lf_migration_ledger.py
```

產生器在任何一筆無法被證明為「僅行尾差異」時會 **abort**，不會寫出帳本。
