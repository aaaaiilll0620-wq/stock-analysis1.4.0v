# -*- coding: utf-8 -*-
"""Text extraction for legacy Word .doc (OLE/CFB) MOPS attachments.

Word 97-2003 stores its text piece table as UTF-16LE inside the WordDocument
stream; decoding the whole container as UTF-16LE and keeping the printable runs
recovers the document text without an external converter. This is a NATIVE text
route (the bytes are text, not an image) -- it is not OCR.
"""
import sys, re, json

RUN = re.compile(r"[一-鿿　-〿＀-￯0-9A-Za-z ，。、：；「」『』（）()%．\.\-/]{4,}")

def extract(path):
    b = open(path, "rb").read()
    runs = []
    for off in (0, 1):
        s = b[off:].decode("utf-16-le", "ignore")
        runs.extend(RUN.findall(s))
    seen, out = set(), []
    for r in runs:
        r = r.strip()
        if len(r) < 4 or r in seen: continue
        seen.add(r); out.append(r)
    return out

if __name__ == "__main__":
    p = sys.argv[1]
    out = extract(p)
    txt = "\n".join(out)
    open(p + ".txt", "w", encoding="utf-8").write(txt)
    print(json.dumps({"path": p, "runs": len(out), "chars": len(txt),
                      "text_extractable": len(txt) > 200, "native_text": True,
                      "text_file": p + ".txt"}, ensure_ascii=False))
