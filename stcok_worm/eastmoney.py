"""
东方财富数据源 — 从 a-stock-data 提取（仅独有数据）

功能:
    - get_dividend_history(code)   — 分红送转历史
    - get_margin_detail(code)      — 融资融券明细
    - get_block_trade(code)        — 大宗交易
    - get_shareholder_count(code)  — 股东户数
    - get_fund_flow_minute(code)   — 资金流分钟级

所有请求走 em_get() 限流器，自带防封。
"""

import logging
from typing import Any, Dict, List, Optional

from ._session import em_get, eastmoney_datacenter, DATACENTER_URL

logger = logging.getLogger(__name__)


def get_dividend_history(code: str, page_size: int = 20) -> List[Dict[str, Any]]:
    """
    分红送转历史 (东方财富数据中心).

    Returns:
        [{impl_date, net_base, ...}, ...]
    """
    return eastmoney_datacenter(
        report_name="RPT_DMSK_FN_DESIGNEDDIVIDEND",
        columns="IMPLE_DATE,SECURITY_CODE,NET_BASE,BEFORE_TAX,AFTER_TAX",
        filter_str=f'(SECURITY_CODE=\"{code}\")',
        sort_columns="IMPLE_DATE", sort_types="-1",
        page_size=page_size,
    )


def get_margin_detail(code: str, page_size: int = 30) -> List[Dict[str, Any]]:
    """融资融券明细 (东方财富数据中心)."""
    return eastmoney_datacenter(
        report_name="RPTA_WEB_MARGIN_TRADING_DETAILS",
        columns="TRADE_DATE,FC_AMOUNT,FS_AMOUNT,RZ_AMOUNT,RZ_MARKET_VALUE",
        filter_str=f'(SECURITY_CODE=\"{code}\")',
        sort_columns="TRADE_DATE", sort_types="-1",
        page_size=page_size,
    )


def get_block_trade(code: str, page_size: int = 20) -> List[Dict[str, Any]]:
    """大宗交易 (东方财富数据中心)."""
    return eastmoney_datacenter(
        report_name="RPTA_WEB_BLOCKTRADE",
        columns="TRADE_DATE,SECURITY_CODE,PRICE,VOLUME,AMOUNT,PREMIUM_RATIO",
        filter_str=f'(SECURITY_CODE=\"{code}\")',
        sort_columns="TRADE_DATE", sort_types="-1",
        page_size=page_size,
    )


def get_shareholder_count(code: str, page_size: int = 10) -> List[Dict[str, Any]]:
    """股东户数变化 (东方财富数据中心)."""
    return eastmoney_datacenter(
        report_name="RPTA_WEB_HOLDERNUMLIST",
        columns="END_DATE,SECURITY_CODE,HOLDER_NUM,PRE_HOLDER_NUM,HOLDER_NUM_CHANGE_RATE",
        filter_str=f'(SECURITY_CODE=\"{code}\")',
        sort_columns="END_DATE", sort_types="-1",
        page_size=page_size,
    )


def get_fund_flow_minute(code: str) -> List[Dict[str, Any]]:
    """资金流分钟级 (东方财富 push2)."""
    market = "1" if code.startswith(("6", "9")) else "0"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/minutechart/get"
    params = {
        "secid": f"{market}.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55",
    }
    r = em_get(url, params=params, timeout=10)
    try:
        data = r.json()
        return data.get("data", {}).get("details", [])
    except Exception:
        return []
