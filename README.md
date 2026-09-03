# Ecommerce Portfolio

> 个人电商工具项目集 — 涵盖竞品监控、小红书热点监控、快速分析、买家秀生成、内容抓取等方向

## 关于

本仓库收录了我在电商领域的个人工具与技能，聚焦于解决实际业务场景中的效率与自动化问题。目前已落地两个工具：竞品新品监控、小红书热门笔记监控，另有多个方向的项目在规划中。

## 项目列表

| 项目 | 方向 | 技术栈 | 简介 | 状态 |
|------|------|--------|------|------|
| [competitor-new-product-monitor](./competitor-new-product-monitor) | 竞品监控 | Python / 浏览器自动化 | 抓取京东/天猫竞品新品，变动对比 + 瀑布流看板 | 已上线 |
| [xhs-hot-note-monitor](./xhs-hot-note-monitor) | 热点监控 | Python / Playwright | 小红书关键词近 7 天热门笔记抓取 + 瀑布流看板 | 已上线 |
| [quick-analysis](./projects/quick-analysis) | 数据分析 | Python / Pandas | 电商数据快速分析与可视化 | 规划中 |
| [buyer-show-gen](./projects/buyer-show-gen) | 内容生成 | Python / LLM API | 买家秀文案与图片自动生成 | 规划中 |
| [content-scraper](./projects/content-scraper) | 数据采集 | Python / Scrapy | 电商平台商品信息与评论抓取 | 规划中 |

## 技术亮点

- **竞品监控**：一键抓取京东/天猫竞品店铺新品，自动对比新增/涨价/降价/下架，生成花瓣网式瀑布流看板
- **热点监控**：小红书关键词搜索 + 「最多点赞/一周内」筛选，拦截接口拿结构化数据，自动下载封面图生成瀑布流看板
- **快速分析**：支持多维度交叉分析，一键生成可视化报表
- **买家秀生成**：结合 LLM 与商品信息，自动生成自然真实的买家评价内容
- **内容抓取**：分布式爬虫架构，支持反爬策略与数据清洗

## 快速开始

```bash
git clone https://github.com/237130014/ecommerce-portfolio.git
cd ecommerce-portfolio
```

每个项目的具体运行方式请参考对应目录下的 README。

## 联系方式

- GitHub: [@237130014](https://github.com/237130014)
- Email: _（待补充）_

## License

[MIT](./LICENSE)
