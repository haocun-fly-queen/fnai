"""发布平台插件基类（阶段 2A）。

设计：
    每个发布平台（WordPress / 微信 / 微博 / 知乎 / Medium / Webhook）
    实现一个 BasePublisher 子类，通过 registry 注册后即可被统一发布入口调用。

    加新平台只需：
        1. 写一个 XxxPublisher(BasePublisher)
        2. 在 publishers/__init__.py 里 register_publisher(...)
        3. 不改 publish.py / 不改任何已有代码

类：
    PublishResult  — 一次发布的结果（success / remote_id / message / metadata）
    BasePublisher  — 抽象基类，定义平台插件必须实现的接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PublishResult:
    """一次发布操作的结果。

    Attributes:
        success: 是否成功
        remote_id: 远程平台的文章 ID（如 WordPress post_id、微信 media_id）
        message: 人类可读的消息（成功提示或错误描述）
        metadata: 平台特定的额外数据（如文章 URL、微博 ID 等）
    """

    success: bool
    remote_id: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePublisher(ABC):
    """发布平台插件基类。

    每个平台实现一个子类并注册到 registry。
    子类必须实现 4 个抽象方法。

    注意：
        - publish() 接收的 article 是已解密 KB、已 refresh 的 SQLAlchemy 对象
        - config 是 decrypt_config() 后的明文配置
        - options 是本次发布的平台特定参数（前端传入）
    """

    @abstractmethod
    async def validate_config(self, config: dict) -> None:
        """验证发布目标配置是否有效。

        在创建/更新发布目标时调用。配置无效应抛 ValueError。

        Args:
            config: 用户提交的配置 dict（明文）

        Raises:
            ValueError: 配置无效（缺字段、URL 不安全等）
        """

    @abstractmethod
    async def publish(
        self,
        article: Any,  # app.models.article.Article（用 Any 避免循环导入）
        config: dict,
        options: dict | None = None,
    ) -> PublishResult:
        """发布一篇文章到该平台。

        Args:
            article: 文章对象（已解密 KB、已 refresh 的 SQLAlchemy 模型）
            config: 发布目标配置（decrypt_config 后的明文）
            options: 本次发布的平台特定参数（如微信的 author/digest、WP 的 status）

        Returns:
            PublishResult: success / remote_id / message / metadata
        """

    @abstractmethod
    def get_config_schema(self) -> dict:
        """返回该平台配置的 JSON Schema。

        前端可据此动态渲染配置表单。
        返回值遵循 JSON Schema 规范（draft-07）。

        示例返回值：
            {
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "title": "站点 URL"},
                    "username": {"type": "string", "title": "用户名"},
                    "app_password": {"type": "string", "title": "应用密码"},
                },
                "required": ["site_url", "username", "app_password"],
            }
        """

    @abstractmethod
    def get_publish_options_schema(self) -> dict:
        """返回发布选项的 JSON Schema。

        前端可据此动态渲染"发布选项"表单（如微信的 author/digest）。
        如果该平台没有额外选项，返回空 schema：
            {"type": "object", "properties": {}}
        """
