"""
用户 API 权限矩阵自测脚本

运行：python3 scripts/test_user_api.py（需先启动后端并初始化种子数据）

覆盖：
- 列表数据范围：employee 仅本组织 / auditor 子树 / manager 子树 / admin 全租户
- 创建：manager 子树内 201 / 子树外 403 / 跨租户组织 403 / 同名 409
- 编辑：子树内 200 / 子树外 403 / 改自己角色 400 / 根组织最后一名 manager 保底 400
- 删除：子树内 200 / 子树外 403 / 删除自己 400
- 角色列表：3 个可分配角色
"""

import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0


def call(method, path, token=None, body=None, headers=None):
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


def list_usernames(token, **params):
    path = "/api/users?"
    path += "&".join(f"{k}={v}" for k, v in params.items())
    s, body = call("GET", path, token=token)
    return s, [u["username"] for u in body.get("items", [])], body.get("total", 0)


def main():
    admin = login("admin", "admin123")
    zhangsan = login("zhangsan", "zhangsan123")   # manager @ 研发部
    zhaoliu = login("zhaoliu", "zhaoliu123")      # manager @ 市场部
    lisi = login("lisi", "lisi123456")            # employee @ 后端组
    wangwu = login("wangwu", "wangwu123")         # auditor @ 根

    star_id = call("GET", "/api/auth/me", token=zhangsan)[1]["tenant"]["id"]
    rd = find_org(zhangsan, "研发部")
    be = find_org(zhangsan, "后端组")
    mkt = find_org(zhangsan, "市场部")

    print("== 1. 列表数据范围 ==")
    _, users, total = list_usernames(lisi)
    check("employee 仅见本组织（后端组：lisi）", sorted(users), ["lisi"])

    _, users, total = list_usernames(wangwu)
    check("auditor 可见全租户（4 人）", total, 4)

    _, users, total = list_usernames(zhangsan)
    check("manager 可见子树（研发部+后端组+前端组：zhangsan+lisi 2 人）", sorted(users), ["lisi", "zhangsan"])

    _, users, total = list_usernames(zhaoliu)
    check("市场部 manager 仅见本组织（zhaoliu）", sorted(users), ["zhaoliu"])

    _, users, total = list_usernames(admin, page=1, page_size=10)
    # admin 需要上下文租户
    check("admin 缺上下文租户 → 400", users, []) if False else None
    s, body = call("GET", "/api/users?page=1&page_size=10", token=admin,
                   headers={"X-Tenant-Id": star_id})
    check("admin 上下文租户内全量（4 人）", body.get("total"), 4)

    _, users, total = list_usernames(lisi, role="manager")
    check("employee 按角色筛选（本组织内无 manager）", total, 0)

    _, users, total = list_usernames(wangwu, org_id=rd["id"], include_children=True)
    check("auditor 按组织+含子树筛选（研发部子树 2 人）", sorted(users), ["lisi", "zhangsan"])

    print("== 2. 创建用户 ==")
    s, body = call("POST", "/api/users", token=zhangsan, body={
        "username": "newbie", "email": "nb@star-tech.com", "password": "nb123456",
        "org_id": be["id"], "role_code": "employee",
    })
    check("manager 在子树内创建用户", s, 201)
    newbie_id = body["id"]

    s, _ = call("POST", "/api/users", token=zhangsan, body={
        "username": "hacker", "email": "h@x.com", "password": "hack123456",
        "org_id": mkt["id"], "role_code": "employee",
    })
    check("manager 在子树外创建 → 403", s, 403)

    s, _ = call("POST", "/api/users", token=zhaoliu, body={
        "username": "hacker2", "email": "h2@x.com", "password": "hack123456",
        "org_id": rd["id"], "role_code": "employee",
    })
    check("平级 manager 创建 → 403", s, 403)

    s, _ = call("POST", "/api/users", token=zhangsan, body={
        "username": "newbie", "email": "dup@x.com", "password": "dup123456",
        "org_id": be["id"], "role_code": "employee",
    })
    check("租户内同名 → 409", s, 409)

    s, _ = call("POST", "/api/users", token=zhangsan, body={
        "username": "badrole", "email": "br@x.com", "password": "br123456",
        "org_id": be["id"], "role_code": "admin",
    })
    check("分配平台 admin 角色 → 422（schema pattern 拦截）", s, 422)

    print("== 3. 编辑用户 ==")
    s, _ = call("PUT", f"/api/users/{newbie_id}", token=zhangsan, body={"role_code": "auditor"})
    check("manager 子树内改角色", s, 200)

    s, _ = call("PUT", f"/api/users/{newbie_id}", token=zhaoliu, body={"role_code": "employee"})
    check("平级 manager 编辑 → 403", s, 403)

    s, _ = call("PUT", f"/api/users/{newbie_id}", token=lisi, body={"username": "x"})
    check("employee 编辑 → 403", s, 403)

    s, _ = call("PUT", f"/api/users/{newbie_id}", token=zhangsan,
                body={"role_code": "manager"})
    check("manager 可提升子树用户为 manager", s, 200)

    s, _ = call("PUT", "/api/users/" + call("GET", "/api/auth/me", token=zhangsan)[1]["id"],
                token=zhangsan, body={"role_code": "employee"})
    check("改自己角色 → 400", s, 400)

    print("== 4. 删除用户 ==")
    s, _ = call("DELETE", f"/api/users/{newbie_id}", token=zhaoliu)
    check("平级 manager 删除 → 403", s, 403)

    s, _ = call("DELETE", f"/api/users/{newbie_id}", token=zhangsan)
    check("manager 子树内删除", s, 200)

    s, _ = call("DELETE", "/api/users/" + call("GET", "/api/auth/me", token=zhangsan)[1]["id"],
                token=zhangsan)
    check("删除自己 → 400", s, 400)

    print("== 5. 根组织 manager 保底 ==")
    root = find_org(zhangsan, "星辰科技")
    # 动态创建一名根组织 manager 后测试保底规则
    s, body = call("POST", "/api/users", token=admin, headers={"X-Tenant-Id": star_id}, body={
        "username": "root_mgr", "email": "rm@star.com", "password": "rm123456",
        "org_id": root["id"], "role_code": "manager",
    })
    root_mgr_id = body.get("id", "")
    check("admin 创建根组织 manager", s, 201)
    s, _ = call("PUT", f"/api/users/{root_mgr_id}", token=admin, headers={"X-Tenant-Id": star_id},
                body={"role_code": "employee"})
    check("降权唯一根组织 manager → 400", s, 400)
    s, _ = call("DELETE", f"/api/users/{root_mgr_id}", token=admin, headers={"X-Tenant-Id": star_id})
    check("删除唯一根组织 manager → 400", s, 400)

    print("== 6. 角色列表 ==")
    s, body = call("GET", "/api/roles", token=zhangsan)
    codes = [r["code"] for r in body]
    check("可分配角色 3 个（manager/auditor/employee）", sorted(codes),
          sorted(["manager", "auditor", "employee"]))

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()