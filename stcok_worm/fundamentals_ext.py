"""
基本面扩展数据源 — 基于 akshare 封装（东财 F10 财报 / 分红 / 解禁）。

与 fundamentals.py 的区别：
    fundamentals.py   用东财 datacenter 直连（季报快照 RPT_LICO_FN_CPD、实时 company_info）
    fundamentals_ext  用 akshare 的东财 F10 实现，补齐：
        - 86 个预计算财务比率（季度，因子金矿）
        - 三张表原表（利润表 / 资产负债表 / 现金流量表）
        - 分红历史汇总（全市场一次性）
        - 限售股解禁事件（按日期区间批量）

所有函数返回 pandas.DataFrame；失败返回空 DataFrame，不会抛异常。
对外遵循 stock_worm 风格：logger.warning 容错 + 串行限流。
"""

import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)

# 关键：akshare 内部 requests 无 timeout，个别股票请求会永久挂死。
# 全局给 requests.Session.request 注入 20s 超时（Windows 无 signal.alarm，用 monkeypatch 最稳）。
import requests  # noqa: E402

_ORIG_REQUEST = requests.Session.request


def _patched_request(self, method, url, **kwargs):
    kwargs.setdefault("timeout", 20)
    return _ORIG_REQUEST(self, method, url, **kwargs)


requests.Session.request = _patched_request

# 限流：akshare 内部已有限流，这里再垫一层保险。
# 东财 F10 接口稳定，批量构建数据湖时压到 0.5s/只（约 2 req/s）以缩短总时长。
_MIN_INTERVAL = 0.5
_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _prefix(code: str) -> str:
    """6 位代码 → 东财 F10 前缀 (SH/SZ/BJ)。"""
    code = code.strip().split(".")[0]
    if code.startswith(("6", "9")):
        return "SH" + code
    if code.startswith("8"):
        return "BJ" + code
    return "SZ" + code


# 东财版财务分析指标列码 → 干净英文名映射（已与 sina 版已知值交叉校验）
_EM_RENAME = {
    "REPORT_DATE": "date",
    "EPSJB": "eps",
    "EPSKCJB": "eps_diluted",
    "BPS": "bps",
    "MGZBGJ": "capital_reserve_ps",
    "MGWFPLR": "undistributed_ps",
    "MGJYXJJE": "ocf_ps",
    "TOTALOPERATEREVE": "revenue",
    "PARENTNETPROFIT": "net_profit",
    "KCFJCXSYJLR": "deduct_np",
    "TOTALOPERATEREVETZ": "revenue_yoy",
    "PARENTNETPROFITTZ": "net_profit_yoy",
    "KCFJCXSYJLRTZ": "deduct_np_yoy",
    "ROEJQ": "roe",
    "ZZCJLL": "roa",
    "XSJLL": "net_margin",
    "XSMLL": "gross_margin",
    "JYXJLYYSR": "ocf_to_revenue",
    "LD": "current_ratio",
    "SD": "quick_ratio",
    "XJLLB": "cash_ratio",
    "ZCFZL": "debt_to_asset",
    "QYCS": "equity_multiplier",
    "ZZCZZTS": "asset_turnover",
    "CHZZTS": "inventory_turnover",
    "YSZKZZTS": "receivable_turnover",
    "ROIC": "roic",
    "EPSJBTZ": "eps_yoy",
    "ROEJQTZ": "roe_yoy",
    "BPSTZ": "bps_yoy",
    "MGJYXJJETZ": "ocf_ps_yoy",
    "ZZCJLLTZ": "roa_yoy",
    "ZCFZLTZ": "debt_to_asset_yoy",
    "XSMLL_TB": "gross_margin_yoy",
    "INTEREST_COVERAGE_RATIO": "interest_coverage",
    "MGZBGJTZ": "capital_reserve_ps_yoy",
    "MGWFPLRTZ": "undistributed_ps_yoy",
}


def _suffix(code: str) -> str:
    code = code.strip().split(".")[0]
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith("8"):
        return "BJ"
    return "SZ"


def financial_indicators(code: str, start_year: str = "2006") -> pd.DataFrame:
    """个股财务分析指标（季度，东财版，141 列全历史，~0.2s/只）。

    用 stock_financial_analysis_indicator_em（走 eastmoney，稳定快速），
    不走高延迟且常超时的新浪接口。返回干净列：code, date, eps, bps, roe,
    gross_margin, net_margin, revenue_yoy, net_profit_yoy, debt_to_asset,
    current_ratio, roic, asset_turnover ... 直接可做基本面因子。
    """
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_financial_analysis_indicator_em(
            symbol=f"{code}.{_suffix(code)}", indicator="按报告期")
    except Exception as exc:
        logger.warning("financial_indicators %s failed: %s", code, exc)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    want = {k: v for k, v in _EM_RENAME.items() if k in df.columns}
    out = df[list(want.keys())].rename(columns=want).copy()
    out.insert(0, "code", code)
    return out


def income_statement(code: str) -> pd.DataFrame:
    """利润表（东财 F10，含同比）。"""
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_profit_sheet_by_report_em(symbol=_prefix(code))
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.insert(0, "code", code)
        return df
    except Exception as exc:
        logger.warning("income_statement failed for %s: %s", code, exc)
        return pd.DataFrame()


def balance_sheet(code: str) -> pd.DataFrame:
    """资产负债表（东财 F10，含同比）。"""
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_balance_sheet_by_report_em(symbol=_prefix(code))
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.insert(0, "code", code)
        return df
    except Exception as exc:
        logger.warning("balance_sheet failed for %s: %s", code, exc)
        return pd.DataFrame()


def cash_flow_statement(code: str) -> pd.DataFrame:
    """现金流量表（东财 F10，含同比）。"""
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_cash_flow_sheet_by_report_em(symbol=_prefix(code))
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.insert(0, "code", code)
        return df
    except Exception as exc:
        logger.warning("cash_flow_statement failed for %s: %s", code, exc)
        return pd.DataFrame()


def dividend_summary_all() -> pd.DataFrame:
    """全市场分红历史汇总（1 次调用）。

    返回：代码, 名称, 上市日期, 累计股息, 年均股息, 分红次数, 融资总额, 融资次数。
    用于构造股息率/分红稳定性因子。
    """
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_history_dividend()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"代码": "code", "名称": "name"})
        return df
    except Exception as exc:
        logger.warning("dividend_summary_all failed: %s", exc)
        return pd.DataFrame()


def unlock_detail(start_date: str, end_date: str) -> pd.DataFrame:
    """限售股解禁事件（按日期区间批量）。

    start_date/end_date 格式 'YYYYMMDD'。返回解禁明细：
    代码、名称、解禁日期、解禁数量、解禁比例、总股本、流通股本等。
    """
    import akshare as ak
    try:
        _throttle()
        df = ak.stock_restricted_release_detail_em(
            start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.copy()
    except Exception as exc:
        logger.warning("unlock_detail %s~%s failed: %s", start_date, end_date, exc)
        return pd.DataFrame()
