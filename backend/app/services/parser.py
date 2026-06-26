# 概念：文档解析（Document Parsing）
#   把用户上传的二进制文件（PDF/Word/PPT/Markdown/纯文本）抽取成"纯文本字符串"。
#   这是 RAG 链路的第一步——只有先变成文本，才能切分、算 embedding、入库检索。
#   Java 对照：≈ Apache Tika / POI 那一层，把各种格式统一抽成 String。
#
# 模块：backend/app/services/parser.py，属于 service 层（无状态纯函数）。
#   被 workers/tasks.py 的 process_document 调用（Celery worker 进程里跑）。
#
# 作用：
#   输入：文件字节 data + content_type（MIME）
#   输出：抽取出来的纯文本 str
#   不干什么：不做切分（chunker 的事）、不算向量（embedding 的事）、不碰 DB。
#
# 怎么写：
#   - 按 MIME 分派到对应解析器（pdf/docx/pptx/markdown/plain）。
#   - 各解析库都吃"文件路径"或"file-like 对象"，所以统一用 io.BytesIO 包字节流，
#     不落临时文件（worker 里 storage 已经有原始文件，但这里只拿到了 bytes）。
#   - 解析失败统一抛 ParseError，让上层把文档状态置为 FAILED 并记 error_message。
#   - 陷阱：PDF 扫描件（纯图片）抽不出文字，会得到空字符串——这里不做 OCR，
#     返回空串后由上层判断"抽取内容为空"并标记失败，提示用户。

import io
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 业务异常
# ============================================================


class ParseError(Exception):
    """文档解析失败。上层（tasks）catch 后把 document.status 置 FAILED。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ============================================================
# MIME → 解析器分派
# ============================================================

# MIME 常量（跟 config.allowed_mime_types 对齐）
MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIME_TXT = "text/plain"
MIME_MD = "text/markdown"


def parse(data: bytes, content_type: str) -> str:
    """把文件字节抽取成纯文本。

    Args:
        data: 文件原始字节
        content_type: MIME type（已在上传时校验过白名单）

    Returns:
        抽取出的纯文本（可能为空字符串，上层需判断）

    Raises:
        ParseError: 格式不支持 / 解析过程报错
    """
    if content_type == MIME_PDF:
        text = _parse_pdf(data)
    elif content_type == MIME_DOCX:
        text = _parse_docx(data)
    elif content_type == MIME_PPTX:
        text = _parse_pptx(data)
    elif content_type in (MIME_TXT, MIME_MD):
        text = _parse_text(data)
    else:
        raise ParseError(f"不支持的文件类型: {content_type}")

    # 统一清洗：去掉行尾空白、合并多余空行
    cleaned = _normalize(text)
    logger.info(
        "parse done: content_type=%s in_bytes=%d out_chars=%d",
        content_type, len(data), len(cleaned),
    )
    return cleaned


# ============================================================
# 各格式解析实现
# ============================================================


def _parse_pdf(data: bytes) -> str:
    """PDF → 文本（逐页抽取）。

    用 pypdf。扫描件（图片型 PDF）抽不出文字，返回空串。
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ParseError(f"缺少 pypdf 依赖: {exc}")

    try:
        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages)
    except Exception as exc:
        raise ParseError(f"PDF 解析失败: {exc}")


def _parse_docx(data: bytes) -> str:
    """Word(.docx) → 文本（段落 + 表格单元格）。

    用 python-docx。只处理 .docx（OOXML），老的 .doc 不支持。
    """
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:  # pragma: no cover
        raise ParseError(f"缺少 python-docx 依赖: {exc}")

    try:
        doc = DocxDocument(io.BytesIO(data))
        parts: list[str] = [p.text for p in doc.paragraphs if p.text.strip()]
        # 表格内容也抽出来（企业资料里大量信息在表格里）
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    except Exception as exc:
        raise ParseError(f"Word 解析失败: {exc}")


def _parse_pptx(data: bytes) -> str:
    """PPT(.pptx) → 文本（逐张幻灯片抽取所有文本框）。

    用 python-pptx。
    """
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover
        raise ParseError(f"缺少 python-pptx 依赖: {exc}")

    try:
        prs = Presentation(io.BytesIO(data))
        slides: list[str] = []
        for slide in prs.slides:
            texts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:  # type: ignore[attr-defined]
                    for para in shape.text_frame.paragraphs:  # type: ignore[attr-defined]
                        line = "".join(run.text for run in para.runs)
                        if line.strip():
                            texts.append(line)
            if texts:
                slides.append("\n".join(texts))
        return "\n\n".join(slides)
    except Exception as exc:
        raise ParseError(f"PPT 解析失败: {exc}")


def _parse_text(data: bytes) -> str:
    """纯文本 / Markdown → 文本。

    Markdown 不渲染，直接当纯文本喂给 embedding（标题/列表符号保留也无妨，
    反而能给模型一点结构信号）。
    编码：优先 UTF-8，失败回退 GBK（中文 Windows 常见），再失败用 errors=replace。
    """
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 兜底：替换无法解码的字节，保证不抛异常
    return data.decode("utf-8", errors="replace")


# ============================================================
# 文本清洗
# ============================================================


def _normalize(text: str) -> str:
    """规整文本：去行尾空白、压缩 3+ 连续空行为 1 个空行。

    目的：减少无意义 token，让 chunk 更紧凑。
    """
    lines = [line.rstrip() for line in text.splitlines()]
    # 压缩连续空行
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                result.append(line)
        else:
            blank_run = 0
            result.append(line)
    return "\n".join(result).strip()
