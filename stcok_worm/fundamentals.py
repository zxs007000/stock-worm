"""
基础数据层 — 季报快照 + F10公司资料 + 个股信息

端点:
    - quarterly_snapshot(code)      — 季报37字段快照
    - company_info(code)            — 个股基础信息 (行业/总股本/市值等)
"""

import logging
from typing import Any, Dict, List, Optional

from ._session import em_get, DATACENTER_URL, get_secid

logger = logging.getLogger(__name__)


def quarterly_snapshot(code: str) -> Optional[Dict[str, Any]]:
    """季报快照 37字段 (东财数据中心)."""
    code = code.strip().split(".")[0]
    params = {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": "1",
        "pageSize": "1",
        "sortColumns": "REPORTDATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"][0]
    except Exception as exc:
        logger.warning("quarterly_snapshot failed for %s: %s", code, exc)
    return None


def company_info(code: str) -> Optional[Dict[str, Any]]:
    """个股基础信息 (东财 push2)."""
    secid = get_secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": secid,
        "fields": "f57,f58,f84,f85,f116,f117,f127,f162,f163,f164,f167,f168,f169,f170,f171,f173,f177,f292",
        "invt": "2",
        "fltt": "2",
    }
    try:
        r = em_get(url, params=params, timeout=10)
        d = r.json()
        if d.get("data"):
            data = d["data"]
            return {
                "code": data.get("f57", ""),
                "name": data.get("f58", ""),
                "total_shares": data.get("f84"),
                "float_shares": data.get("f85"),
                "market_cap": data.get("f116"),
                "float_cap": data.get("f117"),
                "industry": data.get("f127", ""),
                "pe_ttm": data.get("f162"),
                "pe_static": data.get("f163"),
                "pb": data.get("f167"),
                "roe": data.get("f173"),
                "revenue_yoy": data.get("f177"),
                "listing_date": data.get("f292", ""),
            }
    except Exception as exc:
        logger.warning("company_info failed for %s: %s", code, exc)
    return None
