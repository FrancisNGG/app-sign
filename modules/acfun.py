# -*- coding: utf-8 -*-
"""
AcFun签到模块
"""
import requests


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
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.acfun.cn/member/',
        'Cookie': cookie
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        # 1. 访问个人中心页面（预热session）
        print(f"[{name}] 访问个人中心...")
        member_url = 'https://www.acfun.cn/member/'
        member_resp = session.get(member_url, timeout=10)
        
        if member_resp.status_code != 200:
            result_msg = "签到失败: 无法访问个人中心，Cookie可能已过期"
            print(f"[{name}] {result_msg}")
            notify_func(config, name, result_msg)
            return False
        
        # 2. 调用签到接口
        print(f"[{name}] 执行签到...")
        signin_url = 'https://www.acfun.cn/rest/pc-direct/user/signIn'
        signin_resp = session.get(signin_url, timeout=10)
        
        if signin_resp.status_code != 200:
            result_msg = f"签到失败: HTTP {signin_resp.status_code}"
            print(f"[{name}] {result_msg}")
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
                
                print(f"[{name}] {result_msg}")
            
            elif result_code == 1 or 'duplicate' in result.get('msg', '').lower() or '已' in result.get('msg', ''):
                # 已经签到过
                msg = result.get('msg', '今日已签到')
                result_msg = f"{msg}"
                if balance_info:
                    result_msg += f"\n{balance_info}"
                print(f"[{name}] {result_msg}")
            
            else:
                # 其他错误
                msg = result.get('msg', '未知错误')
                host_msg = result.get('host-msg', '')
                error_info = f"{msg} {host_msg}".strip()
                result_msg = f"签到失败: {error_info}"
                print(f"[{name}] {result_msg}")
        
        except ValueError:
            # 无法解析JSON
            result_msg = "签到失败: 返回数据格式异常"
            print(f"[{name}] {result_msg}")
            print(f"[{name}] 响应内容: {signin_resp.text[:200]}")
        
        notify_func(config, name, result_msg)
        return "失败" not in result_msg
        
    except requests.RequestException as e:
        result_msg = f"签到失败: 网络请求异常 - {e}"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
    except Exception as e:
        result_msg = f"签到失败: {e}"
        print(f"[{name}] {result_msg}")
        notify_func(config, name, result_msg)
        return False
