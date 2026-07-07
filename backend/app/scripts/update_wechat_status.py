"""更新微信发布状态的工具脚本

用途：查询微信发布状态并更新数据库中的 PublishLog 状态

使用方法：
  python -m app.scripts.update_wechat_status

或者作为定时任务运行（每分钟检查一次待审核的发布）
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.publish_log import PublishLog, PublishStatus
from app.models.publish_target import PublishTarget, PublishTargetType
from app.services.wechat_mp import WechatMpClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_pending_wechat_status():
    """更新所有待审核的微信发布状态"""
    async with get_db_session() as db:
        # 查询所有状态为 PENDING 的微信发布记录（最近 24 小时内）
        stmt = (
            select(PublishLog, PublishTarget)
            .join(PublishTarget, PublishLog.target_id == PublishTarget.id)
            .where(
                PublishLog.status == PublishStatus.PENDING,
                PublishTarget.type == PublishTargetType.WECHAT_MP,
                PublishLog.published_at >= datetime.utcnow() - timedelta(hours=24),
            )
        )

        result = await db.execute(stmt)
        records = result.all()

        if not records:
            logger.info("没有待更新的发布记录")
            return

        logger.info(f"找到 {len(records)} 条待更新的发布记录")

        for log, target in records:
            if not log.remote_id:
                logger.warning(f"PublishLog {log.id} 没有 remote_id，跳过")
                continue

            try:
                # 创建微信客户端
                client = WechatMpClient(
                    db=db,
                    app_id=target.config["app_id"],
                    app_secret=target.config["app_secret"],
                )

                # 查询发布状态
                status_data = await client.get_publish_status(log.remote_id)
                wechat_status = status_data.get("publish_status", 1)

                # 微信发布状态：
                # 0 = 成功
                # 1 = 审核中
                # 2 = 审核失败
                # 3 = 已发表（成功）

                if wechat_status in (0, 3):
                    # 发布成功
                    log.status = PublishStatus.SUCCESS
                    log.published_at = datetime.utcnow()
                    logger.info(f"✅ PublishLog {log.id} 更新为 SUCCESS")

                elif wechat_status == 2:
                    # 审核失败
                    log.status = PublishStatus.FAILED
                    log.error_message = status_data.get("fail_reason", "微信审核失败")
                    logger.info(f"❌ PublishLog {log.id} 更新为 FAILED")

                else:
                    # 仍在审核中
                    logger.info(f"⏳ PublishLog {log.id} 仍在审核中")

            except Exception as e:
                logger.error(f"更新 PublishLog {log.id} 失败: {e}")
                continue

        await db.commit()
        logger.info("状态更新完成")


async def main():
    """主函数"""
    await update_pending_wechat_status()


if __name__ == "__main__":
    asyncio.run(main())
