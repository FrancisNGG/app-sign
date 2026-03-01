"""
sign_executor.py

签到执行器 - 负责执行签到任务，调用各网站的签到模块。
"""

import importlib
import logging
from typing import Dict, Optional
from datetime import datetime

from .task_scheduler import Task, TaskStatus

# 通知推送
try:
    from modules.utils.notify import push_notification
except ImportError:
    push_notification = None

logger = logging.getLogger(__name__)


class SignExecutionError(Exception):
    """签到执行异常"""
    pass


class SignModuleNotFoundError(SignExecutionError):
    """模块未找到异常（不遮蔽 Python 内建同名异常）"""
    pass

# 向后兼容别名
ModuleNotFoundError = SignModuleNotFoundError


class SignExecutor:
    """
    签到执行器
    
    职责：
    - 加载网站对应的签到模块
    - 执行签到任务
    - 处理执行异常
    - 发送通知
    """
    
    def __init__(self, notify_manager=None, result_recorder=None):
        """
        初始化签到执行器
        
        Args:
            notify_manager: 保留参数（已废弃，通知直接从配置文件读取）
            result_recorder: 结果记录回调函数 (site_name, success, message, error_type)
        """
        self.notify_manager = notify_manager
        self.result_recorder = result_recorder
        self.module_cache = {}  # 模块缓存
    
    async def execute_sign(
        self,
        task: Task,
        site_config: Dict,
        cookies: Optional[str] = None
    ) -> str:
        """
        执行签到任务
        
        Args:
            task: 任务对象
            site_config: 网站配置
            cookies: Cookie字符串
            
        Returns:
            str: 签到结果消息
            
        Raises:
            SignExecutionError: 签到失败
        """
        try:
            module_name = site_config.get('module')
            if not module_name:
                raise SignModuleNotFoundError(f"网站 {task.site_name} 未配置module")
            
            # 加载模块
            sign_module = self._get_module(module_name)
            
            # 获取签到函数
            sign_func = None
            if hasattr(sign_module, 'sign_in'):
                sign_func = getattr(sign_module, 'sign_in')
            else:
                raise SignModuleNotFoundError(
                    f"模块 {module_name} 未实现 sign_in() 函数"
                )
            
            # 检查函数是否可调用
            if not callable(sign_func):
                raise SignModuleNotFoundError(
                    f"模块 {module_name} 中的函数不可调用"
                )
            
            # 加载全局配置
            from modules.utils.cookie_sync import load_config
            global_config, _ = load_config()
            
            # 创建通知函数，捕获详细消息
            captured_messages = []
            def notify_func(config, site_name, message):
                """通知函数 - 捕获签到详情"""
                logger.info(f"[NOTIFY] [{site_name}] {message}")
                captured_messages.append(message)
            
            # 执行签到 - sign_in()是同步函数，不需要await
            logger.info(f"执行签到: {task.site_name}")
            result = sign_func(
                site=site_config,
                config=global_config,
                notify_func=notify_func
            )
            
            # 处理返回值 - sign_in() 返回布尔值
            # 如果有捕获的消息，使用详细消息，否则使用通用消息
            is_success = bool(result)
            
            if captured_messages:
                message = captured_messages[-1]  # 使用最后一条消息
            else:
                message = "签到成功" if is_success else "签到失败"
            
            if is_success:
                logger.info(f"签到成功: {task.site_name} - {message}")
                try:
                    await self._send_notification(
                        site_name=task.site_name,
                        status="success",
                        message=message
                    )
                except Exception as notif_err:
                    logger.warning(f"发送通知失败: {notif_err}")
                
                # 记录签到结果
                if self.result_recorder:
                    try:
                        self.result_recorder(task.site_name, True, message, None)
                    except Exception as rec_err:
                        logger.warning(f"记录结果失败: {rec_err}")
                
                return message
            else:
                raise SignExecutionError(message or "签到失败")
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"签到执行异常: {task.site_name} - {error_msg}", exc_info=True)
            
            try:
                await self._send_notification(
                    site_name=task.site_name,
                    status="failed",
                    message=error_msg
                )
            except Exception as notif_err:
                logger.warning(f"发送异常通知失败: {notif_err}")
            
            # 分析错误类型并记录
            error_type = 'unknown'
            if 'cookie' in error_msg.lower() or '403' in error_msg:
                error_type = 'cookie_expired'
            elif 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                error_type = 'network_error'
            elif 'login' in error_msg.lower() or '401' in error_msg:
                error_type = 'login_failed'
            
            # 记录失败结果
            if self.result_recorder:
                try:
                    self.result_recorder(task.site_name, False, error_msg, error_type)
                except Exception as rec_err:
                    logger.warning(f"记录错误结果失败: {rec_err}")
            
            raise SignExecutionError(error_msg)
    
    def _get_module(self, module_name: str):
        """
        获取签到模块
        
        Args:
            module_name: 模块名称（如 'right', 'bilibili'）
            
        Returns:
            模块对象
            
        Raises:
            ModuleNotFoundError: 模块不存在
        """
        if module_name in self.module_cache:
            return self.module_cache[module_name]
        
        try:
            # 动态加载站点脚本（从modules.sites中）
            module = importlib.import_module(f'modules.sites.{module_name}')
            self.module_cache[module_name] = module
            logger.debug(f"加载模块: {module_name}")
            return module
        except ImportError as e:
            raise SignModuleNotFoundError(f"模块 {module_name} 不存在: {str(e)}")
    
    async def _send_notification(
        self,
        site_name: str,
        status: str,
        message: str
    ):
        """发送通知"""
        if not push_notification:
            return
        try:
            from modules.utils.cookie_sync import load_config
            config, _ = load_config('config/config.yaml')
            icon = '✓' if status == 'success' else '✗'
            result_msg = f"{icon} {message}"
            push_notification(config, site_name, result_msg)
        except Exception as e:
            logger.warning(f"发送通知失败: {str(e)}")
    
    async def handle_execution_error(
        self,
        task: Task,
        error: Exception,
        site_config: Dict
    ):
        """
        处理执行错误
        
        Args:
            task: 任务对象
            error: 异常对象
            site_config: 网站配置
        """
        error_msg = str(error)
        logger.error(f"错误处理: {task.site_name} - {error_msg}")
        
        # 分析错误类型
        if isinstance(error, SignModuleNotFoundError):
            await self._send_notification(
                site_name=task.site_name,
                status="error",
                message=f"模块未找到: {error_msg}"
            )
        elif "Cookie" in error_msg or "cookie" in error_msg:
            await self._send_notification(
                site_name=task.site_name,
                status="error",
                message="Cookie已失效，请重新登录"
            )
        else:
            await self._send_notification(
                site_name=task.site_name,
                status="error",
                message=f"签到异常: {error_msg}"
            )


class AsyncSignExecutor:
    """
    异步批量签到执行器
    
    支持并发执行多个签到任务
    """
    
    def __init__(self, sign_executor: SignExecutor, max_concurrent: int = 3):
        """
        初始化
        
        Args:
            sign_executor: SignExecutor实例
            max_concurrent: 最大并发数
        """
        self.sign_executor = sign_executor
        self.max_concurrent = max_concurrent
    
    async def execute_batch(
        self,
        tasks: list,
        sites_config: Dict
    ) -> Dict[str, bool]:
        """
        批量执行签到任务
        
        Args:
            tasks: Task对象列表
            sites_config: 所有网站配置
            
        Returns:
            {task_id: 是否成功} 的字典
        """
        import asyncio
        
        results = {}
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def sign_with_semaphore(task: Task):
            async with semaphore:
                try:
                    site_config = sites_config.get(task.site_name, {})
                    cookies = site_config.get('cookie')
                    
                    await self.sign_executor.execute_sign(
                        task=task,
                        site_config=site_config,
                        cookies=cookies
                    )
                    
                    results[task.task_id] = True
                    return True
                except Exception as e:
                    logger.error(f"批量签到失败: {task.site_name} - {str(e)}")
                    results[task.task_id] = False
                    return False
        
        # 并发执行
        await asyncio.gather(*[sign_with_semaphore(t) for t in tasks])
        
        return results
