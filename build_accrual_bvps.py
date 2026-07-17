"""
build_accrual_bvps.py — 用东财三张表造 accruals / bvps 日频面板
================================================================
背景: 因子 fundamental_quality_accrual 需 panel['accruals'],
      fundamental_value_pb_inv     需 panel['bvps'].
      原 fund_factors_daily 只有 ROE/rev_yoy/profit_yoy, 缺这俩.

精确公式(与因子注释一致):
    accruals = (净利润 − 经营现金流量净额) / 股东权益合计
             = (income.NETPROFIT − cashflow.NETCASH_OPERATE) / balance.TOTAL_EQUITY
    bvps     = 股东权益合计 / 股本
             = balance.TOTAL_EQUITY / balance.SHARE_CAPITAL

为什么不用 financial_indicators 派生:
    accruals = (NI − CFO)/Equity 是大数相减, 对 NI/CFO 输入误差极敏感
    (茅台 NI≈CFO, 3% 误差直接翻转符号). 三表真值才稳. bvps 同理用资产负债表真值.

输出: data/fundamentals/fund_accrual_bvps_daily.parquet
     = dict {'accruals': DataFrame(date×code), 'bvps': DataFrame(date×code)}
     季报考前填充(ffill)到日频, 与 fund_factors_daily 同 date×code 网格.

并发: ThreadPoolExecutor 多股票并发, 每股票内三表顺序拉取(带重试/超时).
断点续跑: 每批追加写 raw 长表 + 记录 done_codes, 重跑自动跳过已完成.
"""
from __future__ import annotations
import os, sys, time, json, argparse, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_accrual_bvps")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stcok_worm.fundamentals_ext as fe  # noqa: E402

DATA = HERE / "data" / "fundamentals"
RAW = DATA / "fund_accrual_bvps_raw.parquet"        # 长表: code,report_date,accruals,bvps
DONE = DATA / "fund_accrual_bvps_done.json"          # 已完成 code 列表
OUT = DATA / "fund_accrual_bvps_daily.parquet"       # 最终日频 dict
FUND = DATA / "fund_factors_daily.parquet"           # 取 date×code 网格 + codes

BATCH = 25                      # 每批写盘
MAX_WORKERS = 3                 # 并发股票数(东财 F10 别太狠)
PER_TABLE_TRIES = 4             # 单表重试


def _fetch(fn_name: str, code: str):
    for t in range(PER_TABLE_TRIES):
        try:
            d = getattr(fe, fn_name)(code)
            if d is not None and not d.empty:
                return d
        except Exception as e:  # akshare 偶发超时/空
            log.warning("  %s %s try%d: %s", fn_name, code, t + 1, repr(e)[:80])
            time.sleep(1.5 * (t + 1))
    return None


def compute_one(code: str) -> pd.DataFrame | None:
    inc = _fetch("income_statement", code)
    cf = _fetch("cash_flow_statement", code)
    bs = _fetch("balance_sheet", code)
    if inc is None or cf is None or bs is None:
        return None
    try:
        inc = inc.copy(); inc["RD"] = pd.to_datetime(inc["REPORT_DATE"])
        cf = cf.copy();  cf["RD"] = pd.to_datetime(cf["REPORT_DATE"])
        bs = bs.copy();  bs["RD"] = pd.to_datetime(bs["REPORT_DATE"])
        ni = inc.set_index("RD")["NETPROFIT"]
        cfo = cf.set_index("RD")["NETCASH_OPERATE"]
        eq = bs.set_index("RD")["TOTAL_EQUITY"]
        sh = bs.set_index("RD")["SHARE_CAPITAL"]
    except Exception as e:
        log.warning("  列解析失败 %s: %s", code, repr(e)[:80])
        return None
    idx = ni.index.union(cfo.index).union(eq.index)
    ni = ni.reindex(idx); cfo = cfo.reindex(idx)
    eq = eq.reindex(idx); sh = sh.reindex(idx)
    with np.errstate(divide="ignore", invalid="ignore"):
        accruals = (ni - cfo) / eq
        bvps = eq / sh
    out = pd.DataFrame({
        "code": code,
        "report_date": idx,
        "accruals": accruals.to_numpy(dtype="float64"),
        "bvps": bvps.to_numpy(dtype="float64"),
    })
    out = out[out["report_date"].notna()]
    return out if not out.empty else None


def load_done() -> set:
    if DONE.exists():
        try:
            return set(json.loads(DONE.read_text()))
        except Exception:
            return set()
    return set()


def run_build(codes, done):
    raw_parts = []
    if RAW.exists():
        try:
            raw_parts.append(pd.read_parquet(RAW))
        except Exception:
            pass
    pending = [c for c in codes if c not in done]
    log.info("待算 %d / 总数 %d (已完成 %d)", len(pending), len(codes), len(done))
    if not pending:
        log.info("全部已完成, 跳过重算")
        return pd.concat(raw_parts) if raw_parts else pd.DataFrame()
    results = []
    done_local = set(done)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(compute_one, c): c for c in pending}
        n = 0
        for fut in as_completed(futs):
            c = futs[fut]
            n += 1
            try:
                df = fut.result()
            except Exception as e:
                log.warning("  异常 %s: %s", c, repr(e)[:80])
                df = None
            if df is not None and not df.empty:
                results.append(df)
                done_local.add(c)
            if n % BATCH == 0:
                # 落盘: 追加 raw + 更新 done
                if results:
                    chunk = pd.concat(results)
                    if raw_parts:
                        raw_parts.append(chunk)
                        pd.concat(raw_parts).to_parquet(RAW, index=False)
                    else:
                        chunk.to_parquet(RAW, index=False)
                        raw_parts = [chunk]
                    results = []
                DONE.write_text(json.dumps(sorted(done_local)))
                rate = n / (time.time() - t0) if (time.time() - t0) > 0 else 0
                eta = (len(pending) - n) / rate / 60 if rate > 0 else 0
                log.info("进度 %d/%d  速度 %.2f 只/s  ETA %.0f min", n, len(pending), rate, eta)
    # 收尾落盘
    if results:
        if raw_parts:
            pd.concat(raw_parts + results).to_parquet(RAW, index=False)
        else:
            pd.concat(results).to_parquet(RAW, index=False)
    DONE.write_text(json.dumps(sorted(done_local)))
    # 重新读取完整 raw
    return pd.read_parquet(RAW) if RAW.exists() else pd.DataFrame()


def finalize(raw: pd.DataFrame):
    if raw.empty:
        log.error("raw 为空, 无法 finalize")
        return
    ff = pd.read_pickle(FUND)
    roe = ff.get("ROE")
    if roe is None:
        log.error("fund_factors_daily 无 ROE, 无法取网格")
        return
    dates = roe.index
    codes = list(roe.columns)
    log.info("finalize: %d 只 × %d 日 -> accruals/bvps 日频", len(codes), len(dates))
    acc = pd.DataFrame(index=dates, columns=codes, dtype="float32")
    bv = pd.DataFrame(index=dates, columns=codes, dtype="float32")
    for code in codes:
        sub = raw[raw["code"] == code]
        if sub.empty:
            continue
        sub = sub.sort_values("report_date")
        sub = sub[~sub["report_date"].duplicated(keep="last")]
        for col, target in (("accruals", acc), ("bvps", bv)):
            s = sub.set_index("report_date")[col]
            s = s.reindex(dates).ffill()
            target[code] = s.to_numpy(dtype="float32")
    log.info("accruals 非空占比: %.3f | bvps 非空占比: %.3f",
             float(acc.notna().to_numpy().mean()), float(bv.notna().to_numpy().mean()))
    pd.to_pickle({"accruals": acc, "bvps": bv}, OUT)
    log.info("写出 %s", OUT)


def main():
    global MAX_WORKERS
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize-only", action="store_true", help="仅从 raw 组装日频(不重算)")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = ap.parse_args()
    MAX_WORKERS = args.workers

    ff = pd.read_pickle(FUND)
    codes = list(ff.get("ROE").columns)
    log.info("目标 codes: %d", len(codes))

    if args.finalize_only:
        raw = pd.read_parquet(RAW) if RAW.exists() else pd.DataFrame()
        finalize(raw)
        return
    done = load_done()
    raw = run_build(codes, done)
    finalize(raw)


if __name__ == "__main__":
    main()
