"""
监管事件数据源 — stock_worm 的新能力（最高价值、零成本）。

数据源：
    巨潮披露（CNINFO）个股公告 + 东方财富个股公告，二者均为公开、免费、结构化。
    逐只拉取全部公告，按「公告标题」关键词做严重度分级，只保留监管类事件。

覆盖的监管事件（按严重度 3→1）：
    3 立案调查 / 行政处罚 / 公开谴责 / 市场禁入
    2 通报批评 / 监管函 / 监管关注函 / 警示函 / 责令整改 / 约谈
    1 问询函 / 关注函 / 监管问询

为什么值得做：
    监管事件是最强的负面事件信号之一——立案/处罚往往领先于业绩爆雷、ST、退市；
    且数据完全公开、无需付费、量级小（全市场每年数千条），是性价比最高的因子源。

对外风格：复用 fundamentals_ext 的 20s 超时补丁 + 限流；失败返回空 DataFrame。
"""

import logging
import re
import time

import pandas as pd

logger = logging.getLogger(__name__)

# 复用 fundamentals_ext 的全局 20s 超时补丁与限流（导入即生效）
from .fundamentals_ext import _throttle  # noqa: F401

# 严重度分级（3 最严重）
_SEVERITY_KEYWORDS = {
    3: ["立案调查", "立案通知书", "立案告知", "行政处罚", "处罚决定书",
        "收到处罚", "公开谴责", "市场禁入"],
    2: ["通报批评", "监管函", "监管关注函", "监管工作函", "警示函",
        "责令", "责令改正", "公开致歉", "约见", "约谈"],
    1: ["问询函", "问询", "关注函", "监管问询", "工作函"],
}
_PATTERNS = {sev: re.compile("|".join(map(re.escape, kws)))
             for sev, kws in _SEVERITY_KEYWORDS.items()}

SEVERITY_LABEL = {
    3: "立案/处罚/谴责",
    2: "监管函/警示/通报",
    1: "问询/关注",
}


def classify_title(title: str):
    """返回 (severity, label)，非监管事件返回 (0, None)。按 3→2→1 顺序保证最高严重度优先。"""
    title = title or ""
    for sev in (3, 2, 1):
        if _PATTERNS[sev].search(title):
            return sev, SEVERITY_LABEL[sev]
    return 0, None


def _normalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """把 akshare 两种返回结构统一成 (code, event_date, title, notice_type, url)。"""
    if source == "cninfo":
        cols = {"代码": "code", "公告标题": "title", "公告时间": "event_date",
                "公告链接": "url", "简称": "_name"}
    else:  # eastmoney notice
        cols = {"代码": "code", "公告标题": "title", "公告日期": "event_date",
                "网址": "url", "公告类型": "notice_type", "名称": "_name"}
    out = df.rename(columns=cols)
    keep = [c for c in ["code", "title", "event_date", "url", "notice_type"] if c in out.columns]
    out = out[keep].copy()
    out["event_date"] = pd.to_datetime(out["event_date"], errors="coerce")
    return out


def regulatory_events(code: str, start_date: str = "20180101",
                      end_date: str = "20261231", source: str = "auto") -> pd.DataFrame:
    """个股监管事件（按严重度筛选后的净结果）。

    source:
        'auto'  先试东财公告（快、带公告类型），失败回退 CNINFO
        'cninfo' 只用 CNINFO（独立 host，不与东财抢带宽）
        'eastmoney' 只用东财公告
    返回: DataFrame[code, event_date, title, notice_type, severity, event_type, url]
    """
    import akshare as ak

    df = None
    tried = []
    if source in ("auto", "eastmoney"):
        tried.append("eastmoney")
        try:
            _throttle()
            raw = ak.stock_individual_notice_report(
                security=code, symbol="全部", begin_date=start_date, end_date=end_date)
            if raw is not None and not raw.empty:
                df = _normalize(raw, "eastmoney")
        except Exception as exc:
            logger.warning("regulatory(eastmoney) %s failed: %s", code, exc)
    if df is None and source in ("auto", "cninfo"):
        tried.append("cninfo")
        try:
            _throttle()
            raw = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=code, start_date=start_date, end_date=end_date)
            if raw is not None and not raw.empty:
                df = _normalize(raw, "cninfo")
        except Exception as exc:
            logger.warning("regulatory(cninfo) %s failed: %s", code, exc)

    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["event_date"])
    if df.empty:
        return pd.DataFrame()

    # 分类
    recs = []
    for _, r in df.iterrows():
        sev, label = classify_title(r.get("title", ""))
        if sev == 0:
            continue
        recs.append({
            "code": code,
            "event_date": r["event_date"],
            "title": r.get("title", ""),
            "notice_type": r.get("notice_type", ""),
            "severity": sev,
            "event_type": label,
            "url": r.get("url", ""),
        })
    if not recs:
        return pd.DataFrame()
    return pd.DataFrame(recs)


def regulatory_events_all(codes, start_date="20180101", end_date="20261231",
                          source="cninfo", progress_path=None):
    """批量拉取全市场监管事件，断点续传，返回合并后的 DataFrame。

    source 默认 'cninfo'：独立 host，可与其他东财拉取并行而不抢带宽。
    progress_path 指定时做断点续传（已完成的 code 跳过）。
    """
    import json
    import os

    done = set()
    if progress_path and os.path.exists(progress_path):
        try:
            done = set(json.load(open(progress_path, encoding="utf-8")).get("reg_done", []))
        except Exception:
            pass

    chunks = []
    ok = 0
    t0 = time.time()
    for i, code in enumerate(codes):
        if code in done:
            continue
        df = regulatory_events(code, start_date, end_date, source=source)
        if not df.empty:
            chunks.append(df)
            ok += 1
            done.add(code)
        # 每 200 只落一次进度
        if len(chunks) >= 200:
            yield pd.concat(chunks, ignore_index=True)
            chunks = []
            if progress_path:
                json.dump({"reg_done": sorted(done)}, open(progress_path, "w"), ensure_ascii=False)
            logger.info("监管事件进度 %d/%d 命中%d 用时%.0fs", i + 1, len(codes), ok, time.time() - t0)
    if chunks:
        yield pd.concat(chunks, ignore_index=True)
    if progress_path:
        json.dump({"reg_done": sorted(done)}, open(progress_path, "w"), ensure_ascii=False)
    logger.info("监管事件完成: 命中 %d/%d 只", ok, len(codes))
