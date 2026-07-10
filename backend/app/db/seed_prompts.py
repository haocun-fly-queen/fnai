"""预置 Prompt 模板 —— 系统级模板，所有租户共享。

设计原则：
    每个模板针对一种文章场景，对应一组 4+2 阶段 prompt：
        outline / section / seo / quality（基础 4 阶段）
        table_section / list_section（结构化输出，Phase 2 新增）
    模板里的占位符（用 {curly_braces}）由生成服务在调用时填充：
        {topic}            用户输入的主题
        {target_word_count} 目标字数
        {outline}          上一阶段生成的大纲 JSON
        {section_title}    当前正在写的小节标题
        {section_points}   当前小节的要点
        {full_content}     前一阶段写完的完整正文
        {context}          从 RAG 检索回来的相关 chunks 文本
        {columns}          表格列名（table_section_prompt 专用）
        {key_points}       列表要点（list_section_prompt 专用）

10 种模板：
    blog        —— 博客文章（叙述性强，1500 字，3-5 个小节）
    product     —— 产品介绍（卖点驱动，1200 字，痛点→方案→功能→优势→CTA）
    news        —— 新闻稿（倒金字塔，800 字，事实优先）
    seo         —— SEO 长文（2500 字，覆盖关键词，问答式小节）
    social      —— 社交媒体（500 字，钩子开头，强 CTA）
    ecommerce   —— 电商产品描述（卖点、痛点、使用场景，带购买引导）
    tech_doc    —— 技术文档（API 文档、使用指南，准确、逻辑清晰、带代码示例）
    marketing   —— 营销文案（广告、落地页，情感化、转化导向）
    comparison  —— 对比评测（产品对比、技术选型，多维度对比表）
    tutorial    —— 教程指南（教学、操作步骤，分步骤、带示例）

用法：
    docker exec fnai-backend-dev python -m app.db.seed_prompts
"""

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models import PromptTemplate, TemplateType


# ============================================================
# 5 个预置模板定义
# ============================================================
#
# 注：所有 prompt 都用中文，因为目标用户是中文内容创作者；
#     生成结果默认中文，必要时模板里加"请用中文输出"显式提示。

SYSTEM_TEMPLATES: list[dict[str, Any]] = [
    # ─────────────────────────────────────────────────
    # 1. blog —— 博客文章
    # ─────────────────────────────────────────────────
    {
        "code": "blog",
        "name": "博客文章",
        "description": "通用博客风格：叙述清晰、案例丰富、读起来舒服。适合主题深度展开。",
        "default_word_count": 1500,
        "outline_prompt": (
            "你是资深内容编辑。请基于以下信息为一篇博客文章设计大纲。\n\n"
            "【主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 给出 1 个吸引人的标题；\n"
            "2. 拆 3-5 个小节，每节给出 2-4 个要点（key_points）；\n"
            "3. 整体逻辑通顺，由浅入深；\n"
            '4. 每节 content_type 为 "text"；\n'
            "5. 严格按 JSON 输出，结构如下：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["...", "..."]}}]}}\n'
            "不要输出 JSON 以外的内容。"
        ),
        "section_prompt": (
            "你正在为博客文章写一个小节。基于以下信息写出该小节的正文。\n\n"
            "【文章主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出小节正文 Markdown（不要重复标题，不要带 # 号）；\n"
            "2. 语气亲切自然，可以用案例和类比；\n"
            "3. 控制在 300-500 字；\n"
            "4. 不要编造参考资料里没有的事实数据。"
        ),
        "seo_prompt": (
            "为以下文章生成 SEO 元信息。\n\n"
            "【标题】{title}\n"
            "【正文】{full_content}\n\n"
            "严格按 JSON 输出：\n"
            '{{"meta_title": "≤60 字符的 SEO 标题",'
            ' "meta_description": "≤155 字符的描述",'
            ' "keywords": ["关键词1", "关键词2", "..."]}}'
        ),
        "quality_prompt": (
            "请对以下博客文章做最后润色：\n\n"
            "{full_content}\n\n"
            "要求：\n"
            "1. 修复明显错别字和不通顺的地方；\n"
            "2. 保持 Markdown 结构和小节标题；\n"
            "3. 不要大改原意；\n"
            "4. 直接输出润色后的完整 Markdown，不要任何额外说明。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 2. product —— 产品介绍
    # ─────────────────────────────────────────────────
    {
        "code": "product",
        "name": "产品介绍",
        "description": "卖点驱动：痛点→方案→功能→优势→行动号召。适合落地页/产品页文案。",
        "default_word_count": 1200,
        "outline_prompt": (
            "你是 B2B 内容营销专家。为一款产品写一篇介绍文章设计大纲。\n\n"
            "【产品/主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "采用 PAS-FAB 结构：痛点 → 方案 → 功能 → 优势 → 行动号召（5 小节）。\n"
            '每节 content_type 为 "text"。严格按 JSON 输出：\n'
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["..."]}}]}}'
        ),
        "section_prompt": (
            "为产品介绍文章写一个小节。\n\n"
            "【产品/主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出小节 Markdown 正文（不要重复标题）；\n"
            "2. 语气专业、有说服力，避免夸大；\n"
            "3. 200-400 字；\n"
            "4. 仅使用参考资料里有的功能/数据，不要编造。"
        ),
        "seo_prompt": (
            "为以下产品介绍生成 SEO 元信息：\n\n"
            "【标题】{title}\n"
            "【正文】{full_content}\n\n"
            "重点关键词应贴近【产品名 + 场景 + 行业】组合。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下产品介绍润色，强化卖点逻辑：\n\n"
            "{full_content}\n\n"
            "要求：1) 改流畅；2) 保持结构；3) 不夸大；4) 直接输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 3. news —— 新闻稿
    # ─────────────────────────────────────────────────
    {
        "code": "news",
        "name": "新闻稿",
        "description": "倒金字塔：核心事实优先、800 字、客观语气。适合公司动态、产品发布。",
        "default_word_count": 800,
        "outline_prompt": (
            "你是公关稿撰写人。为以下事件起草新闻稿大纲。\n\n"
            "【事件/主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "采用倒金字塔结构：导语（5W1H 核心事实）→ 主体（细节展开）→ 背景（公司/产品简介）。\n"
            '拆 3 个小节即可，每节 content_type 为 "text"。严格按 JSON 输出：\n'
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["..."]}}]}}'
        ),
        "section_prompt": (
            "为新闻稿写一个小节。\n\n"
            "【事件】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 第三人称、客观语气，避免营销腔；\n"
            "2. 直接事实陈述，不议论；\n"
            "3. 200-300 字；\n"
            "4. 直接输出 Markdown 正文（不要重复标题）。"
        ),
        "seo_prompt": (
            "为新闻稿生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "严格 JSON："
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下新闻稿做最后校对：\n\n{full_content}\n\n"
            "要求：1) 检查事实陈述；2) 删掉营销腔；3) 保持简洁客观；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 4. seo —— SEO 长文
    # ─────────────────────────────────────────────────
    {
        "code": "seo",
        "name": "SEO 长文",
        "description": "覆盖关键词、问答式小节、2500 字。专为搜索引擎排名优化。",
        "default_word_count": 2500,
        "outline_prompt": (
            "你是 SEO 内容策略专家。为以下主题设计一篇长尾 SEO 文章大纲。\n\n"
            "【主题/关键词】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 标题包含核心关键词；\n"
            "2. 拆 5-7 个小节，每个小节标题尽量是用户会搜的问题（如 \"什么是 X\" / \"X 怎么用\" / \"X 和 Y 的区别\"）；\n"
            "3. 每节给 3-5 个要点；\n"
            '4. 每节 content_type 为 "text"；\n'
            "5. 严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["..."]}}]}}'
        ),
        "section_prompt": (
            "为 SEO 文章写一个小节。\n\n"
            "【主题/关键词】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 自然嵌入主题关键词 2-3 次（不要堆砌）；\n"
            "2. 段落短、读起来轻松；\n"
            "3. 400-500 字；\n"
            "4. 直接输出 Markdown 正文。"
        ),
        "seo_prompt": (
            "为以下 SEO 长文生成元信息（必须最大化搜索友好度）：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "严格 JSON："
            '{{"meta_title": "≤60 字符，含主关键词", '
            '"meta_description": "≤155 字符，含主关键词且自然", '
            '"keywords": ["核心主词", "长尾1", "长尾2", "..."]}}'
        ),
        "quality_prompt": (
            "对以下 SEO 文章做润色：\n\n{full_content}\n\n"
            "要求：1) 保持关键词分布；2) 段落短一些便于阅读；3) 修通顺；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 5. social —— 社交媒体
    # ─────────────────────────────────────────────────
    {
        "code": "social",
        "name": "社交媒体短文",
        "description": "钩子开头、强 CTA、500 字。适合公众号/小红书/LinkedIn 单贴。",
        "default_word_count": 500,
        "outline_prompt": (
            "你是社交媒体内容创作者。为以下主题设计一篇短文大纲。\n\n"
            "【主题】{topic}\n【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "结构：钩子开头 → 2-3 个核心点 → 强行动号召。\n"
            '拆 3 个小节即可（开头/主体/CTA），每节 content_type 为 "text"。严格 JSON：\n'
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["..."]}}]}}'
        ),
        "section_prompt": (
            "为社交媒体短文写一个小节。\n\n"
            "【主题】{topic}\n【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 口语化、有节奏感、可以用 emoji（适度）；\n"
            "2. 100-200 字；\n"
            "3. 直接输出 Markdown 正文（不要重复标题）。"
        ),
        "seo_prompt": (
            "为社交短文生成元信息（用于配文摘要）：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n严格 JSON："
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["tag1", "tag2"]}}'
        ),
        "quality_prompt": (
            "对以下社交短文润色：\n\n{full_content}\n\n"
            "要求：1) 钩子要狠；2) CTA 要明确；3) 节奏紧凑；4) 输出完整 Markdown。"
        ),
        "table_section_prompt": "",
        "list_section_prompt": "",
    },
    # ─────────────────────────────────────────────────
    # 6. ecommerce —— 电商产品描述
    # ─────────────────────────────────────────────────
    {
        "code": "ecommerce",
        "name": "电商产品描述",
        "description": "商品详情页风格：强调卖点、痛点、使用场景，带购买引导。适合淘宝/京东/独立站产品页。",
        "default_word_count": 1200,
        "outline_prompt": (
            "你是电商文案专家。为以下商品设计一篇产品描述文章的大纲。\n\n"
            "【商品/主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "结构：核心卖点 → 用户痛点 → 解决方案 → 使用场景 → 产品参数 → 购买行动号召。\n"
            '其中"产品参数"小节 content_type 设为 "table"，并给出 table_columns；\n'
            '其他小节 content_type 为 "text"。\n'
            "严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text|table", '
            '"key_points": ["..."], "table_columns": ["参数", "详情"]}}]}}'
        ),
        "section_prompt": (
            "为电商产品描述写一个小节。\n\n"
            "【商品/主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出小节 Markdown 正文（不要重复标题）；\n"
            "2. 语言简洁有力，突出用户利益；\n"
            "3. 200-400 字；\n"
            "4. 仅使用参考资料里有的功能/数据，不要编造。"
        ),
        "table_section_prompt": (
            "为电商产品描述写一个参数表格小节。\n\n"
            "【商品/主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【表格列名】{columns}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 输出 Markdown 表格，表头为指定列名；\n"
            "2. 行数根据实际参数数量决定，覆盖关键参数；\n"
            "3. 参数值来自参考资料，不要编造；\n"
            "4. 不要输出表格以外的内容。"
        ),
        "list_section_prompt": "",
        "seo_prompt": (
            "为以下电商产品描述生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "关键词应包含【产品名 + 核心卖点 + 使用场景】。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下电商产品描述润色：\n\n{full_content}\n\n"
            "要求：1) 强化卖点逻辑；2) 购买引导要明确；3) 不夸大；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 7. tech_doc —— 技术文档
    # ─────────────────────────────────────────────────
    {
        "code": "tech_doc",
        "name": "技术文档",
        "description": "API 文档、使用指南风格：准确、逻辑清晰、带代码示例。适合开发者文档和技术博客。",
        "default_word_count": 2000,
        "outline_prompt": (
            "你是技术文档工程师。为以下技术主题设计一篇文档大纲。\n\n"
            "【主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "结构：概述 → 快速开始 → 核心概念 → API/参数说明 → 示例 → 常见问题。\n"
            '其中"API/参数说明"小节 content_type 设为 "table"，并给出 table_columns；\n'
            '其中"常见问题"小节 content_type 设为 "list"；\n'
            '其他小节 content_type 为 "text"。\n'
            "严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text|table|list", '
            '"key_points": ["..."], "table_columns": ["参数", "类型", "说明"]}}]}}'
        ),
        "section_prompt": (
            "为技术文档写一个小节。\n\n"
            "【主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出 Markdown 正文（不要重复标题）；\n"
            "2. 语言准确、简洁，面向开发者；\n"
            "3. 适当使用代码块（```）展示示例；\n"
            "4. 300-500 字；\n"
            "5. 仅使用参考资料里有的信息，不要编造 API。"
        ),
        "table_section_prompt": (
            "为技术文档写一个参数/接口说明表格。\n\n"
            "【主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【表格列名】{columns}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 输出 Markdown 表格，表头为指定列名；\n"
            "2. 覆盖所有关键参数/接口；\n"
            "3. 信息来自参考资料，不要编造；\n"
            "4. 不要输出表格以外的内容。"
        ),
        "list_section_prompt": (
            "为技术文档写一个常见问题列表。\n\n"
            "【主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【要点提示】{key_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 每个要点用 **Q: 问题** / **A: 回答** 格式；\n"
            "2. 回答简洁、准确，可附代码片段；\n"
            "3. 覆盖要点提示中的所有问题；\n"
            "4. 不要输出列表以外的内容。"
        ),
        "seo_prompt": (
            "为以下技术文档生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "关键词应包含【技术名 + 用途 + 版本】。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下技术文档做润色和校对：\n\n{full_content}\n\n"
            "要求：1) 检查技术准确性；2) 术语统一；3) 代码格式正确；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 8. marketing —— 营销文案
    # ─────────────────────────────────────────────────
    {
        "code": "marketing",
        "name": "营销文案",
        "description": "广告、落地页风格：情感化、转化导向、FOMO/紧迫感。适合广告投放和活动推广。",
        "default_word_count": 1000,
        "outline_prompt": (
            "你是营销文案专家。为以下产品/活动设计一篇营销文案大纲。\n\n"
            "【产品/活动】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "采用 AIDA 结构：注意力 → 兴趣 → 欲望 → 行动。\n"
            '每节 content_type 为 "text"。\n'
            "严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text", "key_points": ["..."]}}]}}'
        ),
        "section_prompt": (
            "为营销文案写一个小节。\n\n"
            "【产品/活动】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出 Markdown 正文（不要重复标题）；\n"
            "2. 情感化表达，制造紧迫感和 FOMO；\n"
            "3. 150-300 字；\n"
            "4. 不要编造数据，使用参考资料中的信息。"
        ),
        "table_section_prompt": "",
        "list_section_prompt": "",
        "seo_prompt": (
            "为以下营销文案生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "关键词应包含【产品名 + 促销词 + 场景】。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下营销文案润色：\n\n{full_content}\n\n"
            "要求：1) 强化情感冲击力；2) CTA 要醒目；3) 节奏紧凑；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 9. comparison —— 对比评测
    # ─────────────────────────────────────────────────
    {
        "code": "comparison",
        "name": "对比评测",
        "description": "产品对比、技术选型风格：多维度对比表、优缺点并陈。适合产品评测和技术选型文章。",
        "default_word_count": 2000,
        "outline_prompt": (
            "你是产品评测专家。为以下对比主题设计一篇评测文章大纲。\n\n"
            "【对比主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "结构：概述 → 核心维度对比 → 各产品优缺点 → 适用场景 → 推荐结论。\n"
            '其中"核心维度对比"小节 content_type 设为 "table"，并给出 table_columns（如：对比维度, 产品A, 产品B）；\n'
            '其中"各产品优缺点"小节 content_type 设为 "list"；\n'
            '其他小节 content_type 为 "text"。\n'
            "严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text|table|list", '
            '"key_points": ["..."], "table_columns": ["对比维度", "产品A", "产品B"]}}]}}'
        ),
        "section_prompt": (
            "为对比评测文章写一个小节。\n\n"
            "【对比主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出 Markdown 正文（不要重复标题）；\n"
            "2. 客观公正，有理有据；\n"
            "3. 300-500 字；\n"
            "4. 仅使用参考资料里的数据，不要编造。"
        ),
        "table_section_prompt": (
            "为对比评测文章写一个多维度对比表格。\n\n"
            "【对比主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【表格列名】{columns}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 输出 Markdown 表格，表头为指定列名；\n"
            "2. 每行一个对比维度，内容简洁明了；\n"
            "3. 数据来自参考资料，不要编造；\n"
            "4. 不要输出表格以外的内容。"
        ),
        "list_section_prompt": (
            "为对比评测文章写一个优缺点列表。\n\n"
            "【对比主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【要点提示】{key_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 每个产品/方案单独列出优点和缺点；\n"
            "2. 用 **产品名** 做小标题，下面用 ✅ 优点 / ❌ 缺点 分列；\n"
            "3. 每点简洁，1-2 句话；\n"
            "4. 不要输出列表以外的内容。"
        ),
        "seo_prompt": (
            "为以下对比评测文章生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "关键词应包含【产品A vs 产品B + 对比 + 年份】。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下对比评测文章润色：\n\n{full_content}\n\n"
            "要求：1) 保持客观中立；2) 对比维度一致；3) 数据准确；4) 输出完整 Markdown。"
        ),
    },
    # ─────────────────────────────────────────────────
    # 10. tutorial —— 教程指南
    # ─────────────────────────────────────────────────
    {
        "code": "tutorial",
        "name": "教程指南",
        "description": "教学、操作步骤风格：分步骤、带示例、循序渐进。适合操作手册和入门教程。",
        "default_word_count": 1800,
        "outline_prompt": (
            "你是教程撰写专家。为以下主题设计一篇教程/指南的大纲。\n\n"
            "【主题】{topic}\n"
            "【目标字数】{target_word_count} 字\n"
            "【参考资料】\n{context}\n\n"
            "结构：前言（为什么学）→ 前置准备 → 分步骤教学 → 进阶技巧 → 总结。\n"
            '其中"前置准备"小节 content_type 设为 "list"；\n'
            '其中"分步骤教学"小节 content_type 设为 "list"，key_points 列出各步骤；\n'
            '其他小节 content_type 为 "text"。\n'
            "严格按 JSON 输出：\n"
            '{{"title": "...", "sections": [{{"heading": "...", "content_type": "text|list", '
            '"key_points": ["步骤1", "步骤2", "..."]}}]}}'
        ),
        "section_prompt": (
            "为教程/指南写一个小节。\n\n"
            "【主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【本节要点】{section_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 直接输出 Markdown 正文（不要重复标题）；\n"
            "2. 语言清晰、循序渐进，面向初学者；\n"
            "3. 适当使用代码块和截图描述；\n"
            "4. 300-500 字；\n"
            "5. 仅使用参考资料里的信息，不要编造。"
        ),
        "table_section_prompt": "",
        "list_section_prompt": (
            "为教程/指南写一个步骤列表。\n\n"
            "【主题】{topic}\n"
            "【小节标题】{section_title}\n"
            "【步骤要点】{key_points}\n"
            "【参考资料】\n{context}\n\n"
            "要求：\n"
            "1. 每个步骤用 **步骤 N: 标题** 做小标题；\n"
            "2. 每步下面写具体操作说明，可附代码块；\n"
            "3. 步骤之间有逻辑顺序，循序渐进；\n"
            "4. 不要输出列表以外的内容。"
        ),
        "seo_prompt": (
            "为以下教程/指南生成 SEO 元信息：\n\n"
            "【标题】{title}\n【正文】{full_content}\n\n"
            "关键词应包含【主题 + 教程/指南 + 年份】。严格 JSON：\n"
            '{{"meta_title": "≤60 字符", "meta_description": "≤155 字符", "keywords": ["..."]}}'
        ),
        "quality_prompt": (
            "对以下教程/指南润色：\n\n{full_content}\n\n"
            "要求：1) 步骤逻辑清晰；2) 术语准确；3) 代码格式正确；4) 输出完整 Markdown。"
        ),
    },
]


# ============================================================
# 灌库函数
# ============================================================


async def seed_prompts() -> None:
    """把 5 个预置模板写入 prompt_templates 表。

    幂等：按 (tenant_id IS NULL, code) 查，存在则更新，不存在则插入。
    这样改了 prompt 内容重跑就能更新生产模板。
    """
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    inserted = 0
    updated = 0
    async with Session() as db:
        for tpl_def in SYSTEM_TEMPLATES:
            existing = await db.scalar(
                select(PromptTemplate).where(
                    PromptTemplate.tenant_id.is_(None),
                    PromptTemplate.code == tpl_def["code"],
                )
            )
            if existing is None:
                db.add(
                    PromptTemplate(
                        tenant_id=None,
                        template_type=TemplateType.SYSTEM,
                        code=tpl_def["code"],
                        name=tpl_def["name"],
                        description=tpl_def["description"],
                        outline_prompt=tpl_def["outline_prompt"],
                        section_prompt=tpl_def["section_prompt"],
                        seo_prompt=tpl_def["seo_prompt"],
                        quality_prompt=tpl_def["quality_prompt"],
                        table_section_prompt=tpl_def.get("table_section_prompt", ""),
                        list_section_prompt=tpl_def.get("list_section_prompt", ""),
                        default_word_count=tpl_def["default_word_count"],
                        is_active=True,
                    )
                )
                inserted += 1
                print(f"  + 新增模板: {tpl_def['code']} ({tpl_def['name']})")
            else:
                # 更新（覆盖 prompt 内容，保留 id 和 created_at）
                existing.name = tpl_def["name"]
                existing.description = tpl_def["description"]
                existing.outline_prompt = tpl_def["outline_prompt"]
                existing.section_prompt = tpl_def["section_prompt"]
                existing.seo_prompt = tpl_def["seo_prompt"]
                existing.quality_prompt = tpl_def["quality_prompt"]
                existing.table_section_prompt = tpl_def.get("table_section_prompt", "")
                existing.list_section_prompt = tpl_def.get("list_section_prompt", "")
                existing.default_word_count = tpl_def["default_word_count"]
                existing.is_active = True
                updated += 1
                print(f"  ~ 更新模板: {tpl_def['code']}")
        await db.commit()

    await engine.dispose()
    print(f"\n✅ Prompt 模板已写入：新增 {inserted}，更新 {updated}")


if __name__ == "__main__":
    asyncio.run(seed_prompts())
