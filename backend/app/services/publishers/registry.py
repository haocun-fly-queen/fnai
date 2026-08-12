"""发布平台注册中心（阶段 2A）。

职责：
    - 维护 PublishTargetType → BasePublisher 的映射
    - register_publisher() 注册新平台
    - get_publisher() 获取已注册的平台插件

用法：
    from app.services.publishers.registry import get_publisher, register_publisher

    # 注册（在各插件模块的顶层或 __init__.py 里调用）
    register_publisher(PublishTargetType.WORDPRESS, WordPressPublisher())

    # 使用（在 publish.py 的统一入口里）
    publisher = get_publisher(target.type)
    result = await publisher.publish(article, config, options)
"""

import logging

from app.models.publish_target import PublishTargetType

from .base import BasePublisher

logger = logging.getLogger(__name__)

# 平台类型 → 插件实例 的映射
_PUBLISHERS: dict[PublishTargetType, BasePublisher] = {}


def register_publisher(platform_type: PublishTargetType, publisher: BasePublisher) -> None:
    """注册一个发布平台插件。

    如果该平台已注册，覆盖并打印警告（方便热重载）。

    Args:
        platform_type: 平台枚举值
        publisher: 该平台的 BasePublisher 实例
    """
    if platform_type in _PUBLISHERS:
        logger.warning(f"覆盖已注册的发布平台插件: {platform_type.value}")
    _PUBLISHERS[platform_type] = publisher
    logger.info(f"发布平台已注册: {platform_type.value} -> {publisher.__class__.__name__}")


def get_publisher(platform_type: PublishTargetType) -> BasePublisher:
    """获取已注册的发布平台插件。

    Args:
        platform_type: 平台枚举值

    Returns:
        该平台的 BasePublisher 实例

    Raises:
        ValueError: 该平台未注册
    """
    if platform_type not in _PUBLISHERS:
        raise ValueError(f"未注册的发布平台: {platform_type.value}")
    return _PUBLISHERS[platform_type]


def list_registered_publishers() -> dict[str, str]:
    """列出所有已注册的发布平台（调试用）。

    Returns:
        {平台类型: 插件类名} 的 dict
    """
    return {
        pt.value: pub.__class__.__name__
        for pt, pub in _PUBLISHERS.items()
    }
