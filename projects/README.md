# Projects

本目录包含所有项目，每个子目录为一个独立项目。

## 目录结构

每个项目目录遵循统一结构：

```
project-name/
├── README.md        # 项目说明（必填）
├── src/             # 源代码
├── docs/            # 设计文档 / 架构图
├── screenshots/     # 运行截图
├── requirements.txt # Python 依赖（或 package.json）
├── Dockerfile       # 容器化部署（可选）
└── .gitignore
```

## 项目清单

- [quick-analysis](./quick-analysis) — 电商数据快速分析
- [buyer-show-gen](./buyer-show-gen) — 买家秀自动生成
- [content-scraper](./content-scraper) — 电商内容抓取

## 新增项目

1. 在本目录下创建新文件夹，命名规则：`小写-连字符`（如 `price-tracker`）
2. 复制 [项目模板](#项目模板) 结构
3. 更新顶层 [README](../README.md) 的项目列表表格
