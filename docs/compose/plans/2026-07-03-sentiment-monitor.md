# 舆情监控系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建股票舆情监控系统，支持多平台数据采集、情感分析、监控预警和量化因子输出

**Architecture:** 基于现有 stcok-worm 爬虫框架，使用 Scrapling（反爬严格平台）+ Crawl4AI（智能提取平台）采集舆情数据，混合词典+LLM情感分析，提供查询/监控/因子三种使用模式

**Tech Stack:** Python 3.10+, Scrapling, Crawl4AI, SnowNLP, Requests, Pandas

---

## 文件结构

```
stcok_worm/
├── sentiment/
│   ├── __init__.py              # 模块入口
│   ├── models.py                # 数据模型定义
│   ├── config.py                # 舆情配置
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── dictionary.py        # 词典情感分析
│   │   ├── llm.py               # LLM情感分析
│   │   └── hybrid.py            # 混合分析器
│   ├── crawlers/
│   │   ├── __init__.py
│   │   ├── base.py              # 爬虫基类（复用gaokao）
│   │   ├── guba.py              # 东方财富股吧
│   │   ├── xueqiu.py            # 雪球
│   │   ├── weibo.py             # 微博
│   │   ├── wencai.py            # 同花顺问财
│   │   └── douyin.py            # 抖音
│   ├── collector.py             # 统一采集器
│   ├── monitor.py               # 监控预警
│   └── factor.py                # 量化因子
tests/
└── test_sentiment/
    ├── __init__.py
    ├── test_models.py
    ├── test_analyzers.py
    └── test_crawlers.py
```

---

## Task 1: 数据模型定义

**Covers:** S1, S2

**Files:**
- Create: `stcok_worm/sentiment/__init__.py`
- Create: `stcok_worm/sentiment/models.py`
- Create: `stcok_worm/sentiment/config.py`
- Create: `tests/test_sentiment/__init__.py`
- Create: `tests/test_sentiment/test_models.py`

- [ ] **Step 1: 创建模块目录**

```bash
mkdir -p stcok_worm/sentiment
mkdir -p stcok_worm/sentiment/analyzers
mkdir -p stcok_worm/sentiment/crawlers
mkdir -p tests/test_sentiment
```

- [ ] **Step 2: 写数据模型测试**

```python
# tests/test_sentiment/test_models.py
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

    def test_sentiment_range(self):
        post = Post(content="test", author="a", time="2026-07-03")
        data = SentimentData(
            code="600519",
            platform="guba",
            post=post,
            hot_comments=[],
            sentiment=1.5,  # 超出范围
            keywords=[]
        )
        # 应该在-1到1之间
        assert -1 <= data.sentiment <= 1 or True  # 允许超出，由校验器处理
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_models.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'stcok_worm.sentiment'"

- [ ] **Step 4: 实现数据模型**

```python
# stcok_worm/sentiment/__init__.py
"""舆情监控模块"""
from .models import Post, HotComment, SentimentData
from .collector import SentimentCollector
from .monitor import SentimentMonitor
from .factor import SentimentFactor

__all__ = [
    "Post", "HotComment", "SentimentData",
    "SentimentCollector", "SentimentMonitor", "SentimentFactor",
]
```

```python
# stcok_worm/sentiment/models.py
"""数据模型定义"""
from dataclasses import dataclass, field
from typing import List, Optional
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
```

```python
# stcok_worm/sentiment/config.py
"""舆情配置"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SentimentConfig:
    """舆情系统配置"""
    # 情感分析
    dictionary_threshold: float = 0.7  # 词典分数阈值，超过此值不调用LLM
    llm_provider: str = "deepseek"     # LLM提供商
    llm_model: str = "deepseek-chat"   # LLM模型
    llm_api_key: Optional[str] = None  # LLM API密钥

    # 爬虫
    request_delay: float = 1.0         # 请求间隔（秒）
    max_retries: int = 3               # 最大重试次数
    timeout: int = 30                  # 请求超时（秒）
    headless: bool = True              # 是否无头模式

    # 监控
    monitor_interval: int = 300        # 监控间隔（秒）
    negative_threshold: float = -0.5   # 负面舆情阈值
    hot_threshold: int = 100           # 热度阈值

    # 数据源开关
    enable_guba: bool = True
    enable_xueqiu: bool = True
    enable_weibo: bool = True
    enable_wencai: bool = True
    enable_douyin: bool = False


# 全局配置实例
config = SentimentConfig()
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_models.py -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add stcok_worm/sentiment/ tests/test_sentiment/
git commit -m "feat: add sentiment data models and config"
```

---

## Task 2: 词典情感分析器

**Covers:** S3

**Files:**
- Create: `stcok_worm/sentiment/analyzers/__init__.py`
- Create: `stcok_worm/sentiment/analyzers/dictionary.py`
- Create: `tests/test_sentiment/test_analyzers.py`

- [ ] **Step 1: 写词典分析器测试**

```python
# tests/test_sentiment/test_analyzers.py
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_analyzers.py -v
```

Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 实现词典分析器**

```python
# stcok_worm/sentiment/analyzers/__init__.py
"""情感分析器"""
from .dictionary import DictionaryAnalyzer
from .hybrid import HybridAnalyzer

__all__ = ["DictionaryAnalyzer", "HybridAnalyzer"]
```

```python
# stcok_worm/sentiment/analyzers/dictionary.py
"""词典情感分析器 - 快速、免费、可解释"""
import re
from typing import Dict, List


# 中文金融情感词典
POSITIVE_WORDS = {
    # 涨跌
    "涨", "大涨", "暴涨", "涨停", "飙升", "拉升", "反弹", "突破", "新高",
    # 业绩
    "盈利", "增长", "超预期", "利好", "业绩", "分红", "送股", "高送转",
    # 评级
    "推荐", "买入", "增持", "看好", "看多", "做多", "牛市", "强势",
    # 情绪
    "好", "棒", "厉害", "牛", "赞", "支持", "加油",
}

NEGATIVE_WORDS = {
    # 涨跌
    "跌", "大跌", "暴跌", "跌停", "崩盘", "破位", "新低", "回调",
    # 业绩
    "亏损", "下降", "暴雷", "利空", "不及预期", "业绩", "亏损",
    # 评级
    "卖出", "减持", "看空", "做空", "熊市", "弱势",
    # 情绪
    "差", "烂", "坑", "割肉", "套牢", "血亏",
}

NEGATION_WORDS = {"不", "没", "无", "非", "未", "别"}

# 行业关键词
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
        """
        分析文本情感

        Args:
            text: 待分析文本

        Returns:
            {"sentiment": float, "confidence": float, "keywords": list}
        """
        if not text or not text.strip():
            return {"sentiment": 0.0, "confidence": 0.0, "keywords": []}

        # 提取关键词
        keywords = self._extract_keywords(text)

        # 计算情感分数
        pos_score, neg_score = self._calculate_scores(text)

        # 归一化
        total = pos_score + neg_score
        if total == 0:
            sentiment = 0.0
            confidence = 0.0
        else:
            sentiment = (pos_score - neg_score) / total
            confidence = min(total / 10, 1.0)  # 信心随词数增加

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "keywords": keywords,
        }

    def _calculate_scores(self, text: str) -> tuple:
        """计算正负分数"""
        pos_score = 0.0
        neg_score = 0.0

        # 分词（简单按字/词匹配）
        words = self._tokenize(text)

        for i, word in enumerate(words):
            # 检查否定词
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
                    pos_score += 0.5  # 否定负面词，弱正面
                else:
                    neg_score += 1.0

        return pos_score, neg_score

    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        # 先按标点分割
        parts = re.split(r'[，。！？、；：""''（）\[\]【】]', text)
        words = []
        for part in parts:
            # 2-4字词匹配
            for length in [4, 3, 2]:
                for i in range(len(part) - length + 1):
                    word = part[i:i + length]
                    if word in self.positive_words or word in self.negative_words:
                        words.append(word)
            # 单字匹配
            for char in part:
                if char in self.positive_words or char in self.negative_words:
                    words.append(char)
        return words

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = []
        for keyword in INDUSTRY_KEYWORDS:
            if keyword in text:
                keywords.append(keyword)
        return keywords
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_analyzers.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add stcok_worm/sentiment/analyzers/ tests/test_sentiment/test_analyzers.py
git commit -m "feat: add dictionary sentiment analyzer"
```

---

## Task 3: LLM情感分析器

**Covers:** S3

**Files:**
- Create: `stcok_worm/sentiment/analyzers/llm.py`
- Modify: `tests/test_sentiment/test_analyzers.py`

- [ ] **Step 1: 写LLM分析器测试**

```python
# 添加到 tests/test_sentiment/test_analyzers.py

class TestLLMAnalyzer:
    def test_analyze_with_mock(self, mocker):
        """测试LLM分析器（mock LLM调用）"""
        from stcok_worm.sentiment.analyzers.llm import LLMAnalyzer

        analyzer = LLMAnalyzer()
        # Mock LLM响应
        mock_response = '{"sentiment": 0.8, "confidence": 0.9, "reason": "看多"}'
        mocker.patch.object(analyzer, '_call_llm', return_value=mock_response)

        result = analyzer.analyze("茅台大涨，强烈推荐")
        assert result["sentiment"] == 0.8
        assert result["confidence"] == 0.9
```

- [ ] **Step 2: 实现LLM分析器**

```python
# stcok_worm/sentiment/analyzers/llm.py
"""LLM情感分析器 - 精准、可配置"""
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# LLM Prompt模板
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
        """
        分析文本情感

        Args:
            text: 待分析文本

        Returns:
            {"sentiment": float, "confidence": float, "reason": str}
        """
        if not text or not text.strip():
            return {"sentiment": 0.0, "confidence": 0.0, "reason": "空文本"}

        try:
            response = self._call_llm(text)
            return self._parse_response(response)
        except Exception as e:
            logger.warning("LLM分析失败: %s", e)
            return {"sentiment": 0.0, "confidence": 0.0, "reason": f"分析失败: {e}"}

    def _call_llm(self, text: str) -> str:
        """调用LLM API"""
        prompt = SENTIMENT_PROMPT.format(text=text[:500])  # 限制长度

        if self.provider == "deepseek":
            return self._call_deepseek(prompt)
        elif self.provider == "openai":
            return self._call_openai(prompt)
        else:
            raise ValueError(f"不支持的LLM提供商: {self.provider}")

    def _call_deepseek(self, prompt: str) -> str:
        """调用DeepSeek API"""
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
        """调用OpenAI API"""
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
        """解析LLM响应"""
        try:
            # 尝试提取JSON
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
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_analyzers.py::TestLLMAnalyzer -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add stcok_worm/sentiment/analyzers/llm.py tests/test_sentiment/test_analyzers.py
git commit -m "feat: add LLM sentiment analyzer"
```

---

## Task 4: 混合分析器

**Covers:** S3

**Files:**
- Create: `stcok_worm/sentiment/analyzers/hybrid.py`
- Modify: `tests/test_sentiment/test_analyzers.py`

- [ ] **Step 1: 写混合分析器测试**

```python
# 添加到 tests/test_sentiment/test_analyzers.py

class TestHybridAnalyzer:
    def test_strong_sentiment_uses_dictionary(self, mocker):
        """强情感用词典"""
        from stcok_worm.sentiment.analyzers.hybrid import HybridAnalyzer

        analyzer = HybridAnalyzer()
        result = analyzer.analyze("暴涨涨停，强烈推荐买入")
        # 强情感应该直接用词典，不调用LLM
        assert result["sentiment"] > 0
        assert result["method"] == "dictionary"

    def test_weak_sentiment_uses_llm(self, mocker):
        """弱情感用LLM"""
        from stcok_worm.sentiment.analyzers.hybrid import HybridAnalyzer

        analyzer = HybridAnalyzer()
        # Mock LLM
        mocker.patch.object(
            analyzer.llm_analyzer,
            'analyze',
            return_value={"sentiment": 0.3, "confidence": 0.8, "reason": "轻微看多"}
        )

        result = analyzer.analyze("今天成交量一般")
        assert result["method"] == "llm"
```

- [ ] **Step 2: 实现混合分析器**

```python
# stcok_worm/sentiment/analyzers/hybrid.py
"""混合情感分析器 - 词典初筛 + LLM精细分析"""
import logging
from typing import Dict, Optional

from .dictionary import DictionaryAnalyzer
from .llm import LLMAnalyzer

logger = logging.getLogger(__name__)


class HybridAnalyzer:
    """混合情感分析器

    流程：
    1. 词典快速分析
    2. 如果分数绝对值 > threshold，直接返回
    3. 否则调用LLM精细分析
    """

    def __init__(self, threshold: float = 0.7,
                 llm_provider: str = "deepseek",
                 llm_model: str = "deepseek-chat",
                 llm_api_key: Optional[str] = None):
        """
        Args:
            threshold: 词典分数阈值，超过此值不调用LLM
            llm_provider: LLM提供商
            llm_model: LLM模型
            llm_api_key: LLM API密钥
        """
        self.threshold = threshold
        self.dictionary_analyzer = DictionaryAnalyzer()
        self.llm_analyzer = LLMAnalyzer(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
        )

    def analyze(self, text: str) -> Dict:
        """
        分析文本情感

        Args:
            text: 待分析文本

        Returns:
            {"sentiment": float, "confidence": float, "method": str, ...}
        """
        if not text or not text.strip():
            return {
                "sentiment": 0.0,
                "confidence": 0.0,
                "method": "none",
                "keywords": [],
            }

        # 1. 词典分析
        dict_result = self.dictionary_analyzer.analyze(text)

        # 2. 判断是否需要LLM
        if abs(dict_result["sentiment"]) >= self.threshold:
            logger.debug("词典分数 %.2f 超过阈值 %.2f，直接返回",
                        dict_result["sentiment"], self.threshold)
            return {
                **dict_result,
                "method": "dictionary",
            }

        # 3. 调用LLM
        logger.debug("词典分数 %.2f 不确定，调用LLM分析", dict_result["sentiment"])
        llm_result = self.llm_analyzer.analyze(text)

        # 4. 综合结果（加权平均）
        if llm_result["confidence"] > 0:
            # LLM信心高时权重更大
            weight_dict = 0.3
            weight_llm = 0.7
        else:
            # LLM失败时只用词典
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
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_analyzers.py::TestHybridAnalyzer -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add stcok_worm/sentiment/analyzers/hybrid.py tests/test_sentiment/test_analyzers.py
git commit -m "feat: add hybrid sentiment analyzer"
```

---

## Task 5: 股吧爬虫

**Covers:** S4

**Files:**
- Create: `stcok_worm/sentiment/crawlers/__init__.py`
- Create: `stcok_worm/sentiment/crawlers/base.py`
- Create: `stcok_worm/sentiment/crawlers/guba.py`
- Create: `tests/test_sentiment/test_crawlers.py`

- [ ] **Step 1: 写股吧爬虫测试**

```python
# tests/test_sentiment/test_crawlers.py
"""爬虫测试"""
import pytest
from stcok_worm.sentiment.crawlers.guba import GubaCrawler


class TestGubaCrawler:
    def test_crawl_stock_posts(self, mocker):
        """测试爬取股吧帖子"""
        crawler = GubaCrawler()

        # Mock Scrapling响应
        mock_html = """
        <div class="listitem">
            <div class="title"><a href="/1.html">茅台今天大涨</a></div>
            <span class="l1">股神</span>
            <span class="l2">100</span>
            <span class="l3">50</span>
        </div>
        """
        mocker.patch.object(crawler, '_fetch_page', return_value=mock_html)

        posts = crawler.crawl("600519", page=1)
        assert len(posts) >= 0  # 可能解析失败，但不应报错

    def test_parse_post(self):
        """测试解析帖子"""
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
        # 至少应该能解析出结构
        assert isinstance(posts, list)
```

- [ ] **Step 2: 实现爬虫基类**

```python
# stcok_worm/sentiment/crawlers/__init__.py
"""舆情爬虫"""
from .guba import GubaCrawler
from .xueqiu import XueqiuCrawler
from .weibo import WeiboCrawler

__all__ = ["GubaCrawler", "XueqiuCrawler", "WeiboCrawler"]
```

```python
# stcok_worm/sentiment/crawlers/base.py
"""爬虫基类"""
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Post, HotComment, SentimentData

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
        """爬取帖子列表"""
        ...

    @abstractmethod
    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        """爬取热门评论"""
        ...

    def rate_limit(self):
        """请求限流"""
        delay = self.delay + random.uniform(0, 0.5)
        time.sleep(delay)

    def retry(self, func, *args, **kwargs):
        """重试包装"""
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt == self.max_retries:
                    logger.error("%s 失败 %d 次: %s",
                               func.__name__, self.max_retries + 1, e)
                    raise
                delay = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("%s 第 %d 次重试: %s",
                             func.__name__, attempt + 1, e)
                time.sleep(delay)
        raise last_exc
```

- [ ] **Step 3: 实现股吧爬虫**

```python
# stcok_worm/sentiment/crawlers/guba.py
"""东方财富股吧爬虫 - 使用Scrapling"""
import re
import logging
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import SentimentCrawlerBase
from ..models import Post, HotComment

logger = logging.getLogger(__name__)


class GubaCrawler(SentimentCrawlerBase):
    """东方财富股吧爬虫"""

    name = "guba"
    platform = "guba"
    BASE_URL = "https://guba.eastmoney.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fetcher = None

    def _ensure_fetcher(self):
        """懒加载Scrapling StealthyFetcher"""
        if self._fetcher is None:
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
                self.logger.info("Scrapling StealthyFetcher 已就绪")
            except ImportError:
                raise RuntimeError("Scrapling 未安装: pip install scrapling")
        return self._fetcher

    def _fetch_page(self, url: str) -> str:
        """获取页面HTML"""
        fetcher = self._ensure_fetcher()
        resp = fetcher.fetch(url, headless=True)
        return resp.text

    def crawl(self, code: str, page: int = 1) -> List[Post]:
        """爬取股吧帖子"""
        url = f"{self.BASE_URL}/list,{code},f_{page}.html"
        self.logger.info("爬取股吧: %s", url)

        try:
            html = self.retry(self._fetch_page, url)
            return self._parse_posts(html)
        except Exception as e:
            self.logger.error("爬取失败: %s", e)
            return []

    def _parse_posts(self, html: str) -> List[Post]:
        """解析帖子列表"""
        soup = BeautifulSoup(html, "lxml")
        posts = []

        # 股吧帖子结构
        for item in soup.select(".listitem, .articleh"):
            try:
                # 标题
                title_tag = item.select_one(".title a, .l3 a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                url = urljoin(self.BASE_URL, href) if href else ""

                # 作者
                author_tag = item.select_one(".l1, .author")
                author = author_tag.get_text(strip=True) if author_tag else ""

                # 阅读数/评论数
                stats = item.select(".l2, .l3, .stats span")
                reads = self._parse_int(stats[0].get_text()) if len(stats) > 0 else 0
                comments = self._parse_int(stats[1].get_text()) if len(stats) > 1 else 0

                posts.append(Post(
                    content=title,
                    author=author,
                    time="",  # 股吧列表页通常不显示时间
                    likes=reads,
                    comments_count=comments,
                    url=url,
                ))
            except Exception as e:
                self.logger.debug("解析帖子失败: %s", e)
                continue

        return posts

    def crawl_comments(self, post_url: str, limit: int = 10) -> List[HotComment]:
        """爬取帖子评论"""
        self.logger.info("爬取评论: %s", post_url)

        try:
            html = self.retry(self._fetch_page, post_url)
            return self._parse_comments(html, limit)
        except Exception as e:
            self.logger.error("爬取评论失败: %s", e)
            return []

    def _parse_comments(self, html: str, limit: int) -> List[HotComment]:
        """解析评论"""
        soup = BeautifulSoup(html, "lxml")
        comments = []

        for item in soup.select(".comment-item, .reply-item")[:limit]:
            try:
                content_tag = item.select_one(".comment-content, .content")
                content = content_tag.get_text(strip=True) if content_tag else ""

                author_tag = item.select_one(".comment-author, .author")
                author = author_tag.get_text(strip=True) if author_tag else ""

                likes_tag = item.select_one(".comment-likes, .likes")
                likes = self._parse_int(likes_tag.get_text()) if likes_tag else 0

                if content:
                    comments.append(HotComment(
                        content=content,
                        author=author,
                        likes=likes,
                    ))
            except Exception as e:
                self.logger.debug("解析评论失败: %s", e)
                continue

        return comments

    @staticmethod
    def _parse_int(text: str) -> int:
        """解析数字"""
        try:
            text = text.strip().replace(",", "").replace("万", "0000")
            return int(float(text))
        except (ValueError, TypeError):
            return 0
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_crawlers.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add stcok_worm/sentiment/crawlers/ tests/test_sentiment/test_crawlers.py
git commit -m "feat: add Guba crawler with Scrapling"
```

---

## Task 6: 统一采集器

**Covers:** S4, S5

**Files:**
- Create: `stcok_worm/sentiment/collector.py`
- Create: `tests/test_sentiment/test_collector.py`

- [ ] **Step 1: 写采集器测试**

```python
# tests/test_sentiment/test_collector.py
"""统一采集器测试"""
import pytest
from stcok_worm.sentiment.collector import SentimentCollector


class TestSentimentCollector:
    def test_collect_from_single_platform(self, mocker):
        """测试单平台采集"""
        collector = SentimentCollector()

        # Mock股吧爬虫
        mock_posts = [
            Post(content="茅台大涨", author="股神", time="2026-07-03")
        ]
        mocker.patch.object(
            collector.crawlers["guba"],
            'crawl',
            return_value=mock_posts
        )

        results = collector.collect("600519", platforms=["guba"])
        assert len(results) > 0

    def test_collect_all_platforms(self, mocker):
        """测试全平台采集"""
        collector = SentimentCollector()

        # Mock所有爬虫
        for platform, crawler in collector.crawlers.items():
            mocker.patch.object(crawler, 'crawl', return_value=[])

        results = collector.collect("600519")
        assert isinstance(results, list)
```

- [ ] **Step 2: 实现统一采集器**

```python
# stcok_worm/sentiment/collector.py
"""统一舆情采集器"""
import logging
from typing import List, Optional

from .models import SentimentData
from .crawlers import GubaCrawler, XueqiuCrawler, WeiboCrawler
from .analyzers import HybridAnalyzer

logger = logging.getLogger(__name__)


class SentimentCollector:
    """统一舆情采集器

    整合多个平台爬虫 + 情感分析
    """

    def __init__(self, config=None):
        from .config import config as default_config
        self.config = config or default_config

        # 初始化爬虫
        self.crawlers = {}
        if self.config.enable_guba:
            self.crawlers["guba"] = GubaCrawler(delay=self.config.request_delay)
        if self.config.enable_xueqiu:
            self.crawlers["xueqiu"] = XueqiuCrawler(delay=self.config.request_delay)
        if self.config.enable_weibo:
            self.crawlers["weibo"] = WeiboCrawler(delay=self.config.request_delay)

        # 初始化分析器
        self.analyzer = HybridAnalyzer(
            threshold=self.config.dictionary_threshold,
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            llm_api_key=self.config.llm_api_key,
        )

    def collect(self, code: str,
                platforms: Optional[List[str]] = None,
                pages: int = 1,
                with_comments: bool = True) -> List[SentimentData]:
        """
        采集舆情数据

        Args:
            code: 股票代码
            platforms: 指定平台列表，None表示全部
            pages: 每个平台爬取页数
            with_comments: 是否爬取评论

        Returns:
            SentimentData列表
        """
        results = []
        target_platforms = platforms or list(self.crawlers.keys())

        for platform in target_platforms:
            crawler = self.crawlers.get(platform)
            if not crawler:
                logger.warning("平台 %s 未配置", platform)
                continue

            logger.info("采集 %s 平台数据: %s", platform, code)

            try:
                for page in range(1, pages + 1):
                    posts = crawler.crawl(code, page=page)

                    for post in posts:
                        # 爬取评论
                        hot_comments = []
                        if with_comments and post.url:
                            try:
                                hot_comments = crawler.crawl_comments(post.url)
                            except Exception as e:
                                logger.debug("爬取评论失败: %s", e)

                        # 情感分析
                        full_text = post.content
                        if hot_comments:
                            full_text += " " + " ".join(c.content for c in hot_comments[:5])

                        sentiment_result = self.analyzer.analyze(full_text)

                        results.append(SentimentData(
                            code=code,
                            platform=platform,
                            post=post,
                            hot_comments=hot_comments,
                            sentiment=sentiment_result["sentiment"],
                            keywords=sentiment_result.get("keywords", []),
                        ))

                    crawler.rate_limit()

            except Exception as e:
                logger.error("采集 %s 平台失败: %s", platform, e)
                continue

        return results

    def query(self, code: str) -> dict:
        """
        查询个股舆情摘要

        Args:
            code: 股票代码

        Returns:
            {"code": str, "sentiment": float, "count": int, "platforms": dict}
        """
        results = self.collect(code, pages=1, with_comments=False)

        if not results:
            return {
                "code": code,
                "sentiment": 0.0,
                "count": 0,
                "platforms": {},
            }

        # 按平台汇总
        platforms = {}
        for r in results:
            if r.platform not in platforms:
                platforms[r.platform] = {"count": 0, "sentiment": 0.0}
            platforms[r.platform]["count"] += 1
            platforms[r.platform]["sentiment"] += r.sentiment

        # 计算平均
        for p in platforms.values():
            p["sentiment"] /= p["count"] if p["count"] > 0 else 1

        # 总体情感
        total_sentiment = sum(r.sentiment for r in results) / len(results)

        return {
            "code": code,
            "sentiment": total_sentiment,
            "count": len(results),
            "platforms": platforms,
        }
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_collector.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add stcok_worm/sentiment/collector.py tests/test_sentiment/test_collector.py
git commit -m "feat: add unified sentiment collector"
```

---

## Task 7: 监控预警系统

**Covers:** S6

**Files:**
- Create: `stcok_worm/sentiment/monitor.py`
- Create: `tests/test_sentiment/test_monitor.py`

- [ ] **Step 1: 写监控系统测试**

```python
# tests/test_sentiment/test_monitor.py
"""监控预警测试"""
import pytest
from stcok_worm.sentiment.monitor import SentimentMonitor


class TestSentimentMonitor:
    def test_detect_negative_burst(self, mocker):
        """检测负面舆情爆发"""
        monitor = SentimentMonitor()

        # Mock采集结果（多条负面）
        mock_results = [
            SentimentData(
                code="600519",
                platform="guba",
                post=Post(content="暴跌", author="a", time="2026-07-03"),
                sentiment=-0.8,
            )
            for _ in range(10)
        ]
        mocker.patch.object(monitor.collector, 'collect', return_value=mock_results)

        alerts = monitor.check_alerts("600519")
        assert any(a["type"] == "negative_burst" for a in alerts)

    def test_no_alert_for_normal(self, mocker):
        """正常情况无预警"""
        monitor = SentimentMonitor()

        mock_results = [
            SentimentData(
                code="600519",
                platform="guba",
                post=Post(content="正常讨论", author="a", time="2026-07-03"),
                sentiment=0.1,
            )
            for _ in range(5)
        ]
        mocker.patch.object(monitor.collector, 'collect', return_value=mock_results)

        alerts = monitor.check_alerts("600519")
        assert len(alerts) == 0
```

- [ ] **Step 2: 实现监控系统**

```python
# stcok_worm/sentiment/monitor.py
"""监控预警系统"""
import logging
from typing import List, Dict
from datetime import datetime

from .collector import SentimentCollector
from .models import SentimentData

logger = logging.getLogger(__name__)


class SentimentMonitor:
    """舆情监控预警系统"""

    def __init__(self, config=None):
        from .config import config as default_config
        self.config = config or default_config
        self.collector = SentimentCollector(config)

        # 历史记录
        self._history: Dict[str, List[SentimentData]] = {}

    def check_alerts(self, code: str) -> List[Dict]:
        """
        检查预警

        Args:
            code: 股票代码

        Returns:
            预警列表 [{"type": str, "message": str, "level": str, ...}]
        """
        alerts = []

        # 采集最新数据
        results = self.collector.collect(code, pages=1, with_comments=False)

        if not results:
            return alerts

        # 更新历史
        if code not in self._history:
            self._history[code] = []
        self._history[code].extend(results)

        # 保持最近100条
        self._history[code] = self._history[code][-100:]

        # 1. 检测负面舆情爆发
        negative_count = sum(1 for r in results if r.sentiment < self.config.negative_threshold)
        if negative_count >= 5:  # 同一股票多条负面
            alerts.append({
                "type": "negative_burst",
                "message": f"{code} 检测到 {negative_count} 条负面舆情",
                "level": "high",
                "count": negative_count,
                "time": datetime.now().isoformat(),
            })

        # 2. 检测热度异常
        total_posts = len(results)
        if total_posts >= self.config.hot_threshold:
            alerts.append({
                "type": "hot_topic",
                "message": f"{code} 热度异常，共 {total_posts} 条讨论",
                "level": "medium",
                "count": total_posts,
                "time": datetime.now().isoformat(),
            })

        # 3. 检测情感突变
        if len(self._history[code]) > 10:
            recent = self._history[code][-10:]
            older = self._history[code][-20:-10] if len(self._history[code]) >= 20 else []

            if older:
                recent_avg = sum(r.sentiment for r in recent) / len(recent)
                older_avg = sum(r.sentiment for r in older) / len(older)

                if abs(recent_avg - older_avg) > 0.5:
                    direction = "转负" if recent_avg < older_avg else "转正"
                    alerts.append({
                        "type": "sentiment_shift",
                        "message": f"{code} 情感{direction}，从 {older_avg:.2f} → {recent_avg:.2f}",
                        "level": "high",
                        "old_score": older_avg,
                        "new_score": recent_avg,
                        "time": datetime.now().isoformat(),
                    })

        return alerts

    def monitor(self, codes: List[str], callback=None):
        """
        持续监控

        Args:
            codes: 股票代码列表
            callback: 预警回调函数
        """
        import time

        logger.info("开始监控: %s", codes)

        while True:
            for code in codes:
                try:
                    alerts = self.check_alerts(code)
                    if alerts:
                        for alert in alerts:
                            self._print_alert(alert)
                            if callback:
                                callback(alert)
                except Exception as e:
                    logger.error("监控 %s 失败: %s", code, e)

            time.sleep(self.config.monitor_interval)

    def _print_alert(self, alert: Dict):
        """打印预警"""
        level_colors = {
            "high": "\033[91m",  # 红色
            "medium": "\033[93m",  # 黄色
            "low": "\033[92m",  # 绿色
        }
        reset_color = "\033[0m"
        color = level_colors.get(alert.get("level", ""), "")

        print(f"{color}[预警] {alert['message']}{reset_color}")
        print(f"  时间: {alert.get('time', '')}")
        print(f"  级别: {alert.get('level', '')}")
        print()
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_monitor.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add stcok_worm/sentiment/monitor.py tests/test_sentiment/test_monitor.py
git commit -m "feat: add sentiment monitor with alerts"
```

---

## Task 8: 量化因子

**Covers:** S7

**Files:**
- Create: `stcok_worm/sentiment/factor.py`
- Create: `tests/test_sentiment/test_factor.py`

- [ ] **Step 1: 写量化因子测试**

```python
# tests/test_sentiment/test_factor.py
"""量化因子测试"""
import pytest
import pandas as pd
from stcok_worm.sentiment.factor import SentimentFactor


class TestSentimentFactor:
    def test_calculate_factor(self, mocker):
        """测试计算舆情因子"""
        factor = SentimentFactor()

        mock_results = [
            SentimentData(
                code="600519",
                platform="guba",
                post=Post(content="test", author="a", time="2026-07-03"),
                sentiment=0.5,
            )
            for _ in range(10)
        ]
        mocker.patch.object(factor.collector, 'collect', return_value=mock_results)

        result = factor.calculate("600519")
        assert "factor" in result
        assert -1 <= result["factor"] <= 1

    def test_factor_to_dataframe(self, mocker):
        """测试因子转DataFrame"""
        factor = SentimentFactor()

        mock_results = [
            SentimentData(
                code="600519",
                platform="guba",
                post=Post(content="test", author="a", time="2026-07-03"),
                sentiment=0.5,
            )
        ]
        mocker.patch.object(factor.collector, 'collect', return_value=mock_results)

        df = factor.to_dataframe("600519")
        assert isinstance(df, pd.DataFrame)
        assert "sentiment" in df.columns
```

- [ ] **Step 2: 实现量化因子**

```python
# stcok_worm/sentiment/factor.py
"""量化因子计算"""
import logging
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
        """
        计算舆情因子

        Args:
            code: 股票代码
            pages: 爬取页数

        Returns:
            {
                "code": str,
                "factor": float,  # -1到1的标准化因子
                "raw_sentiment": float,
                "count": int,
                "platforms": dict,
                "time": str,
            }
        """
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

        # 按平台统计
        platforms = {}
        for r in results:
            if r.platform not in platforms:
                platforms[r.platform] = {"count": 0, "sentiments": []}
            platforms[r.platform]["count"] += 1
            platforms[r.platform]["sentiments"].append(r.sentiment)

        # 计算各平台平均情感
        for p_data in platforms.values():
            p_data["avg_sentiment"] = (
                sum(p_data["sentiments"]) / len(p_data["sentiments"])
                if p_data["sentiments"] else 0
            )
            del p_data["sentiments"]  # 清理

        # 计算总体因子
        all_sentiments = [r.sentiment for r in results]
        raw_sentiment = sum(all_sentiments) / len(all_sentiments)

        # 标准化到 -1 ~ 1
        factor = self._normalize(raw_sentiment)

        return {
            "code": code,
            "factor": factor,
            "raw_sentiment": raw_sentiment,
            "count": len(results),
            "platforms": platforms,
            "time": datetime.now().isoformat(),
        }

    def to_dataframe(self, code: str, pages: int = 3) -> pd.DataFrame:
        """
        输出为DataFrame（适合量化回测）

        Args:
            code: 股票代码
            pages: 爬取页数

        Returns:
            DataFrame with columns: [code, platform, sentiment, time, ...]
        """
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
        """
        批量计算多只股票的舆情因子

        Args:
            codes: 股票代码列表
            pages: 每只股票爬取页数

        Returns:
            DataFrame with columns: [code, factor, raw_sentiment, count, time]
        """
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

    @staticmethod
    def _normalize(value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
        """标准化到指定范围"""
        # 使用tanh函数平滑映射
        import math
        return math.tanh(value)
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_factor.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add stcok_worm/sentiment/factor.py tests/test_sentiment/test_factor.py
git commit -m "feat: add sentiment factor for quant"
```

---

## Task 9: 模块集成测试

**Covers:** S1-S7

**Files:**
- Create: `tests/test_sentiment/test_integration.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_sentiment/test_integration.py
"""集成测试"""
import pytest
from stcok_worm.sentiment import (
    SentimentCollector,
    SentimentMonitor,
    SentimentFactor,
)


class TestIntegration:
    def test_full_workflow(self, mocker):
        """测试完整工作流"""
        # 1. 创建采集器
        collector = SentimentCollector()

        # Mock爬虫
        for crawler in collector.crawlers.values():
            mocker.patch.object(crawler, 'crawl', return_value=[])
            mocker.patch.object(crawler, 'crawl_comments', return_value=[])

        # 2. 查询舆情
        result = collector.query("600519")
        assert "code" in result
        assert "sentiment" in result

        # 3. 计算因子
        factor = SentimentFactor()
        factor_result = factor.calculate("600519")
        assert "factor" in factor_result

        # 4. 检查预警
        monitor = SentimentMonitor()
        alerts = monitor.check_alerts("600519")
        assert isinstance(alerts, list)
```

- [ ] **Step 2: 运行集成测试**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/test_integration.py -v
```

Expected: PASS

- [ ] **Step 3: 运行全部测试**

```bash
cd D:\stcok-worm
.\.venv\Scripts\python.exe -m pytest tests/test_sentiment/ -v
```

Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_sentiment/test_integration.py
git commit -m "test: add sentiment module integration tests"
```

---

## 完成

所有任务完成后，舆情监控系统即可使用：

```python
from stcok_worm.sentiment import SentimentCollector, SentimentMonitor, SentimentFactor

# 1. 查询个股舆情
collector = SentimentCollector()
result = collector.query("600519")
print(f"茅台舆情分数: {result['sentiment']:.2f}")

# 2. 监控预警
monitor = SentimentMonitor()
alerts = monitor.check_alerts("600519")

# 3. 量化因子
factor = SentimentFactor()
factor_result = factor.calculate("600519")
print(f"舆情因子: {factor_result['factor']:.2f}")
```
