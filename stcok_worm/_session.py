"""
共用会话 + 东财限流器 + 重试机制

所有东方财富接口请求统一走 em_get()，内置串行限流 + 随机抖动 + 连接级重试。
"""

import logging
import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
PUSH2_URL = "https://push2.eastmoney.com/api/qt/clist/get"
PUSH2EX_URL = "https://push2ex.eastmoney.com/api/qt/clist/get"
REPORTAPI_URL = "https://reportapi.eastmoney.com/report/list"
SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"
NP_WEBLIST_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"

EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def _build_session() -> requests.Session:
    """构建带重试的东财 session。"""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


EM_SESSION = _build_session()


def em_get(url: str, params: dict = None, headers: dict = None,
           timeout: int = 15, **kwargs) -> requests.Response:
    """东财统一请求入口：自动节流 + 复用 session + 重试。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        resp = EM_SESSION.get(url, params=params, headers=headers,
                              timeout=timeout, **kwargs)
        return resp
    except requests.exceptions.RequestException as exc:
        logger.warning("em_get %s failed: %s", url[:80], exc)
        raise
    finally:
        _em_last_call[0] = time.time()


def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "",
                          sort_types: str = "-1") -> list:
    """东财数据中心统一查询。"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


def eastmoney_push2(fields: str, filt: str = "", fs: str = "",
                    sort_field: str = "", sort_type: str = "desc",
                    page_size: int = 20) -> list:
    """东财 push2 行情接口（行业板块/资金流等）。"""
    params = {
        "pn": "1", "pz": str(page_size),
        "po": "1" if sort_type == "desc" else "0",
        "np": "1", "fltt": "2", "invt": "2", "fid": sort_field,
        "fs": fs, "fields": fields,
    }
    if filt:
        params["fid"] = filt
    r = em_get(PUSH2_URL, params=params, timeout=15)
    d = r.json()
    if d.get("data") and d["data"].get("diff"):
        return d["data"]["diff"]
    return []


def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀 (sh/sz/bj)。"""
    code = code.strip().split(".")[0].strip().upper()
    if code.startswith(("SH", "SZ", "BJ")):
        code = code[2:]
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def get_secid(code: str) -> str:
    """代码 → 东财 secid (如 '0.000858', '1.600519')。"""
    code = code.strip().split(".")[0].strip()
    prefix = get_prefix(code)
    market = "1" if prefix == "sh" else "0"
    return f"{market}.{code}"
