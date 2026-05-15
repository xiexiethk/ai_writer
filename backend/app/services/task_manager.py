"""
后台任务管理器
"""
import asyncio
import logging
from typing import Dict, Any, Callable, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class Task:
    def __init__(self, task_id: str, func: Callable, *args, **kwargs):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.status = TaskStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.progress: float = 0

    async def run(self):
        """执行任务"""
        try:
            self.status = TaskStatus.RUNNING
            logger.info(f"任务 {self.task_id} 开始执行")
            self.result = await self.func(*self.args, **self.kwargs)
            self.status = TaskStatus.SUCCESS
            self.progress = 100
            logger.info(f"任务 {self.task_id} 执行成功")
        except Exception as e:
            self.status = TaskStatus.FAILED
            self.error = str(e)
            logger.error(f"任务 {self.task_id} 执行失败: {e}")
            raise


class TaskManager:
    """支持高并发的任务管理器"""

    def __init__(self, max_concurrent: int = 20):
        self.tasks: Dict[str, Task] = {}
        # 使用信号量控制最大并发数为 20
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def create_task(
        self, task_id: str, func: Callable, *args, **kwargs
    ) -> Task:
        """创建任务"""
        task = Task(task_id, func, *args, **kwargs)
        self.tasks[task_id] = task
        return task

    async def submit_task(
        self, task_id: str, func: Callable, *args, **kwargs
    ) -> Task:
        """提交任务并异步执行"""
        task = self.create_task(task_id, func, *args, **kwargs)

        # 在后台执行任务
        asyncio.create_task(self._execute_task(task))

        return task

    async def _execute_task(self, task: Task):
        """在信号量控制下执行任务"""
        async with self._semaphore:
            try:
                await task.run()
            except Exception as e:
                logger.error(f"任务执行异常: {e}")

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]


# 全局任务管理器
task_manager = TaskManager()
