"""词典情感分析器 - 快速、免费、可解释"""
import re
from typing import Dict, List

POSITIVE_WORDS = {
    "涨", "大涨", "暴涨", "涨停", "飙升", "拉升", "反弹", "突破", "新高",
    "盈利", "增长", "超预期", "利好", "分红", "送股", "高送转",
    "推荐", "买入", "增持", "看好", "看多", "做多", "牛市", "强势",
    "好", "棒", "厉害", "牛", "赞", "支持", "加油",
}

NEGATIVE_WORDS = {
    "跌", "大跌", "暴跌", "跌停", "崩盘", "破位", "新低", "回调",
    "亏损", "下降", "暴雷", "利空", "不及预期",
    "卖出", "减持", "看空", "做空", "熊市", "弱势",
    "差", "烂", "坑", "割肉", "套牢", "血亏",
}

NEGATION_WORDS = {"不", "没", "无", "非", "未", "别"}

INDUSTRY_KEYWORDS = {
    "白酒", "茅台", "五粮液", "银行", "券商", "保险", "地产",
    "科技", "芯片", "新能源", "光伏", "锂电", "医药", "消费",
}


class DictionaryAnalyzer:
    """词典情感分析器"""

    def __init__(self):
        self.positive_words = POSITIVE_WORDS
        self.negative_words = NEGATIVE_WORDS
        self.negation_words = NEGATION_WORDS

    def analyze(self, text: str) -> Dict:
        if not text or not text.strip():
            return {"sentiment": 0.0, "confidence": 0.0, "keywords": []}

        keywords = self._extract_keywords(text)
        pos_score, neg_score = self._calculate_scores(text)

        total = pos_score + neg_score
        if total == 0:
            sentiment = 0.0
            confidence = 0.0
        else:
            sentiment = (pos_score - neg_score) / total
            confidence = min(total / 10, 1.0)

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "keywords": keywords,
        }

    def _calculate_scores(self, text: str) -> tuple:
        pos_score = 0.0
        neg_score = 0.0
        words = self._tokenize(text)

        for i, word in enumerate(words):
            has_negation = False
            if i > 0 and words[i - 1] in self.negation_words:
                has_negation = True

            if word in self.positive_words:
                if has_negation:
                    neg_score += 1.0
                else:
                    pos_score += 1.0
            elif word in self.negative_words:
                if has_negation:
                    pos_score += 0.5
                else:
                    neg_score += 1.0

        return pos_score, neg_score

    def _tokenize(self, text: str) -> List[str]:
        parts = re.split(r'[，。！？、；：""''（）\[\]【】]', text)
        words = []
        for part in parts:
            for length in [4, 3, 2]:
                for i in range(len(part) - length + 1):
                    word = part[i:i + length]
                    if word in self.positive_words or word in self.negative_words:
                        words.append(word)
            for char in part:
                if char in self.positive_words or char in self.negative_words:
                    words.append(char)
        return words

    def _extract_keywords(self, text: str) -> List[str]:
        keywords = []
        for keyword in INDUSTRY_KEYWORDS:
            if keyword in text:
                keywords.append(keyword)
        return keywords
