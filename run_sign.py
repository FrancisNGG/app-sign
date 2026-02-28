# -*- coding: utf-8 -*-
"""
App Sign v2.0 - 简化启动脚本
直接启动Web服务，所有功能通过Web API和前端实现
"""
import sys
import os
import io

# 确保 stdout 和 stderr 使用 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import logging
from logging.handlers import TimedRotatingFileHandler

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)

# 添加文件日志处理器（写入 logs/app_sign_logs_YYYYMMDD.log，按天轮转，保留30天）
def _setup_file_logging():
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app_sign_logs.log')
    fh = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        backupCount=30,
        encoding='utf-8'
    )
    fh.suffix = '%Y%m%d'
    # 轮转后文件重命名：app_sign_logs.log.20260228 → app_sign_logs_20260228.log
    def _namer(name):
        base, date_part = name.rsplit('.', 1)
        return os.path.join(os.path.dirname(base), f'app_sign_logs_{date_part}.log')
    fh.namer = _namer
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
    ))
    logging.getLogger().addHandler(fh)

_setup_file_logging()
logger = logging.getLogger(__name__)

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    """主入口"""
    logger.info("=" * 50)
    logger.info("App Sign v2.0 - Web服务启动")
    logger.info("=" * 50)
    
    try:
        # 导入并启动Web服务
        from web.web_server_v2 import start_server
        
        logger.info("启动Web服务器...")
        start_server(host='0.0.0.0', port=21333, debug=False)
        
    except KeyboardInterrupt:
        logger.info("\n收到中断信号，正在关闭...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
