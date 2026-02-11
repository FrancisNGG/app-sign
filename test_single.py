#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单平台测试脚本 - 用于调试单个平台的签到功能
"""
import yaml
import sys
from modules.notify import push_notification
from modules import right, pcbeta, smzdm, youdao, tieba, acfun, bilibili


def load_config():
    """加载配置文件"""
    with open('config/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_site(site_name):
    """测试指定站点"""
    config = load_config()
    sites = config.get('sites', [])
    
    # 查找指定站点
    target_site = None
    for site in sites:
        if site_name.lower() in site.get('name', '').lower():
            target_site = site
            break
    
    if not target_site:
        print(f"❌ 未找到站点: {site_name}")
        print(f"\n可用的站点:")
        for site in sites:
            print(f"  - {site.get('name')}")
        return
    
    print(f"\n{'='*60}")
    print(f"🧪 测试站点: {target_site.get('name')}")
    print(f"{'='*60}\n")
    
    # 判断站点类型并测试
    name = target_site.get('name', '').lower()
    
    if '远景' in target_site.get('name', '') or 'pcbeta' in name:
        print("📝 使用模块: pcbeta.py (账号密码登录)")
        pcbeta.sign_in(target_site, config, push_notification)
    elif '什么值得买' in target_site.get('name', '') or 'smzdm' in name:
        print("📝 使用模块: smzdm.py (Cookie登录)")
        smzdm.sign_in(target_site, config, push_notification)
    elif '恩山' in target_site.get('name', '') or 'right' in name:
        print("📝 使用模块: right.py (Cookie登录)")
        right.sign_in(target_site, config, push_notification)
    elif '有道' in target_site.get('name', '') or 'youdao' in name:
        print("📝 使用模块: youdao.py (Cookie登录)")
        youdao.sign_in(target_site, config, push_notification)
    elif '贴吧' in target_site.get('name', '') or 'tieba' in name:
        print("📝 使用模块: tieba.py (Cookie登录)")
        tieba.sign_in(target_site, config, push_notification)
    elif 'acfun' in name or 'a站' in target_site.get('name', ''):
        print("📝 使用模块: acfun.py (Cookie登录)")
        acfun.sign_in(target_site, config, push_notification)
    elif '哔哩' in target_site.get('name', '') or 'bilibili' in name or 'b站' in target_site.get('name', ''):
        print("📝 使用模块: bilibili.py (Cookie登录)")
        bilibili.sign_in(target_site, config, push_notification)
    else:
        print("⚠️  未识别的站点类型，尝试使用默认方法...")
        if target_site.get('username'):
            print("检测到账号密码，使用 pcbeta 模块")
            pcbeta.sign_in(target_site, config, push_notification)
        elif target_site.get('cookie'):
            print("检测到 Cookie，使用 right 模块")
            right.sign_in(target_site, config, push_notification)
        else:
            print("❌ 无法确定登录方式")
    
    print(f"\n{'='*60}")
    print("✅ 测试完成")
    print(f"{'='*60}\n")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("🔍 单平台测试工具\n")
        print("用法:")
        print(f"  python {sys.argv[0]} <站点名称关键词>\n")
        print("示例:")
        print(f"  python {sys.argv[0]} 远景")
        print(f"  python {sys.argv[0]} 恩山")
        print(f"  python {sys.argv[0]} 什么值得买\n")
        
        # 显示所有可用站点
        try:
            config = load_config()
            sites = config.get('sites', [])
            if sites:
                print("📋 当前配置的站点:")
                for idx, site in enumerate(sites, 1):
                    print(f"  {idx}. {site.get('name')}")
        except:
            pass
        
        sys.exit(1)
    
    site_name = sys.argv[1]
    test_site(site_name)


if __name__ == "__main__":
    main()
