"""
数据库初始化种子数据

运行：python3 seed.py

按 RBAC 权限模型初始化：
- 4 个内置全局角色（admin / manager / auditor / employee）
- 1 个平台管理员账号（tenant_id = NULL）
- 3 个租户，其中星辰科技含演示组织树与 4 类角色用户
"""

import uuid

from app.database import SessionLocal, engine, Base
from app.models.tenant import Tenant
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.core.security import hash_password

# 确保表已创建
Base.metadata.create_all(bind=engine)


def new_id() -> str:
    return str(uuid.uuid4())


def build_org(tenant_id: str, name: str, parent) -> Organization:
    """创建组织：ID 先生成，path 一次算好（物化路径依赖插入前可知 ID）"""
    org_id = new_id()
    path = f"{parent.path}{org_id}/" if parent else f"/{org_id}/"
    return Organization(
        id=org_id,
        tenant_id=tenant_id,
        parent_id=parent.id if parent else None,
        name=name,
        path=path,
    )


db = SessionLocal()

try:
    # ---------- 内置角色 ----------
    if db.query(Role).count() == 0:
        roles = [
            Role(code="admin", name="平台管理员", builtin=True),
            Role(code="manager", name="经理", builtin=True),
            Role(code="auditor", name="审计员", builtin=True),
            Role(code="employee", name="员工", builtin=True),
        ]
        db.add_all(roles)
        db.flush()
        print("已创建 4 个内置角色")
    role_admin = db.query(Role).filter(Role.code == "admin").first()
    role_manager = db.query(Role).filter(Role.code == "manager").first()
    role_auditor = db.query(Role).filter(Role.code == "auditor").first()
    role_employee = db.query(Role).filter(Role.code == "employee").first()

    # ---------- 平台管理员 ----------
    if db.query(User).filter(User.tenant_id.is_(None)).count() == 0:
        db.add(User(
            id=new_id(),
            username="admin",
            email="admin@oasis-curator.com",
            password_hash=hash_password("admin123"),
            tenant_id=None,
            org_id=None,
            role_id=role_admin.id,
            status="active",
        ))
        db.flush()
        print("已创建平台管理员账号 admin")

    # ---------- 租户 ----------
    if db.query(Tenant).count() == 0:
        db.add_all([
            Tenant(id=new_id(), name="星辰科技", plan="enterprise", status="active"),
            Tenant(id=new_id(), name="云端数据", plan="pro", status="active"),
            Tenant(id=new_id(), name="智慧医疗", plan="basic", status="active"),
        ])
        db.flush()
        print("已创建 3 个默认租户")
    tenant_star = db.query(Tenant).filter(Tenant.name == "星辰科技").first()
    tenant_cloud = db.query(Tenant).filter(Tenant.name == "云端数据").first()
    tenant_med = db.query(Tenant).filter(Tenant.name == "智慧医疗").first()

    # ---------- 组织树 ----------
    if db.query(Organization).count() == 0:
        # 星辰科技：根组织 → 研发部(后端组/前端组)、市场部
        root_star = build_org(tenant_star.id, "星辰科技", None)
        rd = build_org(tenant_star.id, "研发部", root_star)
        mkt = build_org(tenant_star.id, "市场部", root_star)
        be = build_org(tenant_star.id, "后端组", rd)
        fe = build_org(tenant_star.id, "前端组", rd)
        # 云端数据 / 智慧医疗：仅根组织
        root_cloud = build_org(tenant_cloud.id, "云端数据", None)
        root_med = build_org(tenant_med.id, "智慧医疗", None)

        db.add_all([root_star, rd, mkt, be, fe, root_cloud, root_med])
        db.flush()
        print("已创建组织树（星辰科技 5 组织 + 云端数据/智慧医疗根组织）")

        # ---------- 演示用户 ----------
        users = [
            # 星辰科技
            User(id=new_id(), username="zhangsan", email="zs@star-tech.com",
                 password_hash=hash_password("zhangsan123"), tenant_id=tenant_star.id,
                 org_id=rd.id, role_id=role_manager.id, status="active"),
            User(id=new_id(), username="lisi", email="ls@star-tech.com",
                 password_hash=hash_password("lisi123456"), tenant_id=tenant_star.id,
                 org_id=be.id, role_id=role_employee.id, status="active"),
            User(id=new_id(), username="wangwu", email="ww@star-tech.com",
                 password_hash=hash_password("wangwu123"), tenant_id=tenant_star.id,
                 org_id=root_star.id, role_id=role_auditor.id, status="active"),
            User(id=new_id(), username="zhaoliu", email="zl@star-tech.com",
                 password_hash=hash_password("zhaoliu123"), tenant_id=tenant_star.id,
                 org_id=mkt.id, role_id=role_manager.id, status="active"),
            # 云端数据
            User(id=new_id(), username="cloud_manager", email="cm@cloud-data.com",
                 password_hash=hash_password("cloud123456"), tenant_id=tenant_cloud.id,
                 org_id=root_cloud.id, role_id=role_manager.id, status="active"),
            # 智慧医疗
            User(id=new_id(), username="med_employee", email="me@med-ai.com",
                 password_hash=hash_password("med123456"), tenant_id=tenant_med.id,
                 org_id=root_med.id, role_id=role_employee.id, status="active"),
        ]
        db.add_all(users)
        db.flush()
        print(f"已创建 {len(users)} 个演示用户")

    db.commit()
    print("种子数据初始化完成")

    # ---------- 打印测试账号 ----------
    print("\n--- 测试账号 ---")
    for u in db.query(User).order_by(User.username).all():
        role = db.query(Role).filter(Role.id == u.role_id).first()
        if u.tenant_id is None:
            loc = "平台"
        else:
            tenant = db.query(Tenant).filter(Tenant.id == u.tenant_id).first()
            org = db.query(Organization).filter(Organization.id == u.org_id).first()
            loc = f"{tenant.name} / {org.name}"
        print(f"  {u.username:<14} {role.code:<9} @ {loc}")

finally:
    db.close()