"""
stcok_worm — 全栈A股数据源包 (基于 a-stock-data V3.3 改写)

十层架构:
    1. 行情层    tencent + mootdx + eastmoney  K线 + 实时行情 + PE/PB
    2. 研报层    research                      个股研报 + 行业研报 + 一致预期
    3. 信号层    signals                       龙虎榜 + 解禁 + 行业排名 + 板块归属 + 涨停池
    4. 资金面    eastmoney                     融资融券 + 大宗交易 + 股东户数 + 分红 + 资金流
    5. 新闻层    news                          个股新闻 + 全球资讯
    6. 基础数据  fundamentals + fundamentals_ext  季报快照 + 公司信息 + 86 比率 + 三张表 + 分红 + 解禁
        数据湖    datalake                      本地 parquet 湖读取（财务比率/分红/解禁/季报/行业映射/监管事件）
        行业映射  industry_map                  多源行业标签（东财板块优先 + 巨潮兜底，不依赖单一东财）
    12. 数据湖构建 lake_build                   把财务比率/分红/解禁/监管/行业映射拉进本地湖（CLI: python -m stcok_worm.lake_build）
    11. 监管事件  regulatory                    立案/处罚/问询函/监管函/警示函（巨潮+东财公告，标题分级）
    7. 公告层    filings                       巨潮全量公告
    8. 期权层    options                       ETF期权T型报价 + 希腊字母 + IV
    9. 可转债    cb_sina                       可转债列表 + 日线 (独有)
   10. 宏观      bond_yield + index            国债收益率 + ETF净值 (独有)

数据源优先级 (不封IP优先):
    1. mootdx (通达信 TCP) — 不封IP
    2. 腾讯财经 (HTTP) — 不封IP
    3. 新浪/巨潮 (HTTP) — 低风险
    4. 东财 (HTTP) — 仅用于独有数据，已内置限流防封

用法:
    from stcok_worm import tencent, mootdx, eastmoney, research, signals
    from stcok_worm import news, fundamentals, filings, options
    from stcok_worm import cb_sina, bond_yield, idx_src
    from stcok_worm import fundamentals_ext, datalake, industry_map
"""

from . import tencent
from . import mootdx_source as mootdx
from . import eastmoney
from . import cb_sina
from . import bond_yield
from . import index as idx_src
from . import research
from . import signals
from . import news
from . import fundamentals
from . import fundamentals_ext
from . import datalake
from . import lake_build
from . import regulatory
from . import industry_map
from . import filings
from . import options
from . import realtime
# JRJ / 证券之星 已按层整合到 tencent.signals.news 模块
# from stcok_worm import tencent, signals, news

__all__ = [
    "tencent", "mootdx", "eastmoney",
    "research", "signals", "news", "fundamentals", "fundamentals_ext", "datalake",
    "lake_build", "regulatory", "industry_map", "filings", "options",
    "cb_sina", "bond_yield", "idx_src", "realtime",
]
