# -*- coding: utf-8 -*-
"""
华米运动刷步数模块
"""
import re
import json
import random
import requests
from datetime import datetime, timedelta


def sign_in(site, config, notify_func):
    """
    华米运动刷步数
    
    刷步流程：
    1. 使用手机号密码获取code
    2. 使用code获取login_token
    3. 获取app_token
    4. 生成随机步数
    5. 提交步数数据
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '华米运动')
    username = site.get('username', '')  # 手机号
    password = site.get('password', '')
    min_step = site.get('min_step', 10000)  # 最小步数
    max_step = site.get('max_step', 20000)  # 最大步数
    
    if not username or not password:
        result_msg = "刷步失败: 缺少账号或密码"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return
    
    headers = {
        'User-Agent': 'MiFit/5.5.1 (iPad; iOS 15.1; Scale/2.00)',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
    }
    
    try:
        # 1. 获取code
        print(f"[{name}] 正在登录...")
        code_url = f'https://api-user.huami.com/registrations/+86{username}/tokens'
        code_data = {
            'client_id': 'HuaMi',
            'password': password,
            'redirect_uri': 'https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html',
            'token': 'access'
        }
        
        code_resp = requests.post(code_url, data=code_data, headers=headers, allow_redirects=False, timeout=10)
        
        if code_resp.status_code != 303:
            result_msg = f"刷步失败: 登录失败 (HTTP {code_resp.status_code})"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        # 从重定向Location中提取code
        location = code_resp.headers.get('Location', '')
        code_match = re.search(r'access=(.+?)&', location)
        if not code_match:
            result_msg = "刷步失败: 无法获取access code"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        code = code_match.group(1)
        print(f"[{name}] 获取code成功")
        
        # 2. 获取login_token和userid
        print(f"[{name}] 获取登录令牌...")
        login_url = 'https://account.huami.com/v2/client/login'
        login_data = {
            'app_name': 'com.xiaomi.hm.health',
            'app_version': '5.5.1',
            'code': code,
            'country_code': 'CN',
            'device_id': '54FAAB9E-2480-4365-AAB2-8423D5C64A98',
            'device_model': 'phone',
            'grant_type': 'access_token',
            'third_name': 'huami_phone'
        }
        
        login_resp = requests.post(login_url, data=login_data, headers=headers, timeout=10)
        
        if login_resp.status_code != 200:
            result_msg = f"刷步失败: 获取登录令牌失败 (HTTP {login_resp.status_code})"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        login_data = login_resp.json()
        login_token = login_data.get('token_info', {}).get('login_token', '')
        userid = login_data.get('token_info', {}).get('user_id', '')
        
        if not login_token or not userid:
            result_msg = "刷步失败: 登录令牌或用户ID为空"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        print(f"[{name}] 登录成功, 用户ID: {userid}")
        
        # 3. 获取app_token
        print(f"[{name}] 获取应用令牌...")
        token_url = f'https://account-cn.huami.com/v1/client/app_tokens?app_name=com.xiaomi.hm.health&dn=api-user.huami.com%2Capi-mifit.huami.com%2Capp-analytics.huami.com&login_token={login_token}'
        token_headers = {
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; MI 6 MIUI/20.6.18)'
        }
        
        token_resp = requests.get(token_url, headers=token_headers, timeout=10)
        
        if token_resp.status_code != 200:
            result_msg = f"刷步失败: 获取应用令牌失败 (HTTP {token_resp.status_code})"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        token_data = token_resp.json()
        app_token = token_data.get('token_info', {}).get('app_token', '')
        
        if not app_token:
            result_msg = "刷步失败: 应用令牌为空"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        print(f"[{name}] 获取应用令牌成功")
        
        # 4. 生成随机步数
        step = random.randint(int(min_step), int(max_step))
        print(f"[{name}] 生成随机步数: {step} (范围: {min_step}-{max_step})")
        
        # 5. 生成当天日期
        today = datetime.now()
        date_str = today.strftime('%Y-%m-%d')
        
        # 6. 构建步数数据（模拟真实运动数据）
        data_json = [{
            "data_hr": "\\/\\/\\/\\/\\/\\/9L\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/Vv\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/0v\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/9e\\/\\/\\/\\/\\/0n\\/a\\/\\/\\/S\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/0b\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/1FK\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/R\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\/",
            "date": date_str,
            "data": [{
                "start": 0,
                "stop": 1439,
                "value": "UAAAAAA..."  # 心率数据，这里使用固定值
            }],
            "summary": json.dumps({
                "v": 6,
                "slp": {
                    "st": 0,
                    "ed": 0,
                    "dp": 0,
                    "lt": 0,
                    "wk": 0,
                    "usrSt": -1440,
                    "usrEd": -1440,
                    "wc": 0,
                    "is": 0,
                    "lb": 0,
                    "to": 0,
                    "dt": 0,
                    "rhr": 0,
                    "ss": 0
                },
                "stp": {
                    "ttl": step,  # 总步数
                    "dis": int(step * 0.7),  # 距离(米)
                    "cal": int(step * 0.04),  # 卡路里
                    "wk": int(step / 200),  # 运动分钟数
                    "rn": 0,
                    "runDist": 0,
                    "runCal": 0,
                    "stage": []
                },
                "goal": 8000,
                "tz": "28800"
            }),
            "source": 24,
            "type": 0
        }]
        
        # 7. 提交步数
        print(f"[{name}] 提交步数数据...")
        submit_url = 'https://api-mifit-cn.huami.com/v1/data/band_data.json'
        submit_headers = {
            'apptoken': app_token,
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'MiFit/5.5.1 (iPad; iOS 15.1; Scale/2.00)'
        }
        submit_data = {
            'userid': userid,
            'last_sync_data_time': int((today - timedelta(days=1)).timestamp()),
            'device_type': '0',
            'last_deviceid': 'DA932FFFFE8816E7',
            'data_json': json.dumps(data_json)
        }
        
        submit_resp = requests.post(submit_url, data=submit_data, headers=submit_headers, timeout=10)
        
        if submit_resp.status_code != 200:
            result_msg = f"刷步失败: 提交数据失败 (HTTP {submit_resp.status_code})"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return
        
        # 8. 解析结果
        try:
            result = submit_resp.json()
            message = result.get('message', '')
            
            if message == 'success' or 'success' in message.lower():
                result_msg = f"刷步成功\n日期: {date_str}\n步数: {step}\n账号: {username}"
                print(f"[{name}] 刷步成功: {step}步")
            else:
                result_msg = f"刷步失败: {message}"
                print(f"[{name}] {result_msg}")
        except:
            result_msg = f"刷步完成\n日期: {date_str}\n步数: {step}\n账号: {username}"
            print(f"[{name}] {result_msg}")
        
        notify_func(config, name, result_msg)
        
    except requests.RequestException as e:
        result_msg = f"刷步失败: 网络请求异常 - {e}"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
    except Exception as e:
        result_msg = f"刷步失败: {e}"
        print(f"[{name}] {result_msg}")
        import traceback
        traceback.print_exc()
        notify_func(config, name, result_msg)
