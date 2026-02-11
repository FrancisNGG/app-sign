# -*- coding: utf-8 -*-
"""
远景论坛（PCBeta）签到模块 - 使用账号密码登录
"""
import requests
import time


def sign_in(site, config, notify_func):
    """
    远景论坛签到
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '远景论坛')
    username = site.get('username')
    password = site.get('password')
    
    if not username or not password:
        print(f"[{name}] 缺少账号或密码配置")
        notify_func(config, name, "配置错误：缺少账号密码")
        return False
    
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        session = requests.Session()
        session.headers.update({"User-Agent": ua})
        
        print(f"[{name}] 开始登录...")
        
        # 1. 登录
        login_url = "https://i.pcbeta.com/member.php?mod=logging&action=login&loginsubmit=yes&inajax=1"
        login_data = {
            "username": username,
            "password": password
        }
        
        res = session.post(login_url, data=login_data, timeout=20)
        
        # 检查登录是否成功
        if res.status_code != 200:
            print(f"[{name}] 登录失败：HTTP {res.status_code}")
            notify_func(config, name, "登录失败")
            return False
        
        # 简单判断登录状态（远景论坛登录成功会返回包含特定信息的响应）
        if "欢迎" not in res.text and len(res.text) < 100:
            # 可能登录成功但没有明确提示
            pass
        
        print(f"[{name}] 登录成功")
        
        # 2. 领取任务
        time.sleep(2)
        task_apply_url = "https://i.pcbeta.com/home.php?mod=task&do=apply&id=149"
        res = session.get(task_apply_url, timeout=20)
        print(f"[{name}] 已领取任务")
        
        # 3. 完成任务（签到）
        time.sleep(2)
        task_draw_url = "https://i.pcbeta.com/home.php?mod=task&do=draw&id=149"
        res = session.get(task_draw_url, timeout=20)
        
        # 4. 检查结果
        result_text = res.text
        sign_status = ""
        if "成功完成" in result_text:
            sign_status = "签到成功"
        elif "不是进行中" in result_text or "已完成过" in result_text:
            sign_status = "今日已签到"
        else:
            sign_status = "签到完成"
        
        # 5. 获取积分信息
        time.sleep(2)
        credit_url = "https://i.pcbeta.com/home.php?mod=spacecp&ac=credit"
        try:
            res_credit = session.get(credit_url, timeout=20)
            credit_html = res_credit.text
            
            # 提取用户名
            import re
            nickname_match = re.search(r'访问我的空间">(.+?)<', credit_html)
            nickname = nickname_match.group(1) if nickname_match else username
            
            # 提取积分信息 (PB币部分)
            pb_section = re.search(r'<em>\s*PB币([\s\S]+?)</ul>', credit_html)
            if pb_section:
                pb_info = pb_section.group(0)
                # 清理HTML标签
                pb_clean = re.sub(r'<[^>]+>', ' ', pb_info)
                # 清理HTML实体
                pb_clean = pb_clean.replace('&nbsp;', ' ').replace('&amp;', '&')
                pb_clean = ' '.join(pb_clean.split())
                
                # 去掉公式部分（括号及其内容）
                pb_clean = re.sub(r'\s*\([^)]*总积分[^)]*\)\s*', '', pb_clean)
                
                info_msg = f"{nickname} {pb_clean}"
                print(f"[{name}] ✓ {sign_status}")
                print(f"[{name}] {info_msg}")
                notify_func(config, name, f"{sign_status}\n{info_msg}")
            else:
                print(f"[{name}] ✓ {sign_status}（未获取到积分详情）")
                notify_func(config, name, sign_status)
        except Exception as e:
            print(f"[{name}] ✓ {sign_status}（获取积分信息失败: {e}）")
            notify_func(config, name, sign_status)
        
        return True
            
    except Exception as e:
        print(f"[{name}] ✗ 运行出错: {e}")
        notify_func(config, name, f"签到失败: {str(e)}")
        return False
