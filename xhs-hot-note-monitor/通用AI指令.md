# 小红书热门笔记抓取 — 通用 AI 指令

> 这是一份**工具无关**的指令，任何 AI 编程助手 / Agent（WorkBuddy、Cursor、Claude Code、Copilot 等）都能执行。
> 让对方把下面「📋 复制这段」整段复制，粘贴发给他的 AI 助手即可。

---

## 📋 复制这段发给你的 AI 助手

```text
请帮我运行「小红书热门笔记抓取」工具，按以下步骤执行：

1. 克隆工具仓库（若本地已存在则跳过）：
   git clone https://github.com/237130014/ecommerce-portfolio.git

2. 进入目录 ecommerce-portfolio/xhs-hot-note-monitor，准备 Python 环境：
   - 若无 .venv 目录，执行：python -m venv .venv
   - 安装依赖：pip install -r requirements.txt
     （建议用国内镜像加速：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple）
   - 安装浏览器内核：playwright install chromium
   （以上命令请用 .venv 里的 python 执行；Windows 是 .venv\Scripts\python.exe，macOS/Linux 是 .venv/bin/python）

3. 我要抓取的关键词是：【在这里填你的关键词，例如：黄金项链、银饰耳环、珍珠手链】
   请把 references/keywords.json 里的 keywords 字段改成这些词（多个词用逗号分隔，保持 JSON 格式有效）。

4. 运行抓取（首次运行会自动弹出二维码，请让我用小红书 App 扫码登录）：
   python run.py

5. 抓取完成后，请把以下结果告诉我，并展示文件路径：
   - 网页看板：xhs-baseline/小红书热门笔记-日期.html
   - 明细表格：xhs-baseline/热门笔记明细.csv
```

---

## 📝 对方只需改一个地方

第 3 步里的 **【在这里填你的关键词】**，换成他想抓的词，其余原样复制。

---

## ✅ 为什么这样写能跨工具通用

- 全程是**标准命令行 + 通用步骤**，不依赖任何特定工具的专属能力。
- 不出现「WorkBuddy」「技能」等工具名词，任何会执行命令、读写文件的 AI 助手都能照做。
- 路径、命令都写成跨平台可识别形式（`python` / `.venv` 两种写法都标注）。

---

## ⚠️ 唯一需要本人做的

**首次扫码登录**——登录态绑定个人账号，AI 助手不能也不该代扫。扫码只需一次，之后自动复用。

---

## 💡 给「非技术」对方的极简版（可选）

如果对方连上面这段都嫌长，可以直接只发这一句：

```text
帮我把 GitHub 上的 ecommerce-portfolio 仓库里的 xhs-hot-note-monitor 工具跑起来，关键词抓【换成他的关键词】，按 README 里说的步骤来。
```

AI 助手会自己去看仓库 README 并执行。前提是对方的 AI 助手能访问 GitHub 和本地命令行。
