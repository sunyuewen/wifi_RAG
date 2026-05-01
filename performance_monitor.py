"""
Wi-Fi GPT 系统性能监控模块
实时追踪优化效果的关键指标，支持按阶段延迟分解和分位数统计
"""

import statistics
from datetime import datetime
from typing import Dict, List
from collections import defaultdict


class PerformanceMonitor:
    """性能指标收集器"""

    def __init__(self):
        self.metrics = {
            "router_cache_hits": 0,
            "router_cache_misses": 0,
            "local_rule_hits": 0,
            "llm_route_calls": 0,
            "total_queries": 0,
            "total_chitchat": 0,
            "total_technical": 0,
            "retrieval_cache_hits": 0,
            "retrieval_cache_misses": 0,
        }
        self.query_latencies: List[float] = []
        self.stage_latencies: Dict[str, List[float]] = defaultdict(list)
        self.document_uploads: Dict = {}
        self.file_duplicates_skipped: int = 0

    def log_stage_latency(self, stage: str, latency_seconds: float):
        """记录管线各阶段延迟"""
        self.stage_latencies[stage].append(latency_seconds)

    def log_query(self, route_source: str, latency: float, is_cached: bool,
                  route_result: int = 1):
        """
        记录查询路由和总延迟

        Args:
            route_source: "cache" / "local_rule" / "llm"
            latency: 总查询延迟（秒）
            is_cached: 路由缓存是否命中
            route_result: 0=闲聊 / 1=技术查询
        """
        self.metrics["total_queries"] += 1
        self.query_latencies.append(latency)

        if route_result == 0:
            self.metrics["total_chitchat"] += 1
        else:
            self.metrics["total_technical"] += 1

        if is_cached:
            self.metrics["router_cache_hits"] += 1
        else:
            self.metrics["router_cache_misses"] += 1

        if route_source == "llm":
            self.metrics["llm_route_calls"] += 1
        elif route_source == "local_rule":
            self.metrics["local_rule_hits"] += 1

    def log_upload(self, filename: str, new_chunks: int, skipped: int, elapsed: float):
        """记录文件上传信息"""
        self.document_uploads[filename] = {
            "new_chunks": new_chunks,
            "skipped": skipped,
            "time": elapsed,
            "timestamp": datetime.now().isoformat()
        }
        self.file_duplicates_skipped += skipped

    @staticmethod
    def _percentile(data: List[float], p: float) -> float:
        """计算分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    def get_report(self) -> Dict:
        """生成性能报告（含阶段延迟分解和分位数统计）"""
        total = self.metrics["total_queries"]

        if total == 0:
            return {"status": "暂无数据"}

        latencies = self.query_latencies
        cache_hit_rate = self.metrics["router_cache_hits"] / total * 100
        llm_call_rate = self.metrics["llm_route_calls"] / total * 100

        # 阶段延迟统计
        stage_stats = {}
        for stage, lats in self.stage_latencies.items():
            if lats:
                stage_stats[stage] = {
                    "count": len(lats),
                    "avg_s": round(statistics.mean(lats), 3),
                    "p50_s": round(self._percentile(lats, 50), 3),
                    "p90_s": round(self._percentile(lats, 90), 3),
                    "p99_s": round(self._percentile(lats, 99), 3),
                }

        return {
            "total_queries": total,
            "chitchat_queries": self.metrics["total_chitchat"],
            "technical_queries": self.metrics["total_technical"],
            "router_cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "llm_route_call_rate": f"{llm_call_rate:.1f}%",
            "retrieval_cache_hits": self.metrics["retrieval_cache_hits"],
            "retrieval_cache_misses": self.metrics["retrieval_cache_misses"],
            "latency": {
                "avg_s": round(statistics.mean(latencies), 3),
                "p50_s": round(self._percentile(latencies, 50), 3),
                "p90_s": round(self._percentile(latencies, 90), 3),
                "p99_s": round(self._percentile(latencies, 99), 3),
                "min_s": round(min(latencies), 3),
                "max_s": round(max(latencies), 3),
            },
            "stage_breakdown": stage_stats,
            "duplicate_files_skipped": self.file_duplicates_skipped,
            "total_uploads": len(self.document_uploads),
        }

    def print_dashboard(self):
        """打印性能仪表盘"""
        report = self.get_report()

        print("\n" + "=" * 60)
        print("Wi-Fi GPT 系统性能监控")
        print("=" * 60)

        for key, value in report.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for sub_key, sub_value in value.items():
                    print(f"    {sub_key}: {sub_value}")
            else:
                print(f"  {key}: {value}")

        print("=" * 60 + "\n")


# 全局单例
_monitor = PerformanceMonitor()


def log_query(route_source: str, latency: float, is_cached: bool = False,
              route_result: int = 1):
    _monitor.log_query(route_source, latency, is_cached, route_result)


def log_stage_latency(stage: str, latency_seconds: float):
    _monitor.log_stage_latency(stage, latency_seconds)


def log_upload(filename: str, new_chunks: int, skipped: int, elapsed: float):
    _monitor.log_upload(filename, new_chunks, skipped, elapsed)


def get_metrics() -> Dict:
    return _monitor.get_report()


def increment_retrieval_cache_hits():
    _monitor.metrics["retrieval_cache_hits"] += 1


def increment_retrieval_cache_misses():
    _monitor.metrics["retrieval_cache_misses"] += 1


if __name__ == "__main__":
    # 演示用法
    print("\n启动性能监控...")

    for i in range(10):
        log_query(
            route_source=["cache", "local_rule", "llm"][i % 3],
            latency=0.5 + i * 0.1,
            is_cached=(i % 3 == 0),
            route_result=1 if i % 2 == 0 else 0
        )

    log_stage_latency("routing", 0.05)
    log_stage_latency("routing", 0.08)
    log_stage_latency("retrieval", 0.3)
    log_stage_latency("retrieval", 0.45)

    log_upload("wifi_protocol.pdf", new_chunks=150, skipped=0, elapsed=2.5)
    log_upload("802.11be_spec.pdf", new_chunks=200, skipped=0, elapsed=3.2)

    _monitor.print_dashboard()
