# 撤回記錄 · D7.2.1 對 6514 的向下修復

**狀態：** `WITHDRAWN 2026-09-03`（裁決人：使用者 `aaaai`；記錄人：本 session）
**適用範圍：** `6514` 一筆。D7.2.1 對其他 7 筆的向下修復**不受本撤回影響**。
**本文件不刪除任何既有 artefact。** D7.2.1 的 JSON 原樣保留，本撤回以引用生效。

---

## 一 · 被撤回的內容

`research/b0_8_holder_terms/holder_consideration_semantics_d7_2_1.json`：

```json
{"security_id": "6514", "prior": "CASH_LEG_PRESENT",
 "repaired": "CONSIDERATION_NOT_ESTABLISHED",
 "reason": "no authoritative holder-consideration clause resolved in bundle",
 "holder_cash": false, "holder_security": false, "tender_language": false}
```

該修復是 D7.2.1「Y2_defect / LEXICAL_TRANSACTION_VOCABULARY_OVERINCLUSION_DEFECT」
批次中 `removed_count: 8` 的其中一筆。

## 二 · 撤回理由：修復理由已被第一手文件證偽

修復理由是**「bundle 裡沒有解析出權威的持股人對價條款」**。該條款存在，
而且就在語料裡：

```
artifacts/b0_8_holder_terms/d7_6_docs_raw/2024_6514_20240619F05.pdf
sha256 778f048d5633f8ab3580a106...      5,302,156 bytes
6514 自身 2024-06-19 股東常會議事手冊所附雙語合併契約暨合併計畫
```

> 「本合併案將由UMT按每一股本公司普通股股份新台幣 53.80元支付合併對價」
>
> *"…shall be cancelled and cease to exist in consideration and exchange for the
> right to receive … **NTD53.80 in cash, without interest, per share** (the
> 'Per-Share Merger Consideration')."*

「in cash, without interest」且**無股票腿** ⇒ `holder_cash = true`、
`holder_security = false`。D7.2.1 那三個布林值全部相反。

## 三 · 同一批 B0.8 內部本來就有矛盾，本撤回是採信其中較強的一方

```
D7.6   deep_document_acquisition_d7_6.json
       6514: DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR = CONSIDERATION_ESTABLISHED
       linkage: 發行人自身 2024/06/19 股東常會 circular 與所附雙語合併契約暨合併計畫
       holder_cash: true, holder_security: false

D7.2.1 holder_consideration_semantics_d7_2_1.json
       6514: CONSIDERATION_NOT_ESTABLISHED
       holder_cash: false, holder_security: false
```

兩者**針對同一筆事件給出相反結論**。D7.6 指名了具體文書並讀到條款；
D7.2.1 給的是一句否定式的覆蓋陳述。第一手文件在檔案系統上，內容與 D7.6 一致。

## 四 · 為什麼會漏：不是條款不存在，是沒有人讀

`research/b0_8_holder_terms/disappearing_party_edoc_consideration_d7_6.json`：

```json
"6514": {"counterparty": "UMT", "disappearing": "芮特",
         "docs_on_edoc_surface": 113, "docs_scanned": 0,
         "result": "SOURCE_FAMILY_NOT_EXHAUSTED", "semantics": "UNKNOWN"}
```

**`docs_on_edoc_surface: 113`，`docs_scanned: 0`。** 那一族來源自己標記為
`SOURCE_FAMILY_NOT_EXHAUSTED`，而下游把它讀成了「未確立」。

⚠ **這是本撤回真正要留下的教訓：`NOT_EXHAUSTED`（沒查完）被當成
`NOT_ESTABLISHED`（不存在）。** 兩者在 B0.8 的下游被折疊成同一個
`UNKNOWN`，而 d8_1 的 `missing: ["consideration semantics"]` 讓它看起來像是
資料缺口，不像是工作缺口。凡是由 `SOURCE_FAMILY_NOT_EXHAUSTED` 導出的
`UNKNOWN`，都應該重新檢視。

## 五 · 撤回後的狀態

| | 撤回前 | 撤回後 |
|---|---|---|
| 6514 consideration semantics | `CONSIDERATION_NOT_ESTABLISHED` | `CASH_ONLY`（每股 NT$53.80） |
| `holder_cash` / `holder_security` | `false` / `false` | `true` / `false` |
| `HXA_CASH_SCOPE` | 22 筆（不含 6514） | 23 筆（含 6514），見 B1 §2.3(4) |
| 結算口徑 | —（fail closed） | HX-A/DOC，用文件對價 53.80 |

**未變更：** d8_1 的 158 筆逐事件 JSON、D7.2.1 對其他 7 筆的修復、
`4152` 的排除（其理由是兩份 artefact 對 MIXED 有未經裁決的分歧，
與本案的「沒查完」不同型），以及任何 reconstruction classification 的落盤資料。

## 六 · 未解決

本撤回**不**主張 6514 的 credit / payment date 已確立。語料索引有一份
2024-10-16「合併對價發放通知」（classed `CASH_CONSIDERATION_PAYMENT`），
但**本體未快取**。HX-A/DOC 不需要該日期（它在邊界日結算），所以這不擋 B1；
但若日後要以實際支付日建模，那份文書仍需取得。
