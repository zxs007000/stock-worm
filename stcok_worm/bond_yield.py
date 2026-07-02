"""
国债收益率数据源.

功能:
    - get_china_yield_10y()      — 中国10年期国债收益率
    - get_china_yield_curve()    — 完整收益率曲线

数据源: akshare.bond_zh_us_rate() — 9271行历史数据, 实时到最新
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    _has_akshare = True
except ImportError:
    _has_akshare = False


def get_china_yield_10y() -> Optional[pd.DataFrame]:
    """
    中国10年期国债收益率.

    Returns:
        DataFrame: [date, yield_10y]
    """
    df = get_china_yield_curve()
    if df is None or df.empty:
        return None

    # 找 10Y 列
    for col in df.columns:
        if "10" in str(col) and ("Y" in str(col).upper() or "年" in str(col)):
            date_col = df.columns[0]
            result = df[[date_col, col]].copy()
            result.columns = ["date", "yield_10y"]
            result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
            result["yield_10y"] = pd.to_numeric(result["yield_10y"], errors="coerce")
            return result.dropna().reset_index(drop=True)

    logger.warning("未找到10Y列, 可用列: %s", list(df.columns))
    return None


def get_china_yield_curve() -> Optional[pd.DataFrame]:
    """
    中国国债完整收益率曲线 (akshare).

    Returns:
        DataFrame with columns [date, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, ...]
    """
    if not _has_akshare:
        raise ImportError("pip install akshare")
    try:
        df = ak.bond_zh_us_rate()
        return df
    except Exception as e:
        logger.error("获取国债收益率失败: %s", e)
        return None
