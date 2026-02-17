# -*- coding: utf-8 -*-
"""
百度贴吧签到模块
"""
import re
import time
import random
import requests
from urllib.parse import quote
from . import safe_print, get_user_agent


def sign_in(site, config, notify_func):
    """
    百度贴吧签到
    
    签到流程：
    1. 验证Cookie有效性
    2. 获取关注的贴吧列表（支持分页）
    3. 对每个贴吧进行签到
    4. 统计签到结果
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', '百度贴吧')
    cookie = site.get('cookie', '')
    
    if not cookie:
        result_msg = "签到失败: 缺少Cookie"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    
    headers = {
        'User-Agent': get_user_agent(config),
        'Cookie': cookie,
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://tieba.baidu.com/'
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        # 1. 验证Cookie有效性
        safe_print(f"[{name}] 验证Cookie...")
        check_url = 'https://tieba.baidu.com/f/user/json_userinfo'
        check_resp = session.get(check_url, timeout=10)
        
        if check_resp.status_code != 200 or 'session_id' not in check_resp.text:
            result_msg = "签到失败: Cookie无效或已过期"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 2. 获取关注的贴吧列表
        safe_print(f"[{name}] 获取关注的贴吧列表...")
        all_bars = []
        
        # 获取第一页以确定总页数
        first_page_url = 'https://tieba.baidu.com/f/like/mylike?pn=1'
        first_resp = session.get(first_page_url, timeout=10)
        
        if first_resp.status_code != 200:
            result_msg = "签到失败: 无法获取贴吧列表"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 提取总页数
        total_pages_match = re.search(r'&pn=([^"]+)">尾页</a>', first_resp.text)
        total_pages = int(total_pages_match.group(1)) if total_pages_match else 1
        safe_print(f"[{name}] 共{total_pages}页贴吧")
        
        # 遍历所有页面获取贴吧列表
        for page in range(1, total_pages + 1):
            page_url = f'https://tieba.baidu.com/f/like/mylike?pn={page}'
            page_resp = session.get(page_url, timeout=10)
            
            if page_resp.status_code == 200:
                # 提取当前页所有贴吧名称
                bars = re.findall(r'href="/f\?kw=[^"]+"\s+title="([^"]+)"', page_resp.text)
                all_bars.extend(bars)
                safe_print(f"[{name}] 第{page}页: 找到{len(bars)}个贴吧")
            
            # 翻页延迟
            if page < total_pages:
                time.sleep(random.uniform(0.5, 1.5))
        
        safe_print(f"[{name}] 共找到{len(all_bars)}个贴吧")
        
        if not all_bars:
            result_msg = "签到失败: 未找到关注的贴吧"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 3. 对每个贴吧进行签到
        signed = []  # 签到成功的贴吧
        already_signed = []  # 已签到的贴吧
        failed = []  # 签到失败的贴吧
        
        sign_headers = headers.copy()
        sign_headers.update({
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://tieba.baidu.com'
        })
        
        for bar in all_bars:
            try:
                sign_url = 'https://tieba.baidu.com/sign/add'
                sign_data = f'ie=utf-8&kw={quote(bar)}'
                
                sign_resp = session.post(sign_url, data=sign_data, headers=sign_headers, timeout=10)
                
                if sign_resp.status_code == 200:
                    result = sign_resp.json()
                    
                    # 签到成功
                    if result.get('error') == '':
                        forum_name = result.get('data', {}).get('forum_info', {}).get('forum_name', bar)
                        signed.append(forum_name)
                        safe_print(f"[{name}] ✓ {forum_name}")
                    
                    # 已经签到过
                    elif 'error' in result:
                        error_msg = result.get('error', '')
                        # 匹配"亲，你之前已经签过了"等消息
                        if '已经签' in error_msg or '已签' in error_msg:
                            already_signed.append(bar)
                            safe_print(f"[{name}] - {bar} (已签)")
                        else:
                            failed.append(f"{bar}: {error_msg}")
                            safe_print(f"[{name}] ✗ {bar}: {error_msg}")
                else:
                    failed.append(f"{bar}: HTTP {sign_resp.status_code}")
                    safe_print(f"[{name}] ✗ {bar}: HTTP {sign_resp.status_code}")
                
                # 随机延迟，避免请求过快
                time.sleep(random.uniform(0.5, 2.0))
                
            except Exception as e:
                failed.append(f"{bar}: {str(e)}")
                safe_print(f"[{name}] ✗ {bar}: {e}")
        
        # 4. 生成结果消息
        result_parts = []
        
        # 已签到数量
        if already_signed:
            result_parts.append(f"已签到: {len(already_signed)}个")
        else:
            result_parts.append("已签到: 无")
        
        # 成功（横向列出贴吧名称）
        if signed:
            # 限制显示前10个贴吧
            if len(signed) <= 10:
                result_parts.append(f"成功: {' '.join(signed)}")
            else:
                result_parts.append(f"成功: {' '.join(signed[:10])}...等{len(signed)}个")
        else:
            result_parts.append("成功: 无")
        
        # 失败（横向列出贴吧名称，提取贴吧名）
        if failed:
            # 从"贴吧名: 错误信息"中提取贴吧名
            failed_names = [f.split(':')[0].strip() for f in failed]
            if len(failed_names) <= 10:
                result_parts.append(f"失败: {' '.join(failed_names)}")
            else:
                result_parts.append(f"失败: {' '.join(failed_names[:10])}...等{len(failed_names)}个")
        else:
            result_parts.append("失败: 无")
        
        result_msg = "\n".join(result_parts) if result_parts else "签到完成"
        
        safe_print(f"[{name}] 签到完成: 成功{len(signed)} 已签{len(already_signed)} 失败{len(failed)}")
        notify_func(config, name, result_msg)
        # 只要有成功或已签的贴吧，就认为本次签到成功
        return len(signed) > 0 or len(already_signed) > 0
        
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
