# App Sign - 自动签到服务

<p align="center">
  <img src="image/app_sign_logo.png" alt="App Sign Logo" width="120" />
</p>

自动访问多个网站进行日常签到，简化重复的手动操作。支持 Cookie 保活、智能重试、日志轮转等高级特性。基于 Docker 容器化部署，支持 DSM 7.2 环境。

## ✨ 功能特性

- **智能自动签到** - 支持 7 个常用网站的日常签到
  - 恩山无线论坛 / 什么值得买 / 远景论坛
  - 有道云笔记 / 百度贴吧 / AcFun / 哔哩哔哩

- **Cookie 保活机制** - 确保签到持续有效
  - 恩山论坛：Playwright 主动刷新（超时自动更新）
  - 其他网站：每日签到自动延长有效期
  - CookieCloud 备用（故障恢复）
  - **🆕 动态配置更新**：签到时自动从最新配置读取 Cookie

- **智能错误重试** - 失败自动进入重试队列
  - 支持自定义最大重试次数
  - 可配置重试延迟时间（默认 1 小时）

- **日志轮转管理** - 每天自动生成新日志
  - **🆕 按天轮转**：每天 0 点自动切换日志文件
  - **🆕 自动清理**：自动删除 7 天前的过期日志
  - **🆕 故障恢复**：日志文件被删除时自动重建

- **容器化部署** - Docker + docker-compose，开箱即用

## 📋 配置要求

### 1. 创建配置文件

编辑 `config/config.yaml`：

```yaml
sites:
  - name: "恩山无线论坛"
    base_url: "https://www.right.com.cn/forum/"
    run_time: "09:00:00"    # 签到时间
    random_range: 0         # 随机延迟（分钟）
    cookie: "你的Cookie值"
    
  - name: "什么值得买"
    base_url: "https://www.smzdm.com/"
    run_time: "09:00:00"
    random_range: 0
    cookie: "你的Cookie值"

# 其他网站配置...

# Cookie 保活备用（可选）
cookiecloud:
  server: "https://your-cookiecloud.server"
  uuid: "your-uuid"
  password: "your-password"

# 重试配置
retry:
  enabled: true           # 启用重试机制
  max_retries: 3          # 最大重试次数
  retry_delay_hours: 1    # 重试延迟时间（小时）
```

### 2. 获取 Cookie

使用浏览器开发者工具（F12）：
1. 打开网站
2. 访问 DevTools → Network → 找任意请求
3. 复制 Request Headers 中的 `Cookie` 字段

## 🚀 快速开始

### 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动签到服务
python run_sign.py

# 检查 Cookie 状态
python run_sign.py --check-cookie

# 手动同步 CookieCloud
python run_sign.py --sync-cookies
```

### Docker 部署（推荐）

```bash
# 构建并启动
docker-compose up -d --build

# 查看实时日志
docker logs -f app-sign

# 停止服务
docker-compose down
```

## 📂 项目结构

```
.
├── config/
│   ├── config.example.yaml  # 配置示例
│   └── config.yaml          # 配置文件（Cookie 等）
├── image/                    # Logo 和其他图片资源
│   ├── app_sign_logo.ico  
│   └── app_sign_logo.png
├── modules/
│   ├── right.py             # 恩山论坛签到
│   ├── smzdm.py             # 什么值得买签到
│   ├── bilibili.py          # 哔哩哔哩签到
│   ├── acfun.py             # AcFun 签到
│   ├── tieba.py             # 百度贴吧签到
│   ├── youdao.py            # 有道云笔记签到
│   ├── pcbeta.py            # 远景论坛签到
│   ├── cookie_keepalive.py  # Cookie 保活模块
│   ├── cookie_sync.py       # CookieCloud 同步模块
│   ├── cookie_metadata.py   # Cookie 元数据管理
│   └── notify.py            # 通知模块（Bark、email等）
├── logs/                     # 日志目录（自动生成）
│   └── sign_YYYYMMDD.log    # 按天轮转的日志文件
├── run_sign.py              # 主程序
├── Dockerfile               # 容器镜像定义
├── docker-compose.yaml      # 容器编排配置
├── requirements.txt         # Python 依赖
├── README.md                # 说明文档
└── .gitignore               # Git 忽略规则
```
│   ├── app_sign_logo.ico  
│   └── app_sign_logo.png
├── modules/
│   ├── right.py             # 恩山论坛签到
│   ├── smzdm.py             # 什么值得买签到
│   ├── cookie_keepalive.py  # Cookie 保活模块
│   └── ...
├── logs/                     # 日志目录（自动生成）
├── run_sign.py              # 主程序
├── Dockerfile               # 容器镜像定义
├── docker-compose.yaml      # 容器编排配置
├── README.md                # 说明文档
└── requirements.txt         # Python 依赖
```

## 📝 日志管理

### 日志轮转策略
- **🆕 按天轮转**：日志文件格式为 `sign_YYYYMMDD.log`（如 `sign_20260213.log`）
- **🆕 午夜自动切换**：每天 0 点自动创建新日志文件
- **🆕 自动清理**：自动删除 7 天前的过期日志文件
- **🆕 故障恢复**：日志文件被删除时自动重建，不中断服务

### 查看日志

```bash
# 查看今天的日志
tail -f logs/sign_$(date +%Y%m%d).log

# 查看所有日志
ls -lah logs/

# 或通过 Docker 查看
docker logs -f app-sign
```

### 日志内容示例

```
2026-02-13 09:01:44 [INFO] 日志系统初始化完成，日志文件: logs/sign_20260213.log
============================================================
自动签到服务启动
启动时间: 2026年02月13日 09:01:44
============================================================

[09:01:44] 检测到 1 个任务到达执行时间

============================================================
[2026-02-13 09:01:44] 执行任务
站点: 什么值得买
预定时间: 09:01:44
============================================================
[什么值得买] 开始签到...
[什么值得买] ✓ 签到成功
[什么值得买] 连续签到天数: 2445
```

## 🔄 工作流程

```
自动签到服务
├── 启动时
│   ├── 初始化日志系统（按天轮转）
│   ├── 清理 7 天前的过期日志
│   ├── 加载配置文件 config.yaml
│   ├── 初始化 Cookie 保活任务（恩山论坛）
│   └── 生成当日任务表
│
├── 每秒检查一次
│   ├── Cookie 保活任务（按需执行，通常每 2 小时）
│   ├── 日常签到任务（在预定时间触发）
│   └── 日期切换检查（午夜 00:00:00）
│
├── 任务执行时
│   ├── 从最新配置中读取该站点的 Cookie（🆕 动态更新）
│   ├── 自动检测网站类型
│   ├── 执行签到操作
│   ├── 失败时自动加入重试队列
│   └── 记录日志和发送通知
│
└── 日期变更时（午夜）
    ├── 生成新日期的任务表
    ├── 切换日志文件
    └── 清理 7 天前的日志
```

## 🔐 Cookie 更新策略

| 网站 | Cookie 有效期 | 更新方式 | 频率 |
|------|-------------|--------|------|
| 恩山论坛 | 100-120 分钟 | Playwright 主动刷新 | 每 2 小时 |
| 什么值得买 | 长期有效 | 每日签到自动延长 | 每日 |
| 其他网站 | 7 天至 6 个月 | 每日签到自动延长 | 每日 |

**💡 关键特性**：
- CookieCloud 作为**备用方案**，仅在 Playwright 保活失败时使用
- 日常签到时从最新配置读取 Cookie，确保总是使用最新值
- Playwright 刷新成功后会自动保存新 Cookie 到配置文件

## 🚨 故障处理

### 签到失败自动重试

失败任务会按照以下策略重试：
```
第 1 次失败 → 1 小时后重试
第 2 次失败 → 再延迟 1 小时重试  
第 3 次失败（默认配置）→ 放弃重试，发送通知
```

可在 `config.yaml` 中修改 `retry` 配置自定义重试策略。

### 日志文件被删除

无需担心！系统会：
1. ✅ 检测到文件缺失
2. ✅ 自动重建日志文件
3. ✅ 记录恢复发生的时间
4. ✅ 继续正常运行

## ⚙️ 部署到 DSM 7.2

### 方式 1: SSH 部署（推荐）

```bash
# 上传文件到 DSM
scp -r app-sign/ admin@nas:/volume1/docker/

# SSH 连接
ssh admin@nas

# 启动容器
cd /volume1/docker/app-sign
docker-compose up -d --build

# 查看日志
docker logs -f app-sign
```

### 方式 2: 容器管理器 GUI

1. 容器管理器 → 项目 → 新建
2. 选择 docker-compose.yaml 文件
3. 点击"启动"
4. 通过"日志"标签页查看输出

### 持久化存储配置

在 `docker-compose.yaml` 中确保配置文件被正确挂载：
```yaml
volumes:
  - ./config:/app/config
  - ./logs:/app/logs
```

## 🆕 最近更新

### v2.0 优化更新（2026年2月）

✅ **修复问题**
- 修复 AcFun、哔哩哔哩、百度贴吧、有道云笔记模块签到返回值缺失问题
- 解决成功签到被错误加入重试队列的 Bug
- 修复 Cookie 引用陈旧导致签到失败的问题

✅ **性能优化**
- 动态读取最新配置，确保签到时使用最新 Cookie
- Cookie 保活成功后正确更新到签到任务中
- 日志自动轮转，避免单个文件无限增长

✅ **新增功能**
- 日志按天轮转（每天 0 点自动切换）
- 自动删除 7 天前的过期日志
- 日志文件被删除时自动重建（无需重启）

## 🐛 常见问题

**Q: 签到为什么还是失败？**  
A: 
1. 检查 config.yaml 中的 Cookie 是否正确
2. Cookie 可能已过期，重新获取最新值
3. 查看 logs/ 目录中的日志文件排查具体错误

**Q: 日志文件太大？**  
A: 不用担心！现在日志会按天自动轮转，每个文件只记录当天的日志。超过 7 天的旧日志会自动删除。

**Q: DSM 容器管理器看不到日志？**  
A: 改用命令行查看：
```bash
docker logs -f app-sign
# 或查看日志文件
docker exec app-sign tail -f logs/sign_$(date +%Y%m%d).log
```

**Q: 日志文件被意外删除了？**  
A: 系统会自动检测并重新创建日志文件，并在日志中记录恢复信息。无需重启服务！

**Q: Cookie 保活什么时候执行？**  
A: 
- 仅对恩山论坛执行
- 根据 Cookie 剩余有效期自动判断（通常每 2 小时一次）
- 其他网站通过每日签到自动延长 Cookie 有效期

**Q: 重试什么时候执行？**  
A: 失败任务会进入重试队列，按配置延迟时间后重试（默认 1 小时）

**Q: 能否修改签到时间？**  
A: 可以！在 config.yaml 中修改每个网站的 `run_time` 字段即可（格式：HH:MM:SS）

**Q: 能否修改日志保留天数？**  
A: 可以！修改 run_sign.py 中的 `cleanup_old_logs()` 函数的 `days` 参数

## 📊 监控与通知

### 支持的通知方式

- **Bark** - iOS 推送通知（推荐）
- **Email** - 邮件通知（待扩展）
- **钉钉** - 钉钉机器人（待扩展）

在 `modules/notify.py` 中配置通知参数。

## 🔗 相关资源

- [Playwright 官方文档](https://playwright.dev/python/)
- [CookieCloud](https://github.com/easychen/CookieCloud)
- [Docker 官方文档](https://docs.docker.com/)

## 🤌 免责声明

本项目代码全部由 AI 驱动完成，本人并未参与任何代码编写。本人不承担任何层面的责任。如有侵权联系删除。

## 📄 License

MIT

