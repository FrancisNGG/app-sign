# -*- coding: utf-8 -*-
"""
Playwright 浏览器管理模块 - 全局浏览器实例管理

改进：
- 容器启动时初始化一个全局浏览器实例
- 所有登录都在同一个浏览器中打开新标签页
- 浏览器数据和缓存存放在 /app/cache 目录
- 减少浏览器启动开销
"""
import asyncio
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Callable, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from ..utils.cookie_sync import load_config, save_config

# 全局浏览器实例
_global_browser: Optional[Browser] = None
_global_context: Optional[BrowserContext] = None
_global_playwright = None
_init_lock = threading.Lock()


class BrowserManager:
    """
    Playwright浏览器管理器 - 全局浏览器单例模式
    所有登录操作都在同一个浏览器实例中进行，通过新建标签页支持多个站点
    """
    
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        """初始化管理器"""
        self.log_callback = log_callback or print
        self.current_page: Optional[Page] = None
        self.site_config = None
        self.cookies = []
        
    def _log(self, message: str):
        """输出日志"""
        self.log_callback(message)
    
    @staticmethod
    async def initialize_global_browser():
        """
        初始化全局浏览器实例（容器启动时调用）
        """
        global _global_browser, _global_context, _global_playwright

        with _init_lock:
            if _global_browser is not None:
                return  # 已初始化

            try:
                # 创建缓存目录（支持 Docker /app/cache 和本地相对路径）
                _module_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                cache_dir = os.environ.get('APP_CACHE_DIR', os.path.join(_module_root, 'cache'))
                profile_dir = os.path.join(cache_dir, 'profile')
                Path(profile_dir).mkdir(parents=True, exist_ok=True)

                print("📦 初始化全局浏览器实例")
                print(f"   缓存目录: {profile_dir}")

                _global_playwright = await async_playwright().start()

                # 解析分辨率
                resolution = os.environ.get('RESOLUTION', '1920x1080x24')
                try:
                    width_str, height_str, _ = resolution.split('x')
                    width = int(width_str)
                    height = int(height_str)
                except Exception:
                    width = 1920
                    height = 1080

                # 清理残留锁文件，避免 profile 被误判占用
                for lock_name in ['SingletonLock', 'SingletonCookie', 'SingletonSocket', 'Singleton']:
                    lock_path = os.path.join(profile_dir, lock_name)
                    if os.path.exists(lock_path):
                        try:
                            os.remove(lock_path)
                        except Exception:
                            pass

                # 启动持久化上下文（数据与缓存写入 /app/cache/profile）
                _global_context = await _global_playwright.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    viewport=None,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        f'--window-size={width},{height}',
                        '--start-maximized',
                    ]
                )

                _global_browser = _global_context.browser

                print("✅ 全局浏览器实例初始化成功")

                return _global_browser

            except Exception as e:
                print(f"❌ 初始化全局浏览器失败: {e}")
                _global_browser = None
                _global_context = None
                raise
    
    @staticmethod
    async def close_global_browser():
        """关闭全局浏览器实例"""
        global _global_browser, _global_context, _global_playwright
        
        try:
            if _global_context:
                await _global_context.close()
            if _global_browser:
                await _global_browser.close()
            if _global_playwright:
                await _global_playwright.stop()
            
            _global_context = None
            _global_browser = None
            _global_playwright = None
            print("✅ 全局浏览器已关闭")
        except Exception as e:
            print(f"⚠️  关闭浏览器时出错: {e}")
    
    async def start_browser_for_site(self, site_name: str, base_url: str, headless: bool = True) -> Dict:
        """
        在全局浏览器中为网站创建新标签页
        
        Args:
            site_name: 站点名称
            base_url: 网站URL
            headless: 忽略此参数（保持兼容性）
            
        Returns:
            dict: 操作结果
        """
        global _global_browser, _global_context
        
        try:
            # 确保全局浏览器已初始化
            if _global_browser is None or _global_context is None:
                self._log(f"❌ 全局浏览器未初始化")
                return {
                    'status': 'error',
                    'message': '浏览器未初始化'
                }
            
            self._log(f"📱 在全局浏览器中打开新标签页: {site_name}")
            self._log(f"🌐 导航到: {base_url}")
            
            # 创建新标签页
            self.current_page = await _global_context.new_page()

            # 尝试最大化窗口以占满VNC桌面
            try:
                await asyncio.sleep(0.5)
                await asyncio.create_subprocess_exec(
                    'wmctrl',
                    '-r',
                    ':ACTIVE:',
                    '-b',
                    'add,maximized_vert,maximized_horz'
                )
            except Exception:
                pass
            
            # 导航到网站（较宽松的等待时间）
            try:
                await self.current_page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                self._log(f"⚠️  页面加载超时，但继续: {str(e)}")
            
            self._log(f"✅ 标签页已打开")
            
            self.site_config = {'name': site_name, 'base_url': base_url}
            
            return {
                'status': 'success',
                'message': f'已为 {site_name} 打开新标签页，请在VNC中登录',
                'site_name': site_name,
                'vnc_enabled': True
            }
            
        except Exception as e:
            self._log(f"❌ 打开标签页失败: {str(e)}")
            import traceback
            self._log(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'打开标签页失败: {str(e)}'
            }
    
    async def manual_confirm_login(self) -> Dict:
        """
        用户登录完成，提取Cookie
        """
        try:
            if self.current_page is None:
                return {
                    'status': 'error',
                    'message': '没有活跃的标签页'
                }
            
            self._log(f"💾 提取Cookie中...")
            
            # 等待一秒，确保登录完成
            await asyncio.sleep(1)
            
            # 获取所有 Cookie
            cookies = await self.current_page.context.cookies()
            self.cookies = cookies
            
            self._log(f"✅ 成功提取 {len(cookies)} 个Cookie")
            
            return {
                'status': 'success',
                'message': f'已提取 {len(cookies)} 个Cookie',
                'cookies_count': len(cookies)
            }
            
        except Exception as e:
            self._log(f"❌ Cookie提取失败: {str(e)}")
            import traceback
            self._log(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'提取失败: {str(e)}'
            }
    
    async def save_cookies_to_config(self, site_name: str) -> Dict:
        """
        保存Cookie到config.yaml
        """
        try:
            if not self.cookies:
                return {
                    'status': 'error',
                    'message': '没有可保存的Cookie'
                }
            
            self._log(f"📝 保存Cookie到config.yaml...")
            
            config, encoding = load_config('config/config.yaml')
            if config is None:
                return {
                    'status': 'error',
                    'message': '无法读取config文件'
                }
            
            # 查找对应的站点配置
            sites = config.get('sites', [])
            target_site = None
            for site in sites:
                if site.get('name') == site_name:
                    target_site = site
                    break
            
            if not target_site:
                return {
                    'status': 'error',
                    'message': f'找不到站点: {site_name}'
                }
            
            # 格式化Cookie字符串
            cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in self.cookies])
            
            # 更新站点配置
            target_site['cookie'] = cookie_str
            target_site['last_updated'] = datetime.now().isoformat()
            
            # 保存配置
            save_config(config, 'config/config.yaml', encoding)
            
            self._log(f"✅ Cookie已保存")
            self._log(f"   站点: {site_name}")
            self._log(f"   Cookie数量: {len(self.cookies)}")
            
            return {
                'status': 'success',
                'message': f'已保存 {len(self.cookies)} 个Cookie',
                'site_name': site_name,
                'cookies_count': len(self.cookies)
            }
            
        except Exception as e:
            self._log(f"❌ 保存失败: {str(e)}")
            import traceback
            self._log(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'保存失败: {str(e)}'
            }
    
    async def close_current_page(self) -> Dict:
        """关闭当前标签页"""
        try:
            if self.current_page:
                await self.current_page.close()
                self.current_page = None
                self._log("✅ 标签页已关闭")
            
            return {
                'status': 'success',
                'message': '标签页已关闭'
            }
            
        except Exception as e:
            self._log(f"❌ 关闭标签页失败: {str(e)}")
            return {
                'status': 'error',
                'message': f'关闭失败: {str(e)}'
            }
    
    async def stop_browser(self):
        """关闭当前标签页（保持兼容性）"""
        return await self.close_current_page()

    # 鼠标和键盘控制方法
    async def click(self, x: int, y: int) -> Dict:
        """在坐标点击"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.mouse.click(x, y)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def input_text(self, selector: str, text: str) -> Dict:
        """在元素中输入文本"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.fill(selector, text)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def type_text(self, text: str) -> Dict:
        """逐字符键入文本"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.keyboard.type(text)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def press_key(self, key: str) -> Dict:
        """按下键盘按键"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.keyboard.press(key)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def scroll(self, dx: int, dy: int) -> Dict:
        """滚动页面"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.mouse.wheel(dx, dy)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def double_click(self, x: int, y: int) -> Dict:
        """双击"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.mouse.dblclick(x, y)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    async def hover(self, x: int, y: int) -> Dict:
        """鼠标悬停"""
        try:
            if not self.current_page:
                return {'status': 'error', 'message': '没有活跃标签页'}
            await self.current_page.mouse.move(x, y)
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
