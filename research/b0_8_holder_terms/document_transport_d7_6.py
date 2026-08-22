# -*- coding: utf-8 -*-
"""Download MOPS t57sb01 documents (WSL python) preserving raw bytes + provenance."""
import urllib.request, urllib.parse, re, os, sys, json, hashlib, time
URL = "https://doc.twse.com.tw/server-java/t57sb01"
H = {"User-Agent": "Mozilla/5.0", "Referer": URL,
     "Content-Type": "application/x-www-form-urlencoded"}
RAW = "/mnt/c/dev/Project 1/artifacts/b0_8_holder_terms/d7_6_docs_raw"

def step9(kind, co, filename, tries=8):
    """Return (url, None) for the HTML-indirection flow, ("INLINE", bytes) when the
    server streams the file body straight back (older .doc/.xls attachments)."""
    body = urllib.parse.urlencode({"step": "9", "kind": kind, "co_id": co,
                                   "filename": filename, "id": "", "key": ""}).encode()
    last = None
    for i in range(tries):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(URL, data=body, headers=H),
                                         timeout=120).read()
        except Exception as e:
            last = "%s:%s" % (type(e).__name__, e); time.sleep(2 + 2 * i); continue
        t = raw.decode("big5", "replace")
        m = re.search(r"href='([^']+)'", t)
        if m and m.group(1).startswith("/"):
            return "https://doc.twse.com.tw" + m.group(1), None
        if not t.lstrip().lower().startswith("<html"):
            return "INLINE", raw          # server returned the document body itself
        last = "NO_DOCUMENT_LINK"; time.sleep(2 + 2 * i)
    return None, last

def download(kind, co, filename):
    os.makedirs(RAW, exist_ok=True)
    url, err = step9(kind, co, filename)
    if not url:
        return {"filename": filename, "state": "RETRIEVAL_UNRESOLVED", "error": err}
    if url == "INLINE":
        b = err
        p = os.path.join(RAW, filename)
        open(p, "wb").write(b)
        return {"filename": filename, "state": "ACQUIRED",
                "locator": URL + " [step=9 inline body] kind=%s co_id=%s filename=%s" % (kind, co, filename),
                "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "stored": p,
                "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    b = None
    for i in range(5):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": URL}), timeout=600).read()
            break
        except Exception as e:
            err = "%s:%s" % (type(e).__name__, e); time.sleep(3 + 3 * i)
    if b is None:
        return {"filename": filename, "state": "ACQUISITION_ERROR", "locator": url, "error": err}
    p = os.path.join(RAW, filename)
    open(p, "wb").write(b)
    return {"filename": filename, "state": "ACQUIRED", "locator": url, "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(), "stored": p,
            "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

if __name__ == "__main__":
    kind = sys.argv[1]
    for spec in sys.argv[2:]:
        co, fn = spec.split(":")
        print(json.dumps(download(kind, co, fn), ensure_ascii=False), flush=True)
