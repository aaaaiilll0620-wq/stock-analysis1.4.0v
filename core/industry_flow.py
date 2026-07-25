"""
法人資金流向產業 (Institutional Flow by Industry) — 想法2 B版,0 FinMind API
================================================================================
把「全市場每日三大法人淨買 (股數)」× 收盤價 換成金額,再依 TEJ 產業別聚合,得到
『各產業每日法人淨流入 (億元)』時間序列,供 app 畫可移動的資金流向圖。

資料源 (全部本機、0 FinMind API),歷史種子 ∪ 每日快照:
  · ~/tej_cache/institutional_flow/{stock_id}.parquet   —— TEJ 種子,2004-01-02 起全歷史
        法人淨買 (foreign_net/trust_net,單位=股)。
  · ~/tej_cache/price_valuation/{stock_id}.parquet      —— 同源收盤價 + 成交量 (股)。
  · ~/market_cache/institutional_flow_daily/{date}.parquet —— collector 每日 17:30 從
        證交所 T86 + 櫃買 3insti 收的全市場法人淨買 (接上 TEJ 種子的斷點,已實測一致)。
  · ~/market_cache/price_valuation_daily/{date}.parquet —— 同源全市場收盤價 + 成交量。
  · tej_exports/inbox_industry/Industry.xlsx           —— 代號→產業/子產業對照 (2436 檔)。

兩種量綱 (app 可切換):
  · 金額     淨流入 = foreign_net(股) × close ÷ 1e8  → 億元
  · 占成交額 淨流入 ÷ turnover × 100 → %。turnover = Trading_Volume(股) × close ÷ 1e8。
    金額口徑會被權值股單日爆量壓垮 (如晶圓代工單日 -1121 億),占比口徑天生同尺度。

雲端相容:tej_cache/market_cache 只在本機。故 build_snapshot() 把聚合結果落地成
  cloud_cache/IndustryFlow/{flow,members}.parquet,deploy 後雲端 App 直接讀 snapshot;
  本機若無 snapshot 則即時算 (compute_flow)。members 只留最近 N 日 (下鑽用,全歷史太大)。

已知限制:產業別是「當下的」分類表套到歷史 (TEJ Industry.xlsx 只有現任成分),已下市個股
  對不到產業會被丟掉。這是描述圖不是訊號,可接受;不要拿它回測。
================================================================================
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
CHIP_DIR = MARKET_CACHE / "institutional_flow_daily"
PRICE_DIR = MARKET_CACHE / "price_valuation_daily"

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
TEJ_CHIP_DIR = TEJ_CACHE / "institutional_flow"
TEJ_PRICE_DIR = TEJ_CACHE / "price_valuation"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDUSTRY_XLSX = _PROJECT_ROOT / "tej_exports" / "inbox_industry" / "Industry.xlsx"
SNAPSHOT = _PROJECT_ROOT / "cloud_cache" / "IndustryFlow" / "flow.parquet"
MEMBERS_SNAPSHOT = _PROJECT_ROOT / "cloud_cache" / "IndustryFlow" / "members.parquet"
# 代號→產業對照的 parquet 快照。存在的理由是雲端相容:下鑽成分股 (load_members) 需要這份對照,
# 若現場讀 Industry.xlsx 就會要求 openpyxl —— 而 requirements.txt 沒有它 (且雲端依賴是刻意鎖版的,
# 不為一張圖動)。改成 build 時把對照落地成 parquet,雲端只讀 parquet、完全不碰 Excel。
MAP_SNAPSHOT = _PROJECT_ROOT / "cloud_cache" / "IndustryFlow" / "industry_map.parquet"

# 逐日增量檔。為什麼不每天重寫整份快照:snapshot 要 commit 進 repo,而 parquet 無法 diff ——
# 每天重寫 13MB 就是每天一顆 13MB 的新 blob (一年 3GB+ 的 git 歷史)。改成基底檔不動、
# 每天只新增「那一天」的小檔 (flow ~10KB + members ~30KB),一年約 10MB。
# 這也與 collector 自己的 {date}.parquet 慣例一致。
DAILY_FLOW_DIR = _PROJECT_ROOT / "cloud_cache" / "IndustryFlow" / "daily_flow"
DAILY_MEMBERS_DIR = _PROJECT_ROOT / "cloud_cache" / "IndustryFlow" / "daily_members"

# 產業層級 → Industry.xlsx 欄名 (由粗到細)。子產業 = 散裝航運/貨櫃輪這種粒度 (265 類)。
LEVELS = {
    "子產業": "TEJ子產業_名稱",
    "產業":   "TEJ產業_名稱",
    "上市產業": "TSE產業_名稱",
}
DEFAULT_LEVEL = "子產業"

# snapshot 長格式欄位
_SNAP_COLS = ["date", "level", "industry", "foreign", "trust", "combined", "turnover", "n_stocks"]
_MEM_COLS = ["date", "stock_id", "foreign", "trust", "combined", "turnover"]
_FLOW_COLS = [c for c in _SNAP_COLS if c != "level"]


@lru_cache(maxsize=None)
def _industry_map(level: str) -> pd.Series:
    """
    代號(str) → 產業名(str)。優先讀 parquet 快照 (雲端只有這條路,不需要 openpyxl),
    無快照則回頭讀 Industry.xlsx (本機 build 時走這條),並去掉 TEJ 名稱前綴代碼
    (如 'M54B 貨櫃輪' → '貨櫃輪')。
    """
    if MAP_SNAPSHOT.exists():
        try:
            df = pd.read_parquet(MAP_SNAPSHOT)
            sub = df[df["level"] == level]
            if not sub.empty:
                return pd.Series(sub["industry"].values, index=sub["stock_id"].values)
        except Exception:
            pass
    return _industry_map_from_xlsx(level)


def _industry_map_from_xlsx(level: str) -> pd.Series:
    """從 Industry.xlsx 讀對照 (需 openpyxl,只在本機 build 時會走到)。"""
    col = LEVELS.get(level, LEVELS[DEFAULT_LEVEL])
    df = pd.read_excel(INDUSTRY_XLSX, usecols=["代號", col])
    sid = df["代號"].astype(str).str.strip()
    name = df[col].astype(str).str.replace(r"^\S+\s+", "", regex=True).str.strip()
    return pd.Series(name.values, index=sid.values)


def _industry_long(levels: List[str]) -> pd.DataFrame:
    """所有層級攤平成 stock_id, level, industry 長格式 (2436 × N 列),供 SQL join 聚合。
    **刻意直接讀 xlsx**:這是 build 路徑,若走 _industry_map 會讀到上一輪自己寫的 parquet 快照
    (循環依賴,分類表更新後永遠追不上)。"""
    frames = []
    for lv in levels:
        s = _industry_map_from_xlsx(lv)
        frames.append(pd.DataFrame({"stock_id": s.index, "level": lv, "industry": s.values}))
    out = pd.concat(frames, ignore_index=True)
    return out[out["industry"].notna() & (out["industry"].str.strip() != "")
               & (out["industry"] != "nan")].reset_index(drop=True)


def _globs(tej_dir: Path, daily_dir: Path, history: bool) -> List[str]:
    """要掃的 parquet glob (TEJ 全歷史種子 ∪ collector 每日快照);目錄不存在就跳過。"""
    out = []
    if history and tej_dir.exists() and any(tej_dir.glob("*.parquet")):
        out.append((tej_dir / "*.parquet").as_posix())
    if daily_dir.exists() and any(daily_dir.glob("*.parquet")):
        out.append((daily_dir / "*.parquet").as_posix())
    return out


def _dates_available() -> List[str]:
    """collector 每日快照中 chip 與 price 都有的交易日 (由舊到新);純供診斷/狀態顯示。"""
    chip = {Path(f).stem for f in glob.glob(str(CHIP_DIR / "*.parquet"))}
    price = {Path(f).stem for f in glob.glob(str(PRICE_DIR / "*.parquet"))}
    return sorted(chip & price)


def _connect(days: Optional[int] = None, start: Optional[str] = None, history: bool = True,
             on_dates: Optional[List[str]] = None):
    """
    建 duckdb 連線並把『每檔每日法人淨流入 + 成交額 (億元)』做成 TEMP TABLE `m`。
    來源檔數上萬 (TEJ 2300 檔 × 2 + 每日快照),故在 SQL 內 join/聚合,不把全歷史拉進 pandas。
    回傳 (con, n_rows);來源不存在 (如雲端) → (None, 0)。
    """
    chip_g = _globs(TEJ_CHIP_DIR, CHIP_DIR, history)
    px_g = _globs(TEJ_PRICE_DIR, PRICE_DIR, history)
    if not chip_g or not px_g:
        return None, 0

    import duckdb
    con = duckdb.connect()
    chip_list = ", ".join(f"'{g}'" for g in chip_g)
    px_list = ", ".join(f"'{g}'" for g in px_g)

    if days:
        d = con.execute(f"""
            SELECT DISTINCT CAST(date AS VARCHAR) AS date
            FROM read_parquet([{chip_list}], union_by_name=true)
            ORDER BY date DESC LIMIT {int(days)}
        """).df()
        if not d.empty:
            cut = str(d["date"].min())
            start = max(start, cut) if start else cut

    if on_dates:                            # 只算指定的幾天 (逐日增量用)
        _lst = ", ".join("'" + str(d).replace("'", "") + "'" for d in on_dates)
        where = f"AND CAST(date AS VARCHAR) IN ({_lst})"
    else:
        where = f"AND CAST(date AS VARCHAR) >= '{start}'" if start else ""
    # QUALIFY 去重:TEJ 種子與每日快照在接縫日 (2026-07-14) 會重疊,同 (股票,日) 只留一列。
    con.execute(f"""
        CREATE TEMP TABLE m AS
        WITH chip AS (
            SELECT CAST(stock_id AS VARCHAR) AS stock_id, CAST(date AS VARCHAR) AS date,
                   CAST(foreign_net AS DOUBLE) AS fn, CAST(trust_net AS DOUBLE) AS tn
            FROM read_parquet([{chip_list}], union_by_name=true)
            WHERE foreign_net IS NOT NULL {where}
            QUALIFY row_number() OVER (PARTITION BY stock_id, date ORDER BY fn) = 1
        ), px AS (
            SELECT CAST(stock_id AS VARCHAR) AS stock_id, CAST(date AS VARCHAR) AS date,
                   CAST(close AS DOUBLE) AS close,
                   CAST(COALESCE("Trading_Volume", 0) AS DOUBLE) AS vol
            FROM read_parquet([{px_list}], union_by_name=true)
            WHERE close > 0 {where}
            QUALIFY row_number() OVER (PARTITION BY stock_id, date ORDER BY close) = 1
        )
        SELECT c.date AS date, c.stock_id AS stock_id,
               c.fn * p.close / 1e8 AS "foreign",
               c.tn * p.close / 1e8 AS trust,
               p.vol * p.close / 1e8 AS turnover
        FROM chip c JOIN px p ON c.stock_id = p.stock_id AND c.date = p.date
    """)
    n = con.execute("SELECT count(*) FROM m").fetchone()[0]
    return con, int(n)


def compute_members(days: Optional[int] = None, start: Optional[str] = None,
                    history: bool = True) -> pd.DataFrame:
    """
    『每檔每日法人淨流入 + 成交額 (億元)』per-stock 長格式 (產業無關,下鑽用)。
    回傳欄:date, stock_id, foreign, trust, combined, turnover。來源不存在 → 空表。
    ⚠️ 全歷史約 800 萬列,呼叫時務必給 days/start 收斂範圍。
    """
    con, n = _connect(days, start, history)
    if con is None or n == 0:
        return pd.DataFrame(columns=_MEM_COLS)
    try:
        out = con.execute("""
            SELECT date, stock_id, "foreign", trust, "foreign" + trust AS combined, turnover
            FROM m ORDER BY date, stock_id
        """).df()
    finally:
        con.close()
    return out


def _aggregate(members: pd.DataFrame, level: str) -> pd.DataFrame:
    """per-stock members → 各產業每日淨流入 (依 level 對映產業名後 groupby);小範圍用。"""
    if members.empty:
        return pd.DataFrame(columns=_FLOW_COLS)
    m = members.copy()
    m["industry"] = m["stock_id"].map(_industry_map(level))
    m = m.dropna(subset=["industry"])
    if "turnover" not in m.columns:
        m["turnover"] = float("nan")
    g = (m.groupby(["date", "industry"])
           .agg(foreign=("foreign", "sum"), trust=("trust", "sum"),
                turnover=("turnover", "sum"), n_stocks=("stock_id", "size"))
           .reset_index())
    g["combined"] = g["foreign"] + g["trust"]
    return (g[_FLOW_COLS]
            .sort_values(["date", "combined"], ascending=[True, False]).reset_index(drop=True))


def _aggregate_sql(con, levels: List[str]) -> pd.DataFrame:
    """在 duckdb 內把 TEMP TABLE m join 產業對照表聚合成所有層級的長格式 (含 level 欄)。"""
    con.register("imap", _industry_long(levels))
    return con.execute("""
        SELECT m.date AS date, im.level AS level, im.industry AS industry,
               sum(m."foreign") AS "foreign", sum(m.trust) AS trust,
               sum(m."foreign" + m.trust) AS combined,
               sum(m.turnover) AS turnover, count(*) AS n_stocks
        FROM m JOIN imap im ON m.stock_id = im.stock_id
        GROUP BY 1, 2, 3
        ORDER BY date, combined DESC
    """).df()


def compute_flow(level: str = DEFAULT_LEVEL, days: Optional[int] = None,
                 start: Optional[str] = None, history: bool = True) -> pd.DataFrame:
    """
    『各產業每日法人淨流入 (億元)』長格式,即時從本機資料源算。
    回傳欄:date, industry, foreign, trust, combined, turnover, n_stocks。
    本機資料源不存在 (如雲端) → 回空表。
    """
    if not INDUSTRY_XLSX.exists():
        return pd.DataFrame(columns=_FLOW_COLS)
    con, n = _connect(days, start, history)
    if con is None or n == 0:
        return pd.DataFrame(columns=_FLOW_COLS)
    try:
        df = _aggregate_sql(con, [level])
    finally:
        con.close()
    return df.drop(columns=["level"])[_FLOW_COLS].reset_index(drop=True)


def build_snapshot(levels: Optional[List[str]] = None, days: Optional[int] = None,
                   start: Optional[str] = None, members_days: int = 250,
                   history: bool = True) -> Tuple[int, int]:
    """
    把聚合結果落地成兩份 snapshot (供雲端讀):
      · cloud_cache/IndustryFlow/flow.parquet     —— 各層級產業每日淨流入 (主圖,全期間)
      · cloud_cache/IndustryFlow/members.parquet  —— 每檔每日淨流入 (下鑽用,只留最近
            members_days 個交易日;全歷史 800 萬列太大,雲端 repo 塞不下)
    回傳 (flow 列數, members 列數)。
    """
    levels = levels or list(LEVELS.keys())
    con, n = _connect(days, start, history)
    if con is None or n == 0:
        raise RuntimeError("找不到任何法人/價格資料 —— 先跑 scripts/market_snapshot_collector.py,"
                           f"或確認 TEJ 種子在 {TEJ_CACHE}。")
    imap = _industry_long(levels)          # 一併落地供雲端讀 (雲端沒有 openpyxl)
    try:
        df = _aggregate_sql(con, levels)[_SNAP_COLS]
        mem_where = ""
        if members_days:
            d = con.execute(f"SELECT DISTINCT date FROM m ORDER BY date DESC "
                            f"LIMIT {int(members_days)}").df()
            if not d.empty:
                mem_where = f"WHERE date >= '{str(d['date'].min())}'"
        members = con.execute(f"""
            SELECT date, stock_id, "foreign", trust, "foreign" + trust AS combined, turnover
            FROM m {mem_where} ORDER BY date, stock_id
        """).df()
    finally:
        con.close()

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    for target, data in [(SNAPSHOT, df), (MEMBERS_SNAPSHOT, members), (MAP_SNAPSHOT, imap)]:
        tmp = target.with_suffix(".parquet.tmp")
        _downcast(data).to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, target)
    _industry_map.cache_clear()            # 換過快照後,同程序內的後續查詢要讀到新的
    return len(df), len(members)


def _downcast(df: pd.DataFrame) -> pd.DataFrame:
    """金額欄 float64 → float32 (億元只要 2 位小數,float32 有效位數綽綽有餘),檔案減半。
    snapshot 是要 commit 進 repo 給雲端讀的,體積直接等於 git 歷史的增長速度。"""
    out = df.copy()
    for c in ("foreign", "trust", "combined", "turnover"):
        if c in out.columns:
            out[c] = out[c].astype("float32")
    if "n_stocks" in out.columns:
        out["n_stocks"] = out["n_stocks"].astype("int32")
    return out


def _read_daily(dir_: Path) -> pd.DataFrame:
    """讀某個逐日增量目錄裡的全部檔案 (無檔案 → 空表)。壞檔只跳過不讓整頁掛掉。"""
    files = sorted(glob.glob(str(dir_ / "*.parquet")))
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(f))
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def base_max_date() -> Optional[str]:
    """歷史基底 flow.parquet 的最新資料日 (供增量判斷起點);無基底回 None。"""
    if not SNAPSHOT.exists():
        return None
    try:
        d = pd.read_parquet(SNAPSHOT, columns=["date"])
        return str(d["date"].max()) if not d.empty else None
    except Exception:
        return None


def daily_dates() -> List[str]:
    """已落地的逐日增量檔日期 (由舊到新)。"""
    return sorted(Path(f).stem for f in glob.glob(str(DAILY_FLOW_DIR / "*.parquet")))


def append_days(dates: Optional[List[str]] = None,
                levels: Optional[List[str]] = None) -> List[str]:
    """
    逐日增量:把「基底之後、尚未落地」的交易日各寫成一個小 parquet。
      · cloud_cache/IndustryFlow/daily_flow/{date}.parquet     (含 level 欄,~10KB)
      · cloud_cache/IndustryFlow/daily_members/{date}.parquet  (~30KB)
    只讀 collector 的每日快照 (history=False) —— 增量要補的就是 TEJ 種子之後的日子。
    冪等:已存在的日期不重算。回傳實際新增的日期清單。
    """
    levels = levels or list(LEVELS.keys())
    have = set(daily_dates())
    base_max = base_max_date()
    todo = [d for d in _dates_available()
            if d not in have and (base_max is None or d > base_max)]
    if dates:
        todo = [d for d in dates if d not in have]
    if not todo:
        return []

    imap = _industry_long(levels)
    added = []
    DAILY_FLOW_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_MEMBERS_DIR.mkdir(parents=True, exist_ok=True)
    for d in todo:
        con, n = _connect(on_dates=[d], history=False)
        if con is None or n == 0:
            continue
        try:
            con.register("imap", imap)
            f = con.execute("""
                SELECT m.date AS date, im.level AS level, im.industry AS industry,
                       sum(m."foreign") AS "foreign", sum(m.trust) AS trust,
                       sum(m."foreign" + m.trust) AS combined,
                       sum(m.turnover) AS turnover, count(*) AS n_stocks
                FROM m JOIN imap im ON m.stock_id = im.stock_id
                GROUP BY 1, 2, 3 ORDER BY level, combined DESC
            """).df()
            mem = con.execute("""
                SELECT date, stock_id, "foreign", trust, "foreign" + trust AS combined, turnover
                FROM m ORDER BY stock_id
            """).df()
        finally:
            con.close()
        if f.empty:
            continue
        for target, data in ((DAILY_FLOW_DIR / f"{d}.parquet", f[_SNAP_COLS]),
                             (DAILY_MEMBERS_DIR / f"{d}.parquet", mem[_MEM_COLS])):
            tmp = target.with_suffix(".parquet.tmp")
            _downcast(data).to_parquet(tmp, index=False, compression="zstd")
            os.replace(tmp, target)
        added.append(d)
    return added


def compact(members_days: int = 250) -> Tuple[int, int]:
    """
    把逐日增量檔折進歷史基底、刪掉逐日檔,並把 members 基底裁回最近 members_days 日。
    逐日檔累積太多時跑一次 (它會重寫 13MB 基底,所以別天天跑)。回傳 (flow 列數, members 列數)。
    """
    if not daily_dates():
        return 0, 0
    flow = pd.concat([x for x in (pd.read_parquet(SNAPSHOT) if SNAPSHOT.exists() else None,
                                  _read_daily(DAILY_FLOW_DIR)) if x is not None and not x.empty],
                     ignore_index=True)
    flow = flow.drop_duplicates(subset=["date", "level", "industry"], keep="last")
    mem = pd.concat([x for x in ((pd.read_parquet(MEMBERS_SNAPSHOT)
                                  if MEMBERS_SNAPSHOT.exists() else None),
                                 _read_daily(DAILY_MEMBERS_DIR)) if x is not None and not x.empty],
                    ignore_index=True)
    mem = mem.drop_duplicates(subset=["date", "stock_id"], keep="last")
    keep = sorted(mem["date"].unique())[-int(members_days):]
    mem = mem[mem["date"].isin(set(keep))]

    for target, data in ((SNAPSHOT, flow[_SNAP_COLS].sort_values(["date", "level"])),
                         (MEMBERS_SNAPSHOT, mem[_MEM_COLS].sort_values(["date", "stock_id"]))):
        tmp = target.with_suffix(".parquet.tmp")
        _downcast(data.reset_index(drop=True)).to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, target)
    for dir_ in (DAILY_FLOW_DIR, DAILY_MEMBERS_DIR):
        for f in glob.glob(str(dir_ / "*.parquet")):
            os.remove(f)
    return len(flow), len(mem)


def _members_frame() -> pd.DataFrame:
    """members 來源:歷史基底 ∪ 逐日增量 (雲端/本機皆可);兩者皆無則本機即時算最近一年。"""
    frames = []
    if MEMBERS_SNAPSHOT.exists():
        try:
            frames.append(pd.read_parquet(MEMBERS_SNAPSHOT))
        except Exception:
            pass
    inc = _read_daily(DAILY_MEMBERS_DIR)
    if not inc.empty:
        frames.append(inc)
    frames = [f for f in frames if f is not None and not f.empty]
    if frames:
        m = pd.concat(frames, ignore_index=True)
        return m.drop_duplicates(subset=["date", "stock_id"], keep="last")
    return compute_members(days=250)


def members_range() -> Tuple[Optional[str], Optional[str]]:
    """下鑽成分股資料實際涵蓋的日期範圍 (可能比主圖短) → (min, max);無資料回 (None, None)。"""
    m = _members_frame()
    if m is None or m.empty:
        return None, None
    return str(m["date"].min()), str(m["date"].max())


def load_members(level: str, industry: str, date: Optional[str] = None,
                 start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """
    某產業的成分股法人淨流入 (下鑽用)。
      · date 指定 → 只看該日;否則看 [start, end] 區間 (皆省略 = 全部可用期間)。
    回傳欄:stock_id, foreign, trust, combined, turnover, days (依 combined 由高到低)。
    """
    cols = ["stock_id", "foreign", "trust", "combined", "turnover", "days"]
    m = _members_frame()
    if m is None or m.empty:
        return pd.DataFrame(columns=cols)
    m = m.copy()
    if "turnover" not in m.columns:          # 舊 snapshot 沒有成交額欄 → 占比口徑留空
        m["turnover"] = float("nan")
    m["industry"] = m["stock_id"].map(_industry_map(level))
    m = m[m["industry"] == industry]
    if date:
        m = m[m["date"] == date]
    else:
        if start:
            m = m[m["date"] >= start]
        if end:
            m = m[m["date"] <= end]
    if m.empty:
        return pd.DataFrame(columns=cols)
    g = (m.groupby("stock_id")
           .agg(foreign=("foreign", "sum"), trust=("trust", "sum"),
                combined=("combined", "sum"), turnover=("turnover", "sum"),
                days=("date", "nunique"))
           .reset_index())
    return g[cols].sort_values("combined", ascending=False).reset_index(drop=True)


def load_flow(level: str = DEFAULT_LEVEL) -> pd.DataFrame:
    """
    讀某層級的產業流向長格式:**歷史基底 ∪ 逐日增量** (雲端/本機皆可),
    兩者皆無則本機即時算最近一年 (compute_flow)。全無 → 空表。
    """
    frames = []
    if SNAPSHOT.exists():
        try:
            frames.append(pd.read_parquet(SNAPSHOT))
        except Exception:
            pass
    inc = _read_daily(DAILY_FLOW_DIR)
    if not inc.empty:
        frames.append(inc)
    frames = [f for f in frames if f is not None and not f.empty and "level" in f.columns]
    if frames:
        df = pd.concat(frames, ignore_index=True)
        sub = df[df["level"] == level].drop(columns=["level"])
        if not sub.empty:
            if "turnover" not in sub.columns:        # 舊 snapshot → 占比口徑留空
                sub["turnover"] = float("nan")
            sub = sub.drop_duplicates(subset=["date", "industry"], keep="last")
            return (sub[_FLOW_COLS]
                    .sort_values(["date", "combined"], ascending=[True, False])
                    .reset_index(drop=True))
    return compute_flow(level, days=250)
