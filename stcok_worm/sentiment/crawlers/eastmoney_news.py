"""东财新闻爬虫 - 使用已有stcok_worm接口"""
import logging
from typing import List

from .base import SentimentCrawlerBase
from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class EastMoneyNewsCrawler(SentimentCrawlerBase):
    """东财新闻爬虫 - 基于stcok_worm.news模块"""

    name = "eastmoney_news"
    platform = "eastmoney_news"

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        from stcok_worm import news

        try:
            articles = news.stock_news(code, page_size=10)
            posts = []
            for a in articles:
                posts.append(Post(
                    content=a.get("title", ""),
                    author=a.get("source", ""),
                    time=a.get("time", ""),
                    url=a.get("url", ""),
                ))
            return posts
        except Exception as e:
            self.logger.error("东财新闻爬取失败: %s", e)
            return []

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        return []


class EastMoneyResearchCrawler(SentimentCrawlerBase):
    """东财研报爬虫 - 基于stcok_worm.research模块"""

    name = "eastmoney_research"
    platform = "eastmoney_research"

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        from stcok_worm import research

        try:
            reports = research.stock_reports(code, page_size=5)
            posts = []
            for r in reports:
                title = r.get("title", "")
                org = r.get("orgSName", "")
                rating = r.get("emRatingName", "")
                content = f"{title} ({org} {rating})" if org else title

                posts.append(Post(
                    content=content,
                    author=org,
                    time=r.get("publishDate", ""),
                ))
            return posts
        except Exception as e:
            self.logger.error("东财研报爬取失败: %s", e)
            return []

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        return []
