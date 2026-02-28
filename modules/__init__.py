# -*- coding: utf-8 -*-
"""
签到模块包

模块结构：
- sites/: 所有支持的签到站点脚本（acfun, bilibili, pcbeta, right, smzdm, tieba, youdao）
- core/: 核心功能模块（sign_executor, task_scheduler, credential_manager, browser_manager）
- utils/: 工具模块（cookie_sync, notify, cookie_metadata, cookie_keepalive）
"""
import threading
import sys

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

# 全局打印锁，确保多线程环境下输出不混乱
_print_lock = threading.Lock()


def safe_print(*args, **kwargs):
    """
    线程安全的打印函数
    
    在多线程环境下，防止来自不同线程的输出相互混淆
    """
    with _print_lock:
        print(*args, **kwargs)


def get_user_agent(config=None):
    """从配置读取全局User-Agent，缺失时返回默认值"""
    if isinstance(config, dict):
        value = config.get('user_agent')
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DEFAULT_USER_AGENT


# ==================== 延迟导入子模块（避免循环依赖）====================
# 这些模块被组织到子文件夹，但通过此处重新导出以保持向后兼容

def __getattr__(name):
    """模块属性延迟加载 - 用于动态导入子模块"""
    
    # 核心模块映射
    core_modules = {
        'SignExecutor': 'modules.core.sign_executor',
        'SignExecutionError': 'modules.core.sign_executor',
        'ModuleNotFoundError': 'modules.core.sign_executor',
        'TaskScheduler': 'modules.core.task_scheduler',
        'Task': 'modules.core.task_scheduler',
        'TaskType': 'modules.core.task_scheduler',
        'TaskStatus': 'modules.core.task_scheduler',
        'CredentialManager': 'modules.core.credential_manager',
        'LoginState': 'modules.core.credential_manager',
        'LoginSession': 'modules.core.credential_manager',
        'CaptchaType': 'modules.core.credential_manager',
        'CaptchaInfo': 'modules.core.credential_manager',
        'BrowserManager': 'modules.core.browser_manager',
    }
    
    # 工具模块映射
    utils_modules = {
        'load_config': 'modules.utils.cookie_sync',
        'save_config': 'modules.utils.cookie_sync',
        'NotificationManager': 'modules.utils.notify',
        'CookieMetadata': 'modules.utils.cookie_metadata',
        'CookieKeepalive': 'modules.utils.cookie_keepalive',
    }
    
    # 查找要导入的模块
    all_modules = {**core_modules, **utils_modules}
    
    if name in all_modules:
        module_path = all_modules[name]
        module = __import__(module_path, fromlist=[name])
        attr = getattr(module, name)
        # 缓存导入的属性，避免重复导入
        globals()[name] = attr
        return attr
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # 工具函数
    'safe_print',
    'get_user_agent',
    # Core modules
    'SignExecutor',
    'SignExecutionError',
    'ModuleNotFoundError',
    'TaskScheduler',
    'Task',
    'TaskType',
    'TaskStatus',
    'CredentialManager',
    'LoginState',
    'LoginSession',
    'CaptchaType',
    'CaptchaInfo',
    'BrowserManager',
    # Utils modules
    'load_config',
    'save_config',
    'NotificationManager',
    'CookieMetadata',
    'CookieKeepalive',
]
