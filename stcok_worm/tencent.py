"""
腾讯财经数据源 — 从 a-stock-data 提取

功能:
    - get_kline(code, period)    — A股K线
    - get_etf_daily(code)        — ETF日线
    - get_index_daily(code)       — 指数日线
    - get_stock_quote(code)       — 实时行情(PE/PB/市值)
    - get_quotes_batch(codes)    — 批量实时行情

特点: 不封IP，可高频调用 (建议 0.5s 间隔)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def _normalize_code(code: str) -> str:
    """将各种代码格式统一为6位纯数字: sh600519→600519, 600519.SH→600519."""
    code = code.strip().split(".")[0].strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    return code


def _market_prefix(code: str) -> str:
    code = _normalize_code(code)
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def _parse_kline_data(data: dict, prefix: str, code: str) -> list:
    """解析腾讯 K-line 返回数据。"""
    inner_data = data.get("data", {})
    # 容错：空结果时 data["data"] 可能是空列表
    if not isinstance(inner_data, dict):
        return []
    inner = inner_data.get(f"{prefix}{code}", {})
    if not isinstance(inner, dict):
        return []
    rows = inner.get("day", []) or inner.get("qfqday", []) or []
    if not rows:
        qt = inner.get("qt", {})
        if isinstance(qt, dict):
            rows = qt.get("day", []) or qt.get("qfqday", [])
    return rows  # type: ignore


def get_kline(code: str, period: str = "day") -> Optional[list]:
    """
    A股K线 (腾讯财经).

    Args:
        code: 6位代码 (如 "688017")，也兼容 "sh600519" / "600519.SH"
        period: day/week/month

    Returns:
        [{"date", "open", "close", "high", "low", "volume"}, ...]
    """
    norm_code = _normalize_code(code)
    prefix = _market_prefix(norm_code)
    url = (f"{KLINE_URL}?"
           f"param={prefix}{norm_code},{period},2000-01-01,{datetime.now().strftime('%Y-%m-%d')},2000,qfq")
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = resp.json()
    except Exception:
        return None

    rows = _parse_kline_data(data, prefix, norm_code)
    if not rows:
        return None

    records = []
    for r in rows:
        try:
            records.append({
                "date": str(r[0]), "open": float(r[1]),
                "close": float(r[2]), "high": float(r[3]),
                "low": float(r[4]),
                "volume": float(r[5]) if len(r) > 5 else 0.0,
            })
        except (IndexError, ValueError):
            continue
    return records or None


def get_etf_daily(code: str) -> Optional[list]:
    """
    ETF日线 (腾讯财经 qfqday).

    Args:
        code: ETF代码 (如 "159307")

    Returns:
        [{"date", "open", "close", "high", "low", "volume"}, ...]
    """
    return get_kline(code)


def get_index_daily(code: str) -> Optional[list]:
    """
    指数日线 (腾讯财经).

    Args:
        code: 指数代码 (如 "000001" 上证, "399006" 创业板)

    Returns:
        [{"date", "open", "close", "high", "low", "volume"}, ...]
    """
    return get_kline(code)


def get_stock_quote(code: str) -> Dict[str, Any]:
    """
    实时行情 (腾讯财经).

    Returns:
        {name, price, pe_ttm, pb, mcap, turnover, ...}
    """
    result = get_quotes_batch([code])
    return result.get(code, {})


def get_quotes_batch(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    批量实时行情.

    Args:
        codes: 代码列表 (如 ["688017", "300476"])

    Returns:
        {code: {name, price, pe_ttm, pb, mcap_yi, ...}}
    """
    prefixed = []
    for c in codes:
        nc = _normalize_code(c)
        p = _market_prefix(nc)
        prefixed.append(f"{p}{nc}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.content.decode("gbk")
    except Exception:
        return {}

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]  # 去掉 sh/sz 前缀
        result[code] = {
            "name": vals[1],
            "price": _f(vals[3]),
            "last_close": _f(vals[4]),
            "open": _f(vals[5]),
            "change_amt": _f(vals[31]),
            "change_pct": _f(vals[32]),
            "high": _f(vals[33]),
            "low": _f(vals[34]),
            "amount_wan": _f(vals[37]),
            "turnover_pct": _f(vals[38]),
            "pe_ttm": _f(vals[39]),
            "mcap_yi": _f(vals[44]),
            "pb": _f(vals[46]),
            "limit_up": _f(vals[47]),
            "limit_down": _f(vals[48]),
        }
    return result


# ── JRJ (金融界) K线 ──────────────────────────────────────────

JRJ_KLINE_URL = "https://gateway.jrj.com/quot-kline"
JRJ_PRICE_DIVISOR = 10000  # API 价格×10000
JRJ_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 周期映射
_JRJ_PERIOD_MAP = {
    "day": "day", "week": "week", "month": "month",
    "5m": "5minkline", "15m": "15minkline", "30m": "30minkline", "60m": "60minkline",
    # 兼容旧格式
    "5minkline": "5minkline", "15minkline": "15minkline",
    "30minkline": "30minkline", "60minkline": "60minkline",
}


def _jrj_security_id(code: str) -> int:
    """6位代码 → JRJ 内部 securityId (2=mkt_sz, 1=mkt_sh, 0=mkt_bj)."""
    code = code.strip().split(".")[0].strip()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    if code.startswith(("6", "9")):
        return int(f"1{code}")
    elif code.startswith("8"):
        return int(f"0{code}")
    return int(f"2{code}")


def jrj_kline(code: str, period: str = "day", count: int = 180) -> Optional[list]:
    """A股K线 (金融界 gateway.jrj.com, 全周期).

    Args:
        code: 6位代码 (如 "000001")，兼容 sh/sz 前缀
        period: day | week | month | 5m | 15m | 30m | 60m
        count: 返回K线数量

    Returns:
        [{"date","open","close","high","low","volume","amount"}, ...] 或 None
        价格已除10000为元，amount 为元
    """
    period = _JRJ_PERIOD_MAP.get(period, period)
    sid = _jrj_security_id(code)
    params = {
        "format": "json",
        "securityId": str(sid),
        "type": period,
        "direction": "left",
        "range.num": str(count),
    }
    try:
        resp = requests.get(JRJ_KLINE_URL, params=params,
                            headers={"User-Agent": JRJ_UA, "Referer": "https://www.jrj.com.cn/"},
                            timeout=15)
        data = resp.json()
    except Exception as exc:
        logger.warning("jrj_kline failed for %s: %s", code, exc)
        return None

    rows = data.get("data", [])
    if not rows:
        return None

    records = []
    for r in rows:
        try:
            records.append({
                "date": str(r.get("date", "")),
                "open": float(r.get("nOpenPx", 0)) / JRJ_PRICE_DIVISOR,
                "close": float(r.get("nLastPx", 0)) / JRJ_PRICE_DIVISOR,
                "high": float(r.get("nHighPx", 0)) / JRJ_PRICE_DIVISOR,
                "low": float(r.get("nLowPx", 0)) / JRJ_PRICE_DIVISOR,
                "volume": float(r.get("llVolume", 0)),
                "amount": float(r.get("llValue", 0)) / JRJ_PRICE_DIVISOR,
            })
        except (ValueError, TypeError):
            continue
    return records or None


def _f(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0
