"""URL 安全验证工具（防止 SSRF 攻击）。

概念：SSRF（Server-Side Request Forgery）服务端请求伪造攻击
模块：core/url_validator.py
作用：验证用户提供的 URL，防止攻击内网服务
怎么写：
    - 拦截内网 IP（127.x, 10.x, 172.16-31.x, 192.168.x, 169.254.x）
    - 拦截 localhost、link-local 地址
    - 解析域名后再次检查 IP（防止 DNS rebinding）
    - 支持自定义白名单
"""

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class URLValidationError(Exception):
    """URL 验证失败。"""

    def __init__(self, message: str, url: str):
        self.message = message
        self.url = url
        super().__init__(f"{message}: {url}")


def is_private_ip(ip: str) -> bool:
    """检查是否为私有 IP 地址。

    Args:
        ip: IP 地址字符串（如 "192.168.1.1"）

    Returns:
        True 表示是私有/保留地址
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
        )
    except ValueError:
        # 无效 IP，返回 True 拒绝
        return True


def validate_url_safe(
    url: str,
    allowed_schemes: Optional[set[str]] = None,
    allowed_domains: Optional[set[str]] = None,
    check_dns: bool = True,
) -> str:
    """验证 URL 安全性，防止 SSRF 攻击。

    Args:
        url: 待验证的 URL
        allowed_schemes: 允许的协议（默认：http, https）
        allowed_domains: 白名单域名（如果设置，只允许这些域名）
        check_dns: 是否解析域名并检查 IP（防止 DNS rebinding）

    Returns:
        规范化后的 URL（scheme + netloc 转小写）

    Raises:
        URLValidationError: URL 不安全

    示例：
        validate_url_safe("https://example.com/api")  # OK
        validate_url_safe("http://127.0.0.1/admin")    # 抛出异常
        validate_url_safe("http://169.254.169.254/")   # 抛出异常（AWS 元数据）
    """
    if allowed_schemes is None:
        allowed_schemes = {"http", "https"}

    # 1. 基本解析
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise URLValidationError(f"URL 解析失败: {e}", url)

    # 2. 检查协议
    if parsed.scheme.lower() not in allowed_schemes:
        raise URLValidationError(
            f"不允许的协议，仅支持 {allowed_schemes}",
            url,
        )

    # 3. 检查是否有主机名
    if not parsed.netloc:
        raise URLValidationError("URL 缺少主机名", url)

    # 4. 提取主机名（去掉端口）
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("无法解析主机名", url)

    hostname_lower = hostname.lower()

    # 5. 白名单检查（如果设置）
    if allowed_domains:
        if hostname_lower not in allowed_domains:
            raise URLValidationError(
                f"域名不在白名单中，允许的域名: {allowed_domains}",
                url,
            )

    # 6. 检查是否为 IP 地址
    try:
        # 如果 hostname 是 IP 地址，直接检查
        if is_private_ip(hostname):
            raise URLValidationError(
                "不允许访问内网 IP 地址（127.x, 10.x, 192.168.x, 172.16-31.x, 169.254.x）",
                url,
            )
    except ValueError:
        # hostname 不是 IP，是域名，继续
        pass

    # 7. 检查危险的域名模式
    dangerous_patterns = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "[::]",
        "[::1]",
    ]
    if any(pattern in hostname_lower for pattern in dangerous_patterns):
        raise URLValidationError(
            "不允许访问 localhost 或环回地址",
            url,
        )

    # 8. DNS 解析检查（防止 DNS rebinding 攻击）
    if check_dns:
        try:
            # 解析域名获取 IP 列表
            addr_info = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )

            # 检查所有解析出的 IP
            for info in addr_info:
                ip = info[4][0]  # (family, type, proto, canonname, (address, port))
                if is_private_ip(ip):
                    raise URLValidationError(
                        f"域名 {hostname} 解析到内网 IP {ip}，可能是 DNS rebinding 攻击",
                        url,
                    )

            logger.debug(f"URL validated: {url} -> {[info[4][0] for info in addr_info]}")

        except socket.gaierror as e:
            # DNS 解析失败（域名不存在或网络问题）
            raise URLValidationError(
                f"域名解析失败: {e}",
                url,
            )
        except OSError as e:
            # 其他网络错误
            logger.warning(f"DNS check failed for {hostname}: {e}, allowing")
            # 网络问题不应该阻止正常请求，记录警告但放行

    # 9. 返回规范化 URL（scheme 和 netloc 小写）
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    ).geturl()

    return normalized


def validate_wordpress_url(url: str) -> str:
    """验证 WordPress 站点 URL。

    WordPress URL 必须是公网 HTTPS/HTTP，不能指向内网。

    Args:
        url: WordPress 站点 URL

    Returns:
        规范化后的 URL

    Raises:
        URLValidationError: URL 不安全
    """
    return validate_url_safe(url, allowed_schemes={"http", "https"}, check_dns=True)


def validate_webhook_url(url: str) -> str:
    """验证 Webhook URL。

    Webhook URL 必须是公网 HTTPS/HTTP，不能指向内网。

    Args:
        url: Webhook URL

    Returns:
        规范化后的 URL

    Raises:
        URLValidationError: URL 不安全
    """
    return validate_url_safe(url, allowed_schemes={"http", "https"}, check_dns=True)
