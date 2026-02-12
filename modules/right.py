# -*- coding: utf-8 -*-
"""
恩山无线论坛签到模块 - 使用 Cookie 方式
依赖CookieCloud同步浏览器Cookie（包含5秒盾验证Cookie）
Cookie保活由 modules/cookie_keepalive.py 独立管理
"""
import requests
import re
import time
from urllib.parse import urljoin


def sign_in(site, config, notify_func):
    """
    恩山论坛签到
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '恩山无线论坛')
    base_url = site.get('base_url', 'https://www.right.com.cn/forum/')
    cookie_raw = site.get('cookie', '')
    
    if not cookie_raw:
        print(f"[{name}] 缺少 Cookie 配置")
        notify_func(config, name, "配置错误：缺少Cookie")
        return False
    
    # 解析 Cookie
    cookies = {}
    for item in cookie_raw.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            cookies[k] = v
    
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        
        print(f"[{name}] 开始签到...")
        
        # 创建会话
        session = requests.Session()
        session.cookies.update(cookies)
        session.headers.update({"User-Agent": ua})
        
        # 1. 先访问首页保活Cookie
        print(f"[{name}] 刷新会话...")
        session.get(base_url, timeout=15, allow_redirects=True)
        import time
        time.sleep(1)
        
        # 2. 重新访问获取 formhash
        res = session.get(base_url, timeout=20, allow_redirects=True)
        html = res.text
        
        # 提取 formhash
        fh = re.search(r'formhash=([a-z0-9]+)', html)
        if not fh:
            print(f"[{name}] ✗ Cookie已失效，无法获取 formhash")
            notify_func(config, name, "Cookie已失效")
            return False
        
        formhash = fh.group(1)
        print(f"[{name}] 获取 formhash 成功")
        
        # 延迟后执行签到
        time.sleep(1)
        
        # 3. 执行签到
        sign_url = urljoin(base_url, "plugin.php?id=erling_qd:action&action=sign&inajax=1")
        data = {
            "formhash": formhash,
            "qdxq": "kx",
            "qdmode": "1",
            "todaysay": "Good Day"
        }
        
        headers = {
            "User-Agent": ua,
            "Referer": base_url,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        res_sign = session.post(
            sign_url,
            data=data,
            headers=headers,
            timeout=25,
            allow_redirects=True
        )
        
        # 4. 判断结果并提取信息
        result_text = res_sign.text
        
        # 尝试解析JSON格式
        try:
            import json
            result_json = json.loads(result_text)
            
            # JSON格式的恩山返回
            if isinstance(result_json, dict):
                sign_info_parts = []
                
                # 提取今日积分
                if 'credit' in result_json:
                    credit = result_json.get('credit', 0)
                    sign_info_parts.append(f"今日积分：{credit}")
                
                # 提取连续签到天数
                if 'continuous_days' in result_json:
                    days = result_json.get('continuous_days', '0')
                    sign_info_parts.append(f"连续签到：{days} 天")
                
                # 提取总签到天数
                if 'total_days' in result_json:
                    total = result_json.get('total_days', '0')
                    sign_info_parts.append(f"总签到天数：{total} 天")
                
                # 提取消息
                message = result_json.get('message', '')
                success = result_json.get('success', False)
                
                # 判断签到状态
                if success or "成功" in message:
                    sign_status = "签到成功"
                elif "已经" in message or "已签" in message:
                    sign_status = "今日已签到"
                else:
                    sign_status = message if message else "签到完成"
                
                # 输出结果
                if sign_info_parts:
                    sign_info = "\n".join(sign_info_parts)
                    print(f"[{name}] ✓ {sign_status}")
                    print(f"[{name}] {sign_info}")
                    notify_func(config, name, f"{sign_status}\n{sign_info}")
                else:
                    print(f"[{name}] ✓ {sign_status}")
                    notify_func(config, name, sign_status)
                
                return True
        except json.JSONDecodeError:
            # 不是JSON格式，使用正则提取
            pass
        
        # 备用：使用正则表达式提取（适合HTML格式）
        sign_info_parts = []
        
        # 提取今日积分（多种可能的格式）
        today_credit = re.search(r'今日积分[:：]\s*(\d+)', result_text) or \
                      re.search(r'今日获得\s*(\d+)\s*积分', result_text) or \
                      re.search(r'获得\s*(\d+)\s*积分', result_text)
        if today_credit:
            sign_info_parts.append(f"今日积分：{today_credit.group(1)}")
        
        # 提取连续签到
        continuous = re.search(r'连续签到[:：]\s*(\d+)\s*天', result_text) or \
                    re.search(r'已连续签到\s*(\d+)\s*天', result_text)
        if continuous:
            sign_info_parts.append(f"连续签到：{continuous.group(1)} 天")
        
        # 提取总签到天数
        total_days = re.search(r'总签到天数[:：]\s*(\d+)\s*天', result_text) or \
                    re.search(r'累计签到\s*(\d+)\s*天', result_text)
        if total_days:
            sign_info_parts.append(f"总签到天数：{total_days.group(1)} 天")
        
        # 判断签到状态
        if "成功" in result_text:
            sign_status = "签到成功"
        elif "已经" in result_text or "已签" in result_text:
            sign_status = "今日已签到"
        elif "恭喜" in result_text or "完成" in result_text:
            sign_status = "签到完成"
        else:
            sign_status = "签到完成"
        
        # 输出结果
        if sign_info_parts:
            sign_info = "\n".join(sign_info_parts)
            print(f"[{name}] ✓ {sign_status}")
            print(f"[{name}] {sign_info}")
            notify_func(config, name, f"{sign_status}\n{sign_info}")
        else:
            print(f"[{name}] ✓ {sign_status}")
            notify_func(config, name, sign_status)
        
        return True
            
    except Exception as e:
        print(f"[{name}] ✗ 运行出错: {e}")
        notify_func(config, name, f"签到失败: {str(e)}")
        return False
