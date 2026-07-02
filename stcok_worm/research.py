"""
研报层 — 东财研报 + 同花顺一致预期 + 行业研报

端点:
    - stock_reports(code)           — 个股研报列表 + 评级 + EPS预测
    - industry_reports(industry)    — 行业研报列表
    - consensus_eps(code)           — 同花顺机构一致预期 EPS
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from ._session import em_get, REPORTAPI_URL

logger = logging.getLogger(__name__)


def stock_reports(code: str, page_size: int = 10) -> List[Dict[str, Any]]:
    """
    个股研报列表 (东财 reportapi).

    Args:
        code: 6位股票代码
        page_size: 返回条数

    Returns:
        [{title, org, rating, eps_this_year, eps_next_year, ...}, ...]
    """
    params = {
        "industryCode": "*",
        "pageSize": str(page_size),
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": "",
        "endTime": "",
        "pageNo": "1",
        "fields": "",
        "qType": "0",
        "orgCode": "",
        "code": code,
        "rcode": "",
        "p": "1",
        "pageNum": "1",
        "pageNumber": "1",
    }
    try:
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        data = r.json()
        if data.get("data"):
            return data["data"]
    except Exception as exc:
        logger.warning("stock_reports failed for %s: %s", code, exc)
    return []


def industry_reports(industry_code: str = "*", page_size: int = 10) -> List[Dict[str, Any]]:
    """
    行业研报列表 (东财 reportapi, qType=1).

    Args:
        industry_code: 东财行业码 (如 '1238'=IT服务Ⅱ), '*' = 全行业
        page_size: 返回条数
    """
    params = {
        "industryCode": industry_code,
        "pageSize": str(page_size),
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": "",
        "endTime": "",
        "pageNo": "1",
        "fields": "",
        "qType": "1",
        "orgCode": "",
        "code": "",
        "rcode": "",
        "p": "1",
        "pageNum": "1",
        "pageNumber": "1",
    }
    try:
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        data = r.json()
        if data.get("data"):
            return data["data"]
    except Exception as exc:
        logger.warning("industry_reports failed: %s", exc)
    return []


def consensus_eps(code: str) -> Optional[Dict[str, Any]]:
    """
    同花顺机构一致预期 EPS.

    Returns:
        {eps_this_year, eps_next_year, pe_fwd, ...} or None
    """
    code = code.strip().split(".")[0]
    url = f"https://basic.10jqka.com.cn/stock/0{code}/expected.html"
    try:
        from ._session import EM_SESSION
        r = EM_SESSION.get(url, timeout=10)
        r.encoding = "utf-8"
        text = r.text

        import re
        rows = re.findall(r'<td[^>]*>([\d.]+)</td>', text)
        if len(rows) >= 4:
            return {
                "eps_this_year": float(rows[0]) if rows[0] else None,
                "eps_next_year": float(rows[1]) if rows[1] else None,
                "pe_fwd": float(rows[2]) if rows[2] else None,
                "analyst_count": int(float(rows[3])) if rows[3] else None,
            }
    except Exception as exc:
        logger.warning("consensus_eps failed for %s: %s", code, exc)
    return None
