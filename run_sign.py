# -*- coding: utf-8 -*-
"""
统一签到脚本 - 主入口
支持多个论坛/网站的自动签到
"""
import yaml
import time
import random
import threading
from datetime import datetime, timedelta
from modules.notify import push_notification
from modules import right, pcbeta, smzdm, youdao, tieba, acfun, bilibili, sync_cookies

# 全局任务表
daily_tasks = []
tasks_lock = threading.Lock()
last_schedule_date = None


def load_config():
    """加载配置文件"""
    for enc in ['utf-8', 'gbk']:
        try:
            with open('config/config.yaml', 'r', encoding=enc) as f:
                return yaml.safe_load(f)
        except:
            continue
    return None


def detect_site_type(site):
    """
    自动检测站点类型
    
    根据配置自动判断使用哪个模块：
    - 如果有 username 和 password，优先使用账号密码登录
    - 如果只有 cookie，使用 Cookie 方式
    - 根据 base_url 或 name 判断具体平台
    
    Args:
        site: 站点配置字典
        
    Returns:
        模块对象或 None
    """
    name = site.get('name', '').lower()
    base_url = site.get('base_url', '').lower()
    has_username = bool(site.get('username'))
    has_cookie = bool(site.get('cookie'))
    
    # 远景论坛 - 优先账号密码
    if 'pcbeta' in name or 'pcbeta.com' in base_url or '远景' in site.get('name', ''):
        if has_username:
            return pcbeta
        else:
            print(f"[{site.get('name')}] 远景论坛需要账号密码登录")
            return None
    
    # 什么值得买 - 使用 Cookie
    if 'smzdm' in name or 'smzdm.com' in base_url or '什么值得买' in site.get('name', ''):
        if has_cookie:
            return smzdm
        else:
            print(f"[{site.get('name')}] 什么值得买需要 Cookie")
            return None
    
    # 恩山论坛 - 使用 Cookie
    if 'right.com.cn' in base_url or '恩山' in site.get('name', ''):
        if has_cookie:
            return right
        else:
            print(f"[{site.get('name')}] 恩山论坛需要 Cookie")
            return None
    
    # 有道云笔记 - 使用 Cookie
    if 'youdao' in name or 'note.youdao.com' in base_url or '有道' in site.get('name', ''):
        if has_cookie:
            return youdao
        else:
            print(f"[{site.get('name')}] 有道云笔记需要 Cookie")
            return None
    
    # 百度贴吧 - 使用 Cookie
    if 'tieba' in name or 'tieba.baidu.com' in base_url or '贴吧' in site.get('name', ''):
        if has_cookie:
            return tieba
        else:
            print(f"[{site.get('name')}] 百度贴吧需要 Cookie")
            return None
    
    # AcFun - 使用 Cookie
    if 'acfun' in name or 'acfun.cn' in base_url or 'ac' in name or 'a站' in site.get('name', ''):
        if has_cookie:
            return acfun
        else:
            print(f"[{site.get('name')}] AcFun需要 Cookie")
            return None
    
    # 哔哩哔哩 - 使用 Cookie
    if 'bilibili' in name or 'bilibili.com' in base_url or 'b站' in site.get('name', ''):
        if has_cookie:
            return bilibili
        else:
            print(f"[{site.get('name')}] 哔哩哔哩需要 Cookie")
            return None
    
    # 默认：根据配置判断
    if has_username:
        # 有账号密码，尝试通用账号密码登录（目前支持远景）
        print(f"[{site.get('name')}] 检测到账号密码，但未识别平台类型")
        return None
    elif has_cookie:
        # 有 Cookie，尝试通用 Cookie 登录（默认恩山）
        return right
    else:
        print(f"[{site.get('name')}] 配置不完整：缺少登录凭证")
        return None


def process_site(site, config):
    """
    处理单个站点的签到
    
    Args:
        site: 站点配置
        config: 全局配置
    """
    name = site.get('name', '未知站点')
    
    # 自动检测站点类型
    module = detect_site_type(site)
    
    if not module:
        print(f"[{name}] 跳过：无法识别站点类型或配置不完整")
        return
    
    # 执行签到
    try:
        module.sign_in(site, config, push_notification)
    except Exception as e:
        print(f"[{name}] 执行失败: {e}")
        push_notification(config, name, f"执行失败: {str(e)}")


def generate_daily_tasks(config):
    """
    生成当天的任务表
    
    根据配置的 run_time 和 random_range 为每个站点生成实际执行时间
    考虑随机延迟，避免所有站点同时签到
    
    Args:
        config: 配置字典
        
    Returns:
        任务列表，每个任务包含 site、scheduled_time、executed 字段
    """
    sites = config.get('sites', [])
    tasks = []
    
    print(f"\n{'='*60}")
    print(f"生成任务表 - {datetime.now().strftime('%Y年%m月%d日')}")
    print(f"{'='*60}")
    
    for site in sites:
        run_time = site.get('run_time', '09:00:00')  # 默认09:00:00
        random_range = site.get('random_range', 0)  # 默认无随机延迟
        
        # 解析基础时间 (HH:MM:SS)
        try:
            time_parts = run_time.split(':')
            if len(time_parts) == 2:
                # 兼容旧格式 HH:MM，自动补充秒数
                hour, minute = map(int, time_parts)
                second = 0
            else:
                hour, minute, second = map(int, time_parts)
            
            base_seconds = hour * 3600 + minute * 60 + second
            
            # 添加随机延迟（random_range 单位为分钟）
            if random_range > 0:
                offset_seconds = random.randint(0, random_range * 60)
                actual_seconds = base_seconds + offset_seconds
            else:
                actual_seconds = base_seconds
            
            # 确保不超过一天的秒数
            actual_seconds = actual_seconds % 86400
            
            # 转换回时间格式
            h = actual_seconds // 3600
            m = (actual_seconds % 3600) // 60
            s = actual_seconds % 60
            scheduled_time = f"{h:02d}:{m:02d}:{s:02d}"
            
            tasks.append({
                'site': site,
                'scheduled_time': scheduled_time,
                'executed': False
            })
            
            # 输出任务信息
            if random_range > 0:
                offset_min = (actual_seconds - base_seconds) // 60
                print(f"  {site.get('name', '未知')}")
                print(f"    基准时间: {run_time}")
                print(f"    随机延迟: {offset_min} 分钟")
                print(f"    执行时间: {scheduled_time}")
            else:
                print(f"  {site.get('name', '未知')}: {scheduled_time}")
                
        except Exception as e:
            print(f"  [错误] {site.get('name', '未知')}: 时间格式错误 - {e}")
            continue
    
    # 按执行时间排序
    tasks.sort(key=lambda x: x['scheduled_time'])
    
    print(f"{'='*60}")
    print(f"共生成 {len(tasks)} 个任务")
    print(f"{'='*60}\n")
    
    return tasks


def execute_task(task, config):
    """
    在独立线程中执行单个任务
    
    Args:
        task: 任务字典
        config: 配置字典
    """
    with tasks_lock:
        if task['executed']:
            return
        task['executed'] = True
    
    site = task['site']
    name = site.get('name', '未知站点')
    scheduled_time = task['scheduled_time']
    
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 执行任务")
    print(f"站点: {name}")
    print(f"预定时间: {scheduled_time}")
    print(f"{'='*60}")
    
    process_site(site, config)
    
    print(f"{'='*60}")
    print(f"任务完成: {name}")
    print(f"{'='*60}\n")


def check_and_regenerate_tasks(config):
    """
    检查是否需要重新生成任务表
    
    每天0点或首次启动时生成任务表
    
    Args:
        config: 配置字典
        
    Returns:
        bool: 是否重新生成了任务表
    """
    global daily_tasks, last_schedule_date
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # 首次启动或日期变更时重新生成任务表
    if last_schedule_date != current_date:
        with tasks_lock:
            daily_tasks = generate_daily_tasks(config)
            last_schedule_date = current_date
        return True
    
    return False

def main():
    """
    主函数 - 基于任务表的定时签到调度器
    
    工作流程：
    1. 启动时立即生成当天的任务表
    2. 每天0点自动重新生成任务表
    3. 主循环每秒检查是否有任务需要执行
    4. 使用线程执行任务，避免阻塞
    5. 已执行的任务不会重复执行
    """
    print(f"\n{'='*60}")
    print(f"自动签到服务启动")
    print(f"启动时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 加载配置
    config = load_config()
    if not config:
        print("[错误] 无法加载配置文件")
        return
    
    # 首次启动时尝试同步 Cookie
    cookiecloud_enabled = False
    try:
        # 检查是否配置了 CookieCloud
        cookiecloud_config = config.get('cookiecloud', {})
        if (cookiecloud_config.get('server') and 
            cookiecloud_config.get('uuid') and 
            cookiecloud_config.get('password')):
            
            print("🔄 检测到 CookieCloud 配置，正在同步 Cookie...\n")
            
            # 立即同步一次
            if sync_cookies.sync_cookies():
                # 重新加载配置以获取最新的 Cookie
                config = load_config()
                cookiecloud_enabled = True
                
                # 启动定期同步任务
                sync_interval = cookiecloud_config.get('sync_time', 60)
                print(f"\n🔄 启动 Cookie 定期同步任务...\n")
                sync_cookies.start_sync_task(config, sync_interval)
            else:
                print("⚠️  首次 Cookie 同步失败，跳过定期同步\n")
        else:
            print("ℹ️  未配置 CookieCloud，跳过 Cookie 同步\n")
    except Exception as e:
        print(f"⚠️  Cookie 同步失败: {e}")
        import traceback
        traceback.print_exc()
        print("   继续使用现有配置...\n")
    
    # 首次启动时生成任务表
    check_and_regenerate_tasks(config)
    
    print(f"开始监控任务执行...\n")
    
    last_check_second = None
    
    while True:
        try:
            # 获取当前时间
            now = datetime.now()
            current_time = now.strftime('%H:%M:%S')
            current_date = now.strftime('%Y-%m-%d')
            
            # 避免同一秒内重复检查
            if current_time == last_check_second:
                time.sleep(0.3)
                continue
            
            last_check_second = current_time
            
            # 重新加载配置（以便支持动态修改配置）
            config = load_config()
            if not config:
                print(f"[{now.strftime('%H:%M:%S')}] 警告: 配置文件加载失败")
                time.sleep(5)
                continue
            
            # 检查是否需要重新生成任务表（每天0点）
            if check_and_regenerate_tasks(config):
                print(f"[{now.strftime('%H:%M:%S')}] 任务表已更新\n")
            
            # 检查是否有任务需要执行
            with tasks_lock:
                tasks_to_execute = [
                    task for task in daily_tasks 
                    if task['scheduled_time'] == current_time and not task['executed']
                ]
            
            # 执行到达时间的任务
            if tasks_to_execute:
                print(f"\n[{now.strftime('%H:%M:%S')}] 检测到 {len(tasks_to_execute)} 个任务到达执行时间")
                
                # 如果多个任务时间相同，使用线程并行执行
                threads = []
                for task in tasks_to_execute:
                    t = threading.Thread(
                        target=execute_task, 
                        args=(task, config),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
                    
                    # 如果任务时间不同但在同一秒内，添加小延迟避免请求过于集中
                    if len(tasks_to_execute) > 1:
                        time.sleep(0.5)
                
                # 等待所有任务完成
                for t in threads:
                    t.join()
                
                print(f"[{now.strftime('%H:%M:%S')}] 本轮任务执行完成\n")
            
            # 每秒检查一次
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print(f"\n{'='*60}")
            print(f"用户中断，程序退出")
            print(f"退出时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
            print(f"{'='*60}\n")
            break
        except Exception as e:
            print(f"[错误] 主循环异常: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    main()