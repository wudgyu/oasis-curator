"""
IAM 角色管理 API 自测脚本

运行：python3 scripts/test_iam_roles_api.py（需先启动后端并初始化种子数据）

覆盖：
- 角色列表（内置 + 租户自定义）
- 保存自定义角色（新建 200 / 编码冲突 409 / 覆盖 200）
- 删除（自定义 200 / 内置 403 / 跨租户 403）
- 非 admin 访问 403
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


# 测试用角色配置（符合 IAM 生成器输出 Schema）
TEST_CONFIG = {
    "role": {
        "name": "测试只读角色",
        "code": "smoke_readonly",
        "description": "自测脚本创建的只读角色",
    },
    "permissions": [
        {"resource": "ecs", "actions": ["read", "list"]},
    ],
    "data_scope": {"type": "global"},
}

# 与内置角色同名的配置（用于覆盖场景）
OVERWRITE_CONFIG = {
    "role": {
        "name": "测试只读角色 v2",
        "code": "smoke_readonly",
        "description": "覆盖后的描述",
    },
    "permissions": [
        {"resource": "ecs", "actions": ["read", "list", "update"]},
    ],
    "data_scope": {"type": "by_location", "locations": ["beijing"]},
}


def main():
    admin = login("admin", "admin123")
    zhangsan = login("zhangsan", "zhangsan123")  # manager @ 研发部

    _, me = call("GET", "/api/auth/me", token=admin)
    # admin 无自身租户，用普通用户的租户作为上下文
    _, zs_me = call("GET", "/api/auth/me", token=zhangsan)
    tenant_id = zs_me["tenant"]["id"]
    admin_headers = {"X-Tenant-Id": tenant_id}

    print("\n1. 角色列表（内置 + 自定义）")
    s, roles = call("GET", "/api/iam/roles", token=admin, headers=admin_headers)
    check("admin 查询角色列表 200", s, 200)
    check("列表包含 4 个内置角色", len(roles), 4)

    print("\n2. 保存自定义角色")
    s, saved = call(
        "POST", "/api/iam/save-role",
        token=admin, headers=admin_headers, body={"config": TEST_CONFIG, "overwrite": False},
    )
    check("新建自定义角色 200", s, 200)
    check("返回角色编码", saved["code"], "smoke_readonly")
    check("未覆盖标记", saved["overwritten"], False)

    print("\n3. 编码冲突与覆盖")
    s, _ = call(
        "POST", "/api/iam/save-role",
        token=admin, headers=admin_headers, body={"config": TEST_CONFIG, "overwrite": False},
    )
    check("重复编码 409", s, 409)

    s, overwritten = call(
        "POST", "/api/iam/save-role",
        token=admin, headers=admin_headers, body={"config": OVERWRITE_CONFIG, "overwrite": True},
    )
    check("覆盖保存 200", s, 200)
    check("覆盖标记", overwritten["overwritten"], True)

    s, roles = call("GET", "/api/iam/roles", token=admin, headers=admin_headers)
    check("列表包含 5 个角色（4 内置 + 1 自定义）", len(roles), 5)
    custom = [r for r in roles if not r["builtin"]][0]
    check("自定义角色绑定租户", custom["tenant_id"], tenant_id)
    check("自定义角色含权限配置", len(custom["permissions"]), 1)
    check("覆盖后数据范围生效", custom["data_scope"]["type"], "by_location")

    print("\n4. 删除权限控制")
    s, _ = call(
        "DELETE", f"/api/iam/roles/{custom['id']}",
        token=zhangsan, headers=admin_headers,
    )
    check("manager 删除 403", s, 403)

    builtin_id = [r for r in roles if r["builtin"]][0]["id"]
    s, _ = call(
        "DELETE", f"/api/iam/roles/{builtin_id}",
        token=admin, headers=admin_headers,
    )
    check("删除内置角色 403", s, 403)

    s, _ = call(
        "DELETE", f"/api/iam/roles/{custom['id']}",
        token=admin, headers=admin_headers,
    )
    check("admin 删除自定义角色 200", s, 200)

    s, roles = call("GET", "/api/iam/roles", token=admin, headers=admin_headers)
    check("删除后回到 4 个内置角色", len(roles), 4)

    print("\n5. 非 admin 访问生成器")
    s, _ = call("GET", "/api/iam/templates", token=zhangsan, headers=admin_headers)
    check("manager 查模板 403", s, 403)

    print(f"\n{'=' * 50}")
    print(f"通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
