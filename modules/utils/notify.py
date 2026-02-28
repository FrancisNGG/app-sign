# -*- coding: utf-8 -*-
"""
通知推送模块 - 支持多种推送服务（Bark、Telegram、企业微信等）
"""
import requests
import time
from datetime import datetime
from .. import safe_print


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
    
    url = f"https://api.day.app/{api_key}"

    # 失败重试：最多2次（总计3次）
    max_retries = int(bark_config.get('max_retries', 2))
    retry_delay = int(bark_config.get('retry_delay_seconds', 1))

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                safe_print(f"[通知] 已发送 Bark 推送: {site_name} - {result_msg}")
                return

            raise requests.RequestException(f"HTTP {response.status_code}: {response.text[:120]}")
        except Exception as e:
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            safe_print(f"[通知] Bark 推送失败: {e}")


def push_notification(config, site_name, result_msg):
    """
    统一推送入口，支持多种推送服务

    config['notify'] 支持两种格式：
      - 字典格式（当前默认）: {bark: {...}, telegram: {...}}
      - 列表格式（旧版）:     [{bark: {...}}, {telegram: {...}}]

    Args:
        config: 全局配置字典
        site_name: 站点名称
        result_msg: 结果消息
    """
    notify_config = config.get('notify', {})

    # 兼容列表格式（旧版）
    if isinstance(notify_config, list):
        for notify_item in notify_config:
            if isinstance(notify_item, dict):
                bark_cfg = notify_item.get('bark')
                if isinstance(bark_cfg, dict):
                    push_bark(bark_cfg, site_name, result_msg)
        return

    # 字典格式（当前默认）
    if not isinstance(notify_config, dict):
        return

    # Bark 推送
    bark_cfg = notify_config.get('bark')
    if isinstance(bark_cfg, dict):
        push_bark(bark_cfg, site_name, result_msg)

    # Telegram 推送（预留）
    # telegram_cfg = notify_config.get('telegram')
    # if isinstance(telegram_cfg, dict):
    #     push_telegram(telegram_cfg, site_name, result_msg)

    # 企业微信推送（预留）
    # wechat_cfg = notify_config.get('wechat')
    # if isinstance(wechat_cfg, dict):
    #     push_wechat(wechat_cfg, site_name, result_msg)
