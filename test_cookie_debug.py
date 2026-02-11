#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cookie 调试脚本 - 测试恩山论坛 Cookie 是否有效
"""
import yaml
import requests
import re


def main():
    print("\n" + "="*60)
    print("🔍 恩山论坛 Cookie 调试")
    print("="*60 + "\n")
    
    # 加载配置
    with open('config/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 查找恩山论坛配置
    for site in config['sites']:
        if '恩山' in site['name']:
            cookie_raw = site['cookie']
            base_url = site['base_url']
            
            print(f"站点: {site['name']}")
            print(f"URL: {base_url}")
            print(f"Cookie 长度: {len(cookie_raw)} 字符")
            
            # 检查 Cookie 中是否有换行符
            if '\n' in cookie_raw:
                print("⚠️  警告: Cookie 包含换行符")
                cookie_raw = cookie_raw.replace('\n', ' ')
            
            # 解析 Cookie
            cookies = {}
            for item in cookie_raw.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    cookies[k] = v
            
            print(f"\n解析后 Cookie 数量: {len(cookies)}")
            print(f"\n关键 Cookie 检查:")
            for key in ['rHEX_2132_auth', 'rHEX_2132_saltkey', 'rHEX_2132_sid']:
                if key in cookies:
                    value = cookies[key]
                    display = value[:30] + '...' if len(value) > 30 else value
                    print(f"  ✅ {key}: {display} (长度: {len(value)})")
                else:
                    print(f"  ❌ {key}: 未找到")
            
            # 测试访问
            print(f"\n{'='*60}")
            print("🌐 测试访问恩山论坛")
            print("="*60 + "\n")
            
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            
            try:
                print("正在访问首页...")
                res = requests.get(
                    base_url,
                    cookies=cookies,
                    headers={'User-Agent': ua},
                    timeout=10,
                    allow_redirects=True
                )
                
                print(f"✅ 状态码: {res.status_code}")
                print(f"   最终URL: {res.url}")
                
                # 检查是否被重定向到登录页
                if 'login' in res.url.lower():
                    print("\n❌ 被重定向到登录页，Cookie 已失效")
                    return
                
                # 查找 formhash
                print("\n查找 formhash...")
                fh = re.search(r'name="formhash"\s+value="([^"]+)"', res.text)
                
                if fh:
                    formhash = fh.group(1)
                    print(f"✅ 找到 formhash: {formhash}")
                    print("\n✅ Cookie 有效！可以进行签到操作")
                else:
                    print(f"❌ 未找到 formhash")
                    
                    # 检查页面内容
                    print("\n页面分析:")
                    
                    # 标题
                    title = re.search(r'<title>(.*?)</title>', res.text)
                    if title:
                        print(f"  页面标题: {title.group(1)}")
                    
                    # 检查是否需要登录
                    if '登录' in res.text:
                        print(f"  ⚠️  页面包含'登录'关键字")
                    
                    if 'login' in res.text.lower():
                        print(f"  ⚠️  页面包含'login'关键字")
                    
                    # 检查是否有用户信息
                    if '退出' in res.text or 'logout' in res.text.lower():
                        print(f"  ✅ 页面包含'退出'关键字，说明已登录")
                    
                    # 保存页面用于调试
                    with open('debug_right_response.html', 'w', encoding='utf-8') as f:
                        f.write(res.text)
                    print(f"\n  📄 页面已保存到 debug_right_response.html")
                    
            except requests.RequestException as e:
                print(f"❌ 访问失败: {e}")
            except Exception as e:
                print(f"❌ 发生错误: {e}")
                import traceback
                traceback.print_exc()
            
            break


if __name__ == '__main__':
    main()
