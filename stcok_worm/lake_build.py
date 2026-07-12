"""
数据湖构建器（stock_worm 内置能力）
==================================

把以下源拉到本地数据湖（datalake 约定的目录结构），落盘为 parquet / csv，
供 oos_framework 等下游直接消费。复用 fundamentals_ext（财务/分红/解禁抓取）、
regulatory（监管事件抓取）、datalake（路径与读取），是「抓取 + 读取 + 构建」
完整闭环的构建端。

产物（默认根 D:/work Buddy GZ/Claw/stockworm，可用 --lake 或 STOCKWORM_LAKE 覆盖）:
  fundamentals/fin_indicators.parquet      个股财务分析指标（季度，38 比率）— 逐只拉，断点续传
  fundamentals/dividends_summary.parquet   全市场分红汇总（1 次调用）
  fundamentals/unlocks.parquet             限售股解禁事件（按年分批）
  fundamentals/regulatory_events.parquet   监管事件（立案/处罚/问询函/监管函/警示函，标题分级）
  metadata/industry_map.csv                行业映射（东财行业板块，天然 1:1）

用法:
  python -m stcok_worm.lake_build                 # 全量基本面（fin + dividends + unlock）
  python -m stcok_worm.lake_build --only fin
  python -m stcok_worm.lake_build --only dividends
  python -m stcok_worm.lake_build --only unlock
  python -m stcok_worm.lake_build --only regulatory --source eastmoney
  python -m stcok_worm.lake_build --only industry
  python -m stcok_worm.lake_build --lake D:/other_lake

依赖: akshare, stcok_worm.fundamentals_ext, stcok_worm.regulatory, stcok_worm.datalake
"""

from __future__ import annotations

import os
import sys
import argparse
import time
import json
import logging

os.environ.setdefault("TQDM_DISABLE", "1")  # 关掉 akshare 内部进度条，日志更干净
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lake_build")

# 触发 fundamentals_ext 内的 20s 全局超时补丁 + 限流（避免挂死 / 被打）
from stcok_worm.fundamentals_ext import (
    financial_indicators,
    dividend_summary_all,
    unlock_detail,
    _throttle,  # noqa: F401
)
from stcok_worm import regulatory
from stcok_worm import datalake


# ---------- 路径（尊重 datalake.LAKE_ROOT，可运行时覆盖） ----------
def _paths():
    root = datalake.LAKE_ROOT
    fund = root / "fundamentals"
    meta = root / "metadata"
    daily = root / "daily"
    for p in (fund, meta, daily):
        p.mkdir(parents=True, exist_ok=True)
    return fund, meta, daily


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


# ---------- 通用工具 ----------
def write_append(out, df_new):
    import pandas as pd
    if out.exists():
        old = pd.read_parquet(out)
        # 对齐 date 类型（parquet 可能是 datetime，新抓为字符串，反之亦然）
        if "date" in old.columns and "date" in df_new.columns:
            old = old.copy()
            old["date"] = pd.to_datetime(old["date"], errors="coerce")
            df_new = df_new.copy()
            df_new["date"] = pd.to_datetime(df_new["date"], errors="coerce")
        df = pd.concat([old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_parquet(out, index=False)


def list_codes_from_daily(min_bars: int = 250):
    """从本地日线湖列出有效股票（按最少交易日过滤）。"""
    import pandas as pd
    daily = datalake.LAKE_ROOT / "daily"
    if not daily.exists():
        return []
    codes = []
    for f in sorted(daily.glob("*.parquet")):
        code = f.stem
        try:
            d = pd.read_parquet(f, columns=["close"])
            if len(d) >= min_bars:
                codes.append(code)
        except Exception:
            continue
    return sorted(codes)


def load_progress(path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(path, p: dict):
    path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")


# ---------- 1. 财务比率 ----------
FIN_DONE_KEY = "fin_done"


def build_fin(min_bars: int = 250):
    """逐只拉财务分析指标，断点续传，存 fin_indicators.parquet。"""
    fund, meta, _ = _paths()
    out = fund / "fin_indicators.parquet"
    prog_path = meta / "fund_ext_progress.json"
    progress = load_progress(prog_path)
    done = set(progress.get(FIN_DONE_KEY, []))

    codes = [c for c in list_codes_from_daily(min_bars) if c not in done]
    logger.info("财务比率: 待拉 %d / 总计 %d", len(codes), len(list_codes_from_daily(min_bars)))
    if not codes:
        logger.info("财务比率: 已全部完成")
        return

    import pandas as pd
    chunks, ok, t0 = [], 0, time.time()
    for i, code in enumerate(codes):
        df = financial_indicators(code)  # 东财版，全历史，忽略 start_year
        if not df.empty:
            chunks.append(df)
            ok += 1
            done.add(code)
        if len(chunks) >= 100:
            write_append(out, pd.concat(chunks, ignore_index=True))
            chunks = []
            progress[FIN_DONE_KEY] = sorted(done)
            save_progress(prog_path, progress)
            logger.info("  财务比率进度 %d/%d  成功%d  用时%.0fs",
                        i + 1, len(codes), ok, time.time() - t0)
    if chunks:
        write_append(out, pd.concat(chunks, ignore_index=True))
    progress[FIN_DONE_KEY] = sorted(done)
    save_progress(prog_path, progress)
    logger.info("财务比率完成: 成功 %d/%d  总用时 %.1fmin", ok, len(codes), (time.time() - t0) / 60)


# ---------- 2. 分红 ----------
def build_dividends():
    out = _paths()[0] / "dividends_summary.parquet"
    logger.info("拉取全市场分红汇总...")
    df = dividend_summary_all()
    if not df.empty:
        df.to_parquet(out, index=False)
        logger.info("分红汇总完成: %d 只 -> %s", len(df), out)
    else:
        logger.warning("分红汇总为空")


# ---------- 3. 解禁 ----------
def build_unlock():
    out = _paths()[0] / "unlocks.parquet"
    logger.info("拉取限售股解禁事件 (2006-2026, 按年分批)...")
    import pandas as pd
    chunks = []
    for y in range(2006, 2027):
        s, e = f"{y}0101", f"{y}1231"
        df = unlock_detail(s, e)
        if not df.empty:
            chunks.append(df)
            logger.info("  %d 解禁 %d 条", y, len(df))
        time.sleep(0.3)
    if chunks:
        all_df = pd.concat(chunks, ignore_index=True)
        all_df.to_parquet(out, index=False)
        logger.info("解禁事件完成: 合计 %d 条 -> %s", len(all_df), out)
    else:
        logger.warning("解禁事件为空")


# ---------- 4. 监管事件 ----------
def build_regulatory(source: str = "eastmoney", start: str = "20100101", end: str = "20261231",
                      min_bars: int = 250):
    """逐只拉个股公告 → 标题严重度分级，只留监管类，存 regulatory_events.parquet。

    source: 'eastmoney'（快，~2-8s/只，需东财带宽）/ 'cninfo'（独立 host，慢，可与东财并行）。
    """
    fund, meta, _ = _paths()
    out = fund / "regulatory_events.parquet"
    prog_path = meta / "reg_progress.json"
    codes = list_codes_from_daily(min_bars)
    logger.info("监管事件全量拉取: %d 只 (source=%s, start=%s)", len(codes), source, start)
    n = 0
    for chunk in regulatory.regulatory_events_all(
        codes, start_date=start, end_date=end, source=source, progress_path=str(prog_path)
    ):
        if chunk is not None and not chunk.empty:
            write_append(out, chunk)
            n += 1
            logger.info("  累计落盘 %d 批", n)
    if out.exists():
        import pandas as pd
        logger.info("监管事件数据湖完成: %d 行 -> %s", len(pd.read_parquet(out)), out)
    else:
        logger.warning("未生成任何监管事件")


# ---------- 5. 行业映射 ----------
def _resolve_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return df.columns[0]


def build_industry_map():
    """东财行业板块 → metadata/industry_map.csv（天然 1:1 映射，适合行业中性化）。

    带指数退避重试 + 断点续传 + 增量落盘，抗东财限流。
    """
    import akshare as ak
    import pandas as pd
    _, meta, _ = _paths()
    out = meta / "industry_map.csv"
    prog_path = meta / "ind_map_progress.json"

    done_boards = set(load_progress(prog_path).get("done", []))
    seen = set()
    if out.exists():
        try:
            seen.update(pd.read_csv(out, dtype=str)["code"].astype(str).tolist())
            logger.info("续传: 已有 %d 只映射", len(seen))
        except Exception:
            pass

    logger.info("拉取东财行业板块列表...")
    boards = _retry(ak.stock_board_industry_name_em)
    name_col = _resolve_col(boards, ["板块名称", "名称", "board_name"])
    board_names = boards[name_col].astype(str).tolist()
    pending = [b for b in board_names if b not in done_boards]
    logger.info("行业板块数: %d (待拉 %d)", len(board_names), len(pending))

    n_new = 0
    for i, bname in enumerate(pending):
        try:
            _throttle()
            cons = _retry(ak.stock_board_industry_cons_em, symbol=bname)
        except Exception:
            continue
        if cons is None or cons.empty:
            done_boards.add(bname)
            continue
        code_col = _resolve_col(cons, ["代码", "code"])
        batch = []
        for code in cons[code_col].astype(str).tolist():
            code = code.zfill(6)
            if code in seen:
                continue
            seen.add(code)
            batch.append((code, bname))
        if batch:
            pd.DataFrame(batch, columns=["code", "eastmoney_industry"]).to_csv(
                out, mode="a", index=False,
                header=not out.exists() or out.stat().st_size == 0,
                encoding="utf-8-sig")
            n_new += len(batch)
        done_boards.add(bname)
        save_progress(prog_path, {"done": sorted(done_boards)})
        if (i + 1) % 20 == 0:
            logger.info("  进度 %d/%d  累计映射 %d 只", i + 1, len(pending), len(seen))

    df = pd.read_csv(out, dtype=str) if out.exists() else pd.DataFrame(columns=["code", "eastmoney_industry"])
    logger.info("行业映射完成: %d 只 -> %s (本轮新增 %d)", len(df), out, n_new)
    print(df.head(10).to_string())


# ---------- manifest ----------
def write_manifest():
    import pandas as pd
    fund = _paths()[0]
    lines = ["# 基本面 / 监管 / 行业 数据湖（由 stcok_worm.lake_build 生成）", ""]
    for f, desc in [
        ("fin_indicators.parquet", "个股财务分析指标(季度,38比率): ROE/毛利率/资产负债率/流动比率/营收净利增速/周转率..."),
        ("dividends_summary.parquet", "全市场分红汇总: 累计股息/年均股息/分红次数/融资总额"),
        ("unlocks.parquet", "限售股解禁事件: 代码/解禁日期/数量/比例"),
        ("regulatory_events.parquet", "监管事件: 立案/处罚/问询函/监管函/警示函（标题严重度分级）"),
    ]:
        p = fund / f
        if p.exists():
            lines.append(f"- {f}: {len(pd.read_parquet(p))} 行 — {desc}")
        else:
            lines.append(f"- {f}: 未生成 — {desc}")
    (fund / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="stock_worm 数据湖构建器")
    ap.add_argument("--only", choices=["fin", "dividends", "unlock", "regulatory", "industry"], default=None,
                    help="只构建指定部分（默认 fin+dividends+unlock）")
    ap.add_argument("--lake", default=None, help="数据湖根目录（覆盖默认/STOCKWORM_LAKE）")
    ap.add_argument("--source", default="eastmoney", choices=["eastmoney", "cninfo", "auto"],
                    help="监管事件源（仅 --only regulatory 生效）")
    ap.add_argument("--start", default="20100101", help="监管/起始日 YYYYMMDD")
    ap.add_argument("--end", default="20261231")
    ap.add_argument("--min-bars", type=int, default=250, help="纳入的股票最少交易日数")
    args = ap.parse_args()

    if args.lake:
        datalake.set_lake_root(args.lake)
        logger.info("数据湖根目录: %s", datalake.LAKE_ROOT)

    if args.only in (None, "dividends"):
        build_dividends()
    if args.only in (None, "unlock"):
        build_unlock()
    if args.only in (None, "fin"):
        build_fin(min_bars=args.min_bars)
    if args.only == "regulatory":
        build_regulatory(source=args.source, start=args.start, end=args.end, min_bars=args.min_bars)
    if args.only == "industry":
        build_industry_map()

    if args.only in (None, "fin", "dividends", "unlock"):
        write_manifest()
    logger.info("数据湖构建完成。")


if __name__ == "__main__":
    main()
