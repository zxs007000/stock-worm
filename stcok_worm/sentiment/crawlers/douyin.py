"""抖音爬虫 - 使用Crawl4AI"""
import asyncio
import json
import logging
import re
from typing import List

from .base import SentimentCrawlerBase
from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class DouyinCrawler(SentimentCrawlerBase):
    """抖音财经爬虫"""

    name = "douyin"
    platform = "douyin"
    BASE_URL = "https://www.douyin.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._crawler = None

    def _ensure_crawler(self):
        if self._crawler is None:
            try:
                from crawl4ai import AsyncWebCrawler
                self._crawler = AsyncWebCrawler(
                    headless=True,
                    verbose=False,
                    user_agent_mode="random",
                )
                self.logger.info("Crawl4AI 已就绪 (抖音)")
            except ImportError:
                raise RuntimeError("Crawl4AI 未安装: pip install crawl4ai")
        return self._crawler

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        """爬取抖音搜索结果"""
        keyword = self._code_to_keyword(code)
        url = f"{self.BASE_URL}/search/{keyword}?type=video"
        self.logger.info("爬取抖音: %s", keyword)

        try:
            return asyncio.run(self._async_crawl(url))
        except Exception as e:
            self.logger.error("抖音爬取失败: %s", e)
            return []

    async def _async_crawl(self, url: str) -> List[Post]:
        """异步爬取"""
        crawler = self._ensure_crawler()
        await crawler.start()

        try:
            result = await crawler.arun(
                url=url,
                wait_for="div[data-e2e='scroll-list']",
                js_code="window.scrollTo(0, document.body.scrollHeight);",
                page_timeout=30000,
                remove_overlay_elements=True,
                excluded_tags=["nav", "footer", "script", "style"],
            )

            if not result.success:
                self.logger.warning("抖音爬取失败: %s", result.error_message)
                return []

            return self._parse_markdown(result.markdown or "")
        finally:
            await crawler.close()

    def _parse_markdown(self, markdown: str) -> List[Post]:
        """从Markdown解析视频信息"""
        posts = []

        # 抖音搜索结果通常包含视频标题和描述
        lines = markdown.split("\n")
        current_post = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配视频标题（通常包含链接）
            if re.search(r'\[.*?\]\(https://www\.douyin\.com/video/\d+\)', line):
                if current_post:
                    posts.append(current_post)

                # 提取标题和URL
                match = re.search(r'\[(.*?)\]\(https://www\.douyin\.com/video/(\d+)\)', line)
                if match:
                    title = match.group(1)
                    video_id = match.group(2)
                    url = f"https://www.douyin.com/video/{video_id}"

                    current_post = Post(
                        content=title,
                        author="抖音用户",
                        time="",
                        url=url,
                    )
            elif current_post:
                # 累积描述内容
                if " likes " in line or " comments " in line:
                    # 解析互动数据
                    likes_match = re.search(r'(\d+)\s*likes', line)
                    comments_match = re.search(r'(\d+)\s*comments', line)

                    if likes_match:
                        current_post.likes = int(likes_match.group(1))
                    if comments_match:
                        current_post.comments_count = int(comments_match.group(1))
                else:
                    current_post.content += " " + line

        if current_post:
            posts.append(current_post)

        return posts

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        """爬取视频评论"""
        self.logger.info("爬取抖音评论: %s", post_url)

        try:
            return asyncio.run(self._async_crawl_comments(post_url, limit))
        except Exception as e:
            self.logger.error("爬取抖音评论失败: %s", e)
            return []

    async def _async_crawl_comments(self, url: str, limit: int) -> List[HotComment]:
        """异步爬取评论"""
        crawler = self._ensure_crawler()
        await crawler.start()

        try:
            # 滚动加载评论
            js_code = """
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(r => setTimeout(r, 2000));
            """

            result = await crawler.arun(
                url=url,
                js_code=js_code,
                page_timeout=30000,
                css_selector="div[data-e2e='comment-list']",
            )

            if not result.success:
                return []

            return self._parse_comments_markdown(result.markdown or "", limit)
        finally:
            await crawler.close()

    def _parse_comments_markdown(self, markdown: str, limit: int) -> List[HotComment]:
        """从Markdown解析评论"""
        comments = []
        lines = markdown.split("\n")

        for line in lines:
            if len(comments) >= limit:
                break

            line = line.strip()
            if not line or len(line) < 5:
                continue

            # 简单提取评论内容
            if not line.startswith("#") and not line.startswith("!"):
                comments.append(HotComment(
                    content=line[:200],  # 限制长度
                    author="抖音用户",
                    likes=0,
                ))

        return comments

    @staticmethod
    def _code_to_keyword(code: str) -> str:
        """股票代码转搜索关键词"""
        keyword_map = {
            "600519": "茅台",
            "000858": "五粮液",
            "300750": "宁德时代",
        }
        return keyword_map.get(code, code)
