# 概念：文本切分（Chunking）
#   把一篇长文本切成若干"小段"（chunk）。原因有二：
#     1. embedding 模型有输入长度上限，整篇几百页喂不进去；
#     2. 检索粒度——按"段"匹配比按"整篇"匹配精准得多。
#   段与段之间留一点"重叠"（overlap），避免把一句话从中间切断、丢失上下文。
#   Java 对照：≈ 把一个大 String 按窗口滑动切成 List<Segment>。
#
# 模块：backend/app/services/chunker.py，service 层纯函数。
#   被 workers/tasks.py 的 process_document 调用（parser 之后、embedding 之前）。
#
# 作用：
#   输入：纯文本 str + chunk_size + overlap
#   输出：list[Chunk]，每个 Chunk 带 (index, text, char_start, char_end)
#   不干什么：不算 embedding、不碰 DB。
#   char_start/char_end 是关键：DocumentChunk 表要存，检索命中后能跳回原文定位高亮。
#
# 怎么写：
#   - 用"滑动窗口 + 步长 = size - overlap"的字符切分（不是按 token，简单稳定，
#     中文按字符切已经够用；V2 想更精准可换 tiktoken 按 token 切）。
#   - 优先在"自然边界"（段落 \n\n、句号、换行）附近断开，避免切碎句子——
#     在理论切点附近的小窗口里找最近的边界字符。
#   - 陷阱：overlap 必须 < size，否则窗口不前进会死循环——构造时校验。
#   - 陷阱：纯空白/过短的段丢弃（DocumentChunk 有 content_length > 0 约束）。

from dataclasses import dataclass

from app.core.config import settings


# ============================================================
# 数据结构
# ============================================================


@dataclass
class Chunk:
    """一个文本分片。字段跟 DocumentChunk 表对齐。"""

    index: int        # 第几段（从 0 开始）
    text: str         # 段内容
    char_start: int   # 在原文中的起始字符位置（含）
    char_end: int     # 在原文中的结束字符位置（不含）


# 在切点附近多大范围内寻找"自然断句边界"
_BOUNDARY_SEARCH_WINDOW = 80
# 优先级从高到低的断句字符
_BOUNDARY_CHARS = ("\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";")


# ============================================================
# 主函数
# ============================================================


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """把纯文本切成带位置信息的分片列表。

    Args:
        text: 待切分的纯文本
        chunk_size: 每段目标字符数（默认读 settings.chunk_size = 500）
        overlap: 段间重叠字符数（默认读 settings.chunk_overlap = 50）

    Returns:
        Chunk 列表（空文本返回空列表）

    Raises:
        ValueError: overlap >= chunk_size（会导致窗口不前进）
    """
    size = chunk_size if chunk_size is not None else settings.chunk_size
    ov = overlap if overlap is not None else settings.chunk_overlap

    if ov >= size:
        raise ValueError(f"overlap({ov}) 必须小于 chunk_size({size})")

    text = text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    n = len(text)
    start = 0
    index = 0

    while start < n:
        # 理论切点
        ideal_end = min(start + size, n)
        # 在理论切点附近找自然边界（除非已经到文末）
        end = ideal_end if ideal_end >= n else _find_boundary(text, ideal_end)

        piece = text[start:end].strip()
        if piece:
            # 重新计算 strip 后的精确位置，保证 char_start/end 指向真实内容
            lead = len(text[start:end]) - len(text[start:end].lstrip())
            real_start = start + lead
            real_end = real_start + len(piece)
            chunks.append(
                Chunk(
                    index=index,
                    text=piece,
                    char_start=real_start,
                    char_end=real_end,
                )
            )
            index += 1

        if end >= n:
            break
        # 下一段起点：回退 overlap，但必须前进（防死循环）
        next_start = end - ov
        start = next_start if next_start > start else end

    return chunks


# ============================================================
# 辅助：寻找自然断句边界
# ============================================================


def _find_boundary(text: str, ideal_end: int) -> int:
    """在 ideal_end 附近找最近的自然断句点，找不到就用 ideal_end。

    策略：在 [ideal_end - window, ideal_end + window] 范围内，
    按边界字符优先级，找离 ideal_end 最近的一个，在其后断开。
    """
    n = len(text)
    lo = max(0, ideal_end - _BOUNDARY_SEARCH_WINDOW)
    hi = min(n, ideal_end + _BOUNDARY_SEARCH_WINDOW)
    window = text[lo:hi]

    best_pos = -1
    best_dist = _BOUNDARY_SEARCH_WINDOW + 1
    for marker in _BOUNDARY_CHARS:
        idx = 0
        while True:
            found = window.find(marker, idx)
            if found == -1:
                break
            # 边界落点 = marker 结束位置（在标点之后断开）
            abs_pos = lo + found + len(marker)
            dist = abs(abs_pos - ideal_end)
            if dist < best_dist:
                best_dist = dist
                best_pos = abs_pos
            idx = found + 1
        # 高优先级边界一旦找到就用（\n\n 比句号更适合断段）
        if best_pos != -1:
            return best_pos

    return ideal_end
