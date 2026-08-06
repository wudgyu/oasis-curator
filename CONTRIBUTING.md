# 🤝 贡献指南

> 感谢你愿意成为 Oasis Curator 绿洲里的一位共建者。每一份贡献，都让这座知识馆更完整。

## 🌿 我们的价值观

- **守护 (Preserve)** — 代码即文档，注重可读性与可维护性
- **策展 (Curate)** — PR 不在于多，而在于精；每一次合并都应该让代码库更好
- **引导 (Guide)** — 友善的 Review、清晰的反馈，是帮助新人最好的方式

## 🐛 报告 Bug

在 [Issues](../../issues) 中创建 Bug 报告，请包含：

- 清晰的问题描述
- 复现步骤（越具体越好）
- 预期行为 vs 实际行为
- 截图或日志（如有）
- 环境信息（OS、Python 版本、Docker 版本等）

## 💡 提议新能力

在 [Discussions](../../discussions) 中发起讨论，说明：

- 想解决什么问题
- 你的方案设计（接口、流程）
- 可能的替代方案
- 与现有模块的关系

## 🔧 提交代码

### 流程

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### Commit 规范

参考 Conventional Commits：

```
feat: 新增文档处理 Agent
fix: 修复多租户检索越权问题
docs: 补充 RAG 配置说明
refactor: 重构向量检索层
test: 为 IAM 生成器补充单元测试
chore: 升级依赖版本
```

### 代码规范

- **Python**: 遵循 PEP 8，使用 `ruff` + `mypy`
- **TypeScript**: 严格模式，禁止 `any`
- **测试**: 核心逻辑必须覆盖，新功能需附带测试
- **文档**: 公共 API 必须有 docstring / JSDoc

## 📖 改进文档

- 翻译、补全、纠错都欢迎
- 文档源文件位于 `docs/`
- 预览方式：本地启动后访问 `/docs`

## 🎨 品牌素材

Logo、配色、字体的优化建议请在 Discussions 中发起 `brand:` 前缀的话题。

---

> *每一份贡献，无论大小，都在为这座知识馆添砖加瓦。*
> *Oasis Curator · 守护知识，激活智慧。*
