#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发保存配置测试
测试save_config函数是否能正确处理并发写入
"""
import os
import sys
import time
import threading
import shutil
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import cookie_sync


def test_concurrent_save():
    """并发保存测试：多个线程同时修改配置"""
    print("="*70)
    print("并发保存配置测试")
    print("="*70)
    
    # 创建测试配置文件
    test_config_path = 'config/test_config.yaml'
    backup_config_path = 'config/test_config_backup.yaml'
    
    # 备份原配置
    original_config_path = 'config/config.yaml'
    shutil.copy(original_config_path, backup_config_path)
    
    try:
        # 读取原始配置
        config, encoding = cookie_sync.load_config(original_config_path)
        if not config:
            print("❌ 无法读取配置文件")
            return False
        
        # 获取所有站点
        sites = config.get('sites', [])
        print(f"\n找到 {len(sites)} 个站点")
        for site in sites:
            print(f"  - {site.get('name')}: {len(site.get('cookie', ''))} 字符")
        
        # 创建修改函数
        def modify_and_save(thread_id, site_index):
            """在指定站点添加修改标记"""
            thread_name = f"线程-{thread_id}"
            print(f"\n[{thread_name}] 开始修改站点 {site_index}")
            
            # 加载配置
            cfg, enc = cookie_sync.load_config(original_config_path)
            if not cfg:
                print(f"[{thread_name}] ❌ 加载配置失败")
                return False
            
            sites_list = cfg.get('sites', [])
            if site_index >= len(sites_list):
                print(f"[{thread_name}] ❌ 站点索引超出范围")
                return False
            
            # 修改当前站点的cookie（若为空则直接设置，否则附加标记）
            site = sites_list[site_index]
            old_cookie = site.get('cookie', '')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            
            # 如果cookie为空，设置为标记；否则附加标记
            if old_cookie:
                new_cookie = f"{old_cookie}[{thread_name}_{timestamp}]"
            else:
                new_cookie = f"[MARKER_{thread_name}_{timestamp}]"
            
            site['cookie'] = new_cookie
            
            # 模拟耗时操作（增加并发问题概率）
            time.sleep(0.01)
            
            # 保存配置
            print(f"[{thread_name}] 保存配置...")
            cookie_sync.save_config(cfg, original_config_path, encoding=enc)
            print(f"[{thread_name}] ✅ 配置已保存")
            return True
        
        # 创建多个线程进行并发修改
        num_threads = 8
        threads = []
        
        print(f"\n启动 {num_threads} 个并发线程进行修改...")
        for i in range(num_threads):
            site_idx = i % len(sites)
            t = threading.Thread(
                target=modify_and_save,
                args=(i+1, site_idx),
                daemon=False
            )
            threads.append(t)
            t.start()
            time.sleep(0.05)  # 略微错开启动时间
        
        # 等待所有线程完成
        print("\n等待所有线程完成...")
        for t in threads:
            t.join()
        
        print("\n所有线程完成！")
        
        # 验证配置文件的完整性
        print("\n" + "="*70)
        print("验证配置文件完整性")
        print("="*70)
        
        final_config, final_enc = cookie_sync.load_config(original_config_path)
        if not final_config:
            print("❌ 无法读取最终配置")
            return False
        
        final_sites = final_config.get('sites', [])
        
        # 检查站点数量是否一致
        if len(final_sites) != len(sites):
            print(f"❌ 站点数量不匹配！原始: {len(sites)}, 最终: {len(final_sites)}")
            return False
        
        print(f"✅ 站点数量正确: {len(final_sites)}")
        
        # 检查每个站点是否都有内容
        all_valid = True
        for i, site in enumerate(final_sites):
            name = site.get('name', f'Site-{i}')
            cookie = site.get('cookie', '')
            
            # 某些站点（如远景论坛）使用账号密码，不需要cookie
            username = site.get('username', '')
            if not cookie and not username:
                print(f"❌ {name}: Cookie和username都为空！")
                all_valid = False
            elif not cookie and username:
                # 使用账号密码的站点，无需Cookie
                print(f"ℹ️  {name}: 使用账号密码登录")
            elif cookie:
                # 统计修改次数（查找[线程-或MARKER标记）
                mod_count = cookie.count('[线程-') + cookie.count('[MARKER_')
                if mod_count > 0:
                    print(f"✅ {name}: 有 {mod_count} 个修改标记 ({len(cookie)} 字符)")
                else:
                    print(f"⚠️  {name}: 未找到修改标记 ({len(cookie)} 字符)")
        
        if not all_valid:
            print("\n❌ 配置文件完整性检查失败！")
            return False
        
        print("\n✅ 配置文件完整性检查通过！")
        return True
        
    finally:
        # 恢复原始配置
        shutil.copy(backup_config_path, original_config_path)
        if os.path.exists(backup_config_path):
            os.remove(backup_config_path)
        print("\n✅ 已恢复原始配置")


if __name__ == '__main__':
    success = test_concurrent_save()
    sys.exit(0 if success else 1)
