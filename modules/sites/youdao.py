# -*- coding: utf-8 -*-
"""
有道云笔记签到模块
"""
import re
import requests
from .. import safe_print, get_user_agent


def sign_in(site, config, notify_func):
    """
    有道云笔记签到
    
    签到流程：
    1. 从Cookie中提取CSTK参数
    2. Android客户端登录奖励
    3. Android客户端签到
    4. Windows客户端签到
    5. 获取用户信息
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '有道云笔记')
    cookie = site.get('cookie', '')
    
    if not cookie:
        result_msg = "签到失败: 缺少Cookie"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    
    headers = {
        'User-Agent': get_user_agent(config),
        'Cookie': cookie
    }
    
    headers_android = {
        'User-Agent': 'ynote-android',
        'Cookie': cookie
    }
    
    session = requests.Session()
    
    try:
        # 1. 提取CSTK参数
        cstk_match = re.search(r'YNOTE_CSTK=(.{8})', cookie)
        if not cstk_match:
            result_msg = "签到失败: 无法提取CSTK参数"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        cstk = cstk_match.group(1)
        safe_print(f"[{name}] CSTK: {cstk}")
        
        rewards = []
        
        # 2. Android客户端登录奖励
        try:
            login_url = 'https://note.youdao.com/yws/api/daupromotion?method=sync'
            login_resp = session.post(login_url, headers=headers_android, timeout=10)
            if login_resp.status_code == 200:
                login_data = login_resp.json()
                if 'rewardSpace' in str(login_data):
                    reward_match = re.search(r'"rewardSpace":(\d+)', login_resp.text)
                    if reward_match:
                        space_bytes = int(reward_match.group(1))
                        space_mb = round(space_bytes / (1024 * 1024), 2)
                        rewards.append(f"Android登录奖励: {space_mb}MB")
                        safe_print(f"[{name}] Android登录奖励: {space_mb}MB")
        except Exception as e:
            safe_print(f"[{name}] Android登录奖励失败: {e}")
        
        # 3. Android客户端签到
        try:
            android_url = 'https://note.youdao.com/yws/mapi/user?method=checkin&_system=android'
            android_resp = session.post(android_url, headers=headers_android, timeout=10)
            if android_resp.status_code == 200:
                android_data = android_resp.json()
                if 'space' in str(android_data):
                    space_match = re.search(r'"space":(\d+)', android_resp.text)
                    if space_match:
                        space_bytes = int(space_match.group(1))
                        space_mb = round(space_bytes / (1024 * 1024), 2)
                        rewards.append(f"Android签到: {space_mb}MB")
                        safe_print(f"[{name}] Android签到奖励: {space_mb}MB")
        except Exception as e:
            safe_print(f"[{name}] Android签到失败: {e}")
        
        # 4. Windows客户端签到
        try:
            windows_url = f'https://note.youdao.com/yws/mapi/user?method=checkin&device_type=PC&_system=windows&_appName=ynote&_vendor=official-website&cstk={cstk}'
            windows_resp = session.post(windows_url, headers=headers, timeout=10)
            if windows_resp.status_code == 200:
                windows_data = windows_resp.json()
                if 'space' in str(windows_data):
                    space_match = re.search(r'"space":(\d+)', windows_resp.text)
                    if space_match:
                        space_bytes = int(space_match.group(1))
                        space_mb = round(space_bytes / (1024 * 1024), 2)
                        rewards.append(f"Windows签到: {space_mb}MB")
                        safe_print(f"[{name}] Windows签到奖励: {space_mb}MB")
        except Exception as e:
            safe_print(f"[{name}] Windows签到失败: {e}")
        
        # 5. 获取用户信息
        try:
            user_url = 'https://note.youdao.com/yws/mapi/user?method=get'
            user_resp = session.post(user_url, headers=headers_android, timeout=10)
            if user_resp.status_code == 200:
                capacity_match = re.search(r'"total":(\d+)', user_resp.text)
                if capacity_match:
                    total_bytes = int(capacity_match.group(1))
                    total_mb = round(total_bytes / (1024 * 1024), 2)
                    rewards.append(f"总容量: {total_mb}MB")
                    safe_print(f"[{name}] 当前总容量: {total_mb}MB")
        except Exception as e:
            safe_print(f"[{name}] 获取用户信息失败: {e}")
        
        # 生成结果消息
        if rewards:
            result_msg = "签到成功\n" + "\n".join(rewards)
        else:
            result_msg = "签到完成，但未获取到奖励信息"
        
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return True
        
    except requests.RequestException as e:
        result_msg = f"签到失败: 网络请求异常 - {e}"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    except Exception as e:
        result_msg = f"签到失败: {e}"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False


# ==================== 异步API适配函数 ====================
async def sign(base_url, cookies, **kwargs):
    """
    异步签到函数 - 用于Web API调用
    
    Args:
        base_url: 网站URL
        cookies: Cookie字符串
        **kwargs: 其他参数
        
    Returns:
        str: 签到结果消息
    """
    if not cookies:
        return "签到失败：缺少Cookie"
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _sign_sync,
            cookies,
            base_url
        )
        return result
        
    except Exception as e:
        return f"签到失败：{str(e)}"


def _sign_sync(cookies, base_url):
    """同步签到实现"""
    try:
        headers = {
            'User-Agent': get_user_agent(),
            'Referer': base_url,
            'Cookie': cookies
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # 签到接口
        sign_url = f'{base_url}user/checkin'
        resp = session.post(sign_url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('ret') == 0:
                return f"签到成功：{data.get('msg', '签到完成')}"
            else:
                return f"签到失败：{data.get('msg', '失败')}"
        else:
            return f"签到失败：HTTP {resp.status_code}"
            
    except Exception as e:
        return f"签到异常：{str(e)}"
