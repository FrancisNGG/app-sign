# -*- coding: utf-8 -*-
"""
CookieCloud Cookie 同步脚本
从 CookieCloud 服务获取最新的 Cookie 并更新到 config.yaml
保留原有的YAML格式（注释、缩进等）
"""
import json
import requests
import hashlib
import base64
import re
import os
import tempfile
import threading
from datetime import datetime
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# 优先使用 ruamel.yaml 保留格式，否则使用 pyyaml
try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    import yaml
    HAS_RUAMEL = False

# 全局锁：保护config文件的读-修改-写操作，防止并发问题
_config_write_lock = threading.Lock()

# 站点域名映射
DOMAIN_MAPPING = {
    '恩山无线论坛': 'right.com.cn',
    '什么值得买': 'smzdm.com',
    '有道云笔记': 'note.youdao.com',
    '百度贴吧': 'tieba.baidu.com',
    'AcFun': 'acfun.cn',
    '哔哩哔哩': 'bilibili.com'
}



def load_config(config_path='config/config.yaml'):
    """
    加载配置文件，同时保留原有格式信息
    
    使用全局锁保护读操作，防止读取正在被写入的文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        (config_dict, encoding): 配置字典和文件编码
    """
    with _config_write_lock:
        if HAS_RUAMEL:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_obj = YAML()
                    yaml_obj.preserve_quotes = True
                    yaml_obj.default_flow_style = False
                    config = yaml_obj.load(f)
                    return config, 'utf-8'
            except Exception as e:
                print(f"⚠️  ruamel.yaml 加载失败: {e}，使用标准yaml")
        
        # 备用方案：使用标准 PyYAML
        for enc in ['utf-8', 'gbk']:
            try:
                with open(config_path, 'r', encoding=enc) as f:
                    config = yaml.safe_load(f)
                    return config, enc
            except:
                continue
        return None, None


def save_config(config, config_path='config/config.yaml', encoding='utf-8'):
    """
    保存配置文件，优先使用 ruamel.yaml 保留格式与注释

    使用全局锁保护读-修改-写操作，使用临时文件+原子重命名确保文件完整性

    Args:
        config: 配置字典
        config_path: 配置文件路径
        encoding: 文件编码
    """
    with _config_write_lock:
        try:
            # 使用临时文件+原子重命名的方式写入，确保文件不会被损坏
            config_dir = os.path.dirname(config_path) or '.'
            temp_fd, temp_path = tempfile.mkstemp(dir=config_dir, text=True, suffix='.tmp')
            try:
                with os.fdopen(temp_fd, 'w', encoding=encoding) as temp_file:
                    if HAS_RUAMEL:
                        yaml_obj = YAML()
                        yaml_obj.preserve_quotes = True
                        yaml_obj.default_flow_style = False
                        yaml_obj.width = 4096
                        yaml_obj.dump(config, temp_file)
                    else:
                        yaml.safe_dump(
                            config,
                            temp_file,
                            allow_unicode=True,
                            default_flow_style=False,
                            sort_keys=False
                        )

                if os.path.exists(config_path):
                    os.replace(temp_path, config_path)
                else:
                    os.rename(temp_path, config_path)
            except Exception as write_error:
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise write_error

        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            import traceback
            traceback.print_exc()


def decrypt_cookie_data(encrypted_data, uuid, password):
    """
    解密 CookieCloud 数据（CryptoJS AES legacy 格式）
    兼容 CryptoJS.AES.encrypt() 的 OpenSSL 格式
    
    Args:
        encrypted_data: 加密的数据（base64编码，OpenSSL格式：Salted__ + salt + ciphertext）
        uuid: 用户UUID
        password: 用户密码
    
    Returns:
        解密后的JSON数据
    """
    try:
        # Base64 解码
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # 检查 OpenSSL 格式标识 "Salted__"
        if encrypted_bytes[:8] != b'Salted__':
            print(f"❌ 不是有效的 CryptoJS/OpenSSL 加密格式")
            return None
        
        # 提取 Salt（8-16字节）和密文（16字节之后）
        salt = encrypted_bytes[8:16]
        ciphertext = encrypted_bytes[16:]
        
        # 生成密钥材料：MD5(uuid + '-' + password) 前16个字符作为 password_bytes
        key_string = uuid + '-' + password
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        password_bytes = key_hash[:16].encode('utf-8')
        
        # 使用 OpenSSL EVP_BytesToKey 派生 key 和 iv
        # 需要 32字节 key + 16字节 iv = 48字节
        key_iv = b""
        prev = b""
        while len(key_iv) < 48:
            prev = hashlib.md5(prev + password_bytes + salt).digest()
            key_iv += prev
        
        key = key_iv[:32]  # AES-256 需要32字节
        iv = key_iv[32:48]  # IV 需要16字节
        
        # AES-256-CBC 解密
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        
        # 去除PKCS7填充
        padding_length = decrypted[-1]
        if padding_length > 16 or padding_length == 0:
            print(f"❌ 无效的填充长度: {padding_length}")
            print(f"   解密密钥可能不正确，请检查 UUID 和密码")
            return None
        
        decrypted = decrypted[:-padding_length]
        
        # 解析JSON
        return json.loads(decrypted.decode('utf-8'))
        
    except base64.binascii.Error as e:
        print(f"❌ Base64 解码失败: {e}")
        return None
    except UnicodeDecodeError as e:
        print(f"❌ UTF-8 解码失败: {e}")
        print(f"   解密密钥可能不正确，请检查 UUID 和密码")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        return None
    except Exception as e:
        print(f"❌ 解密失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_cookies_from_cloud(server_url, uuid, password):
    """
    从 CookieCloud 获取 Cookie
    
    Args:
        server_url: CookieCloud 服务器地址
        uuid: CookieCloud UUID
        password: CookieCloud 密码
    
    Returns:
        Cookie 数据字典，格式 {域名: [cookie列表]}
    """
    try:
        # 确保服务器地址格式正确
        server_url = server_url.rstrip('/')
        
        # 请求 CookieCloud API
        url = f"{server_url}/get/{uuid}"
        print(f"📡 正在从 CookieCloud 获取数据...")
        print(f"   服务器: {server_url}")
        print(f"   UUID: {uuid[:8]}...{uuid[-8:]}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data or 'encrypted' not in data:
            print("❌ CookieCloud 返回数据格式错误")
            return None
        
        # 解密数据
        print("🔓 正在解密 Cookie 数据...")
        decrypted_data = decrypt_cookie_data(data['encrypted'], uuid, password)
        
        if not decrypted_data:
            return None
        
        # 提取 Cookie
        cookie_data = decrypted_data.get('cookie_data', {})
        print(f"✅ 成功获取 {len(cookie_data)} 个域名的 Cookie")
        
        return cookie_data
    except requests.RequestException as e:
        print(f"❌ 请求 CookieCloud 失败: {e}")
        return None
    except Exception as e:
        print(f"❌ 处理 Cookie 数据失败: {e}")
        return None


def format_cookies_for_domain(cookie_data, domain):
    """
    将指定域名的 Cookie 格式化为字符串
    
    Args:
        cookie_data: CookieCloud 返回的 Cookie 数据
        domain: 目标域名
    
    Returns:
        Cookie 字符串，格式 "key1=value1; key2=value2"
    """
    cookies = []
    
    # 遍历所有域名，查找匹配的 Cookie
    for site_domain, site_cookies in cookie_data.items():
        # 检查域名是否匹配（支持子域名）
        if domain in site_domain or site_domain in domain:
            for cookie in site_cookies:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                if name and value:
                    cookies.append(f"{name}={value}")
    
    return '; '.join(cookies)


def sync_cookies(config_path='config/config.yaml'):
    """
    同步 Cookie 到配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        bool: 同步是否成功
    """
    print(f"\n{'='*60}")
    print("🔄 Cookie 同步任务")
    print(f"{'='*60}\n")
    print(f"⏰ 同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 加载配置
    config, encoding = load_config(config_path)
    if not config:
        print("❌ 无法加载配置文件")
        return False
    
    # 检查 CookieCloud 配置
    cookiecloud_config = config.get('cookiecloud', {})
    server_url = cookiecloud_config.get('server', '')
    uuid = cookiecloud_config.get('uuid', '')
    password = cookiecloud_config.get('password', '')
    
    if not server_url:
        print("❌ 配置文件中缺少 CookieCloud 服务器地址")
        print("   请在 config.yaml 中添加：")
        print("   cookiecloud:")
        print("     server: \"https://cookie.example.com\"  # 或 http://localhost:8088")
        print("     uuid: \"your-uuid\"")
        print("     password: \"your-password\"")
        return False
    
    if not uuid or not password:
        print("❌ 配置文件中缺少 CookieCloud UUID 或密码")
        print("   请在 config.yaml 中添加：")
        print("   cookiecloud:")
        print(f"     server: \"{server_url}\"")
        print("     uuid: \"your-uuid\"")
        print("     password: \"your-password\"")
        return False
    
    # 从 CookieCloud 获取 Cookie
    cookie_data = get_cookies_from_cloud(server_url, uuid, password)
    if not cookie_data:
        print("❌ 获取 Cookie 失败")
        return False
    
    # 更新各个站点的 Cookie
    print(f"\n{'='*60}")
    print("📝 更新站点 Cookie")
    print(f"{'='*60}\n")
    
    updated_count = 0
    sites = config.get('sites', [])
    
    for site in sites:
        site_name = site.get('name', '')
        if site_name not in DOMAIN_MAPPING:
            continue
        
        domain = DOMAIN_MAPPING[site_name]
        new_cookie = format_cookies_for_domain(cookie_data, domain)
        
        if new_cookie:
            old_cookie = site.get('cookie', '')
            if new_cookie != old_cookie:
                site['cookie'] = new_cookie
                updated_count += 1
                print(f"✅ {site_name}: Cookie 已更新")
                print(f"   域名: {domain}")
                print(f"   Cookie 长度: {len(new_cookie)} 字符\n")
            else:
                print(f"ℹ️  {site_name}: Cookie 无变化\n")
        else:
            print(f"⚠️  {site_name}: 未找到匹配的 Cookie\n")
    
    # 保存配置
    if updated_count > 0:
        print(f"{'='*60}")
        print(f"💾 保存配置文件...")
        save_config(config, config_path, encoding)
        print(f"✅ 成功更新 {updated_count} 个站点的 Cookie")
    else:
        print(f"{'='*60}")
        print(f"ℹ️  所有站点 Cookie 都是最新的，无需更新")
    
    print(f"{'='*60}\n")
    return True


def start_sync_task(config, interval_minutes=60):
    """
    启动定期同步任务
    
    Args:
        config: 配置字典
        interval_minutes: 同步间隔时间（分钟）
    """
    import time
    import threading
    
    def sync_loop():
        """同步循环"""
        while True:
            try:
                print(f"\n[Cookie同步] 下次同步将在 {interval_minutes} 分钟后执行")
                time.sleep(interval_minutes * 60)
                
                print(f"\n[Cookie同步] 定时同步任务触发")
                sync_cookies()
                
            except Exception as e:
                print(f"❌ [Cookie同步] 同步失败: {e}")
                import traceback
                traceback.print_exc()
    
    # 启动后台线程
    thread = threading.Thread(target=sync_loop, daemon=True, name="CookieSync")
    thread.start()
    print(f"✅ Cookie 定期同步任务已启动（间隔: {interval_minutes} 分钟）")
    return thread
def main():
    """主函数"""
    try:
        sync_cookies()
    except Exception as e:
        print(f"❌ 同步过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
