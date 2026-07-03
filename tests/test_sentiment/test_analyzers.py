"""情感分析器测试"""
import pytest
from stcok_worm.sentiment.analyzers.dictionary import DictionaryAnalyzer


class TestDictionaryAnalyzer:
    def setup_method(self):
        self.analyzer = DictionaryAnalyzer()

    def test_positive_text(self):
        result = self.analyzer.analyze("茅台大涨，业绩超预期，强烈推荐买入")
        assert result["sentiment"] > 0
        assert result["confidence"] > 0

    def test_negative_text(self):
        result = self.analyzer.analyze("暴跌崩盘，业绩暴雷，赶紧跑")
        assert result["sentiment"] < 0
        assert result["confidence"] > 0

    def test_neutral_text(self):
        result = self.analyzer.analyze("今天天气不错")
        assert abs(result["sentiment"]) < 0.3

    def test_empty_text(self):
        result = self.analyzer.analyze("")
        assert result["sentiment"] == 0.0
        assert result["confidence"] == 0.0

    def test_keywords_extraction(self):
        result = self.analyzer.analyze("茅台白酒板块大涨")
        assert "茅台" in result["keywords"] or "白酒" in result["keywords"]
