"""
可转债数据源 (新浪财经) — 封装自 HistoricalCBCollector

功能:
    - get_cb_list()              — 全量转债列表
    - get_cb_daily(code)         — 单债日线
    - build_cb_sections()        — 批量组装日截面

数据源: akshare.bond_zh_hs_daily() — 85-90% 成功率, ~0.12s/只
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    _has_akshare = True
except ImportError:
    _has_akshare = False


def get_cb_list() -> pd.DataFrame:
    """全量转债列表 (东方财富)."""
    if not _has_akshare:
        raise ImportError("pip install akshare")
    df = ak.bond_zh_cov()
    rename = {
        "债券代码": "bond_code", "债券简称": "bond_name",
        "正股代码": "stock_code", "信用评级": "rating",
        "发行规模": "issue_size", "转股价": "convert_price",
    }
    df = df.rename(columns=rename, errors="ignore")
    if "bond_code" in df.columns:
        df["bond_code"] = df["bond_code"].astype(str).str.strip()
    if "stock_code" in df.columns:
        df["stock_code"] = df["stock_code"].astype(str).str.strip()
    if "convert_price" in df.columns:
        df["convert_price"] = pd.to_numeric(df["convert_price"], errors="coerce")
    return df


def get_cb_daily(code: str) -> Optional[pd.DataFrame]:
    """
    单只转债日线 (新浪财经).

    Args:
        code: 转债代码 (如 "127027")

    Returns:
        DataFrame: [date, open, high, low, close, volume]
    """
    if not _has_akshare:
        raise ImportError("pip install akshare")
    prefix = "sh" if code.startswith("11") else "sz"
    try:
        df = ak.bond_zh_hs_daily(symbol=prefix + code)
    except Exception:
        return None
    if df is None or df.empty or "date" not in df.columns:
        return None
    df = df[["date", "close", "open", "high", "low", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for c in ["close", "open", "high", "low"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    return df.dropna(subset=["date", "close"]).reset_index(drop=True)


def build_cb_sections(
    cb_data: Dict[str, pd.DataFrame],
    stock_data: Dict[str, pd.DataFrame],
    master: pd.DataFrame,
) -> pd.DataFrame:
    """
    批量组装日截面 (含 premium_rt 计算).

    与 rebuild_sections.py 逻辑相同, 返回合并后的 DataFrame.
    """
    cp_series = master.set_index("bond_code")["convert_price"].dropna()
    cp_series = cp_series[cp_series > 0]
    sc_series = master.set_index("bond_code")["stock_code"].dropna()
    rating_series = master.set_index("bond_code")["rating"].fillna("")

    frames = []
    for bc, bdf in cb_data.items():
        cp = cp_series.get(bc)
        if cp is None:
            continue
        sc = sc_series.get(bc)
        if sc is None or str(sc).strip() in ("", "nan"):
            continue
        sc = str(sc).strip()
        sdf = stock_data.get(sc)
        if sdf is None or sdf.empty:
            continue

        merged = pd.merge(
            bdf[["date", "close"]],
            sdf[["date", "close"]],
            on="date", how="inner", suffixes=("", "_stock"),
        )
        if merged.empty:
            continue

        cp_val = float(cp)
        merged["convert_value"] = (100.0 / cp_val) * merged["close_stock"]
        merged["premium_rt"] = round((merged["close"] / merged["convert_value"] - 1.0) * 100, 2)
        merged["dblow"] = round(merged["close"] + merged["premium_rt"], 2)
        merged["bond_code"] = bc
        merged["rating"] = str(rating_series.get(bc, ""))
        merged["price"] = round(merged["close"], 2)
        frames.append(merged[["date", "bond_code", "price", "premium_rt", "dblow", "rating"]])

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
