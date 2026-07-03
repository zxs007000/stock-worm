"""微博爬虫 - 使用Scrapling"""
import json
import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import SentimentCrawlerBase
from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class WeiboCrawler(SentimentCrawlerBase):
    """微博财经爬虫"""

    name = "weibo"
    platform = "weibo"
    BASE_URL = "https://m.weibo.cn"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fetcher = None

    def _ensure_fetcher(self):
        if self._fetcher is None:
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
                self.logger.info("Scrapling StealthyFetcher 已就绪 (微博)")
            except ImportError:
                raise RuntimeError("Scrapling 未安装: pip install scrapling")
        return self._fetcher

    def _fetch_page(self, url: str) -> str:
        fetcher = self._ensure_fetcher()
        resp = fetcher.fetch(url, headless=True)
        return resp.text

    def _fetch_api(self, url: str) -> dict:
        """通过API获取数据（微博移动端API）"""
        fetcher = self._ensure_fetcher()
        resp = fetcher.fetch(url, headless=True)
        try:
            return json.loads(resp.text)
        except json.JSONDecodeError:
            return {}

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        """爬取微博搜索结果"""
        # 方案1: 通过移动端API搜索
        keyword = self._code_to_keyword(code)
        url = f"{self.BASE_URL}/api/container/getIndex?containerid=100103type%3D1%26q%3D{keyword}&page_type=searchall&page={page}"
        self.logger.info("爬取微博: %s", keyword)

        try:
            data = self.retry(self._fetch_api, url)
            return self._parse_api_response(data)
        except Exception as e:
            self.logger.warning("API方式失败，尝试HTML方式: %s", e)

        # 方案2: 通过HTML页面解析
        try:
            html_url = f"{self.BASE_URL}/search?containerid=100103type%3D1%26q%3D{keyword}"
            html = self.retry(self._fetch_page, html_url)
            return self._parse_html(html)
        except Exception as e:
            self.logger.error("微博爬取失败: %s", e)
            return []

    def _parse_api_response(self, data: dict) -> List[Post]:
        """解析API响应"""
        posts = []
        cards = data.get("data", {}).get("cards", [])

        for card in cards:
            if card.get("card_type") == 9:
                mblog = card.get("mblog", {})
                if not mblog:
                    continue

                content = self._clean_html(mblog.get("text", ""))
                author = mblog.get("user", {}).get("screen_name", "")
                created_at = mblog.get("created_at", "")
                reposts = mblog.get("reposts_count", 0)
                comments = mblog.get("comments_count", 0)
                attitudes = mblog.get("attitudes_count", 0)
                mid = mblog.get("id", "")

                url = f"https://weibo.com/{mblog.get('user', {}).get('id', '')}/{mid}" if mid else ""

                posts.append(Post(
                    content=content,
                    author=author,
                    time=created_at,
                    likes=attitudes,
                    comments_count=comments,
                    reposts=reposts,
                    url=url,
                ))

        return posts

    def _parse_html(self, html: str) -> List[Post]:
        """解析HTML页面"""
        soup = BeautifulSoup(html, "lxml")
        posts = []

        for item in soup.select(".card-wrap, .weibo-text"):
            try:
                content_tag = item.select_one(".text, .weibo-text")
                content = self._clean_html(content_tag.get_text(strip=True)) if content_tag else ""

                author_tag = item.select_one(".name, .author")
                author = author_tag.get_text(strip=True) if author_tag else ""

                time_tag = item.select_one(".time, .date")
                time_str = time_tag.get_text(strip=True) if time_tag else ""

                likes_tag = item.select_one(".like-num, .likes")
                likes = self._parse_int(likes_tag.get_text()) if likes_tag else 0

                if content:
                    posts.append(Post(
                        content=content,
                        author=author,
                        time=time_str,
                        likes=likes,
                    ))
            except Exception as e:
                self.logger.debug("解析微博失败: %s", e)
                continue

        return posts

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        """爬取微博评论"""
        self.logger.info("爬取微博评论: %s", post_url)

        try:
            # 提取微博ID
            mid = self._extract_mid(post_url)
            if not mid:
                return []

            # 通过API获取评论
            api_url = f"{self.BASE_URL}/api/comments/hotflow?id={mid}&mid={mid}&max_id_type=0"
            data = self.retry(self._fetch_api, api_url)
            return self._parse_comments_api(data, limit)
        except Exception as e:
            self.logger.error("爬取微博评论失败: %s", e)
            return []

    def _parse_comments_api(self, data: dict, limit: int) -> List[HotComment]:
        """解析评论API响应"""
        comments = []
        data_list = data.get("data", {}).get("data", [])

        for item in data_list[:limit]:
            try:
                content = item.get("text", "")
                author = item.get("user", {}).get("screen_name", "")
                likes = item.get("like_count", 0)
                created_at = item.get("created_at", "")

                if content:
                    comments.append(HotComment(
                        content=self._clean_html(content),
                        author=author,
                        likes=likes,
                        time=created_at,
                    ))
            except Exception as e:
                self.logger.debug("解析评论失败: %s", e)
                continue

        return comments

    @staticmethod
    def _code_to_keyword(code: str) -> str:
        """股票代码转搜索关键词"""
        # 简单映射，实际可以查股票名称
        keyword_map = {
            "600519": "茅台",
            "000858": "五粮液",
            "300750": "宁德时代",
        }
        return keyword_map.get(code, code)

    @staticmethod
    def _clean_html(html: str) -> str:
        """清理HTML标签"""
        clean = re.sub(r'<[^>]+>', '', html)
        clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
        return clean.strip()

    @staticmethod
    def _extract_mid(url: str) -> str:
        """从URL提取微博ID"""
        match = re.search(r'/(\d+)/(\w+)', url)
        if match:
            return match.group(2)
        match = re.search(r'mid=(\d+)', url)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _parse_int(text: str) -> int:
        try:
            text = text.strip().replace(",", "")
            if "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            return int(float(text))
        except (ValueError, TypeError):
            return 0
