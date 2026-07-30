# Buyer Show Gen — 买家秀自动生成

## 简介

结合 LLM 与商品信息，自动生成自然真实的买家秀文案与配图，用于电商内容运营提效。

## 技术栈

- **语言**: Python 3.11+
- **LLM 调用**: OpenAI API / 本地模型 (Ollama)
- **图片处理**: Pillow, diffusers (Stable Diffusion)
- **Web 界面**: Gradio
- **数据存储**: SQLite

## 核心功能

- [ ] 商品信息输入（标题 / 类目 / 卖点）
- [ ] 买家秀文案生成（多种风格：真实/种草/测评）
- [ ] 配图生成（基于商品图的风格迁移 / AI 生图）
- [ ] 批量生成与导出
- [ ] 生成质量评分与人工微调

## 技术亮点

> _待项目完成后补充_

## 项目结构

```
buyer-show-gen/
├── README.md
├── requirements.txt
├── src/
│   ├── text_generator.py    # 文案生成模块
│   ├── image_generator.py   # 图片生成模块
│   ├── scorer.py            # 质量评分
│   └── app.py               # Web 界面入口
├── docs/
│   └── prompt_design.md
└── screenshots/
```

## 本地运行

```bash
cd projects/buyer-show-gen
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # 填入你的 API Key
python src/app.py
```

## 运行截图

> _待补充_
