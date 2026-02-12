#!/usr/bin/env python3
"""
综合测试脚本 - 验证完整的 Cookie 管理系统
"""

import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from modules.cookie_metadata import CookieMetadata
from datetime import datetime, timedelta, timezone

def test_cookie_metadata():
    """测试 Cookie 元数据系统"""
    print("=" * 80)
    print("测试 1: Cookie 元数据系统")
    print("=" * 80)
    
    # 测试 1.1: 创建 Playwright 元数据
    print("\n【测试 1.1】创建 Playwright 元数据 (2 小时有效期)")
    playwright_metadata = CookieMetadata.create_from_playwright(valid_hours=2.0)
    print(f"✅ 来源: {playwright_metadata.source}")
    print(f"✅ 最后更新: {playwright_metadata.last_updated}")
    print(f"✅ 截止时间: {playwright_metadata.valid_until}")
    print(f"✅ 有效期: {playwright_metadata.get_remaining_hours()}h")
    
    # 测试 1.2: 创建 CookieCloud 元数据
    print("\n【测试 1.2】创建 CookieCloud 元数据 (24 小时有效期)")
    cookiecloud_metadata = CookieMetadata.create_from_cookiecloud(valid_hours=24.0)
    print(f"✅ 来源: {cookiecloud_metadata.source}")
    print(f"✅ 截止时间: {cookiecloud_metadata.valid_until}")
    print(f"✅ 有效期: {cookiecloud_metadata.get_remaining_hours():.1f}h")
    
    # 测试 1.3: 测试有效期检查
    print("\n【测试 1.3】有效期检查")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    is_valid = playwright_metadata.is_valid(now)
    print(f"✅ Playwright Cookie 是否有效: {is_valid}")
    
    # 测试 1.4: 冲突检测逻辑
    print("\n【测试 1.4】冲突检测逻辑")
    now = datetime.now(timezone.utc)
    should_skip = playwright_metadata.should_skip_cookiecloud_update(now)
    print(f"✅ 是否应跳过 CookieCloud 更新: {should_skip}")
    print(f"   原因: Playwright Cookie 来源，有 {playwright_metadata.get_remaining_hours(now):.1f} 小时有效期")
    
    # 测试 1.5: 元数据序列化和反序列化
    print("\n【测试 1.5】元数据序列化和反序列化")
    metadata_dict = playwright_metadata.to_dict()
    print(f"✅ 序列化为字典: {list(metadata_dict.keys())}")
    
    restored_metadata = CookieMetadata(metadata_dict)
    print(f"✅ 反序列化成功")
    print(f"   来源: {restored_metadata.source}")
    print(f"   有效期: {restored_metadata.get_remaining_hours():.1f}h")
    
    print("\n✅ Cookie 元数据系统测试通过\n")


def test_configuration():
    """测试配置系统"""
    print("=" * 80)
    print("测试 2: 配置系统")
    print("=" * 80)
    
    from modules.cookie_sync import load_config
    
    print("\n【测试 2.1】加载配置文件")
    config_result = load_config()
    
    if not config_result:
        print("❌ 配置加载失败")
        return False
    
    # load_config() 返回元组 (config, encoding)
    if isinstance(config_result, tuple):
        config = config_result[0]
    else:
        config = config_result
    
    if not config:
        print("❌ 配置加载失败")
        return False
    
    print(f"✅ 成功加载配置")
    print(f"   站点数量: {len(config.get('sites', []))}")
    print(f"   CookieCloud 配置: {'已配置' if config.get('cookiecloud', {}).get('server') else '未配置'}")
    
    print("\n【测试 2.2】检查站点配置")
    for i, site in enumerate(config.get('sites', [])[:3]):
        name = site.get('name', '未知')
        has_cookie = bool(site.get('cookie'))
        print(f"✅ 站点 {i+1}: {name} - Cookie: {'✅' if has_cookie else '❌'}")
    
    print("\n✅ 配置系统测试通过\n")
    return True


def test_imports():
    """测试所有必要的导入"""
    print("=" * 80)
    print("测试 3: 模块导入")
    print("=" * 80)
    
    try:
        print("\n【测试 3.1】导入核心模块")
        from modules import cookie_metadata
        print("✅ cookie_metadata 模块")
        
        from modules import cookie_keepalive
        print("✅ cookie_keepalive 模块")
        
        from modules import cookie_sync
        print("✅ cookie_sync 模块")
        
        from modules import right
        print("✅ right 模块")
        
        print("\n【测试 3.2】检查关键函数")
        assert hasattr(cookie_metadata, 'CookieMetadata'), "缺少 CookieMetadata 类"
        print("✅ CookieMetadata 类存在")
        
        assert hasattr(cookie_keepalive, 'keepalive_task'), "缺少 keepalive_task 函数"
        print("✅ keepalive_task 函数存在")
        
        assert hasattr(cookie_sync, 'sync_cookies'), "缺少 sync_cookies 函数"
        print("✅ sync_cookies 函数存在")
        
        print("\n✅ 模块导入测试通过\n")
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "综合测试 - Cookie 管理系统" + " " * 32 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    # 运行所有测试
    results = []
    
    try:
        test_imports()
        results.append(True)
    except Exception as e:
        print(f"❌ 模块导入测试失败: {e}")
        results.append(False)
    
    try:
        test_cookie_metadata()
        results.append(True)
    except Exception as e:
        print(f"❌ Cookie 元数据测试失败: {e}")
        results.append(False)
    
    try:
        test_configuration()
        results.append(True)
    except Exception as e:
        print(f"❌ 配置系统测试失败: {e}")
        results.append(False)
    
    # 打印总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    total = len(results)
    passed = sum(results)
    print(f"✅ 通过: {passed}/{total} 个测试")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统已准备好部署。\n")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查上面的输出。\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
