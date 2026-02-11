#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CookieCloud Cookie 对比工具
对比从 CookieCloud 获取的原始 Cookie 和配置文件中的 Cookie
"""
import yaml
from modules.sync_cookies import load_config, get_cookies_from_cloud, format_cookies_for_domain, DOMAIN_MAPPING


def main():
    print("\n" + "="*60)
    print("🔍 CookieCloud Cookie 对比分析")
    print("="*60 + "\n")
    
    # 1. 加载配置
    config, encoding = load_config()
    if not config:
        print("❌ 无法加载配置文件")
        return
    
    # 2. 从 CookieCloud 获取最新 Cookie
    cookiecloud_config = config.get('cookiecloud', {})
    server_url = cookiecloud_config.get('server', '')
    uuid = cookiecloud_config.get('uuid', '')
    password = cookiecloud_config.get('password', '')
    
    if not (server_url and uuid and password):
        print("❌ CookieCloud 配置不完整")
        return
    
    print("📡 从 CookieCloud 获取最新 Cookie...\n")
    cookie_data = get_cookies_from_cloud(server_url, uuid, password)
    
    if not cookie_data:
        print("❌ 获取 Cookie 失败")
        return
    
    # 3. 对比每个站点
    print(f"{'='*60}")
    print("📊 站点 Cookie 对比")
    print(f"{'='*60}\n")
    
    sites = config.get('sites', [])
    
    for site in sites:
        site_name = site.get('name', '')
        
        if site_name not in DOMAIN_MAPPING:
            continue
        
        domain = DOMAIN_MAPPING[site_name]
        
        print(f"站点: {site_name}")
        print(f"域名: {domain}")
        print("-" * 60)
        
        # 从 CookieCloud 获取该域名的 Cookie
        cloud_cookie = format_cookies_for_domain(cookie_data, domain)
        
        # 配置文件中的 Cookie
        config_cookie = site.get('cookie', '')
        
        print(f"  CookieCloud Cookie 长度: {len(cloud_cookie)} 字符")
        print(f"  配置文件 Cookie 长度: {len(config_cookie)} 字符")
        
        if cloud_cookie == config_cookie:
            print(f"  ✅ Cookie 完全一致")
        else:
            print(f"  ⚠️  Cookie 不一致")
            
            # 解析 Cookie 对比字段
            def parse_cookie(cookie_str):
                cookies = {}
                for item in cookie_str.split(';'):
                    if '=' in item:
                        k, v = item.strip().split('=', 1)
                        cookies[k] = v
                return cookies
            
            cloud_cookies = parse_cookie(cloud_cookie)
            config_cookies = parse_cookie(config_cookie)
            
            cloud_keys = set(cloud_cookies.keys())
            config_keys = set(config_cookies.keys())
            
            only_in_cloud = cloud_keys - config_keys
            only_in_config = config_keys - cloud_keys
            common_keys = cloud_keys & config_keys
            
            if only_in_cloud:
                print(f"\n  📥 CookieCloud 独有的字段 ({len(only_in_cloud)} 个):")
                for key in sorted(only_in_cloud)[:5]:
                    value = cloud_cookies[key]
                    display = value[:30] + '...' if len(value) > 30 else value
                    print(f"     + {key}={display}")
                if len(only_in_cloud) > 5:
                    print(f"     ... 还有 {len(only_in_cloud) - 5} 个")
            
            if only_in_config:
                print(f"\n  📤 配置文件独有的字段 ({len(only_in_config)} 个):")
                for key in sorted(only_in_config)[:5]:
                    value = config_cookies[key]
                    display = value[:30] + '...' if len(value) > 30 else value
                    print(f"     - {key}={display}")
                if len(only_in_config) > 5:
                    print(f"     ... 还有 {len(only_in_config) - 5} 个")
            
            if common_keys:
                # 检查值是否相同
                different_values = []
                for key in common_keys:
                    if cloud_cookies[key] != config_cookies[key]:
                        different_values.append(key)
                
                if different_values:
                    print(f"\n  📝 值不同的字段 ({len(different_values)} 个):")
                    for key in sorted(different_values)[:3]:
                        cloud_val = cloud_cookies[key]
                        config_val = config_cookies[key]
                        print(f"     • {key}:")
                        print(f"       CookieCloud: {cloud_val[:40]}...")
                        print(f"       配置文件:    {config_val[:40]}...")
                    if len(different_values) > 3:
                        print(f"     ... 还有 {len(different_values) - 3} 个字段值不同")
        
        # 检查关键 Cookie
        print(f"\n  🔑 关键字段检查:")
        
        # 针对不同站点检查不同的关键字段
        if '恩山' in site_name:
            key_fields = ['rHEX_2132_auth', 'rHEX_2132_saltkey']
        elif '什么值得买' in site_name:
            key_fields = ['sess', '__jsluid_s']
        else:
            key_fields = []
        
        if key_fields:
            cloud_cookies = parse_cookie(cloud_cookie)
            config_cookies = parse_cookie(config_cookie)
            
            for field in key_fields:
                in_cloud = field in cloud_cookies
                in_config = field in config_cookies
                
                if in_cloud and in_config:
                    if cloud_cookies[field] == config_cookies[field]:
                        print(f"     ✅ {field}: 两者一致")
                    else:
                        print(f"     ⚠️  {field}: 两者值不同")
                elif in_cloud:
                    print(f"     ⚠️  {field}: 仅在 CookieCloud 中")
                elif in_config:
                    print(f"     ⚠️  {field}: 仅在配置文件中")
                else:
                    print(f"     ❌ {field}: 两者都没有")
        
        print()


if __name__ == '__main__':
    main()
