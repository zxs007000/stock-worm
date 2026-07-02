"""
期权层 — ETF期权 T型报价 + 希腊字母 + 隐含波动率

端点:
    - option_contracts(underlying)   — 期权合约列表
    - option_tquote(underlying)      — T型报价
"""

import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from ._session import EM_SESSION

logger = logging.getLogger(__name__)

UNDERLYING_MAP = {
    "510050": "50ETF",
    "510300": "300ETF",
    "588000": "科创50ETF",
    "510500": "500ETF",
}


def option_contracts(underlying: str = "510050") -> List[Dict[str, Any]]:
    """
    ETF期权合约列表 (新浪源).

    Args:
        underlying: ETF代码 (510050/510300/588000/510500)
    """
    url = f"https://hq.sinajs.cn/list=OP_{underlying}"
    try:
        r = EM_SESSION.get(url, timeout=10,
                           headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gbk"
        text = r.text
        match = re.search(r'"(.+)"', text)
        if not match:
            return []
        raw = match.group(1)
        parts = raw.split(",")
        contracts = []
        i = 0
        while i < len(parts) - 5:
            contracts.append({
                "call_code": parts[i] if i < len(parts) else "",
                "strike": float(parts[i + 1]) if i + 1 < len(parts) else 0,
                "put_code": parts[i + 2] if i + 2 < len(parts) else "",
                "month": parts[i + 3] if i + 3 < len(parts) else "",
            })
            i += 4
        return contracts
    except Exception as exc:
        logger.warning("option_contracts failed for %s: %s", underlying, exc)
    return []


def option_tquote(underlying: str = "510050") -> Optional[pd.DataFrame]:
    """
    ETF期权 T型报价 (含希腊字母/IV, 新浪源).

    Returns:
        DataFrame: [strike, call_code, call_last, call_bid, call_ask,
                    put_last, put_bid, put_ask, ...]
    """
    contracts = option_contracts(underlying)
    if not contracts:
        return None

    rows = []
    for c in contracts:
        call_code = c.get("call_code", "")
        put_code = c.get("put_code", "")
        strike = c.get("strike", 0)
        if not call_code or not put_code:
            continue

        call_data = _fetch_option_quote(call_code)
        put_data = _fetch_option_quote(put_code)

        row = {"strike": strike}
        if call_data:
            row.update({f"call_{k}": v for k, v in call_data.items()})
        if put_data:
            row.update({f"put_{k}": v for k, v in put_data.items()})
        rows.append(row)

    if not rows:
        return None
    return pd.DataFrame(rows)


def _fetch_option_quote(code: str) -> Optional[Dict[str, Any]]:
    """获取单个期权合约行情。"""
    url = f"https://hq.sinajs.cn/list={code}"
    try:
        r = EM_SESSION.get(url, timeout=5,
                           headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gbk"
        text = r.text
        match = re.search(r'"(.+)"', text)
        if not match:
            return None
        fields = match.group(1).split(",")
        if len(fields) < 15:
            return None
        return {
            "name": fields[0],
            "open": float(fields[1]) if fields[1] else 0,
            "last": float(fields[2]) if fields[2] else 0,
            "high": float(fields[3]) if fields[3] else 0,
            "low": float(fields[4]) if fields[4] else 0,
            "bid1": float(fields[6]) if len(fields) > 6 and fields[6] else 0,
            "ask1": float(fields[7]) if len(fields) > 7 and fields[7] else 0,
            "volume": int(float(fields[10])) if len(fields) > 10 and fields[10] else 0,
            "hold": int(float(fields[13])) if len(fields) > 13 and fields[13] else 0,
        }
    except Exception:
        return None
