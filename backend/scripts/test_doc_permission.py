"""
文档级权限自测脚本

运行：python3 scripts/test_doc_permission.py（需先启动后端并初始化种子数据）

覆盖：
- 可见性三态：tenant（租户公开）/ private（仅上传者）/ roles（指定角色）
- 检索与问答链路的可见性过滤（private 文档的 chunk 不被他人召回）
- 文档列表的可见性过滤
- 上传参数校验（非法可见性 / roles 缺角色 / 非法角色 → 400）
- 删除权限（他人文档 403，上传者本人 200）

账号（种子数据，均属星辰科技租户）：
- zhangsan / manager（上传者）
- lisi / employee（普通用户）
- wangwu / auditor
"""

import sys
import tempfile
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0

# 每份测试文档埋入唯一关键词，便于判定检索命中来源
SECRET_PRIVATE = "ZEBRA7749"
SECRET_ROLES = "FALCON3312"
SECRET_TENANT = "OTTER5580"


def check(name: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}：期望 {expected}，实际 {actual}")


def login(client: httpx.Client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败 {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def make_doc(keyword: str) -> Path:
    """生成含唯一关键词的临时 Markdown 文档"""
    tmp = Path(tempfile.mkstemp(suffix=".md")[1])
    tmp.write_text(
        f"# 权限测试文档\n\n本文档的关键标识为 {keyword}，用于验证文档级权限过滤。\n",
        encoding="utf-8",
    )
    return tmp


def upload(client: httpx.Client, headers: dict, path: Path, visibility: str, roles: str | None = None):
    data = {"strategy": "paragraphs", "visibility": visibility}
    if roles:
        data["allowed_roles"] = roles
    with path.open("rb") as f:
        return client.post(
            f"{BASE}/api/documents",
            headers=headers,
            files={"file": (path.name, f, "text/markdown")},
            data=data,
        )


def search_hits(client: httpx.Client, headers: dict, keyword: str) -> set:
    """检索关键词，返回命中的 doc_id 集合"""
    resp = client.get(
        f"{BASE}/api/documents/search",
        headers=headers,
        params={"q": keyword, "top_k": 5},
    )
    assert resp.status_code == 200, resp.text
    return {c["doc_id"] for c in resp.json()["chunks"]}


def main() -> None:
    client = httpx.Client(timeout=120)
    h_zhang = login(client, "zhangsan", "zhangsan123")   # manager
    h_lisi = login(client, "lisi", "lisi123456")          # employee
    h_wang = login(client, "wangwu", "wangwu123")         # auditor
    h_cloud = login(client, "cloud_manager", "cloud123456")  # 其他租户

    docs: dict[str, str] = {}
    tmp_files = []
    try:
        # ---------- 1. 参数校验 ----------
        print("\n[1] 上传参数校验")
        f = make_doc("VALIDATION")
        tmp_files.append(f)
        check("非法可见性 → 400", upload(client, h_zhang, f, "public").status_code, 400)
        check("roles 缺角色 → 400", upload(client, h_zhang, f, "roles").status_code, 400)
        check(
            "非法角色 → 400",
            upload(client, h_zhang, f, "roles", "superuser").status_code,
            400,
        )

        # ---------- 2. 三态上传 ----------
        print("\n[2] 上传三种可见性的文档")
        f_private = make_doc(SECRET_PRIVATE)
        f_roles = make_doc(SECRET_ROLES)
        f_tenant = make_doc(SECRET_TENANT)
        tmp_files += [f_private, f_roles, f_tenant]

        resp = upload(client, h_zhang, f_private, "private")
        check("private 文档上传 200", resp.status_code, 200)
        docs["private"] = resp.json()["id"]

        resp = upload(client, h_zhang, f_roles, "roles", "auditor")
        check("roles 文档上传 200", resp.status_code, 200)
        docs["roles"] = resp.json()["id"]

        resp = upload(client, h_zhang, f_tenant, "tenant")
        check("tenant 文档上传 200", resp.status_code, 200)
        docs["tenant"] = resp.json()["id"]

        # ---------- 3. 检索可见性 ----------
        # 注意：向量检索始终返回 Top-K 近邻（可能包含语义无关的文档块），
        # 因此判定口径是"目标文档是否出现在命中中"，而非"命中是否为空"
        print("\n[3] 检索链路可见性过滤")
        check("上传者本人可检索 private 文档", docs["private"] in search_hits(client, h_zhang, SECRET_PRIVATE), True)
        check("employee 检索不到 private 文档", docs["private"] in search_hits(client, h_lisi, SECRET_PRIVATE), False)
        check("auditor 检索不到 private 文档", docs["private"] in search_hits(client, h_wang, SECRET_PRIVATE), False)

        check("auditor 可检索 roles 文档", docs["roles"] in search_hits(client, h_wang, SECRET_ROLES), True)
        check("上传者本人可检索 roles 文档", docs["roles"] in search_hits(client, h_zhang, SECRET_ROLES), True)
        check("employee 检索不到 roles 文档", docs["roles"] in search_hits(client, h_lisi, SECRET_ROLES), False)

        check("employee 可检索 tenant 文档", docs["tenant"] in search_hits(client, h_lisi, SECRET_TENANT), True)

        # 跨租户：其他租户完全检索不到（租户隔离仍然生效）
        check("其他租户检索不到 tenant 文档", docs["tenant"] in search_hits(client, h_cloud, SECRET_TENANT), False)

        # ---------- 4. 问答链路 ----------
        print("\n[4] 问答链路可见性过滤")
        resp = client.post(
            f"{BASE}/api/qa/ask", headers=h_lisi, json={"question": f"{SECRET_PRIVATE} 是什么？"}
        )
        check("employee 提问 private 文档内容 → 拒答", resp.json()["refused"], True)
        resp = client.post(
            f"{BASE}/api/qa/ask", headers=h_zhang, json={"question": f"{SECRET_PRIVATE} 是什么？"}
        )
        check("上传者提问 private 文档内容 → 不拒答", resp.json()["refused"], False)

        # ---------- 5. 列表可见性 ----------
        print("\n[5] 文档列表可见性过滤")
        list_lisi = {d["id"] for d in client.get(f"{BASE}/api/documents", headers=h_lisi).json()["items"]}
        check("employee 列表不含 private 文档", docs["private"] not in list_lisi, True)
        check("employee 列表不含 roles 文档", docs["roles"] not in list_lisi, True)
        check("employee 列表含 tenant 文档", docs["tenant"] in list_lisi, True)

        list_wang = {d["id"] for d in client.get(f"{BASE}/api/documents", headers=h_wang).json()["items"]}
        check("auditor 列表含 roles 文档", docs["roles"] in list_wang, True)
        check("auditor 列表不含 private 文档", docs["private"] not in list_wang, True)

        list_zhang = {d["id"] for d in client.get(f"{BASE}/api/documents", headers=h_zhang).json()["items"]}
        check("上传者列表含全部三份", {docs["private"], docs["roles"], docs["tenant"]} <= list_zhang, True)

        item = next(
            d for d in client.get(f"{BASE}/api/documents", headers=h_zhang).json()["items"]
            if d["id"] == docs["roles"]
        )
        check("roles 文档返回可见角色", item["allowed_roles"], ["auditor"])
        check("is_owner 标记正确", item["is_owner"], True)

        # ---------- 6. 删除权限 ----------
        print("\n[6] 删除权限")
        denied = client.delete(f"{BASE}/api/documents/{docs['tenant']}", headers=h_lisi)
        check("employee 删除他人文档 → 403", denied.status_code, 403)
        allowed = client.delete(f"{BASE}/api/documents/{docs['tenant']}", headers=h_zhang)
        check("上传者删除自己的文档 → 200", allowed.status_code, 200)
        docs.pop("tenant")

    finally:
        # 清理：上传者删除剩余测试文档 + 临时文件
        for doc_id in list(docs.values()):
            resp = client.delete(f"{BASE}/api/documents/{doc_id}", headers=h_zhang)
            print(f"      清理文档 {doc_id}: HTTP {resp.status_code}")
        for f in tmp_files:
            f.unlink(missing_ok=True)

    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
