# -*- coding: utf-8 -*-
"""
captcha_browser.py

截图流浏览器会话管理 —— 让用户在前端页面上远程操控一个 headless 浏览器，
支持点击、输入、滚动、拖拽等操作，从而手动完成滑块验证码、点选验证码、
5秒盾等复杂人机验证，最终提取站点 Cookie。
"""

import asyncio
import uuid
import base64
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from modules.sites import SITE_REGISTRY

logger = logging.getLogger(__name__)

# 浏览器渲染分辨率（与前端保持一致）
VIEWPORT_W = 1280
VIEWPORT_H = 720


# ==================== 会话类 ====================
class FetchCookieSession:
    """单个浏览器远程控制会话。"""

    def __init__(self, session_id: str, module: str, login_url: str):
        self.session_id = session_id
        self.module = module
        self.login_url = login_url

        # 状态: starting | ready | error | closed
        self.status = 'starting'
        self.error_message: Optional[str] = None
        self.current_url: str = login_url

        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(minutes=30)

        # Playwright 对象（在 initialize() 中赋值）
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        # 注意：asyncio.Lock() 必须在事件循环线程中创建，延迟到 initialize() 里赋值
        self._page_lock: Optional[asyncio.Lock] = None

    # ---- 生命周期 ----

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    async def initialize(self) -> None:
        """启动 headless Chromium，导航到登录页。"""
        # 在事件循环线程内创建 Lock，避免 Python 3.10+ RuntimeError
        self._page_lock = asyncio.Lock()

        # 从 config.yaml 读取 user_agent，保持与签到请求一致
        import re as _re
        _ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        try:
            import os as _os, yaml as _yaml
            _cfg_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'config', 'config.yaml')
            with open(_cfg_path, 'r', encoding='utf-8') as _f:
                _cfg = _yaml.safe_load(_f)
            _ua = (_cfg.get('global') or {}).get('user_agent') or _ua
        except Exception:
            pass
        # 从 UA 中提取 Chrome 主版本号，同步到 sec-ch-ua
        _m = _re.search(r'Chrome/(\d+)', _ua)
        _chrome_ver = _m.group(1) if _m else '144'

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                # 隐藏自动化特征，避免风控
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--disable-extensions',
                '--disable-default-apps',
                '--disable-component-update',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-networking',
                '--disable-sync',
                '--metrics-recording-only',
                '--disable-client-side-phishing-detection',
                '--disable-hang-monitor',
                '--disable-prompt-on-repost',
                '--password-store=basic',
                '--use-mock-keychain',
                # 模拟正常分辨率
                f'--window-size={VIEWPORT_W},{VIEWPORT_H}',
            ]
        )
        self._context = await self._browser.new_context(
            viewport={'width': VIEWPORT_W, 'height': VIEWPORT_H},
            user_agent=_ua,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'sec-ch-ua': f'"Google Chrome";v="{_chrome_ver}", "Chromium";v="{_chrome_ver}", "Not_A Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
            },
            permissions=['geolocation'],
            java_script_enabled=True,
        )
        # 注入脚本：覆盖自动化检测属性，模拟 macOS Chrome 真实环境
        await self._context.add_init_script(f"""
            // 删除 webdriver 标记
            Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});

            // 模拟 macOS Chrome 完整 window.chrome 对象
            window.chrome = {{
                app: {{
                    InstallState: {{DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'}},
                    RunningState: {{CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'}},
                    getDetails: function() {{}},
                    getIsInstalled: function() {{}},
                    installState: function() {{}},
                    isInstalled: false,
                    runningState: function() {{}}
                }},
                csi: function() {{}},
                loadTimes: function() {{
                    return {{
                        commitLoadTime: Date.now() / 1000 - 0.3,
                        connectionInfo: 'h2',
                        finishDocumentLoadTime: Date.now() / 1000 - 0.1,
                        finishLoadTime: Date.now() / 1000,
                        firstPaintAfterLoadTime: 0,
                        firstPaintTime: Date.now() / 1000 - 0.2,
                        navigationType: 'Other',
                        npnNegotiatedProtocol: 'h2',
                        requestTime: Date.now() / 1000 - 0.5,
                        startLoadTime: Date.now() / 1000 - 0.4,
                        wasAlternateProtocolAvailable: false,
                        wasFetchedViaSpdy: true,
                        wasNpnNegotiated: true
                    }};
                }},
                runtime: {{
                    OnInstalledReason: {{CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update'}},
                    OnRestartRequiredReason: {{APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic'}},
                    PlatformArch: {{ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'}},
                    PlatformNaclArch: {{ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'}},
                    PlatformOs: {{ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win'}},
                    RequestUpdateCheckStatus: {{NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available'}},
                    connect: function() {{}},
                    id: undefined
                }}
            }};

            // 模拟 macOS platform
            Object.defineProperty(navigator, 'platform', {{get: () => 'MacIntel'}});

            // 覆盖 plugins，模拟 macOS Chrome 真实插件列表
            const _plugins = [
                {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
                {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''}},
                {{name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}}
            ];
            Object.defineProperty(navigator, 'plugins', {{
                get: () => Object.assign(_plugins, {{
                    item: (i) => _plugins[i],
                    namedItem: (n) => _plugins.find(p => p.name === n),
                    refresh: () => {{}}
                }})
            }});
            Object.defineProperty(navigator, 'mimeTypes', {{get: () => [{{type: 'application/pdf'}}, {{type: 'application/x-google-chrome-pdf'}}]}});

            // 覆盖 languages
            Object.defineProperty(navigator, 'languages', {{get: () => ['zh-CN', 'zh', 'en-US', 'en']}});

            // 覆盖 hardwareConcurrency（macOS 常见核数）
            Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => 8}});

            // 覆盖 deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {{get: () => 8}});

            // 覆盖 permissions
            const _origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({{state: Notification.permission}})
                    : _origQuery(params);
        """)
        self._page = await self._context.new_page()
        try:
            await self._page.goto(
                self.login_url,
                wait_until='domcontentloaded',
                timeout=30000
            )
        except Exception as e:
            logger.warning(f"[{self.session_id}] 导航警告（页面仍可用）: {e}")
        self.current_url = self._page.url
        self.status = 'ready'
        logger.info(f"[{self.session_id}] 会话就绪: {self.current_url}")

    async def close(self) -> None:
        """释放所有浏览器资源。"""
        self.status = 'closed'
        for obj, method in [
            (self._context, 'close'),
            (self._browser, 'close'),
            (self._playwright, 'stop'),
        ]:
            if obj:
                try:
                    await getattr(obj, method)()
                except Exception:
                    pass
        self._page = self._context = self._browser = self._playwright = None

    # ---- 截图 ----

    async def screenshot_jpeg(self) -> Optional[bytes]:
        """返回当前页面 JPEG 截图原始字节。"""
        if not self._page:
            return None
        async with self._page_lock:
            try:
                data = await self._page.screenshot(type='jpeg', quality=75)
                self.current_url = self._page.url
                return data
            except Exception as e:
                logger.warning(f"[{self.session_id}] 截图失败: {e}")
                return None

    # ---- 输入事件转发 ----

    async def do_action(self, action_type: str, **kwargs) -> bool:
        """将前端鼠标/键盘事件转发到浏览器页面。返回 True 表示成功。"""
        if not self._page or self.status != 'ready':
            return False
        async with self._page_lock:
            try:
                page = self._page
                if action_type == 'click':
                    await page.mouse.click(float(kwargs['x']), float(kwargs['y']))
                elif action_type == 'dblclick':
                    await page.mouse.dblclick(float(kwargs['x']), float(kwargs['y']))
                elif action_type == 'mousedown':
                    await page.mouse.move(float(kwargs['x']), float(kwargs['y']))
                    await page.mouse.down()
                elif action_type == 'mousemove':
                    await page.mouse.move(float(kwargs['x']), float(kwargs['y']))
                elif action_type == 'mouseup':
                    await page.mouse.move(float(kwargs['x']), float(kwargs['y']))
                    await page.mouse.up()
                elif action_type == 'type':
                    await page.keyboard.type(str(kwargs['text']))
                elif action_type == 'key':
                    await page.keyboard.press(str(kwargs['key']))
                elif action_type == 'scroll':
                    # 先移动鼠标到滚动位置，再滚轮
                    if 'x' in kwargs and 'y' in kwargs:
                        await page.mouse.move(float(kwargs['x']), float(kwargs['y']))
                    await page.mouse.wheel(
                        float(kwargs.get('delta_x', 0)),
                        float(kwargs.get('delta_y', 100))
                    )
                elif action_type == 'goto':
                    url = str(kwargs.get('url', ''))
                    if url:
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                else:
                    logger.warning(f"[{self.session_id}] 未知操作类型: {action_type}")
                    return False
                self.current_url = page.url
                return True
            except Exception as e:
                logger.warning(f"[{self.session_id}] 操作 [{action_type}] 失败: {e}")
                return False

    # ---- Cookie 提取 ----

    async def extract_cookies(self) -> Optional[str]:
        """提取当前上下文所有 Cookie，返回 `name=value; ...` 格式字符串。"""
        if not self._context:
            return None
        try:
            cookies = await self._context.cookies()
            if not cookies:
                return ''
            parts = [f"{c['name']}={c['value']}" for c in cookies if c.get('name')]
            return '; '.join(parts)
        except Exception as e:
            logger.error(f"[{self.session_id}] 提取 Cookie 失败: {e}")
            return None


# ==================== 会话池 ====================
class FetchCookieManager:
    """线程安全的浏览器会话池。"""

    def __init__(self):
        self._sessions: Dict[str, FetchCookieSession] = {}
        self._lock = threading.Lock()

    def create_session(self, module: str) -> Tuple[str, FetchCookieSession]:
        """创建新会话（尚未初始化浏览器），返回 (session_id, session)。"""
        login_url = (SITE_REGISTRY.get(module) or {}).get('base_url', 'about:blank')
        session_id = f"fc_{uuid.uuid4().hex[:12]}"
        session = FetchCookieSession(session_id, module, login_url)
        with self._lock:
            # 清理过期会话
            expired = [
                sid for sid, s in self._sessions.items()
                if s.is_expired and s.status not in ('starting',)
            ]
            for sid in expired:
                del self._sessions[sid]
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> Optional[FetchCookieSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
