# -*- coding: utf-8 -*-
"""
什么值得买（SMZDM）签到模块 - 使用 Cookie 方式
"""
import requests
import time


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
        ua = "smzdm_android_V8.7.8 rv:456 (Nexus 5;Android6.0.1;zh)smzdmapp"
        headers = {
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        print(f"[{name}] 开始签到...")
        
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
                    print(f"[{name}] DEBUG - 获取用户信息失败: {e}")
                return None, None
            
            if error_code == '0':
                # 签到成功
                sign_info, smzdm_id = get_user_info()
                if sign_info:
                    print(f"[{name}] ✓ 签到成功")
                    print(f"[{name}] {sign_info}")
                    notify_func(config, name, f"签到成功\n{sign_info}")
                else:
                    print(f"[{name}] ✓ 签到成功")
                    notify_func(config, name, "签到成功")
                return True
            elif '11111' in error_code:
                # Cookie 失效
                print(f"[{name}] Cookie 已失效，请更新")
                notify_func(config, name, "Cookie已失效")
                return False
            else:
                # 其他情况，可能已签到
                msg = result.get('error_msg', '未知状态')
                print(f"[{name}] 签到响应: {msg}")
                
                # 尝试获取签到信息
                sign_info, smzdm_id = get_user_info()
                
                # 如果包含"已经"等关键词，视为已签到
                if any(x in msg for x in ["已", "完成", "重复"]):
                    if sign_info:
                        print(f"[{name}] {sign_info}")
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
            print(f"[{name}] 解析响应失败: {e}")
            print(f"[{name}] 响应内容: {res.text[:200]}")
            notify_func(config, name, "签到完成（响应异常）")
            return False
            
    except Exception as e:
        print(f"[{name}] ✗ 运行出错: {e}")
        notify_func(config, name, f"签到失败: {str(e)}")
        return False
