"""
新闻层 — 东财个股新闻 + 全球资讯 + 金融界快讯 + 证券之星快讯

端点:
    - stock_news(code)              — 个股新闻流 (东财)
    - global_news(page_size)        — 全球财经资讯 7x24 (东财)
    - jrj_news(page, page_size)     — 7x24快讯 (金融界)
    - stockstar_express()           — 证券之星快讯 (SSR解析)
"""

import logging
import re
from typing import Any, Dict, List, Optional

import requests

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


# ── JRJ (金融界) 快讯 ──────────────────────────────────────

JRJ_NEWS_URL = "https://gateway.jrj.com/jrj-news/news/queryNewsList"
JRJ_NEWS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def jrj_news(page: int = 1, page_size: int = 20) -> Optional[Dict[str, Any]]:
    """7×24快讯 (金融界 gateway.jrj.com).

    Args:
        page: 页码
        page_size: 每页数量

    Returns:
        {total, list: [{id, title, source, pubTime, content, category, ...}]}
    """
    try:
        r = requests.post(JRJ_NEWS_URL, json={
            "pageNum": page,
            "pageSize": page_size,
        }, headers={
            "User-Agent": JRJ_NEWS_UA,
            "Referer": "https://www.jrj.com.cn/",
            "Content-Type": "application/json",
        }, timeout=15)
        d = r.json()
        if d.get("code") != 20000:
            logger.warning("jrj_news returned %s: %s", d.get("code"), d.get("msg"))
            return None
        data = d.get("data", {})
        return {
            "total": data.get("total", 0),
            "list": data.get("list", data.get("rows", [])),
        }
    except Exception as exc:
        logger.warning("jrj_news failed: %s", exc)
        return None


# ── 证券之星快讯 ───────────────────────────────────────────

STOCKSTAR_EXPRESS_URL = "https://express.stockstar.com/"
STOCKSTAR_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def stockstar_express() -> List[Dict[str, Any]]:
    """证券之星快讯 (SSR HTML 解析, 首页 20 条).

    Returns:
        [{pubcode, time, content, datarank, important, url}, ...]
        重要快讯 important=True 且 datarank 较高。
        SSR 渲染，无翻页参数。
    """
    try:
        r = requests.get(STOCKSTAR_EXPRESS_URL, headers={
            "User-Agent": STOCKSTAR_UA,
        }, timeout=15)
        html = r.text
    except Exception as exc:
        logger.warning("stockstar_express failed: %s", exc)
        return []

    # 提取快讯列表 <ul class="remark_list" data-date="YYYY-MM-DD">
    items = []
    blocks = re.findall(r'<ul[^>]*remark_list[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*>(.*?)</ul>', html, re.DOTALL)
    for _, block in blocks:
        lis = re.findall(r'<li[^>]*data-id="([^"]*)"[^>]*data-rank="([^"]*)"[^>]*>(.*?)</li>', block, re.DOTALL)
        for pubcode, rank_str, inner in lis:
            # 过滤模板占位项 (data-date="0")
            if not pubcode:
                continue
            # 提取时间和标题
            time_match = re.search(r'<span[^>]*class="[^"]*time[^"]*"[^>]*>(.*?)</span>', inner)
            content_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', inner)
            if not content_match:
                continue
            items.append({
                "pubcode": pubcode,
                "time": time_match.group(1).strip() if time_match else "",
                "content": content_match.group(2).strip(),
                "url": "https://express.stockstar.com" + content_match.group(1) if content_match.group(1).startswith('/') else content_match.group(1),
                "datarank": int(rank_str) if rank_str else 0,
                "important": 'red' in inner.split('</span>')[0].lower() if '</span>' in inner else False,
            })
    return items
