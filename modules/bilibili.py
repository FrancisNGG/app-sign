# -*- coding: utf-8 -*-
"""
哔哩哔哩签到模块
"""
import re
import time
import requests


def sign_in(site, config, notify_func):
    """
    哔哩哔哩签到
    
    签到流程：
    1. 获取随机视频BV号
    2. 分享视频
    3. 观看视频（心跳）
    4. 漫画签到
    5. 获取用户信息
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '哔哩哔哩')
    cookie = site.get('cookie', '')
    
    if not cookie:
        result_msg = "签到失败: 缺少Cookie"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.bilibili.com/',
        'Cookie': cookie
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    # 任务状态收集
    task_results = []  # 横向显示的任务结果
    user_info = []  # 用户信息
    
    try:
        # 1. 提取bili_jct参数（CSRF Token）
        bili_jct_match = re.search(r'bili_jct=([^;]+)', cookie)
        if not bili_jct_match:
            result_msg = "签到失败: Cookie中缺少bili_jct参数"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        bili_jct = bili_jct_match.group(1)
        print(f"[{name}] 获取bili_jct成功")
        
        # 2. 获取随机视频BV号
        print(f"[{name}] 获取随机视频...")
        try:
            video_url = 'https://api.bilibili.com/x/web-interface/dynamic/region?pn=1&ps=12&rid=129'
            video_resp = session.get(video_url, timeout=10)
            
            if video_resp.status_code == 200:
                bv_match = re.search(r'(BV[A-Za-z0-9]{10})', video_resp.text)
                if bv_match:
                    bv_id = bv_match.group(1)
                    print(f"[{name}] 获取视频: {bv_id}")
                else:
                    bv_id = 'BV1xx411c7mD'  # 默认视频
                    print(f"[{name}] 使用默认视频: {bv_id}")
            else:
                bv_id = 'BV1xx411c7mD'
                print(f"[{name}] 使用默认视频: {bv_id}")
        except:
            bv_id = 'BV1xx411c7mD'
            print(f"[{name}] 使用默认视频: {bv_id}")
        
        # 3. 分享视频
        print(f"[{name}] 分享视频...")
        try:
            share_url = 'https://api.bilibili.com/x/web-interface/share/add'
            share_data = f'bvid={bv_id}&csrf={bili_jct}'
            share_headers = headers.copy()
            share_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            share_resp = session.post(share_url, data=share_data, headers=share_headers, timeout=10)
            
            if share_resp.status_code == 200:
                share_result = share_resp.json()
                if share_result.get('code') == 0:
                    task_results.append("分享视频✓")
                    print(f"[{name}] 分享视频成功")
                else:
                    msg = share_result.get('message', '未知错误')
                    task_results.append(f"分享视频✗")
                    print(f"[{name}] 分享视频: {msg}")
            
            time.sleep(2)
        except Exception as e:
            print(f"[{name}] 分享视频失败: {e}")
        
        # 4. 观看视频（心跳）
        print(f"[{name}] 观看视频...")
        try:
            heartbeat_url = 'https://api.bilibili.com/x/click-interface/web/heartbeat'
            heartbeat_data = f'bvid={bv_id}&csrf={bili_jct}&played_time=2'
            heartbeat_headers = headers.copy()
            heartbeat_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            heartbeat_resp = session.post(heartbeat_url, data=heartbeat_data, headers=heartbeat_headers, timeout=10)
            
            if heartbeat_resp.status_code == 200:
                task_results.append("观看视频✓")
                print(f"[{name}] 观看视频成功")
            
            time.sleep(2)
        except Exception as e:
            print(f"[{name}] 观看视频失败: {e}")
        
        # 5. 漫画签到（直播签到活动已下线，已移除）
        print(f"[{name}] 漫画签到...")
        try:
            manga_url = 'https://manga.bilibili.com/twirp/activity.v1.Activity/ClockIn'
            manga_headers = headers.copy()
            manga_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            manga_data = 'platform=ios'
            
            manga_resp = session.post(manga_url, data=manga_data, headers=manga_headers, timeout=10)
            
            if manga_resp.status_code == 200:
                manga_text = manga_resp.text
                if 'duplicate' in manga_text or 'clockin clockin is duplicate' in manga_text:
                    task_results.append("漫画签到✓")
                    print(f"[{name}] 漫画签到: 今日已签到")
                elif 'msg":"success"' in manga_text or '"code":0' in manga_text:
                    task_results.append("漫画签到✓")
                    print(f"[{name}] 漫画签到成功")
                else:
                    task_results.append("漫画签到✓")
                    print(f"[{name}] 漫画签到完成")
            
            time.sleep(2)
        except Exception as e:
            print(f"[{name}] 漫画签到失败: {e}")
        
        # 6. 获取用户信息
        print(f"[{name}] 获取用户信息...")
        try:
            nav_url = 'https://api.bilibili.com/x/web-interface/nav'
            nav_resp = session.get(nav_url, timeout=10)
            
            if nav_resp.status_code == 200:
                nav_result = nav_resp.json()
                if nav_result.get('code') == 0:
                    data = nav_result.get('data', {})
                    uname = data.get('uname', '未知')
                    level = data.get('level_info', {}).get('current_level', 0)
                    coin = data.get('money', 0)
                    exp = data.get('level_info', {}).get('current_exp', 0)
                    
                    user_info.append(f"用户: {uname}")
                    user_info.append(f"等级: Lv.{level} (经验{exp})")
                    user_info.append(f"硬币: {coin}个")
                    
                    print(f"[{name}] 用户: {uname} | Lv.{level} | {coin}硬币")
        except Exception as e:
            print(f"[{name}] 获取用户信息失败: {e}")
        
        # 7. 获取漫读券
        try:
            manga_coupon_url = 'https://manga.bilibili.com/twirp/user.v1.User/GetCoupons'
            manga_coupon_headers = headers.copy()
            manga_coupon_headers['Content-Type'] = 'application/json; charset=utf-8'
            manga_coupon_data = '{"notExpired":true,"pageNum":1,"pageSize":20,"tabType":1,"type":0}'
            
            manga_coupon_resp = session.post(manga_coupon_url, data=manga_coupon_data, headers=manga_coupon_headers, timeout=10)
            
            if manga_coupon_resp.status_code == 200:
                manga_data = manga_coupon_resp.json()
                remain = manga_data.get('data', {}).get('total_remain_amount', 0)
                user_info.append(f"漫读券: {remain}张")
                print(f"[{name}] 漫读券: {remain}张")
        except Exception as e:
            print(f"[{name}] 获取漫读券失败: {e}")
        
        # 生成结果消息
        msg_parts = []
        
        # 任务结果（横向显示）
        if task_results:
            msg_parts.append(" ".join(task_results))
        
        # 用户信息
        if user_info:
            msg_parts.extend(user_info)
        
        result_msg = "\n".join(msg_parts)
        
        # 检查是否有成功的任务
        has_success = any("✓" in result for result in task_results) if task_results else False
        
        print(f"[{name}] 签到完成")
        notify_func(config, name, result_msg)
        return has_success
        
    except requests.RequestException as e:
        result_msg = f"签到失败: 网络请求异常 - {e}"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    except Exception as e:
        result_msg = f"签到失败: {e}"
        print(f"[{name}] {result_msg}")
        import traceback
        traceback.print_exc()
        notify_func(config, name, result_msg)
        return False
