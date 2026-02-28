"""
credential_manager.py

处理用户账号密码登录、验证码检测和Cookie提取的核心模块。
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
import base64
from io import BytesIO

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


class LoginState(str, Enum):
    """登录状态"""
    IN_PROGRESS = "in_progress"
    AWAITING_INPUT = "awaiting_input"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class CaptchaType(str, Enum):
    """验证码类型"""
    IMAGE = "image"
    TEXT = "text"
    SLIDER = "slider"
    CLICK = "click"
    UNKNOWN = "unknown"


@dataclass
class CaptchaInfo:
    """验证码信息"""
    captcha_type: CaptchaType
    message: str = "请处理验证码"
    image_base64: Optional[str] = None  # 图片验证码的base64
    timeout: int = 300  # 秒
    selector: Optional[str] = None  # 验证码元素selector


@dataclass
class LoginSession:
    """登录会话"""
    session_id: str
    site_name: str
    username: str
    started_at: datetime
    expires_at: datetime
    
    # Playwright 相关
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    
    # 登录状态
    state: LoginState = LoginState.IN_PROGRESS
    current_step: str = "initializing"
    error_message: Optional[str] = None
    
    # 验证码相关
    captcha_detected: bool = False
    captcha_info: Optional[CaptchaInfo] = None
    captcha_attempts: int = 0
    max_captcha_attempts: int = 3
    
    # 结果
    cookies: Dict[str, str] = field(default_factory=dict)


class CredentialManager:
    """
    身份验证管理器
    
    负责：
    - 账号密码登录
    - 验证码检测和提交
    - Cookie提取
    - 会话管理
    """
    
    def __init__(self, browser_manager=None):
        """
        初始化凭证管理器
        
        Args:
            browser_manager: 浏览器管理器，用于获取browser实例
        """
        self.browser_manager = browser_manager
        self.sessions: Dict[str, LoginSession] = {}
        self.browser: Optional[Browser] = None
        
    async def signup_browser(self):
        """初始化Playwright浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        
    async def cleanup_browser(self):
        """清理浏览器资源"""
        if self.browser:
            await self.browser.close()
    
    async def start_login(
        self,
        site_name: str,
        base_url: str,
        username: str,
        password: str,
        module_name: str = None
    ) -> LoginSession:
        """
        开始登录流程
        
        Args:
            site_name: 网站名称
            base_url: 网站地址
            username: 用户名
            password: 密码
            module_name: 对应的签到模块名称
            
        Returns:
            LoginSession对象
            
        Raises:
            RuntimeError: 浏览器未初始化或启动失败
        """
        if not self.browser:
            await self.signup_browser()
        
        # 创建会话
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = LoginSession(
            session_id=session_id,
            site_name=site_name,
            username=username,
            started_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        try:
            # 创建浏览器上下文和页面
            session.context = await self.browser.new_context()
            session.page = await session.context.new_page()
            
            # 设置viewport
            await session.page.set_viewport_size({"width": 1280, "height": 720})
            
            # 保存会话
            self.sessions[session_id] = session
            
            # 异步启动登录流程
            asyncio.create_task(self._login_flow(session, base_url, username, password))
            
            logger.info(f"登录会话启动: {session_id} ({site_name})")
            
        except Exception as e:
            session.state = LoginState.ERROR
            session.error_message = f"启动浏览器失败: {str(e)}"
            logger.error(f"启动登录会话失败: {str(e)}")
            raise
        
        return session
    
    async def _login_flow(
        self,
        session: LoginSession,
        base_url: str,
        username: str,
        password: str
    ):
        """
        执行登录流程
        """
        try:
            session.current_step = "navigating"
            session.state = LoginState.IN_PROGRESS
            
            # 导航到登录页
            logger.info(f"导航到: {base_url}")
            await session.page.goto(base_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1)  # 等待页面稳定
            
            session.current_step = "finding_login_form"
            
            # 查找登录表单并填充（这是通用逻辑，具体网站可能需要定制）
            await self._fill_login_form(session, username, password)
            
            session.current_step = "checking_captcha"
            
            # 检测验证码
            await self._check_for_captcha(session)
            
            if session.captcha_detected:
                # 等待用户提交验证码
                session.state = LoginState.AWAITING_INPUT
                logger.info(f"检测到验证码，等待用户处理")
                await asyncio.sleep(0.5)  # 短暂等待，避免busy loop
                return
            
            # 继续登录流程
            session.current_step = "submitting_login"
            await self._wait_for_login_success(session)
            
            session.current_step = "extracting_cookies"
            await self._extract_cookies(session)
            
            session.state = LoginState.SUCCESS
            logger.info(f"登录成功: {session.site_name}")
            
        except asyncio.CancelledError:
            session.state = LoginState.CANCELLED
            logger.info(f"登录流程被取消: {session.site_name}")
        except Exception as e:
            session.state = LoginState.ERROR
            session.error_message = str(e)
            logger.error(f"登录流程错误: {str(e)}", exc_info=True)
    
    async def _fill_login_form(
        self,
        session: LoginSession,
        username: str,
        password: str
    ):
        """填充登录表单"""
        page = session.page
        
        # 尝试找到用户名和密码输入框
        # 这是通用的启发式方法，具体网站可能需要定制
        try:
            # 常见的用户名选择器
            username_selectors = [
                "input[name='username']",
                "input[name='user']",
                "input[name='login']",
                "input[type='text']:first-of-type",
                "input[id*='user']",
                "input[placeholder*='用户名']",
                "input[placeholder*='账号']",
                "input[placeholder*='邮箱']",
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        username_input = elements[0]
                        break
                except:
                    pass
            
            if username_input:
                await username_input.fill(username)
                logger.debug(f"填充用户名: {username}")
            else:
                # 如果找不到，尝试tab键导航
                await page.keyboard.press("tab")
                await page.keyboard.type(username)
            
            # 填充密码
            password_selectors = [
                "input[name='password']",
                "input[name='pass']",
                "input[type='password']",
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        password_input = elements[0]
                        break
                except:
                    pass
            
            if password_input:
                await password_input.fill(password)
                logger.debug(f"填充密码")
            else:
                await page.keyboard.press("tab")
                await page.keyboard.type(password)
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"填充登录表单失败: {str(e)}")
            raise
    
    async def _check_for_captcha(self, session: LoginSession):
        """检测验证码"""
        page = session.page
        
        # 验证码选择器（常见的）
        captcha_selectors = {
            "image": [
                "img[src*='captcha']",
                "img[id*='captcha']",
                ".geetest_holder img",
                ".captcha-image",
                "#jcaptcha",
            ],
            "text": [
                "input[placeholder*='验证码']",
                "input[placeholder*='代码']",
            ],
            "slider": [
                ".geetest_slider",
                ".slider-container",
                ".captcha-slider",
            ],
            "click": [
                "div[id*='captcha'][class*='click']",
                ".slide-verify",
            ]
        }
        
        # 检查各种验证码类型
        for captcha_type, selectors in captcha_selectors.items():
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info(f"检测到 {captcha_type} 类型验证码")
                        session.captcha_detected = True
                        
                        captcha_info = CaptchaInfo(
                            captcha_type=CaptchaType(captcha_type),
                            selector=selector
                        )
                        
                        # 如果是图片验证码，抓取图片
                        if captcha_type == "image":
                            try:
                                screenshot = await element.screenshot()
                                captcha_info.image_base64 = base64.b64encode(
                                    screenshot
                                ).decode('utf-8')
                            except Exception as e:
                                logger.warning(f"获取验证码图片失败: {str(e)}")
                        
                        session.captcha_info = captcha_info
                        return
                except Exception as e:
                    logger.debug(f"检查选择器失败: {selector} - {str(e)}")
    
    async def submit_captcha(
        self,
        session_id: str,
        captcha_answer: Union[str, List[Tuple[int, int]], int]
    ) -> bool:
        """
        提交验证码答案
        
        Args:
            session_id: 会话ID
            captcha_answer: 验证码答案
                - 文本验证码: 字符串
                - 点击验证码: [(x1,y1), (x2,y2)] 坐标列表
                - 滑块验证码: 距离数字
        
        Returns:
            bool: 验证码是否成功
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")
        
        if session.state != LoginState.AWAITING_INPUT:
            raise RuntimeError(f"会话状态不是等待输入: {session.state}")
        
        if session.captcha_attempts >= session.max_captcha_attempts:
            session.state = LoginState.ERROR
            session.error_message = f"验证码尝试次数超过上限"
            return False
        
        session.captcha_attempts += 1
        page = session.page
        
        try:
            if session.captcha_info.captcha_type == CaptchaType.IMAGE:
                # 文本验证码
                selectors = [
                    "input[placeholder*='验证码']",
                    "input[placeholder*='代码']",
                    "input[id*='captcha']",
                ]
                
                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.fill(str(captcha_answer))
                            logger.info(f"填充文本验证码")
                            break
                    except:
                        pass
            
            elif session.captcha_info.captcha_type == CaptchaType.CLICK:
                # 点击验证码
                for x, y in captcha_answer:
                    await page.click(f'[data-x="{x}"][data-y="{y}"]', force=True)
                    await asyncio.sleep(0.3)
                logger.info(f"提交点击验证码坐标")
            
            elif session.captcha_info.captcha_type == CaptchaType.SLIDER:
                # 滑块验证码
                slider = await page.query_selector(".geetest_slider")
                if slider:
                    box = await slider.bounding_box()
                    if box:
                        # 模拟拖动
                        await page.mouse.move(box['x'] + 10, box['y'] + 10)
                        await page.mouse.down()
                        await page.mouse.move(
                            box['x'] + 10 + captcha_answer,
                            box['y'] + 10,
                            steps=10
                        )
                        await page.mouse.up()
                logger.info(f"提交滑块验证码")
            
            # 查找并点击提交按钮
            submit_selectors = [
                "button:has-text('登录')",
                "button:has-text('提交')",
                "button:has-text('确定')",
                "button[type='submit']",
                "input[type='submit']",
            ]
            
            for selector in submit_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        await button.click()
                        logger.info(f"点击登录按钮")
                        break
                except:
                    pass
            
            await asyncio.sleep(2)
            
            # 检查是否仍有验证码
            session.current_step = "checking_captcha"
            await self._check_for_captcha(session)
            
            if session.captcha_detected:
                session.state = LoginState.AWAITING_INPUT
                return False
            
            # 继续登录流程
            session.state = LoginState.IN_PROGRESS
            session.current_step = "continuing_login"
            await self._wait_for_login_success(session)
            
            session.current_step = "extracting_cookies"
            await self._extract_cookies(session)
            
            session.state = LoginState.SUCCESS
            return True
            
        except Exception as e:
            logger.error(f"提交验证码失败: {str(e)}", exc_info=True)
            session.state = LoginState.ERROR
            session.error_message = f"验证码提交失败: {str(e)}"
            return False
    
    async def _wait_for_login_success(
        self,
        session: LoginSession,
        timeout: int = 10
    ):
        """
        等待登录成功
        
        判断标准：
        1. URL变化（离开登录页）
        2. 页面内容变化（出现用户信息或面板）
        3. 特定元素出现（签到按钮、个人中心等）
        """
        page = session.page
        original_url = page.url
        
        # 尝试找登录成功的标志
        success_indicators = [
            "text=个人中心",
            "text=我的",
            "text=用户中心",
            "text=签到",
            "[class*='user-info']",
            "[class*='dashboard']",
            "[class*='panel']",
        ]
        
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            try:
                # 检查URL是否变化
                if page.url != original_url and "login" not in page.url.lower():
                    logger.info(f"URL已变化，判定为登录成功")
                    return
                
                # 检查成功指示符
                for indicator in success_indicators:
                    try:
                        element = await page.query_selector(indicator)
                        if element:
                            logger.info(f"找到成功指示符: {indicator}")
                            return
                    except:
                        pass
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"检查登录状态时出错: {str(e)}")
                await asyncio.sleep(0.5)
        
        logger.warning(f"登录超时未能确认成功")
    
    async def _extract_cookies(self, session: LoginSession):
        """提取登录后的Cookie"""
        page = session.page
        
        try:
            # 获取所有cookies
            context_cookies = await session.context.cookies()
            
            for cookie in context_cookies:
                session.cookies[cookie['name']] = cookie['value']
            
            logger.info(f"提取了 {len(session.cookies)} 个Cookie")
            
        except Exception as e:
            logger.error(f"提取Cookie失败: {str(e)}")
            raise
    
    async def get_session_status(self, session_id: str) -> Dict:
        """获取会话状态"""
        session = self.sessions.get(session_id)
        
        if not session:
            return {
                "status": "error",
                "message": "会话不存在"
            }
        
        # 检查会话是否过期
        if datetime.now() > session.expires_at:
            session.state = LoginState.CANCELLED
            session.error_message = "会话已过期"
            await self.cleanup_session(session_id)
        
        response = {
            "status": session.state.value,
            "session_id": session_id,
            "site_name": session.site_name,
            "current_step": session.current_step,
        }
        
        if session.state == LoginState.ERROR:
            response["message"] = session.error_message
        
        if session.state == LoginState.AWAITING_INPUT:
            response["captcha_info"] = {
                "type": session.captcha_info.captcha_type.value,
                "message": session.captcha_info.message,
                "image_base64": session.captcha_info.image_base64,
                "timeout": session.captcha_info.timeout,
            }
        
        if session.state == LoginState.SUCCESS:
            response["message"] = "登录成功"
        
        return response
    
    async def cleanup_session(self, session_id: str):
        """清理会话"""
        session = self.sessions.pop(session_id, None)
        
        if session:
            try:
                if session.page:
                    await session.page.close()
                if session.context:
                    await session.context.close()
            except Exception as e:
                logger.error(f"清理会话失败: {str(e)}")
            
            logger.info(f"会话已清理: {session_id}")
    
    async def cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_ids = [
            session_id for session_id, session in self.sessions.items()
            if datetime.now() > session.expires_at
        ]
        
        for session_id in expired_ids:
            await self.cleanup_session(session_id)
        
        if expired_ids:
            logger.info(f"清理了 {len(expired_ids)} 个过期会话")
