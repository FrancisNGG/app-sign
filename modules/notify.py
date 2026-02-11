# -*- coding: utf-8 -*-
"""
通知推送模块 - 支持 Bark 等推送服务
"""
import requests
from datetime import datetime


def push_bark(config, site_name, result_msg):
    """
    发送 Bark 推送通知
    
    Args:
        config: 配置字典
        site_name: 站点名称
        result_msg: 结果消息
    """
    bark_conf = config.get('bark', {})
    if not bark_conf.get('key'):
        return
    
    payload = {
        "title": f"【{site_name}】签到通知",
        "body": f"{result_msg}\n时间：{datetime.now().strftime('%H:%M:%S')}",
        "group": bark_conf.get('group', 'app-sign'),
        "sound": bark_conf.get('sound', 'silence'),
        "icon": bark_conf.get('icon', '')
    }
    
    try:
        url = f"https://api.day.app/{bark_conf['key']}"
        requests.post(url, json=payload, timeout=10)
        print(f"[通知] 已发送 Bark 推送: {site_name} - {result_msg}")
    except Exception as e:
        print(f"[通知] Bark 推送失败: {e}")


def push_notification(config, site_name, result_msg):
    """
    统一推送入口，可扩展其他推送服务
    
    Args:
        config: 配置字典
        site_name: 站点名称
        result_msg: 结果消息
    """
    # Bark 推送
    push_bark(config, site_name, result_msg)
    
    # 可以在这里添加其他推送服务
    # push_telegram(config, site_name, result_msg)
    # push_wechat(config, site_name, result_msg)
