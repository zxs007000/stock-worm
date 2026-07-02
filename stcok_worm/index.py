"""
指数数据源.

功能:
    - get_etf_nav(code)           — ETF历史净值
    - get_dividend_yield(code)    — 从分红历史反算股息率

数据源: akshare + eastmoney.py
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


def get_etf_nav(code: str) -> Optional[pd.DataFrame]:
    """
    ETF 历史净值 (akshare).

    Args:
        code: ETF代码 (如 "159307")

    Returns:
        DataFrame: [date, nav, price]
    """
    if not _has_akshare:
        raise ImportError("pip install akshare")
    try:
        df = ak.fund_etf_fund_info_em(fund=code)
        if df is not None and not df.empty:
            rename = {
                "净值日期": "date", "单位净值": "nav",
                "累计净值": "cum_nav", "日增长率": "change_pct",
            }
            df = df.rename(columns=rename, errors="ignore")
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            return df
    except Exception as e:
        logger.warning("ETF净值失败 %s: %s", code, e)
    return None


def get_dividend_yield(code: str) -> float:
    """
    从ETF累计净值和单位净值的差值反算股息率.

    公式: (累计净值 - 单位净值) / 单位净值 × 100

    不需要调东财接口，akshare 的 ETF净值数据即可计算。

    Args:
        code: ETF代码 (如 "159307")

    Returns:
        股息率 (%)，如 8.44
    """
    nav_df = get_etf_nav(code)
    if nav_df is None or nav_df.empty:
        return 0.0

    last = nav_df.iloc[-1]
    nav_val = float(last.get("nav", 0))
    cum_val = float(last.get("cum_nav", 0))
    if nav_val <= 0:
        return 0.0

    div_per_share = cum_val - nav_val
    if div_per_share <= 0:
        return 0.0

    dividend_yield = (div_per_share / nav_val) * 100
    return round(dividend_yield, 2)
