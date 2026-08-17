"""
数据库初始化种子数据

运行：python3 seed.py

创建默认租户和测试用户，用于开发阶段验证认证流程。
"""

from app.database import SessionLocal, engine, Base
from app.models.tenant import Tenant
from app.models.user import User
from app.core.security import hash_password

# 确保表已创建
Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    # 创建默认租户
    if db.query(Tenant).count() == 0:
        tenants = [
            Tenant(name="星辰科技", plan="enterprise", status="active"),
            Tenant(name="云端数据", plan="pro", status="active"),
            Tenant(name="智慧医疗", plan="basic", status="active"),
        ]
        db.add_all(tenants)
        db.flush()
        print(f"已创建 {len(tenants)} 个默认租户")

    # 创建测试用户
    if db.query(User).count() == 0:
        tenant_star = db.query(Tenant).filter(Tenant.name == "星辰科技").first()
        tenant_cloud = db.query(Tenant).filter(Tenant.name == "云端数据").first()
        tenant_med = db.query(Tenant).filter(Tenant.name == "智慧医疗").first()

        users = [
            User(
                username="admin",
                email="admin@star-tech.com",
                password_hash=hash_password("admin123"),
                tenant_id=tenant_star.id,
                role="admin",
                status="active",
            ),
            User(
                username="editor",
                email="editor@star-tech.com",
                password_hash=hash_password("editor123"),
                tenant_id=tenant_star.id,
                role="editor",
                status="active",
            ),
            User(
                username="viewer",
                email="viewer@star-tech.com",
                password_hash=hash_password("viewer123"),
                tenant_id=tenant_star.id,
                role="viewer",
                status="active",
            ),
            User(
                username="cloud_admin",
                email="admin@cloud-data.com",
                password_hash=hash_password("admin123"),
                tenant_id=tenant_cloud.id,
                role="admin",
                status="active",
            ),
            User(
                username="med_admin",
                email="admin@med-ai.com",
                password_hash=hash_password("admin123"),
                tenant_id=tenant_med.id,
                role="admin",
                status="disabled",
            ),
        ]
        db.add_all(users)
        db.flush()
        print(f"已创建 {len(users)} 个测试用户")

    db.commit()
    print("种子数据初始化完成")

    # 打印测试账号
    print("\n--- 测试账号 ---")
    all_users = db.query(User).all()
    for u in all_users:
        tenant = db.query(Tenant).filter(Tenant.id == u.tenant_id).first()
        print(f"  {u.username} / {u.role} @ {tenant.name} [{u.status}]")

finally:
    db.close()