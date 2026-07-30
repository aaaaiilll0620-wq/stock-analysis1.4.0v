# -*- coding: utf-8 -*-
"""face_audit.py — 五個面的全面體檢 (L4 第一步:先看定義層,不談權重)
================================================================================
量的對象是**生產真身五面分數** (realbody_scores,經 L3 換身),不是替身因子。

問的問題,對**五個面一視同仁**(好的面也要查有沒有隱含偏誤):

  §1 量尺 —— 這個面在橫斷面上「分得開」嗎?
      分桶式絕對分數 (if/elif 加減分) 在多頭會集體衝頂、空頭會集體塌底,
      橫斷面離散度隨 regime 漂移 → 同一個 IC 在不同市況量到的不是同一件事。
      指標:相異值比例、Top-20% 並列率、逐月標準差、多空離散度比。

  §2 效力 —— IC / t、分時代、分多空、五分位平均 vs 中位、右尾機率。
      平均與中位背離 = 效果集中在右尾 (少數大獎),不是廣泛有效。

  §3 隱含偏誤 —— 對「好的面」(基本面/估值) 特別要查:
      (a) 覆蓋率是否隨時間變化 (2019 前後斷層 → IC 只在某段可信)
      (b) IC 是否集中在單一時代 (換一段就沒了)
      (c) 是不是流動性/規模的代理 (ADV 五分位內中性化後還在不在)
      (d) 是不是產業押注 (產業內中性化後還在不在)

  §4 合成層 —— real_composite 不是五面的靜態加權:
      advisor 上面還疊了 regime 乘數 (空頭降動能/技術) 與 per-stock 動態權重
      (強勢多頭排列 → 估值權重砍 60% 轉給動能/籌碼)。
      本節量殘差 = real_composite − Σw·face,反推這兩層實際動了多少、動在誰身上,
      並用留一法量每個面對合成 IC 的邊際貢獻。

用法:python scripts/face_audit.py            # 全部
      python scripts/face_audit.py --part 1  # 只跑某節
================================================================================
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from lab_paths import RET_COL, REAL_COMP_COL, REAL_FACES, load_real_panel   # noqa: E402
from regime_switch_lab import build_regime, ERAS                            # noqa: E402

FACE_LABEL = {"f_fund": "基本面(.31)", "f_val": "估值(.08)", "f_tech": "技術(.19)",
              "f_mom": "動能(.27)", "f_whale": "籌碼(.15)"}
W = {"f_fund": 0.31, "f_val": 0.08, "f_tech": 0.19, "f_mom": 0.27, "f_whale": 0.15}
COLS = REAL_FACES + [REAL_COMP_COL, "c2"]
LABEL = {**FACE_LABEL, REAL_COMP_COL: "真身綜合分", "c2": "c2 (對照組)"}


def tstat(x) -> float:
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def ic_series(df: pd.DataFrame, col: str, min_n: int = 30) -> pd.Series:
    out = {}
    for a, g in df.groupby("as_of"):
        m = g[col].notna() & g[RET_COL].notna()
        if m.sum() >= min_n:
            out[a] = g.loc[m, col].rank().corr(g.loc[m, RET_COL].rank())
    return pd.Series(out).dropna()


def load() -> pd.DataFrame:
    d = load_real_panel(adv_floor=2e7)
    reg = build_regime()
    rm = dict(zip(reg["date"], reg["bear"])); rd = sorted(rm)
    import bisect
    def bear_at(a):
        i = bisect.bisect_right(rd, str(a)) - 1
        return bool(rm[rd[i]]) if i >= 0 else False
    d["bear"] = d["as_of"].astype(str).map({a: bear_at(a) for a in d["as_of"].unique()})
    return d


# =====================================================================
# §1 量尺
# =====================================================================
def part1(d: pd.DataFrame):
    print("=" * 100)
    print("§1 量尺 —— 這個面在橫斷面上分得開嗎? (分桶式絕對分數的通病:集體衝頂/塌底)")
    print("=" * 100)
    print(f"{'面':<14}{'相異值/檔數':>12}{'Top20%並列率':>14}{'橫斷面std':>11}"
          f"{'多頭std':>9}{'空頭std':>9}{'空/多':>8}")
    for c in COLS:
        uniq, tie, sd, sd_bull, sd_bear = [], [], [], [], []
        for a, g in d.groupby("as_of"):
            v = g[c].dropna()
            if len(v) < 30:
                continue
            uniq.append(v.nunique() / len(v))
            k = max(1, int(len(v) * 0.20))
            thr = v.nlargest(k).min()
            # 並列率:恰好等於門檻值的檔數 ÷ 應取檔數 → 1.0 表示前 20% 全是同分,排序等於隨機
            tie.append((v == thr).sum() / k)
            sd.append(v.std(ddof=1))
            (sd_bear if bool(g["bear"].iloc[0]) else sd_bull).append(v.std(ddof=1))
        r = np.nanmean(sd_bear) / np.nanmean(sd_bull) if sd_bull else np.nan
        print(f"{LABEL[c]:<14}{np.nanmean(uniq):>12.3f}{np.nanmean(tie):>14.2f}"
              f"{np.nanmean(sd):>11.2f}{np.nanmean(sd_bull):>9.2f}{np.nanmean(sd_bear):>9.2f}{r:>8.2f}")
    print("\n判讀:相異值比例低 + Top20%並列率高 → 這個面的前段名單有大量同分,")
    print("      誰進 top20% 由 nlargest 的穩定排序(等於股號順序)決定,不是由分數決定。")
    print("      空/多 std 比遠離 1.0 → 離散度隨市況漂移,跨時代的 IC 不是同一把尺量的。")


# =====================================================================
# §2 效力
# =====================================================================
def part2(d: pd.DataFrame):
    print("\n" + "=" * 100)
    print("§2 效力 —— IC / 分時代 / 分多空")
    print("=" * 100)
    print(f"{'面':<14}{'全期IC':>9}{'t':>7}{'多頭IC':>9}{'t':>7}{'空頭IC':>9}{'t':>7}"
          + "".join(f"{nm[:9]:>10}" for nm, _, _ in ERAS))
    for c in COLS:
        s = ic_series(d, c)
        sb = ic_series(d[~d["bear"]], c); sr = ic_series(d[d["bear"]], c)
        row = (f"{LABEL[c]:<14}{s.mean():>9.4f}{tstat(s.values):>7.2f}"
               f"{sb.mean():>9.4f}{tstat(sb.values):>7.2f}{sr.mean():>9.4f}{tstat(sr.values):>7.2f}")
        for nm, st, en in ERAS:
            sub = s[(s.index.astype(str) >= st) & (s.index.astype(str) <= en)]
            row += f"{(sub.mean() if len(sub) else np.nan):>10.4f}"
        print(row)

    print("\n五分位 (Q1=最低分, Q5=最高分):平均 vs 中位背離 = 效果只在右尾")
    print(f"{'面':<14}{'Q1均':>8}{'Q5均':>8}{'Q5−Q1均':>10}{'Q1中':>8}{'Q5中':>8}{'Q5−Q1中':>10}"
          f"{'Q1的>20%機率':>13}{'Q5的>20%機率':>13}")
    for c in COLS:
        qm, qmed, qhit = {}, {}, {}
        for a, g in d.groupby("as_of"):
            g = g.dropna(subset=[c, RET_COL])
            if len(g) < 50:
                continue
            q = pd.qcut(g[c].rank(method="first"), 5, labels=False)
            for i in (0, 4):
                v = g.loc[q == i, RET_COL]
                qm.setdefault(i, []).append(v.mean())
                qmed.setdefault(i, []).append(v.median())
                qhit.setdefault(i, []).append((v > 20).mean() * 100)
        print(f"{LABEL[c]:<14}{np.nanmean(qm[0]):>8.3f}{np.nanmean(qm[4]):>8.3f}"
              f"{np.nanmean(qm[4])-np.nanmean(qm[0]):>10.3f}"
              f"{np.nanmean(qmed[0]):>8.3f}{np.nanmean(qmed[4]):>8.3f}"
              f"{np.nanmean(qmed[4])-np.nanmean(qmed[0]):>10.3f}"
              f"{np.nanmean(qhit[0]):>13.2f}{np.nanmean(qhit[4]):>13.2f}")


# =====================================================================
# §3 隱含偏誤 (好的面也要查)
# =====================================================================
def _neutral_rank(d: pd.DataFrame, col: str, by: str) -> pd.Series:
    """在 (as_of × by) 群組內取百分位 → 抽掉 by 這個維度的解釋力。"""
    return d.groupby(["as_of", by])[col].rank(pct=True)


def part3(d: pd.DataFrame):
    print("\n" + "=" * 100)
    print("§3 隱含偏誤 —— IC 是真的,還是流動性/產業/單一時代的代理?")
    print("=" * 100)

    d = d.copy()
    d["_adv_q"] = d.groupby("as_of")["adv20"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    d["_ind"] = d["tej_ind_name"].fillna("未分類")

    print(f"{'面':<14}{'原始IC':>9}{'t':>7}{'ADV五分位內':>12}{'t':>7}{'產業內':>9}{'t':>7}"
          f"{'最大時代貢獻':>13}{'去掉它之後IC':>13}")
    for c in COLS:
        s = ic_series(d, c)
        d["_na"] = _neutral_rank(d, c, "_adv_q")
        d["_ni"] = _neutral_rank(d, c, "_ind")
        sa = ic_series(d, "_na"); si = ic_series(d, "_ni")
        # 哪個時代貢獻最大,拿掉之後還剩多少
        best, best_v, rest = None, -9e9, np.nan
        for nm, st, en in ERAS:
            m = (s.index.astype(str) >= st) & (s.index.astype(str) <= en)
            if m.sum() == 0:
                continue
            contrib = s[m].sum() / len(s)          # 該時代對全期均值的貢獻量
            if contrib > best_v:
                best, best_v, rest = nm, contrib, s[~m].mean()
        print(f"{LABEL[c]:<14}{s.mean():>9.4f}{tstat(s.values):>7.2f}"
              f"{sa.mean():>12.4f}{tstat(sa.values):>7.2f}{si.mean():>9.4f}{tstat(si.values):>7.2f}"
              f"{best[:11]:>13}{rest:>13.4f}")

    print("\n覆蓋率 (該面非 NaN 比例) 逐時代 —— 斷層代表該段的 IC 是在不同母體上量的:")
    print(f"{'面':<14}" + "".join(f"{nm[:10]:>12}" for nm, _, _ in ERAS))
    for c in COLS:
        row = f"{LABEL[c]:<14}"
        for nm, st, en in ERAS:
            sub = d[(d["as_of"] >= st) & (d["as_of"] <= en)]
            row += f"{(sub[c].notna().mean()*100 if len(sub) else np.nan):>12.1f}"
        print(row)


# =====================================================================
# §4 合成層
# =====================================================================
def part4(d: pd.DataFrame):
    print("\n" + "=" * 100)
    print("§4 合成層 —— real_composite 不是五面的靜態加權")
    print("=" * 100)
    d = d.copy()
    d["_static"] = sum(W[f] * d[f] for f in REAL_FACES)
    d["_resid"] = d[REAL_COMP_COL] - d["_static"]

    print(f"靜態加權重建 vs 真身綜合分:殘差 平均 {d['_resid'].mean():+.2f}、"
          f"中位 {d['_resid'].median():+.2f}、std {d['_resid'].std():.2f}")
    print(f"  |殘差| > 1 分的比例: {(d['_resid'].abs() > 1).mean()*100:.1f}%    "
          f"> 5 分: {(d['_resid'].abs() > 5).mean()*100:.1f}%")
    print("  (殘差來源:advisor 的 regime 乘數 + per-stock 動態權重 + 洗盤加分;"
          "非 0 表示那兩層有在動)")
    corr = d[["_resid"] + REAL_FACES].corr().loc["_resid", REAL_FACES]
    print("  殘差與各面的相關 → 看動態權重把分數轉給了誰:")
    print("    " + "  ".join(f"{FACE_LABEL[f]} {corr[f]:+.3f}" for f in REAL_FACES))

    # 殘差為正 (被動態權重加分) 的那群,未來報酬如何
    hi = d["_resid"] > d["_resid"].quantile(0.9)
    lo = d["_resid"] < d["_resid"].quantile(0.1)
    print(f"\n  殘差前10% (被加最多分) 的未來報酬 平均 {d.loc[hi, RET_COL].mean():+.3f}% / "
          f"中位 {d.loc[hi, RET_COL].median():+.3f}%")
    print(f"  殘差後10% (被扣最多分) 的未來報酬 平均 {d.loc[lo, RET_COL].mean():+.3f}% / "
          f"中位 {d.loc[lo, RET_COL].median():+.3f}%")
    print(f"  母體平均 {d[RET_COL].mean():+.3f}% / 中位 {d[RET_COL].median():+.3f}%")

    print("\n留一法 —— 拿掉某個面之後,合成分的 IC 變多少 (正的增量 = 該面有貢獻)")
    base = ic_series(d, "_static")
    print(f"{'配置':<20}{'IC':>9}{'t':>7}{'vs 全五面':>11}")
    print(f"{'全五面 (靜態加權)':<20}{base.mean():>9.4f}{tstat(base.values):>7.2f}{'':>11}")
    for f in REAL_FACES:
        rest = [x for x in REAL_FACES if x != f]
        wsum = sum(W[x] for x in rest)
        d["_loo"] = sum(W[x] * d[x] for x in rest) / wsum
        s = ic_series(d, "_loo")
        print(f"{'去掉 ' + FACE_LABEL[f]:<20}{s.mean():>9.4f}{tstat(s.values):>7.2f}"
              f"{s.mean() - base.mean():>+11.4f}")
    print("\n判讀:『去掉它之後 IC 反而變高』= 該面對合成是淨拖累,權重再怎麼調都救不了定義。")


# =====================================================================
# §5 名目權重 vs 有效權重
# =====================================================================
def part5(d: pd.DataFrame):
    print("\n" + "=" * 100)
    print("§5 名目權重 vs 有效權重 —— 五個面的量尺不同,加權相加時名目權重不等於實際影響力")
    print("=" * 100)
    d = d.copy()
    d["_static"] = sum(W[f] * d[f] for f in REAL_FACES)

    # 逐月做變異數分解:face i 對合成分橫斷面變異的貢獻 = w_i·cov(f_i, composite)/var(composite)
    share = {f: [] for f in REAL_FACES}
    for a, g in d.groupby("as_of"):
        g = g.dropna(subset=REAL_FACES + ["_static"])
        if len(g) < 50:
            continue
        var = g["_static"].var(ddof=1)
        if var <= 0:
            continue
        for f in REAL_FACES:
            share[f].append(W[f] * g[f].cov(g["_static"]) / var)

    print(f"{'面':<14}{'名目權重':>9}{'橫斷面std':>11}{'有效權重':>10}{'名目→有效':>12}")
    for f in REAL_FACES:
        eff = np.nanmean(share[f])
        print(f"{FACE_LABEL[f]:<14}{W[f]:>9.2f}{d[f].std():>11.2f}{eff:>10.2f}"
              f"{(eff - W[f]):>+12.2f}")
    print(f"{'合計':<14}{sum(W.values()):>9.2f}{'':>11}"
          f"{sum(np.nanmean(share[f]) for f in REAL_FACES):>10.2f}")
    print("\n判讀:有效權重 = 該面實際貢獻多少橫斷面排序變異。與名目權重的落差來自")
    print("      (a) 各面 std 不同(估值 std 29 vs 基本面 15) (b) 面與面之間的相關。")
    print("      要讓『調權重』這件事有意義,五個面得先在同一把尺上(例如逐月橫斷面百分位)。")


# =====================================================================
# §6 機制診斷 (⚠ in-sample,不是結論)
# =====================================================================
def part6(d: pd.DataFrame):
    print("\n" + "=" * 100)
    print("§6 機制診斷 —— 把 §1/§5 指出的兩個病分開治,各能拿回多少?")
    print("⚠ 這是 in-sample 分解,目的是確認『病因是哪一個』,**不是**可以拿去用的配方。")
    print("   確認性檢定(walk-forward + 虛無對照)見 docs/預註冊_FaceRedesign.md。")
    print("=" * 100)
    d = d.copy()
    g = d.groupby("as_of")
    for f in REAL_FACES:
        d[f + "_p"] = g[f].transform(lambda s: s.rank(pct=True) * 100)

    variants = {
        "現行:靜態加權 (原量尺)": sum(W[f] * d[f] for f in REAL_FACES),
        "A 只換量尺 (逐月百分位,權重不動)": sum(W[f] * d[f + "_p"] for f in REAL_FACES),
        "B 量尺 + 拿掉兩個負面 (技術/籌碼)":
            sum(W[f] * d[f + "_p"] for f in ("f_fund", "f_val", "f_mom")) / (0.31 + 0.08 + 0.27),
        "C 量尺 + 兩個負面翻符號":
            (0.31 * d["f_fund_p"] + 0.08 * d["f_val_p"] + 0.27 * d["f_mom_p"]
             + 0.19 * (100 - d["f_tech_p"]) + 0.15 * (100 - d["f_whale_p"])),
        "D 量尺 + 只留兩個顯著正面 (基本面+估值)":
            (0.31 * d["f_fund_p"] + 0.08 * d["f_val_p"]) / 0.39,
        "E 對照:c2 (4 腿純橫斷面百分位)": d["c2"],
    }
    print(f"{'配置':<34}{'IC':>9}{'t':>7}{'產業內IC':>10}{'t':>7}{'2022空頭IC':>11}")
    d["_ind"] = d["tej_ind_name"].fillna("未分類")
    for name, s in variants.items():
        d["_v"] = s
        ic = ic_series(d, "_v")
        d["_vn"] = d.groupby(["as_of", "_ind"])["_v"].rank(pct=True)
        icn = ic_series(d, "_vn")
        m22 = (ic.index.astype(str) >= "2022-01-01") & (ic.index.astype(str) <= "2022-12-31")
        print(f"{name:<34}{ic.mean():>9.4f}{tstat(ic.values):>7.2f}"
              f"{icn.mean():>10.4f}{tstat(icn.values):>7.2f}{ic[m22].mean():>11.4f}")
    print("\n判讀:A vs 現行 = 量尺病治好能拿回多少;B/C vs A = 定義病(負面)還剩多少;")
    print("      D = 只留下已驗證有效的兩面;E 是同一母體上已知最強的排序器,當上限參考。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=str, default="all")
    args = ap.parse_args()
    d = load()
    print(f"真身面板 {len(d)} 列 / {d['as_of'].nunique()} 月 "
          f"(多頭 {(~d['bear']).groupby(d['as_of']).first().sum()} 月 / "
          f"空頭 {d['bear'].groupby(d['as_of']).first().sum()} 月)\n")
    for p, fn in [("1", part1), ("2", part2), ("3", part3), ("4", part4), ("5", part5), ("6", part6)]:
        if args.part in ("all", p):
            fn(d)


if __name__ == "__main__":
    main()
