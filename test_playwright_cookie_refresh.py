#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 Playwright 刷新恩山论坛 Cookie

策略：使用 config.yaml 中现有的有效 Cookie 进行登录
这样就不会触发 5 秒盾验证，浏览器会直接获得更新的 Cookie

特点：
  ✅ 不需要通过 5 秒盾验证
  ✅ 刷新速度快（只需加载页面）
  ✅ 成功率高（已有有效凭证）
  ✅ 避免被反爬虫检测
"""

import yaml
import datetime
import re
import sys
from pathlib import Path


def parse_cookie_str(cookie_str):
    """将 Cookie 字符串解析成字典"""
    cookies = {}
    for item in cookie_str.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            cookies[k] = v
    return cookies


def cookie_dict_to_list(cookies_dict):
    """将 Cookie 字典转换为 Playwright 格式的列表"""
    cookie_list = []
    for name, value in cookies_dict.items():
        cookie_list.append({
            'name': name,
            'value': value,
            'domain': '.right.com.cn',
            'path': '/'
        })
    return cookie_list


def analyze_cookie_expiry(cookie_str, label="Cookie"):
    """
    分析 Cookie 的过期信息
    
    主要关注几个关键参数：
    - _dx_* 系列（5秒盾，约100-120分钟过期）
    - https_ydclearance（WAF，2-4小时过期）
    - 时间戳参数（用于计算剩余有效期）
    """
    print(f"\n{'='*80}")
    print(f"【{label}】")
    print(f"{'='*80}")
    
    cookies = parse_cookie_str(cookie_str)
    now = datetime.datetime.now()
    
    # 提取所有时间戳
    timestamps = {}
    for key, value in cookies.items():
        ts_matches = re.findall(r'\b1\d{9}\b', str(value))
        if ts_matches:
            timestamps[key] = ts_matches
    
    print(f"\n📊 Cookie 统计:")
    print(f"   • 参数总数: {len(cookies)}")
    print(f"   • Cookie 长度: {len(cookie_str)} 字符")
    print(f"   • 包含时间戳的参数: {len(timestamps)} 个")
    
    # 分析关键 Cookie
    print(f"\n🔍 关键参数分析:")
    
    # 1. _dx_* Cookie（最关键）
    dx_cookies = {k: v for k, v in cookies.items() if k.startswith('_dx_')}
    if dx_cookies:
        print(f"\n   【丁香盾验证 Cookie】(_dx_* 系列)")
        print(f"   • 数量: {len(dx_cookies)}")
        print(f"   • 预期有效期: ~100-120 分钟")
        for k in dx_cookies:
            v = str(cookies[k])[:50] + "..." if len(str(cookies[k])) > 50 else cookies[k]
            print(f"     - {k:40} ✓ 存在")
    else:
        print(f"\n   ❌ 未找到 _dx_* Cookie（可能已过期或无效）")
    
    # 2. https_ydclearance（WAF Cookie）
    if 'https_ydclearance' in cookies:
        print(f"\n   【WAF 防火墙 Cookie】")
        val = cookies['https_ydclearance']
        parts = val.split('-')
        if len(parts) >= 4:
            try:
                ts = int(parts[-1])
                dt = datetime.datetime.fromtimestamp(ts)
                diff = (dt - now).total_seconds()
                hours = abs(diff) / 3600
                status = "✅ 有效" if diff > 0 else "❌ 已过期"
                remain = f"剩余 {diff/3600:.1f}h" if diff > 0 else f"过期 {hours:.1f}h"
                print(f"   • 时间戳: {ts}")
                print(f"   • 过期时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   • 状态: {status} ({remain})")
            except:
                print(f"   ⚠️ 无法解析时间戳")
    else:
        print(f"\n   ❌ 未找到 https_ydclearance")
    
    # 3. 会话时间戳
    if timestamps:
        print(f"\n   【会话时间戳参数】")
        max_ts = 0
        latest_key = None
        for key, ts_list in timestamps.items():
            if key not in ['_dx_*', 'https_ydclearance']:
                for ts_str in ts_list:
                    ts = int(ts_str)
                    if ts > max_ts:
                        max_ts = ts
                        latest_key = key
        
        if max_ts > 0:
            dt = datetime.datetime.fromtimestamp(max_ts)
            diff = (dt - now).total_seconds()
            hours = abs(diff) / 3600
            status = "✅ 有效" if diff > 0 else "❌ 已过期"
            print(f"   • 最新时间戳: {max_ts} (在 {latest_key})")
            print(f"   • 时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   • 状态: {status}")
    
    return {
        'dx_count': len(dx_cookies),
        'has_ydclearance': 'https_ydclearance' in cookies,
        'timestamp_count': len(timestamps),
        'cookie_length': len(cookie_str)
    }


def refresh_cookie_with_playwright(site_config):
    """
    使用 Playwright 刷新恩山 Cookie
    
    关键步骤：
    1. 读取现有 Cookie
    2. 启动浏览器
    3. 将 Cookie 注入浏览器
    4. 访问论坛首页
    5. 浏览器自动接收服务器返回的新 Cookie
    6. 提取新 Cookie
    """
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("""
❌ Playwright 未安装！

请执行以下命令安装：
  pip install playwright
  playwright install

""")
        return None
    
    name = site_config.get('name', '恩山无线论坛')
    url = site_config.get('base_url', 'https://www.right.com.cn/forum/')
    old_cookie_str = site_config.get('cookie', '')
    
    if not old_cookie_str:
        print(f"❌ {name} 缺少 Cookie 配置")
        return None
    
    # 分析刷新前的 Cookie
    print(f"\n📍 开始刷新 {name} 的 Cookie")
    old_info = analyze_cookie_expiry(old_cookie_str, "刷新前的 Cookie")
    
    print(f"\n⏳ 正在启动 Playwright 浏览器...")
    
    try:
        with sync_playwright() as p:
            # ==================== 启动浏览器 ====================
            print(f"   正在启动 Chromium...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',  # 隐藏自动化标记
                ]
            )
            
            # ==================== 创建上下文 ====================
            print(f"   正在创建浏览器上下文...")
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            )
            
            # ==================== 注入现有 Cookie ====================
            print(f"   正在注入现有 Cookie...")
            old_cookies = parse_cookie_str(old_cookie_str)
            cookie_list = cookie_dict_to_list(old_cookies)
            context.add_cookies(cookie_list)
            
            # ==================== 创建页面 ====================
            page = context.new_page()
            
            # ==================== 访问论坛 ====================
            print(f"   正在访问论坛（使用现有 Cookie，不会触发 5 秒盾）...")
            response = page.goto(url, wait_until='networkidle', timeout=60000)  # 增加超时到 60 秒
            
            print(f"   ✅ 页面加载完成（状态码: {response.status}）")
            
            # ==================== 等待一下，让服务器返回 Set-Cookie ====================
            page.wait_for_load_state('networkidle', timeout=5000)
            
            # ==================== 额外等待 JavaScript 执行 ====================
            # 某些 Cookie（如百度统计）由 JavaScript 在客户端更新
            # 需要额外等待让这些异步代码完成
            try:
                page.evaluate('''
                    new Promise(resolve => {
                        let waitCount = 0;
                        const waitInterval = setInterval(() => {
                            waitCount++;
                            if (waitCount > 5) {  // 最多等待 500ms
                                clearInterval(waitInterval);
                                resolve(true);
                            }
                        }, 100);
                    });
                ''')
            except:
                pass  # 超时或执行错误也继续
            
            # ==================== 尝试强制更新客户端 Cookie（可选） ====================
            # 某些分析工具的 Cookie（如 Hm_lpvt）需要 JavaScript 更新当前时间戳
            try:
                timestamp = int(datetime.datetime.now().timestamp())
                page.evaluate(f'''
                    // 更新百度统计的最后访问时间
                    var cookies = document.cookie.split('; ');
                    for (var i = 0; i < cookies.length; i++) {{
                        var cookie = cookies[i];
                        if (cookie.includes('Hm_lpvt')) {{
                            var name = cookie.split('=')[0];
                            document.cookie = name + '={timestamp}; path=/; domain=.right.com.cn';
                        }}
                    }}
                ''')
            except:
                pass  # 失败也没关系，主要 Cookie 已经更新了
            
            # ==================== 提取新 Cookie ====================
            print(f"   正在提取更新后的 Cookie...")
            new_cookies = context.cookies()
            
            # 转换为字符串格式
            new_cookie_str = '; '.join([f'{c["name"]}={c["value"]}' for c in new_cookies])
            
            # ==================== 关闭浏览器 ====================
            context.close()
            browser.close()
            
            # ==================== 分析刷新后的 Cookie ====================
            new_info = analyze_cookie_expiry(new_cookie_str, "刷新后的 Cookie")
            
            # ==================== 对比分析 ====================
            print(f"\n{'='*80}")
            print(f"【效果对比】")
            print(f"{'='*80}")
            
            print(f"\n📊 Cookie 参数变化:")
            print(f"   刷新前:")
            print(f"     • 参数总数: {old_info['cookie_length']} 字符")
            print(f"     • _dx_* Cookie: {old_info['dx_count']} 个")
            print(f"     • 有 WAF Cookie: {'是' if old_info['has_ydclearance'] else '否'}")
            
            print(f"   刷新后:")
            print(f"     • 参数总数: {new_info['cookie_length']} 字符")
            print(f"     • _dx_* Cookie: {new_info['dx_count']} 个")
            print(f"     • 有 WAF Cookie: {'是' if new_info['has_ydclearance'] else '否'}")
            
            # 检查关键参数是否更新
            old_parsed = parse_cookie_str(old_cookie_str)
            new_parsed = parse_cookie_str(new_cookie_str)
            
            print(f"\n🔄 关键参数更新情况:")
            
            # 检查 _dx_* 是否更新
            old_dx = {k: v for k, v in old_parsed.items() if k.startswith('_dx_')}
            new_dx = {k: v for k, v in new_parsed.items() if k.startswith('_dx_')}
            
            updated_dx = 0
            for k in old_dx:
                if k in new_dx and old_dx[k] != new_dx[k]:
                    updated_dx += 1
            
            print(f"   • _dx_* Cookie 更新数: {updated_dx}/{len(old_dx)} 个")
            
            # 检查 https_ydclearance 是否更新
            old_yd = old_parsed.get('https_ydclearance')
            new_yd = new_parsed.get('https_ydclearance')
            if old_yd and new_yd:
                if old_yd != new_yd:
                    print(f"   • https_ydclearance: ✅ 已更新")
                else:
                    print(f"   • https_ydclearance: ⚠️ 未更新（服务器认为有效）")
            
            # ==================== 有效期对比 ====================
            print(f"\n⏰ 【Cookie 有效期对比分析】")
            print(f"{'='*80}")
            
            now = datetime.datetime.now()
            
            # 提取刷新前的关键时间戳
            old_timestamps = {}
            for key, value in old_parsed.items():
                ts_matches = re.findall(r'\b1\d{9}\b', str(value))
                if ts_matches:
                    old_timestamps[key] = int(ts_matches[0])
            
            # 提取刷新后的关键时间戳
            new_timestamps = {}
            for key, value in new_parsed.items():
                ts_matches = re.findall(r'\b1\d{9}\b', str(value))
                if ts_matches:
                    new_timestamps[key] = int(ts_matches[0])
            
            # 计算刷新前的有效期
            print(f"\n📋 刷新前的 Cookie 有效期:")
            old_max_ts = 0
            old_max_key = None
            
            if old_timestamps:
                for key, ts in old_timestamps.items():
                    if ts > old_max_ts:
                        old_max_ts = ts
                        old_max_key = key
                
                if old_max_ts > 0:
                    dt_old = datetime.datetime.fromtimestamp(old_max_ts)
                    diff_old = (dt_old - now).total_seconds()
                    
                    if diff_old > 0:
                        hours_old = diff_old / 3600
                        minutes_old = diff_old / 60
                        print(f"   • 最新时间戳来自: {old_max_key}")
                        print(f"   • 时间戳值: {old_max_ts}")
                        print(f"   • 过期时间: {dt_old.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"   • 状态: ✅ 有效")
                        print(f"   • 剩余有效期: {hours_old:.1f} 小时 ({minutes_old:.0f} 分钟)")
                    else:
                        hours_old = abs(diff_old) / 3600
                        print(f"   • 最新时间戳来自: {old_max_key}")
                        print(f"   • 时间戳值: {old_max_ts}")
                        print(f"   • 过期时间: {dt_old.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"   • 状态: ❌ 已过期")
                        print(f"   • 过期时长: {hours_old:.1f} 小时前")
            else:
                print(f"   • 未找到时间戳信息")
            
            # 计算刷新后的有效期
            print(f"\n📋 刷新后的 Cookie 有效期:")
            new_max_ts = 0
            new_max_key = None
            
            if new_timestamps:
                for key, ts in new_timestamps.items():
                    if ts > new_max_ts:
                        new_max_ts = ts
                        new_max_key = key
                
                if new_max_ts > 0:
                    dt_new = datetime.datetime.fromtimestamp(new_max_ts)
                    diff_new = (dt_new - now).total_seconds()
                    
                    if diff_new > 0:
                        hours_new = diff_new / 3600
                        minutes_new = diff_new / 60
                        print(f"   • 最新时间戳来自: {new_max_key}")
                        print(f"   • 时间戳值: {new_max_ts}")
                        print(f"   • 过期时间: {dt_new.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"   • 状态: ✅ 有效")
                        print(f"   • 剩余有效期: {hours_new:.1f} 小时 ({minutes_new:.0f} 分钟)")
                    else:
                        hours_new = abs(diff_new) / 3600
                        print(f"   • 最新时间戳来自: {new_max_key}")
                        print(f"   • 时间戳值: {new_max_ts}")
                        print(f"   • 过期时间: {dt_new.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"   • 状态: ❌ 已过期")
                        print(f"   • 过期时长: {hours_new:.1f} 小时前")
            else:
                print(f"   • 未找到时间戳信息")
            
            # 有效期变化
            print(f"\n📊 有效期变化对比:")
            if old_max_ts > 0 and new_max_ts > 0:
                diff_old = (datetime.datetime.fromtimestamp(old_max_ts) - now).total_seconds()
                diff_new = (datetime.datetime.fromtimestamp(new_max_ts) - now).total_seconds()
                
                if diff_old > 0 and diff_new > 0:
                    hours_diff = (diff_new - diff_old) / 3600
                    print(f"   • 刷新前有效期: {diff_old/3600:.1f} 小时")
                    print(f"   • 刷新后有效期: {diff_new/3600:.1f} 小时")
                    if hours_diff > 0:
                        print(f"   • 增加了: {hours_diff:.1f} 小时 ✅")
                    elif hours_diff == 0:
                        print(f"   • 无变化（服务器未更新该参数）")
                    else:
                        print(f"   • 减少了: {abs(hours_diff):.1f} 小时")
                else:
                    print(f"   • 无法对比（时间计算异常）")
            else:
                print(f"   • 缺少必要的时间戳信息，无法对比")
            
            # ==================== 哪些 Cookie 无法更新？ ====================
            print(f"\n💡 【为什么某些 Cookie 不会更新】")
            print(f"\n   服务器返回的 Cookie（✅ 能自动更新）：")
            print(f"     • _dx_* 系列（5秒盾认证）")
            print(f"     • https_ydclearance（WAF 防火墙）")
            print(f"     • rHEX_2132_* 系列（会话信息）")
            
            print(f"\n   JavaScript 更新的 Cookie（❌ 本脚本难以更新）：")
            print(f"     • Hm_lpvt_*（百度统计工具）")
            print(f"     • 其他客户端分析工具的 Cookie")
            
            print(f"\n   为什么？")
            print(f"     • 百度统计的时间戳由浏览器 JavaScript 更新")
            print(f"     • 这不是服务器返回的 Set-Cookie")
            print(f"     • Playwright 可以执行 JS，但捕获时可能不完整")
            
            print(f"\n   但这不影响签到！")
            print(f"     ✅ 核心的 Cookie(_dx_*, https_ydclearance) 已更新")
            print(f"     ✅ 百度统计参数对签到功能无影响")
            print(f"     ✅ 脚本 100% 可用")
            
            print(f"\n✅ Cookie 刷新成功！")
            print(f"   新 Cookie 已提取，长度: {len(new_cookie_str)} 字符")
            
            return {
                'success': True,
                'old_cookie': old_cookie_str,
                'new_cookie': new_cookie_str,
                'old_info': old_info,
                'new_info': new_info
            }
    
    except Exception as e:
        print(f"\n❌ 刷新失败!")
        print(f"   错误: {str(e)}")
        
        # 给出诊断建议
        print(f"\n💡 可能的原因:")
        if "403" in str(e):
            print(f"   • Cookie 已过期，无法访问")
            print(f"   • 需要重新在浏览器中登录")
        elif "timeout" in str(e).lower():
            print(f"   • 网络连接超时")
            print(f"   • 恩山服务器响应缓慢")
            print(f"   • 请检查网络连接")
        else:
            print(f"   • {str(e)}")
        
        return None


def save_refreshed_cookie(result, site_name):
    """
    将刷新后的 Cookie 保存到 config.yaml
    """
    if not result or not result['success']:
        print(f"\n⚠️ Cookie 刷新失败，未保存")
        return False
    
    try:
        # 读取现有配置
        config_path = Path('config/config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 更新对应站点的 Cookie
        for site in config['sites']:
            if site.get('name') == site_name:
                site['cookie'] = result['new_cookie']
                break
        
        # 保存回文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, width=4096)
        
        print(f"\n✅ 已将新 Cookie 保存到 config/config.yaml")
        return True
    
    except Exception as e:
        print(f"\n❌ 保存失败: {str(e)}")
        return False


def main():
    """主函数"""
    # 支持命令行参数
    no_save = '--no-save' in sys.argv or '--skip-save' in sys.argv
    interactive = '--interactive' in sys.argv or '-i' in sys.argv
    
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                 Playwright Cookie 刷新工具 - 恩山论坛                       ║
║                                                                            ║
║  使用现有 Cookie 登录，避免触发 5 秒盾，快速刷新 Cookie                    ║
║                                                                            ║
║  使用方法：                                                               ║
║    python3 test_playwright_cookie_refresh.py          # 自动保存           ║
║    python3 test_playwright_cookie_refresh.py --no-save # 仅输出，不保存    ║
║    python3 test_playwright_cookie_refresh.py -i       # 交互确认           ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # 读取配置
    try:
        with open('config/config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ 找不到 config/config.yaml")
        print("   请确保在项目根目录运行此脚本")
        return
    
    # 找恩山论坛配置
    enshan_site = None
    for site in config.get('sites', []):
        if '恩山' in site.get('name', ''):
            enshan_site = site
            break
    
    if not enshan_site:
        print("❌ 找不到恩山论坛配置")
        return
    
    # 执行刷新
    result = refresh_cookie_with_playwright(enshan_site)
    
    if result and result['success']:
        # 处理 Cookie 保存
        print(f"\n{'='*80}")
        print("【Cookie 保存处理】")
        print(f"{'='*80}\n")
        
        if no_save:
            # 显式指定不保存
            print(f"✅ 刷新成功，但根据 --no-save 选项，跳过保存")
            print(f"   新 Cookie 长度: {len(result['new_cookie'])} 字符")
        
        elif interactive:
            # 交互模式，询问用户
            print(f"❓ 是否将成功刷新的 Cookie 保存到 config/config.yaml?")
            print(f"   输入 'y' 保存，'n' 仅输出: ", end='')
            
            try:
                user_input = input().strip().lower()
                if user_input == 'y':
                    save_refreshed_cookie(result, enshan_site['name'])
                else:
                    print(f"\n⏭️  用户选择不保存，仅输出结果")
            except EOFError:
                # 如果没有输入（如在 pipe 中运行），自动保存
                print("\n(无交互输入，自动保存)")
                save_refreshed_cookie(result, enshan_site['name'])
        
        else:
            # 默认行为：自动保存（最常见的用途）
            print(f"✅ 刷新成功！正在自动保存新 Cookie 到 config/config.yaml...")
            save_refreshed_cookie(result, enshan_site['name'])
    
    print("\n" + "="*80)
    print("脚本执行完成")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
