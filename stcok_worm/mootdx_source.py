"""
通达信 TCP 数据源 — 基于 tdxpy 直连

功能:
    - get_kline(code, freq)    — K线 (日/周/月)
    - get_quote(code)           — 实时行情
    - get_finance(code)         — 财务数据
    - get_xdxr(code)            — 除权除息

数据源: 通达信 TCP 协议 (端口 7709)，不封 IP
依赖: pip install tdxpy (无 httpx 冲突)
"""

import logging
import random
from typing import Any, Dict, List, Optional

try:
    from tdxpy.constants import TDXParams
    from tdxpy.hq import TdxHq_API
except Exception:  # tdxpy is an optional dependency (mootdx TCP only)
    TDXParams = None
    TdxHq_API = None

logger = logging.getLogger(__name__)

# 服务器列表 (电信优先，延迟低)
_SERVERS = [
    ("180.153.18.170", 7709),
    ("180.153.18.171", 7709),
    ("202.108.253.130", 7709),
    ("60.191.117.167", 7709),
    ("115.238.56.198", 7709),
    ("218.75.126.9", 7709),
    ("14.17.75.71", 7709),
    ("114.80.63.12", 7709),
    ("180.153.39.51", 7709),
]

_api: Optional[TdxHq_API] = None
_connected = False


def _get_api() -> Optional[TdxHq_API]:
    """获取或重建连接。"""
    global _api, _connected

    if TdxHq_API is None:
        return None

    if _api and _connected:
        return _api

    # 打乱顺序，分散连接
    servers = list(_SERVERS)
    random.shuffle(servers)

    for ip, port in servers:
        try:
            api = TdxHq_API()
            if api.connect(ip, port, time_out=3):
                _api = api
                _connected = True
                logger.debug("tdxpy connected to %s:%d", ip, port)
                return api
        except Exception as e:
            logger.debug("tdxpy connect failed %s:%d: %s", ip, port, e)
            continue

    logger.warning("tdxpy 所有服务器连接失败")
    _connected = False
    return None


def _market(code: str) -> int:
    """0=深交所, 1=上交所"""
    code = code.strip().split(".")[0]
    if code.startswith(("6", "9")):
        return TDXParams.MARKET_SH
    elif code.startswith("8"):
        return 2  # 北交所
    return TDXParams.MARKET_SZ


def _raw_code(code: str) -> str:
    """去除前缀，取6位纯代码。"""
    code = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
    return code.split(".")[0][:6]


def available() -> bool:
    """检查 tdxpy 是否可用。"""
    try:
        import tdxpy  # noqa: F401
        return True
    except ImportError:
        return False


def get_kline(code: str, freq: int = 9, count: int = 800) -> Optional[list]:
    """
    K线数据 (通达信 TCP).

    Args:
        code: 6位代码
        freq: 9=日K, 5=周K, 6=月K, 0=5分钟, 1=15分钟, 2=30分钟, 3=1小时
        count: 最多800条

    Returns:
        [{"date", "open", "close", "high", "low", "volume", "amount"}, ...]
    """
    api = _get_api()
    if not api:
        return None

    raw = _raw_code(code)
    market = _market(code)

    try:
        data = api.get_security_bars(freq, market, raw, 0, count)
        if not data:
            return None
        records = []
        for item in data:
            records.append({
                "date": str(item.get("datetime", ""))[:10],
                "open": float(item.get("open", 0)),
                "close": float(item.get("close", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "volume": float(item.get("vol", 0)),
                "amount": float(item.get("amount", 0)),
            })
        return records
    except Exception as e:
        logger.warning("tdxpy K线失败 %s: %s", code, e)
        _disconnect()
        return None


def get_quote(code: str) -> Optional[Dict[str, Any]]:
    """
    实时行情 (通达信 TCP).

    Returns:
        {price, open, high, low, last_close, volume, amount,
         bid1, ask1, bid_vol1, ask_vol1, ...}
    """
    api = _get_api()
    if not api:
        return None

    raw = _raw_code(code)
    market = _market(code)

    if market == 2:  # 北交所暂不支持
        return None

    try:
        data = api.get_security_quotes([(market, raw)])
        if not data:
            return None
        item = data[0]
        return {
            "name": item.get("code", raw),
            "price": float(item.get("price", 0)),
            "last_close": float(item.get("last_close", 0)),
            "open": float(item.get("open", 0)),
            "high": float(item.get("high", 0)),
            "low": float(item.get("low", 0)),
            "volume": float(item.get("vol", 0)),
            "amount": float(item.get("amount", 0)),
            "bid1": float(item.get("bid1", 0)),
            "ask1": float(item.get("ask1", 0)),
            "bid_vol1": float(item.get("bid_vol1", 0)),
            "ask_vol1": float(item.get("ask_vol1", 0)),
            "change_pct": float(item.get("percent", 0)),
            "pe_ttm": float(item.get("pe_ttm", 0)),
        }
    except Exception as e:
        logger.warning("tdxpy 行情失败 %s: %s", code, e)
        _disconnect()
        return None


def get_finance(code: str) -> Optional[Dict[str, Any]]:
    """
    财务数据 (通达信 TCP).

    Returns:
        {37字段: liutongguben, zongguben, zongzichan, ...,}
    """
    api = _get_api()
    if not api:
        return None

    raw = _raw_code(code)
    market = _market(code)

    try:
        data = api.get_finance_info(market, raw)
        if not data:
            return None
        return data
    except Exception as e:
        logger.warning("tdxpy 财务失败 %s: %s", code, e)
        _disconnect()
        return None


def get_xdxr(code: str) -> Optional[list]:
    """
    除权除息数据 (通达信 TCP).

    Returns:
        [{year, month, day, category, fenhong, peigujia, ...}, ...]
    """
    api = _get_api()
    if not api:
        return None

    raw = _raw_code(code)
    market = _market(code)

    try:
        data = api.get_xdxr_info(market, raw)
        if not data:
            return None
        return data
    except Exception as e:
        logger.warning("tdxpy 除权除息失败 %s: %s", code, e)
        _disconnect()
        return None


def get_index_kline(code: str, freq: int = 9, count: int = 800) -> Optional[list]:
    """
    指数K线 (通达信 TCP).

    Args:
        code: 指数代码 (如 000001, 399006)
        freq: 同 get_kline
    """
    api = _get_api()
    if not api:
        return None

    raw = _raw_code(code)
    market = _market(code)

    try:
        data = api.get_index_bars(freq, market, raw, 0, count)
        if not data:
            return None
        records = []
        for item in data:
            records.append({
                "date": str(item.get("datetime", ""))[:10],
                "open": float(item.get("open", 0)),
                "close": float(item.get("close", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "volume": float(item.get("vol", 0)),
                "amount": float(item.get("amount", 0)),
            })
        return records
    except Exception as e:
        logger.warning("tdxpy 指数K线失败 %s: %s", code, e)
        _disconnect()
        return None


def _disconnect():
    """断开连接，下次调用自动重连。"""
    global _api, _connected
    if _api:
        try:
            _api.disconnect()
        except Exception:
            pass
    _api = None
    _connected = False
