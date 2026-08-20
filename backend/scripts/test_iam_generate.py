"""End-to-end test: generate IAM configs with real LLM"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.core.iam_config import IamConfigGenerator

TEST_CASES = [
    "创建一个只读角色，只能看北京机房和上海机房的云主机资源",
    "我要一个全局只读",
    "帮我创建一个审计员角色，可以查看所有操作日志",
    "创建一个数据库管理员，管理杭州机房的所有数据库，还可以备份和恢复",
    "部门管理员，管理本部门的云主机和对象存储",
]


async def main():
    generator = IamConfigGenerator()

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n{'=' * 60}")
        print(f"测试 {i}/{len(TEST_CASES)}: {case}")
        print("=" * 60)

        config, metadata = await generator.generate(
            user_input=case,
            tenant_id="test-tenant",
            existing_role_codes=["auditor"],
        )

        print(json.dumps(json.loads(config.model_dump_json()), ensure_ascii=False, indent=2))
        print(f"metadata: {metadata}")


if __name__ == "__main__":
    asyncio.run(main())
