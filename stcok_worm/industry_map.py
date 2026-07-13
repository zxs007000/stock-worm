"""
行业映射数据源 — stock_worm 多源封装（不依赖单一东财）

行业中性化需要每只股票一个稳定的行业标签，但没有任何单一公开源 100% 可靠：

  · 东财行业板块  stock_board_industry_cons_em
        天然 1:1、速度快；但 board / push2 端点偶发整体失效（RemoteDisconnected），
        全市场板块一次性取不到，且对东财带宽 / 封 IP 有依赖。

  · 巨潮行业变更  stock_industry_change_cninfo
        逐只、host 与东财完全独立；东财挂时的稳健兜底。
        取「巨潮行业分类标准」最新一条的「行业大类」作为中性化行业。

因此本模块把两个源封装成统一接口，并让 source 默认 = 'auto'：
        先取东财板块（快），对东财未覆盖 / 东财端点失效的股票，用巨潮兜底。
        最终每只股票至少含 eastmoney_industry / cninfo_industry 之一，
        且 eastmoney_industry 始终被填充（东财优先，缺口用巨潮补），下游中性化不漏标的。

对外风格：复用 fundamentals_ext 的 20s 超时补丁 + 限流；失败返回空 / 不抛异常。

典型用法:
    from stcok_worm import industry_map
    rec = industry_map.industry_map("000001")            # auto: 东财优先 + 巨潮兜底
    for chunk in industry_map.industry_map_all(
            codes, source="auto", progress_path="meta/industry_progress.json"):
        ...   # chunk: DataFrame[code, eastmoney_industry, cninfo_industry]
"""

from __future__ import annotations

import json
import logging
import os
import time

import pandas as pd

logger = logging.getLogger(__name__)

# 复用 fundamentals_ext 的 20s 超时补丁 + 限流（导入即生效）
from .fundamentals_ext import _throttle  # noqa: F401


# ---------- 内部工具 ----------
def _retry(fn, *args, max_tries=5, base=2.0, **kwargs):
    """东财偶发 RemoteDisconnected，指数退避重试。"""
    last = None
    for attempt in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # 含 RemoteDisconnected / ConnectionError
            last = e
            wait = base * (2 ** attempt)
            logger.warning("网络重试 %d/%d: %s | %.1fs 后重连", attempt + 1, max_tries, str(e)[:80], wait)
            time.sleep(wait)
    logger.error("已达最大重试次数，放弃: %s", last)
    raise last


def _resolve_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return df.columns[0]


# ---------- 东财行业板块（板块 → 成分，一次性） ----------
_EM_BOARD_CACHE: dict = {"map": None}


def _eastmoney_board_map(force: bool = False) -> dict:
    """返回 {code: industry} 全市场映射（一次性拉全部板块成分，first-board-wins）。

    失败时缓存空映射并返回 {}，避免每只股票重试 62s。由调用方退化为巨潮兜底。
    """
    if _EM_BOARD_CACHE["map"] is not None and not force:
        return _EM_BOARD_CACHE["map"]
    try:
        import akshare as ak
        boards = _retry(ak.stock_board_industry_name_em)
        name_col = _resolve_col(boards, ["板块名称", "名称", "board_name"])
        board_names = boards[name_col].astype(str).tolist()
        mapping: dict = {}
        for bname in board_names:
            try:
                _throttle()
                cons = _retry(ak.stock_board_industry_cons_em, symbol=bname)
            except Exception as exc:
                logger.warning("东财板块 %s 拉取失败: %s", bname, exc)
                continue
            if cons is None or cons.empty:
                continue
            code_col = _resolve_col(cons, ["代码", "code"])
            for code in cons[code_col].astype(str).tolist():
                code = code.zfill(6)
                mapping.setdefault(code, bname)
        _EM_BOARD_CACHE["map"] = mapping
        logger.info("东财行业板块映射: %d 只 / %d 板块", len(mapping), len(board_names))
        return mapping
    except Exception as exc:
        logger.warning("东财板块全面失败，缓存空映射，后续直走巨潮: %s", exc)
        _EM_BOARD_CACHE["map"] = {}
        return {}


# ---------- 巨潮行业变更（逐只） ----------
def _pick_cninfo(df):
    """从 stock_industry_change_cninfo 返回结构取最新「行业大类」。"""
    if df is None or df.empty:
        return None
    d = df.copy()
    std = d[d.get("分类标准", "").astype(str).str.contains("巨潮", na=False)]
    if std.empty:
        std = d
    std = std.sort_values("变更日期")
    r = std.iloc[-1]
    for col in ["行业大类", "行业门类", "行业中类", "行业次类"]:
        v = r.get(col)
        if isinstance(v, str) and v.strip() and v != "nan":
            return v.strip()
    return None


def _cninfo_industry(code: str):
    """逐只取巨潮最新行业大类。仅对网络错误重试；schema 缺列（无变更记录）立即跳过。"""
    import akshare as ak
    import requests as _rq
    for attempt in range(3):
        try:
            df = ak.stock_industry_change_cninfo(
                symbol=code, start_date="20050101", end_date="20261231")
            return _pick_cninfo(df)
        except (_rq.exceptions.ConnectionError, _rq.exceptions.Timeout, TimeoutError):
            time.sleep(2.0 * (2 ** attempt))
        except Exception:
            return None  # 无行业变更记录 / schema 缺列 → 该股无数据，快速跳过
    return None


# ---------- 公开 API ----------
def industry_map(code: str, source: str = "auto"):
    """单只股票行业标签。

    source:
        'auto'      东财优先，缺则用巨潮兜底；
                    返回 {'code', 'eastmoney_industry', 'cninfo_industry'}
        'eastmoney' 仅东财（需先拉全市场板块，单只调用会触发一次全量，慎用）
        'cninfo'    仅巨潮（逐只，独立 host，最稳）
    返回 dict（含可用字段）或 None（无数据）。
    """
    code = code.strip().split(".")[0].zfill(6)
    em, cn = None, None
    if source in ("auto", "eastmoney"):
        try:
            m = _eastmoney_board_map()
            em = m.get(code)
        except Exception as exc:
            logger.warning("industry_map(eastmoney) %s failed: %s", code, exc)
    if (em is None) and source in ("auto", "cninfo"):
        cn = _cninfo_industry(code)
    if em is None and cn is None:
        return None
    return {
        "code": code,
        # eastmoney_industry 优先填东财，缺口用巨潮补，确保下游中性化不漏标的
        "eastmoney_industry": em if em is not None else cn,
        "cninfo_industry": cn,  # 巨潮真值（仅巨潮/cninfo 兜底时有值）
    }


def industry_map_all(codes, source: str = "auto", progress_path: str = None, batch_size: int = 50):
    """批量行业映射，断点续传。yield DataFrame[code, eastmoney_industry, cninfo_industry]。

    source:
        'auto'（默认） 东财优先 + 巨潮兜底（不依赖单一东财）
        'eastmoney'    仅东财板块
        'cninfo'       仅巨潮逐只
    progress_path 指定时做断点续传（已完成 code 跳过，键 'ind_done'）。
    eastmoney_industry 始终被填充（东财值优先，缺口用巨潮值补），保证下游中性化不漏标的。
    """
    done = set()
    if progress_path and os.path.exists(progress_path):
        try:
            done = set(json.load(open(progress_path, encoding="utf-8")).get("ind_done", []))
        except Exception:
            pass

    codes = [str(c).strip().split(".")[0].zfill(6) for c in codes]
    pending = [c for c in codes if c not in done]

    # 预取东财板块映射（仅当 source 含 eastmoney）
    em_map = {}
    if source in ("auto", "eastmoney"):
        try:
            em_map = _eastmoney_board_map()
        except Exception as exc:
            logger.warning("industry_map_all 东财板块映射失败，退化为巨潮: %s", exc)
            em_map = {}

    rows = []
    n_new = 0
    t0 = time.time()
    for i, code in enumerate(pending):
        em, cn = None, None
        if source in ("auto", "eastmoney") and code in em_map:
            em = em_map[code]
        if (em is None) and source in ("auto", "cninfo"):
            cn = _cninfo_industry(code)
        if em is None and cn is None:
            continue  # 两源都无该股票数据
        rec = {"code": code}
        rec["eastmoney_industry"] = em if em is not None else cn  # 下游安全填充
        rec["cninfo_industry"] = cn  # 巨潮真值列
        rows.append(rec)
        done.add(code)
        n_new += 1
        if (i + 1) % batch_size == 0:
            yield pd.DataFrame(rows)
            rows = []
            if progress_path:
                json.dump({"ind_done": sorted(done)}, open(progress_path, "w"), ensure_ascii=False)
            logger.info("行业映射进度 %d/%d 已映射 %d 只 用时%.0fs",
                        i + 1, len(pending), len(done), time.time() - t0)
    if rows:
        yield pd.DataFrame(rows)
    if progress_path:
        json.dump({"ind_done": sorted(done)}, open(progress_path, "w"), ensure_ascii=False)
    logger.info("行业映射分批完成: 本轮新增 %d 只，累计 done %d", n_new, len(done))
