# Docs

存放跨项目的设计文档、架构图和技术笔记。

## 目录结构

```
docs/
├── README.md
├── architecture.md              # 仓库策略、项目规划、面试展示要点
└── bsk-browser-automation.md    # 抓取层技术栈：bsk 真实登录态浏览器自动化
```

## 抓取层技术栈

所有需要登录态的抓取工具（竞品监控、京东主图、得物热点）共用一套 bsk 抓取层，
完整讲解见 **[bsk-browser-automation.md](./bsk-browser-automation.md)**。

## 技术决策记录

记录重要技术选型的原因和上下文，便于回顾和讨论。已记录：

- [抓取层为什么用 bsk 而不是 headless](./bsk-browser-automation.md)
