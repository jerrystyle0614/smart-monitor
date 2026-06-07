"""test_crypto.py — AES-256-GCM 加解密測試"""
import os
import pytest

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)  # 測試用固定金鑰

from bot.crypto import encrypt, decrypt, encrypt_fields, decrypt_fields, CryptoError


def test_encrypt_decrypt_roundtrip():
    """加密後解密應還原原始值"""
    original = "64.86"
    assert decrypt(encrypt(original)) == original


def test_encrypt_produces_different_output():
    """相同輸入每次加密結果應不同（GCM 隨機 nonce）"""
    v = "900.0"
    assert encrypt(v) != encrypt(v)


def test_decrypt_invalid_raises():
    """解密無效密文應拋出 CryptoError"""
    with pytest.raises(CryptoError):
        decrypt("not-valid-ciphertext")


def test_encrypt_fields():
    """encrypt_fields 只加密指定欄位"""
    data = {"stock_id": "2330", "cost_price": "900.0", "stock_name": "台積電"}
    result = encrypt_fields(data, ["cost_price"])
    assert result["stock_id"] == "2330"
    assert result["stock_name"] == "台積電"
    assert result["cost_price"] != "900.0"
    assert decrypt(result["cost_price"]) == "900.0"


def test_decrypt_fields():
    """decrypt_fields 還原指定欄位"""
    data = {"stock_id": "2330", "cost_price": "900.0"}
    encrypted = encrypt_fields(data, ["cost_price"])
    decrypted = decrypt_fields(encrypted, ["cost_price"])
    assert decrypted["cost_price"] == "900.0"


def test_decrypt_fields_skips_none():
    """decrypt_fields 遇到 None 值應略過不處理"""
    data = {"stop_loss": None, "cost_price": "900.0"}
    encrypted = encrypt_fields(data, ["cost_price"])
    result = decrypt_fields(encrypted, ["cost_price", "stop_loss"])
    assert result["stop_loss"] is None
    assert result["cost_price"] == "900.0"
