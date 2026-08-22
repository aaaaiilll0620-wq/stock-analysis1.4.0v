# -*- coding: utf-8 -*-
"""Scan an extracted-text file for holder-consideration clause candidates."""
import sys, re, json, os

STOCK_PAT = [r"換股比例", r"換發比例", r"換發本公司", r"換發新股", r"股份轉換比例",
             r"發行新股.{0,20}對價", r"以.{0,10}股.{0,20}換發", r"每一股.{0,30}股",
             r"換發.{0,10}普通股", r"轉換為.{0,12}股份", r"對價.{0,20}普通股"]
CASH_PAT  = [r"現金對價", r"現金為對價", r"以現金.{0,10}(支付|對價|收購)", r"每股.{0,6}新台幣.{0,12}元",
             r"現金收購", r"收購價格", r"合併對價.{0,20}現金", r"股東.{0,20}取得現金",
             r"價金", r"現金.{0,6}給付.{0,10}股東"]
LINK_PAT  = [r"股份轉換", r"合併契約", r"合併基準日", r"股份轉換基準日", r"消滅公司", r"存續公司",
             r"投資控股", r"簡易合併", r"公開收購"]

def scan(path, window=160):
    t = open(path, encoding="utf-8", errors="replace").read()
    pages = t.split("\x0c")
    hits = {"stock": [], "cash": [], "link": []}
    for i, pg in enumerate(pages, 1):
        flat = re.sub(r"\s+", "", pg)
        for tag, pats in (("stock", STOCK_PAT), ("cash", CASH_PAT), ("link", LINK_PAT)):
            for p in pats:
                for m in re.finditer(p, flat):
                    a = max(0, m.start()-window); b = min(len(flat), m.end()+window)
                    hits[tag].append({"page": i, "pattern": p, "excerpt": flat[a:b]})
    return hits

if __name__ == "__main__":
    h = scan(sys.argv[1])
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for tag in ("stock", "cash", "link"):
        seen = set(); out = []
        for x in h[tag]:
            k = (x["page"], x["excerpt"][:60])
            if k in seen: continue
            seen.add(k); out.append(x)
        print("###", tag, len(h[tag]), "raw /", len(out), "uniq")
        for x in out[:lim]:
            print("  p%d [%s] %s" % (x["page"], x["pattern"], x["excerpt"]))
