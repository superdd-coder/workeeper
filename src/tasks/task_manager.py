"""异步任务队列管理器 - 支持文件上传队列化和进度追踪"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine
from datetime import datetime

logger = logging.getLogger("task_manager")


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    filename: str
    collection: str = "default"
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "collection": self.collection,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def to_dict_with_type(self, task_type: str) -> dict[str, Any]:
        d = self.to_dict()
        d["task_type"] = task_type
        return d


class TaskManager:
    """管理异步任务队列"""

    def __init__(self, max_concurrent: int = 5, timeout: int = 3600):
        self.tasks: dict[str, Task] = {}
        self._task_args: dict[str, tuple[str, dict]] = {}  # task_id -> (task_type, kwargs)
        self._async_tasks: dict[str, asyncio.Task] = {}  # task_id -> asyncio.Task
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._running = 0
        self._processor_task: asyncio.Task | None = None
        self._handlers: dict[str, Callable[..., Coroutine]] = {}

    def register_handler(self, task_type: str, handler: Callable[..., Coroutine]):
        """注册任务处理器"""
        self._handlers[task_type] = handler

    async def start(self):
        """启动任务处理器"""
        if self._processor_task is None:
            self._processor_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """停止任务处理器"""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            self._processor_task = None

    def create_task(self, filename: str, task_type: str = "upload", collection: str = "default", **kwargs) -> Task:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            filename=filename,
            collection=collection,
            message="Queued for processing",
        )
        self.tasks[task_id] = task
        self._task_args[task_id] = (task_type, kwargs)
        asyncio.create_task(self._enqueue_task(task_id, task_type, kwargs))
        return task

    def cancel_task(self, task_id: str) -> bool:
        """取消正在运行或等待中的任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False
        atask = self._async_tasks.get(task_id)
        if atask and not atask.done():
            atask.cancel()
        task.status = TaskStatus.FAILED
        task.error = "Cancelled by user"
        task.message = "Cancelled"
        task.completed_at = datetime.now()
        return True

    def clear_completed_tasks(self) -> None:
        """删除所有已完成或失败的任务"""
        to_remove = [tid for tid, t in self.tasks.items() if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        for tid in to_remove:
            del self.tasks[tid]
            self._task_args.pop(tid, None)

    def retry_task(self, task_id: str) -> Task | None:
        """重新排队失败的任务"""
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.FAILED:
            return None
        args = self._task_args.get(task_id)
        if not args:
            return None
        task_type, kwargs = args
        # Reset task state
        task.status = TaskStatus.PENDING
        task.progress = 0.0
        task.message = "Re-queued"
        task.error = None
        task.result = None
        task.started_at = None
        task.completed_at = None
        asyncio.create_task(self._enqueue_task(task_id, task_type, kwargs))
        return task

    async def _enqueue_task(self, task_id: str, task_type: str, kwargs: dict):
        """将任务加入队列"""
        await self.queue.put((task_id, task_type, kwargs))

    async def _process_queue(self):
        """处理任务队列"""
        logger.info("Task queue processor started")
        while True:
            try:
                # 等待任务
                task_id, task_type, kwargs = await self.queue.get()
                logger.info("Dequeued task %s type=%s", task_id, task_type)

                # 检查并发限制
                while self._running >= self.max_concurrent:
                    await asyncio.sleep(0.1)

                # 处理任务
                self._running += 1
                logger.info("Executing task %s (running=%d)", task_id, self._running)
                atask = asyncio.create_task(self._execute_task(task_id, task_type, kwargs))
                self._async_tasks[task_id] = atask

            except asyncio.CancelledError:
                logger.info("Task queue processor cancelled")
                break
            except Exception as e:
                logger.error("Queue processor error: %s", e, exc_info=True)

    async def _execute_task(self, task_id: str, task_type: str, kwargs: dict):
        """执行单个任务（带超时）"""
        task = self.tasks.get(task_id)
        if not task:
            self._running -= 1
            return

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now()
        task.message = "Processing..."
        logger.info("[TASK %s] Starting execution: type=%s kwargs=%s", task_id, task_type, {k: v for k, v in kwargs.items() if k != "file_path"})

        try:
            handler = self._handlers.get(task_type)
            if not handler:
                raise ValueError(f"No handler registered for task type: {task_type}")

            kwargs["collection"] = task.collection
            loop = asyncio.get_running_loop()

            async def _run():
                if asyncio.iscoroutinefunction(handler):
                    return await handler(task, **kwargs)
                return await loop.run_in_executor(None, lambda: handler(task, **kwargs))

            result = await asyncio.wait_for(_run(), timeout=self.timeout)

            task.status = TaskStatus.COMPLETED
            task.progress = 100.0
            task.message = "Completed"
            task.result = result
            task.completed_at = datetime.now()
            logger.info("[TASK %s] COMPLETED: %s", task_id, result)

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task timed out after {self.timeout}s"
            task.message = f"Failed: timed out after {self.timeout}s"
            task.completed_at = datetime.now()
            logger.error("[TASK %s] TIMED OUT after %ds", task_id, self.timeout)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.message = f"Failed: {str(e)}"
            task.completed_at = datetime.now()
            logger.error("[TASK %s] FAILED: %s", task_id, e, exc_info=True)

        finally:
            self._async_tasks.pop(task_id, None)
            self._running -= 1

    def get_task(self, task_id: str) -> Task | None:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def get_all_tasks(self, collection: str | None = None) -> list[Task]:
        """获取所有任务，可按collection过滤"""
        tasks = self.tasks.values()
        if collection:
            tasks = [t for t in tasks if t.collection == collection]
        return list(tasks)

    def get_pending_tasks(self, collection: str | None = None) -> list[Task]:
        """获取待处理任务"""
        tasks = [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]
        if collection:
            tasks = [t for t in tasks if t.collection == collection]
        return tasks

    def get_processing_tasks(self, collection: str | None = None) -> list[Task]:
        """获取正在处理的任务"""
        tasks = [t for t in self.tasks.values() if t.status == TaskStatus.PROCESSING]
        if collection:
            tasks = [t for t in tasks if t.collection == collection]
        return tasks

    def get_active_tasks(self, collection: str | None = None, task_type: str | None = None) -> list[dict]:
        """Get active (pending/processing) tasks with type info, optionally filtered by collection and type."""
        result = []
        for task_id, task in self.tasks.items():
            if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                continue
            if collection and task.collection != collection:
                continue
            ttype, _ = self._task_args.get(task_id, ("unknown", {}))
            if task_type and ttype != task_type:
                continue
            result.append(task.to_dict_with_type(ttype))
        return result

    def has_active_task(self, collection: str, task_type: str) -> bool:
        """Check if there's an active task of given type for a collection."""
        for task_id, task in self.tasks.items():
            if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                continue
            if task.collection != collection:
                continue
            ttype, _ = self._task_args.get(task_id, ("unknown", {}))
            if ttype == task_type:
                return True
        return False


# 全局任务管理器实例
task_manager = TaskManager()
