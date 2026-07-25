"""
Squarified Treemap 版面計算 (純數學,無繪圖依賴)
================================================================================
把一組正值切成一堆長寬比盡量接近 1 的矩形,填滿指定畫布。演算法出自
Bruls, Huizing & van Wijk (2000) "Squarified Treemaps"。

為什麼自己寫:Altair/Vega-Lite 沒有 treemap mark,而本專案的雲端依賴是鎖版的
(numpy 1.26 / altair 5.3,曾因 numpy 2.x ABI 破壞在雲端 segfault),不值得為一張圖
引入 plotly。算完 x/x2/y/y2 後用 `mark_rect` 畫即可,零新依賴。

用法:
    rects = squarify([50, 30, 12, 8], width=100, height=60)
    # → [{'x':..,'y':..,'x2':..,'y2':..,'w':..,'h':..}, ...] 與輸入同順序
================================================================================
"""
from __future__ import annotations

from typing import Dict, List, Sequence

__all__ = ["squarify"]


def _normalize(sizes: Sequence[float], area: float) -> List[float]:
    """把原始值等比縮放成「總和 = 畫布面積」,之後每塊的面積就直接是它的值。"""
    total = float(sum(sizes))
    if total <= 0:
        return [0.0] * len(sizes)
    k = area / total
    return [float(s) * k for s in sizes]


def _layout_row(sizes: List[float], x: float, y: float, dy: float) -> List[Dict]:
    """一整排靠左直立排列 (共用寬度 = 排總面積 ÷ 可用高度)。"""
    width = sum(sizes) / dy if dy else 0.0
    out, cy = [], y
    for s in sizes:
        h = s / width if width else 0.0
        out.append({"x": x, "y": cy, "x2": x + width, "y2": cy + h, "w": width, "h": h})
        cy += h
    return out


def _layout_col(sizes: List[float], x: float, y: float, dx: float) -> List[Dict]:
    """一整列靠下水平排列 (共用高度 = 列總面積 ÷ 可用寬度)。"""
    height = sum(sizes) / dx if dx else 0.0
    out, cx = [], x
    for s in sizes:
        w = s / height if height else 0.0
        out.append({"x": cx, "y": y, "x2": cx + w, "y2": y + height, "w": w, "h": height})
        cx += w
    return out


def _layout(sizes: List[float], x: float, y: float, dx: float, dy: float) -> List[Dict]:
    """沿較短邊鋪一排 —— 這是 squarified 讓長寬比接近 1 的關鍵。"""
    return _layout_row(sizes, x, y, dy) if dx >= dy else _layout_col(sizes, x, y, dx)


def _leftover(sizes: List[float], x: float, y: float, dx: float, dy: float):
    """鋪完這一排後剩下的畫布 (x, y, dx, dy)。"""
    if dx >= dy:
        width = sum(sizes) / dy if dy else 0.0
        return x + width, y, dx - width, dy
    height = sum(sizes) / dx if dx else 0.0
    return x, y + height, dx, dy - height


def _worst(sizes: List[float], x: float, y: float, dx: float, dy: float) -> float:
    """這排裡最差的長寬比 (越接近 1 越好);任一邊為 0 視為無限差。"""
    worst = 1.0
    for r in _layout(sizes, x, y, dx, dy):
        w, h = r["w"], r["h"]
        if w <= 0 or h <= 0:
            return float("inf")
        worst = max(worst, w / h, h / w)
    return worst


def squarify(values: Sequence[float], width: float, height: float) -> List[Dict]:
    """
    把 values 切成填滿 width × height 的矩形清單,**與輸入同順序**回傳。

    · values 需為正值;<= 0 會被當成 0 面積 (仍會回一個零面積矩形佔位,保持索引對齊)。
    · 內部會先由大到小排序 (squarified 的前提),回傳前再還原成輸入順序。
    · 回傳每個 dict 含 x, y, x2, y2, w, h (左下原點座標系;Altair 的 y 軸方向不影響版面)。
    """
    n = len(values)
    if n == 0 or width <= 0 or height <= 0:
        return [{"x": 0.0, "y": 0.0, "x2": 0.0, "y2": 0.0, "w": 0.0, "h": 0.0}] * n

    # 只對正值排版;非正值最後補零面積矩形 (呼叫端通常已先過濾,這裡只是不炸)
    idx = [i for i in range(n) if values[i] > 0]
    zero = {"x": 0.0, "y": 0.0, "x2": 0.0, "y2": 0.0, "w": 0.0, "h": 0.0}
    if not idx:
        return [dict(zero) for _ in range(n)]

    idx.sort(key=lambda i: values[i], reverse=True)
    sizes = _normalize([values[i] for i in idx], width * height)

    rects: List[Dict] = []
    x, y, dx, dy = 0.0, 0.0, float(width), float(height)
    i = 0
    while i < len(sizes):
        if dx <= 0 or dy <= 0:                       # 畫布用盡 (數值退化) → 其餘給零面積
            rects.extend(dict(zero) for _ in range(len(sizes) - i))
            break
        row = [sizes[i]]
        j = i + 1
        # 一直把下一塊加進這排,直到長寬比開始變差為止
        while j < len(sizes) and _worst(row + [sizes[j]], x, y, dx, dy) <= _worst(row, x, y, dx, dy):
            row.append(sizes[j])
            j += 1
        rects.extend(_layout(row, x, y, dx, dy))
        x, y, dx, dy = _leftover(row, x, y, dx, dy)
        i = j

    out = [dict(zero) for _ in range(n)]
    for pos, i_orig in enumerate(idx):
        out[i_orig] = rects[pos]
    return out
