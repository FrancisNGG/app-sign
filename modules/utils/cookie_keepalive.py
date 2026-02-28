# -*- coding: utf-8 -*-
"""
Cookie 保活模块 - 优先使用Playwright刷新，失败时使用CookieCloud同步
"""
import os
import sys
import re
import time
import datetime
import json
from urllib.parse import urljoin

# 添加项目根目录到 sys.path，以便导入模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def parse_cookie_string(cookie_raw):
    """
    解析Cookie字符串为字典
    
    Args:
        cookie_raw: Cookie字符串
        
    Returns:
        dict: Cookie字典
    """
    cookies = {}
    for item in cookie_raw.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            cookies[k] = v
    return cookies


def has_right_auth_cookie(cookie_dict):
    """判断是否包含恩山登录态关键cookie（*_auth）"""
    if not isinstance(cookie_dict, dict):
        return False
    for key, value in cookie_dict.items():
        if str(key).lower().endswith('_auth') and str(value).strip():
            return True
    return False


def page_indicates_logged_out(html_text):
    """判断页面内容是否显示未登录状态"""
    if not html_text:
        return True
    text = str(html_text).lower()
    keywords = [
        '请先登录', '先登录', '未登录', '登录后',
        'member.php?mod=logging', 'action=login', '登录'
    ]
    return any(keyword in text for keyword in keywords)


def extract_cookie_timestamps(cookie_dict):
    """
    从Cookie中提取所有时间戳
    
    Args:
        cookie_dict: Cookie字典
        
    Returns:
        dict: {参数名: 时间戳}
    """
    timestamps = {}
    for key, value in cookie_dict.items():
        # 查找UNIX时间戳（10位数字，以1开头）
        ts_matches = re.findall(r'\b1\d{9}\b', str(value))
        if ts_matches:
            timestamps[key] = int(ts_matches[0])
    return timestamps


def analyze_cookie_validity(cookie_dict):
    """
    分析Cookie的剩余有效期
    
    Args:
        cookie_dict: Cookie字典
        
    Returns:
        dict: {
            'valid': bool,  # 是否有效
            'max_timestamp': int,  # 最大时间戳
            'remaining_seconds': int,  # 剩余秒数
            'remaining_hours': float,  # 剩余小时数
            'max_key': str,  # 时间戳对应的参数名
            'expires_at': str  # 过期时间（格式 HH:MM:SS）
        }
    """
    timestamps = extract_cookie_timestamps(cookie_dict)
    
    if not timestamps:
        return {
            'valid': False,
            'max_timestamp': 0,
            'remaining_seconds': 0,
            'remaining_hours': 0,
            'max_key': None,
            'expires_at': 'Unknown'
        }
    
    # 找最新的时间戳（即最近的过期时间）
    max_timestamp = max(timestamps.values())
    max_key = [k for k, v in timestamps.items() if v == max_timestamp][0]
    
    now = time.time()
    remaining_seconds = int(max_timestamp - now)
    remaining_hours = remaining_seconds / 3600
    
    # 计算过期时间
    if remaining_seconds > 0:
        expires_at = datetime.datetime.fromtimestamp(max_timestamp).strftime('%H:%M:%S')
        valid = True
    else:
        expires_at = (datetime.datetime.now() - datetime.timedelta(seconds=abs(remaining_seconds))).strftime('%H:%M:%S')
        valid = False
    
    return {
        'valid': valid,
        'max_timestamp': max_timestamp,
        'remaining_seconds': remaining_seconds,
        'remaining_hours': remaining_hours,
        'max_key': max_key,
        'expires_at': expires_at
    }


def refresh_cookie_with_playwright(site, config):
    """
    使用Playwright刷新Cookie
    
    策略：使用现有的有效Cookie进行访问
    这样就不会触发反爬，浏览器会直接获得更新的Cookie
    
    Args:
        site: 站点配置
        config: 全局配置
        
    Returns:
        dict: {
            'success': bool,
            'cookie_raw': str,  # 新Cookie（如果成功）
            'message': str
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            'success': False,
            'cookie_raw': None,
            'message': 'Playwright未安装'
        }
    
    name = site.get('name', '恩山无线论坛')
    url = site.get('base_url', 'https://www.right.com.cn/forum/')
    old_cookie_str = site.get('cookie', '')
    
    if not old_cookie_str:
        return {
            'success': False,
            'cookie_raw': None,
            'message': f'{name} 缺少Cookie配置'
        }
    
    try:
        # 解析现有Cookie
        old_cookies = parse_cookie_string(old_cookie_str)
        
        # 转换为Playwright格式
        cookie_list = []
        for name_key, value in old_cookies.items():
            cookie_list.append({
                'name': name_key,
                'value': value,
                'domain': '.right.com.cn',
                'path': '/'
            })
        
        # 启动Playwright浏览器
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # 注入现有Cookie
            context.add_cookies(cookie_list)
            
            # 创建页面并访问论坛
            page = context.new_page()
            response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待页面加载完成（load 超时不影响 Cookie 刷新）
            try:
                page.wait_for_load_state('load', timeout=10000)
            except Exception:
                pass
            
            # 让JavaScript执行完成
            try:
                page.evaluate('''
                    new Promise(resolve => {
                        let waitCount = 0;
                        const waitInterval = setInterval(() => {
                            waitCount++;
                            if (waitCount > 5) {
                                clearInterval(waitInterval);
                                resolve(true);
                            }
                        }, 100);
                    });
                ''')
            except:
                pass
            
            # 提取新Cookie
            new_cookies = context.cookies()
            new_cookie_str = '; '.join([f'{c["name"]}={c["value"]}' for c in new_cookies])
            
            # 关闭浏览器
            context.close()
            browser.close()
            
            new_cookie_dict = parse_cookie_string(new_cookie_str)

            # 关键校验：必须拿到登录态cookie，否则即使能打开页面也不算成功
            if new_cookie_str and has_right_auth_cookie(new_cookie_dict):
                return {
                    'success': True,
                    'cookie_raw': new_cookie_str,
                    'message': '刷新成功'
                }
            else:
                return {
                    'success': False,
                    'cookie_raw': None,
                    'message': 'Playwright未获取到登录态Cookie（缺少_auth）'
                }
    
    except Exception as e:
        return {
            'success': False,
            'cookie_raw': None,
            'message': f'Playwright刷新异常: {str(e)}'
        }



def verify_cookie_validity(site, config):
    """
    验证Cookie是否有效
    
    通过访问论坛首页来验证
    
    Args:
        site: 站点配置
        config: 全局配置
        
    Returns:
        dict: {
            'valid': bool,
            'status_code': int,
            'message': str
        }
    """
    try:
        import requests
        from . import get_user_agent
        
        base_url = site.get('base_url', 'https://www.right.com.cn/forum/')
        cookie_raw = site.get('cookie', '')
        
        if not cookie_raw:
            return {
                'valid': False,
                'status_code': 0,
                'message': '缺少Cookie'
            }
        
        # 解析Cookie
        cookies = parse_cookie_string(cookie_raw)

        # 先检查是否包含登录态cookie
        if not has_right_auth_cookie(cookies):
            return {
                'valid': False,
                'status_code': 0,
                'message': '缺少登录态Cookie（*_auth）'
            }
        
        # 创建会话
        session = requests.Session()
        session.cookies.update(cookies)
        session.headers.update({
            'User-Agent': get_user_agent(config)
        })
        
        # 访问论坛首页
        response = session.get(base_url, timeout=15, allow_redirects=True)
        
        # HTTP 200 且页面不是未登录状态才算有效
        valid = (response.status_code == 200 and not page_indicates_logged_out(response.text))
        
        return {
            'valid': valid,
            'status_code': response.status_code,
            'message': f'HTTP {response.status_code}' if valid else '页面显示未登录'
        }
    
    except Exception as e:
        return {
            'valid': False,
            'status_code': 0,
            'message': f'验证异常: {str(e)}'
        }


def calculate_next_refresh_time(cookie_dict):
    """
    计算下一次刷新时间：Cookie有效期结束后2分钟
    
    Args:
        cookie_dict: Cookie字典
        
    Returns:
        datetime.datetime: 下次刷新的时间
    """
    analysis = analyze_cookie_validity(cookie_dict)

    # 如果缺少登录态Cookie，尽快触发保活
    if not has_right_auth_cookie(cookie_dict):
        return datetime.datetime.now() + datetime.timedelta(seconds=30)

    # 无时间戳或已过期时，尽快触发保活，避免等待过久
    if not analysis['valid']:
        return datetime.datetime.now() + datetime.timedelta(minutes=2)
    
    # Cookie有效期结束时间 + 2分钟
    expires_timestamp = analysis['max_timestamp']
    next_refresh_timestamp = expires_timestamp + 120  # 2分钟 = 120秒
    
    return datetime.datetime.fromtimestamp(next_refresh_timestamp)


def keepalive_task(site, config):
    """
    Cookie保活任务
    
    工作流程：
    1. 分析当前Cookie的有效期
    2. 计算下次执行时间（有效期+2分钟）
    3. 优先使用Playwright刷新Cookie
    4. 如果Playwright失败，使用CookieCloud同步
    5. 验证新Cookie是否有效
    6. 如果仍无效，加入重试队列（1小时后）
    
    Args:
        site: 站点配置
        config: 全局配置
        
    Returns:
        dict: {
            'success': bool,
            'next_exec_time': datetime.datetime,
            'steps': list,  # 执行步骤记录
            'message': str
        }
    """
    name = site.get('name', '恩山无线论坛')
    cookie_raw = site.get('cookie', '')
    
    steps = []
    
    print(f"\n{'='*60}")
    print(f"[Cookie保活] {name} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # ==================== 步骤1: 分析当前Cookie ====================
    cookie_dict = parse_cookie_string(cookie_raw)
    analysis = analyze_cookie_validity(cookie_dict)
    
    print(f"\n[步骤1] 分析当前Cookie有效期")
    if analysis['valid']:
        print(f"  状态: ✅ 有效")
        print(f"  最新参数: {analysis['max_key']}")
        print(f"  剩余时间: {analysis['remaining_hours']:.1f} 小时")
        print(f"  过期时间: {analysis['expires_at']}")
        steps.append(f"Cookie有效，剩余{analysis['remaining_hours']:.1f}小时")
    else:
        print(f"  状态: ❌ 已过期")
        print(f"  过期于: {analysis['expires_at']}")
        steps.append(f"Cookie已过期，立即刷新")
    
    # ==================== 步骤2: 计算下次执行时间 ====================
    next_exec_time = calculate_next_refresh_time(cookie_dict)
    print(f"\n[步骤2] 计算下次执行时间")
    print(f"  预定时间: {next_exec_time.strftime('%Y-%m-%d %H:%M:%S')}")
    steps.append(f"下次执行时间: {next_exec_time.strftime('%H:%M:%S')}")
    
    # ==================== 步骤3: 优先使用Playwright刷新 ====================
    print(f"\n[步骤3] 尝试使用Playwright刷新Cookie")
    playwright_result = refresh_cookie_with_playwright(site, config)
    
    if playwright_result['success']:
        print(f"  状态: ✅ Playwright刷新成功")
        print(f"  消息: {playwright_result['message']}")
        
        cookie_raw = playwright_result['cookie_raw']
        site['cookie'] = cookie_raw
        
        # 重新计算下次执行时间
        cookie_dict = parse_cookie_string(cookie_raw)
        next_exec_time = calculate_next_refresh_time(cookie_dict)
        
        steps.append(f"Playwright刷新成功，新Cookie：{len(cookie_raw)} characters")
        steps.append(f"下次执行时间更新为: {next_exec_time.strftime('%H:%M:%S')}")
        
        # ==================== 步骤4: 验证新Cookie ====================
        print(f"\n[步骤4] 验证新Cookie有效性")
        verify_result = verify_cookie_validity(site, config)
        
        if verify_result['valid']:
            print(f"  状态: ✅ Cookie有效")
            print(f"  HTTP: {verify_result['status_code']}")
            steps.append("新Cookie验证成功")
            
            # 保存新Cookie到config
            try:
                from . import cookie_sync
                from . import cookie_metadata
                
                # 重新加载config
                config_result = cookie_sync.load_config()
                if config_result and config_result[0]:
                    saved_config, encoding = config_result
                    # 更新site的cookie和metadata
                    for s in saved_config.get('sites', []):
                        if s.get('name') == name:
                            s['cookie'] = cookie_raw
                            # 创建并保存元数据
                            metadata = cookie_metadata.CookieMetadata.create_from_playwright(valid_hours=2.0)
                            s['cookie_metadata'] = metadata.to_dict()
                            break
                    # 保存回文件
                    cookie_sync.save_config(saved_config, encoding=encoding)
                    print(f"  已保存到config（包括元数据）")
                    steps.append("新Cookie已保存（含元数据）")
                else:
                    print(f"  保存失败: 无法加载配置")
            except Exception as e:
                print(f"  保存出错: {e}")
                steps.append(f"保存出错: {e}")
            
            print(f"\n{'='*60}")
            print(f"[成功] {name} Cookie保活成功")
            print(f"  下次执行: {next_exec_time.strftime('%H:%M:%S')}")
            print(f"{'='*60}\n")
            
            return {
                'success': True,
                'next_exec_time': next_exec_time,
                'steps': steps,
                'message': 'Cookie保活成功（Playwright）'
            }
        else:
            print(f"  状态: ❌ Cookie仍无效")
            print(f"  HTTP: {verify_result['status_code']}")
            steps.append(f"新Cookie验证失败: {verify_result['message']}")
            # 继续到步骤5（重试）
    else:
        print(f"  状态: ❌ Playwright刷新失败")
        print(f"  原因: {playwright_result['message']}")
        steps.append(f"Playwright刷新失败: {playwright_result['message']}")
    
    # ==================== 步骤4: 都失败了，加入重试队列 ====================
    print(f"\n[步骤4] Cookie保活失败，返回重试信息")
    
    # 计算1小时后的重试时间
    retry_time = datetime.datetime.now() + datetime.timedelta(hours=1)
    
    print(f"  状态: ❌ 失败")
    print(f"  下次重试: {retry_time.strftime('%H:%M:%S')}")
    print(f"  建议: 检查CookieCloud配置或手动在浏览器中访问论坛")
    
    steps.append(f"保活失败，{retry_time.strftime('%H:%M:%S')}后重试")
    steps.append("建议手动在浏览器中访问站点重新登录")
    
    print(f"\n{'='*60}")
    print(f"[失败] {name} Cookie保活失败，已加入重试队列")
    print(f"  重试时间: {retry_time.strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")
    
    return {
        'success': False,
        'next_exec_time': retry_time,  # 1小时后重试
        'steps': steps,
        'message': 'Cookie保活失败，1小时后重试'
    }
