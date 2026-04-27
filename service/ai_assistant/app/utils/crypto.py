"""
AES-CBC 密码解密工具模块

功能介绍：
-----------
本模块提供后端 AES-CBC 解密功能，用于解密前端传输的加密密码。

加密格式：
    iv_base64:ciphertext_base64（URL-Safe Base64 编码）

前端使用 CryptoJS 进行 AES-CBC 加密，后端使用 pycryptodome 解密。
密钥长度支持 16/24/32 字节（对应 AES-128/192/256）。

主要函数：
- decrypt_password(): 解密前端传来的加密密码字符串
"""
from __future__ import annotations

import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from app.config import settings


def _load_key() -> bytes:
    """从应用配置加载 AES 密钥并编码为字节，校验长度是否为 16/24/32 字节。"""
    key = settings.AES_SECRET_KEY
    if len(key) not in (16, 24, 32):
        raise ValueError(f"AES 密钥长度必须为 16/24/32 字符，当前: {len(key)}")
    return key.encode("utf-8")


def _url_safe_base64_decode(data: str) -> bytes:
    """
    解码 URL 安全的 Base64 字符串。
    
    还原规则：
        - 将 '-' 还原为 '+'
        - 将 '_' 还原为 '/'
        - 补齐 Base64 填充符 '='
    """
    # 还原 URL 安全编码
    data = data.replace("-", "+").replace("_", "/")
    # 补齐 Base64 填充
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.b64decode(data)


def decrypt_password(encrypted_data: str) -> str:
    """
    解密前端传来的 AES-CBC 加密密码。

    参数:
        encrypted_data: 前端加密字符串，格式为 iv_base64:ciphertext_base64。

    返回:
        明文密码字符串（UTF-8）。

    异常:
        ValueError: 格式无效或解密失败。
    """
    try:
        if ":" not in encrypted_data:
            raise ValueError("无效的加密格式，缺少 IV 分隔符")
        
        iv_part, ciphertext_part = encrypted_data.split(":", 1)
        iv = _url_safe_base64_decode(iv_part)
        ciphertext = _url_safe_base64_decode(ciphertext_part)
        
        if len(iv) != 16:
            raise ValueError(f"IV 长度必须为 16 字节，当前: {len(iv)}")
    except Exception as exc:
        raise ValueError("无效的加密数据格式") from exc

    try:
        cipher = AES.new(_load_key(), AES.MODE_CBC, iv=iv)
        padded = cipher.decrypt(ciphertext)
        plaintext = unpad(padded, AES.block_size).decode("utf-8")
    except (ValueError, KeyError) as exc:
        raise ValueError("AES 解密失败") from exc

    return plaintext
