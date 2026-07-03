"""爬虫基类"""
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import List

from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class SentimentCrawlerBase(ABC):
    """舆情爬虫基类"""

    name: str = ""
    platform: str = ""

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"crawler.{self.name}")

    @abstractmethod
    def crawl(self, code: str, page: int = 1) -> List[Post]:
        ...

    @abstractmethod
    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        ...

    def rate_limit(self):
        delay = self.delay + random.uniform(0, 0.5)
        time.sleep(delay)

    def retry(self, func, *args, **kwargs):
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt == self.max_retries:
                    logger.error("%s 失败 %d 次: %s", func.__name__, self.max_retries + 1, e)
                    raise
                delay = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("%s 第 %d 次重试: %s", func.__name__, attempt + 1, e)
                time.sleep(delay)
        raise last_exc
