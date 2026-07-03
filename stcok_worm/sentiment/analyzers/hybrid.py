"""混合情感分析器 - 词典初筛 + LLM精细分析"""
import logging
from typing import Dict, Optional

from .dictionary import DictionaryAnalyzer
from .llm import LLMAnalyzer

logger = logging.getLogger(__name__)


class HybridAnalyzer:
    """混合情感分析器"""

    def __init__(self, threshold: float = 0.7,
                 llm_provider: str = "deepseek",
                 llm_model: str = "deepseek-chat",
                 llm_api_key: Optional[str] = None):
        self.threshold = threshold
        self.dictionary_analyzer = DictionaryAnalyzer()
        self.llm_analyzer = LLMAnalyzer(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
        )

    def analyze(self, text: str) -> Dict:
        if not text or not text.strip():
            return {
                "sentiment": 0.0,
                "confidence": 0.0,
                "method": "none",
                "keywords": [],
            }

        dict_result = self.dictionary_analyzer.analyze(text)

        if abs(dict_result["sentiment"]) >= self.threshold:
            return {
                **dict_result,
                "method": "dictionary",
            }

        llm_result = self.llm_analyzer.analyze(text)

        if llm_result["confidence"] > 0:
            weight_dict = 0.3
            weight_llm = 0.7
        else:
            weight_dict = 1.0
            weight_llm = 0.0

        final_sentiment = (
            dict_result["sentiment"] * weight_dict +
            llm_result["sentiment"] * weight_llm
        )
        final_confidence = (
            dict_result["confidence"] * weight_dict +
            llm_result["confidence"] * weight_llm
        )

        return {
            "sentiment": final_sentiment,
            "confidence": final_confidence,
            "method": "hybrid",
            "keywords": dict_result.get("keywords", []),
            "llm_reason": llm_result.get("reason", ""),
        }
