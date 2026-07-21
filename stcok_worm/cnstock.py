"""cnstock.py — 中国证券网财报数据源 (data.cnstock.com/gpsj/cwsj).

⚠️⚠️⚠️  IP 封禁高风险警告 ⚠️⚠️⚠️
--------------------------------------------------------------------------
data.cnstock.com 对「高频 / 并发」访问极度敏感。实测: 用 8 线程并发猛打
stock_detail() 接口, 约 200 次请求后整域返回 403 Forbidden(IP 级封禁),
个股口与批量口同时失效, 且封禁持续时间不定(数分钟~数小时)。
>>> 因此本模块已内置全局限速 + 并发上限 + 403/429 指数退避, 任何调用方
    都不要再自行开高并发(ThreadPoolExecutor workers 请 <= SAFE_WORKERS)。
>>> 若仍看到 403, 立刻停手等封禁解除, 不要硬刚(越刚封得越久)。
>>> 解封后可降速(workers=2, 本模块间隔>=MIN_INTERVAL)重爬补齐。
--------------------------------------------------------------------------

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
import json, time, logging, threading
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

# ───────────────────── 防封 IP 的全局限速器 ─────────────────────
# 关键教训: 旧版 _throttle 只保证「两次调用间隔>=0.3s」, 但多线程并发时
# 8 个线程会同时越过检查, 瞬间打出 8 个请求 -> 触发整域 403 封禁。
# 新版用「全局锁 + 信号量」强制:
#   - 任意时刻最多 SAFE_CONCURRENCY 个并发请求
#   - 相邻请求(全局)至少间隔 MIN_INTERVAL 秒
#   - 遇到 403/429 立即指数退避, 绝不停火硬刚
MIN_INTERVAL = 1.0          # 全局相邻请求最小间隔(秒)
SAFE_CONCURRENCY = 2        # 全局最大并发请求数(防封上限, 调用方勿超越)
_MAX_RETRY = 4              # 403/429 退避重试次数
_RATE_LOCK = threading.Lock()
_LAST_CALL = [0.0]
_SEM = threading.Semaphore(SAFE_CONCURRENCY)


def _rate_limit():
    """线程安全的全局限速: 保证相邻请求间隔 >= MIN_INTERVAL。"""
    with _RATE_LOCK:
        now = time.time()
        wait = MIN_INTERVAL - (now - _LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[0] = time.time()


def _get(url: str):
    """带防封保护的 GET: 全局并发<=SAFE_CONCURRENCY, 间隔>=MIN_INTERVAL,
    遇 403/429 指数退避(不硬刚, 避免延长 IP 封禁)。失败返回 None。"""
    delay = 2.0
    for _ in range(_MAX_RETRY):
        with _SEM:
            _rate_limit()
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
            except Exception as e:
                logger.warning("cnstock GET %s 异常: %s", url, repr(e)[:80])
                time.sleep(delay)
                delay *= 2
                continue
        if r.status_code in (403, 429):
            # 反爬/限流: 退避后重试; 多次仍失败则放弃(返回 None)
            logger.warning("cnstock %s 被限流(HTTP %d), 退避 %.1fs", url, r.status_code, delay)
            time.sleep(delay)
            delay *= 2
            continue
        try:
            r.raise_for_status()
            return r
        except Exception as e:
            logger.warning("cnstock GET %s 失败: %s", url, repr(e)[:80])
            time.sleep(delay)
            delay *= 2
            continue
    logger.warning("cnstock %s 经 %d 次重试仍失败(疑似 IP 封禁), 放弃", url, _MAX_RETRY)
    return None


def fetch_period(n: int = 1) -> pd.DataFrame:
    """拉取第 n 期财报摘要(1=最新). 返回 DataFrame(代码,名称,17字段)."""
    url = BASE.format(n)
    try:
        r = _get(url)
        if r is None:
            return pd.DataFrame()
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


def stock_detail(code: str) -> pd.DataFrame:
    """爬取个股财务摘要全历史(中国证券网个股详情页).

    ⚠️ 此接口是 403 封禁的主因(被 8 并发打挂过)。本模块已用 _get() 限速+
    退避保护, 但调用方仍需低并发(workers<=SAFE_CONCURRENCY)。若返回空 DF
    且日志出现 403, 说明 IP 已被封, 请停止并等待解封, 切勿循环硬刚。

    URL: https://data.cnstock.com/gpsj/cwsj/{code}.html
    返回: DataFrame(index=报告期, columns=14个指标), 含 23 年(2001-2024)季报数据.
    """
    import re
    code = str(code).split(".")[0]
    url = f"https://data.cnstock.com/gpsj/cwsj/{code}.html"
    try:
        r = _get(url)
        if r is None:
            return pd.DataFrame()
        r.encoding = "utf-8"
    except Exception as e:
        logger.warning("cnstock stock_detail(%s) fetch failed: %s", code, repr(e)[:80])
        return pd.DataFrame()
    tables = re.findall(r"<table[^>]*>(.*?)</table>", r.text, re.S)
    if not tables:
        return pd.DataFrame()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S)
    cols = ["序号", "报告期", "净利润同比", "每股收益(本期)", "每股收益(同比)",
            "每股净资产(本期)", "每股净资产(同比)", "净资产收益率(本期)", "净资产收益率(同比)",
            "每股现金流(本期)", "每股现金流(同比)", "毛利率(本期)", "毛利率(同比)", "分配方案"]
    data = []
    for r in rows[3:]:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(clean) >= len(cols):
            data.append(clean[: len(cols)])
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=cols)
    for c in df.columns[2:13]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "报告期" in df.columns:
        df["报告期"] = pd.to_datetime(df["报告期"], errors="coerce")
        df = df.set_index("报告期").sort_index()
    return df


if __name__ == "__main__":
    # 自检
    p1 = fetch_period(1)
    print(f"period 1: {len(p1)} 只, 字段: {list(p1.columns)[:10]}...")
    print(p1.head(2).to_string())
    panel = build_panel("shouru_benqi", 3)
    print(f"\n收入面板: {panel.shape}")
    print(panel.head())
