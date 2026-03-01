# -*- coding: utf-8 -*-
"""
Web服务器 v2.0 - Flask应用，集成新的登录、任务调度、签到执行功能

新增特性：
- 账号密码登录（支持验证码）
- Cookie自动保活
- 任务队列管理
- 实时签到状态

路由：
- 认证: /api/auth-*, /auth, /
- 网站/登录: /api/sites/*, /api/login/*, /api/sign/*
- 前端: /dashboard, /add-site, 等
"""

import os
import sys
import asyncio
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict
from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, abort, session
from flask_cors import CORS
import bcrypt
import logging
from logging.handlers import TimedRotatingFileHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)

# 若根 logger 尚无文件处理器（单独运行此模块时），自动补充
def _ensure_file_logging():
    root = logging.getLogger()
    if any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers):
        return
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app_sign_logs.log')
    fh = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        backupCount=30,
        encoding='utf-8'
    )
    fh.suffix = '%Y%m%d'
    def _namer(name):
        base, date_part = name.rsplit('.', 1)
        return os.path.join(os.path.dirname(base), f'app_sign_logs_{date_part}.log')
    fh.namer = _namer
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
    ))
    root.addHandler(fh)

logger = logging.getLogger(__name__)

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

_ensure_file_logging()

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(WEB_DIR, 'frontend')
STATIC_DIR = os.path.join(WEB_DIR, 'static')

# 导入新模块
from modules import (
    CredentialManager, LoginState, LoginSession,
    TaskScheduler, TaskType, TaskStatus,
    SignExecutor,
    load_config, save_config, safe_print
)

# ==================== 配置文件初始化 ====================
def initialize_config():
    """初始化配置文件，如果不存在则创建默认配置"""
    config_dir = os.path.join(project_root, 'config')
    config_path = os.path.join(config_dir, 'config.yaml')
    
    # 确保config目录存在
    os.makedirs(config_dir, exist_ok=True)
    
    # 如果config.yaml不存在，创建默认配置
    if not os.path.exists(config_path):
        try:
            from config_template import DEFAULT_CONFIG
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_CONFIG)
            
            logger.info(f"✓ 已创建默认配置文件: {config_path}")
            
        except Exception as e:
            logger.error(f"创建配置文件失败: {str(e)}")
            # 创建最小化的配置
            try:
                minimal_config = """# 应用签到配置文件
sites: []
auth:
  username: admin
  password: admin
global:
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
"""
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(minimal_config)
                logger.info(f"✓ 已创建最小配置文件: {config_path}")
            except Exception as e2:
                logger.error(f"创建最小配置文件失败: {str(e2)}")
    else:
        logger.info(f"✓ 配置文件已存在: {config_path}")


# ==================== Flask应用初始化 ====================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'app-sign-v2-secret-key')
# Session 安全配置
app.config['SESSION_COOKIE_HTTPONLY'] = True      # 禁止 JS 读取 cookie，防止 XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'    # 限制跨站请求携带 cookie，缓解 CSRF
# SESSION_COOKIE_SECURE 设为 True 时仅 HTTPS 可用；生产环境建议启用
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SECURE_COOKIE', '').lower() in ('1', 'true', 'yes')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)  # session 12 小时后自动过期
CORS(app)

# 截图流浏览器会话管理器（延迟导入，避免 Playwright 启动过早）
_fetch_cookie_manager = None

def get_fetch_cookie_manager():
    global _fetch_cookie_manager
    if _fetch_cookie_manager is None:
        from web.captcha_browser import FetchCookieManager
        _fetch_cookie_manager = FetchCookieManager()
    return _fetch_cookie_manager

# 初始化配置文件
initialize_config()

# ==================== 辅助函数 ====================
from modules import safe_print

# ... 其他导入 ...

def record_sign_result(site_name: str, success: bool, message: str, error_type: str = None):
    """记录签到任务结果，便于前端查询（已弃用，保留为兼容）"""
    # 现在直接通过ctx._record_sign_result进行记录
    ctx._record_sign_result(site_name, success, message, error_type)

# ==================== 全局管理器 ====================
class AppContext:
    """应用上下文 - 管理所有全局对象"""
    
    def __init__(self):
        self.credential_manager: Optional[CredentialManager] = None
        self.task_scheduler: TaskScheduler = TaskScheduler()
        
        # 日志和锁
        self.log_messages: list = []
        self.log_lock = threading.Lock()
        self.config_cache = None
        self.config_cache_time = None
        
        # 签到任务结果存储 {site_name: {status, message, timestamp, error_type}}
        self.sign_results: Dict = {}
        self.sign_results_lock = threading.Lock()
        
        # 创建SignExecutor，传递record_sign_result回调
        # 这样sign_executor可以直接记录结果，避免线程延迟问题
        self.sign_executor: SignExecutor = SignExecutor(
            result_recorder=self._record_sign_result
        )
        self.browser_manager = None
        
        # 异步事件循环
        self.async_loop: Optional[asyncio.AbstractEventLoop] = None
        self.async_thread: Optional[threading.Thread] = None
        self.async_loop_lock = threading.Lock()

        # 保活并发保护：记录当前正在执行保活的站点名，防止同站点并发
        self._running_keepalives: set = set()
        self._running_keepalives_lock = threading.Lock()

        # 签到调度跟踪：记录上次生成任务的日期，用于跨天自动续签
        self._last_task_generation_date = None
    
    def _record_sign_result(self, site_name: str, success: bool, message: str, error_type: str = None):
        """SignExecutor的结果回调 - 直接记录签到结果"""
        safe_print(f"[_record_sign_result] site={site_name}, message={repr(message)}")
        with self.sign_results_lock:
            self.sign_results[site_name] = {
                'status': 'success' if success else 'failed',
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'error_type': error_type
            }
            safe_print(f"[_record_sign_result] 已保存: {self.sign_results[site_name]}")
        
        # 无论成功失败，都将签到结果写回 config 对应站点
        try:
            from modules.utils.cookie_sync import load_config, save_config
            full_config, encoding = load_config('config/config.yaml')
            config_path = 'config/config.yaml'

            if full_config and 'sites' in full_config:
                sites = full_config['sites']
                if isinstance(sites, dict) and site_name in sites:
                    if success:
                        sites[site_name]['last_sign_time'] = datetime.now().isoformat()
                        sites[site_name]['last_sign_status'] = 'success'
                    sites[site_name]['last_sign_message'] = message
                    save_config(full_config, config_path, encoding)
                    safe_print(f"[_record_sign_result] 已更新 {site_name} 的签到结果")
                elif isinstance(sites, list):
                    for site in sites:
                        if isinstance(site, dict) and (
                            site.get('aliases') == site_name or
                            site.get('name') == site_name
                        ):
                            if success:
                                site['last_sign_time'] = datetime.now().isoformat()
                                site['last_sign_status'] = 'success'
                            site['last_sign_message'] = message
                            save_config(full_config, config_path, encoding)
                            safe_print(f"[_record_sign_result] 已更新 {site_name} 的签到结果")
                            break
        except Exception as e:
            safe_print(f"[_record_sign_result] 更新config失败: {str(e)}")
    
    async def initialize_async(self):
        """异步初始化（在后台线程中运行，不阻塞）"""
        try:
            logger.info("✓ 异步初始化完成（浏览器将在需要时启动）")
        except Exception as e:
            logger.error(f"异步初始化失败: {str(e)}")

    # ==================== 保活后台调度线程 ====================
    def start_keepalive_scheduler(self):
        """启动保活后台调度线程（每60秒检查一次）"""
        def _loop():
            logger.info("[KeepAlive] 保活调度线程已启动")
            while True:
                try:
                    self._run_due_keepalives()
                except Exception as e:
                    logger.error(f"[KeepAlive] 调度异常: {e}")
                # 每60秒检查一次
                import time as _time
                _time.sleep(60)

        t = threading.Thread(target=_loop, daemon=True, name="KeepAliveScheduler")
        t.start()
        logger.info("[KeepAlive] 保活调度线程已注册")

    def _run_due_keepalives(self):
        """检查所有站点，对到期的站点执行保活"""
        from modules.utils.cookie_sync import load_config, save_config
        from modules.utils.cookie_keepalive import refresh_cookie_with_playwright

        try:
            full_config, encoding = load_config('config/config.yaml')
        except Exception as e:
            logger.warning(f"[KeepAlive] 读取配置失败: {e}")
            return

        sites = full_config.get('sites', [])
        if not isinstance(sites, list):
            return

        now = datetime.now()
        for site in sites:
            if not isinstance(site, dict):
                continue
            ka = site.get('keepalive', {})
            if not ka.get('enabled', False):
                continue

            interval_min = int(ka.get('interval_minutes', 1440))
            last_str = ka.get('last_keepalive_time')
            site_name = site.get('aliases') or site.get('name', '?')

            # ---- 判断是否到期：统一用 last_keepalive_time + interval_minutes ----
            run_reason = None
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str)
                    due_dt = last_dt + timedelta(minutes=interval_min)
                    if now < due_dt:
                        continue  # 未到执行时间
                    overdue_sec = int((now - due_dt).total_seconds())
                    if overdue_sec > 60:
                        run_reason = f'补跑（应于 {due_dt.strftime("%H:%M:%S")} 执行，已超期 {overdue_sec//60} 分 {overdue_sec%60} 秒）'
                    else:
                        run_reason = f'正常到期（间隔 {interval_min} 分钟）'
                except Exception:
                    run_reason = 'last_keepalive_time 解析失败，立即执行'
            else:
                run_reason = '首次执行'

            # ---- 防并发：跳过正在运行的站点 ----
            with self._running_keepalives_lock:
                if site_name in self._running_keepalives:
                    logger.debug(f"[KeepAlive] {site_name} 保活仍在进行中，跳过本轮")
                    continue
                self._running_keepalives.add(site_name)

            logger.info(f"[KeepAlive] {site_name} 开始保活 — {run_reason}")

            # 在独立线程中执行，避免阻塞检查循环
            def _do_keepalive(site_cfg=site, s_name=site_name, enc=encoding,
                             ka_interval=interval_min, _ctx=self):
                try:
                    result = refresh_cookie_with_playwright(site_cfg, full_config)
                    if result.get('success'):
                        new_cookie = result['cookie_raw']
                        logger.info(f"[KeepAlive] {s_name} 保活成功，更新 Cookie")
                        try:
                            from modules.utils.cookie_metadata import CookieMetadata
                            import datetime as _dt
                            now_utc = _dt.datetime.now(_dt.timezone.utc)
                            metadata = CookieMetadata({
                                'last_updated': now_utc.isoformat(),
                                'source': 'playwright',
                                'refresh_attempts': 0
                            })
                            cfg2, enc2 = load_config('config/config.yaml')
                            for s in cfg2.get('sites', []):
                                if isinstance(s, dict) and (
                                    s.get('aliases') == s_name or s.get('name') == s_name
                                ):
                                    s['cookie'] = new_cookie
                                    s['cookie_metadata'] = metadata.to_dict()
                                    ka = s.setdefault('keepalive', {})
                                    ka['last_keepalive_time'] = datetime.now().isoformat()
                                    ka.pop('next_keepalive_time', None)  # 清理旧字段
                                    ka['last_keepalive_status'] = 'success'
                                    ka['last_keepalive_message'] = result.get('message', '保活成功')
                                    break
                            save_config(cfg2, 'config/config.yaml', enc2)
                            logger.info(f"[KeepAlive] {s_name} Cookie 已写回 config")
                        except Exception as e2:
                            logger.error(f"[KeepAlive] {s_name} 写回 config 失败: {e2}")
                    else:
                        msg = result.get('message', '保活失败')
                        logger.warning(f"[KeepAlive] {s_name} 保活失败: {msg}")
                        try:
                            cfg2, enc2 = load_config('config/config.yaml')
                            for s in cfg2.get('sites', []):
                                if isinstance(s, dict) and (
                                    s.get('aliases') == s_name or s.get('name') == s_name
                                ):
                                    ka = s.setdefault('keepalive', {})
                                    # 失败也更新 last_keepalive_time，确保下次按 interval 正常调度
                                    ka['last_keepalive_time'] = datetime.now().isoformat()
                                    ka.pop('next_keepalive_time', None)  # 清理旧字段
                                    ka['last_keepalive_status'] = 'failed'
                                    ka['last_keepalive_message'] = msg
                                    # 累加重试次数到 cookie_metadata
                                    meta_d = s.get('cookie_metadata') or {}
                                    meta_d['refresh_attempts'] = int(meta_d.get('refresh_attempts', 0)) + 1
                                    s['cookie_metadata'] = meta_d
                                    break
                            save_config(cfg2, 'config/config.yaml', enc2)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"[KeepAlive] {s_name} 执行异常: {e}")
                finally:
                    # 无论成功/失败/异常，解除"正在运行"标记
                    with _ctx._running_keepalives_lock:
                        _ctx._running_keepalives.discard(s_name)

            threading.Thread(target=_do_keepalive, daemon=True,
                             name=f"KA-{site_name}").start()

    # ==================== 签到后台调度线程 ====================
    def start_sign_scheduler(self):
        """启动签到后台调度线程（每30秒检查一次）"""
        def _loop():
            import time as _time
            # 启动时立即生成今日任务
            try:
                self._generate_todays_sign_tasks()
            except Exception as e:
                logger.error(f"[SignScheduler] 初始生成任务失败: {e}")
            logger.info("[SignScheduler] 签到调度线程已启动")
            while True:
                try:
                    self._run_due_sign_tasks()
                except Exception as e:
                    logger.error(f"[SignScheduler] 调度异常: {e}")
                _time.sleep(30)

        t = threading.Thread(target=_loop, daemon=True, name="SignScheduler")
        t.start()
        logger.info("[SignScheduler] 签到调度线程已注册")

    def _generate_todays_sign_tasks(self):
        """为今日所有启用站点生成签到任务（跳过今日已签到成功的站点）"""
        import random as _random
        from modules.utils.cookie_sync import load_config as _load_cfg
        from modules.core.task_scheduler import Task, TaskType
        import uuid

        try:
            full_config, _ = _load_cfg('config/config.yaml')
        except Exception as e:
            logger.warning(f"[SignScheduler] 读取配置失败: {e}")
            return

        sites = full_config.get('sites', []) if full_config else []
        if not isinstance(sites, list):
            return

        now = datetime.now()
        today = now.date()
        generated = 0

        for site in sites:
            if not isinstance(site, dict):
                continue
            if not site.get('enabled', True):
                continue

            site_name = site.get('aliases') or site.get('name', '?')

            # 今日已签到成功则跳过
            last_sign_str = site.get('last_sign_time')
            if last_sign_str:
                try:
                    last_sign = datetime.fromisoformat(last_sign_str)
                    if last_sign.date() == today and site.get('last_sign_status') == 'success':
                        logger.debug(f"[SignScheduler] {site_name} 今日已签到成功，跳过")
                        continue
                except Exception:
                    pass

            # 解析 run_time
            run_time_str = site.get('run_time', '09:00:00')
            try:
                run_time = datetime.strptime(run_time_str, '%H:%M:%S').time()
            except ValueError:
                run_time = datetime.strptime('09:00:00', '%H:%M:%S').time()

            # 计划时间 = 今天的 run_time + 随机延迟
            scheduled = datetime.combine(today, run_time)
            random_range = site.get('random_range', 0)
            if random_range > 0:
                scheduled += timedelta(minutes=_random.randint(0, random_range))

            # 如果计划时间已超过1小时，立即补签
            if scheduled < now - timedelta(hours=1):
                scheduled = now + timedelta(seconds=5)
                logger.info(f"[SignScheduler] {site_name} 签到时间已超期，安排立即补签")
            elif scheduled < now:
                # 1小时内的轻微超期，延迟2秒执行
                scheduled = now + timedelta(seconds=2)

            # 避免向 pending 队列重复添加同一站点的签到任务
            already_pending = any(
                t.site_name == site_name and t.task_type.value == 'sign'
                for t in self.task_scheduler.pending_tasks
            )
            if already_pending:
                logger.debug(f"[SignScheduler] {site_name} 已在待执行队列中，跳过")
                continue

            task = Task(
                task_id=f"sign_{uuid.uuid4().hex[:8]}",
                site_name=site_name,
                task_type=TaskType.SIGN,
                scheduled_time=scheduled,
                max_retries=int((site.get('retry') or {}).get('max_retries', 3))
            )
            self.task_scheduler.add_pending_tasks([task])
            generated += 1
            logger.info(f"[SignScheduler] {site_name} 签到任务已安排 @ {scheduled.strftime('%H:%M:%S')}")

        self._last_task_generation_date = today
        logger.info(f"[SignScheduler] 共生成 {generated} 个今日签到任务")

    def _run_due_sign_tasks(self):
        """检查并执行到期的签到任务"""
        now = datetime.now()
        today = now.date()

        # 日期变更时重新生成任务（跨天自动续签）
        if self._last_task_generation_date != today:
            logger.info("[SignScheduler] 日期已变更，重新生成今日签到任务...")
            self._generate_todays_sign_tasks()
            return

        # 获取到期的签到任务（含重试队列）
        due_tasks = self.task_scheduler.get_executable_tasks(now)
        retry_tasks = self.task_scheduler.get_executable_retry_tasks(now)
        all_due = [t for t in (due_tasks + retry_tasks) if t.task_type.value == 'sign']

        for task in all_due:
            self.task_scheduler.start_task(task)

            def _do_sign(t=task):
                _sites_cfg = load_sites_config()
                site_config = _sites_cfg.get(t.site_name)
                if not site_config:
                    logger.warning(f"[SignScheduler] {t.site_name} 配置不存在，跳过")
                    self.task_scheduler.complete_task(t, success=False, message="配置不存在")
                    return

                retry_cfg = site_config.get('retry', {})
                retry_enabled = retry_cfg.get('enabled', True)
                max_attempts = (int(retry_cfg.get('max_retries', 3)) + 1) if retry_enabled else 1
                retry_delay_min = float(retry_cfg.get('retry_delay_minutes', 1))

                import asyncio as _aio
                import time as _time
                last_err = None
                for attempt in range(1, max_attempts + 1):
                    if attempt > 1:
                        logger.info(f"[SignScheduler] {t.site_name} 第{attempt}次重试，等待 {retry_delay_min} 分钟...")
                        _time.sleep(retry_delay_min * 60)
                        _fresh = load_sites_config()
                        site_config = _fresh.get(t.site_name) or site_config

                    new_loop = _aio.new_event_loop()
                    _aio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(
                            self.sign_executor.execute_sign(t, site_config)
                        )
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"[SignScheduler] {t.site_name} 第{attempt}/{max_attempts}次失败: {e}")
                    finally:
                        new_loop.close()

                if last_err is None:
                    self.task_scheduler.complete_task(t, success=True, message="签到成功")
                else:
                    self.task_scheduler.complete_task(t, success=False, message=str(last_err))

            thread = threading.Thread(target=_do_sign, daemon=True,
                                      name=f"Sign-{task.site_name}")
            thread.start()

        # 清理超期未执行的任务
        self.task_scheduler.cleanup_overdue_tasks(now)


ctx = AppContext()


def get_async_loop():
    """获取或启动异步事件循环"""
    with ctx.async_loop_lock:
        if ctx.async_loop and ctx.async_loop.is_running():
            return ctx.async_loop
        
        loop_ready = threading.Event()
        ctx.async_loop = asyncio.new_event_loop()
        
        def run_loop():
            asyncio.set_event_loop(ctx.async_loop)
            loop_ready.set()
            ctx.async_loop.run_forever()
        
        ctx.async_thread = threading.Thread(target=run_loop, daemon=True)
        ctx.async_thread.start()
        loop_ready.wait()
        
        # 异步初始化（非阻塞）
        asyncio.run_coroutine_threadsafe(ctx.initialize_async(), ctx.async_loop)
        
        return ctx.async_loop


def run_async(coro, timeout=30):
    """在后台事件循环中执行协程
    
    Args:
        coro: 协程对象
        timeout: 超时秒数，默认30秒；浏览器相关操作可传入更大值
    """
    loop = get_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def add_log(message: str):
    """添加日志消息"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    
    with ctx.log_lock:
        ctx.log_messages.append(log_entry)
        if len(ctx.log_messages) > 1000:
            ctx.log_messages.pop(0)


# ==================== 认证相关 ====================
def load_auth_config() -> dict:
    """加载Web认证配置"""
    try:
        config, _ = load_config('config/config.yaml')
        if config and 'auth' in config:
            return config['auth']
    except Exception as e:
        logger.warning(f"加载认证配置失败: {str(e)}")
    
    return {'username': 'admin', 'password': 'admin'}


def save_auth_config(username: str, password: str) -> bool:
    """保存Web认证配置（password 应已经过 hash_password 处理）"""
    try:
        config, encoding = load_config('config/config.yaml')
        if config is None:
            return False
        
        config['auth'] = {'username': username, 'password': password}
        save_config(config, 'config/config.yaml', encoding)
        return True
    except Exception as e:
        logger.error(f"保存认证配置失败: {str(e)}")
        return False


def hash_password(plain: str) -> str:
    """将明文密码哈希为 bcrypt 字符串（用于存入 config.yaml）"""
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain: str, stored: str) -> bool:
    """
    验证密码。
    - stored 是 bcrypt 格式（$2b$/$2a$ 开头）: 做哈希比对
    - stored 是明文（手动在 config.yaml 中重置）: 直接比对，
      并自动将明文升级为哈希写回 config，方便忘记密码后重置。
    """
    if stored.startswith(('$2b$', '$2a$', '$2y$')):
        try:
            return bcrypt.checkpw(plain.encode('utf-8'), stored.encode('utf-8'))
        except Exception:
            return False
    else:
        # 明文兜底：允许手动在 config.yaml 写明文实现密码重置
        if plain == stored:
            # 自动升级：将明文升级为哈希写回 config
            try:
                auth = load_auth_config()
                save_auth_config(auth.get('username', 'admin'), hash_password(plain))
                logger.info("检测到明文密码，已自动升级为 bcrypt 哈希")
            except Exception as e:
                logger.warning(f"密码自动升级失败（不影响登录）: {e}")
            return True
        return False


def is_authenticated() -> bool:
    """检查用户是否已认证"""
    return 'username' in session and session.get('username') is not None


def require_login(f):
    """API认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return jsonify({'status': 'error', 'message': '未授权，请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function


def redirect_if_not_login(f):
    """前端认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('auth_page'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== 前端路由 ====================
@app.route('/')
@redirect_if_not_login
def index():
    """主页 - 重定向到Dashboard"""
    return redirect(url_for('dashboard'))


@app.route('/auth')
def auth_page():
    """认证页"""
    return send_from_directory(FRONTEND_DIR, 'auth.html')


@app.route('/dashboard')
@redirect_if_not_login
def dashboard():
    """签到面板"""
    return send_from_directory(FRONTEND_DIR, 'dashboard.html')


@app.route('/add-site')
@redirect_if_not_login
def add_site():
    """添加网站页面"""
    return send_from_directory(FRONTEND_DIR, 'add-site.html')


@app.route('/settings')
@redirect_if_not_login
def settings_page():
    """系统设置页面"""
    return send_from_directory(FRONTEND_DIR, 'settings.html')


@app.route('/fetch-cookie')
@redirect_if_not_login
def fetch_cookie_page():
    """截图流浏览器登录页 —— 通过账号密码获取Cookie"""
    return send_from_directory(FRONTEND_DIR, 'fetch-cookie.html')


# 静态文件
@app.route('/static/<path:path>')
def static_files(path):
    """静态文件服务"""
    return send_from_directory(STATIC_DIR, path)


# ==================== 认证API ====================
@app.route('/api/auth-login', methods=['POST'])
def auth_login():
    """Web认证登入"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400
        
        auth = load_auth_config()
        if username == auth.get('username') and verify_password(password, auth.get('password', '')):
            session['username'] = username
            return jsonify({'status': 'success', 'message': '登录成功'})
        else:
            return jsonify({'status': 'error', 'message': '用户名或密码错误'}), 401
    
    except Exception as e:
        logger.error(f"认证登入异常: {str(e)}")
        return jsonify({'status': 'error', 'message': '服务器错误'}), 500


@app.route('/api/auth-logout', methods=['POST'])
def auth_logout():
    """Web认证登出"""
    try:
        session.clear()
        return jsonify({'status': 'success', 'message': '登出成功'})
    except Exception as e:
        logger.error(f"认证登出异常: {str(e)}")
        return jsonify({'status': 'error', 'message': '服务器错误'}), 500


@app.route('/api/auth-status', methods=['GET'])
def auth_status():
    """认证状态查询"""
    return jsonify({
        'status': 'success',
        'authenticated': is_authenticated(),
        'username': session.get('username') if is_authenticated() else None
    })


# ==================== 登录API (新增) ====================
@app.route('/api/login/start', methods=['POST'])
@require_login
def login_start():
    """
    开始登录流程
    
    请求: {
        "site": "恩山无线论坛",
        "username": "user@example.com",
        "password": "password",
        "site_config": { "base_url": "...", "module": "..." }
    }
    """
    try:
        # 按需初始化credential_manager
        if ctx.credential_manager is None:
            ctx.credential_manager = CredentialManager(ctx.browser_manager)
        
        data = request.get_json() or {}
        site_name = data.get('site', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        site_config = data.get('site_config', {})
        
        if not all([site_name, username, password, site_config]):
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 启动登录
        base_url = site_config.get('base_url', '')
        module_name = site_config.get('module', '')
        
        session_obj = run_async(ctx.credential_manager.start_login(
            site_name=site_name,
            base_url=base_url,
            username=username,
            password=password,
            module_name=module_name
        ))
        
        return jsonify({
            'status': 'success',
            'session_id': session_obj.session_id,
            'message': '登录流程已启动',
            'next_step': 'check_status'
        })
    
    except Exception as e:
        logger.error(f"登录启动异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'启动登录失败: {str(e)}'
        }), 500


@app.route('/api/login/status/<session_id>', methods=['GET'])
@require_login
def login_status(session_id: str):
    """获取登录进度和验证码信息"""
    try:
        status_dict = run_async(ctx.credential_manager.get_session_status(session_id))
        return jsonify(status_dict)
    
    except Exception as e:
        logger.error(f"查询登录状态异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '查询状态失败'
        }), 500


@app.route('/api/login/captcha/submit', methods=['POST'])
@require_login
def login_captcha_submit():
    """
    提交验证码
    
    请求: {
        "session_id": "sess_xxx",
        "captcha_text": "abcd1234"  // 文本
        // 或
        "captcha_position": [{"x": 100, "y": 200}, ...]  // 点击
        // 或
        "slider_distance": 150  // 滑块
    }
    """
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            return jsonify({'status': 'error', 'message': '缺少session_id'}), 400
        
        # 确定答案类型
        if 'captcha_text' in data:
            answer = data['captcha_text']
        elif 'captcha_position' in data:
            answer = [(p['x'], p['y']) for p in data['captcha_position']]
        elif 'slider_distance' in data:
            answer = data['slider_distance']
        else:
            return jsonify({'status': 'error', 'message': '缺少验证码答案'}), 400
        
        # 提交验证码
        success = run_async(ctx.credential_manager.submit_captcha(session_id, answer))
        
        if success:
            # 重新查询状态
            status_dict = run_async(ctx.credential_manager.get_session_status(session_id))
            status_dict['captcha_submitted'] = True
            return jsonify(status_dict)
        else:
            return jsonify({
                'status': 'error',
                'message': '验证码错误'
            }), 400
    
    except Exception as e:
        logger.error(f"提交验证码异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'提交验证码失败: {str(e)}'
        }), 500


@app.route('/api/login/cancel', methods=['POST'])
@require_login
def login_cancel():
    """取消登录流程"""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            return jsonify({'status': 'error', 'message': '缺少session_id'}), 400
        
        run_async(ctx.credential_manager.cleanup_session(session_id))
        
        return jsonify({
            'status': 'success',
            'message': '登录流程已取消'
        })
    
    except Exception as e:
        logger.error(f"取消登录异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'取消失败: {str(e)}'
        }), 500


# ==================== 截图流Cookie获取API ====================

@app.route('/api/fetch-cookie/start', methods=['POST'])
@require_login
def fetch_cookie_start():
    """启动远程浏览器会话，打开对应站点登录页。"""
    try:
        data = request.get_json() or {}
        module = (data.get('module') or '').strip()
        if not module:
            return jsonify({'status': 'error', 'message': '缺少 module 参数'}), 400

        from modules.sites import SITE_REGISTRY
        if module not in SITE_REGISTRY:
            return jsonify({'status': 'error', 'message': f'模块 {module} 不支持账号密码登录'}), 400

        manager = get_fetch_cookie_manager()
        session_id, sess = manager.create_session(module)

        # 异步初始化浏览器（在后台事件循环中）
        async def _init():
            try:
                await sess.initialize()
            except Exception as e:
                sess.status = 'error'
                sess.error_message = str(e)
                logger.error(f"会话初始化失败: {e}")

        loop = get_async_loop()
        asyncio.run_coroutine_threadsafe(_init(), loop)

        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'login_url': SITE_REGISTRY[module].get('login_url') or SITE_REGISTRY[module].get('base_url', ''),
            'viewport': {'width': 1280, 'height': 720}
        })
    except Exception as e:
        logger.error(f"fetch_cookie_start 异常: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fetch-cookie/<session_id>/screenshot')
@require_login
def fetch_cookie_screenshot(session_id):
    """返回当前浏览器截图 (JPEG 二进制)。"""
    from flask import Response
    manager = get_fetch_cookie_manager()
    sess = manager.get(session_id)
    if not sess:
        return jsonify({'status': 'error', 'message': '会话不存在或已过期'}), 404
    if sess.status == 'starting':
        # 还在启动中，返回透明1x1占位
        import base64
        placeholder = base64.b64decode(
            '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U'
            'HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN'
            'DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy'
            'MjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAA'
            'AAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAA'
            'AAAAP/aAAwDAQACEQMRAD8AJQAB/9k='
        )
        return Response(placeholder, mimetype='image/jpeg',
                        headers={'Cache-Control': 'no-store'})
    try:
        jpeg = run_async(sess.screenshot_jpeg(), timeout=60)
        if jpeg is None:
            abort(503)
        return Response(jpeg, mimetype='image/jpeg',
                        headers={'Cache-Control': 'no-store'})
    except Exception as e:
        logger.error(f"截图异常 [{session_id}]: {e}")
        abort(500)


@app.route('/api/fetch-cookie/<session_id>/action', methods=['POST'])
@require_login
def fetch_cookie_action(session_id):
    """转发鼠标/键盘事件到远程浏览器。"""
    manager = get_fetch_cookie_manager()
    sess = manager.get(session_id)
    if not sess or sess.status not in ('ready',):
        return jsonify({'status': 'error', 'message': '会话未就绪'}), 400
    try:
        data = request.get_json() or {}
        action_type = data.pop('type', '')
        ok = run_async(sess.do_action(action_type, **data), timeout=15)
        return jsonify({'status': 'success' if ok else 'error',
                        'current_url': sess.current_url})
    except Exception as e:
        logger.error(f"action 异常 [{session_id}]: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fetch-cookie/<session_id>/status')
@require_login
def fetch_cookie_status(session_id):
    """查询会话状态和当前 URL。"""
    manager = get_fetch_cookie_manager()
    sess = manager.get(session_id)
    if not sess:
        return jsonify({'status': 'error', 'message': '会话不存在'}), 404
    return jsonify({
        'status': 'success',
        'session_status': sess.status,
        'current_url': sess.current_url,
        'error_message': sess.error_message
    })


@app.route('/api/fetch-cookie/<session_id>/extract', methods=['POST'])
@require_login
def fetch_cookie_extract(session_id):
    """提取浏览器 Cookie 并关闭会话。"""
    manager = get_fetch_cookie_manager()
    sess = manager.get(session_id)
    if not sess:
        return jsonify({'status': 'error', 'message': '会话不存在'}), 404
    try:
        cookie_str = run_async(sess.extract_cookies(), timeout=60)
        run_async(sess.close(), timeout=10)
        manager.remove(session_id)
        if cookie_str:
            return jsonify({'status': 'success', 'cookie': cookie_str})
        else:
            return jsonify({'status': 'error', 'message': '未获取到Cookie，请确认已完成登录'}), 400
    except Exception as e:
        logger.error(f"extract 异常 [{session_id}]: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fetch-cookie/<session_id>/close', methods=['POST'])
@require_login
def fetch_cookie_close(session_id):
    """关闭并销毁会话。"""
    manager = get_fetch_cookie_manager()
    sess = manager.get(session_id)
    if sess:
        try:
            run_async(sess.close(), timeout=10)
        except Exception:
            pass
        manager.remove(session_id)
    return jsonify({'status': 'success'})


# ==================== 网站管理API ====================
def get_supported_sites() -> Dict[str, Dict]:
    """
    扫描 modules/sites/ 文件夹，与 SITE_REGISTRY 取交集后返回已实现的站点。
    站点元数据的唯一权威来源为 modules/sites/__init__.py 中的 SITE_REGISTRY。
    """
    import os
    from modules.sites import SITE_REGISTRY

    sites_dir = os.path.join(project_root, 'modules', 'sites')
    supported_sites = {}

    try:
        if os.path.exists(sites_dir):
            for filename in os.listdir(sites_dir):
                if filename.endswith('.py') and filename != '__init__.py':
                    module_name = filename[:-3]
                    if module_name in SITE_REGISTRY:
                        supported_sites[module_name] = SITE_REGISTRY[module_name]

        logger.debug(f"扫描到 {len(supported_sites)} 个支持的站点")
        return supported_sites

    except Exception as e:
        logger.error(f"扫描支持的站点失败: {str(e)}")
        from modules.sites import SITE_REGISTRY as _r
        return dict(_r)  # 降级：直接返回注册表全量


def load_sites_config() -> dict:
    """加载网站配置"""
    try:
        config, _ = load_config('config/config.yaml')
        if config and 'sites' in config:
            sites = config['sites']
            if isinstance(sites, dict):
                return sites
            elif isinstance(sites, list):
                # 列表格式转换为字典 (以 aliases 为 key，支持同一站点多个账号)
                sites_dict = {}
                for site in sites:
                    if isinstance(site, dict):
                        # aliases 是用户为每个账号起的唯一标签，优先用它做 key
                        site_key = site.get('aliases') or site.get('name')
                        if site_key:
                            sites_dict[site_key] = site
                return sites_dict
            elif sites is None:
                return {}
            else:
                return {}
    except Exception as e:
        logger.warning(f"加载网站配置失败: {str(e)}")
    
    return {}


@app.route('/api/sites/supported', methods=['GET'])
@require_login
def get_supported_sites_list():
    """获取所有支持的站点列表"""
    try:
        supported = get_supported_sites()
        return jsonify({
            'status': 'success',
            'sites': list(supported.values()),
            'total': len(supported)
        })
    except Exception as e:
        logger.error(f"获取支持的站点列表异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '获取站点列表失败'
        }), 500


@app.route('/api/sites', methods=['GET'])
@require_login
def get_sites():
    """获取所有网站的签到状态"""
    try:
        from datetime import datetime, time, timedelta
        
        sites_config = load_sites_config()
        
        sites_list = []
        for site_name, site_cfg in sites_config.items():
            # 计算认证类型
            has_cookie = bool(site_cfg.get('cookie'))
            has_credentials = bool(site_cfg.get('username'))
            if has_cookie:
                credential_type = 'cookie'
            elif has_credentials:
                credential_type = 'account'
            else:
                credential_type = 'none'
            
            # 计算下次签到时间
            run_time_str = site_cfg.get('run_time', '09:00:00')
            try:
                run_time = datetime.strptime(run_time_str, '%H:%M:%S').time()
                now = datetime.now()
                scheduled = datetime.combine(now.date(), run_time)
                if scheduled <= now:
                    scheduled = datetime.combine(now.date() + timedelta(days=1), run_time)
                next_sign_time = scheduled.isoformat()
            except:
                next_sign_time = None
            
            site_info = {
                'name': site_cfg.get('name', site_name),  # 站点类型名（如"什么值得买"）
                'aliases': site_name,  # 用户标签（dict key，每账号唯一）
                'enabled': site_cfg.get('enabled', True),
                'module': site_cfg.get('module'),
                'last_sign_time': site_cfg.get('last_sign_time'),
                'last_sign_status': site_cfg.get('last_sign_status'),
                'last_sign_message': site_cfg.get('last_sign_message'),
                'next_sign_time': next_sign_time,
                'run_time': site_cfg.get('run_time', '09:00:00'),
                'random_range': site_cfg.get('random_range', 0),
                'credential_type': credential_type,
                'cookie_status': {
                    'has_cookie': has_cookie,
                },
                'keepalive': site_cfg.get('keepalive', {}),
                'cookie_metadata': {
                    k: v for k, v in (site_cfg.get('cookie_metadata') or {}).items()
                    if k != 'valid_until'
                } or None,
            }
            sites_list.append(site_info)
        
        response = jsonify({
            'status': 'success',
            'sites': sites_list,
            'summary': {
                'total': len(sites_list),
                'enabled': len([s for s in sites_list if s['enabled']])
            }
        })
        # 禁用缓存，确保每次都获取最新数据
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        logger.error(f"获取网站列表异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '获取列表失败'
        }), 500


@app.route('/api/sites/<site_name>', methods=['GET'])
@require_login
def get_site(site_name: str):
    """获取网站详情"""
    try:
        sites_config = load_sites_config()
        
        if site_name not in sites_config:
            return jsonify({
                'status': 'error',
                'message': '网站不存在'
            }), 404
        
        site_cfg = sites_config[site_name]
        return jsonify({
            'status': 'success',
            'site': {
                'name': site_name,
                'enabled': site_cfg.get('enabled', True),
                'module': site_cfg.get('module'),
                'base_url': site_cfg.get('base_url'),
                'run_time': site_cfg.get('run_time'),
                'random_range': site_cfg.get('random_range'),
                'cookie': site_cfg.get('cookie', ''),
                'username': site_cfg.get('username', ''),
                'password': site_cfg.get('password', ''),
                'keepalive': site_cfg.get('keepalive', {}),
                'last_sign_time': site_cfg.get('last_sign_time'),
                'last_sign_status': site_cfg.get('last_sign_status')
            }
        })
    
    except Exception as e:
        logger.error(f"获取网站详情异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '获取详情失败'
        }), 500


@app.route('/api/sites/save-cookie', methods=['POST'])
@require_login
def save_cookie():
    """保存Cookie到配置 - 支持新建和更新"""
    try:
        data = request.get_json()
        module = data.get('module')
        aliases = data.get('aliases', '').strip()
        cookie = data.get('cookie', '').strip()
        run_time = data.get('run_time', '09:00:00')
        random_range = data.get('random_range', 0)
        enabled = data.get('enabled', True)
        auth_type = data.get('auth_type', 'cookie')  # 'cookie' 或 'account'
        username_val = data.get('username', '').strip()
        password_val = data.get('password', '').strip()

        # 新增参数
        retry_config = data.get('retry', {})
        keepalive_config = data.get('keepalive', {})

        if not module:
            return jsonify({
                'status': 'error',
                'message': '模块不能为空'
            }), 400

        if auth_type != 'account' and not cookie:
            return jsonify({
                'status': 'error',
                'message': 'Cookie不能为空'
            }), 400

        if auth_type == 'account' and (not username_val or not password_val):
            return jsonify({
                'status': 'error',
                'message': '账号和密码不能为空'
            }), 400
        
        if not aliases:
            return jsonify({
                'status': 'error',
                'message': '卡片标签名称不能为空'
            }), 400
        
        # 加载完整配置
        full_config, encoding = load_config('config/config.yaml')
        if not full_config:
            return jsonify({
                'status': 'error',
                'message': '无法加载配置文件'
            }), 500
        
        # 获取支持的站点信息
        supported_sites = get_supported_sites()
        if module not in supported_sites:
            return jsonify({
                'status': 'error',
                'message': f'不支持的模块: {module}'
            }), 400
        
        site_info = supported_sites[module]
        
        # 获取或初始化sites列表
        sites = full_config.get('sites', [])
        if not isinstance(sites, list):
            sites = []

        # 先查找是否已存在同 module+aliases 的站点（更新模式）
        site_index = None
        for idx, site in enumerate(sites):
            if site.get('module') == module and site.get('aliases') == aliases:
                site_index = idx
                break

        # 仅新建时才校验 aliases 全局唯一性（更新已有站点时跳过此检查）
        if site_index is None:
            for existing_site in sites:
                if (existing_site.get('aliases') or '').strip() == aliases:
                    return jsonify({
                        'status': 'error',
                        'message': f'标签名称 "{aliases}" 已存在，请修改为其他名称'
                    }), 400

        if site_index is not None:
            # 更新现有站点
            sites[site_index]['aliases'] = aliases
            if cookie:  # 账号密码模式下 cookie 为空，不覆盖已有 cookie
                sites[site_index]['cookie'] = cookie
            sites[site_index]['run_time'] = run_time
            sites[site_index]['random_range'] = random_range
            sites[site_index]['enabled'] = enabled
            sites[site_index]['retry'] = {
                'enabled': retry_config.get('enabled', True),
                'max_retries': retry_config.get('max_retries', 3),
                'retry_delay_minutes': retry_config.get('retry_delay_minutes', 1)
            }
            if auth_type == 'account':
                # 账号密码模式：保存凭据，移除 keepalive（不需要）
                if username_val:
                    sites[site_index]['username'] = username_val
                if password_val:
                    sites[site_index]['password'] = password_val
                sites[site_index].pop('keepalive', None)
            else:
                # Cookie 模式：更新 keepalive，清除可能残留的账号密码
                sites[site_index]['keepalive'] = {
                    'enabled': keepalive_config.get('enabled', True),
                    'last_keepalive_time': keepalive_config.get('last_keepalive_time'),
                    'method': keepalive_config.get('method', 'browser_refresh'),
                    'interval_minutes': keepalive_config.get('interval_minutes', 1440)
                }
                sites[site_index].pop('username', None)
                sites[site_index].pop('password', None)

            logger.info(f"✓ 已更新 {aliases} 的配置")
        else:
            # 创建新站点（字段顺序按照test-config.yaml的规范）
            new_site = {
                'name': site_info['name'],
                'aliases': aliases,
                'module': module,
                'enabled': enabled,
                'base_url': site_info.get('base_url', ''),
                'cookie': cookie,
                'run_time': run_time,
                'random_range': random_range,
                'last_sign_time': None,
                'last_sign_status': None,
                'last_sign_message': None,
                'retry': {
                    'enabled': retry_config.get('enabled', True),
                    'max_retries': retry_config.get('max_retries', 3),
                    'retry_delay_minutes': retry_config.get('retry_delay_minutes', 1)
                }
            }
            if auth_type == 'account':
                # 账号密码模式：保存凭据，每次签到直接登录，不需要 keepalive
                if username_val:
                    new_site['username'] = username_val
                if password_val:
                    new_site['password'] = password_val
            else:
                # Cookie 模式才需要保活配置
                new_site['keepalive'] = {
                    'enabled': keepalive_config.get('enabled', True),
                    'last_keepalive_time': keepalive_config.get('last_keepalive_time'),
                    'method': keepalive_config.get('method', 'browser_refresh'),
                    'interval_minutes': keepalive_config.get('interval_minutes', 1440)
                }
            sites.append(new_site)
            logger.info(f"✓ 已创建新站点: {aliases}")
        
        # 更新完整配置中的sites
        full_config['sites'] = sites
        
        # 保存配置文件
        try:
            save_config(full_config, 'config/config.yaml', encoding)
            logger.info(f"✓ 配置already保存: {aliases}")
        except Exception as save_error:
            logger.error(f"save_config异常: {save_error}")
            import traceback
            traceback.print_exc()
            raise
        
        return jsonify({
            'status': 'success',
            'message': f'已保存 {aliases} 的配置'
        })
    
    except Exception as e:
        logger.error(f"保存配置异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': '保存失败'
        }), 500


@app.route('/api/sites/update', methods=['POST'])
@require_login
def update_site():
    """更新网站配置"""
    try:
        data = request.get_json()
        site_name = data.get('name')
        
        if not site_name:
            return jsonify({
                'status': 'error',
                'message': '网站名称不能为空'
            }), 400
        
        # 加载完整的配置（保留 sites 列表格式）
        full_config, encoding = load_config('config/config.yaml')
        
        if not full_config or 'sites' not in full_config:
            return jsonify({
                'status': 'error',
                'message': '配置格式错误'
            }), 400
        
        sites = full_config['sites']
        config_path = 'config/config.yaml'

        # 如果要修改 aliases，先校验新名称不与其他账号冲突
        if 'aliases' in data and isinstance(sites, list):
            new_aliases = data.get('aliases', '').strip()
            if new_aliases and new_aliases != site_name:
                for s in sites:
                    if isinstance(s, dict) and (s.get('aliases') or s.get('name')) == new_aliases:
                        return jsonify({
                            'status': 'error',
                            'message': f'标签名称 "{new_aliases}" 已被其他账号使用，请修改为其他名称'
                        }), 400

        # 列表格式：按 aliases 查找对应的网站（aliases 是每账号唯一标签）
        if isinstance(sites, list):
            site_found = False
            for site in sites:
                if isinstance(site, dict) and (site.get('aliases') or site.get('name')) == site_name:
                    site_found = True
                    # 更新配置字段
                    if 'run_time' in data:
                        site['run_time'] = data['run_time']
                    
                    if 'random_range' in data:
                        site['random_range'] = data['random_range']
                    
                    if 'enabled' in data:
                        site['enabled'] = data['enabled']
                    
                    # 更新别名（作为字符串）
                    if 'aliases' in data:
                        site['aliases'] = data['aliases']
                    
                    # 更新认证信息
                    if 'cookie' in data and data['cookie']:
                        site['cookie'] = data['cookie'].strip()
                        # 清除账号密码
                        site.pop('username', None)
                        site.pop('password', None)
                    
                    if 'username' in data and data['username']:
                        site['username'] = data['username'].strip()
                        # 清除cookie
                        site.pop('cookie', None)
                    
                    if 'password' in data and data['password']:
                        site['password'] = data['password'].strip()
                    
                    # 更新重试配置
                    if 'retry' in data and isinstance(data['retry'], dict):
                        if 'retry' not in site:
                            site['retry'] = {
                                'enabled': True,
                                'max_retries': 3,
                                'retry_delay_minutes': 1
                            }
                        if 'enabled' in data['retry']:
                            site['retry']['enabled'] = data['retry']['enabled']
                        if 'max_retries' in data['retry']:
                            site['retry']['max_retries'] = data['retry']['max_retries']
                        if 'retry_delay_minutes' in data['retry']:
                            site['retry']['retry_delay_minutes'] = data['retry']['retry_delay_minutes']
                    
                    # 更新保活配置
                    if 'keepalive' in data and isinstance(data['keepalive'], dict):
                        if 'keepalive' not in site:
                            site['keepalive'] = {
                                'enabled': True,
                                'last_keepalive_time': None,
                                'method': 'browser_refresh',
                                'interval_minutes': 1440
                            }
                        if 'enabled' in data['keepalive']:
                            site['keepalive']['enabled'] = data['keepalive']['enabled']
                        if 'method' in data['keepalive']:
                            site['keepalive']['method'] = data['keepalive']['method']
                        if 'interval_minutes' in data['keepalive']:
                            site['keepalive']['interval_minutes'] = data['keepalive']['interval_minutes']
                    
                    break
            
            if not site_found:
                return jsonify({
                    'status': 'error',
                    'message': '网站不存在'
                }), 404
        
        else:
            # 字典格式（兼容旧配置）
            if site_name not in sites:
                return jsonify({
                    'status': 'error',
                    'message': '网站不存在'
                }), 404
            
            # 更新配置字段
            if 'run_time' in data:
                sites[site_name]['run_time'] = data['run_time']
            
            if 'random_range' in data:
                sites[site_name]['random_range'] = data['random_range']
            
            if 'enabled' in data:
                sites[site_name]['enabled'] = data['enabled']
            
            # 更新别名（作为字符串）
            if 'aliases' in data:
                sites[site_name]['aliases'] = data['aliases']
            
            # 更新认证信息
            if 'cookie' in data and data['cookie']:
                sites[site_name]['cookie'] = data['cookie'].strip()
                sites[site_name].pop('username', None)
                sites[site_name].pop('password', None)
            
            if 'username' in data and data['username']:
                sites[site_name]['username'] = data['username'].strip()
                sites[site_name].pop('cookie', None)
            
            if 'password' in data and data['password']:
                sites[site_name]['password'] = data['password'].strip()
            
            # 更新重试配置
            if 'retry' in data and isinstance(data['retry'], dict):
                if 'retry' not in sites[site_name]:
                    sites[site_name]['retry'] = {
                        'enabled': True,
                        'max_retries': 3,
                        'retry_delay_minutes': 1
                    }
                if 'enabled' in data['retry']:
                    sites[site_name]['retry']['enabled'] = data['retry']['enabled']
                if 'max_retries' in data['retry']:
                    sites[site_name]['retry']['max_retries'] = data['retry']['max_retries']
                if 'retry_delay_minutes' in data['retry']:
                    sites[site_name]['retry']['retry_delay_minutes'] = data['retry']['retry_delay_minutes']
            
            # 更新保活配置
            if 'keepalive' in data and isinstance(data['keepalive'], dict):
                if 'keepalive' not in sites[site_name]:
                    sites[site_name]['keepalive'] = {
                        'enabled': True,
                        'last_keepalive_time': None,
                        'method': 'browser_refresh',
                        'interval_minutes': 1440
                    }
                if 'enabled' in data['keepalive']:
                    sites[site_name]['keepalive']['enabled'] = data['keepalive']['enabled']
                if 'method' in data['keepalive']:
                    sites[site_name]['keepalive']['method'] = data['keepalive']['method']
                if 'interval_minutes' in data['keepalive']:
                    sites[site_name]['keepalive']['interval_minutes'] = data['keepalive']['interval_minutes']
        
        # 保存完整的配置 - 正确传入encoding参数
        save_config(full_config, config_path, encoding)
        
        logger.info(f"✓ 已更新 {site_name} 的配置")
        
        return jsonify({
            'status': 'success',
            'message': f'已更新 {site_name} 的配置'
        })
    
    except Exception as e:
        logger.error(f"更新网站配置异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '更新失败'
        }), 500


@app.route('/api/sites/<site_name>', methods=['DELETE'])
@require_login
def delete_site(site_name: str):
    """删除网站配置"""
    try:
        site_name = site_name.strip()
        
        if not site_name:
            return jsonify({
                'status': 'error',
                'message': '网站名称不能为空'
            }), 400
        
        # 加载完整的配置
        full_config, encoding = load_config('config/config.yaml')
        
        if not full_config or 'sites' not in full_config:
            return jsonify({
                'status': 'error',
                'message': '配置格式错误'
            }), 400
        
        sites = full_config['sites']
        config_path = 'config/config.yaml'
        site_found = False
        
        # 列表格式：按 aliases 查找并删除（aliases 是每账号唯一标签）
        if isinstance(sites, list):
            for i, site in enumerate(sites):
                if isinstance(site, dict) and (site.get('aliases') or site.get('name')) == site_name:
                    sites.pop(i)
                    site_found = True
                    break
        # 字典格式：直接删除
        elif isinstance(sites, dict):
            if site_name in sites:
                del sites[site_name]
                site_found = True
        
        if not site_found:
            return jsonify({
                'status': 'error',
                'message': '网站不存在'
            }), 404
        
        # 保存完整的配置
        save_config(full_config, config_path, encoding)
        
        logger.info(f"✓ 已删除网站: {site_name}")
        
        return jsonify({
            'status': 'success',
            'message': f'已删除网站: {site_name}'
        })
    
    except Exception as e:
        logger.error(f"删除网站异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '删除失败'
        }), 500


# ==================== 签到执行API ====================
@app.route('/api/sign/status', methods=['GET'])
@require_login
def sign_status():
    """获取签到系统状态"""
    try:
        stats = ctx.task_scheduler.get_task_statistics()

        # 用 config.yaml 持久化数据覆盖 success_today，
        # 避免服务重启后内存记录归零导致显示为 0
        try:
            _cfg, _ = load_config('config/config.yaml')
            today_str = datetime.now().date().isoformat()
            stats['success_today'] = sum(
                1 for s in (_cfg or {}).get('sites', [])
                if isinstance(s, dict)
                and s.get('last_sign_status') == 'success'
                and (s.get('last_sign_time') or '')[:10] == today_str
            )
        except Exception:
            pass  # 读取失败则保留内存计数

        response = jsonify({
            'status': 'success',
            'task_statistics': stats,
            'timestamp': datetime.now().isoformat()
        })
        # 禁用缓存，确保每次都获取最新数据
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        logger.error(f"获取签到状态异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '获取状态失败'
        }), 500


@app.route('/api/sign/<site_name>/execute', methods=['POST'])
@require_login
def execute_sign(site_name):
    """立即执行某个网站的签到"""
    try:
        # 检查网站是否存在
        sites_config = load_sites_config()
        if site_name not in sites_config:
            return jsonify({
                'status': 'error',
                'message': f'网站 {site_name} 不存在'
            }), 404
        
        # 在后台线程中执行签到
        def run_sign():
            from modules.core.task_scheduler import Task, TaskType
            import uuid, asyncio as aio, time as _time
            task = None
            try:
                safe_print(f"\n[run_sign] 开始执行: {site_name}")

                # 获取网站配置
                _sites_cfg = load_sites_config()
                site_config = _sites_cfg.get(site_name)
                if not site_config:
                    raise Exception(f"网站 {site_name} 配置不存在")

                # 读取重试配置
                retry_cfg = site_config.get('retry', {})
                retry_enabled = retry_cfg.get('enabled', True)
                max_attempts = (int(retry_cfg.get('max_retries', 3)) + 1) if retry_enabled else 1
                retry_delay_min = float(retry_cfg.get('retry_delay_minutes', 1))

                # 创建任务并注册到调度器（使其出现在 running_site_names）
                task = Task(
                    task_id=str(uuid.uuid4()),
                    site_name=site_name,
                    task_type=TaskType.SIGN,
                    scheduled_time=datetime.now(),
                    max_retries=0   # 重试已在外层循环处理，避免 complete_task 二次入队
                )
                ctx.task_scheduler.start_task(task)

                last_err = None
                for attempt in range(1, max_attempts + 1):
                    if attempt > 1:
                        safe_print(f"[run_sign] 第 {attempt}/{max_attempts} 次重试，等待 {retry_delay_min} 分钟…")
                        _time.sleep(retry_delay_min * 60)
                        # 重新加载配置（Cookie 可能已更新）
                        _fresh = load_sites_config()
                        site_config = _fresh.get(site_name) or site_config

                    new_loop = aio.new_event_loop()
                    aio.set_event_loop(new_loop)
                    try:
                        safe_print(f"[run_sign] 调用 execute_sign（第 {attempt} 次）: {site_name}")
                        new_loop.run_until_complete(
                            ctx.sign_executor.execute_sign(task, site_config)
                        )
                        safe_print(f"[run_sign] 第 {attempt} 次执行成功")
                        last_err = None
                        break  # 成功，退出重试循环
                    except Exception as attempt_err:
                        last_err = attempt_err
                        safe_print(f"[run_sign] 第 {attempt}/{max_attempts} 次失败: {attempt_err}")
                    finally:
                        new_loop.close()

                if last_err is None:
                    ctx.task_scheduler.complete_task(task, success=True, message="签到成功")
                else:
                    safe_print(f"[run_sign] 全部 {max_attempts} 次均失败，最终错误: {last_err}")
                    ctx.task_scheduler.complete_task(task, success=False, message=str(last_err))

            except Exception as e:
                error_str = str(e)
                safe_print(f"[run_sign ERROR] {error_str}")
                import traceback
                traceback.print_exc()
                if task:
                    ctx.task_scheduler.complete_task(task, success=False, message=error_str)

                # 分析错误类型
                error_type = 'unknown'
                if 'cookie' in error_str.lower() or '403' in error_str:
                    error_type = 'cookie_expired'
                elif 'timeout' in error_str.lower() or 'connection' in error_str.lower():
                    error_type = 'network_error'
                elif 'login' in error_str.lower() or '401' in error_str:
                    error_type = 'login_failed'

                record_sign_result(site_name, False, error_str, error_type)
        
        thread = threading.Thread(target=run_sign, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'已启动 {site_name} 的签到任务',
            'site': site_name
        })
    
    except Exception as e:
        logger.error(f"执行签到异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '签到启动失败'
        }), 500


@app.route('/api/testroute', methods=['GET']) 
def test_route():
    """测试路由是否工作"""
    return jsonify({
        'status': 'success',
        'message': 'Flask路由系统正常工作'
    })


@app.route('/api/sign/<site_name>/status', methods=['GET'])
@require_login
def get_sign_status(site_name):
    """获取签到任务结果"""
    try:
        with ctx.sign_results_lock:
            safe_print(f"[get_sign_status] site={site_name}, ctx.sign_results={ctx.sign_results}")
            if site_name in ctx.sign_results:
                result = ctx.sign_results[site_name]
                safe_print(f"[get_sign_status] found result: {result}")
                return jsonify({
                    'status': 'success',
                    'data': result,
                    'site': site_name
                })
            else:
                return jsonify({
                    'status': 'pending',
                    'message': '签到任务进行中或未启动',
                    'site': site_name
                })
    except Exception as e:
        logger.error(f"查询签到状态异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '查询失败'
        }), 500


# ==================== 系统API ====================
@app.route('/api/logs', methods=['GET'])
@require_login
def get_logs():
    """获取日志"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        with ctx.log_lock:
            logs = ctx.log_messages[-limit:]
        
        return jsonify({
            'status': 'success',
            'logs': logs
        })
    
    except Exception as e:
        logger.error(f"获取日志异常: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '获取日志失败'
        }), 500


# ==================== 系统设置 ====================
@app.route('/api/settings', methods=['GET'])
@require_login
def get_settings():
    """获取系统设置（管理员账号 + 通知配置）"""
    try:
        from modules.utils.cookie_sync import load_config
        config, _ = load_config('config/config.yaml')
        auth = config.get('auth', {})
        notify = config.get('notify', {})
        bark = notify.get('bark', {})
        return jsonify({
            'success': True,
            'auth_username': auth.get('username', ''),
            'bark_enabled': bark.get('enabled', False),
            'bark_key': bark.get('key', ''),
            'bark_group': bark.get('group', 'app-sign'),
            'bark_sound': bark.get('sound', 'silence'),
            'bark_url': bark.get('url', ''),
            'bark_icon': bark.get('icon', ''),
            'bark_max_retries': bark.get('max_retries', 2),
            'bark_retry_delay_seconds': bark.get('retry_delay_seconds', 1.0),
            'user_agent': (config.get('global') or {}).get('user_agent', '')
        })
    except Exception as e:
        logger.error(f"获取设置异常: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/settings/test-bark', methods=['POST'])
@require_login
def settings_test_bark():
    """用页面当前填写的参数发送一条 Bark 测试通知"""
    try:
        data = request.get_json() or {}
        bark_key = (data.get('bark_key') or '').strip()
        if not bark_key:
            return jsonify({'success': False, 'message': 'Bark Key 不能为空'}), 400

        bark_config = {
            'enabled': True,
            'key':     bark_key,
            'group':   (data.get('bark_group') or 'app-sign').strip() or 'app-sign',
            'sound':   (data.get('bark_sound') or 'silence').strip() or 'silence',
            'url':     (data.get('bark_url') or '').strip(),
            'icon':    (data.get('bark_icon') or '').strip(),
            'max_retries': int(data.get('bark_max_retries') or 0),
            'retry_delay_seconds': int(data.get('bark_retry_delay_seconds') or 1),
        }

        from modules.utils.notify import push_bark
        # push_bark 是同步阻塞的，直接调用；若失败会在函数内打印日志但不抛异常
        # 我们通过捕获 requests 异常来感知结果
        import requests as _req
        payload = {
            'title': '【App-Sign】Bark 测试通知',
            'body':  '✅ 恭喜！通知配置正常，Bark 推送已成功送达。',
            'group': bark_config['group'],
            'sound': bark_config['sound'],
        }
        if bark_config['icon']:
            payload['icon'] = bark_config['icon']
        if bark_config['url']:
            payload['url'] = bark_config['url']

        resp = _req.post(f"https://api.day.app/{bark_key}", json=payload, timeout=10)
        if resp.status_code == 200:
            return jsonify({'success': True, 'message': '测试通知已发送，请检查您的设备'})
        else:
            return jsonify({'success': False, 'message': f'Bark 服务返回 {resp.status_code}: {resp.text[:200]}'})
    except Exception as e:
        logger.error(f"test-bark 异常: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
@require_login
def save_settings():
    """保存系统设置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'}), 400

        from modules.utils.cookie_sync import load_config, save_config
        config, encoding = load_config('config/config.yaml')

        # 管理员账号
        auth_username = data.get('auth_username', '').strip()
        auth_password = data.get('auth_password', '').strip()
        if not auth_username:
            return jsonify({'success': False, 'message': '用户名不能为空'}), 400

        if 'auth' not in config:
            config['auth'] = {}
        config['auth']['username'] = auth_username
        if auth_password:
            # 保存时自动哈希，若已是 bcrypt 格式则不重复哈希
            if not auth_password.startswith(('$2b$', '$2a$', '$2y$')):
                auth_password = hash_password(auth_password)
            config['auth']['password'] = auth_password

        # 通知设置 — Bark
        if 'notify' not in config:
            config['notify'] = {}
        if 'bark' not in config['notify']:
            config['notify']['bark'] = {}
        config['notify']['bark']['enabled'] = bool(data.get('bark_enabled', False))
        config['notify']['bark']['key'] = data.get('bark_key', '').strip()
        config['notify']['bark']['group'] = data.get('bark_group', 'app-sign').strip() or 'app-sign'
        config['notify']['bark']['sound'] = data.get('bark_sound', 'silence').strip() or 'silence'
        config['notify']['bark']['url'] = data.get('bark_url', '').strip()
        config['notify']['bark']['icon'] = data.get('bark_icon', '').strip()
        config['notify']['bark']['max_retries'] = int(data.get('bark_max_retries', 2))
        config['notify']['bark']['retry_delay_seconds'] = int(data.get('bark_retry_delay_seconds', 1))

        # 浏览器标识 — User-Agent
        user_agent = data.get('user_agent', '').strip()
        if user_agent:
            if 'global' not in config:
                config['global'] = {}
            config['global']['user_agent'] = user_agent

        save_config(config, 'config/config.yaml', encoding)
        logger.info(f"系统设置已更新: 用户名={auth_username}")
        return jsonify({'success': True, 'message': '设置已保存'})

    except Exception as e:
        logger.error(f"保存设置异常: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== 错误处理 ====================
@app.errorhandler(404)
def not_found(error):
    """404处理"""
    return jsonify({'status': 'error', 'message': '资源不存在'}), 404


@app.errorhandler(500)
def server_error(error):
    """500处理"""
    logger.error(f"服务器错误: {str(error)}")
    return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500


# ==================== 启动/关闭 ====================
def start_server(host='0.0.0.0', port=21333, debug=False):
    """启动Flask服务"""
    try:
        logger.info(f"启动Web服务: {host}:{port}")
        
        # 预初始化异步循环
        get_async_loop()

        # 启动保活后台调度线程
        ctx.start_keepalive_scheduler()

        # 启动签到后台调度线程
        ctx.start_sign_scheduler()
        
        app.run(host=host, port=port, debug=debug, threaded=True)
    
    except Exception as e:
        logger.error(f"启动服务失败: {str(e)}")
        raise


def stop_server():
    """关闭服务"""
    try:
        if ctx.credential_manager:
            run_async(ctx.credential_manager.cleanup_browser())
        logger.info("Web服务已关闭")
    except Exception as e:
        logger.error(f"关闭服务异常: {str(e)}")


if __name__ == '__main__':
    start_server()
