"""AES-CBC 密码解密工具。

前端使用 CryptoJS AES-CBC 加密明文密码后传输。
加密格式：iv_base64:ciphertext_base64（带 URL 安全编码）
此模块使用配置中的共享密钥解密密码。
"""
from __future__ import annotations

import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from app.config import settings


def _load_key() -> bytes:
    """从设置中加载 AES 密钥（UTF-8 字符串，16/24/32 字符）。"""
    key = settings.AES_SECRET_KEY
    if len(key) not in (16, 24, 32):
        raise ValueError(f"AES 密钥长度必须为 16/24/32 字符，当前: {len(key)}")
    return key.encode("utf-8")


def _url_safe_base64_decode(data: str) -> bytes:
    """解码 URL 安全的 Base64 字符串。
    
    前端将 +/-/= 替换为 -/_/空，这里还原并解码。
    """
    # 还原 URL 安全编码
    data = data.replace("-", "+").replace("_", "/")
    # 补齐 Base64 填充
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.b64decode(data)


def decrypt_password(encrypted_data: str) -> str:
    """解密 AES-CBC 加密、PKCS7 填充的密码。

    参数：
        encrypted_data: 前端加密生成的字符串，格式为 iv_base64:ciphertext_base64
                        （带 URL 安全编码）

    返回：
        明文密码字符串（UTF-8）。

    异常：
        ValueError: 如果解密或去填充失败（无效的密文）。
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
