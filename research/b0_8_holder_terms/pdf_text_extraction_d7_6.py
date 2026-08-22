# -*- coding: utf-8 -*-
"""pypdf text extraction for an already-downloaded PDF (Windows python)."""
import sys, os, json
from pypdf import PdfReader
p = sys.argv[1]
rec = {"path": p}
try:
    rd = PdfReader(p)
    rec["pages"] = len(rd.pages)
    txt = []
    for pg in rd.pages:
        try: txt.append(pg.extract_text() or "")
        except Exception: txt.append("")
    rec["chars"] = sum(len(x) for x in txt)
    rec["pages_with_text"] = sum(1 for x in txt if len(x.strip()) > 20)
    rec["text_extractable"] = rec["pages_with_text"] >= max(1, rec["pages"] // 2)
    open(p + ".txt", "w", encoding="utf-8").write("\n\x0c\n".join(txt))
    rec["text_file"] = p + ".txt"
except Exception as e:
    rec["error"] = "%s:%s" % (type(e).__name__, e)
    rec["text_extractable"] = False
open(p + ".extract.json", "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False))
print(json.dumps({k: v for k, v in rec.items()}, ensure_ascii=False))
