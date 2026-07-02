"""
公告层 — 巨潮 cninfo 全量公告

端点:
    - stock_filings(code)           — 个股公告列表
"""

import json
import logging
from typing import Any, Dict, List

from ._session import em_get

logger = logging.getLogger(__name__)

ORG_MAP_URL = "https://static.szse.cn/DownloadReport/file/orgId.json"
_org_map_cache = {}


def _get_org_id(code: str) -> str:
    """动态解析巨潮 orgId。"""
    global _org_map_cache
    code = code.strip().split(".")[0]

    if not _org_map_cache:
        try:
            r = em_get(ORG_MAP_URL, timeout=5)
            _org_map_cache = r.json()
        except Exception:
            _org_map_cache = {}

    if code in _org_map_cache:
        return _org_map_cache[code]

    if code.startswith("6"):
        return f"gssz0{code}"
    return f"gssx0{code}"


def stock_filings(code: str, page_size: int = 10) -> List[Dict[str, Any]]:
    """
    个股公告列表 (巨潮 cninfo).

    Args:
        code: 6位代码
        page_size: 返回条数
    """
    org_id = _get_org_id(code)
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    data = {
        "stock": code,
        "tabName": "fulltext",
        "pageNum": "1",
        "pageSize": str(page_size),
        "column": "szse" if not code.startswith("6") else "sse",
        "category": "",
        "plate": "",
        "seDate": "",
        "searchkey": "",
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    try:
        from ._session import EM_SESSION
        r = EM_SESSION.post(url, data=data, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        result = r.json()
        if result.get("announcements"):
            return [
                {"title": a.get("announcementTitle", ""),
                 "time": a.get("announcementTime", ""),
                 "url": f"https://static.cninfo.com.cn/{a.get('adjunctUrl', '')}",
                 "type": a.get("announcementType", "")}
                for a in result["announcements"]
            ]
    except Exception as exc:
        logger.warning("stock_filings failed for %s: %s", code, exc)
    return []
