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
        # 检查test_playwright_cookie_refresh.py是否存在
        playwright_script = os.path.join(project_root, 'test_playwright_cookie_refresh.py')
        if not os.path.exists(playwright_script):
            return {
                'success': False,
                'cookie_raw': None,
                'message': 'Playwright脚本不存在'
            }
        
        # 动态导入test_playwright_cookie_refresh
        spec = __import__('importlib.util').util.spec_from_file_location(
            "test_playwright_cookie_refresh", 
            playwright_script
        )
        module = __import__('importlib.util').util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 调用refresh_cookie_with_playwright函数
        result = module.refresh_cookie_with_playwright(site)
        
        # 检查返回值是否有效
        if not result or not isinstance(result, dict):
            return {
                'success': False,
                'cookie_raw': None,
                'message': f'Playwright返回无效结果: {type(result).__name__}'
            }
        
        if result.get('success'):
            return {
                'success': True,
                'cookie_raw': result.get('new_cookie'),
                'message': f"刷新成功"
            }
        else:
            return {
                'success': False,
                'cookie_raw': None,
                'message': result.get('message', '刷新失败')
            }
    
    except Exception as e:
        return {
            'success': False,
            'cookie_raw': None,
            'message': f'Playwright刷新异常: {str(e)}'
        }


def sync_with_cookiecloud(site, config):
    """
    使用CookieCloud同步Cookie，带冲突保护
    
    Args:
        site: 站点配置
        config: 全局配置
        
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'skipped': bool  # 是否因冲突而跳过更新
        }
    """
    try:
        from . import sync_cookies
        from . import cookie_metadata
        
        if not sync_cookies.sync_cookies():
            return {
                'success': False,
                'message': 'CookieCloud同步失败',
                'skipped': False
            }
        
        # 重新加载配置以获取最新Cookie
        # load_config() 返回 (config_dict, encoding) 元组
        result = sync_cookies.load_config()
        if result and result[0]:
            new_config = result[0]
            site_name = site.get('name')
            
            for s in new_config.get('sites', []):
                if s.get('name') == site_name:
                    # 检查冲突：是否应该跳过这次更新
                    existing_metadata = s.get('cookie_metadata', {})
                    metadata_obj = cookie_metadata.CookieMetadata(existing_metadata)
                    
                    if metadata_obj.should_skip_cookiecloud_update():
                        # 跳过更新，保护现有更新的 Cookie
                        return {
                            'success': False,
                            'message': f'CookieCloud同步被跳过：现有Cookie更新于{metadata_obj.last_updated}，来源{metadata_obj.source}',
                            'skipped': True
                        }
                    
                    # 允许更新
                    site['cookie'] = s.get('cookie', '')
                    
                    # 更新元数据标记为 cookiecloud 来源
                    new_metadata = cookie_metadata.CookieMetadata.create_from_cookiecloud(valid_hours=24.0)
                    site['cookie_metadata'] = new_metadata.to_dict()
                    
                    return {
                        'success': True,
                        'message': 'CookieCloud同步成功',
                        'skipped': False
                    }
            
            return {
                'success': False,
                'message': '重新加载配置失败',
                'skipped': False
            }
    
    except Exception as e:
        return {
            'success': False,
            'message': f'CookieCloud同步异常: {str(e)}',
            'skipped': False
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
        
        # 创建会话
        session = requests.Session()
        session.cookies.update(cookies)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 访问论坛首页
        response = session.get(base_url, timeout=15, allow_redirects=True)
        
        # HTTP 200 表示有效，其他表示失效
        valid = (response.status_code == 200)
        
        return {
            'valid': valid,
            'status_code': response.status_code,
            'message': f'HTTP {response.status_code}'
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
    
    if not analysis['valid']:
        # Cookie已过期，立即刷新
        return datetime.datetime.now()
    
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
                from . import sync_cookies
                from . import cookie_metadata
                
                # 重新加载config
                config_result = sync_cookies.load_config()
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
                    sync_cookies.save_config(saved_config, encoding=encoding)
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
        
        # ==================== 步骤3.5: 尝试CookieCloud同步 ====================
        print(f"\n[步骤3.5] 尝试使用CookieCloud同步Cookie")
        sync_result = sync_with_cookiecloud(site, config)
        
        if sync_result['success']:
            print(f"  状态: ✅ CookieCloud同步成功")
            print(f"  消息: {sync_result['message']}")
            
            cookie_raw = site.get('cookie', '')
            cookie_dict = parse_cookie_string(cookie_raw)
            next_exec_time = calculate_next_refresh_time(cookie_dict)
            
            steps.append(f"CookieCloud同步成功")
            steps.append(f"下次执行时间: {next_exec_time.strftime('%H:%M:%S')}")
            
            # 验证同步后的Cookie
            print(f"\n[步骤4] 验证同步后的Cookie有效性")
            verify_result = verify_cookie_validity(site, config)
            
            if verify_result['valid']:
                print(f"  状态: ✅ Cookie有效")
                print(f"  HTTP: {verify_result['status_code']}")
                steps.append("同步后的Cookie验证成功")
                
                # 保存同步后的Cookie和元数据到config
                try:
                    from . import sync_cookies as sc
                    
                    config_result = sc.load_config()
                    if config_result and config_result[0]:
                        saved_config, encoding = config_result
                        for s in saved_config.get('sites', []):
                            if s.get('name') == name:
                                s['cookie'] = cookie_raw
                                # Cookie 来源已被标记为 cookiecloud（在 sync_with_cookiecloud 中）
                                break
                        sc.save_config(saved_config, encoding=encoding)
                        print(f"  已保存到config")
                except Exception as e:
                    print(f"  保存出错: {e}")
                
                print(f"\n{'='*60}")
                print(f"[成功] {name} Cookie保活成功")
                print(f"  下次执行: {next_exec_time.strftime('%H:%M:%S')}")
                print(f"{'='*60}\n")
                
                return {
                    'success': True,
                    'next_exec_time': next_exec_time,
                    'steps': steps,
                    'message': 'Cookie保活成功（CookieCloud同步）'
                }
            else:
                print(f"  状态: ❌ Cookie仍无效")
                print(f"  HTTP: {verify_result['status_code']}")
                steps.append(f"同步后验证失败: {verify_result['message']}")
        elif sync_result.get('skipped'):
            # CookieCloud 被跳过（做了保护）
            print(f"  状态: ⏭️ CookieCloud同步被跳过")
            print(f"  原因: {sync_result['message']}")
            steps.append(f"CookieCloud被跳过（保护现有Cookie）")
        else:
            print(f"  状态: ❌ CookieCloud同步失败")
            print(f"  原因: {sync_result['message']}")
            steps.append(f"CookieCloud同步失败: {sync_result['message']}")
    
    # ==================== 步骤5: 都失败了，加入重试队列 ====================
    print(f"\n[步骤5] Cookie保活失败，返回重试信息")
    
    # 计算1小时后的重试时间
    retry_time = datetime.datetime.now() + datetime.timedelta(hours=1)
    
    print(f"  状态: ❌ 失败")
    print(f"  下次重试: {retry_time.strftime('%H:%M:%S')}")
    print(f"  建议: 检查CookieCloud配置或手动在浏览器中访问论坛")
    
    steps.append(f"保活失败，{retry_time.strftime('%H:%M:%S')}后重试")
    steps.append("建议检查CookieCloud配置")
    
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
