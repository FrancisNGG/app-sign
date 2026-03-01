# -*- coding: utf-8 -*-
"""
AcFun签到模块
"""
import requests
from .. import safe_print, get_user_agent


def get_balance(session):
    """获取用户余额信息"""
    try:
        # 获取用户信息
        info_url = 'https://www.acfun.cn/rest/pc-direct/user/personalInfo'
        info_resp = session.get(info_url, timeout=10)
        
        if info_resp.status_code == 200:
            info_result = info_resp.json()
            if info_result.get('result') == 0:
                data = info_result.get('info', {})
                banana = data.get('banana', 0)  # 香蕉
                gold_banana = data.get('goldBanana', 0)  # 金香蕉
                
                # 获取AC币
                coin_url = 'https://www.acfun.cn/rest/pc-direct/payment/acCoin'
                coin_resp = session.get(coin_url, timeout=10)
                
                ac_coin = 0
                if coin_resp.status_code == 200:
                    coin_result = coin_resp.json()
                    if coin_result.get('result') == 0:
                        ac_coin = coin_result.get('acCoin', 0)
                
                return f"余额: {banana}香蕉, {gold_banana}金香蕉, {ac_coin}AC币"
    except:
        pass
    return None


def sign_in(site, config, notify_func):
    """
    AcFun签到
    
    签到流程：
    1. 访问个人中心页面
    2. 调用签到接口
    3. 获取签到结果
    
    Args:
        site: 站点配置
        config: 全局配置
        notify_func: 通知函数
    """
    name = site.get('name', 'AcFun')
    cookie = site.get('cookie', '')
    
    if not cookie:
        result_msg = "签到失败: 缺少Cookie"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    
    headers = {
        'User-Agent': get_user_agent(config),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.acfun.cn/member/',
        'Cookie': cookie
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        # 1. 访问个人中心页面（预热session）
        safe_print(f"[{name}] 访问个人中心...")
        member_url = 'https://www.acfun.cn/member/'
        member_resp = session.get(member_url, timeout=10)
        
        if member_resp.status_code != 200:
            result_msg = "签到失败: 无法访问个人中心，Cookie可能已过期"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 2. 调用签到接口
        safe_print(f"[{name}] 执行签到...")
        signin_url = 'https://www.acfun.cn/rest/pc-direct/user/signIn'
        signin_resp = session.get(signin_url, timeout=10)
        
        if signin_resp.status_code != 200:
            result_msg = f"签到失败: HTTP {signin_resp.status_code}"
            safe_print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 3. 解析签到结果
        try:
            result = signin_resp.json()
            
            # 获取用户余额信息（无论签到成功与否都获取）
            balance_info = get_balance(session)
            
            # 检查返回结果
            result_code = result.get('result')
            
            if result_code == 0:
                # 签到成功
                award_coin = result.get('awardCoin', 0)
                award_banana = result.get('awardBanana', 0)
                
                result_msg = f"签到成功\n奖励: {award_coin}金币, {award_banana}香蕉"
                if balance_info:
                    result_msg += f"\n{balance_info}"
                
                safe_print(f"[{name}] {result_msg}")
            
            elif result_code == 1 or 'duplicate' in result.get('msg', '').lower() or '已' in result.get('msg', ''):
                # 已经签到过
                msg = result.get('msg', '今日已签到')
                result_msg = f"{msg}"
                if balance_info:
                    result_msg += f"\n{balance_info}"
                safe_print(f"[{name}] {result_msg}")
            
            else:
                # 其他错误
                msg = result.get('msg', '未知错误')
                host_msg = result.get('host-msg', '')
                error_info = f"{msg} {host_msg}".strip()
                result_msg = f"签到失败: {error_info}"
                safe_print(f"[{name}] {result_msg}")
        
        except ValueError:
            # 无法解析JSON
            result_msg = "签到失败: 返回数据格式异常"
            safe_print(f"[{name}] {result_msg}")
            safe_print(f"[{name}] 响应内容: {signin_resp.text[:200]}")
        
        notify_func(config, name, result_msg)
        return "失败" not in result_msg
        
    except requests.RequestException as e:
        result_msg = f"签到失败: 网络请求异常 - {e}"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    except Exception as e:
        result_msg = f"签到失败: {e}"
        safe_print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False


# ==================== 异步API适配函数 ====================
async def sign(base_url, cookies, **kwargs):
    """
    异步签到函数 - 用于Web API调用
    
    Args:
        base_url: 网站URL
        cookies: Cookie字符串
        **kwargs: 其他参数
        
    Returns:
        str: 签到结果消息
    """
    if not cookies:
        return "签到失败：缺少Cookie"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://www.acfun.cn/member/',
            'Cookie': cookies
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # 运行在线程中执行（避免阻塞）
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _sign_sync,
            session,
            base_url,
            headers
        )
        
        return result
        
    except Exception as e:
        return f"签到失败：{str(e)}"


def _sign_sync(session, base_url, headers):
    """同步签到实现"""
    try:
        # 访问个人中心页面
        session.get(f'{base_url}member/', timeout=10)
        
        # 调用签到接口
        sign_url = 'https://www.acfun.cn/rest/pc-direct/user/checkIn'
        sign_resp = session.post(sign_url, json={}, timeout=10)
        
        if sign_resp.status_code == 200:
            result = sign_resp.json()
            if result.get('result') == 0:
                reward = result.get('info', {}).get('reward', '未知奖励')
                return f"签到成功！获得奖励：{reward}"
            else:
                msg = result.get('error_msg', '签到失败')
                return f"签到失败：{msg}"
        else:
            return f"签到失败：HTTP {sign_resp.status_code}"
            
    except Exception as e:
        return f"签到异常：{str(e)}"
