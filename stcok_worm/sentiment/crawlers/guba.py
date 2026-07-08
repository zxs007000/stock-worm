"""东方财富股吧爬虫 - 使用Scrapling"""
import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import SentimentCrawlerBase
from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class GubaCrawler(SentimentCrawlerBase):
    """东方财富股吧爬虫"""

    name = "guba"
    platform = "guba"
    BASE_URL = "https://guba.eastmoney.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fetcher = None

    def _ensure_fetcher(self):
        if self._fetcher is None:
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
                self.logger.info("Scrapling StealthyFetcher 已就绪")
            except ImportError:
                raise RuntimeError("Scrapling 未安装: pip install scrapling")
        return self._fetcher

    def _fetch_page(self, url: str) -> str:
        fetcher = self._ensure_fetcher()
        resp = fetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            wait=3000,
            block_ads=True,
            disable_resources=True,
        )
        return resp.text

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        url = f"{self.BASE_URL}/list,{code},f_{page}.html"
        self.logger.info("爬取股吧: %s", url)

        try:
            html = self.retry(self._fetch_page, url)
            return self._parse_posts(html)
        except Exception as e:
            self.logger.error("爬取失败: %s", e)
            return []

    def _parse_posts(self, html: str) -> List[Post]:
        soup = BeautifulSoup(html, "lxml")
        posts = []

        for item in soup.select(".listitem, .articleh"):
            try:
                title_tag = item.select_one(".title a, .l3 a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                url = urljoin(self.BASE_URL, href) if href else ""

                author_tag = item.select_one(".l1, .author")
                author = author_tag.get_text(strip=True) if author_tag else ""

                stats = item.select(".l2, .l3, .stats span")
                reads = self._parse_int(stats[0].get_text()) if len(stats) > 0 else 0
                comments = self._parse_int(stats[1].get_text()) if len(stats) > 1 else 0

                posts.append(Post(
                    content=title,
                    author=author,
                    time="",
                    likes=reads,
                    comments_count=comments,
                    url=url,
                ))
            except Exception as e:
                self.logger.debug("解析帖子失败: %s", e)
                continue

        return posts

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        self.logger.info("爬取评论: %s", post_url)

        try:
            html = self.retry(self._fetch_page, post_url)
            return self._parse_comments(html, limit)
        except Exception as e:
            self.logger.error("爬取评论失败: %s", e)
            return []

    def _parse_comments(self, html: str, limit: int) -> List[HotComment]:
        soup = BeautifulSoup(html, "lxml")
        comments = []

        for item in soup.select(".comment-item, .reply-item")[:limit]:
            try:
                content_tag = item.select_one(".comment-content, .content")
                content = content_tag.get_text(strip=True) if content_tag else ""

                author_tag = item.select_one(".comment-author, .author")
                author = author_tag.get_text(strip=True) if author_tag else ""

                likes_tag = item.select_one(".comment-likes, .likes")
                likes = self._parse_int(likes_tag.get_text()) if likes_tag else 0

                if content:
                    comments.append(HotComment(
                        content=content,
                        author=author,
                        likes=likes,
                    ))
            except Exception as e:
                self.logger.debug("解析评论失败: %s", e)
                continue

        return comments

    @staticmethod
    def _parse_int(text: str) -> int:
        try:
            text = text.strip().replace(",", "")
            if "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            return int(float(text))
        except (ValueError, TypeError):
            return 0
