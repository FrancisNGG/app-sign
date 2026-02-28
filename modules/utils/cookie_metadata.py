# -*- coding: utf-8 -*-
"""
Cookie 元数据管理模块 - 追踪 Cookie 的来源、更新时间、有效期
"""
import datetime
from typing import Dict, Optional, Any


class CookieMetadata:
    """Cookie 元数据类"""
    
    def __init__(self, data: Dict[str, Any] = None):
        """
        初始化元数据
        
        Args:
            data: 元数据字典，包含以下字段：
                - last_updated: 最后更新时间 (ISO 8601 格式)
                - source: 来源 (playwright/cookiecloud/manual)
                - valid_until: 有效期截止时间 (ISO 8601 格式)
                - refresh_attempts: 刷新尝试次数
        """
        if data is None:
            data = {}
        
        self.last_updated = data.get('last_updated')
        self.source = data.get('source', 'unknown')
        self.valid_until = data.get('valid_until')
        self.refresh_attempts = data.get('refresh_attempts', 0)
    
    @staticmethod
    def create_from_playwright(valid_hours: float = 2.0) -> 'CookieMetadata':
        """
        创建 Playwright 刷新的元数据
        
        Args:
            valid_hours: 有效期（小时），默认 2 小时
        
        Returns:
            CookieMetadata 对象
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        valid_until = now + datetime.timedelta(hours=valid_hours)
        
        return CookieMetadata({
            'last_updated': now.isoformat(),
            'source': 'playwright',
            'valid_until': valid_until.isoformat(),
            'refresh_attempts': 0
        })
    
    @staticmethod
    def create_from_cookiecloud(valid_hours: float = 24.0) -> 'CookieMetadata':
        """
        创建 CookieCloud 同步的元数据
        
        Args:
            valid_hours: 有效期（小时），默认 24 小时
        
        Returns:
            CookieMetadata 对象
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        valid_until = now + datetime.timedelta(hours=valid_hours)
        
        return CookieMetadata({
            'last_updated': now.isoformat(),
            'source': 'cookiecloud',
            'valid_until': valid_until.isoformat(),
            'refresh_attempts': 0
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'last_updated': self.last_updated,
            'source': self.source,
            'valid_until': self.valid_until,
            'refresh_attempts': self.refresh_attempts
        }
    
    def is_valid(self, now: Optional[datetime.datetime] = None) -> bool:
        """
        判断 Cookie 是否仍然有效
        
        Args:
            now: 当前时间，默认为系统时间
        
        Returns:
            bool: 是否有效
        """
        if not self.valid_until:
            return False
        
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        elif now.tzinfo is None:
            # 如果 now 没有时区信息，假设为 UTC
            now = now.replace(tzinfo=datetime.timezone.utc)
        
        try:
            valid_until = datetime.datetime.fromisoformat(self.valid_until)
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=datetime.timezone.utc)
            return now < valid_until
        except Exception:
            return False
    
    def get_remaining_hours(self, now: Optional[datetime.datetime] = None) -> float:
        """
        获取剩余有效期（小时）
        
        Args:
            now: 当前时间，默认为系统时间
        
        Returns:
            float: 剩余小时数，负数表示已过期
        """
        if not self.valid_until:
            return 0
        
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=datetime.timezone.utc)
        
        try:
            valid_until = datetime.datetime.fromisoformat(self.valid_until)
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=datetime.timezone.utc)
            delta = valid_until - now
            return delta.total_seconds() / 3600
        except Exception:
            return 0
    
    def increment_attempt(self) -> None:
        """增加一次刷新尝试"""
        self.refresh_attempts = (self.refresh_attempts or 0) + 1
    
    def should_skip_cookiecloud_update(self, now: Optional[datetime.datetime] = None) -> bool:
        """
        判断是否应该跳过 CookieCloud 同步（保护现有 Cookie）
        
        规则：
        - 如果来源是 Playwright 且仍有效 → 保护（不覆盖）
        - 如果剩余有效期 > 30 分钟 → 保护
        - 否则允许 CookieCloud 覆盖
        
        Returns:
            bool: 是否应该跳过更新
        """
        # Playwright Cookie 优先级最高，除非已过期，否则不覆盖
        if self.source == 'playwright':
            return self.is_valid(now)
        
        # 其他来源的 Cookie，如果剩余有效期 > 30 分钟，不覆盖
        remaining = self.get_remaining_hours(now)
        return remaining > 0.5  # 30 分钟 = 0.5 小时
    
    def __repr__(self) -> str:
        """字符串表示"""
        remaining = self.get_remaining_hours()
        if self.is_valid():
            status = f"有效（剩余 {remaining:.1f} 小时）"
        else:
            status = f"已过期（{abs(remaining):.1f} 小时前）"
        
        return (
            f"CookieMetadata(source={self.source}, status={status}, "
            f"updated={self.last_updated}, attempts={self.refresh_attempts})"
        )
