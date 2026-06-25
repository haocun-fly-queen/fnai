"""End-to-end smoke test for /knowledge endpoints (Step 2 验证).

用法：docker exec fnai-backend-dev python -m scripts.test_kb_e2e
   或：python -m scripts.test_kb_e2e （本地也行，但要能访问后端）

⚠️ 这个脚本是验证用，不算测试套件（阶段 5 写正式 pytest）
"""

import io
import json
import sys
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
    assert resp["status"] == "pending", "Step 2 should leave doc in pending"
    assert resp["chunk_count"] == 0, "no chunks until Step 3 Celery runs"

    # ---------- 8) 列文档 ----------
    print("\n[8] 列文档")
    code, resp = call("GET", f"/knowledge/{kb_id}/documents", token=token)
    assert code == 200 and resp["total"] == 1
    assert resp["pending_count"] == 1
    print(f"  ✓ 200, total=1, pending={resp['pending_count']}")

    # ---------- 9) 文档详情 ----------
    print("\n[9] 文档详情")
    code, resp = call("GET", f"/knowledge/{kb_id}/documents/{doc_id}", token=token)
    assert code == 200
    print(f"  ✓ 200, filename={resp['filename']}, content_type={resp['content_type']}")

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

    # ---------- 11) 验证文件真的落盘了（容器里）----------
    print("\n[11] 验证文件在容器 /tmp/fnai-storage/ 里")
    # 文件存在 backend 容器里，不在宿主机
    # 用 docker exec 查
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "fnai-backend-dev", "find", "/tmp/fnai-storage", "-name", f"*{doc_id}*"],
        capture_output=True, text=True, timeout=10,
    )
    found_paths = [p for p in result.stdout.strip().split("\n") if p]
    assert len(found_paths) == 1, f"expected 1 file in container, found {len(found_paths)}: {found_paths}"
    # 取文件大小
    sz_result = subprocess.run(
        ["docker", "exec", "fnai-backend-dev", "stat", "-c", "%s", found_paths[0]],
        capture_output=True, text=True, timeout=10,
    )
    size = int(sz_result.stdout.strip())
    print(f"  ✓ 文件存在: {found_paths[0]} ({size} bytes)")

    # ---------- 12) 删文档（应 204 + 文件没了）----------
    print("\n[12] 删文档")
    code, resp = call("DELETE", f"/knowledge/{kb_id}/documents/{doc_id}", token=token)
    assert code == 204, f"delete doc failed: {code} {resp}"
    print(f"  ✓ 204")
    # 验证文件删了（容器里）
    result = subprocess.run(
        ["docker", "exec", "fnai-backend-dev", "find", "/tmp/fnai-storage", "-name", f"*{doc_id}*"],
        capture_output=True, text=True, timeout=10,
    )
    still = [p for p in result.stdout.strip().split("\n") if p]
    assert not still, f"file still exists in container: {still}"
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
    print("✅ 全部通过（14 个场景）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
