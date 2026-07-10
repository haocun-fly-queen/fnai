"""一次性迁移脚本：加密存量的发布目标敏感字段。

用途：把数据库中已有的明文 app_secret / app_password / cookie / headers 加密。
      加密是幂等的（已加密的值会跳过），可安全重复运行。

使用方法：
    # 先配置 ENCRYPTION_KEY 环境变量（与线上一致）
    python -m app.scripts.encrypt_existing_configs           # 实际执行
    python -m app.scripts.encrypt_existing_configs --dry-run  # 仅预览，不写库

注意：
    - 运行前务必备份数据库
    - ENCRYPTION_KEY 必须与后续运行时使用的密钥一致，否则解密会失败
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.core.config_crypto import encrypt_config
from app.core.crypto import get_crypto_service
from app.db.session import session_scope
from app.models.publish_target import PublishTarget

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate(dry_run: bool = False) -> None:
    """加密所有发布目标的敏感字段。

    Args:
        dry_run: 若为 True，只统计不写库
    """
    # 触发密钥检查（生产环境未配置会在这里抛错）
    get_crypto_service()

    async with session_scope() as db:
        result = await db.execute(select(PublishTarget))
        targets = list(result.scalars().all())

        logger.info(f"共 {len(targets)} 个发布目标待检查")

        changed = 0
        for target in targets:
            old_config = dict(target.config) if target.config else {}
            new_config = encrypt_config(target.type, old_config)

            # 判断是否有字段实际发生变化（即存在需要加密的明文）
            if new_config != old_config:
                changed += 1
                changed_fields = [
                    k for k in new_config
                    if old_config.get(k) != new_config.get(k)
                ]
                logger.info(
                    f"[{'DRY-RUN' if dry_run else 'ENCRYPT'}] "
                    f"target={target.id} type={target.type} "
                    f"fields={changed_fields}"
                )
                if not dry_run:
                    target.config = new_config  # 整体赋值触发 JSONB 变更检测

        if dry_run:
            logger.info(f"[DRY-RUN] 将加密 {changed} 个发布目标（未写库）")
        else:
            await db.commit()
            logger.info(f"完成：加密了 {changed} 个发布目标")


def main() -> None:
    parser = argparse.ArgumentParser(description="加密存量发布目标敏感字段")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览将要加密的记录，不实际写库",
    )
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
