"""发布目标配置的字段级加解密。

概念：按平台类型，只加密 config 中的敏感字段，非敏感字段（URL、用户名等）保持明文
模块：core/config_crypto.py
作用：
    - encrypt_config：写库前调用，加密敏感字段
    - decrypt_config：读库后调用，解密敏感字段
怎么写：
    - 用 SENSITIVE_FIELDS 映射定义每个平台要加密的字段
    - headers 是嵌套 dict，整体 JSON 序列化后加密
    - 返回新 dict，不修改入参（避免 SQLAlchemy JSONB 原地修改检测不到）
"""

import json
import logging
from typing import Any

from app.core.crypto import CryptoError, get_crypto_service

logger = logging.getLogger(__name__)


# 各平台需要加密的敏感字段
# key 为 PublishTargetType 的值（大写字符串），value 为字段名列表
SENSITIVE_FIELDS: dict[str, list[str]] = {
    "WORDPRESS": ["app_password"],
    "WECHAT_MP": ["app_secret"],
    "WEIBO": ["cookie"],
    "WEBHOOK": [],  # headers 单独处理（嵌套 dict）
}

# 需要整体 JSON 加密的嵌套字段（值为 dict/list）
# key 为平台类型，value 为字段名列表
NESTED_SENSITIVE_FIELDS: dict[str, list[str]] = {
    "WEBHOOK": ["headers"],
}


def _normalize_type(target_type: Any) -> str:
    """把 PublishTargetType 枚举或字符串统一成大写字符串。"""
    if hasattr(target_type, "value"):
        return str(target_type.value).upper()
    return str(target_type).upper()


def encrypt_config(target_type: Any, config: dict) -> dict:
    """加密配置中的敏感字段（写库前调用）。

    Args:
        target_type: 发布目标类型（PublishTargetType 或字符串）
        config: 原始配置 dict

    Returns:
        新的 config dict，敏感字段已加密（非敏感字段不变）。
        返回新 dict，不修改入参。

    Raises:
        CryptoError: 加密失败
    """
    if not config:
        return config

    type_key = _normalize_type(target_type)
    crypto = get_crypto_service()
    new_config = dict(config)  # 浅拷贝，避免修改入参

    # 1. 加密普通字符串敏感字段
    for field in SENSITIVE_FIELDS.get(type_key, []):
        value = new_config.get(field)
        if value and isinstance(value, str):
            new_config[field] = crypto.encrypt(value)

    # 2. 加密嵌套字段（headers 等，JSON 序列化后加密）
    for field in NESTED_SENSITIVE_FIELDS.get(type_key, []):
        value = new_config.get(field)
        if value and isinstance(value, (dict, list)):
            # 序列化为 JSON 字符串再加密
            serialized = json.dumps(value, ensure_ascii=False)
            new_config[field] = crypto.encrypt(serialized)

    return new_config


def decrypt_config(target_type: Any, config: dict) -> dict:
    """解密配置中的敏感字段（读库后调用）。

    Args:
        target_type: 发布目标类型（PublishTargetType 或字符串）
        config: 数据库中的配置 dict（敏感字段可能已加密）

    Returns:
        新的 config dict，敏感字段已解密为明文。
        明文存量数据（无加密前缀）原样返回。

    Raises:
        CryptoError: 解密失败（密文损坏或密钥不匹配）
    """
    if not config:
        return config

    type_key = _normalize_type(target_type)
    crypto = get_crypto_service()
    new_config = dict(config)

    # 1. 解密普通字符串敏感字段
    for field in SENSITIVE_FIELDS.get(type_key, []):
        value = new_config.get(field)
        if value and isinstance(value, str):
            new_config[field] = crypto.decrypt(value)

    # 2. 解密嵌套字段（headers 等）
    for field in NESTED_SENSITIVE_FIELDS.get(type_key, []):
        value = new_config.get(field)
        if value and isinstance(value, str):
            # 只有加密过的才是字符串；明文存量数据可能仍是 dict
            if crypto.is_encrypted(value):
                decrypted = crypto.decrypt(value)
                new_config[field] = json.loads(decrypted)
            # 非加密的 dict/其他，保持原样（存量明文）

    return new_config


def mask_config(target_type: Any, config: dict) -> dict:
    """脱敏配置（用于 API 响应，隐藏敏感字段）。

    Args:
        target_type: 发布目标类型
        config: 配置 dict（明文或加密均可）

    Returns:
        新 dict，敏感字段替换为 "******"（如果有值）。
    """
    if not config:
        return config

    type_key = _normalize_type(target_type)
    new_config = dict(config)

    all_sensitive = (
        SENSITIVE_FIELDS.get(type_key, [])
        + NESTED_SENSITIVE_FIELDS.get(type_key, [])
    )
    for field in all_sensitive:
        if new_config.get(field):
            new_config[field] = "******"

    return new_config
