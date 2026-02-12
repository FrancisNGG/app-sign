# -*- coding: utf-8 -*-
"""
通知推送模块 - 支持多种推送服务（Bark、Telegram、企业微信等）
"""
import requests
from datetime import datetime


def push_bark(bark_config, site_name, result_msg):
    """
    发送 Bark 推送通知
    
    Args:
        bark_config: Bark配置字典
        site_name: 站点名称
        result_msg: 结果消息
    """
    # 检查是否启用
    if not bark_config.get('enabled', False):
        return
    
    # 检查API密钥
    api_key = bark_config.get('key', '')
    if not api_key:
        return
    
    # 构建推送数据
    payload = {
        "title": f"【{site_name}】签到通知",
        "body": f"{result_msg}\n时间：{datetime.now().strftime('%H:%M:%S')}",
        "group": bark_config.get('group', 'app-sign'),
        "sound": bark_config.get('sound', 'silence'),
    }
    
    # 添加可选参数
    icon = bark_config.get('icon', '')
    if icon:
        payload['icon'] = icon
    
    url_param = bark_config.get('url', '')
    if url_param:
        payload['url'] = url_param
    
    try:
        url = f"https://api.day.app/{api_key}"
        requests.post(url, json=payload, timeout=10)
        print(f"[通知] 已发送 Bark 推送: {site_name} - {result_msg}")
    except Exception as e:
        print(f"[通知] Bark 推送失败: {e}")


def push_notification(config, site_name, result_msg):
    """
    统一推送入口，支持多种推送服务
    
    Args:
        config: 全局配置字典
        site_name: 站点名称
        result_msg: 结果消息
    """
    # 获取通知配置
    notify_config = config.get('notify', [])
    
    # 如果notify不是列表，返回
    if not isinstance(notify_config, list):
        return
    
    # 遍历所有通知方式
    for notify_item in notify_config:
        if isinstance(notify_item, dict):
            # Bark 推送
            if 'bark' in notify_item:
                bark_config = notify_item['bark']
                if isinstance(bark_config, dict):
                    push_bark(bark_config, site_name, result_msg)
            
            # Telegram 推送（预留）
            # if 'telegram' in notify_item:
            #     telegram_config = notify_item['telegram']
            #     push_telegram(telegram_config, site_name, result_msg)
            
            # 企业微信推送（预留）
            # if 'wechat' in notify_item:
            #     wechat_config = notify_item['wechat']
            #     push_wechat(wechat_config, site_name, result_msg)
