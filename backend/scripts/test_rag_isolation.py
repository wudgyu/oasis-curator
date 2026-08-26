"""
RAG 多租户隔离自测脚本

运行：python3 scripts/test_rag_isolation.py（需先启动后端并初始化种子数据）

覆盖：
- 租户 A（星辰科技）上传文档成功
- 租户 B（云端数据）的文档列表看不到 A 的文档
- 租户 B 语义检索 / RAG 问答均无法命中 A 的文档内容
- 租户 A 自身检索正常（对照组）
"""

import sys
import os
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
SAMPLE_PDF = Path(__file__).resolve().parent.parent / "data" / "samples" / "oasis_curator_manual.pdf"

passed = 0
failed = 0


def check(name: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}：期望 {expected}，实际 {actual}")


def login(client: httpx.Client, username: str, password: str) -> str:
    resp = client.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    return resp.json()["access_token"]


def main() -> None:
    client = httpx.Client(timeout=120)
    token_a = login(client, "zhangsan", "zhangsan123")      # 星辰科技 manager
    token_b = login(client, "cloud_manager", "cloud123456")  # 云端数据 manager
    ha = {"Authorization": f"Bearer {token_a}"}
    hb = {"Authorization": f"Bearer {token_b}"}

    doc_id = None
    try:
        # 1. 租户 A 上传示例 PDF
        with SAMPLE_PDF.open("rb") as f:
            resp = client.post(
                f"{BASE}/api/documents",
                headers=ha,
                files={"file": ("oasis_curator_manual.pdf", f, "application/pdf")},
                data={"strategy": "paragraphs"},
            )
        check("租户 A 上传 PDF 返回 200", resp.status_code, 200)
        body = resp.json()
        doc_id = body["id"]
        print(f"      文档 {doc_id}，解析 {body['chunk_count']} 个文本块")
        check("上传结果包含 chunk 数量", body["chunk_count"] > 0, True)

        # 2. 租户 B 的文档列表看不到 A 的文档
        resp = client.get(f"{BASE}/api/documents", headers=hb)
        check("租户 B 文档列表返回 200", resp.status_code, 200)
        ids_b = [d["id"] for d in resp.json()["items"]]
        check("租户 B 列表不包含 A 的文档", doc_id not in ids_b, True)

        # 3. 租户 B 语义检索：用能命中手册内容的问题，应检索不到任何 A 的文档
        question = "RAG 问答的重排序保留几个候选块？"
        resp = client.get(
            f"{BASE}/api/documents/search",
            headers=hb,
            params={"q": question, "top_k": 5},
        )
        check("租户 B 语义检索返回 200", resp.status_code, 200)
        chunks_b = resp.json()["chunks"]
        check(
            "租户 B 检索不到 A 的文档内容",
            all(c["doc_id"] != doc_id for c in chunks_b),
            True,
        )

        # 4. 租户 B RAG 问答：应拒答（隔离在问答层同样生效）
        resp = client.post(f"{BASE}/api/qa/ask", headers=hb, json={"question": question})
        check("租户 B 问答返回 200", resp.status_code, 200)
        qa_b = resp.json()
        check(
            "租户 B 问答不引用 A 的文档",
            all(doc_id not in c.get("source_file", "") and True for c in qa_b["reranked"]),
            True,
        )

        # 5. 对照组：租户 A 自己能检索到
        resp = client.get(
            f"{BASE}/api/documents/search",
            headers=ha,
            params={"q": question, "top_k": 5},
        )
        chunks_a = resp.json()["chunks"]
        check("租户 A 检索命中自己的文档", any(c["doc_id"] == doc_id for c in chunks_a), True)

        # 6. 租户 B 删除 A 的文档 → 404
        resp = client.delete(f"{BASE}/api/documents/{doc_id}", headers=hb)
        check("租户 B 删除 A 的文档返回 404", resp.status_code, 404)

    finally:
        # 清理：租户 A 删除测试文档
        if doc_id:
            resp = client.delete(f"{BASE}/api/documents/{doc_id}", headers=ha)
            print(f"      清理文档 {doc_id}: HTTP {resp.status_code}")

    print(f"\n{'=' * 50}")
    print(f"通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
