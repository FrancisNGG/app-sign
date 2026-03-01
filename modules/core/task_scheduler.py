"""
task_scheduler.py

任务调度器 - 负责生成每日签到任务和保活任务，管理任务队列和重试。
"""

import uuid
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import random

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型"""
    SIGN = "sign"
    KEEPALIVE = "keepalive"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """任务对象"""
    task_id: str
    site_name: str
    task_type: TaskType
    scheduled_time: datetime
    
    # 执行状态
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_retries: int = 3
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 结果信息
    error_message: Optional[str] = None
    result_message: Optional[str] = None
    
    def is_overdue(self, now: datetime) -> bool:
        """检查任务是否过期（距离计划时间超过1小时）"""
        return (now - self.scheduled_time).total_seconds() > 3600
    
    def should_retry(self) -> bool:
        """检查是否应该重试"""
        return self.status == TaskStatus.FAILED and self.attempts < self.max_retries


class TaskScheduler:
    """
    任务调度器
    
    职责：
    - 生成每日任务队列
    - 管理待执行、执行中、已完成任务
    - 处理任务重试
    - 清理过期任务
    """
    
    def __init__(self):
        self.pending_tasks: List[Task] = []  # 待执行队列
        self.running_tasks: Dict[str, Task] = {}  # 运行中任务
        self.completed_tasks: List[Task] = []  # 已完成任务列表（最近100条）
        self.retry_queue: List[Task] = []  # 重试队列
        
    def generate_daily_tasks(self, sites_config: Dict) -> List[Task]:
        """
        生成每日任务
        
        Args:
            sites_config: 网站配置字典
            
        Returns:
            生成的Tasks列表
        """
        tasks = []
        now = datetime.now()
        
        for site_name, site_config in sites_config.items():
            if not site_config.get('enabled', True):
                logger.debug(f"跳过已禁用网站: {site_name}")
                continue
            
            # 生成签到任务
            sign_task = self._create_sign_task(site_name, site_config, now)
            tasks.append(sign_task)
            
            # 生成保活任务（如果启用）
            if site_config.get('keepalive', {}).get('enabled', True):
                keepalive_task = self._create_keepalive_task(site_name, site_config, now)
                tasks.append(keepalive_task)
        
        # 按计划时间排序
        tasks.sort(key=lambda t: t.scheduled_time)
        
        logger.info(f"生成了 {len(tasks)} 个每日任务")
        return tasks
    
    def _create_sign_task(
        self,
        site_name: str,
        site_config: Dict,
        now: datetime
    ) -> Task:
        """创建签到任务"""
        
        # 解析计划时间
        run_time_str = site_config.get('run_time', '09:00:00')
        try:
            run_time = datetime.strptime(run_time_str, '%H:%M:%S').time()
        except ValueError:
            logger.warning(f"无效的run_time格式: {run_time_str}，使用默认09:00:00")
            run_time = time(9, 0, 0)
        
        # 计算计划执行时间（今天）
        scheduled = datetime.combine(now.date(), run_time)
        
        # 如果时间已过，延迟到明天
        if scheduled <= now:
            scheduled = datetime.combine(now.date() + timedelta(days=1), run_time)
        
        # 添加随机延迟
        random_range = site_config.get('random_range', 0)
        if random_range > 0:
            random_minutes = random.randint(0, random_range)
            scheduled += timedelta(minutes=random_minutes)
        
        task = Task(
            task_id=f"sign_{uuid.uuid4().hex[:8]}",
            site_name=site_name,
            task_type=TaskType.SIGN,
            scheduled_time=scheduled
        )
        
        logger.debug(f"创建签到任务: {site_name} @ {scheduled}")
        return task
    
    def _create_keepalive_task(
        self,
        site_name: str,
        site_config: Dict,
        now: datetime
    ) -> Task:
        """创建保活任务"""
        
        keepalive_config = site_config.get('keepalive', {})
        
        # 获取上次保活时间（字段名与 config.yaml 保持一致）
        last_refresh = keepalive_config.get('last_keepalive_time')
        
        # 计算刷新间隔：config 中存储的是分钟数，转换为小时
        interval_minutes = keepalive_config.get('interval_minutes', 1440)
        check_interval_hours = interval_minutes / 60.0
        
        if last_refresh:
            try:
                last_time = datetime.fromisoformat(last_refresh)
                scheduled = last_time + timedelta(hours=check_interval_hours)
            except (ValueError, TypeError):
                scheduled = now + timedelta(hours=1)
        else:
            # 首次保活：今天凌晨2点
            scheduled = datetime.combine(now.date(), time(2, 0, 0))
            if scheduled <= now:
                scheduled = datetime.combine(
                    now.date() + timedelta(days=1),
                    time(2, 0, 0)
                )
        
        task = Task(
            task_id=f"ka_{uuid.uuid4().hex[:8]}",
            site_name=site_name,
            task_type=TaskType.KEEPALIVE,
            scheduled_time=scheduled,
            max_retries=1  # 保活用1次重试足够
        )
        
        logger.debug(f"创建保活任务: {site_name} @ {scheduled}")
        return task
    
    def add_pending_tasks(self, tasks: List[Task]):
        """添加任务到待执行队列"""
        self.pending_tasks.extend(tasks)
        self.pending_tasks.sort(key=lambda t: t.scheduled_time)
        logger.info(f"添加 {len(tasks)} 个任务到队列，当前队列大小: {len(self.pending_tasks)}")
    
    def get_executable_tasks(self, now: datetime) -> List[Task]:
        """
        获取可执行的任务（时间已到）
        
        Args:
            now: 当前时间
            
        Returns:
            可执行的任务列表
        """
        executable = []
        remaining = []
        
        for task in self.pending_tasks:
            if task.scheduled_time <= now:
                executable.append(task)
            else:
                remaining.append(task)
        
        self.pending_tasks = remaining
        
        if executable:
            logger.info(f"发现 {len(executable)} 个可执行的任务")
        
        return executable
    
    def get_executable_retry_tasks(self, now: datetime) -> List[Task]:
        """获取需要重试的任务"""
        executable = []
        remaining = []
        
        for task in self.retry_queue:
            if task.scheduled_time <= now:
                executable.append(task)
            else:
                remaining.append(task)
        
        self.retry_queue = remaining
        return executable
    
    def start_task(self, task: Task) -> bool:
        """标记任务为运行中"""
        task.status = TaskStatus.RUNNING
        task.executed_at = datetime.now()
        task.attempts += 1
        self.running_tasks[task.task_id] = task
        logger.info(f"启动任务: {task.task_id} ({task.site_name}) [尝试 {task.attempts}/{task.max_retries + 1}]")
        return True
    
    def complete_task(
        self,
        task: Task,
        success: bool = True,
        message: str = None
    ):
        """标记任务完成"""
        task.completed_at = datetime.now()
        task.result_message = message or ("成功" if success else "失败")
        
        if success:
            task.status = TaskStatus.SUCCESS
            logger.info(f"任务完成: {task.task_id} ({task.site_name}) - 成功")
        else:
            task.status = TaskStatus.FAILED
            task.error_message = message or "未知错误"
            logger.warning(f"任务失败: {task.task_id} ({task.site_name}) - {message}")
            
            # 检查是否需要重试
            if task.should_retry():
                self._schedule_retry(task)
        
        # 从运行队列移出
        self.running_tasks.pop(task.task_id, None)
        
        # 保存到已完成列表（保留最近100条）
        self.completed_tasks.append(task)
        if len(self.completed_tasks) > 100:
            self.completed_tasks.pop(0)
    
    def _schedule_retry(self, task: Task):
        """安排任务重试"""
        # 延迟5分钟重试
        task.scheduled_time = datetime.now() + timedelta(minutes=5)
        self.retry_queue.append(task)
        logger.info(f"任务已加入重试队列: {task.task_id} ({task.site_name})")
    
    def get_task_statistics(self) -> Dict:
        """获取任务统计信息"""
        today = datetime.now().date()
        return {
            "pending": len(self.pending_tasks),
            "running": len(self.running_tasks),
            "running_site_names": [
                t.site_name for t in self.running_tasks.values()
                if t.task_type.value == 'sign'
            ],
            "retry_queue": len(self.retry_queue),
            "completed_today": len([
                t for t in self.completed_tasks
                if t.completed_at and t.completed_at.date() == today
            ]),
            "success_today": len([
                t for t in self.completed_tasks
                if t.completed_at and t.completed_at.date() == today
                and t.status == TaskStatus.SUCCESS
            ]),
            "failed_today": len([
                t for t in self.completed_tasks
                if t.completed_at and t.completed_at.date() == today
                and t.status == TaskStatus.FAILED
            ]),
        }
    
    def cleanup_overdue_tasks(self, now: datetime):
        """清理超期未执行的任务（超过1小时）"""
        overdue = [t for t in self.pending_tasks if t.is_overdue(now)]
        
        for task in overdue:
            task.status = TaskStatus.SKIPPED
            task.error_message = "任务超期被跳过"
            self.pending_tasks.remove(task)
            self.completed_tasks.append(task)
        
        if overdue:
            logger.warning(f"清理了 {len(overdue)} 个超期任务")
