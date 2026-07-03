"""爬虫测试"""
import pytest
from stcok_worm.sentiment.crawlers.guba import GubaCrawler


class TestGubaCrawler:
    def test_parse_posts(self):
        crawler = GubaCrawler()
        html = """
        <div class="listitem">
            <div class="title"><a href="/1.html">茅台今天大涨</a></div>
            <span class="l1">股神</span>
            <span class="l2">100</span>
            <span class="l3">50</span>
        </div>
        """
        posts = crawler._parse_posts(html)
        assert isinstance(posts, list)

    def test_parse_int(self):
        assert GubaCrawler._parse_int("100") == 100
        assert GubaCrawler._parse_int("1.5万") == 15000
        assert GubaCrawler._parse_int("abc") == 0
