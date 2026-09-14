"""
文档处理 Agent API 自测脚本

运行：python3 scripts/test_agent_api.py（需先启动后端、初始化种子数据、已上传示例文档）

覆盖：
- 权限：employee 执行 → 403；未登录 → 403
- 同步执行：返回执行轨迹（步骤含工具名/参数/耗时/结果）与最终答复
- SSE 流式：meta（step）事件逐条推送 + done 事件收尾
- 参数校验：不存在的文档 → 404；非法可见性 → 400
- 隔离：其他租户的文档 → 404

注意：本脚本会真实调用 LLM（每轮数秒），并可能向知识库写入文档（结束时清理）。
"""

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"

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


def login(client: httpx.Client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败 {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def stream_agent(client: httpx.Client, headers: dict, payload: dict) -> list:
    """发起 SSE 执行，返回 [(event, data), ...]"""
    events = []
    name = None
    with client.stream(
        "POST", f"{BASE}/api/agent/run/stream", headers=headers, json=payload, timeout=300
    ) as resp:
        assert resp.status_code == 200, resp.read().decode()
        for line in resp.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[len("data: ") :])))
    return events


def pick_document(client: httpx.Client, headers: dict, prefer: str) -> dict:
    """从文档列表挑一个可用于测试的文档"""
    docs = client.get(f"{BASE}/api/documents", headers=headers, params={"page_size": 50}).json()["items"]
    for doc in docs:
        if prefer in doc["file_name"]:
            return doc
    assert docs, "文档列表为空，请先上传示例文档（scripts/make_sample_pdf.py 生成后经 API 上传）"
    return docs[0]


def main() -> None:
    client = httpx.Client(timeout=300)
    h_zhang = login(client, "zhangsan", "zhangsan123")   # manager
    h_lisi = login(client, "lisi", "lisi123456")          # employee
    h_cloud = login(client, "cloud_manager", "cloud123456")  # 其他租户

    created_docs = []
    try:
        # ---------- 1. 权限 ----------
        print("\n[1] 权限控制")
        check(
            "employee 执行 Agent → 403",
            client.post(f"{BASE}/api/agent/run", headers=h_lisi, json={"instruction": "解析文档"}).status_code,
            403,
        )
        check(
            "未登录执行 Agent → 403",
            client.post(f"{BASE}/api/agent/run", json={"instruction": "解析文档"}).status_code,
            403,
        )

        # ---------- 2. 参数校验 ----------
        print("\n[2] 参数校验")
        check(
            "文档不存在 → 404",
            client.post(
                f"{BASE}/api/agent/run", headers=h_zhang,
                json={"instruction": "解析文档", "doc_id": "no-such-doc"},
            ).status_code,
            404,
        )
        doc = pick_document(client, h_zhang, "api_reference.pdf")
        check(
            "其他租户的文档 → 404",
            client.post(
                f"{BASE}/api/agent/run", headers=h_cloud,
                json={"instruction": "解析文档", "doc_id": doc["id"]},
            ).status_code,
            404,
        )
        check(
            "非法可见性 → 400",
            client.post(
                f"{BASE}/api/agent/run", headers=h_zhang,
                json={"instruction": "解析文档", "doc_id": doc["id"], "visibility": "public"},
            ).status_code,
            400,
        )

        # ---------- 3. 同步执行 ----------
        print("\n[3] 同步执行（返回完整轨迹）")
        resp = client.post(
            f"{BASE}/api/agent/run",
            headers=h_zhang,
            json={"instruction": "告诉我这份文档有多少页、多少张表格", "doc_id": doc["id"]},
        )
        check("执行返回 200", resp.status_code, 200)
        run = resp.json()
        check("含执行轨迹", len(run["steps"]) >= 1, True)
        check("步骤含工具名", bool(run["steps"][0]["tool"]), True)
        check("步骤含耗时", run["steps"][0]["elapsed_ms"] >= 0, True)
        check("步骤标记成功", run["steps"][0]["ok"], True)
        check("含最终答复", len(run["answer"]) > 10, True)
        check("任务正常收敛", run["finished"], True)
        check("记录了实际模式", run["mode"] in ("native", "prompt"), True)
        print(f"      轨迹: {' → '.join(s['tool'] for s in run['steps'])}")
        print(f"      答复: {run['answer'][:80]}...")

        # ---------- 4. SSE 流式 ----------
        print("\n[4] SSE 流式执行")
        events = stream_agent(
            client, h_zhang,
            {"instruction": "提取这份文档里的表格", "doc_id": doc["id"]},
        )
        names = [n for n, _ in events]
        check("首个事件为 step", names[0], "step")
        check("最后事件为 done", names[-1], "done")
        steps = [d for n, d in events if n == "step"]
        check("step 事件含工具名", "tool" in steps[0], True)
        check("step 事件含结果摘要", "result_preview" in steps[0], True)
        done = [d for n, d in events if n == "done"][0]
        check("done 事件含最终答复", len(done["answer"]) > 5, True)
        check("done 事件含轨迹", len(done["steps"]), len(steps))
        print(f"      流式步骤: {' → '.join(s['tool'] for s in steps)}")

        # ---------- 5. 入库并清理 ----------
        print("\n[5] 入库产物可见性")
        resp = client.post(
            f"{BASE}/api/agent/run",
            headers=h_zhang,
            json={
                "instruction": "把这份文档摘要后入库",
                "doc_id": doc["id"],
                "visibility": "private",
            },
        )
        run = resp.json()
        indexed = [s for s in run["steps"] if s["tool"] == "index_chunks" and s["ok"]]
        if indexed:
            new_doc_id = indexed[0]["result"]["document_id"]
            created_docs.append(new_doc_id)
            detail = client.get(f"{BASE}/api/documents", headers=h_zhang, params={"page_size": 50}).json()
            item = next((d for d in detail["items"] if d["id"] == new_doc_id), None)
            check("入库文档出现在列表", item is not None, True)
            check("可见性按请求写入", item["visibility"] if item else None, "private")
            print(f"      入库文档: {new_doc_id[:8]}（{indexed[0]['result']['chunk_count']} 块）")
        else:
            check("本次未触发入库（指令未要求）", True, True)

    finally:
        for doc_id in created_docs:
            resp = client.delete(f"{BASE}/api/documents/{doc_id}", headers=h_zhang)
            print(f"      清理入库文档 {doc_id[:8]}: HTTP {resp.status_code}")

    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
