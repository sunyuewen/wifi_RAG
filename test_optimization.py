"""
? Wi-Fi GPT 优化效果测试脚本
用于验证增量索引、动态路由、MultiQuery配置等优化功能
"""

import requests
import time
import json
from typing import Dict, List

API_BASE = "http://127.0.0.1:8000"

class OptimizationTester:
    def __init__(self):
        self.api_key = "sk-e06716410cdb4207a0d57d07108d658c"  # 从.env读取
        self.results = {
            "路由缓存": [],
            "本地规则": [],
            "多查询": [],
            "增量索引": []
        }
    
    # ========================
    # ? 测试1: 动态路由缓存
    # ========================
    def test_router_cache(self):
        """测试路由缓存效果（同一问题多次查询应该更快）"""
        print("\n? [测试1] 动态路由缓存效果")
        print("-" * 50)
        
        test_queries = [
            ("你好，今天天气怎么样？", "闲聊", 0),
            ("WiFi 7的主要特性", "技术", 1),
            ("谢谢你的帮助", "闲聊", 0),
        ]
        
        for query, query_type, expected_route in test_queries:
            latencies = []
            
            for iteration in range(3):
                start = time.time()
                
                payload = {
                    "query": query,
                    "api_key": self.api_key,
                    "history": []
                }
                
                try:
                    response = requests.post(
                        f"{API_BASE}/chat/stream",
                        json=payload,
                        stream=True,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        list(response.iter_content(decode_unicode=True))  # 消费整个流
                    
                except Exception as e:
                    print(f"  ? 错误: {e}")
                    continue
                
                elapsed = time.time() - start
                latencies.append(elapsed)
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                min_latency = min(latencies)
                improvement = ((latencies[0] - min_latency) / latencies[0] * 100) if latencies[0] > 0 else 0
                
                print(f"  ? {query_type} 查询: '{query}'")
                print(f"     第1次: {latencies[0]:.2f}s")
                print(f"     第3次: {latencies[2]:.2f}s")
                print(f"     ? 缓存提速: {improvement:.1f}% {'?' if improvement > 10 else '?'}")
                
                self.results["路由缓存"].append({
                    "query": query,
                    "first": latencies[0],
                    "third": latencies[2],
                    "improvement": improvement
                })
    
    # ========================
    # ? 测试2: 本地规则判决
    # ========================
    def test_local_rules(self):
        """测试本地规则是否能正确分类问题"""
        print("\n? [测试2] 本地规则判决准确度")
        print("-" * 50)
        
        test_cases = [
            # (问题, 预期分类)
            ("你好", "闲聊"),
            ("WiFi协议", "技术"),
            ("谢谢", "闲聊"),
            ("802.11be", "技术"),
            ("怎么样", "闲聊"),
            ("参数优化", "技术"),
            ("今天", "闲聊"),
            ("频段设置", "技术"),
        ]
        
        for query, expected_class in test_cases:
            # 发送查询并观察分类结果
            # 由于系统返回答案而非分类标签，我们通过答案长度和内容推断分类
            
            payload = {
                "query": query,
                "api_key": self.api_key,
                "history": []
            }
            
            try:
                start = time.time()
                response = requests.post(
                    f"{API_BASE}/chat/stream",
                    json=payload,
                    stream=True,
                    timeout=10
                )
                
                answer = ""
                if response.status_code == 200:
                    answer = "".join(response.iter_content(decode_unicode=True))
                
                elapsed = time.time() - start
                
                # 简单启发式：技术回答通常包含"协议"、"参数"等词汇
                is_technical_answer = any(word in answer for word in ["802.11", "协议", "参数", "频段", "带宽"])
                detected_class = "技术" if is_technical_answer else "闲聊"
                
                status = "?" if detected_class == expected_class else "?"
                
                print(f"  {status} '{query}' → {detected_class} (耗时: {elapsed:.2f}s)")
                
                self.results["本地规则"].append({
                    "query": query,
                    "expected": expected_class,
                    "detected": detected_class,
                    "correct": detected_class == expected_class
                })
                
            except Exception as e:
                print(f"  ? 错误: {e}")
    
    # ========================
    # ? 测试3: MultiQuery参数
    # ========================\n    def test_multi_query_config(self):\n        \"\"\"测试MultiQuery参数配置效果\"\"\"\n        print(\"\\n? [测试3] MultiQuery配置效果\")\n        print(\"-\" * 50)\n        \n        query = \"WiFi 7的带宽和速率如何？\"\n        \n        for query_count in [1, 2, 3]:\n            payload = {\n                \"query\": query,\n                \"api_key\": self.api_key,\n                \"history\": [],\n                \"multi_query_count\": query_count\n            }\n            \n            try:\n                start = time.time()\n                response = requests.post(\n                    f\"{API_BASE}/chat/stream\",\n                    json=payload,\n                    stream=True,\n                    timeout=15\n                )\n                \n                answer = \"\"\n                if response.status_code == 200:\n                    answer = \"\".join(response.iter_content(decode_unicode=True))\n                \n                elapsed = time.time() - start\n                answer_length = len(answer)\n                \n                print(f\"  ? multi_query_count={query_count}:\")\n                print(f\"     耗时: {elapsed:.2f}s\")\n                print(f\"     回答长度: {answer_length} 字符\")\n                print(f\"     效率: {answer_length/elapsed:.0f} 字符/秒\")\n                \n                self.results[\"多查询\"].append({\n                    \"query_count\": query_count,\n                    \"time\": elapsed,\n                    \"length\": answer_length,\n                    \"efficiency\": answer_length / elapsed\n                })\n                \n            except Exception as e:\n                print(f\"  ? 错误: {e}\")\n    \n    # ========================\n    # ? 测试4: 增量索引去重\n    # ========================\n    def test_incremental_indexing(self):\n        \"\"\"测试增量索引和文档去重功能\"\"\"\n        print(\"\\n? [测试4] 增量索引去重\")\n        print(\"-\" * 50)\n        \n        # 模拟文件上传（需要实际PDF文件）\n        # 这里只展示测试框架\n        \n        print(\"  ? 提示: 需要实际PDF文件测试\")\n        print(\"  您可以手动上传同一文件两次，观察:\")\n        print(\"    1. 第一次上传: 显示 '新增 X 个知识块'\")\n        print(\"    2. 第二次上传: 显示 '跳过 1 个重复文件'\")\n        \n        self.results[\"增量索引\"].append({\n            \"status\": \"需要手动测试\",\n            \"instruction\": \"上传同一PDF文件两次验证去重效果\"\n        })\n    \n    def run_all_tests(self):\n        \"\"\"运行所有测试\"\"\"\n        print(\"\\n\" + \"=\"*60)\n        print(\"? Wi-Fi GPT 系统优化测试套件\")\n        print(\"=\"*60)\n        \n        try:\n            # 测试原始连接\n            response = requests.get(f\"{API_BASE}/docs\", timeout=5)\n            if response.status_code != 200:\n                print(\"? 无法连接后端服务，请确保 FastAPI 已启动\")\n                print(f\"   启动命令: python -m uvicorn main:app --reload\")\n                return\n        except:\n            print(\"? 无法连接后端服务\")\n            return\n        \n        print(\"? 后端服务连接成功\\n\")\n        \n        try:\n            self.test_router_cache()\n        except Exception as e:\n            print(f\"测试1失败: {e}\")\n        \n        try:\n            self.test_local_rules()\n        except Exception as e:\n            print(f\"测试2失败: {e}\")\n        \n        try:\n            self.test_multi_query_config()\n        except Exception as e:\n            print(f\"测试3失败: {e}\")\n        \n        try:\n            self.test_incremental_indexing()\n        except Exception as e:\n            print(f\"测试4失败: {e}\")\n        \n        self.print_summary()\n    \n    def print_summary(self):\n        \"\"\"打印测试总结\"\"\"\n        print(\"\\n\" + \"=\"*60)\n        print(\"? 测试总结\")\n        print(\"=\"*60)\n        \n        # 路由缓存测试\n        if self.results[\"路由缓存\"]:\n            print(\"\\n? 动态路由缓存\")\n            avg_improvement = sum(r[\"improvement\"] for r in self.results[\"路由缓存\"]) / len(self.results[\"路由缓存\"])\n            print(f\"   平均缓存提速: {avg_improvement:.1f}%\")\n        \n        # 本地规则测试\n        if self.results[\"本地规则\"]:\n            print(\"\\n? 本地规则判决\")\n            correct_count = sum(1 for r in self.results[\"本地规则\"] if r[\"correct\"])\n            accuracy = correct_count / len(self.results[\"本地规则\"]) * 100\n            print(f\"   准确度: {accuracy:.1f}% ({correct_count}/{len(self.results['本地规则'])})\")\n        \n        # 多查询测试\n        if self.results[\"多查询\"]:\n            print(\"\\n? MultiQuery参数灵活性\")\n            for r in self.results[\"多查询\"]:\n                print(f\"   查询数={r['query_count']}: {r['time']:.2f}s, \"\n                      f\"效率={r['efficiency']:.0f}字/秒\")\n        \n        print(\"\\n\" + \"=\"*60)\n        print(\"? 测试完成！\")\n        print(\"=\"*60 + \"\\n\")\n\n\nif __name__ == \"__main__\":\n    tester = OptimizationTester()\n    tester.run_all_tests()\n