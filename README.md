# stcok-worm

全栈 A 股数据源包 — 覆盖可转债、ETF、A 股 K 线、国债收益率、指数股息率。

数据源: 腾讯财经 (HTTP 不封 IP) + 新浪财经 (akshare) + 东方财富 (内置限流) + 通达信 TCP (可选)。

## 安装

```bash
pip install stcok-worm          # 基础安装
pip install stcok-worm[full]    # 含通达信TCP支持
```

本地安装:

```bash
cd stcok-worm && pip install .
```

## 使用示例

### 1. ETF 日线（腾讯财经）

```python
from stcok_worm import tencent
data = tencent.get_etf_daily("159307")
for d in data[:3]:
    print(d["date"], d["close"])
```

### 2. 批量实时行情（腾讯财经）

```python
from stcok_worm import tencent
quotes = tencent.get_quotes_batch(["159307", "510050", "159915"])
for c, q in quotes.items():
    print(f"{q['name']}: ¥{q['price']} PE={q['pe_ttm']}")
```

### 3. 可转债全量列表

```python
from stcok_worm import cb_sina
df = cb_sina.get_cb_list()
print(df[["bond_code", "bond_name", "convert_price"]])
```

### 4. 单只转债日线

```python
from stcok_worm import cb_sina
df = cb_sina.get_cb_daily("127027")
print(f"{len(df)} 行 [{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}]")
```

### 5. 国债收益率

```python
from stcok_worm import bond_yield
df = bond_yield.get_china_yield_10y()
print(df.tail())
```

### 6. ETF 净值 / 股息率

```python
from stcok_worm import index as idx_src
nav = idx_src.get_etf_nav("159307")
dy = idx_src.get_dividend_yield("159307")
print(f"股息率: {dy}%")
```

### 7. 东方财富独有数据

```python
from stcok_worm import eastmoney
divs = eastmoney.get_dividend_history("159307")
margin = eastmoney.get_margin_detail("688017")
block = eastmoney.get_block_trade("300476")
```

### 8. 通达信 TCP（可选，需 mootdx）

```python
from stcok_worm import mootdx_source as mootdx
if mootdx.available():
    kline = mootdx.get_kline("688017")
    print(f"K线: {len(kline)} 行")
```

## 函数速查

| 模块 | 函数 | 参数 | 返回 |
|------|------|------|------|
| tencent | `get_kline(code, period)` | code: 6位代码, period: day/week/month | `[{"date","open","close","high","low","volume"}]` |
| tencent | `get_etf_daily(code)` | code: ETF代码 | 同上 |
| tencent | `get_index_daily(code)` | code: 指数代码 | 同上 |
| tencent | `get_stock_quote(code)` | code: 6位代码 | `{"name","price","pe_ttm","pb","mcap_yi"}` |
| tencent | `get_quotes_batch(codes)` | codes: 代码列表 | `{code: {name,price,pe_ttm,...}}` |
| cb_sina | `get_cb_list()` | — | DataFrame: bond_code, bond_name, stock_code, rating, convert_price |
| cb_sina | `get_cb_daily(code)` | code: 转债代码 | DataFrame: date, open, high, low, close, volume |
| cb_sina | `build_cb_sections(cb_data, stock_data, master)` | 三大dict | DataFrame: date, bond_code, price, premium_rt, dblow, rating |
| bond_yield | `get_china_yield_10y()` | — | DataFrame: date, yield_10y |
| bond_yield | `get_china_yield_curve()` | — | DataFrame: 完整收益率曲线 |
| index | `get_etf_nav(code)` | code: ETF代码 | DataFrame: date, nav, cum_nav |
| index | `get_dividend_yield(code)` | code: ETF代码 | float: 股息率(%) |
| eastmoney | `get_dividend_history(code)` | code: 6位代码 | list[dict]: 分红记录 |
| eastmoney | `get_margin_detail(code)` | code: 6位代码 | list[dict]: 融资融券 |
| eastmoney | `get_block_trade(code)` | code: 6位代码 | list[dict]: 大宗交易 |
| eastmoney | `get_shareholder_count(code)` | code: 6位代码 | list[dict]: 股东户数 |
| eastmoney | `get_fund_flow_minute(code)` | code: 6位代码 | list[dict]: 资金流 |
| mootdx | `get_kline(code, freq)` | freq: 9=日 | `[{"date","open","close",...}]` |
| mootdx | `get_quote(code)` | code: 6位代码 | dict: 五档盘口 |
| mootdx | `get_finance(code)` | code: 6位代码 | dict: 37字段财务 |
| mootdx | `available()` | — | bool: 是否可用 |

## 注意事项

- **腾讯财经**: 不封 IP，建议 0.5s 请求间隔
- **东方财富**: 所有请求走 `em_get()` 内置限流器，间隔 ≥1s+随机抖动，批量调用时自动降速
- **通达信 TCP**: 需要防火墙允许 7709 端口出站，公司网络可能限制 TCP 连接，此时用腾讯替代
- **akshare**: 部分接口可能因源网站变化而失效，升级 akshare (`pip install -U akshare`) 可解决多数问题
- **新浪转债日线**: 实测 85-90% 成功率，~0.12s/只

## cnstock 接口（⚠️ IP 封禁高风险）

`stcok_worm/cnstock.py` 的 `stock_detail()` 接口曾因 **8 线程并发猛打**触发
`data.cnstock.com` 整域 403 封禁（IP 级，持续时间不定）。该模块已内置
**全局并发上限(SAFE_CONCURRENCY=2) + 请求间隔(MIN_INTERVAL=1s) + 403/429 指数退避**，
任何调用方都**勿再开高并发**。详见 `cnstock.py` 顶部警告与 `_get()` 实现。

> 量化建模（XGBoost WFA 因子挖掘 / SHAP 解释 / 数据湖构建器）已独立存放于
> `Vibe-Trading-Ashare` 仓库的 `oos_framework/xgboost_wfa/`，**不在本包内**。

## License

MIT
