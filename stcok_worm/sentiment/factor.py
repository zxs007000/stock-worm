"""量化因子计算"""
import logging
import math
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd

from .collector import SentimentCollector
from .models import SentimentData

logger = logging.getLogger(__name__)


class SentimentFactor:
    """舆情量化因子"""

    def __init__(self, config=None):
        from .config import config as default_config
        self.config = config or default_config
        self.collector = SentimentCollector(config)

    def calculate(self, code: str, pages: int = 3) -> Dict:
        results = self.collector.collect(code, pages=pages, with_comments=False)

        if not results:
            return {
                "code": code,
                "factor": 0.0,
                "raw_sentiment": 0.0,
                "count": 0,
                "platforms": {},
                "time": datetime.now().isoformat(),
            }

        platforms = {}
        for r in results:
            if r.platform not in platforms:
                platforms[r.platform] = {"count": 0, "sentiments": []}
            platforms[r.platform]["count"] += 1
            platforms[r.platform]["sentiments"].append(r.sentiment)

        for p_data in platforms.values():
            p_data["avg_sentiment"] = (
                sum(p_data["sentiments"]) / len(p_data["sentiments"])
                if p_data["sentiments"] else 0
            )
            del p_data["sentiments"]

        all_sentiments = [r.sentiment for r in results]
        raw_sentiment = sum(all_sentiments) / len(all_sentiments)
        factor = math.tanh(raw_sentiment)

        return {
            "code": code,
            "factor": factor,
            "raw_sentiment": raw_sentiment,
            "count": len(results),
            "platforms": platforms,
            "time": datetime.now().isoformat(),
        }

    def to_dataframe(self, code: str, pages: int = 3) -> pd.DataFrame:
        results = self.collector.collect(code, pages=pages, with_comments=False)

        if not results:
            return pd.DataFrame()

        data = []
        for r in results:
            data.append({
                "code": r.code,
                "platform": r.platform,
                "content": r.post.content,
                "author": r.post.author,
                "sentiment": r.sentiment,
                "likes": r.post.likes,
                "comments_count": r.post.comments_count,
                "keywords": ",".join(r.keywords),
                "crawl_time": r.crawl_time,
            })

        return pd.DataFrame(data)

    def batch_factor(self, codes: List[str], pages: int = 2) -> pd.DataFrame:
        results = []
        for code in codes:
            try:
                result = self.calculate(code, pages=pages)
                results.append(result)
            except Exception as e:
                logger.error("计算 %s 因子失败: %s", code, e)
                results.append({
                    "code": code,
                    "factor": 0.0,
                    "raw_sentiment": 0.0,
                    "count": 0,
                    "time": datetime.now().isoformat(),
                })

        return pd.DataFrame(results)
