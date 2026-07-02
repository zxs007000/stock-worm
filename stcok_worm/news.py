"""
新闻层 — 东财个股新闻 + 全球资讯

端点:
    - stock_news(code)              — 个股新闻流
    - global_news(page_size)        — 全球财经资讯 (7x24)
"""

import logging
from typing import Any, Dict, List

from ._session import em_get

logger = logging.getLogger(__name__)


def stock_news(code: str, page_size: int = 10) -> List[Dict[str, Any]]:
    """个股新闻流 (东财 search-api-web)."""
    code = code.strip().split(".")[0]
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "jQuery",
        "param": (
            f'{{"uid":"","keyword":"{code}","type":["cmsArticleWebOld"],'
            f'"client":"web","clientType":"web","clientVersion":"curr",'
            f'"param":{{"cmsArticleWebOld":{{"searchScope":"default",'
            f'"sort":"default","pageIndex":1,"pageSize":{page_size},'
            f'"preTag":"<em>","postTag":"</em>"}}}}}}'
        ),
    }
    try:
        r = em_get(url, params=params, timeout=10)
        text = r.text
        import json
        import re
        match = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            articles = data.get("result", {}).get("cmsArticleWebOld", [])
            if isinstance(articles, dict):
                articles = articles.get("list", [])
            return [
                {"title": a.get("title", "").replace("<em>", "").replace("</em>", ""),
                 "time": a.get("date", ""),
                 "url": a.get("url", ""),
                 "source": a.get("mediaName", "")}
                for a in articles
            ]
    except Exception as exc:
        logger.warning("stock_news failed for %s: %s", code, exc)
    return []


def global_news(page_size: int = 20) -> List[Dict[str, Any]]:
    """全球财经资讯 (东财 np-weblist, 7x24)."""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    params = {
        "client": "web",
        "biz": "web_home_channel",
        "column": "102",
        "order": "1",
        "needInteractData": "0",
        "page_index": "1",
        "page_size": str(page_size),
    }
    try:
        r = em_get(url, params=params, timeout=10)
        data = r.json()
        if data.get("data") and data["data"].get("list"):
            return [
                {"title": n.get("title", ""),
                 "time": n.get("showTime", ""),
                 "url": n.get("url", ""),
                 "source": n.get("source", "")}
                for n in data["data"]["list"]
            ]
    except Exception as exc:
        logger.warning("global_news failed: %s", exc)
    return []
