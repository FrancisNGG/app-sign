# -*- coding: utf-8 -*-
"""
站点模块包
包含所有支持的签到站点脚本

新增站点步骤：
  1. 在 modules/sites/ 下新建对应 .py 文件（实现 sign(site, config, notify_func) 函数）
  2. 在下方 SITE_REGISTRY 中添加对应条目即可
"""

# ==================== 站点注册表（唯一权威来源）====================
# key: 模块文件名（不含 .py 后缀），同时作为 config.yaml 中 site.module 字段的值
SITE_REGISTRY = {
    'acfun': {
        'name': 'AcFun - Cookie',
        'module': 'acfun',
        'base_url': 'https://www.acfun.cn',
        'description': 'AcFun 弹幕视频网',
    },
    'bilibili': {
        'name': '哔哩哔哩 - Cookie',
        'module': 'bilibili',
        'base_url': 'https://www.bilibili.com',
        'description': '哔哩哔哩',
    },
    'pcbeta': {
        'name': '远景论坛 - 账号密码',
        'module': 'pcbeta',
        'base_url': 'https://bbs.pcbeta.com',
        'description': '远景论坛',
    },
    'right': {
        'name': '恩山无线论坛 - Cookie',
        'module': 'right',
        'base_url': 'https://www.right.com.cn/forum',
        'description': '恩山无线论坛',
    },
    'smzdm': {
        'name': '什么值得买 - Cookie',
        'module': 'smzdm',
        'base_url': 'https://www.smzdm.com',
        'description': '什么值得买',
    },
    'tieba': {
        'name': '百度贴吧 - Cookie',
        'module': 'tieba',
        'base_url': 'https://tieba.baidu.com',
        'description': '百度贴吧',
    },
    'youdao': {
        'name': '有道云笔记 - Cookie',
        'module': 'youdao',
        'base_url': 'https://note.youdao.com',
        'description': '有道云笔记',
    },
}
