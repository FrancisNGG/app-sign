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

logger = logging.getLogger(__name__)

# ==================== 各站点登录页 URL ====================
LOGIN_URLS: Dict[str, str] = {
    'smzdm':    'https://user.smzdm.com/login',
    'bilibili': 'https://passport.bilibili.com/login',
    'acfun':    'https://www.acfun.cn/login',
    'tieba':    'https://tieba.baidu.com/index.html',
    'pcbeta':   'https://bbs.pcbeta.com/member.php?mod=logging&action=login',
    'right':    'https://www.right.com.cn/forum/member.php?mod=logging&action=login',
    'youdao':   'https://account.youdao.com/signIn?service=mobilemail&back_url=http%3A%2F%2Fnote.youdao.com',
}

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
        self._page_lock = asyncio.Lock()

    # ---- 生命周期 ----

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    async def initialize(self) -> None:
        """启动 headless Chromium，导航到登录页。"""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-dev-shm-usage']
        )
        self._context = await self._browser.new_context(
            viewport={'width': VIEWPORT_W, 'height': VIEWPORT_H},
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        )
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
        login_url = LOGIN_URLS.get(module, 'about:blank')
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
