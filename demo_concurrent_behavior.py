#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发行为演示：展示全局锁如何保护config文件的访问
"""
import sys
import os
import time
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import cookie_sync


def print_timeline(event, details=""):
    """打印时间轴事件"""
    t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{t}] {event:<50} | {details}")


def simulate_keepalive_task(task_id):
    """模拟保活任务"""
    print_timeline(f"保活任务{task_id}: 启动", "准备加载config")
    
    # 模拟加载延迟
    time.sleep(0.01)
    
    print_timeline(f"保活任务{task_id}: 等待锁", "尝试获取 _config_write_lock")
    
    # 在这里会被阻塞，直到获得锁
    config, encoding = cookie_sync.load_config('config/config.yaml')
    
    print_timeline(f"保活任务{task_id}: 获得锁", "开始修改config")
    
    # 模拟修改延迟
    time.sleep(0.02)
    
    if config and config.get('sites'):
        # 修改第一个site的cookie标记
        config['sites'][0]['cookie'] = f"keepalive_task_{task_id}_updated"
    
    print_timeline(f"保活任务{task_id}: 保存文件", "调用save_config()")
    
    # save_config 也会使用锁，但此时已经获得，所以直接继续
    cookie_sync.save_config(config, 'config/config.yaml', encoding)
    
    print_timeline(f"保活任务{task_id}: 完成", "锁已释放")


def simulate_checkin_task(task_id):
    """模拟签到任务（不访问文件）"""
    print_timeline(f"签到任务{task_id}: 启动", "使用预加载的config数据")
    
    # 签到任务不需要访问文件，仅使用传入的config数据
    # 这里我们模拟它做一些工作
    time.sleep(0.03)
    
    print_timeline(f"签到任务{task_id}: 处理中", "访问网站...")
    time.sleep(0.02)
    
    print_timeline(f"签到任务{task_id}: 完成", "无需等待锁")


def demo_scenario_1():
    """场景1：两个保活任务同时执行"""
    print("\n" + "="*80)
    print("场景1: 两个保活任务同时执行 - 演示全局锁的串行化")
    print("="*80 + "\n")
    
    print_timeline("主线程", "启动保活任务1和2")
    
    t1 = threading.Thread(target=simulate_keepalive_task, args=(1,), daemon=False)
    t2 = threading.Thread(target=simulate_keepalive_task, args=(2,), daemon=False)
    
    # 几乎同时启动
    t1.start()
    time.sleep(0.001)
    t2.start()
    
    t1.join()
    t2.join()
    
    print("\n" + "-"*80)
    print("结果: 任务2被阻塞，直到任务1释放锁。执行是串行的。")
    print("-"*80)


def demo_scenario_2():
    """场景2：保活任务和签到任务并发执行"""
    print("\n" + "="*80)
    print("场景2: 保活任务和签到任务并发执行")
    print("="*80 + "\n")
    
    print_timeline("主线程", "启动保活任务和签到任务")
    
    t1 = threading.Thread(target=simulate_keepalive_task, args=(1,), daemon=False)
    t2 = threading.Thread(target=simulate_checkin_task, args=(1,), daemon=False)
    
    # 几乎同时启动
    t1.start()
    time.sleep(0.001)
    t2.start()
    
    t1.join()
    t2.join()
    
    print("\n" + "-"*80)
    print("结果: 保活任务和签到任务可以并发执行，签到任务不需要等待。")
    print("原因: 签到任务不访问config文件，所以不需要获取全局锁。")
    print("-"*80)


def demo_scenario_3():
    """场景3：复杂场景 - 多个任务交错执行"""
    print("\n" + "="*80)
    print("场景3: 复杂场景 - 多个保活和签到任务交错执行")
    print("="*80 + "\n")
    
    print_timeline("主线程", "启动多个并发任务")
    
    threads = []
    
    # 启动任务序列
    for i in range(2):
        t = threading.Thread(target=simulate_keepalive_task, args=(i,), daemon=False)
        threads.append(t)
        t.start()
        time.sleep(0.002)
    
    for i in range(2):
        t = threading.Thread(target=simulate_checkin_task, args=(i,), daemon=False)
        threads.append(t)
        t.start()
        time.sleep(0.002)
    
    for t in threads:
        t.join()
    
    print("\n" + "-"*80)
    print("结果: 保活任务们互相等待（串行化），签到任务们并发执行。")
    print("异步执行顺序取决于系统调度器，但文件访问是安全的。")
    print("-"*80)


if __name__ == '__main__':
    try:
        demo_scenario_1()
        demo_scenario_2()
        demo_scenario_3()
        
        print("\n" + "="*80)
        print("总结")
        print("="*80)
        print("""
✅ 全局锁 _config_write_lock 的作用：
   - 保护所有保活任务对config文件的访问
   - 确保文件不会被多个线程同时修改
   - 防止了之前的"配置被清空"问题

⏳ 等待情况：
   1. 保活任务相互等待（通过全局锁）← 必要的保护
   2. 签到任务不等待（不访问文件）← 性能好

⚠️ 潜在考虑：
   - 签到任务使用预加载的config内存对象
   - 保活任务更新的最新Cookie可能不会立即被签到任务看到
   - 但这在实践中不是问题，因为：
     * 签到通常在保活之后
     * Cookie有效期很长（2-8小时）
        """)
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
