"""
本地数据湖读取层 — stock_worm 的统一缓存入口。

数据湖由 build_fundamentals_ext.py / build_fundamental_lake.py 等脚本生成，
默认根目录：
    Windows: D:/work Buddy GZ/Claw/stockworm
可通过环境变量 STOCKWORM_LAKE 覆盖（例如 export STOCKWORM_LAKE=/data/stockworm）。

这样 stock_worm 既能 live 抓取（fundamentals_ext.*），也能从本地湖秒级读取，
避免重复打东财。典型用法：

    from stcok_worm import datalake
    datalake.set_lake_root("D:/work Buddy GZ/Claw/stockworm")
    fin = datalake.load_fin_indicators()            # 全市场财务比率
    sub = datalake.load_fin_indicators(["000001","600519"])
    div = datalake.load_dividends()                 # 全市场分红汇总
    unlock = datalake.load_unlocks("20260101","20261231")
    q   = datalake.load_quarterly("000001")         # 个股季报快照
    ind = datalake.load_industry_map()              # 行业映射
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

_DEFAULT_LAKE = "D:/work Buddy GZ/Claw/stockworm"
LAKE_ROOT = Path(os.environ.get("STOCKWORM_LAKE", _DEFAULT_LAKE)).expanduser()


def set_lake_root(p) -> None:
    """设置数据湖根目录（运行时覆盖默认/环境变量）。"""
    global LAKE_ROOT
    LAKE_ROOT = Path(p).expanduser()


def lake_root() -> Path:
    return LAKE_ROOT


def _fund_dir() -> Path:
    return LAKE_ROOT / "fundamentals"


def load_fin_indicators(codes=None) -> pd.DataFrame:
    """财务比率（季度，38 列，因子金矿）。codes 为可迭代的 6 位代码，None=全市场。"""
    f = _fund_dir() / "fin_indicators.parquet"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_parquet(f)
    if codes is not None:
        df = df[df["code"].isin(set(codes))]
    return df


def load_dividends() -> pd.DataFrame:
    """全市场分红历史汇总（来自 stock_history_dividend）。"""
    f = _fund_dir() / "dividends_summary.parquet"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_parquet(f)


def load_unlocks(start: str = None, end: str = None) -> pd.DataFrame:
    """限售股解禁事件。start/end 形如 'YYYYMMDD'（按解禁日期过滤）。"""
    f = _fund_dir() / "unlocks.parquet"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_parquet(f)
    col = "解禁日期" if "解禁日期" in df.columns else None
    if col and start is not None:
        df = df[df[col] >= start]
    if col and end is not None:
        df = df[df[col] <= end]
    return df


def load_quarterly(code: str) -> pd.DataFrame:
    """个股季报快照（fundamentals/{code}.parquet，来自 fundamentals.quarterly_snapshot）。"""
    code = str(code).strip().split(".")[0]
    f = _fund_dir() / f"{code}.parquet"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_parquet(f)


def load_industry_map() -> pd.DataFrame:
    """行业映射（metadata/industry_map.csv）。

    由 stcok_worm.industry_map 多源模块生成，列含：
        code, eastmoney_industry（始终填充，缺口用巨潮补）, cninfo_industry（巨潮真值）。
    下游行业中性化优先用 eastmoney_industry（始终非空），cninfo_industry 可作交叉校验。
    """
    f = LAKE_ROOT / "metadata" / "industry_map.csv"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_csv(f)


def load_regulatory_events(codes=None) -> pd.DataFrame:
    """监管事件（regulatory_events.parquet：code, event_date, title, severity, event_type, url）。
    codes 为可迭代的 6 位代码，None=全市场。"""
    f = _fund_dir() / "regulatory_events.parquet"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_parquet(f)
    if codes is not None:
        df = df[df["code"].isin(set(codes))]
    return df
