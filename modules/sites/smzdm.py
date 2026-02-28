# -*- coding: utf-8 -*-
"""
什么值得买（SMZDM）签到模块 - 使用 Cookie 方式
"""
import asyncio
import requests
import time
from .. import safe_print


def sign_in(site, config, notify_func):
    """
    什么值得买签到
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '什么值得买')
    cookie_raw = site.get('cookie', '')
    
    if not cookie_raw:
        safe_print(f"[{name}] 缺少 Cookie 配置")
        notify_func(config, name, "配置错误：缺少Cookie")
        return False
    
    # 解析 Cookie
    cookies = {}
    for item in cookie_raw.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            cookies[k] = v
    
    try:
        ua = "smzdm_android_V8.7.8 rv:456 (Nexus 5;Android6.0.1;zh)smzdmapp"
        headers = {
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        safe_print(f"[{name}] 开始签到...")
        
        # 签到接口
        checkin_url = "https://api.smzdm.com/v1/user/checkin"
        
        # 构造签到数据
        timestamp = int(time.time() * 1000)
        checkin_data = {
            "weixin": "1",
            "captcha": "",
            "f": "android",
            "v": "8.7.8",
            "time": str(timestamp)
        }
        
        res = requests.post(
            checkin_url,
            data=checkin_data,
            cookies=cookies,
            headers=headers,
            timeout=20
        )
        
        # 解析结果
        try:
            result = res.json()
            error_code = str(result.get('error_code', ''))
            
            # 获取用户信息（包含签到天数）
            def get_user_info():
                try:
                    user_info_url = "https://api.smzdm.com/v1/user/info"
                    timestamp = int(time.time() * 1000)
                    user_data = {
                        "weixin": "1",
                        "f": "android",
                        "v": "8.7.8",
                        "time": str(timestamp)
                    }
                    res_user = requests.post(
                        user_info_url,
                        data=user_data,
                        cookies=cookies,
                        headers=headers,
                        timeout=20
                    )
                    user_result = res_user.json()
                    if user_result.get('error_code') == '0' or user_result.get('error_code') == 0:
                        data = user_result.get('data', {})
                        # 签到信息在 checkin 字段中
                        checkin_data = data.get('checkin', {})
                        checkin_days = checkin_data.get('daily_attendance_number', '0')
                        smzdm_id = data.get('smzdm_id', '')
                        return f"连续签到天数: {checkin_days}", smzdm_id
                except Exception as e:
                    safe_print(f"[{name}] DEBUG - 获取用户信息失败: {e}")
                return None, None
            
            if error_code == '0':
                # 签到成功
                sign_info, smzdm_id = get_user_info()
                if sign_info:
                    safe_print(f"[{name}] ✓ 签到成功")
                    safe_print(f"[{name}] {sign_info}")
                    notify_func(config, name, f"签到成功\n{sign_info}")
                else:
                    safe_print(f"[{name}] ✓ 签到成功")
                    notify_func(config, name, "签到成功")
                return True
            elif '11111' in error_code:
                # Cookie 失效
                safe_print(f"[{name}] Cookie 已失效，请更新")
                notify_func(config, name, "Cookie已失效")
                return False
            else:
                # 其他情况，可能已签到
                msg = result.get('error_msg', '未知状态')
                safe_print(f"[{name}] 签到响应: {msg}")
                
                # 尝试获取签到信息
                sign_info, smzdm_id = get_user_info()
                
                # 如果包含"已经"等关键词，视为已签到
                if any(x in msg for x in ["已", "完成", "重复"]):
                    if sign_info:
                        safe_print(f"[{name}] {sign_info}")
                        notify_func(config, name, f"今日已签到\n{sign_info}")
                    else:
                        notify_func(config, name, "今日已签到")
                else:
                    if sign_info:
                        notify_func(config, name, f"签到完成: {msg}\n{sign_info}")
                    else:
                        notify_func(config, name, f"签到完成: {msg}")
                return True
                
        except Exception as e:
            safe_print(f"[{name}] 解析响应失败: {e}")
            safe_print(f"[{name}] 响应内容: {res.text[:200]}")
            notify_func(config, name, "签到完成（响应异常）")
            return False
            
    except Exception as e:
        safe_print(f"[{name}] ✗ 运行出错: {e}")
        notify_func(config, name, f"签到失败: {str(e)}")
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
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': base_url,
            'Cookie': cookies
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # 签到接口
        sign_url = f'{base_url}checkin'
        resp = session.post(sign_url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                return f"签到成功：{data.get('msg', '签到完成')}"
            else:
                return f"签到失败：{data.get('msg', '失败')}"
        else:
            return f"签到失败：HTTP {resp.status_code}"
            
    except Exception as e:
        return f"签到异常：{str(e)}"
