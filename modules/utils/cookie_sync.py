# -*- coding: utf-8 -*-
"""
Config 读写工具
提供配置文件的线程安全加载和保存功能
"""
import os
import tempfile
import threading
import yaml

_config_write_lock = threading.Lock()


def load_config(config_path='config/config.yaml'):
    """
    加载配置文件，使用全局锁保护读操作。

    Args:
        config_path: 配置文件路径

    Returns:
        (config_dict, encoding): 配置字典和文件编码
    """
    with _config_write_lock:
        for enc in ['utf-8', 'gbk']:
            try:
                with open(config_path, 'r', encoding=enc) as f:
                    config = yaml.safe_load(f)
                    return config, enc
            except:
                continue
        return None, None


def save_config(config, config_path='config/config.yaml', encoding='utf-8'):
    """
    保存配置文件，使用全局锁 + 临时文件原子重命名确保写入安全。

    Args:
        config: 配置字典
        config_path: 配置文件路径
        encoding: 文件编码
    """
    with _config_write_lock:
        try:
            config_dir = os.path.dirname(config_path) or '.'
            temp_fd, temp_path = tempfile.mkstemp(dir=config_dir, text=True, suffix='.tmp')
            try:
                with os.fdopen(temp_fd, 'w', encoding=encoding) as temp_file:
                    yaml.safe_dump(
                        config,
                        temp_file,
                        allow_unicode=True,
                        default_flow_style=False,
                        sort_keys=False,
                        width=4096
                    )
                if os.path.exists(config_path):
                    os.replace(temp_path, config_path)
                else:
                    os.rename(temp_path, config_path)
            except Exception as write_error:
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise write_error
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
