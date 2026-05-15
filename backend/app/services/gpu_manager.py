"""
GPU 资源管理器 - 针对多 GPU 环境（如 4x A6000）进行负载均衡
"""
import os
import pynvml
import logging
import asyncio
import time
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class GPUManager:
    """管理和负载均衡多个 GPU 资源"""
    
    def __init__(self):
        self.initialized = False
        try:
            pynvml.nvmlInit()
            self.device_count = pynvml.nvmlDeviceGetCount()
            self.initialized = True
            logger.info(f"GPUManager 初始化成功，检测到 {self.device_count} 个 GPU")
        except Exception as e:
            logger.error(f"无法初始化 GPUManager: {e}")
            self.device_count = 0

    def _snapshot(self) -> List[Dict]:
        snapshots: List[Dict] = []
        if not self.initialized or self.device_count == 0:
            return snapshots
        for i in range(self.device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            snapshots.append({
                "index": i,
                "used_mb": int(mem.used / 1024**2),
                "free_mb": int(mem.free / 1024**2),
                "util_gpu": int(util.gpu),
            })
        return snapshots

    def get_best_gpu(
        self,
        *,
        max_utilization: Optional[int] = None,
        min_free_mb: Optional[int] = None,
    ) -> int:
        """
        获取当前最空闲的 GPU 索引
        如果没有检测到 GPU，默认返回 0
        """
        if not self.initialized or self.device_count == 0:
            return 0

        try:
            snapshots = self._snapshot()
            if not snapshots:
                return 0

            candidates = snapshots
            if max_utilization is not None:
                candidates = [item for item in candidates if item["util_gpu"] <= max_utilization]
            if min_free_mb is not None:
                candidates = [item for item in candidates if item["free_mb"] >= min_free_mb]

            ranked_pool = candidates or snapshots
            ranked_pool.sort(key=lambda item: (-item["free_mb"], item["util_gpu"], item["used_mb"]))
            best = ranked_pool[0]
            logger.info(
                "为新任务分配 GPU %s (free=%sMB, used=%sMB, util=%s%%)%s",
                best["index"],
                best["free_mb"],
                best["used_mb"],
                best["util_gpu"],
                "" if ranked_pool is candidates else " [未满足空闲阈值，已回退到最优可用 GPU]",
            )
            return best["index"]
        except Exception as e:
            logger.error(f"获取最佳 GPU 失败: {e}")
            return 0

    async def wait_for_available_gpu(
        self,
        *,
        max_utilization: int,
        min_free_mb: int,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> int:
        if not self.initialized or self.device_count == 0:
            return 0

        deadline = time.time() + max(1, timeout_seconds)
        while time.time() < deadline:
            snapshots = self._snapshot()
            candidates = [
                item for item in snapshots
                if item["util_gpu"] <= max_utilization and item["free_mb"] >= min_free_mb
            ]
            if candidates:
                candidates.sort(key=lambda item: (-item["free_mb"], item["util_gpu"], item["used_mb"]))
                best = candidates[0]
                logger.info(
                    "找到空闲 GPU %s (free=%sMB, used=%sMB, util=%s%%)",
                    best["index"], best["free_mb"], best["used_mb"], best["util_gpu"]
                )
                return best["index"]

            logger.info(
                "暂未找到满足阈值的空闲 GPU，等待中... (要求 free>=%sMB, util<=%s%%)",
                min_free_mb, max_utilization
            )
            await asyncio.sleep(max(1, poll_interval_seconds))

        logger.warning("等待空闲 GPU 超时，回退到当前最优 GPU")
        return self.get_best_gpu(max_utilization=max_utilization, min_free_mb=min_free_mb)

    def get_gpu_env(self, gpu_index: int = -1, *, max_utilization: Optional[int] = None, min_free_mb: Optional[int] = None) -> dict:
        """
        生成包含 CUDA_VISIBLE_DEVICES 的环境变量
        """
        if gpu_index == -1:
            gpu_index = self.get_best_gpu(max_utilization=max_utilization, min_free_mb=min_free_mb)
        
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        return env

    def __del__(self):
        if self.initialized:
            try:
                pynvml.nvmlShutdown()
            except:
                pass

# 全局 GPU 管理器
gpu_manager = GPUManager()
