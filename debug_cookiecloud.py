#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CookieCloud 配置调试脚本
用于诊断 CookieCloud 配置和连接问题
"""
import yaml
import json
import requests
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def main():
    print("\n" + "="*60)
    print("🔍 CookieCloud 配置调试工具")
    print("="*60 + "\n")
    
    # 1. 读取配置
    print("📋 步骤 1: 读取配置文件")
    print("-"*60)
    try:
        with open('config/config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        cookiecloud = config.get('cookiecloud', {})
        server = cookiecloud.get('server', '')
        uuid = cookiecloud.get('uuid', '')
        password = cookiecloud.get('password', '')
        
        print(f"✅ 配置文件读取成功")
        print(f"   Server: {server}")
        print(f"   UUID: {uuid}")
        print(f"   Password: {password}")
        print(f"   Password 长度: {len(password)} 字符")
        print(f"   UUID 长度: {len(uuid)} 字符\n")
        
        if not server or not uuid or not password:
            print("❌ 配置不完整，请检查 config.yaml")
            return
            
    except Exception as e:
        print(f"❌ 读取配置失败: {e}")
        return
    
    # 2. 测试服务器连接
    print("📡 步骤 2: 测试服务器连接")
    print("-"*60)
    try:
        server = server.rstrip('/')
        url = f"{server}/get/{uuid}"
        print(f"   请求 URL: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"✅ 服务器响应: HTTP {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ 服务器返回错误状态码")
            print(f"   响应内容: {response.text[:200]}")
            return
        
        data = response.json()
        print(f"   响应数据键: {list(data.keys())}")
        
        if 'encrypted' not in data:
            print(f"❌ 响应中没有 'encrypted' 字段")
            print(f"   完整响应: {json.dumps(data, indent=2)}")
            return
        
        encrypted = data['encrypted']
        print(f"✅ 获取到加密数据")
        print(f"   加密数据长度: {len(encrypted)} 字符")
        print(f"   加密数据前50字符: {encrypted[:50]}...\n")
        
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时，请检查服务器地址和网络连接")
        return
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器，请检查服务器地址")
        return
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 测试密钥生成（OpenSSL 方式）
    print("🔑 步骤 3: 测试密钥生成（OpenSSL EVP_BytesToKey）")
    print("-"*60)
    try:
        # 先 Base64 解码查看格式
        encrypted_bytes = base64.b64decode(encrypted)
        print(f"   加密数据前8字节: {encrypted_bytes[:8]}")
        print(f"   是否为 OpenSSL 格式: {encrypted_bytes[:8] == b'Salted__'}")
        
        if encrypted_bytes[:8] != b'Salted__':
            print(f"❌ 不是 OpenSSL 格式")
            return
        
        # 提取 Salt
        salt = encrypted_bytes[8:16]
        print(f"✅ OpenSSL 格式确认")
        print(f"   Salt: {salt.hex()}")
        print(f"   Salt 长度: {len(salt)} 字节")
        
        # 使用 EVP_BytesToKey 派生密钥
        key_string = f"{uuid}-{password}"
        print(f"   密钥字符串: {key_string}")
        
        # EVP_BytesToKey 算法
        def evp_bytes_to_key(password_bytes, salt, key_len=32, iv_len=16):
            m = []
            i = 0
            while len(b''.join(m)) < (key_len + iv_len):
                md = hashlib.md5()
                data = password_bytes
                if i > 0:
                    data = m[i - 1] + password_bytes
                md.update(data + salt)
                m.append(md.digest())
                i += 1
            ms = b''.join(m)
            return ms[:key_len], ms[key_len:key_len + iv_len]
        
        key, iv = evp_bytes_to_key(key_string.encode(), salt, 32, 16)
        print(f"✅ 密钥派生成功")
        print(f"   Key: {key.hex()}")
        print(f"   Key 长度: {len(key)} 字节")
        print(f"   IV: {iv.hex()}")
        print(f"   IV 长度: {len(iv)} 字节\n")
        
    except Exception as e:
        print(f"❌ 密钥生成失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 测试解密（OpenSSL 方式）
    print("🔓 步骤 4: 测试解密（OpenSSL AES-256-CBC）")
    print("-"*60)
    try:
        ciphertext = encrypted_bytes[16:]
        print(f"   密文长度: {len(ciphertext)} 字节")
        
        # AES-256-CBC 解密
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        print(f"✅ AES 解密完成")
        print(f"   解密后长度: {len(decrypted)} 字节")
        
        # 检查填充
        padding_length = decrypted[-1]
        print(f"   填充长度字节值: {padding_length}")
        print(f"   最后{min(20, len(decrypted))}字节: {decrypted[-min(20, len(decrypted)):].hex()}")
        
        if padding_length > 16 or padding_length == 0:
            print(f"❌ 无效的填充长度: {padding_length}")
            print(f"\n   这说明解密密钥不正确！")
            print(f"   可能的原因：")
            print(f"   1. UUID 不正确")
            print(f"   2. Password 不正确")
            print(f"   3. 服务器使用了不同的加密方式")
            print(f"\n   解密后的前100字节（十六进制）：")
            print(f"   {decrypted[:100].hex()}")
            print(f"\n   解密后的前100字节（尝试UTF-8解码）：")
            try:
                print(f"   {decrypted[:100].decode('utf-8', errors='ignore')}")
            except:
                print(f"   无法解码")
            return
        
        # 去除填充
        decrypted = decrypted[:-padding_length]
        print(f"✅ 填充长度有效，去除填充后长度: {len(decrypted)} 字节")
        
        # 尝试解码
        decrypted_text = decrypted.decode('utf-8')
        print(f"✅ UTF-8 解码成功")
        print(f"   解密文本前200字符: {decrypted_text[:200]}...")
        
        # 解析 JSON
        data = json.loads(decrypted_text)
        print(f"✅ JSON 解析成功")
        
        # 检查 cookie_data
        if 'cookie_data' in data:
            cookies = data['cookie_data']
            print(f"✅ 找到 cookie_data")
            print(f"   Cookie 数量: {len(cookies)}")
            
            # 显示域名列表
            domains = sorted(set(c.get('domain', '') for c in cookies))
            print(f"   域名数量: {len(domains)}")
            print(f"\n   域名列表（前20个）:")
            for d in domains[:20]:
                count = len([c for c in cookies if c.get('domain', '') == d])
                print(f"     - {d} ({count} cookies)")
            
            if len(domains) > 20:
                print(f"     ... 还有 {len(domains) - 20} 个域名")
                
            print(f"\n✅ CookieCloud 配置完全正确！")
        else:
            print(f"⚠️  解密成功但未找到 cookie_data")
            print(f"   数据键: {list(data.keys())}")
        
    except base64.binascii.Error as e:
        print(f"❌ Base64 解码失败: {e}")
    except UnicodeDecodeError as e:
        print(f"❌ UTF-8 解码失败: {e}")
        print(f"   这通常意味着解密密钥不正确")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
    except Exception as e:
        print(f"❌ 解密过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
