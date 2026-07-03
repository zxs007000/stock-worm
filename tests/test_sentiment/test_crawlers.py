"""爬虫测试"""
import pytest
from stcok_worm.sentiment.crawlers.guba import GubaCrawler
from stcok_worm.sentiment.crawlers.weibo import WeiboCrawler


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


class TestWeiboCrawler:
    def test_code_to_keyword(self):
        assert WeiboCrawler._code_to_keyword("600519") == "茅台"
        assert WeiboCrawler._code_to_keyword("000858") == "五粮液"
        assert WeiboCrawler._code_to_keyword("999999") == "999999"

    def test_clean_html(self):
        html = "<p>茅台<b>大涨</b></p>"
        assert WeiboCrawler._clean_html(html) == "茅台大涨"

    def test_parse_int(self):
        assert WeiboCrawler._parse_int("100") == 100
        assert WeiboCrawler._parse_int("1.5万") == 15000

    def test_parse_api_response(self):
        crawler = WeiboCrawler()
        data = {
            "data": {
                "cards": [
                    {
                        "card_type": 9,
                        "mblog": {
                            "text": "<p>茅台大涨</p>",
                            "user": {"screen_name": "股神", "id": 123},
                            "created_at": "2026-07-03",
                            "reposts_count": 10,
                            "comments_count": 20,
                            "attitudes_count": 100,
                            "id": "456",
                        }
                    }
                ]
            }
        }
        posts = crawler._parse_api_response(data)
        assert len(posts) == 1
        assert posts[0].content == "茅台大涨"
        assert posts[0].author == "股神"
        assert posts[0].likes == 100
