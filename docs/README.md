# Onmyoji AutoBot V1.0 项目文档包

本目录用于作为 AI Agent / Claude Code / Codex 等开发 Agent 的项目上下文。

## 文档顺序

1. `01_PRD.md` — 产品需求
2. `02_TDD.md` — 技术设计
3. `03_Agent开发执行任务书.md` — 分阶段开发任务
4. `04_API接口定义.md` — 核心模块接口
5. `05_GUI设计文档.md` — GUI 设计
6. `06_Agent启动提示词.md` — Agent 启动开发提示词

## 推荐使用方式

将整个 docs 目录放入项目根目录：

```text
OnmyojiAutoBot/
├── docs/
├── src/
├── tests/
└── templates/
```

然后向 Agent 说明：

> 请先完整阅读 docs 目录中的 PRD、TDD、任务书和 API 文档。不要一次性生成整个项目。严格按照任务书，从 Task 001 开始，每完成一个任务运行测试并报告结果。

## 开发原则

稳定 → 可维护 → 可测试 → 可调试 → 可扩展 → 功能
