"""cnstock.py — 中国证券网财报数据源 (data.cnstock.com/gpsj/cwsj).

数据: 全市场(4000+)股票财报摘要, 每期 ~1.7MB JSON, 覆盖 5 期历史.
来源: https://data.cnstock.com/result/gpsj/cwsj/report_{n}.js (n=1~5)
字段(17个):
    secucode        — 股票代码(6位纯数字)
    secuabbr        — 股票简称
    shouru_benqi    — 营业收入(本期,万元)
    shouru_tongbi   — 营业收入同比(%)
    lirun_benqi     — 净利润(本期,万元)
    lirun_tongbi    — 净利润同比(%)
    shouyi_benqi    — 每股收益(本期)
    shouyi_tongbi   — 每股收益同比(%)
    jingzichan      — 每股净资产
    jingzichan_tongbi — 每股净资产同比(%)
    shouyilv_benqi  — 净资产收益率(%)
    shouyilv_tongbi — 净资产收益率同比(%)
    xianjinliu_benqi — 每股经营活动现金流量
    xianjinliu_tongbi — 每股经营现金流同比(%)
    maolilv_benqi   — 毛利率(%)
    maolilv_tongbi  — 毛利率同比(%)
    fenhong         — 分红预案

用法:
    from stcok_worm import cnstock
    all_periods = cnstock.fetch_all()       # 5期全部
    latest = cnstock.fetch_period(1)        # 最新一期
    panel = cnstock.build_panel('shouru_benqi')  # 收入矩阵
"""
from __future__ import annotations
import json, time, logging
from typing import Optional
import requests
import pandas as pd

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.cnstock.com/gpsj/cwsj/cwsj.html",
}
BASE = "https://data.cnstock.com/result/gpsj/cwsj/report_{}.js"
MAX_PERIODS = 5

_MIN_INTERVAL = 0.3
_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def fetch_period(n: int = 1) -> pd.DataFrame:
    """拉取第 n 期财报摘要(1=最新). 返回 DataFrame(代码,名称,17字段)."""
    url = BASE.format(n)
    try:
        _throttle()
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        d = r.json()
        rows = [row["cell"] for row in d["rows"]]
        df = pd.DataFrame(rows)
        # 数值化
        for col in df.columns:
            if col in ("secucode", "secuabbr", "fenhong"):
                continue
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["period"] = n
        return df
    except Exception as e:
        logger.warning("cnstock fetch_period(%d) failed: %s", n, repr(e)[:80])
        return pd.DataFrame()


def fetch_all(max_periods: int = MAX_PERIODS) -> pd.DataFrame:
    """拉取最近 max_periods 期财报摘要, 合并为一张表."""
    parts = []
    for i in range(1, max_periods + 1):
        df = fetch_period(i)
        if not df.empty:
            parts.append(df)
            logger.info("cnstock period %d: %d 只", i, len(df))
        else:
            break
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_panel(field: str, max_periods: int = MAX_PERIODS) -> pd.DataFrame:
    """构造某个字段的(股票×报告期) 面板矩阵.

    Args:
        field: 字段名, 如 'shouru_benqi', 'lirun_benqi', 'jingzichan' 等.
    Returns:
        DataFrame(index=period, columns=secucode, values=field值).
    """
    raw = fetch_all(max_periods)
    if raw.empty:
        return pd.DataFrame()
    panel = raw.pivot_table(index="period", columns="secucode", values=field, aggfunc="first")
    return panel


if __name__ == "__main__":
    # 自检
    p1 = fetch_period(1)
    print(f"period 1: {len(p1)} 只, 字段: {list(p1.columns)[:10]}...")
    print(p1.head(2).to_string())
    panel = build_panel("shouru_benqi", 3)
    print(f"\n收入面板: {panel.shape}")
    print(panel.head())
