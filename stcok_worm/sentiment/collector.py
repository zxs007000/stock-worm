"""统一舆情采集器"""
import logging
from typing import List, Optional

from .models import SentimentData
from .crawlers import GubaCrawler, WeiboCrawler, DouyinCrawler, EastMoneyNewsCrawler, EastMoneyResearchCrawler
from .analyzers import HybridAnalyzer

logger = logging.getLogger(__name__)


class SentimentCollector:
    """统一舆情采集器"""

    def __init__(self, config=None):
        from .config import config as default_config
        self.config = config or default_config

        self.crawlers = {}
        # 默认启用新闻+研报（基于已有stcok_worm接口，稳定可靠）
        self.crawlers["eastmoney_news"] = EastMoneyNewsCrawler(delay=0.5)
        self.crawlers["eastmoney_research"] = EastMoneyResearchCrawler(delay=0.5)
        # 可选：需要爬虫的平台
        if self.config.enable_guba:
            self.crawlers["guba"] = GubaCrawler(delay=self.config.request_delay)
        if self.config.enable_weibo:
            self.crawlers["weibo"] = WeiboCrawler(delay=self.config.request_delay)
        if self.config.enable_douyin:
            self.crawlers["douyin"] = DouyinCrawler(delay=self.config.request_delay)

        self.analyzer = HybridAnalyzer(
            threshold=self.config.dictionary_threshold,
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            llm_api_key=self.config.llm_api_key,
        )

    def collect(self, code: str,
                platforms: Optional[List[str]] = None,
                pages: int = 1,
                with_comments: bool = True) -> List[SentimentData]:
        results = []
        target_platforms = platforms or list(self.crawlers.keys())

        for platform in target_platforms:
            crawler = self.crawlers.get(platform)
            if not crawler:
                logger.warning("平台 %s 未配置", platform)
                continue

            logger.info("采集 %s 平台数据: %s", platform, code)

            try:
                for page in range(1, pages + 1):
                    posts = crawler.crawl(code, page=page)

                    for post in posts:
                        hot_comments = []
                        if with_comments and post.url:
                            try:
                                hot_comments = crawler.crawl_comments(post.url)
                            except Exception as e:
                                logger.debug("爬取评论失败: %s", e)

                        full_text = post.content
                        if hot_comments:
                            full_text += " " + " ".join(c.content for c in hot_comments[:5])

                        sentiment_result = self.analyzer.analyze(full_text)

                        results.append(SentimentData(
                            code=code,
                            platform=platform,
                            post=post,
                            hot_comments=hot_comments,
                            sentiment=sentiment_result["sentiment"],
                            keywords=sentiment_result.get("keywords", []),
                        ))

                    crawler.rate_limit()

            except Exception as e:
                logger.error("采集 %s 平台失败: %s", platform, e)
                continue

        return results

    def query(self, code: str) -> dict:
        results = self.collect(code, pages=1, with_comments=False)

        if not results:
            return {
                "code": code,
                "sentiment": 0.0,
                "count": 0,
                "platforms": {},
            }

        platforms = {}
        for r in results:
            if r.platform not in platforms:
                platforms[r.platform] = {"count": 0, "sentiment": 0.0}
            platforms[r.platform]["count"] += 1
            platforms[r.platform]["sentiment"] += r.sentiment

        for p in platforms.values():
            p["sentiment"] /= p["count"] if p["count"] > 0 else 1

        total_sentiment = sum(r.sentiment for r in results) / len(results)

        return {
            "code": code,
            "sentiment": total_sentiment,
            "count": len(results),
            "platforms": platforms,
        }
