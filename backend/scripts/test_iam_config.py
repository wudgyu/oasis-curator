"""Unit tests for IAM config generator"""
import json
import sys
sys.path.insert(0, '.')

from app.core.iam_config import (
    _match_template,
    _extract_json,
    IamConfigGenerator,
    PRESET_TEMPLATES,
)

_generator = IamConfigGenerator()

# --- template matching ---
assert _match_template("我要全局只读") is not None, "全局只读 match"
assert _match_template("创建一个只读角色") is not None, "只读 match"
assert _match_template("审计员查看日志") is not None, "审计员 match"
assert _match_template("部门管理员") is not None, "部门管理 match"
assert _match_template("找一部电影看") is None, "no match"
print("template matching OK")

# --- JSON extraction ---
raw = '```json\n{"role": {"name": "test"}}\n```'
assert _extract_json(raw) == '{"role": {"name": "test"}}', "markdown code block extraction"

raw2 = '{"role": {"name": "test",},}'
extracted = _extract_json(raw2)
assert '"name": "test"' in extracted, "trailing comma removal"
assert "}," not in extracted, "trailing comma in object removed"

raw3 = '你好{"key": "value"}再见'
assert _extract_json(raw3) == '{"key": "value"}', "text extraction"

print("JSON extraction OK")

# --- Schema validation ---
valid_data = {
    "role": {"name": "测试", "code": "test", "description": "desc"},
    "permissions": [{"resource": "ecs", "actions": ["read"]}],
    "data_scope": {"type": "global"},
}
config = _generator._parse_and_validate(json.dumps(valid_data))
assert config.role.name == "测试"
assert config.role.code == "test"
assert config.permissions[0].resource == "ecs"
print("Schema validation OK")

# --- Schema rejection ---
invalid_data = {
    "role": {"name": "bad"},
    # missing permissions and data_scope
}
try:
    _generator._parse_and_validate(json.dumps(invalid_data))
    assert False, "should have raised ValidationError"
except Exception:
    pass
print("Schema rejection OK")

print("All unit tests passed")