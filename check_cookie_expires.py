#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 https_ydclearance Cookie 的过期时间和类型
"""
import yaml
import datetime

# 读取配置获取Cookie
with open('config/config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    
for site in config['sites']:
    if '恩山' in site.get('name', ''):
        cookie = site.get('cookie', '')
        
        # 解析Cookie
        cookies = {}
        for item in cookie.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                cookies[k] = v
        
        # 检查https_ydclearance
        if 'https_ydclearance' in cookies:
            value = cookies['https_ydclearance']
            print('=' * 60)
            print('https_ydclearance Cookie 分析')
            print('=' * 60)
            print(f'\n完整值: {value}')
            
            # 检查是否包含时间戳（通常在最后）
            parts = value.split('-')
            print(f'\n分段数量: {len(parts)}')
            
            if len(parts) >= 4:
                try:
                    timestamp = int(parts[-1])
                    dt = datetime.datetime.fromtimestamp(timestamp)
                    now = datetime.datetime.now()
                    diff = dt - now
                    
                    print(f'\n时间戳: {timestamp}')
                    print(f'过期时间: {dt.strftime("%Y-%m-%d %H:%M:%S")}')
                    print(f'当前时间: {now.strftime("%Y-%m-%d %H:%M:%S")}')
                    
                    if diff.total_seconds() > 0:
                        hours = diff.total_seconds() / 3600
                        minutes = diff.total_seconds() / 60
                        print(f'\n✅ 状态: 有效')
                        print(f'剩余有效期: {hours:.1f} 小时 ({minutes:.0f} 分钟)')
                        
                        if hours < 1:
                            print('⚠️ 警告: 即将过期！')
                    else:
                        hours = abs(diff.total_seconds() / 3600)
                        print(f'\n❌ 状态: 已过期')
                        print(f'过期时长: {hours:.1f} 小时前')
                except Exception as e:
                    print(f'\n无法解析时间戳: {e}')
            
            print('\n' + '=' * 60)
            print('Cookie 类型分析')
            print('=' * 60)
            print('\nhttps_ydclearance 特征:')
            print('  1. 这是5秒盾验证后生成的Cookie')
            print('  2. Cookie值中包含过期时间戳')
            print('  3. 通常有效期约为 2-4 小时')
            print('  4. 即使关闭浏览器，Cookie也会保留（持久Cookie）')
            print('  5. 但过期后需要重新通过5秒盾验证')
            
            print('\n建议:')
            print('  • CookieCloud每60分钟同步可覆盖大部分有效期')
            print('  • 如果签到在Cookie过期时运行，会失败')
            print('  • 建议在每天访问恩山论坛后的2小时内运行签到')
            print('  • 或在浏览器保持恩山标签页打开状态')
        else:
            print('❌ 配置中没有找到 https_ydclearance Cookie')
