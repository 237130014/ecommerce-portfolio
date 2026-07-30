# Quick Analysis — 电商数据快速分析

## 简介

面向电商场景的快速数据分析工具，支持导入商品/订单/评论数据，进行多维度交叉分析并生成可视化报表。

## 技术栈

- **语言**: Python 3.11+
- **数据分析**: Pandas, NumPy
- **可视化**: Matplotlib, Plotly
- **Web 界面**: Streamlit / Gradio
- **数据存储**: SQLite（本地）/ PostgreSQL（可选）

## 核心功能

- [ ] CSV / Excel 数据导入与自动清洗
- [ ] 商品销量趋势分析
- [ ] 用户评论情感分析
- [ ] 多维度交叉报表生成
- [ ] 可视化图表导出（PNG / HTML）

## 技术亮点

> _待项目完成后补充_

## 项目结构

```
quick-analysis/
├── README.md
├── requirements.txt
├── src/
│   ├── data_loader.py    # 数据加载与清洗
│   ├── analyzer.py       # 分析引擎
│   ├── visualizer.py     # 可视化模块
│   └── app.py            # Web 界面入口
├── docs/
│   └── architecture.md
└── screenshots/
```

## 本地运行

```bash
cd projects/quick-analysis
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run src/app.py
```

## 运行截图

> _待补充_
