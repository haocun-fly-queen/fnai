"""Security primitives: password hashing, JWT signing/verification.

本文件是 FNAI 平台的"安全底座"，所有需要加密、签 token、验 token 的地方
都从这里调。改这个文件会影响整个系统的鉴权，所以要谨慎。

学习要点（给 Java 背景的同事）：
- Python 没用 passlib，直接用 bcrypt 库，更轻
- JWT 用 python-jose，签出来的字符串就是 token 本身
- 整个文件分两段：上半段是密码哈希，下半段是 JWT 签发/校验
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ============================================================
# 第一段：密码哈希
# ============================================================
# 用户的密码不能明文存数据库（数据库被黑就完蛋），
# 所以注册时把密码"哈希"成不可逆的密文存进去；
# 登录时把用户输入的密码用同样的算法哈希，看结果是不是一样。
#
# ⚠️ 为什么用 bcrypt 而不是 SHA256/MD5：
#   - bcrypt 慢：故意设计成"算一次要 100ms"，暴力破解代价高
#   - 自带 salt：每次哈希结果都不同，彩虹表攻击无效
#   - rounds=12 是 2026 年的安全基准（rounds 每 +1 慢一倍）
# ============================================================


def hash_password(plain: str) -> str:
    """把明文密码哈希成密文。

    Args:
        plain: 用户输入的明文密码，比如 "MyP@ssw0rd123"

    Returns:
        一串看起来像乱码的字符串，比如 "$2b$12$xxx...xxx"
        这串东西会原样存到 users.hashed_password 字段。

    警告：bcrypt 有 72 字节输入限制。我们在 schema 里限了 128 字符，
    但万一以后去掉那个限制，要在这里做截断处理，否则会抛 ValueError。
    """
    # gensalt() 每次生成不同的随机 salt，rounds=12 是计算成本参数
    salt = bcrypt.gensalt(rounds=12)

    # 编码 → 哈希 → 解码回 str（因为 DB 列是 str 类型）
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码和密文是否匹配。

    Args:
        plain: 用户登录时输入的明文
        hashed: 数据库里存的密文

    Returns:
        True = 密码对，False = 密码错

    重要：任何异常都返回 False，不抛出去。
    原因：如果区分"用户不存在"和"密码错"，攻击者可以通过错误消息
    枚举出哪些 email 注册过。所以"用户不存在"和"密码错"返回同一个错。
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # 哈希格式坏了（DB 损坏？迁移问题？）也算校验失败
        return False


# ============================================================
# 第二段：JWT（JSON Web Token）
# ============================================================
# 我们用 JWT 来做"无状态会话"：
#   - 用户登录成功后，服务器签发一个 token 给前端
#   - 前端之后每次请求都把这个 token 放在 Authorization 头
#   - 服务器用密钥验证 token，确认请求者身份
#
# JWT 的结构：header.payload.signature
#   - header: 算法和类型（HS256, JWT）
#   - payload: 业务数据（user_id, 过期时间, 租户信息...）
#   - signature: 用密钥对前两段做哈希，防篡改
#
# 我们签两种 token：
#   - access_token（15 分钟）：日常请求用，短命
#   - refresh_token（7 天）：用来换新的 access_token，长命
# 为什么分两种：access_token 短命，万一被偷损失小；
#               refresh_token 长命，但只用来换 token，不直接当钥匙用。
# ============================================================


def _now() -> datetime:
    """当前 UTC 时间。统一用 tz-aware datetime，避免时区问题。"""
    return datetime.now(tz=timezone.utc)


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """底层 JWT 签发函数（内部用，外部不直接调）。

    Args:
        subject: 写进 token 的"主体标识"，我们用 user_id 的字符串形式
        expires_delta: 多久后过期，比如 timedelta(minutes=15)
        token_type: "access" 或 "refresh"，混用会爆（防御性检查）
        extra_claims: 额外塞进 payload 的字段，比如 active_tenant_id

    Returns:
        签名后的 JWT 字符串，可以直接发给前端。

    ⚠️ 安全提示：extra_claims 里的内容是"明文的"（虽然签名防篡改），
    所以别塞密码、邮箱、手机号这种敏感信息。我们只塞 user_id 和 tenant_id。
    """
    now = _now()
    payload: dict[str, Any] = {
        # sub = subject，JWT 标准字段，表示"这个 token 代表谁"
        "sub": subject,
        # type = 区分 access/refresh，防"拿 refresh token 当 access 用"
        "type": token_type,
        # iat = issued at，签发时间（调试 + 防重放）
        "iat": int(now.timestamp()),
        # exp = expiry，过期时间（python-jose 会自动校验）
        "exp": int((now + expires_delta).timestamp()),
    }
    # 如果有额外字段，merge 进 payload
    if extra_claims:
        payload.update(extra_claims)

    # 签名 = 用密钥对 (header + payload) 做 HMAC-SHA256
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ============================================================
# 给业务层用的便捷函数
# ============================================================


def create_access_token(
    user_id: UUID,
    active_tenant_id: UUID | None = None,
) -> str:
    """签发 access token（短命，15 分钟）。

    Args:
        user_id: 当前登录用户的 UUID
        active_tenant_id: 当前激活的租户 UUID。新用户刚注册还没选租户时
                         传 None。注意这里必须是 None（不是 UUID 0），
                         因为 None 表示"无激活租户"。

    Returns:
        JWT 字符串，结构：xxx.yyy.zzz

    业务场景：
    - 登录时：传用户的某个 tenant_id（默认第一个）
    - 注册时：传 None（用户刚注册完还没选工作空间）
    - 切换租户时：传新的 tenant_id（重新签发 token）
    """
    delta = timedelta(minutes=settings.access_token_expire_minutes)

    # 把 active_tenant_id 塞进 extra_claims，这样 token 里就携带了"当前租户"信息
    # 业务中间件读 token 就能知道"这个请求要在哪个租户下处理"
    extra_claims: dict[str, Any] = {}
    if active_tenant_id is not None:
        # UUID 转 str 存 payload（JSON 不支持 UUID 类型）
        extra_claims["active_tenant_id"] = str(active_tenant_id)

    return _create_token(
        subject=str(user_id),
        expires_delta=delta,
        token_type="access",
        extra_claims=extra_claims or None,
    )


def create_refresh_token(user_id: UUID) -> str:
    """签发 refresh token（长命，7 天）。

    refresh token 不携带租户信息，因为它唯一的用途是"换 access token"。
    换出来的新 access token 会带 active_tenant_id。

    为什么 refresh token 不带租户：
    - 简化设计：换 token 时如果需要改租户，重新调 switch 接口更清晰
    - 安全：refresh token 暴露的"业务上下文"越少越好
    """
    delta = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(
        subject=str(user_id),
        expires_delta=delta,
        token_type="refresh",
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """验证 token 合法性 + 解析 payload。

    Args:
        token: 客户端传过来的 JWT 字符串
        expected_type: 期望的 token 类型（"access" 或 "refresh"）

    Returns:
        解析后的 payload 字典，结构：
        {
            "sub": "uuid-string",           # user_id
            "type": "access",
            "iat": 1234567890,
            "exp": 1234567890,
            "active_tenant_id": "uuid-string"  # 可选，只有 access token 才有
        }

    Raises:
        ValueError: token 签名错、过期、类型不匹配

    调用方：
    - api/v1/deps.py 的 get_current_user 调这个（验 access token）
    - /auth/refresh 端点调这个（验 refresh token）
    """
    try:
        # python-jose 自动验签 + 验过期时间
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        # 验签失败 / 过期 / 格式错都进这里
        raise ValueError(f"invalid_token: {exc}") from exc

    # 防御性检查：防止有人拿 refresh token 当 access token 用
    if payload.get("type") != expected_type:
        raise ValueError(f"wrong_token_type: expected {expected_type}, got {payload.get('type')}")

    return payload
