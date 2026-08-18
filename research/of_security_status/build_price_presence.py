"""O-F - session-level price-presence index over the D-1 canonical corpus.

O-F asks whether a filed status accounts for a *missing session*. Answering that
needs presence per (security, session), which the D-1 coverage artefact does not
carry: it stores first/last/years only.

Composition is the SAME vintage boundary D-1 froze -- <=2018 from the existing
yearly cache, >=2019 from the 20260817 re-export -- so this index and the
registered price source describe one corpus, not two.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import glob
import io
import os
import sys
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

OLD_CACHE = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
NEW_DIR = os.path.join(REPO, "tej_exports", "DataExport0806",
                       "個股股價、本益比2004-20260817")
OUT = os.path.join(REPO, "data", "b0", "price_presence.parquet")
VINTAGE_BOUNDARY = "2019-01-01"


def d8(v):
    s = str(v).strip().split(".")[0]
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def legacy_rows():
    out = []
    for f in sorted(glob.glob(os.path.join(OLD_CACHE, "*.parquet"))):
        df = pd.read_parquet(f, columns=["stock_id", "date"])
        if df.empty:
            continue
        df["stock_id"] = df["stock_id"].astype(str)
        df["date"] = df["date"].astype(str)
        out.append(df[df["date"] < VINTAGE_BOUNDARY])
    return out


def reexport_rows():
    out = []
    for z in sorted(glob.glob(os.path.join(NEW_DIR, "*.zip"))):
        zf = zipfile.ZipFile(z)
        for name in zf.namelist():
            txt = zf.read(name).decode("utf-16")
            df = pd.read_csv(io.StringIO(txt), sep="\t",
                             usecols=["證券代碼", "年月日"], dtype=str)
            df = pd.DataFrame({
                "stock_id": df["證券代碼"].str.split().str[0],
                "date": df["年月日"].map(d8)})
            df = df.dropna()
            out.append(df[df["date"] >= VINTAGE_BOUNDARY])
    return out


def main():
    frames = legacy_rows() + reexport_rows()
    df = pd.concat(frames, ignore_index=True).drop_duplicates()
    df = df.sort_values(["stock_id", "date"], ignore_index=True)
    df["stock_id"] = df["stock_id"].astype("category")
    df.to_parquet(OUT, index=False)
    print(f"rows       : {len(df):,}")
    print(f"securities : {df['stock_id'].nunique():,}")
    print(f"coverage   : {df['date'].min()} .. {df['date'].max()}")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
