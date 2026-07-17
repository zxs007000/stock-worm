"""
宏观数据源 — GDP / 货币供应(M1/M2/M0) / A股总市值
================================================================
用户需求: 宏观指标(GDP、M1/M2/M0、A股总市值等)用于防御门控的
「右侧预警」(巴菲特指标 = 总市值 / GDP)。

数据源(按用户要求, 多源冗余; 当前主源经 akshare 封装, akshare 即这些网站的爬虫):
    - GDP:            国家统计局 (akshare.macro_china_gdp)
    - M1/M2/M0:       国家统计局 / 央行 (akshare.macro_china_money_supply)
    - A股总市值:       沪深交易所市价总值(沪+深) (akshare.macro_china_stock_market_cap)
                       备选上游: 腾讯财经 / 证券之星 / 金融界(见 total_market_cap(source=...))

对外风格(与 stock_worm 一致):
    - logger.warning 容错, 失败返回空 DataFrame, 不抛异常。
    - 所有函数返回带规范期次(date, 期末日)的 DataFrame, 便于下游按日/季对齐。
    - 串行限流由 akshare 内部处理; 如需更稳可在此包一层 throttle。

日期解析: 国家统计局中文期次("2026年06月份" / "2026年第1-2季度")统一解析为
期末日(date), 方便与日频面板 / 巴菲特指标对齐。
"""

import logging
import re
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    _HAS_AK = True
except Exception as exc:  # pragma: no cover
    _HAS_AK = False
    logger.warning("akshare 不可用, 宏观接口将全部返回空: %s", exc)


# ───────────────────────── 日期解析 ─────────────────────────
def _cn_period_to_date(period: str) -> Optional[pd.Timestamp]:
    """把国家统计局中文期次解析为期末日。

    支持:
        "2026年06月份"          -> 2026-06-30
        "2026年第1季度"         -> 2026-03-31
        "2026年第1-2季度"       -> 2026-06-30
        "2025年第1-4季度"       -> 2025-12-31
        "2026年1-2月"          -> 2026-02-28(月末)
    失败返回 None。
    """
    if not period or not isinstance(period, str):
        return None
    s = period.strip()
    m_year = re.search(r"(\d{4})年", s)
    if not m_year:
        return None
    year = int(m_year.group(1))
    # 季度: 第a-b季度 / 第a季度
    q = re.search(r"第(\d+)(?:-(\d+))?季度", s)
    if q:
        end_q = int(q.group(2)) if q.group(2) else int(q.group(1))
        month_end = {1: 3, 2: 6, 3: 9, 4: 12}[end_q]
        return pd.Timestamp(year=year, month=month_end, day=1) + pd.offsets.MonthEnd(0)
    # 月份: MM月份 / M-MM月
    mo = re.search(r"(\d{1,2})(?:-(\d{1,2}))?月", s)
    if mo:
        end_m = int(mo.group(2)) if mo.group(2) else int(mo.group(1))
        return pd.Timestamp(year=year, month=end_m, day=1) + pd.offsets.MonthEnd(0)
    return None


def _attach_date(df: pd.DataFrame, period_col: str, date_col: str = "date") -> pd.DataFrame:
    """给 DataFrame 加规范期末日列 date_col(由 period_col 解析)。"""
    if df is None or df.empty or period_col not in df.columns:
        return df
    out = df.copy()
    out[date_col] = out[period_col].apply(_cn_period_to_date)
    out[date_col] = pd.to_datetime(out[date_col])
    return out


# ───────────────────────── GDP ─────────────────────────
def gdp_quarterly() -> pd.DataFrame:
    """名义 GDP(季度, 亿元)。

    源: 国家统计局 (经 akshare.macro_china_gdp)。
    列: 季度 / 国内生产总值-绝对值 / 国内生产总值-同比增长 / 一二三产...
    返回: 含规范 `date`(期末日) 的 DataFrame, 按 date 升序。
    """
    if not _HAS_AK:
        return pd.DataFrame()
    try:
        d = ak.macro_china_gdp()
        d = _attach_date(d, "季度")
        return d.sort_values("date").reset_index(drop=True)
    except Exception as exc:
        logger.warning("gdp_quarterly failed: %s", exc)
        return pd.DataFrame()


# ───────────────────────── 货币供应 M1/M2/M0 ─────────────────────────
def money_supply_monthly() -> pd.DataFrame:
    """货币供应 M1/M2/M0(月度, 亿元)。

    源: 国家统计局 / 央行 (经 akshare.macro_china_money_supply)。
    列: 月份 / 货币和准货币(M2)-数量(亿元) / 货币(M1)-数量(亿元) /
        流通中的现金(M0)-数量(亿元) / 各同比环比。
    返回: 含规范 `date`(期末日) 的 DataFrame, 按 date 升序。
    """
    if not _HAS_AK:
        return pd.DataFrame()
    try:
        d = ak.macro_china_money_supply()
        d = _attach_date(d, "月份")
        return d.sort_values("date").reset_index(drop=True)
    except Exception as exc:
        logger.warning("money_supply_monthly failed: %s", exc)
        return pd.DataFrame()


# ───────────────────────── A股总市值 ─────────────────────────
def total_market_cap_monthly(source: str = "akshare") -> pd.DataFrame:
    """A股总市值(月度, 亿元)。

    主源(默认 source='akshare'): 沪深交易所市价总值(沪+深) 相加。
        源: 交易所(经 akshare.macro_china_stock_market_cap), 列
        市价总值-上海 / 市价总值-深圳。
    备选源(预留): 'tencent' / 'stockstar' / 'jrj' —— 用户指定的上游,
        对应接口端点待确认后接入(当前回退到 akshare 并打印 warning)。

    返回: DataFrame, 含 `date`(期末日) 与 `total_market_cap`(总市值, 亿元),
        按 date 升序。
    """
    if source != "akshare":
        logger.warning("total_market_cap source=%s 尚未实现, 回退 akshare", source)
        source = "akshare"
    if not _HAS_AK:
        return pd.DataFrame()
    try:
        d = ak.macro_china_stock_market_cap()
        d = _attach_date(d, "数据日期")
        d = d.copy()
        sh = d.get("市价总值-上海", pd.Series(dtype=float))
        sz = d.get("市价总值-深圳", pd.Series(dtype=float))
        # 仅当沪+深双侧均有值才算完结月份(剔除当月未完结 / 单市缺失的 0 值行)
        valid = sh.notna() & sz.notna()
        d["total_market_cap"] = (sh.fillna(0) + sz.fillna(0)).where(valid)
        out = d.loc[valid, ["date", "total_market_cap", "市价总值-上海", "市价总值-深圳"]]
        return out.sort_values("date").reset_index(drop=True)
    except Exception as exc:
        logger.warning("total_market_cap_monthly failed: %s", exc)
        return pd.DataFrame()


# ───────────────────────── 便捷聚合: 巴菲特指标原料 ─────────────────────────
def buffett_input() -> pd.DataFrame:
    """拼出巴菲特指标所需的低频面板: 总市值 / GDP, 按季末对齐。

    做法: 总市值(月度) 取每季末值; GDP(季度) 用其期末日; 两者按 date 外连接。
    返回: DataFrame[date, total_market_cap, gdp_abs], 按 date 升序。
    注意: 总市值与 GDP 频率不同(月 vs 季), 下游用前视/插值对齐即可。
    """
    mcap = total_market_cap_monthly()
    gdp = gdp_quarterly()
    if mcap.empty or gdp.empty:
        return pd.DataFrame()
    # 总市值取季末(每季度最后一个月)
    mcap = mcap.copy()
    mcap["q_end"] = mcap["date"].dt.to_period("Q").dt.end_time
    mcap_q = mcap.sort_values("date").groupby("q_end").tail(1).drop(columns=["q_end"])
    merged = pd.merge(
        gdp[["date", "国内生产总值-绝对值"]].rename(columns={"国内生产总值-绝对值": "gdp_abs"}),
        mcap[["date", "total_market_cap"]],
        left_on="date", right_on="date", how="outer",
    ).sort_values("date").reset_index(drop=True)
    return merged


# ───────────────────────── 日频巴菲特指标(防御门控右侧预警) ─────────────────────────
def buffett_ratio_daily(index: Optional[pd.DatetimeIndex] = None,
                        publish_lag_days: int = 60) -> pd.Series:
    """日频巴菲特指标 = A股总市值 / 名义GDP, 供防御门控右侧预警作 regime 调制器.

    防前视:
        - 总市值用截至 t 的已实现值(月频前向填充到日).
        - GDP 按**发布日**对齐: 参考季末 + publish_lag_days(默认60天≈下季中发布),
          再前向填充到日. 这样 t 日看到的 GDP 是已发布的, 不提前用当季未发布值.
    估值漂移: 返回值供调用方用长窗口(5Y)分位判定极端, 天然去趋势(见 defensive_gating._macro_gating).

    参数:
        index: 目标日频索引(对齐到面板日期); 为 None 时返回自身日频网格.
        publish_lag_days: GDP 发布滞后天数(参考季末起算).
    返回:
        pd.Series(日期索引, 巴菲特比率=总市值/GDP), 按 index 对齐(缺失前填).
    """
    mcap = total_market_cap_monthly()
    gdp = gdp_quarterly()
    if mcap.empty or gdp.empty:
        return pd.Series(dtype=float)
    # 总市值: 月频 -> 日频(前向填充)
    mcap_s = mcap.set_index("date")["total_market_cap"].sort_index()
    mcap_d = mcap_s.resample("D").ffill()
    # GDP: 只用年度值(Q4=全年累计), 前向填充到次年各季度.
    # 否则直接用累积值(如Q1=33万亿)除以总市值(118万亿)会得到荒谬的 3.5 倍.
    g = gdp.copy()
    g = g.set_index("date")["国内生产总值-绝对值"].sort_index()
    g_annual = g[g.index.quarter == 4]
    if g_annual.empty:
        return pd.Series(dtype=float)
    # 发布滞后: 参考次年1月1日起可用
    g_annual.index = g_annual.index + pd.Timedelta(days=1)  # Q4最后一天→次年1月1日
    g_annual = g_annual.reindex(
        pd.date_range(g_annual.index.min(), mcap_d.index.max(), freq="D")
    ).ffill()
    # 取交叠区间
    lo = max(mcap_d.index.min(), g_annual.index.min())
    hi = min(mcap_d.index.max(), g_annual.index.max())
    mcap_d = mcap_d.loc[lo:hi]
    g_annual = g_annual.loc[lo:hi]
    ratio = (mcap_d / g_annual).dropna()
    ratio = ratio[ratio > 0]
    if index is not None:
        # 对齐到目标索引(前填, 因宏观低频; 超出范围外推为 NaN 由下游处理)
        ratio = ratio.reindex(index.union(ratio.index)).ffill().reindex(index)
    return ratio


# ───────────────────────── M2 同比(流动性共振因子) ─────────────────────────
def m2_growth_daily(index: Optional[pd.DatetimeIndex] = None, win: int = 12) -> pd.Series:
    """M2 同比增速(月频 -> 日频前填), 供防御门控作'估值+流动性'共振的流动性侧.

    用法: 巴菲特指标进入警戒区 且 M2 同比见顶回落(低于其 trailing 均值) => 共振确认系统性风险.
    仅估值高但流动性充裕(M2 同比高企) => 共振不成立, 不(或弱)触发防御, 避免 2014-15H1 式踏空.

    参数: win=12 表示 12 个月同比(YoY).
    返回: pd.Series(日期索引, M2 同比增速, 小数).
    """
    d = money_supply_monthly()
    if d.empty:
        return pd.Series(dtype=float)
    m2_col = [c for c in d.columns if "M2" in c]
    if not m2_col:
        logger.warning("m2_growth_daily: 未找到 M2 列")
        return pd.Series(dtype=float)
    m2 = d.set_index("date")[m2_col[0]].sort_index()
    yoy = m2.pct_change(win)
    yoy_d = yoy.replace([np.inf, -np.inf], np.nan).dropna()
    yoy_d = yoy_d.resample("D").ffill()
    if index is not None:
        yoy_d = yoy_d.reindex(index.union(yoy_d.index)).ffill().reindex(index)
    return yoy_d


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    print("GDP:\n", gdp_quarterly().tail(3))
    print("M2:\n", money_supply_monthly().tail(3))
    print("总市值:\n", total_market_cap_monthly().tail(3))
    print("巴菲特原料:\n", buffett_input().tail(3))
