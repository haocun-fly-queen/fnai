# 概念：Celery 应用实例（异步任务调度中枢）
#   Celery 是 Python 的分布式任务队列。FastAPI 进程把"耗时活儿"（解析+向量化）
#   丢进队列立刻返回，由独立的 worker 进程在后台慢慢做。
#   消息中转站（broker）用 Redis，任务结果也存 Redis。
#   Java 对照：≈ Spring 的 @Async + RabbitMQ/分布式任务，但更轻、更显式。
#
# 模块：backend/app/workers/celery_app.py。
#   被两边 import：
#     - FastAPI 进程：拿到 app 实例好调 process_document.delay(...) 投递任务
#     - worker 进程：celery -A app.workers.celery_app worker 启动时加载
#
# 作用：
#   创建并配置全局唯一的 Celery 实例 `celery_app`；声明去哪找任务模块（include）。
#   不干什么：不定义具体任务（那是 tasks.py 的事）。
#
# 怎么写：
#   - broker / backend 从 settings 读（celery_broker_url=redis db1, result=db2）。
#   - include=["app.workers.tasks"]：告诉 worker 启动时导入这个模块注册任务。
#   - 关键配置：
#       task_acks_late=True        任务执行完才确认，worker 崩了任务会重投（at-least-once）
#       worker_prefetch_multiplier=1  一次只取一个任务，长任务场景更公平
#       task_track_started=True    能看到 STARTED 状态，便于排查卡住的任务
#       时区设 Asia/Shanghai，序列化用 json（安全，不用 pickle）

from celery import Celery

from app.core.config import settings

# 全局唯一 Celery 实例
celery_app = Celery(
    "fnai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # ---- 序列化（用 json，不用 pickle，避免反序列化安全风险）----
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ---- 时区 ----
    timezone="Asia/Shanghai",
    enable_utc=True,
    # ---- 可靠性 ----
    task_acks_late=True,             # 执行完再 ack，崩溃可重投
    worker_prefetch_multiplier=1,    # 长任务公平分发
    task_track_started=True,         # 暴露 STARTED 状态
    # ---- 结果保留 1 天，避免 Redis 堆积 ----
    result_expires=86400,
    # ---- 单任务硬/软超时（防卡死）：软 9 分钟抛异常，硬 10 分钟杀进程 ----
    task_soft_time_limit=540,
    task_time_limit=600,
)
