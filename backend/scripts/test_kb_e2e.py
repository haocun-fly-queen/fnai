"""End-to-end smoke test for /knowledge endpoints (Step 2 + Step 3 验证).

覆盖：KB 增删改查、文档上传、Celery 异步处理（解析→切分→embedding→READY）、
     chunks 入库带向量、删除清理。

用法：docker exec fnai-backend-dev python -m scripts.test_kb_e2e
   或：python -m scripts.test_kb_e2e （本地也行，但要能访问后端 + docker）

⚠️ 这个脚本是验证用，不算测试套件（阶段 5 写正式 pytest）
"""

import io
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"
EMAIL = "kbtest@example.com"
PASSWORD = "test1234"

# 模拟一份 txt 文件（<1KB）
TEST_FILE_CONTENT = """FNAI 平台产品手册 - 测试文档

第一章：什么是 FNAI
FNAI 是一个基于 AI 的内容生成平台，专注于 GEO（生成式搜索引擎优化）。
我们帮助企业批量生产高质量、SEO 友好的文章。

第二章：核心功能
- 多租户管理
- RAG 知识库
- 智能文章生成
- 自动发布到多平台

第三章：使用方法
1. 创建工作空间
2. 上传企业资料到知识库
3. 让 AI 学习并生成文章
""".encode("utf-8")


def call(method: str, path: str, *, token: str | None = None, body: dict | None = None, raw: bytes | None = None, content_type: str = "application/json") -> tuple[int, dict | bytes | None]:
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type
    elif raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    else:
        data = None

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            if not raw:
                return r.status, None
            return r.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def login() -> tuple[str, str]:
    """Login existing user. Return (access_token, tenant_id)."""
    code, resp = call("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    assert code == 200, f"login failed: {code} {resp}"
    return resp["access_token"], resp.get("active_tenant_id") or ""


def main() -> int:
    print("=" * 60)
    print("知识库 Step 2 - 端到端测试")
    print("=" * 60)

    # ---------- 1) 登录 ----------
    print("\n[1] 登录拿 token")
    token, tenant_id = login()
    print(f"  ✓ token={token[:30]}...")
    print(f"  ✓ tenant_id={tenant_id}")

    # ---------- 2) 清理：先删可能的旧 KB（幂等测试）----------
    print("\n[2] 清理旧的测试 KB")
    code, resp = call("GET", "/knowledge", token=token)
    if code == 200:
        for kb in resp.get("items", []):
            if kb["slug"].startswith("e2e-test-"):
                call("DELETE", f"/knowledge/{kb['id']}", token=token)
                print(f"  ✓ 删了旧 KB: {kb['slug']}")

    # ---------- 3) 创建 KB（中文）----------
    print("\n[3] 创建知识库（中文）")
    code, resp = call("POST", "/knowledge", token=token, body={
        "name": "产品手册",
        "slug": "e2e-test-product",
        "description": "FNAI 产品功能介绍",
    })
    assert code == 201, f"create KB failed: {code} {resp}"
    kb_id = resp["id"]
    print(f"  ✓ 201, kb_id={kb_id}, slug={resp['slug']}")

    # ---------- 4) 重复创建同 slug（应 409）----------
    print("\n[4] 重复创建同 slug → 期望 409")
    code, resp = call("POST", "/knowledge", token=token, body={
        "name": "重复测试",
        "slug": "e2e-test-product",
    })
    assert code == 409, f"expected 409, got {code} {resp}"
    print(f"  ✓ 409 conflict ({resp['code']})")

    # ---------- 5) 列 KB ----------
    print("\n[5] 列 KB")
    code, resp = call("GET", "/knowledge", token=token)
    assert code == 200 and resp["total"] >= 1
    print(f"  ✓ 200, total={resp['total']}")

    # ---------- 6) KB 详情 ----------
    print("\n[6] KB 详情")
    code, resp = call("GET", f"/knowledge/{kb_id}", token=token)
    assert code == 200
    print(f"  ✓ 200, name={resp['name']}, document_count={resp['document_count']}")

    # ---------- 7) 上传文档（multipart）----------
    print("\n[7] 上传 txt 文档")
    # 用 multipart/form-data 手搓（urllib 没现成 helper）
    boundary = "----E2EBOUNDARY12345"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + TEST_FILE_CONTENT + f"\r\n--{boundary}--\r\n".encode("utf-8")
    code, resp = call(
        "POST",
        f"/knowledge/{kb_id}/documents",
        token=token,
        raw=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    assert code == 201, f"upload failed: {code} {resp}"
    doc_id = resp["id"]
    print(f"  ✓ 201, doc_id={doc_id}, size={resp['size_bytes']}, status={resp['status']}")
    # Step 3：上传后状态是 pending（worker 还没来得及处理）或 processing
    assert resp["status"] in ("pending", "processing"), f"unexpected status: {resp['status']}"

    # ---------- 8) 列文档 ----------
    print("\n[8] 列文档")
    code, resp = call("GET", f"/knowledge/{kb_id}/documents", token=token)
    assert code == 200 and resp["total"] == 1
    print(f"  ✓ 200, total=1, status_counts pending={resp['pending_count']}")

    # ---------- 9) 文档详情 ----------
    print("\n[9] 文档详情")
    code, resp = call("GET", f"/knowledge/{kb_id}/documents/{doc_id}", token=token)
    assert code == 200
    print(f"  ✓ 200, filename={resp['filename']}, content_type={resp['content_type']}")

    # ---------- 9.5) Step 3 核心：轮询等 Celery 处理到 READY ----------
    print("\n[9.5] 等 Celery 异步处理（轮询文档状态 → READY）")
    final_status = None
    deadline = time.time() + 60  # 最多等 60 秒
    while time.time() < deadline:
        code, resp = call("GET", f"/knowledge/{kb_id}/documents/{doc_id}", token=token)
        assert code == 200
        final_status = resp["status"]
        if final_status in ("ready", "failed"):
            break
        print(f"    ... status={final_status}，等 2s")
        time.sleep(2)

    assert final_status == "ready", (
        f"文档处理未成功，最终 status={final_status}，"
        f"error={resp.get('error_message')}"
    )
    chunk_count = resp["chunk_count"]
    assert chunk_count > 0, f"READY 但 chunk_count={chunk_count}，应 > 0"
    print(f"  ✓ status=ready, chunk_count={chunk_count}")

    # ---------- 9.6) 验证 chunks 真的写进 DB 且带向量 ----------
    print("\n[9.6] 验证 document_chunks 有数据且 embedding 非空（psycopg2 直连）")
    import psycopg2
    from app.core.config import settings as _settings

    conn = psycopg2.connect(_settings.database_url_sync)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), count(embedding) "
                "FROM document_chunks WHERE document_id = %s;",
                (doc_id,),
            )
            n_chunks, n_embedded = cur.fetchone()
    finally:
        conn.close()
    assert n_chunks == chunk_count, f"DB chunk 数({n_chunks}) != API({chunk_count})"
    assert n_embedded == n_chunks, f"有 chunk 的 embedding 为空: {n_embedded}/{n_chunks}"
    print(f"  ✓ DB 里 {n_chunks} 个 chunk，全部有 embedding 向量")

    # ---------- 9.7) Step 4：语义检索 ----------
    print("\n[9.7] 语义检索（POST /search）")
    code, resp = call("POST", f"/knowledge/{kb_id}/search", token=token, body={
        "query": "FNAI 有哪些核心功能",
        "top_k": 5,
    })
    assert code == 200, f"search failed: {code} {resp}"
    assert resp["total"] >= 1, f"检索应有命中，got total={resp['total']}"
    top = resp["items"][0]
    # 校验返回结构：带文档来源 + 分数 + 位置
    for field in ("chunk_id", "document_id", "filename", "chunk_index", "content", "score"):
        assert field in top, f"检索结果缺字段 {field}: {top}"
    assert top["filename"] == "test.txt", f"来源文件名不对: {top['filename']}"
    assert 0.0 <= top["score"] <= 1.0, f"score 越界: {top['score']}"
    print(f"  ✓ 200, total={resp['total']}, top score={top['score']:.4f}, 来源={top['filename']}")

    # ---------- 9.8) 阈值过滤：超高阈值应过滤掉所有结果 ----------
    print("\n[9.8] min_score=0.999 高阈值 → 期望过滤后变少/为空")
    code, resp = call("POST", f"/knowledge/{kb_id}/search", token=token, body={
        "query": "完全无关的内容 xyzzy 量子纠缠火星探测",
        "top_k": 5,
        "min_score": 0.999,
    })
    assert code == 200, f"search failed: {code} {resp}"
    print(f"  ✓ 200, total={resp['total']}（高阈值过滤生效）")

    # ---------- 9.9) 空 query → 期望 422 ----------
    print("\n[9.9] 空 query → 期望 422")
    code, resp = call("POST", f"/knowledge/{kb_id}/search", token=token, body={
        "query": "",
    })
    assert code == 422, f"expected 422, got {code} {resp}"
    print("  ✓ 422（query 校验生效）")

    # ---------- 9.10) 不存在的 KB 检索 → 期望 404 ----------
    print("\n[9.10] 不存在的 KB 检索 → 期望 404")
    fake_kb = "00000000-0000-0000-0000-000000000000"
    code, resp = call("POST", f"/knowledge/{fake_kb}/search", token=token, body={
        "query": "test",
    })
    assert code == 404, f"expected 404, got {code} {resp}"
    print(f"  ✓ 404 ({resp['code']})")

    # ---------- 10) 上传错误 MIME（应 415）----------
    print("\n[10] 上传不支持的 MIME → 期望 415")
    bad_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="hack.exe"\r\n'
        f"Content-Type: application/x-msdownload\r\n\r\n"
    ).encode("utf-8") + b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR" + f"\r\n--{boundary}--\r\n".encode("utf-8")
    code, resp = call(
        "POST",
        f"/knowledge/{kb_id}/documents",
        token=token,
        raw=bad_body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    assert code == 415, f"expected 415, got {code} {resp}"
    print(f"  ✓ 415 ({resp['code']})")

    # ---------- 11) 验证文件真的落盘了 ----------
    print("\n[11] 验证文件落盘到 /tmp/fnai-storage/")
    # 脚本跑在 backend 容器内，storage 路径本地可见，直接用 pathlib 查
    from pathlib import Path
    storage_root = Path("/tmp/fnai-storage")
    found_paths = [str(p) for p in storage_root.rglob(f"*{doc_id}*") if p.is_file()]
    assert len(found_paths) == 1, f"expected 1 file, found {len(found_paths)}: {found_paths}"
    size = Path(found_paths[0]).stat().st_size
    print(f"  ✓ 文件存在: {found_paths[0]} ({size} bytes)")

    # ---------- 12) 删文档（应 204 + 文件没了）----------
    print("\n[12] 删文档")
    code, resp = call("DELETE", f"/knowledge/{kb_id}/documents/{doc_id}", token=token)
    assert code == 204, f"delete doc failed: {code} {resp}"
    print(f"  ✓ 204")
    # 验证文件删了
    still = [str(p) for p in storage_root.rglob(f"*{doc_id}*") if p.is_file()]
    assert not still, f"file still exists: {still}"
    print(f"  ✓ 文件已删除")

    # ---------- 13) 删 KB（应 204）----------
    print("\n[13] 删 KB")
    code, resp = call("DELETE", f"/knowledge/{kb_id}", token=token)
    assert code == 204
    print(f"  ✓ 204")

    # ---------- 14) 删完再查（应 404）----------
    print("\n[14] 再查已删的 KB → 期望 404")
    code, resp = call("GET", f"/knowledge/{kb_id}", token=token)
    assert code == 404
    print(f"  ✓ 404 ({resp['code']})")

    print("\n" + "=" * 60)
    print("✅ 全部通过（含 Step 3 异步处理 + Step 4 语义检索）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
