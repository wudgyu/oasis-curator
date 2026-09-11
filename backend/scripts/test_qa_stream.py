"""
流式问答与会话历史自测脚本

运行：python3 scripts/test_qa_stream.py（需先启动后端、初始化种子数据、已上传示例文档）

覆盖：
- SSE 流式协议：meta（检索/重排序结果）→ token（逐字）→ done（引用）
- 会话落库：提问与回答均入库，标题取首个问题
- 续接会话：带 conversation_id 追问，消息累加到同一会话
- 拒答路径：文档外问题返回 refused=true 且无引用
- 会话归属隔离：他人会话 404、列表互不可见
- 会话删除：级联删除消息
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


def stream_ask(client: httpx.Client, headers: dict, question: str, conversation_id: str | None = None):
    """发起流式提问，返回 (事件列表, 事件名序列)"""
    payload = {"question": question}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    events = []
    name = None
    with client.stream(
        "POST", f"{BASE}/api/qa/ask/stream", headers=headers, json=payload, timeout=120
    ) as resp:
        assert resp.status_code == 200, resp.read().decode()
        for line in resp.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[len("data: ") :])))
    return events


def by_name(events, name):
    return [payload for evt, payload in events if evt == name]


def main() -> None:
    client = httpx.Client(timeout=120)
    h_zhang = login(client, "zhangsan", "zhangsan123")
    h_lisi = login(client, "lisi", "lisi123456")

    conv_id = None
    try:
        # ---------- 1. 流式协议 ----------
        print("\n[1] SSE 流式协议")
        events = stream_ask(client, h_zhang, "RAG 问答的重排序保留几个候选块？")
        names = [n for n, _ in events]
        check("首个事件为 meta", names[0], "meta")
        check("最后一个事件为 done", names[-1], "done")
        check("存在 token 事件", "token" in names, True)

        meta = by_name(events, "meta")[0]
        conv_id = meta["conversation_id"]
        check("meta 含会话 ID", bool(conv_id), True)
        check("meta 含重排序结果", len(meta["reranked"]) > 0, True)

        tokens = by_name(events, "token")
        streamed = "".join(t["text"] for t in tokens)
        done = by_name(events, "done")[0]
        check("token 拼接与最终答案一致", streamed, done["answer"])
        check("逐字粒度（token 数 > 5）", len(tokens) > 5, True)
        check("答案非拒答", done["refused"], False)
        check("答案含引用", len(done["citations"]) > 0, True)

        # ---------- 2. 会话落库 ----------
        print("\n[2] 会话落库与续接")
        convs = client.get(f"{BASE}/api/qa/conversations", headers=h_zhang).json()
        target = next((c for c in convs if c["id"] == conv_id), None)
        check("会话出现在列表中", target is not None, True)
        check("会话标题取首个问题", target["title"].startswith("RAG 问答的重排序"), True)
        check("消息数 = 2", target["message_count"], 2)

        detail = client.get(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_zhang).json()
        check("详情含 2 条消息", len(detail["messages"]), 2)
        check("首条为提问", detail["messages"][0]["role"], "user")
        check("次条为回答", detail["messages"][1]["role"], "assistant")
        check("回答携带引用", len(detail["messages"][1]["citations"]) > 0, True)

        # 续接同一会话
        events2 = stream_ask(client, h_zhang, "固定字符数切分的重叠是多少？", conv_id)
        check("续接会话沿用同一 ID", by_name(events2, "meta")[0]["conversation_id"], conv_id)
        detail2 = client.get(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_zhang).json()
        check("消息数累加为 4", len(detail2["messages"]), 4)

        # ---------- 3. 拒答路径 ----------
        print("\n[3] 拒答路径")
        events3 = stream_ask(client, h_zhang, "平台支持哪些数据库的 SQL 方言？")
        done3 = by_name(events3, "done")[0]
        check("拒答标记为 true", done3["refused"], True)
        check("拒答不含引用", done3["citations"], [])
        check("拒答不产生 token", len(by_name(events3, "token")), 0)

        # ---------- 4. 会话归属隔离 ----------
        print("\n[4] 会话归属隔离")
        check("他人访问会话 → 404", client.get(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_lisi).status_code, 404)
        check("他人删除会话 → 404", client.delete(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_lisi).status_code, 404)
        lisi_convs = client.get(f"{BASE}/api/qa/conversations", headers=h_lisi).json()
        check("他人列表不含该会话", any(c["id"] == conv_id for c in lisi_convs), False)

        # ---------- 5. 重命名与删除 ----------
        print("\n[5] 重命名与删除")
        renamed = client.patch(
            f"{BASE}/api/qa/conversations/{conv_id}", headers=h_zhang, json={"title": "重排序专题"}
        )
        check("重命名返回 200", renamed.status_code, 200)
        check("重命名生效", renamed.json()["title"], "重排序专题")

        deleted = client.delete(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_zhang)
        check("删除会话返回 200", deleted.status_code, 200)
        remaining = client.get(f"{BASE}/api/qa/conversations", headers=h_zhang).json()
        check("列表中已移除", any(c["id"] == conv_id for c in remaining), False)
        conv_id = None

    finally:
        if conv_id:
            client.delete(f"{BASE}/api/qa/conversations/{conv_id}", headers=h_zhang)
            print(f"      清理会话 {conv_id}")
        # 清理本次产生的其他会话（标题匹配测试问题）
        for c in client.get(f"{BASE}/api/qa/conversations", headers=h_zhang).json():
            if c["title"].startswith(("RAG 问答的重排序", "平台支持哪些数据库")):
                client.delete(f"{BASE}/api/qa/conversations/{c['id']}", headers=h_zhang)
                print(f"      清理会话 {c['id']}（{c['title'][:16]}）")

    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
