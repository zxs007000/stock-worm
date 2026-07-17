"""build_macro_signals.py — 构建日频宏观信号, 落盘供防御门控右侧预警.

输出(均 data/macro/):
  - buffett_ratio.parquet : 日频巴菲特指标 = 总市值/GDP (GDP 按发布日对齐, 防前视)
  - m2_growth.parquet     : 日频 M2 同比增速(流动性共振因子)
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stcok_worm.macro as macro  # noqa: E402

OUT_DIR = HERE / "data" / "macro"
OUT_B = OUT_DIR / "buffett_ratio.parquet"
OUT_M = OUT_DIR / "m2_growth.parquet"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/2] 拉取宏观并构建日频巴菲特指标...")
    r = macro.buffett_ratio_daily(publish_lag_days=60)
    print(f"  巴菲特: 长度 {len(r)} | {r.index.min().date()}~{r.index.max().date()} | "
          f"末值 {r.iloc[-1]:.3f} (分位 {(r <= r.iloc[-1]).mean():.0%})")
    r.rename("buffett_ratio").to_frame().to_parquet(OUT_B)
    print(f"  写出 {OUT_B}")

    print("[2/2] 构建日频 M2 同比(流动性共振)...")
    m = macro.m2_growth_daily(win=12)
    print(f"  M2同比: 长度 {len(m)} | {m.index.min().date()}~{m.index.max().date()} | "
          f"末值 {m.iloc[-1]:.3%}")
    m.rename("m2_growth").to_frame().to_parquet(OUT_M)
    print(f"  写出 {OUT_M}")


if __name__ == "__main__":
    main()
