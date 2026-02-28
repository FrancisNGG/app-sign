# App Sign v2

<p align="center">
  <img src="image/app_sign_logo.png" alt="App Sign Logo" width="120" />
</p>

自动签到管理工具，通过 Web 面板统一管理多个网站的每日签到，基于 Playwright 浏览器实现 Cookie 获取与保活。

---

## ✨ 功能特性

- **Web 管理面板** — 浏览器访问，无需命令行操作
- **自动每日签到** — 指定时间自动执行，支持随机延迟防检测
- **Playwright 登录** — 通过真实浏览器完成登录和验证码处理，自动保存 Cookie
- **Cookie 自动保活** — 定期刷新 Cookie，防止过期掉登录
- **Bark 推送通知** — 签到结果推送到 iPhone
- **按天滚动日志** — 日志自动按日归档，保留 30 天
- **Docker 一键部署** — 提供 docker-compose 配置，开箱即用

## 🌐 支持站点

| 站点 | 登录方式 | 说明 |
|------|----------|------|
| 恩山无线论坛 | Cookie | right.com.cn |
| 什么值得买 | Cookie | smzdm.com |
| AcFun | Cookie | acfun.cn |
| 哔哩哔哩 | Cookie | bilibili.com |
| 百度贴吧 | Cookie | tieba.baidu.com |
| 有道云笔记 | Cookie | note.youdao.com |
| 远景论坛 | 账号密码 | pcbeta.com |

---

## 🚀 快速开始

### 💻 本地运行

**环境要求：** Python 3.9+

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 启动服务
python3 run_sign.py

# 3. 打开浏览器
# http://localhost:21333
# 默认账号/密码: admin / admin
```

### 🐳 Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看运行日志
docker logs -f app-sign-v2

# 访问
# http://localhost:21333
```

---

## 📁 项目结构

```
app-sign/
├── run_sign.py                # 启动入口
├── Dockerfile
├── docker-compose.yaml
├── requirements.txt
├── config/
│   └── config.yaml            # 配置文件（自动生成）
├── logs/                      # 日志目录（自动创建）
│   └── app_sign_logs.log      # 当天日志，按天滚动
├── cache/                     # Playwright 浏览器缓存
├── modules/
│   ├── sites/                 # 各站点签到实现
│   │   ├── __init__.py        # SITE_REGISTRY：站点注册表
│   │   ├── acfun.py
│   │   ├── bilibili.py
│   │   ├── pcbeta.py
│   │   ├── right.py
│   │   ├── smzdm.py
│   │   ├── tieba.py
│   │   └── youdao.py
│   ├── core/
│   │   ├── credential_manager.py # 登录 / 验证码处理
│   │   ├── sign_executor.py      # 签到执行器
│   │   └── task_scheduler.py     # 定时任务调度
│   └── utils/
│       ├── cookie_sync.py        # 配置文件读写工具
│       ├── cookie_keepalive.py   # Cookie 保活逻辑
│       ├── cookie_metadata.py    # Cookie 有效期元数据
│       └── notify.py             # Bark 推送
└── web/
    ├── web_server_v2.py           # Flask 后端（主服务）
    ├── captcha_browser.py         # 验证码浏览器
    └── frontend/
        ├── auth.html              # 登录页
        ├── dashboard.html         # 签到面板
        ├── add-site.html          # 添加账号
        ├── settings.html          # 系统设置
        └── fetch-cookie.html      # Cookie 获取页
```

---

## ⚙️ 配置文件说明

`config/config.yaml` 首次启动时自动创建，格式如下：

```yaml
# Web 管理面板认证
auth:
  username: admin
  password: admin

# 站点列表（通过 Web 面板管理，无需手动编辑）
sites:
  - name: 恩山无线论坛
    module: right
    enabled: true
    cookie: "your_cookie_here"
    run_time: "09:00:00"     # 每日签到时间
    random_range: 10          # 随机延迟 0~10 分钟
    keepalive:
      enabled: true
      method: browser_refresh
      interval_minutes: 120   # 每 120 分钟保活一次

# 通知设置
notify:
  bark:
    enabled: false
    key: ""                   # Bark 推送 Key
    title: "签到通知"
    sound: "default"
```

---

## 📝 使用流程

1. **启动服务** → 访问 `http://localhost:21333`
2. **登录面板** → 使用 admin/admin（首次使用请在设置中修改密码）
3. **添加站点** → Dashboard → 添加网站 → 选择站点 → 输入账号密码 → 浏览器自动完成登录保存 Cookie
4. **查看状态** → Dashboard 展示所有站点的签到状态、下次签到时间、Cookie 有效期
5. **手动签到** → 点击站点卡片上的"立即签到"按钮

---

## 📋 日志

```bash
# 实时查看
tail -f logs/app_sign_logs.log

# 历史日志（自动按天归档）
# logs/app_sign_logs_20260228.log
# logs/app_sign_logs_20260301.log
# ...（最多保留 30 天）
```

---

## 🔧 添加新站点

1. 在 `modules/sites/` 下新建 `xxx.py`，实现 `sign(site, config, notify_func)` 函数
2. 在 `modules/sites/__init__.py` 的 `SITE_REGISTRY` 中添加对应条目
3. 重启服务，新站点自动出现在 Web 面板选择列表中

---

## 🌍 端口与部署

| 场景 | 访问地址 |
|------|----------|
| 本地运行 | http://localhost:21333 |
| Docker | http://localhost:21333 |
| 服务器 | http://服务器IP:21333 |

如需修改端口，在 `run_sign.py`、`web/web_server_v2.py`、`docker-compose.yaml`、`Dockerfile` 中统一替换端口号即可。

---

## 🤌 免责声明

本项目代码全部由 AI 驱动完成，本人并未参与任何代码编写。本人不承担任何层面的责任。如有侵权联系删除。

---

## 📄 License

MIT
