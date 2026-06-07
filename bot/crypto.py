"""
crypto.py — AES-256-GCM 加解密模組
敏感欄位（持股成本、張數、停損、目標）加密儲存
"""

import os
import base64
from typing import Optional, List, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(Exception):
    """加解密失敗"""


def _get_key():
    # type: () -> bytes
    """從環境變數讀取 32 bytes AES 金鑰（64 hex 字元）"""
    key_hex = os.environ.get("ENCRYPT_KEY", "")
    if len(key_hex) != 64:
        raise CryptoError("ENCRYPT_KEY 必須是 64 字元 hex 字串（32 bytes）")
    return bytes.fromhex(key_hex)


def encrypt(value):
    # type: (str) -> str
    """
    加密字串，回傳 base64 編碼的 nonce+密文。
    每次加密產生不同的隨機 nonce，確保相同輸入輸出不同。
    """
    try:
        key = _get_key()
        nonce = os.urandom(12)  # GCM 標準 nonce 長度
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("utf-8")
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(u"加密失敗：{}".format(e)) from e


def decrypt(value):
    # type: (str) -> str
    """解密 base64 編碼的 nonce+密文，回傳原始字串"""
    try:
        key = _get_key()
        raw = base64.b64decode(value.encode("utf-8"))
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(u"解密失敗：{}".format(e)) from e


def encrypt_fields(data, fields):
    # type: (Dict, List[str]) -> Dict
    """批次加密 dict 中指定欄位（None 值略過），回傳新 dict"""
    result = dict(data)
    for field in fields:
        val = result.get(field)
        if val is not None:
            result[field] = encrypt(str(val))
    return result


def decrypt_fields(data, fields):
    # type: (Dict, List[str]) -> Dict
    """批次解密 dict 中指定欄位（None 值略過），回傳新 dict"""
    result = dict(data)
    for field in fields:
        val = result.get(field)
        if val is not None:
            result[field] = decrypt(str(val))
    return result
