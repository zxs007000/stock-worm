"""
实时行情 + 历史数据 双数据源调度

数据源分工:
    - Sina (easyquotation): 盘中实时轮询，500ms 级别，5档盘口
    - TDX (tdxpy):          K线/财务/除权除息，按需拉取，不封IP

用法:
    from stcok_worm.realtime import RealtimeQuote

    rt = RealtimeQuote()

    # 实时行情（盘中轮询）
    q = rt.quote("600519")

    # 批量实时
    quotes = rt.quotes(["600519", "000858", "300750"])

    # K线（通达信）
    klines = rt.kline("600519", count=100)

    # 异动检测
    alerts = rt.detect_anomaly("600519", volume_ratio=3.0, price_change=2.0)
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import easyquotation
    _sina = easyquotation.use("sina")
    _has_sina = True
except ImportError:
    _has_sina = False
    _sina = None

try:
    from .mootdx_source import get_kline, get_quote as tdx_quote, get_finance, get_xdxr
    _has_tdx = True
except ImportError:
    _has_tdx = False


class RealtimeQuote:
    """实时行情 + 历史数据统一入口。"""

    def __init__(self, poll_interval: float = 0.5):
        """
        Args:
            poll_interval: 新浪轮询最小间隔（秒），默认0.5s
        """
        self.poll_interval = poll_interval
        self._last_poll = 0.0
        self._quote_cache: Dict[str, dict] = {}
        self._tick_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

    def quote(self, code: str) -> Optional[dict]:
        """
        单只股票实时行情。

        Returns:
            {name, price, open, high, low, last_close, volume, amount,
             bid1-5, ask1-5, bid1_vol-5_vol, ask1_vol-5_vol, change_pct, ...}
        """
        codes = [code.strip().split(".")[0][-6:]]
        result = self.quotes(codes)
        return result.get(codes[0])

    def quotes(self, codes: List[str]) -> Dict[str, dict]:
        """
        批量实时行情（新浪源）。

        Args:
            codes: 6位代码列表

        Returns:
            {code: {price, bid1, ask1, volume, ...}}
        """
        if not _has_sina:
            logger.warning("easyquotation 未安装: pip install easyquotation")
            return {}

        # 限流
        now = time.time()
        wait = self.poll_interval - (now - self._last_poll)
        if wait > 0:
            time.sleep(wait)

        clean_codes = [c.strip().split(".")[0][-6:] for c in codes]
        try:
            raw = _sina.real(clean_codes)
        except Exception as e:
            logger.warning("新浪行情失败: %s", e)
            return {}

        self._last_poll = time.time()

        result = {}
        for code, info in raw.items():
            parsed = {
                "code": code,
                "name": info.get("name", ""),
                "price": _f(info.get("now")),
                "open": _f(info.get("open")),
                "high": _f(info.get("high")),
                "low": _f(info.get("low")),
                "last_close": _f(info.get("close")),
                "volume": _f(info.get("volume")),
                "amount": _f(info.get("amount")),
                "change_pct": _f(info.get("percent")),
                "turnover": _f(info.get("turnover")),
                "pe_ttm": _f(info.get("pe")),
                "bid1": _f(info.get("bid1")),
                "bid2": _f(info.get("bid2")),
                "bid3": _f(info.get("bid3")),
                "bid4": _f(info.get("bid4")),
                "bid5": _f(info.get("bid5")),
                "bid1_vol": _f(info.get("bid1_volume")),
                "bid2_vol": _f(info.get("bid2_volume")),
                "bid3_vol": _f(info.get("bid3_volume")),
                "bid4_vol": _f(info.get("bid4_volume")),
                "bid5_vol": _f(info.get("bid5_volume")),
                "ask1": _f(info.get("ask1")),
                "ask2": _f(info.get("ask2")),
                "ask3": _f(info.get("ask3")),
                "ask4": _f(info.get("ask4")),
                "ask5": _f(info.get("ask5")),
                "ask1_vol": _f(info.get("ask1_volume")),
                "ask2_vol": _f(info.get("ask2_volume")),
                "ask3_vol": _f(info.get("ask3_volume")),
                "ask4_vol": _f(info.get("ask4_volume")),
                "ask5_vol": _f(info.get("ask5_volume")),
                "timestamp": time.time(),
            }
            result[code] = parsed

            # 记录 tick 历史用于异动检测
            self._tick_history[code].append(parsed)

        return result

    def kline(self, code: str, freq: int = 9, count: int = 200) -> Optional[list]:
        """
        K线数据（通达信源）。

        Args:
            freq: 9=日K, 5=周K, 6=月K, 0=5分钟, 1=15分钟, 2=30分钟, 3=1小时
        """
        if not _has_tdx:
            logger.warning("tdxpy 未安装")
            return None
        return get_kline(code, freq=freq, count=count)

    def finance(self, code: str) -> Optional[dict]:
        """财务数据（通达信源）。"""
        if not _has_tdx:
            return None
        return get_finance(code)

    def xdxr(self, code: str) -> Optional[list]:
        """除权除息（通达信源）。"""
        if not _has_tdx:
            return None
        return get_xdxr(code)

    def detect_anomaly(
        self,
        code: str,
        volume_ratio: float = 3.0,
        price_change: float = 2.0,
        bid_ask_imbalance: float = 0.7,
    ) -> List[dict]:
        """
        异动检测（基于最近 tick 历史）。

        Args:
            volume_ratio: 量比阈值（当前成交量 / 前N笔均量）
            price_change: 涨跌幅突变阈值（%）
            bid_ask_imbalance: 买卖盘失衡阈值（0-1）

        Returns:
            [{type, detail, value, threshold}, ...]
        """
        ticks = self._tick_history.get(code)
        if not ticks or len(ticks) < 2:
            return []

        alerts = []
        latest = ticks[-1]
        prev = ticks[-2] if len(ticks) >= 2 else latest

        # 1. 涨跌幅突变
        pct_now = latest.get("change_pct", 0)
        pct_prev = prev.get("change_pct", 0)
        if abs(pct_now - pct_prev) >= price_change:
            alerts.append({
                "type": "price_spike",
                "detail": f"涨跌幅突变 {pct_prev:.2f}% → {pct_now:.2f}%",
                "value": pct_now - pct_prev,
                "threshold": price_change,
            })

        # 2. 量比异常
        if len(ticks) >= 5:
            recent_vols = [t.get("volume", 0) for t in list(ticks)[-5:-1]]
            avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
            cur_vol = latest.get("volume", 0)
            if avg_vol > 0 and cur_vol / avg_vol >= volume_ratio:
                alerts.append({
                    "type": "volume_spike",
                    "detail": f"量比异常 {cur_vol/avg_vol:.1f}x (阈值{volume_ratio}x)",
                    "value": cur_vol / avg_vol,
                    "threshold": volume_ratio,
                })

        # 3. 买卖盘失衡
        bid_total = sum(latest.get(f"bid{i}_vol", 0) for i in range(1, 6))
        ask_total = sum(latest.get(f"ask{i}_vol", 0) for i in range(1, 6))
        total = bid_total + ask_total
        if total > 0:
            bid_ratio = bid_total / total
            if bid_ratio >= bid_ask_imbalance:
                alerts.append({
                    "type": "bid_heavy",
                    "detail": f"买盘强势 {bid_ratio:.0%} (买{bid_total} vs 卖{ask_total})",
                    "value": bid_ratio,
                    "threshold": bid_ask_imbalance,
                })
            elif bid_ratio <= (1 - bid_ask_imbalance):
                alerts.append({
                    "type": "ask_heavy",
                    "detail": f"卖盘强势 {1-bid_ratio:.0%} (卖{ask_total} vs 买{bid_total})",
                    "value": 1 - bid_ratio,
                    "threshold": bid_ask_imbalance,
                })

        return alerts

    def tick_history(self, code: str) -> list:
        """获取最近 tick 历史。"""
        return list(self._tick_history.get(code, []))


def _f(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0
