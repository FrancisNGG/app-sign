# -*- coding: utf-8 -*-
"""
签到模块包
"""
import threading

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
