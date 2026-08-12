"""敏感数据加密服务（Fernet 对称加密）。

概念：加密存储发布目标配置中的敏感字段（app_secret / app_password / cookie 等）
模块：core/crypto.py
作用：
    - 加密：写库前对敏感字段加密
    - 解密：读库后对敏感字段解密
    - 平滑迁移：明文数据（无前缀）原样返回，不影响存量数据
怎么写：
    - 使用 Fernet（AES-128-CBC + HMAC-SHA256，自带完整性校验）
    - 使用 MultiFernet 支持密钥轮换（多密钥，新密钥加密，旧密钥仍能解密）
    - 加密值带 "enc:v1:" 前缀，用于辨识和幂等处理

密钥生成：
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

logger = logging.getLogger(__name__)

# 加密值前缀（版本化，便于将来算法升级）
_PREFIX = "enc:v1:"


class CryptoError(Exception):
    """加解密失败。"""


class CryptoService:
    """敏感数据加解密服务。

    使用方法：
        crypto = get_crypto_service()
        cipher = crypto.encrypt("my-secret")   # "enc:v1:gAAAA..."
        plain = crypto.decrypt(cipher)          # "my-secret"

    设计要点：
        - 加密幂等：已加密的值（带前缀）不会重复加密
        - 解密兼容：明文值（无前缀）原样返回，兼容存量明文数据
        - 密钥轮换：MultiFernet 用第一个密钥加密，所有密钥依次尝试解密
    """

    def __init__(self, keys: list[str]):
        """初始化加密服务。

        Args:
            keys: Fernet 密钥列表（第一个用于加密，全部用于解密）
                  支持多密钥以实现密钥轮换。

        Raises:
            CryptoError: 密钥无效
        """
        if not keys:
            raise CryptoError("加密密钥列表为空")

        try:
            fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
        except Exception as e:
            raise CryptoError(f"加密密钥格式无效: {e}")

        self._fernet = MultiFernet(fernets)

    def encrypt(self, plaintext: str) -> str:
        """加密字符串。

        Args:
            plaintext: 明文

        Returns:
            加密后的字符串（带 "enc:v1:" 前缀）；
            空值或已加密的值原样返回（幂等）。
        """
        if not plaintext:
            return plaintext

        # 已加密 → 不重复加密（幂等）
        if plaintext.startswith(_PREFIX):
            return plaintext

        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return _PREFIX + token

    def decrypt(self, value: str) -> str:
        """解密字符串。

        Args:
            value: 加密字符串（带前缀）或明文

        Returns:
            解密后的明文；
            无前缀的值视为明文（存量数据），原样返回。

        Raises:
            CryptoError: 密文损坏或密钥不匹配
        """
        if not value:
            return value

        # 无前缀 → 视为明文（兼容存量数据）
        if not value.startswith(_PREFIX):
            return value

        token = value[len(_PREFIX):]
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise CryptoError("解密失败：密文损坏或密钥不匹配")

    def is_encrypted(self, value: str) -> bool:
        """判断值是否已加密。"""
        return bool(value) and value.startswith(_PREFIX)


@lru_cache
def get_crypto_service() -> CryptoService:
    """获取全局加密服务实例（单例）。

    密钥来源：settings.encryption_key（可用逗号分隔多个密钥以支持轮换）。

    行为：
        - 生产环境（production）：未配置密钥则抛出异常，强制安全
        - 其他环境：未配置密钥则生成临时密钥 + 警告日志（仅开发便利）

    Raises:
        CryptoError: 生产环境未配置密钥
    """
    raw = settings.encryption_key.strip() if settings.encryption_key else ""

    if raw:
        # 支持逗号分隔的多密钥（密钥轮换）
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return CryptoService(keys)

    # 未配置密钥
    if settings.environment == "production":
        raise CryptoError(
            "生产环境必须配置 ENCRYPTION_KEY 环境变量。"
            "生成方法：python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    # 开发/测试环境：生成临时密钥（重启后失效，仅用于本地开发）
    logger.warning(
        "⚠️  未配置 ENCRYPTION_KEY，正在使用临时密钥（重启后失效）。"
        "生产环境部署前务必配置固定密钥！"
    )
    temp_key = Fernet.generate_key().decode()
    return CryptoService([temp_key])
