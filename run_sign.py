# -*- coding: utf-8 -*-
"""
统一签到脚本 - 主入口
支持多个论坛/网站的自动签到
包含错误重试机制
Cookie保活由独立的 cookie_keepalive 模块管理
"""
import sys
import io

# 确保 stdout 和 stderr 使用 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import argparse
import yaml
import time
import random
import threading
from datetime import datetime, timedelta
from modules.notify import push_notification
from modules import right, pcbeta, smzdm, youdao, tieba, acfun, bilibili, cookie_sync, cookie_keepalive, cookie_metadata
import os
import logging

# 全局任务表
daily_tasks = []
tasks_lock = threading.Lock()
last_schedule_date = None
# 重试任务队列
retry_queue = []
retry_queue_lock = threading.Lock()
# Cookie 保活队列
keepalive_queue = []
keepalive_queue_lock = threading.Lock()
# 初始化 Cookie 保活任务（用来追踪下次执行时间）
keepalive_tasks = {}  # {site_name: {'next_exec_time': datetime, 'site': site}}


def cleanup_old_logs(logs_dir, days=7):
    """
    清理指定天数前的日志文件
    
    Args:
        logs_dir: 日志目录
        days: 保留天数（默认7天）
    """
    try:
        now_timestamp = time.time()
        cutoff_timestamp = now_timestamp - (days * 86400)  # days * 24 * 60 * 60
        
        for filename in os.listdir(logs_dir):
            if filename.startswith('sign_') and filename.endswith('.log'):
                file_path = os.path.join(logs_dir, filename)
                file_mtime = os.path.getmtime(file_path)
                
                # 如果文件修改时间早于cutoff时间，删除
                if file_mtime < cutoff_timestamp:
                    try:
                        os.remove(file_path)
                        logging.info(f"已删除过期日志: {filename}")
                    except Exception as e:
                        logging.warning(f"删除日志失败 {filename}: {e}")
    except Exception as e:
        logging.warning(f"清理日志目录失败: {e}")


def setup_logging():
    """
    初始化日志系统 - 按天轮转
    - 每天0点自动创建新日志文件
    - 自动删除7天前的日志
    - 同时输出到文件和 stdout
    """
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)
    
    # 生成日志文件名（按日期格式，便于辨识和管理）
    # 格式: sign_YYYYMMDD.log
    current_date = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(logs_dir, f"sign_{current_date}.log")
    
    # 配置日志格式
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 创建 logger
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(logging.DEBUG)
    
    # 文件处理器（使用普通 FileHandler，配合外部日期更新逻辑）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Tee 类：同时写入日志文件和 stdout
    class TeeOutput:
        def __init__(self, name, original_stream, log_file_path, logs_directory):
            self.name = name
            self.terminal = original_stream
            self.log_file_path = log_file_path
            self.logs_directory = logs_directory
            self.log_file = open(log_file_path, 'a', encoding='utf-8', buffering=1)
            self.current_date = datetime.now().strftime("%Y%m%d")
        
        def _check_date_change(self):
            """检查日期是否变更，如果变更则切换日志文件"""
            new_date = datetime.now().strftime("%Y%m%d")
            if new_date != self.current_date:
                self.current_date = new_date
                
                # 关闭旧日志文件
                self.log_file.close()
                
                # 打开新日志文件
                self.log_file_path = os.path.join(self.logs_directory, f"sign_{new_date}.log")
                self.log_file = open(self.log_file_path, 'a', encoding='utf-8', buffering=1)
                
                # 清理7天前的日志
                cleanup_old_logs(self.logs_directory, days=7)
                
                # 记录日志滚转信息
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_file.write(f"{timestamp} [INFO] 日志文件已切换至新日期\n")
                self.log_file.flush()
        
        def write(self, message):
            self._check_date_change()
            self.terminal.write(message)
            self.terminal.flush()
            self.log_file.write(message)
            self.log_file.flush()
        
        def flush(self):
            self.terminal.flush()
            self.log_file.flush()
        
        def isatty(self):
            return self.terminal.isatty()
    
    # 重定向 stdout 和 stderr
    if not isinstance(sys.stdout, TeeOutput):
        sys.stdout = TeeOutput('stdout', sys.__stdout__, log_file, logs_dir)
    if not isinstance(sys.stderr, TeeOutput):
        sys.stderr = TeeOutput('stderr', sys.__stderr__, log_file, logs_dir)
    
    # 启动时清理一次过期日志
    cleanup_old_logs(logs_dir, days=7)
    
    logging.info(f"日志系统初始化完成，日志文件: {log_file}")
    return log_file


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
        
    Returns:
        bool: 签到是否成功
    """
    name = site.get('name', '未知站点')
    
    # 自动检测站点类型
    module = detect_site_type(site)
    
    if not module:
        print(f"[{name}] 跳过：无法识别站点类型或配置不完整")
        return False
    
    # 执行签到
    try:
        result = module.sign_in(site, config, push_notification)
        return result if result is not None else False
    except Exception as e:
        print(f"[{name}] 执行失败: {e}")
        push_notification(config, name, f"执行失败: {str(e)}")
        return False


def get_retry_config(config):
    """
    获取重试配置
    
    Args:
        config: 全局配置
        
    Returns:
        dict: 重试配置（enabled, max_retries, retry_delay_hours）
    """
    retry_config = config.get('retry', {})
    return {
        'enabled': retry_config.get('enabled', True),
        'max_retries': retry_config.get('max_retries', 3),
        'retry_delay_hours': retry_config.get('retry_delay_hours', 1)
    }


def should_retry(task, config):
    """
    判断任务是否应该重试
    
    Args:
        task: 任务字典
        config: 全局配置
        
    Returns:
        bool: 是否应该重试
    """
    retry_config = get_retry_config(config)
    if not retry_config['enabled']:
        return False
    
    retry_count = task.get('retry_count', 0)
    max_retries = retry_config['max_retries']
    
    return retry_count < max_retries


def add_retry_task(task, config):
    """
    将失败的任务添加到重试队列
    
    Args:
        task: 失败的任务
        config: 全局配置
    """
    retry_config = get_retry_config(config)
    if not retry_config['enabled']:
        return
    
    # 复制任务并增加重试计数
    retry_task = dict(task)
    retry_task['retry_count'] = task.get('retry_count', 0) + 1
    retry_task['executed'] = False  # 重置执行标记
    
    # 计算重试时间（当前时间 +延迟）
    now = datetime.now()
    retry_time = now + timedelta(hours=retry_config['retry_delay_hours'])
    retry_task['scheduled_time'] = retry_time.strftime('%H:%M:%S')
    retry_task['original_time'] = task.get('scheduled_time', 'unknown')
    
    # 加入重试队列
    with retry_queue_lock:
        retry_queue.append(retry_task)
    
    retry_count = retry_task['retry_count']
    name = task['site'].get('name', '未知站点')
    retry_delay = retry_config['retry_delay_hours']
    
    print(f"\n{'='*60}")
    print(f"[重试] {name}")
    print(f"原始时间: {retry_task['original_time']}")
    print(f"重试次数: {retry_count}/{retry_config['max_retries']}")
    print(f"延迟时间: {retry_delay} 小时")
    print(f"预定重试时间: {retry_task['scheduled_time']}")
    print(f"{'='*60}\n")
    
    # 通知重试信息
    retry_msg = f"签到失败，已加入重试队列（第{retry_count}次重试，延迟{retry_delay}小时）"
    push_notification(config, name, retry_msg)


def generate_daily_tasks(config):
    """
    生成当天的任务表
    
    根据配置的 run_time 和 random_range 为每个站点生成实际执行时间
    考虑随机延迟，避免所有站点同时签到
    
    Args:
        config: 配置字典
        
    Returns:
        任务列表，每个任务包含 site、scheduled_time、executed、retry_count 字段
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
                'executed': False,
                'retry_count': 0  # 新增重试计数
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
    
    # 从最新的config中查询该site的最新配置（确保使用最新的Cookie）
    site_name = task['site'].get('name', '未知站点')
    site = None
    for s in config.get('sites', []):
        if s.get('name') == site_name:
            site = s
            break
    
    if not site:
        # 如果在新config中找不到，则使用task中的旧site
        site = task['site']
    
    name = site.get('name', '未知站点')
    scheduled_time = task['scheduled_time']
    retry_count = task.get('retry_count', 0)
    
    # 构建标题信息
    if retry_count > 0:
        title = f"[重试 {retry_count}] {name}"
    else:
        title = name
    
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 执行任务")
    print(f"站点: {title}")
    print(f"预定时间: {scheduled_time}")
    print(f"{'='*60}")
    
    # 执行签到
    success = process_site(site, config)
    
    # 处理失败的情况
    if not success and should_retry(task, config):
        add_retry_task(task, config)
    elif not success:
        # 重试次数已达上限
        retry_config = get_retry_config(config)
        max_retries = retry_config['max_retries']
        print(f"\n{'='*60}")
        print(f"[任务失败] {name}")
        print(f"已达到最大重试次数（{max_retries}），停止重试")
        print(f"{'='*60}\n")
        
        final_msg = f"签到失败，已达到最大重试次数（{max_retries}），请手动检查"
        push_notification(config, name, final_msg)
    else:
        # 签到成功
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


def initialize_keepalive_tasks(config):
    """
    初始化 Cookie 保活任务
    
    为所有需要保活的网站创建保活任务，计算起始的下次执行时间
    
    Args:
        config: 配置字典
    """
    global keepalive_tasks
    
    sites = config.get('sites', [])
    
    for site in sites:
        name = site.get('name', '')
        
        # 只对恩山论坛启用Cookie保活（可扩展）
        if '恩山' not in name or not site.get('cookie'):
            continue
        
        # 计算下次执行时间
        cookie_dict = cookie_keepalive.parse_cookie_string(site.get('cookie', ''))
        next_exec_time = cookie_keepalive.calculate_next_refresh_time(cookie_dict)
        
        keepalive_tasks[name] = {
            'site': site,
            'next_exec_time': next_exec_time,
            'last_check': None
        }
        
        print(f"[初始化] {name} Cookie保活任务")
        print(f"  下次执行时间: {next_exec_time.strftime('%Y-%m-%d %H:%M:%S')}")


def execute_keepalive_task(site_name, config):
    """
    执行单个Cookie保活任务
    
    Args:
        site_name: 网站名称
        config: 配置字典
        
    Returns:
        bool: 是否执行成功
    """
    global keepalive_tasks
    
    if site_name not in keepalive_tasks:
        return False
    
    site = keepalive_tasks[site_name]['site']
    
    # 执行保活任务
    result = cookie_keepalive.keepalive_task(site, config)
    
    # 更新下次执行时间
    keepalive_tasks[site_name]['next_exec_time'] = result['next_exec_time']
    keepalive_tasks[site_name]['last_check'] = datetime.now()
    
    # 如果失败，添加到重试队列（由keepalive_task处理）
    # 这里我们只是记录结果
    
    return result['success']


def check_keepalive_tasks(config):
    """
    检查是否有Cookie保活任务需要执行
    
    Args:
        config: 配置字典
        
    Yields:
        tuple: (site_name, site_config)
    """
    global keepalive_tasks
    
    now = datetime.now()
    
    for site_name, task_info in keepalive_tasks.items():
        next_exec_time = task_info['next_exec_time']
        
        # 如果当前时间已到或超过下次执行时间
        if now >= next_exec_time:
            yield site_name, task_info['site']


def check_cookies_status(config):
    """
    检查所有网站的 Cookie 状态
    
    Args:
        config: 配置字典
    """
    from datetime import timezone
    
    print(f"\n{'='*80}")
    print("🔍 Cookie 状态检查")
    print(f"{'='*80}\n")
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    for site in config.get('sites', []):
        name = site.get('name', '未知')
        has_cookie = bool(site.get('cookie'))
        metadata_dict = site.get('cookie_metadata', {})
        
        print(f"\n【{name}】")
        print(f"  配置 Cookie: {'✅ 有' if has_cookie else '❌ 无'}")
        
        if has_cookie and metadata_dict:
            metadata = cookie_metadata.CookieMetadata(metadata_dict)
            print(f"  来源: {metadata.source}")
            print(f"  最后更新: {metadata.last_updated}")
            print(f"  刷新尝试: {metadata.refresh_attempts} 次")
            
            remaining = metadata.get_remaining_hours(now)
            if metadata.is_valid(now):
                print(f"  状态: ✅ 有效")
                print(f"  剩余时间: {remaining:.1f} 小时")
                print(f"  截止时间: {metadata.valid_until}")
            else:
                print(f"  状态: ❌ 已过期")
                print(f"  过期时长: {abs(remaining):.1f} 小时")
                print(f"  截止时间: {metadata.valid_until}")
        elif has_cookie:
            print(f"  元数据: 未记录（旧格式 Cookie）")
    
    print(f"\n{'='*80}\n")


def sync_all_cookies(config):
    """
    手动同步所有 Cookie
    
    Args:
        config: 配置字典
    """
    print(f"\n{'='*80}")
    print("🔄 手动同步 Cookie")
    print(f"{'='*80}\n")
    
    if not cookie_sync.sync_cookies():
        print("❌ 同步失败")
        return False
    
    print("✅ 同步成功")
    return True


def main():
    """
    主函数 - 基于任务表的定时签到调度器
    
    工作流程：
    1. 启动时立即生成当天的任务表
    2. 每天0点自动重新生成任务表
    3. 主循环每秒检查是否有任务需要执行
    4. 使用线程执行任务，避免阻塞
    5. 已执行的任务不会重复执行
    6. 失败任务自动加入重试队列，在配置的延迟时间后重试
    """
    # 初始化日志系统
    setup_logging()
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='App Sign - 自动签到服务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例：
  python3 run_sign.py              # 正常运行，开始定时签到
  python3 run_sign.py --check-cookie   # 检查所有网站的 Cookie 状态
  python3 run_sign.py --sync-cookies   # 手动同步一次 Cookie
        '''
    )
    parser.add_argument('--check-cookie', action='store_true',
                       help='检查所有网站的 Cookie 状态并显示有效期')
    parser.add_argument('--sync-cookies', action='store_true',
                       help='手动同步一次 CookieCloud')
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config()
    if not config:
        print("[错误] 无法加载配置文件")
        return
    
    # 处理 --check-cookie 参数
    if args.check_cookie:
        check_cookies_status(config)
        return
    
    # 处理 --sync-cookies 参数
    if args.sync_cookies:
        sync_all_cookies(config)
        return
    
    print(f"\n{'='*60}")
    print(f"自动签到服务启动")
    print(f"启动时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 显示重试配置
    retry_config = get_retry_config(config)
    print(f"[配置] 错误重试机制")
    print(f"  启用状态: {'是' if retry_config['enabled'] else '否'}")
    print(f"  最大重试次数: {retry_config['max_retries']}")
    print(f"  重试延迟: {retry_config['retry_delay_hours']} 小时\n")
    
    # 首次启动时尝试同步 Cookie
    # ⚠️ 重要：不再启用自动定期 CookieCloud 同步
    # 原因：会用过期 Cookie 覆盖 Playwright 刚刷新的新 Cookie
    # 新策略：CookieCloud 只在 Playwright 保活失败时用作故障恢复
    cookiecloud_enabled = False
    try:
        # 检查是否配置了 CookieCloud
        cookiecloud_config = config.get('cookiecloud', {})
        if (cookiecloud_config.get('server') and 
            cookiecloud_config.get('uuid') and 
            cookiecloud_config.get('password')):
            
            print("ℹ️  检测到 CookieCloud 配置（不启用自动同步，仅用于故障恢复）")
            print("   Playwright 保活为主，失败时才同步 CookieCloud\n")
            cookiecloud_enabled = True
        else:
            print("ℹ️  未配置 CookieCloud，将仅使用 Playwright 保活\n")
    except Exception as e:
        print(f"⚠️  检查 CookieCloud 配置失败: {e}\n")
    
    # 首次启动时生成任务表
    check_and_regenerate_tasks(config)
    
    # 初始化 Cookie 保活任务
    try:
        initialize_keepalive_tasks(config)
    except Exception as e:
        print(f"⚠️  初始化 Cookie 保活任务失败: {e}\n")
    
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
            
            # ==================== 检查和执行 Cookie 保活任务 ====================
            keepalive_tasks_to_execute = list(check_keepalive_tasks(config))
            
            if keepalive_tasks_to_execute:
                print(f"\n[{now.strftime('%H:%M:%S')}] 检测到 {len(keepalive_tasks_to_execute)} 个 Cookie 保活任务需要执行")
                
                keepalive_threads = []
                for site_name, site_config in keepalive_tasks_to_execute:
                    def run_keepalive(site_name_inner, site_config_inner):
                        try:
                            result = cookie_keepalive.keepalive_task(site_config_inner, config)
                            
                            with keepalive_queue_lock:
                                if site_name_inner in keepalive_tasks:
                                    keepalive_tasks[site_name_inner]['next_exec_time'] = result['next_exec_time']
                                    keepalive_tasks[site_name_inner]['last_check'] = datetime.now()
                            
                            if result['success']:
                                print(f"  ✅ {site_name_inner} Cookie 保活成功")
                            else:
                                print(f"  ❌ {site_name_inner} Cookie 保活失败（{result['message']}）")
                        except Exception as e:
                            print(f"  ❌ {site_name_inner}: {e}")
                    
                    t = threading.Thread(
                        target=run_keepalive,
                        args=(site_name, site_config),
                        daemon=True
                    )
                    t.start()
                    keepalive_threads.append(t)
                    time.sleep(0.3)
                
                for t in keepalive_threads:
                    t.join(timeout=120)
                
                print(f"[{now.strftime('%H:%M:%S')}] Cookie 保活任务执行完成\n")
            
            # 检查是否有任务需要执行
            with tasks_lock:
                tasks_to_execute = [
                    task for task in daily_tasks 
                    if task['scheduled_time'] == current_time and not task['executed']
                ]
            
            # 检查是否有重试任务需要执行
            with retry_queue_lock:
                retry_tasks_to_execute = [
                    task for task in retry_queue 
                    if task['scheduled_time'] == current_time and not task['executed']
                ]
            
            # 合并所有需要执行的任务
            all_tasks_to_execute = tasks_to_execute + retry_tasks_to_execute
            
            # 执行到达时间的任务
            if all_tasks_to_execute:
                print(f"\n[{now.strftime('%H:%M:%S')}] 检测到 {len(all_tasks_to_execute)} 个任务到达执行时间")
                
                # 如果多个任务时间相同，使用线程并行执行
                threads = []
                for task in all_tasks_to_execute:
                    t = threading.Thread(
                        target=execute_task, 
                        args=(task, config),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
                    
                    # 如果任务时间不同但在同一秒内，添加小延迟避免请求过于集中
                    if len(all_tasks_to_execute) > 1:
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