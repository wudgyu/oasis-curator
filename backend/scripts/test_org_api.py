"""
组织 API 权限矩阵自测脚本

运行：python3 scripts/test_org_api.py（需先启动后端并初始化种子数据）

覆盖：
- 创建子组织（子树内 201 / 平级 403 / employee 403 / 同名 409）
- 重命名（子树内 200 / 平级 403）
- 移动（新父不在子树 403 / admin 成功 / 环 400 / 根组织 400）
- 删除（非空 409 / 空组织 200 / 根组织 400）
- 上下文租户校验（伪造 403 / admin 缺头 400）
"""

import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0


def call(method, path, token=None, body=None, headers=None):
    """发起 HTTP 请求，返回 (status, json_body)"""
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}：期望 {expected}，实际 {actual}")


def login(username, password):
    _, body = call("POST", "/api/auth/login", body={"username": username, "password": password})
    return body["access_token"]


def find_org(token, name):
    _, tree = call("GET", "/api/orgs/tree", token=token)

    def walk(nodes):
        for n in nodes:
            if n["name"] == name:
                return n
            r = walk(n["children"])
            if r:
                return r

    return walk(tree)


def main():
    # ---------- 登录 ----------
    admin = login("admin", "admin123")
    zhangsan = login("zhangsan", "zhangsan123")   # manager @ 研发部
    zhaoliu = login("zhaoliu", "zhaoliu123")      # manager @ 市场部
    lisi = login("lisi", "lisi123456")            # employee @ 后端组
    wangwu = login("wangwu", "wangwu123")         # auditor @ 根

    star_id = call("GET", "/api/auth/me", token=zhangsan)[1]["tenant"]["id"]
    rd = find_org(zhangsan, "研发部")
    be = find_org(zhangsan, "后端组")
    mkt = find_org(zhangsan, "市场部")
    root = find_org(zhangsan, "星辰科技")

    print("== 1. 创建子组织 ==")
    s, body = call("POST", "/api/orgs", token=zhangsan,
                   body={"name": "测试组", "parent_id": rd["id"]})
    check("manager 在子树内创建", s, 201)
    test_org_id = body.get("id", "")
    check("新组织 path 以父 path 为前缀", body.get("path", "").startswith(rd["path"]), True)

    s, _ = call("POST", "/api/orgs", token=zhaoliu,
                body={"name": "越权组", "parent_id": rd["id"]})
    check("manager 在平级组织下创建 → 403", s, 403)

    s, _ = call("POST", "/api/orgs", token=lisi,
                body={"name": "员工建组", "parent_id": be["id"]})
    check("employee 创建 → 403", s, 403)

    s, _ = call("POST", "/api/orgs", token=zhangsan,
                body={"name": "后端组", "parent_id": rd["id"]})
    check("同级同名组织 → 409", s, 409)

    print("== 2. 重命名 ==")
    s, body = call("PUT", f"/api/orgs/{test_org_id}", token=zhangsan, body={"name": "测试组-改"})
    check("manager 重命名子树内组织", s, 200)
    check("重命名生效", body.get("name"), "测试组-改")

    s, _ = call("PUT", f"/api/orgs/{mkt['id']}", token=zhangsan, body={"name": "市场部X"})
    check("manager 重命名平级组织 → 403", s, 403)

    print("== 3. 移动 ==")
    s, _ = call("POST", f"/api/orgs/{test_org_id}/move", token=zhangsan,
                body={"new_parent_id": mkt["id"]})
    check("manager 移动到子树外 → 403", s, 403)

    s, body = call("POST", f"/api/orgs/{test_org_id}/move", token=admin,
                   body={"new_parent_id": mkt["id"]},
                   headers={"X-Tenant-Id": star_id})
    check("admin 移动成功", s, 200)
    check("移动后 parent_id 正确", body.get("parent_id"), mkt["id"])
    check("移动后 path 正确", body.get("path"), mkt["path"] + test_org_id + "/")

    s, _ = call("POST", f"/api/orgs/{rd['id']}/move", token=admin,
                body={"new_parent_id": be["id"]}, headers={"X-Tenant-Id": star_id})
    check("移动到自身子组织（环）→ 400", s, 400)

    s, _ = call("POST", f"/api/orgs/{root['id']}/move", token=admin,
                body={"new_parent_id": mkt["id"]}, headers={"X-Tenant-Id": star_id})
    check("移动根组织 → 400", s, 400)

    print("== 4. 删除 ==")
    s, _ = call("DELETE", f"/api/orgs/{mkt['id']}", token=zhangsan)
    check("manager 删除平级组织 → 403", s, 403)

    s, _ = call("DELETE", f"/api/orgs/{mkt['id']}", token=admin, headers={"X-Tenant-Id": star_id})
    check("删除非空组织 → 409", s, 409)

    s, _ = call("DELETE", f"/api/orgs/{test_org_id}", token=admin, headers={"X-Tenant-Id": star_id})
    check("admin 删除空组织", s, 200)

    s, _ = call("DELETE", f"/api/orgs/{root['id']}", token=admin, headers={"X-Tenant-Id": star_id})
    check("删除根组织 → 400", s, 400)

    print("== 5. 上下文租户校验 ==")
    s, _ = call("GET", "/api/orgs/tree", token=zhangsan, headers={"X-Tenant-Id": "fake-id"})
    check("普通用户伪造 X-Tenant-Id → 403", s, 403)

    s, _ = call("GET", "/api/orgs/tree", token=admin)
    check("admin 缺 X-Tenant-Id → 400", s, 400)

    s, _ = call("GET", "/api/orgs/tree", token=wangwu)
    check("auditor 可读组织树", s, 200)

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()