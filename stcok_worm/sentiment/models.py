"""数据模型定义"""
from dataclasses import dataclass, field
from typing import List
from datetime import datetime


@dataclass
class Post:
    """帖子/文章"""
    content: str
    author: str
    time: str
    likes: int = 0
    comments_count: int = 0
    reposts: int = 0
    url: str = ""


@dataclass
class HotComment:
    """热门评论"""
    content: str
    author: str
    likes: int = 0
    time: str = ""


@dataclass
class SentimentData:
    """舆情数据"""
    code: str
    platform: str
    post: Post
    hot_comments: List[HotComment] = field(default_factory=list)
    sentiment: float = 0.0
    keywords: List[str] = field(default_factory=list)
    raw_html: str = ""
    crawl_time: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """转为字典"""
        return {
            "code": self.code,
            "platform": self.platform,
            "post": {
                "content": self.post.content,
                "author": self.post.author,
                "time": self.post.time,
                "likes": self.post.likes,
                "comments_count": self.post.comments_count,
                "reposts": self.post.reposts,
                "url": self.post.url,
            },
            "hot_comments": [
                {
                    "content": c.content,
                    "author": c.author,
                    "likes": c.likes,
                    "time": c.time,
                }
                for c in self.hot_comments
            ],
            "sentiment": self.sentiment,
            "keywords": self.keywords,
            "crawl_time": self.crawl_time,
        }
