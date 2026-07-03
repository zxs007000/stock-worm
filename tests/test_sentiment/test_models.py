"""数据模型测试"""
import pytest
from stcok_worm.sentiment.models import Post, HotComment, SentimentData


class TestPost:
    def test_create_post(self):
        post = Post(
            content="茅台今天涨了",
            author="股神",
            time="2026-07-03 10:00:00",
            likes=100,
            comments_count=50,
            reposts=20,
            url="https://example.com/1"
        )
        assert post.content == "茅台今天涨了"
        assert post.author == "股神"
        assert post.likes == 100

    def test_post_defaults(self):
        post = Post(content="test", author="a", time="2026-07-03")
        assert post.likes == 0
        assert post.comments_count == 0
        assert post.reposts == 0


class TestHotComment:
    def test_create_comment(self):
        comment = HotComment(
            content="看多",
            author="散户",
            likes=30,
            time="2026-07-03 10:30:00"
        )
        assert comment.content == "看多"
        assert comment.likes == 30


class TestSentimentData:
    def test_create_sentiment_data(self):
        post = Post(content="test", author="a", time="2026-07-03")
        data = SentimentData(
            code="600519",
            platform="guba",
            post=post,
            hot_comments=[],
            sentiment=0.75,
            keywords=["茅台", "白酒"]
        )
        assert data.code == "600519"
        assert data.platform == "guba"
        assert data.sentiment == 0.75
        assert len(data.keywords) == 2

    def test_to_dict(self):
        post = Post(content="test", author="a", time="2026-07-03")
        data = SentimentData(
            code="600519",
            platform="guba",
            post=post,
            sentiment=0.5,
        )
        d = data.to_dict()
        assert d["code"] == "600519"
        assert d["post"]["content"] == "test"
