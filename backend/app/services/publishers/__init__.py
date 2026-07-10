"""发布平台插件包（阶段 2A）。

导入本包时自动注册所有已实现的发布平台插件。

新增平台只需：
    1. 在本目录创建 xxx.py，实现 BasePublisher 子类
    2. 在下面 import 并 register_publisher(...)
"""

from app.models.publish_target import PublishTargetType

from .base import BasePublisher, PublishResult
from .registry import get_publisher, list_registered_publishers, register_publisher

# ── 注册所有已实现的插件 ──────────────────────────────────

# WordPress
from .wordpress import WordPressPublisher

register_publisher(PublishTargetType.WORDPRESS, WordPressPublisher())

# Webhook
from .webhook import WebhookPublisher

register_publisher(PublishTargetType.WEBHOOK, WebhookPublisher())

# 微信公众号
from .wechat_mp import WechatMpPublisher

register_publisher(PublishTargetType.WECHAT_MP, WechatMpPublisher())

# 微博
from .weibo import WeiboPublisher

register_publisher(PublishTargetType.WEIBO, WeiboPublisher())

# ── 导出 ──────────────────────────────────────────────────

__all__ = [
    "BasePublisher",
    "PublishResult",
    "get_publisher",
    "register_publisher",
    "list_registered_publishers",
]
