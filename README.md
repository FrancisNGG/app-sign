# App Sign - 自动签到服务

<p align="center">
  <img src="image/app_sign_logo.png" alt="App Sign Logo" width="120" />
</p>

自动访问多个网站进行日常签到，简化重复的手动操作。基于 Docker 容器化部署，支持 DSM 7.2 环境。

## ✨ 功能特性

- **自动签到** - 支持 7 个常用网站的日常签到
  - 恩山无线论坛 / 什么值得买 / 远景论坛
  - 有道云笔记 / 百度贴吧 / AcFun / 哔哩哔哩

- **Cookie 保活机制** - 确保签到持续有效
  - 恩山论坛：Playwright 主动刷新（超时机制）
  - 其他网站：每日签到自动延长有效期
  - CookieCloud 备用（故障恢复）

- **错误重试** - 失败自动进入重试队列，1 小时后重试

- **容器化部署** - Docker + docker-compose，开箱即用

- **日志系统** - 完整的执行日志，时间戳记录

## 📋 配置要求

### 1. 创建配置文件

编辑 `config/config.yaml`：

```yaml
sites:
  - name: "恩山无线论坛"
    base_url: "https://www.right.com.cn/forum/"
    cookie: "你的Cookie值"
    
  - name: "什么值得买"
    base_url: "https://www.smzdm.com/"
    cookie: "你的Cookie值"

# 其他网站配置...

cookiecloud:
  enabled: true
  server: "https://your-cookiecloud.server"
  uuid: "your-uuid"
  password: "your-password"

retry:
  enabled: true
  max_retries: 3
  delay_minutes: 60
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
│   └── config.yaml          # 配置文件（Cookie 等）
├── image/                    # Logo 和其他图片资源
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

## 📝 日志查看

日志自动保存在 `logs/sign_YYYYMMDD_HHMMSS.log`

```bash
# 查看最新日志
tail -f logs/sign_*.log

# 或通过 Docker 查看
docker logs -f app-sign
```

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
```

### 方式 2: 容器管理器 GUI

1. 容器管理器 → 项目 → 新建
2. 选择 docker-compose.yaml 文件
3. 点击"启动"

## 🔐 Cookie 更新策略

| 网站 | Cookie 有效期 | 更新方式 |
|------|-------------|--------|
| 恩山论坛 | 100-120 分钟 | Playwright 主动刷新 |
| 其他 6 个网站 | 7 天至 6 个月 | 每日签到自动延长 |

**CookieCloud 的作用**：仅作为故障恢复的备用方案，不参与日常同步。

## 🐛 常见问题

**Q: DSM 容器管理器看不到日志？**  
A: 注释掉 docker-compose.yaml 中的 `logging` 配置，使用默认驱动。

**Q: Cookie 提示已过期？**  
A: 重新获取最新的 Cookie，替换配置文件中的值。

**Q: Playwright 什么时候执行？**  
A: 仅对恩山论坛执行，其他网站直接调用各自的签到 API。

## 📖 更多帮助

检查日志文件排查问题：
```bash
cat logs/sign_20260212_120530.log
```

## 📖 免责声明

本项目代码全部由 AI 驱动完成，本人并未参与任何代码编写。本人不承担任何使用上的责任。如有侵权联系删除。

## 📄 License

MIT

