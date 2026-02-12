#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单站点 Cookie 同步测试脚本
用于测试从 CookieCloud 同步指定站点的 Cookie

使用方法:
    python test_sync_cookie.py 恩山
    python test_sync_cookie.py 什么值得买
"""
import sys
import yaml
from datetime import datetime
from modules.cookie_sync import (
    load_config, 
    save_config, 
    get_cookies_from_cloud, 
    format_cookies_for_domain,
    DOMAIN_MAPPING
)


def sync_single_site(site_name):
    """
    同步指定站点的 Cookie
    
    Args:
        site_name: 站点名称（支持模糊匹配）
    """
    print(f"\n{'='*60}")
    print(f"🧪 单站点 Cookie 同步测试")
    print(f"{'='*60}\n")
    print(f"⏰ 同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 目标站点: {site_name}\n")
    
    # 加载配置
    config, encoding = load_config()
    if not config:
        print("❌ 无法加载配置文件")
        return False
    
    # 检查 CookieCloud 配置
    cookiecloud_config = config.get('cookiecloud', {})
    server_url = cookiecloud_config.get('server', '')
    uuid = cookiecloud_config.get('uuid', '')
    password = cookiecloud_config.get('password', '')
    
    if not server_url or not uuid or not password:
        print("❌ CookieCloud 配置不完整")
        print("   请在 config.yaml 中配置：")
        print("   cookiecloud:")
        print("     server: \"https://your-server.com\"")
        print("     uuid: \"your-uuid\"")
        print("     password: \"your-password\"")
        return False
    
    print(f"📡 CookieCloud 服务器: {server_url}\n")
    
    # 查找目标站点
    sites = config.get('sites', [])
    target_site = None
    
    for site in sites:
        name = site.get('name', '')
        if site_name.lower() in name.lower() or name.lower() in site_name.lower():
            target_site = site
            break
    
    if not target_site:
        print(f"❌ 未找到站点: {site_name}")
        print(f"\n可用的站点:")
        for site in sites:
            name = site.get('name', '')
            if name in DOMAIN_MAPPING:
                print(f"  - {name} (支持 CookieCloud 同步)")
            else:
                print(f"  - {name}")
        return False
    
    site_full_name = target_site.get('name', '')
    
    # 检查站点是否支持 Cookie 同步
    if site_full_name not in DOMAIN_MAPPING:
        print(f"❌ 站点 [{site_full_name}] 不支持 CookieCloud 同步")
        print(f"\n支持同步的站点:")
        for name in DOMAIN_MAPPING.keys():
            print(f"  - {name}")
        return False
    
    domain = DOMAIN_MAPPING[site_full_name]
    print(f"✅ 找到站点: {site_full_name}")
    print(f"   匹配域名: {domain}\n")
    
    # 从 CookieCloud 获取 Cookie
    print(f"{'='*60}")
    print(f"📥 从 CookieCloud 获取 Cookie...")
    print(f"{'='*60}\n")
    
    cookie_data = get_cookies_from_cloud(server_url, uuid, password)
    if not cookie_data:
        print("❌ 获取 Cookie 失败")
        return False
    
    print(f"✅ 成功获取 Cookie 数据")
    print(f"   包含域名数量: {len(cookie_data)}")
    
    # 检查是否有该域名的 Cookie
    domain_cookies = []
    for site_domain, site_cookies in cookie_data.items():
        if domain in site_domain or site_domain in domain:
            domain_cookies.extend(site_cookies)
    
    if not domain_cookies:
        print(f"\n⚠️  警告: 在 CookieCloud 中未找到域名 [{domain}] 的 Cookie")
        print(f"   可能原因:")
        print(f"   1. 该站点的 Cookie 未被 CookieCloud 扩展捕获")
        print(f"   2. Cookie 已过期或被清除")
        print(f"   3. 域名配置不正确")
        
        print(f"\n   CookieCloud 中包含的域名:")
        domains = sorted(cookie_data.keys())
        for d in domains[:10]:  # 只显示前10个
            print(f"     - {d}")
        if len(domains) > 10:
            print(f"     ... 还有 {len(domains) - 10} 个域名")
        return False
    
    print(f"   找到匹配域名的 Cookie: {len(domain_cookies)} 个\n")
    
    # 格式化 Cookie
    new_cookie = format_cookies_for_domain(cookie_data, domain)
    if not new_cookie:
        print(f"❌ 格式化 Cookie 失败")
        return False
    
    # 更新站点 Cookie
    print(f"{'='*60}")
    print(f"💾 更新站点 Cookie")
    print(f"{'='*60}\n")
    
    old_cookie = target_site.get('cookie', '')
    
    if new_cookie == old_cookie:
        print(f"ℹ️  Cookie 无变化，无需更新")
        print(f"   当前 Cookie 长度: {len(old_cookie)} 字符")
    else:
        target_site['cookie'] = new_cookie
        
        print(f"✅ Cookie 已更新")
        print(f"   站点: {site_full_name}")
        print(f"   域名: {domain}")
        print(f"   旧 Cookie 长度: {len(old_cookie)} 字符")
        print(f"   新 Cookie 长度: {len(new_cookie)} 字符")
        
        # 保存配置
        print(f"\n{'='*60}")
        print(f"💾 保存配置文件...")
        save_config(config, 'config/config.yaml', encoding)
        print(f"✅ 配置文件已保存")
    
    print(f"{'='*60}\n")
    print(f"✅ 同步完成！")
    return True


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("❌ 缺少站点名称参数")
        print(f"\n使用方法:")
        print(f"  python test_sync_cookie.py 恩山")
        print(f"  python test_sync_cookie.py 什么值得买")
        print(f"\n支持的站点:")
        for name in DOMAIN_MAPPING.keys():
            print(f"  - {name}")
        sys.exit(1)
    
    site_name = sys.argv[1]
    
    try:
        success = sync_single_site(site_name)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
