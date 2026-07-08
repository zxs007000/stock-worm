"""
信号层 — 龙虎榜 + 解禁 + 行业排名 + 板块归属 + 涨停池

端点:
    - dragon_tiger(code)            — 个股龙虎榜席位
    - dragon_tiger_daily(date)      — 全市场龙虎榜
    - lockup_expiry(code)           — 限售解禁日历
    - industry_ranking()            — 行业板块涨跌排名
    - sector_membership(code)       — 个股所属板块
    - limit_up_pool(date)           — 涨停池
    - limit_down_pool(date)         — 跌停池
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ._session import em_get, eastmoney_push2, DATACENTER_URL, get_secid

logger = logging.getLogger(__name__)


def dragon_tiger(code: str, page_size: int = 10) -> List[Dict[str, Any]]:
    """个股龙虎榜席位 (datacenter-web, push2 不通时走此路)."""
    code = code.strip().split(".")[0]
    prefix = "SH" if code.startswith(("6","9")) else "SZ"
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": f'(SECUCODE="{code}.{prefix}")',
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as exc:
        logger.warning("dragon_tiger failed for %s: %s", code, exc)
    return []


def dragon_tiger_daily(date: str = "", page_size: int = 50) -> List[Dict[str, Any]]:
    """全市场每日龙虎榜 (datacenter-web)."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": f'(TRADE_DATE=\'{date}\')',
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "BILLBOARD_NET_AMT",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as exc:
        logger.warning("dragon_tiger_daily failed: %s", exc)
    return []


def lockup_expiry(code: str, page_size: int = 20) -> List[Dict[str, Any]]:
    """限售解禁日历 (东财数据中心)."""
    code = code.strip().split(".")[0]
    params = {
        "reportName": "RPT_LIFT_STAGE",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "FREE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as exc:
        logger.warning("lockup_expiry failed for %s: %s", code, exc)
    return []


def industry_ranking(page_size: int = 50) -> List[Dict[str, Any]]:
    """行业板块涨跌排名 (东财 push2)."""
    return eastmoney_push2(
        fields="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f62,f128,f136,f115",
        fs="m:90+t:2+f:!50",
        sort_field="f3",
        sort_type="desc",
        page_size=page_size,
    )


def sector_membership(code: str) -> List[Dict[str, Any]]:
    """个股所属板块 (行业/概念/地域 + BK码 + 涨跌幅 + 龙头股)."""
    secid = get_secid(code)
    return eastmoney_push2(
        fields="f1,f2,f3,f4,f12,f13,f14,f62,f128,f136,f115",
        fs=f"b:{secid}+b:!50",
        page_size=50,
    )


def limit_up_pool(date: str = "", page_size: int = 50) -> List[Dict[str, Any]]:
    """涨停池 (东财 push2)."""
    return eastmoney_push2(
        fields="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f124",
        fs="m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2",
        sort_field="f3",
        sort_type="desc",
        page_size=page_size,
    )


def limit_down_pool(date: str = "", page_size: int = 50) -> List[Dict[str, Any]]:
    """跌停池 (东财 push2)."""
    return eastmoney_push2(
        fields="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25",
        fs="m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2",
        sort_field="f3",
        sort_type="asc",
        page_size=page_size,
    )
