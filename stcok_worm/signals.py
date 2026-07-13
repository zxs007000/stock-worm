"""
信号层 — 龙虎榜 + 解禁 + 行业排名 + 板块归属 + 涨停池

端点:
    - dragon_tiger(code)            — 个股龙虎榜席位 (东财)
    - dragon_tiger_daily(date)      — 全市场龙虎榜 (东财)
    - dragon_tiger_jrj_daily(date)  — 全市场龙虎榜 (金融界, 含营业部明细)
    - dragon_tiger_jrj_summary(date)— 龙虎榜统计 (金融界)
    - dragon_tiger_jrj_stock(c,d)   — 个股龙虎榜席位明细 (金融界)
    - dragon_tiger_jrj_branches(d)  — 营业部龙虎榜排行 (金融界)
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


# ── JRJ (金融界) 龙虎榜 ──────────────────────────────────────

JRJ_LHB_URL = "https://gateway.jrj.com/quot-dc/v1/lhb"
JRJ_LHB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _jrj_security_id(code: str) -> int:
    """6位代码 → JRJ 内部 securityId."""
    code = code.strip().split(".")[0].strip()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    if code.startswith(("6", "9")):
        return int(f"1{code}")
    elif code.startswith("8"):
        return int(f"0{code}")
    return int(f"2{code}")


def _jrj_lhb_post(endpoint: str, body: dict) -> Optional[Dict[str, Any]]:
    """JRJ 龙虎榜 POST 请求封装."""
    import requests
    try:
        r = requests.post(f"{JRJ_LHB_URL}/{endpoint}", json=body,
                          headers={"User-Agent": JRJ_LHB_UA,
                                   "Referer": "https://www.jrj.com.cn/",
                                   "Content-Type": "application/json"},
                          timeout=15)
        d = r.json()
        if d.get("code") != 20000:
            logger.warning("jrj_lhb %s returned %s: %s", endpoint, d.get("code"), d.get("msg"))
            return None
        return d.get("data", {})
    except Exception as exc:
        logger.warning("jrj_lhb %s failed: %s", endpoint, exc)
        return None


def dragon_tiger_jrj_daily(date: str = "", page: int = 1,
                            page_size: int = 50) -> Optional[Dict[str, Any]]:
    """全市场龙虎榜 (金融界, 含持仓机构明细).

    Args:
        date: 日期 "YYYY-MM-DD"，默认今天
        page: 页码
        page_size: 每页数量

    Returns:
        {total, list: [{sid, code, name, market, close, changePct, turnover,
         buyAmt, sellAmt, netAmt, buyBranch, sellBranch, reason, ...}]}
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    data = _jrj_lhb_post("stockList", {
        "endDate": date, "pageNum": page, "pageSize": page_size,
    })
    if not data:
        return None
    return {
        "total": data.get("total", 0),
        "list": data.get("rows", data.get("list", [])),
    }


def dragon_tiger_jrj_summary(date: str = "") -> Optional[Dict[str, Any]]:
    """龙虎榜统计 (金融界): 上榜数 / 净买额 / 净卖额."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    data = _jrj_lhb_post("stockCount", {"endDate": date})
    if not data:
        return None
    # 返回原始统计结构
    return data


def dragon_tiger_jrj_stock(code: str, date: str = "") -> Optional[Dict[str, Any]]:
    """单只股票龙虎榜席位明细 (金融界).

    Args:
        code: 6位代码
        date: 日期

    Returns:
        {stock: {...}, tradingList: [{type, name, buyAmt, sellAmt, netAmt, ...}]}
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    sid = _jrj_security_id(code)
    data = _jrj_lhb_post("orgList", {"endDate": date, "stockId": sid})
    return data


def dragon_tiger_jrj_branches(date: str = "", page: int = 1,
                               page_size: int = 50) -> Optional[Dict[str, Any]]:
    """营业部龙虎榜排行 (金融界).

    Returns:
        {total, list: [{branchName, buyAmt, sellAmt, netAmt, count, ...}]}
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    data = _jrj_lhb_post("branchCount", {
        "endDate": date, "pageNum": page, "pageSize": page_size,
    })
    if not data:
        return None
    return {
        "total": data.get("total", 0),
        "list": data.get("rows", data.get("list", [])),
    }


def limit_down_pool(date: str = "", page_size: int = 50) -> List[Dict[str, Any]]:
    """跌停池 (东财 push2)."""
    return eastmoney_push2(
        fields="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25",
        fs="m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2",
        sort_field="f3",
        sort_type="asc",
        page_size=page_size,
    )
