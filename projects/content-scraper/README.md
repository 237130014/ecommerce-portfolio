# Content Scraper — 电商内容抓取

## 简介

分布式电商内容抓取工具，支持商品信息、价格监控、用户评论的自动化采集与清洗，具备反爬策略应对能力。

## 技术栈

- **语言**: Python 3.11+
- **爬虫框架**: Scrapy
- **反爬应对**: Playwright（无头浏览器）, fake-useragent
- **数据处理**: Pandas
- **任务调度**: Celery + Redis（可选）
- **数据存储**: SQLite / CSV / JSON

## 核心功能

- [ ] 多平台商品信息抓取（淘宝 / 京东 / 拼多多）
- [ ] 价格变动监控与预警
- [ ] 用户评论批量采集
- [ ] 数据自动清洗与去重
- [ ] 定时任务调度
- [ ] 代理 IP 轮换支持

## 技术亮点

> _待项目完成后补充_

## 项目结构

```
content-scraper/
├── README.md
├── requirements.txt
├── scrapy.cfg
├── src/
│   ├── spiders/              # 各平台爬虫
│   │   ├── taobao_spider.py
│   │   ├── jd_spider.py
│   │   └── pdd_spider.py
│   ├── pipelines/            # 数据处理管道
│   │   ├── clean_pipeline.py
│   │   └── export_pipeline.py
│   ├── middlewares/          # 中间件
│   │   ├── proxy middleware.py
│   │   └── useragent middleware.py
│   └── utils/
│       └── anti_detect.py    # 反检测工具
├── docs/
│   └── architecture.md
└── screenshots/
```

## 本地运行

```bash
cd projects/content-scraper
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# 抓取示例
scrapy crawl taobao -o output/taobao_items.json
```

## 运行截图

> _待补充_

## 注意事项

- 本项目仅供学习研究使用，请遵守各平台的 robots.txt 和服务条款
- 抓取频率请控制在合理范围，避免对目标网站造成压力
