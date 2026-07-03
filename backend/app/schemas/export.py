"""导出相关的 schema（阶段 5）"""

from enum import Enum


class ExportFormat(str, Enum):
    """导出格式枚举。"""

    MARKDOWN = "markdown"
    HTML = "html"
