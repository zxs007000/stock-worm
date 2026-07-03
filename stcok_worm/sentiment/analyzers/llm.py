"""LLM情感分析器 - 精准、可配置"""
import json
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """你是一个专业的金融舆情分析师。请分析以下文本的情感倾向。

文本：{text}

请返回JSON格式：
{{
    "sentiment": <-1到1之间的浮点数，负数表示负面，正数表示正面>,
    "confidence": <0到1之间的浮点数，表示分析置信度>,
    "reason": "<一句话解释分析理由>"
}}

只返回JSON，不要其他内容。"""


class LLMAnalyzer:
    """LLM情感分析器"""

    def __init__(self, provider: str = "deepseek", model: str = "deepseek-chat",
                 api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key

    def analyze(self, text: str) -> Dict:
        if not text or not text.strip():
            return {"sentiment": 0.0, "confidence": 0.0, "reason": "空文本"}

        try:
            response = self._call_llm(text)
            return self._parse_response(response)
        except Exception as e:
            logger.warning("LLM分析失败: %s", e)
            return {"sentiment": 0.0, "confidence": 0.0, "reason": f"分析失败: {e}"}

    def _call_llm(self, text: str) -> str:
        prompt = SENTIMENT_PROMPT.format(text=text[:500])

        if self.provider == "deepseek":
            return self._call_deepseek(prompt)
        elif self.provider == "openai":
            return self._call_openai(prompt)
        else:
            raise ValueError(f"不支持的LLM提供商: {self.provider}")

    def _call_deepseek(self, prompt: str) -> str:
        import requests

        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_openai(self, prompt: str) -> str:
        import requests

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> Dict:
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "sentiment": float(data.get("sentiment", 0)),
                    "confidence": float(data.get("confidence", 0)),
                    "reason": data.get("reason", ""),
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("解析LLM响应失败: %s", e)

        return {"sentiment": 0.0, "confidence": 0.0, "reason": "解析失败"}
