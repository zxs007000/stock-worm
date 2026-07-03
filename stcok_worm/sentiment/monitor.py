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
        self._history: Dict[str, List[SentimentData]] = {}

    def check_alerts(self, code: str) -> List[Dict]:
        alerts = []
        results = self.collector.collect(code, pages=1, with_comments=False)

        if not results:
            return alerts

        if code not in self._history:
            self._history[code] = []
        self._history[code].extend(results)
        self._history[code] = self._history[code][-100:]

        negative_count = sum(1 for r in results if r.sentiment < self.config.negative_threshold)
        if negative_count >= 5:
            alerts.append({
                "type": "negative_burst",
                "message": f"{code} 检测到 {negative_count} 条负面舆情",
                "level": "high",
                "count": negative_count,
                "time": datetime.now().isoformat(),
            })

        total_posts = len(results)
        if total_posts >= self.config.hot_threshold:
            alerts.append({
                "type": "hot_topic",
                "message": f"{code} 热度异常，共 {total_posts} 条讨论",
                "level": "medium",
                "count": total_posts,
                "time": datetime.now().isoformat(),
            })

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
        level_colors = {"high": "\033[91m", "medium": "\033[93m", "low": "\033[92m"}
        reset_color = "\033[0m"
        color = level_colors.get(alert.get("level", ""), "")

        print(f"{color}[预警] {alert['message']}{reset_color}")
        print(f"  时间: {alert.get('time', '')}")
        print(f"  级别: {alert.get('level', '')}")
        print()
