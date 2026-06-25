"""对象存储客户端 —— Step 2 用本地落盘，Step 4 切 MinIO。

⚠️ 开发期临时实现：把文件直接落到宿主机的 /tmp/fnai-storage/。
    生产必须换成 MinIO/S3，原因有三：
      1. 多实例部署时本地落盘数据不共享
      2. 没有副本，单盘故障 = 数据丢失
      3. 没有访问控制（谁都能 cat）

但现在阶段 3 还在搭骨架，**先跑通业务链**，后面再换。

类比 Java：
    LocalStorage  ≈  本地 FileSystem 的封装
    MinioStorage  ≈  AmazonS3Client

    接口一致（put_bytes / get_path / delete / get_size），
    上层 service 不感知底层是本地还是 S3。

⚠️ 路径设计：
    /tmp/fnai-storage/{tenant_id}/{kb_id}/{doc_id}.{ext}
    - tenant_id 第一层：方便"删租户"时 rm -rf /tmp/fnai-storage/{tid}
    - kb_id 第二层：方便"删 KB"时 rm -rf /tmp/fnai-storage/{tid}/{kid}
    - doc_id 第三层：UUID 防重
    - ext 保留：方便运维/调试时一眼看出文件类型
"""

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# ⚠️ 当前用本地落盘（开发期）
# 切 MinIO 时改成从 settings 读 + 用 boto3/minio SDK
LOCAL_STORAGE_ROOT = Path("/tmp/fnai-storage")


# ============================================================
# 路径生成
# ============================================================


def build_storage_key(
    *,
    tenant_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    filename: str,
) -> str:
    """生成 storage_key（DB 里存的"逻辑路径"）。

    用 doc_id 而不是 filename 当 key 的核心部分：
      - 防路径注入（用户文件名是 ../../etc/passwd 也不怕）
      - 防重名冲突

    Args:
        tenant_id: 租户 ID
        knowledge_base_id: 知识库 ID
        document_id: 文档 ID（已生成的 UUID）
        filename: 原始文件名（只用来取扩展名）

    Returns:
        类似 "tenants/{tid}/kb/{kid}/docs/{did}.pdf" 的字符串
    """
    # 取扩展名（最多 5 字符防恶意），统一小写
    ext = Path(filename).suffix.lower()
    # 限制扩展名长度 + 字符集（防 .exe / .php 这种"假扩展名"）
    safe_ext = "".join(c for c in ext if c.isalnum() or c == ".")[:8]

    return (
        f"tenants/{tenant_id}/kb/{knowledge_base_id}/docs/"
        f"{document_id}{safe_ext}"
    )


def local_path_from_key(storage_key: str) -> Path:
    """把 storage_key 翻译成本地文件系统路径。

    ⚠️ 防止 path traversal：拒绝包含 ".." 的 key
    """
    if ".." in storage_key:
        raise ValueError(f"Invalid storage_key (contains '..'): {storage_key!r}")
    return LOCAL_STORAGE_ROOT / storage_key


# ============================================================
# 存储操作（接口稳定，以后换 MinIO 只改这里）
# ============================================================


def put_bytes(storage_key: str, data: bytes) -> str:
    """把字节流写入存储，返回 storage_key。

    Args:
        storage_key: 逻辑路径（来自 build_storage_key）
        data: 文件字节内容

    Returns:
        写入的 storage_key（幂等：相同 key 会覆盖）

    Raises:
        OSError: 磁盘满 / 权限错 / 路径无效
    """
    path = local_path_from_key(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("put_bytes: %s (%d bytes)", storage_key, len(data))
    return storage_key


def get_path(storage_key: str) -> Path:
    """取文件本地路径（用于 FastAPI FileResponse 或读取解析）。

    Returns:
        Path 对象，不存在时 raise FileNotFoundError
    """
    path = local_path_from_key(storage_key)
    if not path.exists():
        raise FileNotFoundError(f"Storage object not found: {storage_key}")
    return path


def get_size(storage_key: str) -> int:
    """取文件大小（字节）。不存在返回 0。"""
    try:
        return get_path(storage_key).stat().st_size
    except FileNotFoundError:
        return 0


def delete(storage_key: str) -> bool:
    """删除文件，返回是否真的删了什么。

    ⚠️ 静默成功：如果文件本来就不存在（重复删），返回 False
    这是为了幂等性：删两次不会报错
    """
    try:
        path = local_path_from_key(storage_key)
        if path.exists():
            path.unlink()
            logger.info("delete: %s", storage_key)
            return True
        return False
    except (OSError, ValueError) as exc:
        logger.warning("delete failed for %s: %s", storage_key, exc)
        return False


def delete_prefix(prefix: str) -> int:
    """删整个目录（用于"删 KB 时清理所有文档"）。

    Returns:
        实际删除的文件数
    """
    # 同样防 path traversal
    if ".." in prefix:
        raise ValueError(f"Invalid prefix: {prefix!r}")

    base = LOCAL_STORAGE_ROOT / prefix
    if not base.exists():
        return 0
    count = 0
    for f in base.rglob("*"):
        if f.is_file():
            try:
                f.unlink()
                count += 1
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", f, exc)
    # 删空目录
    try:
        for d in sorted(base.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if base.is_dir() and not any(base.iterdir()):
            base.rmdir()
    except OSError:
        pass
    return count


# ============================================================
# 启动时确保根目录存在
# ============================================================


def ensure_storage_root() -> None:
    """服务启动时调用一次（生产可挂到 lifespan）。"""
    LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    logger.info("Storage root ready: %s", LOCAL_STORAGE_ROOT)
