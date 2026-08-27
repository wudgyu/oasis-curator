<div align="center">

<img src="./brand/logo/logo-primary.svg" alt="Oasis Curator" width="160" />

# 🌿 Oasis Curator · 绿洲馆长

### *Knowledge Preserved, Context Curated, Wisdom Guided*
**知识有归，脉络可循，疑问可解**

[![License: MIT](https://img.shields.io/badge/License-MIT-1A4D3E.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-1A4D3E.svg)](https://www.python.org/)
[![Vue 3](https://img.shields.io/badge/Vue-3-1A4D3E.svg)](https://vuejs.org/)
[![pnpm 8+](https://img.shields.io/badge/pnpm-8+-C9A84C.svg)](https://pnpm.io/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-C9A84C.svg)](./CONTRIBUTING.md)

*在信息的绿洲里，做一位递钥匙的馆长。*

[快速开始](#-快速开始) · [品牌故事](#-品牌故事) · [核心能力](#-核心能力) · [技术架构](#-技术架构) · [路线图](#-路线图) · [品牌视觉](./brand/README.md)

</div>

---

## 🌿 品牌故事

> *在《头号玩家》的绿洲世界里，博物馆的管理员奥格登·莫罗以"馆长"（The Curator）的身份守护着哈利迪的全部记忆。他不争、不抢、不炫耀权限，却总在关键时刻递上那把最对的钥匙。*

**Oasis Curator** 由此诞生 —— 它不是搜索引擎，不是问答机器人，而是一位真正意义上的**数字馆长**：

| 角色 | 使命 | 对应能力 |
|------|------|----------|
| 🏛️ **守护者** | 让每一条信息有源可溯、有权限可守 | 多租户隔离 + RBAC 权限 + 引用溯源 |
| 📚 **策展人** | 让碎片化的文档链接成有逻辑的脉络 | 智能切分 + 向量索引 + 多 Agent 验证 |
| 🗝️ **引路者** | 让模糊的问题在对话中走向清晰 | 流式问答 + 置信度分级 + 可点击引用 |


> **愿景：让每一份知识，都能被恰到好处地找到。**
---

## 💡 设计哲学

> *最好的知识工具，不是帮你翻遍所有书，而是替你选出最该读的那一本。*

Oasis Curator 的存在，是为了**让用户少翻几页、少点几次链接、少走几步弯路**。
它不追求炫技，而是追求在每一次交互中，递上**最对的那把钥匙**。

---

## ✨ 核心能力

### 🏛️ Knowledge Preserved — 知识有归

- 📄 **多格式文档入库**：PDF、TXT、Markdown 一键上传，自动解析切分（Word 支持规划中）
- 🔒 **多租户数据隔离**：向量元数据租户过滤 + API 层双重防护
- 🛡️ **细粒度权限控制**：文档可见性三级管理（租户公开 / 仅本人 / 指定角色）规划中
- 🔑 **统一认证授权**：JWT + RBAC 2.0，支持多端登录与 API Key 管理

### 📚 Context Curated — 脉络可循

- 🧩 **智能文档切分**：按段落 + 字符滑窗（重叠 100），保留语义边界
- 🔍 **语义检索 + 重排序**：Embedding 召回 Top-5，LLM 打分重排序取 Top-3
- 🤖 **文档处理 Agent**：上传混合文档（中英/含表格），LLM 自主编排解析/翻译/摘要/入库
- 🧠 **多 Agent 质量保障**：检索 → 生成 → 验证 → 融合，逐句防幻觉，置信度分级输出

### 🗝️ Wisdom Guided — 疑问可解

- 💬 **流式对话问答**：逐字输出，引用溯源可点击跳转
- 🎯 **自然语言配权**：IAM 配置生成器，自然语言 → RBAC 权限配置 JSON
- 🔌 **MCP 标准化接入**：将文档检索和问答能力暴露为 MCP 工具，对接 Agent 生态
- 🌗 **双模式部署**：云端（DeepSeek/Kimi）+ 离线（Ollama + Qwen + BGE）

> ✅ **RAG 后端管线（v0.4 前半）已完成**：文档上传 → 解析 → 切分 → Embedding
> （智谱 embedding-2 / Ollama bge-m3 / MiniLM 自动选择）→ ChromaDB 入库 →
> 检索 → LLM 重排序 → 生成带 `[来源: 文件名, 第N段]` 引用，文档外问题明确拒答。
> 评估脚本实测：召回率 100%、答案质量 100%、引用正确率 80%、多租户隔离 10/10。
> 前端文档上传页与问答页随 v0.4 后半（Day 26-27）交付。

---

## 🏗️ 技术架构

```mermaid
graph TB
    %% 认证授权层（统一底座）
    subgraph Auth["🔐 认证授权层（统一底座）"]
        direction LR
        AuthCore["<b>多租户管理 · RBAC 2.0</b><br/>JWT · API Key"]
    end

    %% AI 能力层
    subgraph AI["🧠 AI 能力层"]
        direction LR
        RAG["📚 <b>RAG 文档问答</b><br/>解析 → 切分 → 向量化 → 检索 → 重排 → 生成"]
        DocAgent["🤖 <b>文档处理 Agent</b><br/>LLM 自主编排：解析/翻译/摘要/入库"]
        QAAgent["🛡️ <b>RAG 质量保障 Agent</b><br/>检索 → 生成 → 验证 → 融合 · 防幻觉"]
        IAM["🎯 <b>IAM 配置生成器</b><br/>自然语言 → RBAC 权限配置 JSON"]
        MCP["🔌 <b>MCP 文档服务</b><br/>文档能力 → MCP Tools · 对接 Agent 生态"]
    end

    %% 部署层
    subgraph Deploy["🏗️ 部署层"]
        direction LR
        Cloud["☁️ <b>云端模式</b><br/>DeepSeek / Kimi API"]
        Offline["🌗 <b>离线模式</b><br/>Ollama + Qwen 2.5 + BGE-large-zh"]
        Docker["📦 <b>容器化</b><br/>Docker + Docker Compose"]
    end

    %% 依赖关系
    AI ==>|"鉴权 · 租户隔离 · RBAC"| Auth
    AI ==>|"运行 · 推理 · 部署"| Deploy

    %% 品牌色样式
    classDef authStyle fill:#1A4D3E,stroke:#1A4D3E,stroke-width:2px,color:#F5F0E8
    classDef aiStyle fill:#F5F0E8,stroke:#1A4D3E,stroke-width:2px,color:#1A4D3E
    classDef deployStyle fill:#C9A84C,stroke:#C9A84C,stroke-width:2px,color:#1A4D3E

    class AuthCore authStyle
    class RAG,DocAgent,QAAgent,IAM,MCP aiStyle
    class Cloud,Offline,Docker deployStyle
```

**技术栈速览：**

| 类别 | 技术选型 |
|------|----------|
| 前端 | Vue 3 · TypeScript · Element Plus · Pinia · pnpm |
| 后端 | Python 3.11+ · FastAPI · Pydantic · SQLAlchemy |
| AI 编排 | 手写 RAG 管线 · LangGraph / Function Calling（规划） |
| 向量库 | ChromaDB（Docker 服务端）· Milvus（规划） |
| LLM | DeepSeek · Kimi · Ark（多模型路由自动降级） |
| Embedding | 智谱 embedding-2 · Ollama bge-m3 · MiniLM（自动选择） |
| 协议 | MCP (Model Context Protocol)（规划） |
| 部署 | Docker · Docker Compose · SQLite/PostgreSQL |

---

## 🚀 快速开始

### 前置依赖

- Docker 20.10+ & Docker Compose v2+
- Node.js 18+ & pnpm 8+（前端开发）
- 4 核 CPU / 8GB 内存（最低配置）
- 离线模式额外需要：50GB 磁盘（用于存储本地模型）

> 💡 **包管理器选择**：前端使用 [pnpm](https://pnpm.io/) 而非 npm/yarn，原因是其磁盘空间利用率高、依赖解析严格、安装速度快。如未安装 pnpm，可执行 `npm install -g pnpm` 或使用 `corepack enable && corepack prepare pnpm@latest --activate`。

### ☁️ 云端模式（5 分钟可用）

```bash
# 1. 克隆仓库
git clone https://github.com/wudgyu/oasis-curator.git
cd oasis-curator

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY / KIMI_API_KEY / ZHIPU_API_KEY

# 3. 一键启动
docker compose -f docker-compose.cloud.yml up -d

# 4. 访问
open http://localhost:5173   # 前端
open http://localhost:8000/docs   # API 文档
```

### 🌗 离线模式（私有化部署）

```bash
# 1. 下载离线模型（首次约 30GB）
bash scripts/download_models.sh

# 2. 启动离线栈
DEPLOY_MODE=offline docker compose -f docker-compose.offline.yml up -d

# 3. 访问
open http://localhost:5173
```

### 🛠️ 本地开发

```bash
# 1. 后端：创建虚拟环境并安装依赖（必须使用项目 venv，勿用系统 Python）
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量（LLM API Key 等；.env 已在 .gitignore 中）
cp ../.env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY / KIMI_API_KEY / ZHIPU_API_KEY

# 3. 启动 ChromaDB 向量库（Docker，容器内 8000 映射到宿主机 18000）
docker run -d --name chromadb --restart unless-stopped -p 18000:8000 chromadb/chroma

# 4. 初始化 ChromaDB 命名空间（tenant=curator / database=oasis，幂等可重复执行）
python scripts/init_chroma.py

# 5. 初始化种子数据并启动服务
python seed.py                      # 初始化测试数据（3 租户 + 5 用户）
uvicorn app.main:app --reload       # 或 .venv/bin/uvicorn app.main:app --reload

# 6. 前端（使用 pnpm，API 请求经 Vite 代理转发至 :8000）
cd ../frontend
pnpm install
pnpm dev
```

> ⚠️ **常见坑：未用虚拟环境启动后端**。项目依赖（chromadb / pdfplumber 等）只安装在
> `backend/.venv` 中，若误用系统 Python 运行 `uvicorn`，应用会因缺少依赖反复加载失败，
> 8000 端口上没有真实服务，前端表现为 `/api` 请求 **502**。务必先
> `source .venv/bin/activate`，或直接使用 `.venv/bin/uvicorn`。

访问 `http://localhost:5173`，使用测试账号登录：

| 账号 | 密码 | 角色 | 租户 / 组织 |
|------|------|------|-------------|
| admin | admin123 | admin（平台管理员） | 平台（无租户归属） |
| zhangsan | zhangsan123 | manager（经理） | 星辰科技 / 研发部 |
| lisi | lisi123456 | employee（员工） | 星辰科技 / 研发部·后端组 |
| wangwu | wangwu123 | auditor（审计员） | 星辰科技 / 根组织 |
| zhaoliu | zhaoliu123 | manager（经理） | 星辰科技 / 市场部 |

> 🔐 **认证授权底座（已完成）**：本项目已完成阶段一 —— 统一认证授权基础设施，作为后续所有 AI 模块的底座：
> - **RBAC 权限模型**：平台 admin + 租户内固定角色（manager / auditor / employee），角色决定功能权限与数据范围（详见 `oasis-curator-rbac-model.md`）
> - **组织树管理**：租户内逐级组织树（物化路径实现子树查询），manager 可管理本组织及子组织
> - **数据范围**：employee 仅本组织；auditor / manager 本组织 + 子组织；admin 上下文租户全量
> - **JWT 认证**：登录签发 Token（24h 过期），接口通过 `Authorization: Bearer` 鉴权，角色变更实时生效
> - **多租户隔离**：普通用户唯一归属一个租户；admin 通过 `X-Tenant-Id` 切换工作区租户
> - **前后端联调**：Vue 3 前端已完全接入后端 API（组织树管理页、按角色渲染 UI、401 自动跳转）

---

## 🎬 演示场景

> *5 分钟体验馆长的全部能力*

```
🌿 场景 1：知识有归
→ 上传一份 50 页的产品手册 PDF
→ 系统自动解析 → 切分 → 向量化 → 入库（按租户隔离）
→ 提问："产品保修期是多久？" → 流式输出答案 + 引用跳转

📚 场景 2：脉络可循
→ 上传一份中英文混合、含表格的技术规范
→ 文档处理 Agent 自主决策：解析 → 提取表格 → 翻译 → 摘要 → 入库
→ 全过程可视化，可看到 Agent 思考与执行

🗝️ 场景 3：疑问可解
→ 提问一个刁钻问题，答案可能不明确
→ 多 Agent 质量保障管线启动：
   检索 → 生成 → 验证 → 融合
→ 最终输出：答案 + 置信度（高/中/低）+ 引用来源
→ 错误时低置信度拒答，不编造

🛡️ 场景 4：权限守护
→ 创建两个租户 A 和 B
→ A 上传机密文档，设为"仅本人可见"
→ B 租户的用户用相同问题提问 → 完全检索不到
→ 篡改请求中的 tenant_id → API 层 403 拒绝

🎯 场景 5：自然语言配权
→ 输入："创建一个只读角色，只能看北京和上海机房的云主机"
→ LLM 生成符合 RBAC 2.0 模型的权限配置 JSON
→ 前端 JSON 语法高亮预览 → 确认提交 → 入库持久化
→ 角色管理页面查看完整权限矩阵（权限列表 + 数据范围）
```

---

## 📂 项目结构

```
oasis-curator/
├── frontend/                  # Vue 3 前端（pnpm 管理）
│   ├── src/
│   │   ├── api/               # 类型化 API 层（auth / tenants / orgs / users / roles）
│   │   ├── components/        # AppLayout / UserTable / UserFormDialog / TenantTable / TenantFormDialog
│   │   ├── views/
│   │   │   ├── Login.vue              # 登录页（对接 /api/auth/login）
│   │   │   ├── Home.vue               # 首页仪表盘（按角色范围统计）
│   │   │   ├── OrgManagement.vue      # 组织管理（组织树 + 节点操作）
│   │   │   ├── UserManagement.vue     # 用户管理（服务端分页 + 数据范围 + 角色按钮控制）
│   │   │   └── TenantManagement.vue   # 租户管理（仅 admin）
│   │   ├── stores/           # Pinia stores（auth / user / tenant）
│   │   ├── utils/request.ts  # Axios 拦截器（Token + X-Tenant-Id 注入 + 401 跳转 + 统一错误提示）
│   │   ├── router/           # 路由 + 导航守卫（登录校验 + 角色校验）
│   │   └── types/            # TypeScript 类型定义
│   ├── package.json
│   └── pnpm-lock.yaml
│
├── backend/                   # FastAPI 后端
│   ├── app/
│   │   ├── api/              # 路由模块
│   │   │   ├── auth.py               # 登录 / 登出 / 当前用户 + 上下文租户依赖
│   │   │   ├── tenants.py            # 租户 CRUD（admin，自动建根组织）
│   │   │   ├── orgs.py               # 组织树 CRUD（移动防环 + 空组织删除约束）
│   │   │   ├── users.py              # 用户 CRUD（角色数据范围 + 根组织 manager 保底）
│   │   │   ├── roles.py              # 可分配角色列表
│   │   │   ├── documents.py          # 文档上传（解析→切分→向量化入库）/ 列表 / 删除 / 语义检索
│   │   │   └── qa.py                 # RAG 问答（检索→重排序→生成带引用）
│   │   ├── core/             # 核心模块
│   │   │   ├── config.py             # pydantic-settings 配置（LLM / Embedding / Chroma / 上传）
│   │   │   ├── security.py           # JWT 签发/校验 + bcrypt 密码哈希
│   │   │   ├── permission.py         # RBAC 权限判定层（DataScope + 子树校验 + 组织移动）
│   │   │   ├── llm_provider.py       # LLM 多模型路由（DeepSeek/Kimi/Ark + 自动降级 + 流式）
│   │   │   ├── doc_parser.py         # 文档解析（PDF 逐页提取 / TXT / Markdown，编码自适应）
│   │   │   ├── chunker.py            # 文档切分（固定字符滑窗 / 按段落合并，来源与页码标注）
│   │   │   ├── embedder.py           # Embedding（智谱 embedding-2 / Ollama bge-m3 / MiniLM）
│   │   │   ├── vector_store.py       # ChromaDB 封装（元数据租户过滤 + 余弦距离）
│   │   │   └── rag_pipeline.py       # 手写 RAG 管线（检索→LLM 重排序→拒答门控→生成引用）
│   │   ├── models/           # SQLAlchemy 模型（tenants / organizations / roles / users / documents）
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   └── main.py           # 应用入口（自动建表 + CORS）
│   ├── scripts/              # 自测与工具脚本（test_* / init_chroma / reset_chroma / demo_* / rag_chat / eval_rag）
│   ├── data/samples/         # 示例产品手册（Markdown 源 + PDF 生成脚本）
│   ├── seed.py               # 种子数据（平台管理员 + 3 租户 + 组织树 + 演示用户）
│   └── requirements.txt
│
├── scripts/
│   └── download_models.sh    # 离线模型下载脚本
│
├── docker-compose.cloud.yml
├── docker-compose.offline.yml
├── .env.example
├── LICENSE
└── README.md
```

---

## 🗺️ 路线图

- [x] **v0.1** · 认证授权底座（多租户 + RBAC + JWT）✅ 已完成
- [x] **v0.2** · LLM 多模型路由（DeepSeek / Kimi / Ark）✅ 已完成
- [x] **v0.3** · IAM 配置生成器（自然语言 → 权限配置 → 入库管理）✅ 已完成
- [ ] **v0.4** · RAG 文档问答（后端管线 ✅ 已完成；前端集成进行中）
- [ ] **v0.5** · 文档处理 Agent（Function Calling 自主编排）
- [ ] **v0.6** · 多 Agent 质量保障（LangGraph 防幻觉）
- [ ] **v0.7** · MCP 文档服务（标准化工具接入）
- [ ] **v1.0** · 双模式部署（云端 + 离线）+ 完整文档

---

## 🤝 贡献指南

欢迎任何形式的贡献：

- 🐛 **Bug 反馈**：在 Issues 中描述问题与复现步骤
- 🔧 **代码贡献**：Fork → 分支开发 → 提交 PR
- 📖 **文档改进**：翻译、补全、纠错都欢迎
- 🎨 **品牌素材**：Logo 优化、配色方案、新增应用场景

详见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)。

---

## 📄 开源协议

本项目采用 [MIT License](./LICENSE) 开源。

---

<div align="center">

**🌿 守护知识，激活智慧 🌿**

[回到顶部](#-oasis-curator--绿洲馆长)

</div>
