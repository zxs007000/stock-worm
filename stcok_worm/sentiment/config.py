"""舆情配置"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SentimentConfig:
    """舆情系统配置"""
    dictionary_threshold: float = 0.7
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_api_key: Optional[str] = None
    request_delay: float = 1.0
    max_retries: int = 3
    timeout: int = 30
    headless: bool = True
    monitor_interval: int = 300
    negative_threshold: float = -0.5
    hot_threshold: int = 100
    enable_guba: bool = True
    enable_xueqiu: bool = True
    enable_weibo: bool = True
    enable_wencai: bool = True
    enable_douyin: bool = False


config = SentimentConfig()
