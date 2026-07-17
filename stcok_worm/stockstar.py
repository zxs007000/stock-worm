"""stockstar.py — 证券之星数据源(三大表 / 分红送配 / 融资融券 / 行业分类).

补全 stockworm 在财务数据层的源多样性(此前只有东财 + 新浪).
来源 URL(证券之星 stockstar.com):
  利润表       : https://stock.quote.stockstar.com/finance/profit_{code}.shtml
  资产负债表   : https://stock.quote.stockstar.com/finance/balance_{code}.shtml
  现金流量表   : https://stock.quote.stockstar.com/finance/cashflow_{code}.shtml
  分红送配     : https://stock.quote.stockstar.com/dividend_{code}.shtml
  融资融券     : https://stock.quote.stockstar.com/info/financing_{code}.shtml
  行业分类     : https://quote.stockstar.com/stock/industry_{A..S}.shtml (CSRC 门类, GBK)

设计原则(与 stockworm 风格一致):
  - 所有函数返回 pandas.DataFrame; 失败返回空 DataFrame, 不抛异常.
  - logger.warning 容错 + 全局请求超时(20s)+ 串行限流(0.4s/只).
  - 列名用证券之星原文(中文), 与 akshare 翻译后的英文列不混用, 调用方按需映射.

用法:
    from stcok_worm import stockstar
    df = stockstar.income_statement("600519")
    div = stockstar.dividend("600519")
    mrg = stockstar.margin_trading("600519")
"""
from __future__ import annotations
import re
import time
import logging
import requests
import pandas as pd

logger = logging.getLogger(__name__)

# ── 全局请求超时(防止 akshare 风格的永久挂死) ──
_ORIG_REQ = requests.Session.request


def _patched_req(self, method, url, **kwargs):
    kwargs.setdefault("timeout", 20)
    return _ORIG_REQ(self, method, url, **kwargs)


requests.Session.request = _patched_req

# ── HTTP 头(证券之星对裸 UA 不友好) ──
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://stock.quote.stockstar.com/",
}

# ── 限流(证券之星 0.4s/只 较稳) ──
_MIN_INTERVAL = 0.4
_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


BASE = "https://stock.quote.stockstar.com"
_RETRIES = 3


def _fetch(path: str) -> str | None:
    """GET {BASE}{path}, 重试+限流, 失败返回 None."""
    url = f"{BASE}{path}"
    last = None
    for t in range(_RETRIES):
        try:
            _throttle()
            r = requests.get(url, headers=HEADERS)
            r.raise_for_status()
            # 不强制 encoding, 让 requests 根据 header 自动检测(证券之星用 zh-CN charset)
            return r.text
        except Exception as e:
            last = e
            logger.warning("stockstar fetch %s try%d: %s", path, t + 1, repr(e)[:80])
            time.sleep(1.2 * (t + 1))
    logger.error("stockstar fetch %s failed after %d tries: %s", path, _RETRIES, repr(last)[:80])
    return None


def _code6(code: str) -> str:
    """6 位代码(去掉后缀)."""
    return code.strip().split(".")[0]


def _clean(s: str) -> str:
    """剥 HTML 标签 + 实体 + 合并空白."""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"&[a-z#0-9]+;", " ", s)  # 所有 HTML 实体(nbsp/ensp/emsp...)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _to_float(s):
    """证券之星的数字格式: '187.89亿' / '11.18万' / '1.19%' / '--' -> float | None.
    列名已标单位(如'融资余额(亿)'), 故只去单位、不换算. 百分比列('%'后缀)除以 100.
    """
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "--", "-", "—"):
        return None
    pct = s.endswith("%")
    s = re.sub(r"[亿万千百]$", "", s)
    s = s.replace("%", "").strip()
    if not s:
        return None
    try:
        v = float(s)
        return v / 100.0 if pct else v
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════
# 三大表(利润表 / 资产负债表 / 现金流量表)
# 报表结构相同: table[1] = 报告期(列) × 科目(行)
# ════════════════════════════════════════════════════════════════════════

def _parse_finance_table(html: str) -> pd.DataFrame:
    """把证券之星三张表 HTML 解析为 DataFrame(index=报告期, columns=科目, values=float)."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
    if len(tables) < 2:
        logger.warning("stockstar finance: <table> 数量 < 2")
        return pd.DataFrame()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], re.S)
    if len(rows) < 2:
        return pd.DataFrame()
    # 第一行: 报告期 | 2026-03-31 | 2025-12-31 | ...
    header = [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S)]
    if not header or "报告期" not in header[0]:
        return pd.DataFrame()
    dates_raw = header[1:]
    # 报告期形如 "2026-03-31" / "2025-12-31" 等, 全部转为 Timestamp
    parsed_dates = []
    for d in dates_raw:
        try:
            parsed_dates.append(pd.Timestamp(d))
        except Exception:
            # 跳过解析失败的日期
            parsed_dates.append(None)
    # 过滤掉解析失败的
    keep_cols = [i for i, t in enumerate(parsed_dates) if t is not None]
    if not keep_cols:
        return pd.DataFrame()
    kept_dates = [parsed_dates[i] for i in keep_cols]
    # 数据行: [科目, 值1, 值2, ...]
    series_dict = {}
    for r in rows[1:]:
        cells_raw = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        if not cells_raw:
            continue
        cells = [_clean(c) for c in cells_raw]
        if len(cells) < 2:
            continue
        key = cells[0]
        if not key:
            continue
        vals = cells[1:]
        kept_vals = []
        for j, v in enumerate(vals):
            if j in keep_cols:
                kept_vals.append(_to_float(v))
        if any(v is not None for v in kept_vals):
            series_dict[key] = kept_vals
    if not series_dict:
        return pd.DataFrame()
    df = pd.DataFrame(series_dict, index=pd.DatetimeIndex(kept_dates, name="report_date"))
    df.index.name = "report_date"
    return df


def income_statement(code: str) -> pd.DataFrame:
    """利润表(证券之星). 列=科目(营业总收入/营业总成本/利润总额/净利润/...), 行=报告期."""
    code = _code6(code)
    html = _fetch(f"/finance/profit_{code}.shtml")
    if not html:
        return pd.DataFrame()
    return _parse_finance_table(html)


def balance_sheet(code: str) -> pd.DataFrame:
    """资产负债表(证券之星). 列=科目(流动资产合计/非流动资产合计/资产总计/负债合计/股东权益合计/...)."""
    code = _code6(code)
    html = _fetch(f"/finance/balance_{code}.shtml")
    if not html:
        return pd.DataFrame()
    return _parse_finance_table(html)


def cash_flow_statement(code: str) -> pd.DataFrame:
    """现金流量表(证券之星). 列=科目(经营/投资/筹资 三类流入/流出/净额 + 现金净增加额)."""
    code = _code6(code)
    html = _fetch(f"/finance/cashflow_{code}.shtml")
    if not html:
        return pd.DataFrame()
    return _parse_finance_table(html)


# ════════════════════════════════════════════════════════════════════════
# 分红送配
# ════════════════════════════════════════════════════════════════════════

def _parse_dividend(html: str) -> pd.DataFrame:
    """分红送配 HTML -> DataFrame.
    表格结构: 公告日期 | 分红(每10股) | 送股(每10股) | 转增股(每10股) | 登记日 | 除权日.
    """
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
    if len(tables) < 2:
        return pd.DataFrame()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], re.S)
    if len(rows) < 2:
        return pd.DataFrame()
    header = [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S)]
    if not header or "公告日期" not in header[0]:
        return pd.DataFrame()
    data = []
    for r in rows[1:]:
        cells = [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        data.append(cells[: len(header)])
    df = pd.DataFrame(data, columns=header)
    # 数值列尝试转 float
    for col in df.columns:
        if any(k in col for k in ("分红", "送股", "转增")):
            df[col] = df[col].apply(_to_float)
    if "公告日期" in df.columns:
        df["公告日期"] = pd.to_datetime(df["公告日期"], errors="coerce")
    if "登记日" in df.columns:
        df["登记日"] = pd.to_datetime(df["登记日"], errors="coerce")
    if "除权日" in df.columns:
        df["除权日"] = pd.to_datetime(df["除权日"], errors="coerce")
    return df


def dividend(code: str) -> pd.DataFrame:
    """分红送配(证券之星). 字段: 公告日期/分红(每10股)/送股/转增股/登记日/除权日."""
    code = _code6(code)
    html = _fetch(f"/dividend_{code}.shtml")
    if not html:
        return pd.DataFrame()
    return _parse_dividend(html)


# ════════════════════════════════════════════════════════════════════════
# 融资融券(双层表头)
# ════════════════════════════════════════════════════════════════════════

def _parse_financing(html: str) -> pd.DataFrame:
    """融资融券 HTML -> DataFrame.
    表头分两层(证券之星用 rowspan/colspan):
      第0行: 交易日期 | 融资(横跨 5 列) | 融券(横跨 3 列) | 融资融券余额 | 余额差值
      第1行: (空) | 余额(元) | 当日余额占流通市值比 | 买入额(元) | 偿还额(元) | 净买入(元) | 余额(元) | 余量(股) | 卖出量(股) | ...
    这里只关心前 8 列(融资 5 列 + 融券 2 列 + 交易日期), 简化列名.
    """
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
    if not tables:
        return pd.DataFrame()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S)
    if len(rows) < 3:
        return pd.DataFrame()
    # 我们要的列: 交易日期 + 融资5列 + 融券前2列 = 8 列
    cols = ["交易日期", "融资余额(亿)", "融资占流通市值比(%)",
            "融资买入额(亿)", "融资偿还额(亿)", "融资净买入(亿)",
            "融券余额(亿)", "融券余量(股)"]
    data = []
    for r in rows[2:]:
        cells = [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
        if len(cells) >= len(cols):
            data.append(cells[: len(cols)])
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=cols)
    # 数值化
    for col in df.columns[1:]:
        if "占流通" in col or "%" in col:
            df[col] = df[col].apply(_to_float)  # 已是 0.0119 而非 1.19
        else:
            df[col] = df[col].apply(_to_float)
    if "交易日期" in df.columns:
        df["交易日期"] = pd.to_datetime(df["交易日期"], errors="coerce")
    return df


def margin_trading(code: str) -> pd.DataFrame:
    """融资融券(证券之星). 字段: 交易日期/融资余额/占比/买入/偿还/净买入/融券余额/余量."""
    code = _code6(code)
    html = _fetch(f"/info/financing_{code}.shtml")
    if not html:
        return pd.DataFrame()
    return _parse_financing(html)


# ════════════════════════════════════════════════════════════════════════
# 行业分类(CSRC 门类, 基于 quote.stockstar.com/stock/industry_{A-S}.shtml, GBK)
# ════════════════════════════════════════════════════════════════════════

CSRC_NAMES = {
    "A": "农林牧渔业", "B": "采矿业", "C": "制造业",
    "D": "电力热力燃气及水生产和供应业", "E": "建筑业",
    "F": "批发和零售业", "G": "交通运输仓储和邮政业",
    "H": "住宿和餐饮业", "I": "信息传输软件和信息技术服务业",
    "J": "金融业", "K": "房地产业", "L": "租赁和商务服务业",
    "M": "科学研究和技术服务业", "N": "水利环境和公共设施管理业",
    "O": "居民服务修理和其他服务业", "P": "教育",
    "Q": "卫生和社会工作", "R": "文化体育和娱乐业", "S": "综合",
}

INDUSTRY_BASE = "https://quote.stockstar.com/stock/industry"


def _fetch_gbk(url: str) -> str | None:
    """GET + GBK decode(行业分类页用)."""
    for t in range(_RETRIES):
        try:
            _throttle()
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.content.decode("gbk", errors="replace")
        except Exception as e:
            logger.warning("stockstar _fetch_gbk %s try%d: %s", url, t + 1, repr(e)[:80])
            time.sleep(1.2 * (t + 1))
    return None


def build_industry_map(max_letters: int = 19) -> dict:
    """从证券之星爬取全部 CSRC 行业分类 → {code: industry_letter}.

    爬取 quote.stockstar.com/stock/industry_{A..S}.shtml (19 页),
    从每页的表格中提取股票代码, 返回 code → letter 映射.

    Args:
        max_letters: 最多爬几个字母(默认 19, =全部 A-S).
    Returns:
        dict[str, str]  如 {'600519': 'C', '000001': 'J', ...}
    """
    result = {}
    for i, letter in enumerate(CSRC_NAMES.keys()):
        if i >= max_letters:
            break
        url = f"{INDUSTRY_BASE}_{letter}.shtml"
        html = _fetch_gbk(url)
        if not html:
            logger.warning("build_industry_map: 跳过 %s (fetch 失败)", letter)
            continue
        # 从第二个 table 提取代码(第1列)
        tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
        if len(tables) < 2:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], re.S)
        for r in rows[1:]:  # 跳过表头
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
            if not cells:
                continue
            code = _clean(cells[0])
            if re.match(r"^\d{6}$", code):
                result[code] = letter
        logger.info("build_industry_map: %s(%s) → %d 只", letter, CSRC_NAMES.get(letter, "?"),
                     sum(1 for v in result.values() if v == letter))
    return result


def get_industry(code: str, cache: dict | None = None) -> dict:
    """查询单只股票的 CSRC 行业分类.

    Args:
        code: 6 位代码
        cache: 可选, build_industry_map() 的返回值(避免重复爬 19 页).
    Returns:
        {'code': str, 'letter': str|None, 'name': str|None}  未命中 →letter/name 为 None.
    """
    code = _code6(code)
    if cache is None:
        cache = build_industry_map()
    letter = cache.get(code)
    return {
        "code": code,
        "letter": letter,
        "name": CSRC_NAMES.get(letter) if letter else None,
    }


# ════════════════════════════════════════════════════════════════════════
# 便捷函数: 一键拿齐(三大表 + 分红 + 融资融券 + 行业) 给单只股票
# ════════════════════════════════════════════════════════════════════════

def fetch_all(code: str) -> dict:
    """一次拉全部 5 类数据(给单只股票).

    返回 dict = {
        'income':     DataFrame(利润表),
        'balance':    DataFrame(资产负债表),
        'cash_flow':  DataFrame(现金流量表),
        'dividend':   DataFrame(分红送配),
        'margin':     DataFrame(融资融券),
    } 任意 key 失败 -> 该 key 值为空 DataFrame.
    """
    code = _code6(code)
    return {
        "income": income_statement(code),
        "balance": balance_sheet(code),
        "cash_flow": cash_flow_statement(code),
        "dividend": dividend(code),
        "margin": margin_trading(code),
    }


if __name__ == "__main__":
    # 自检: 600519
    out = fetch_all("600519")
    for k, v in out.items():
        print(f"\n=== {k} (shape={v.shape}) ===")
        print(v.head(3).to_string())
