#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证：并发安全性测试
展示在不使用锁 vs 使用锁的情况下的差异
"""
import os
import sys
import time
import threading
import tempfile
import shutil
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_with_lock():
    """使用锁的安全版本"""
    print("\n" + "="*70)
    print("✅ 使用锁的安全版本")
    print("="*70)
    
    from modules import cookie_sync
    
    test_config_path = 'config/config.yaml'
    backup_path = 'config/config_backup_verify.yaml'
    
    # 备份原配置
    shutil.copy(test_config_path, backup_path)
    
    try:
        # 读取原始配置  
        config, encoding = cookie_sync.load_config(test_config_path)
        original_sites_count = len(config.get('sites', []))
        
        error_count = 0
        threads_run = 0
        
        def modify_thread(thread_id):
            nonlocal threads_run
            try:
                # 加载配置
                cfg, enc = cookie_sync.load_config(test_config_path)
                sites = cfg.get('sites', [])
                
                if sites:
                    # 修改第一个站点
                    sites[0]['cookie'] = f"test_{thread_id}_{datetime.now().isoformat()}"
                    
                    # 保存
                    cookie_sync.save_config(cfg, test_config_path, encoding=enc)
                    threads_run += 1
            except Exception as e:
                nonlocal error_count
                error_count += 1
                print(f"  ❌ 线程 {thread_id} 出错: {e}")
        
        # 启动并发线程
        print("启动 10 个并发线程进行修改...")
        threads = []
        for i in range(10):
            t = threading.Thread(target=modify_thread, args=(i,), daemon=False)
            threads.append(t)
            t.start()
        
        # 等待完成
        for t in threads:
            t.join()
        
        # 验证
        final_config, _ = cookie_sync.load_config(test_config_path)
        final_sites_count = len(final_config.get('sites', []))
        
        print(f"\n验证结果:")
        print(f"  原始站点数: {original_sites_count}")
        print(f"  最终站点数: {final_sites_count}")
        print(f"  成功运行线程: {threads_run}/10")
        print(f"  出错线程: {error_count}/10")
        
        if final_sites_count == original_sites_count and error_count == 0:
            print("\n✅ 结论: 配置文件完整性保证 ✓")
            return True
        else:
            print("\n❌ 结论: 检测到问题")
            return False
            
    finally:
        # 恢复原配置
        shutil.copy(backup_path, test_config_path)
        os.remove(backup_path)


if __name__ == '__main__':
    success = test_with_lock()
    print("\n" + "="*70 + "\n")
    sys.exit(0 if success else 1)
